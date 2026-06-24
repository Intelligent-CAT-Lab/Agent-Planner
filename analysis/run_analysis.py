"""
Run analysis for all the collected data. Use collect_pattern_resolution to generate the csv first, then use analyze_pattern_resolution to generate the analysis json.
default agent: SWE-agent
default config: ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
Run efficiently in parallel using multiprocessing.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple
from multiprocessing import Pool, cpu_count
from dataclasses import dataclass


@dataclass
class AnalysisTask:
    """Represents a single analysis task."""
    agent: str
    model: str
    dataset: str
    step: str  # 'collect' or 'analyze'
    config: str = None  # For analyze step


def run_collect_task(task: AnalysisTask) -> Tuple[bool, str]:
    """Run collect_pattern_resolution.py for a given agent/model/dataset."""
    script_path = Path(__file__).parent / "collect_pattern_resolution.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--agent", task.agent,
        "--model", task.model,
        "--dataset", task.dataset
    ]

    task_id = f"collect-{task.agent}-{task.model}-{task.dataset}"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1200  # 20 minutes timeout
        )

        if result.returncode == 0:
            return True, f"✓ {task_id}"
        else:
            return False, f"✗ {task_id}\n  Error: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"✗ {task_id}\n  Error: Timeout after 20 minutes"
    except Exception as e:
        return False, f"✗ {task_id}\n  Error: {str(e)[:200]}"


def run_analyze_task(task: AnalysisTask) -> Tuple[bool, str]:
    """Run analyze_pattern_resolution.py for a given agent/model/dataset/config."""
    script_path = Path(__file__).parent / "analyze_pattern_resolution.py"

    # Determine version for refiner configs
    version_arg = []
    if task.config in ['refiner', 'refiner-only']:
        version_arg = ["--refiner-version", "5"]

    cmd = [
        sys.executable,
        str(script_path),
        "--agent", task.agent,
        "--model", task.model,
        "--dataset", task.dataset,
        "--config", task.config
    ] + version_arg

    task_id = f"analyze-{task.agent}-{task.model}-{task.dataset}-{task.config}"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )

        if result.returncode == 0:
            return True, f"✓ {task_id}"
        else:
            return False, f"✗ {task_id}\n  Error: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"✗ {task_id}\n  Error: Timeout after 10 minutes"
    except Exception as e:
        return False, f"✗ {task_id}\n  Error: {str(e)[:200]}"


def run_task_wrapper(task: AnalysisTask) -> Tuple[bool, str]:
    """Wrapper to dispatch tasks based on step type."""
    if task.step == 'collect':
        return run_collect_task(task)
    elif task.step == 'analyze':
        return run_analyze_task(task)
    else:
        return False, f"✗ Unknown step: {task.step}"


def main():
    parser = argparse.ArgumentParser(
        description='Run analysis pipeline for all collected data'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name (default: SWE-agent)')
    parser.add_argument('--models', type=str, nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='Model names (default: deepseek-chat-v3-0324 gemini-2.5-flash minimax-m2.5)')
    parser.add_argument('--datasets', type=str, nargs='+',
                       default=['swebench', 'swebench-pro'],
                       help='Dataset names (default: swebench swebench-pro)')
    parser.add_argument('--configs', type=str, nargs='+',
                       default=['monitor', 'refiner-only', 'refiner'],
                       help='Configs to analyze (default: monitor refiner-only refiner)')
    parser.add_argument('--skip-collect', action='store_false',
                       help='Skip collection step (CSV generation)')
    parser.add_argument('--skip-analyze', action='store_true',
                       help='Skip analysis step (JSON generation)')
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of parallel workers (default: 8)')

    args = parser.parse_args()

    # Determine number of workers
    if args.workers is not None:
        num_workers = args.workers
    else:
        num_workers = max(1, cpu_count() - 1)

    print("="*80)
    print("ANALYSIS PIPELINE")
    print("="*80)
    print(f"Agent: {args.agent}")
    print(f"Models: {', '.join(args.models)}")
    print(f"Datasets: {', '.join(args.datasets)}")
    print(f"Analyze configs: {', '.join(args.configs)}")
    print(f"Workers: {num_workers}")
    print(f"Skip collect: {args.skip_collect}")
    print(f"Skip analyze: {args.skip_analyze}")
    print("="*80)

    all_tasks: List[AnalysisTask] = []

    # Step 1: Generate collection tasks (CSV generation)
    if not args.skip_collect:
        print("\n[STEP 1] Collecting data (CSV generation)...")
        collect_tasks = [
            AnalysisTask(agent=args.agent, model=model, dataset=dataset, step='collect')
            for model in args.models
            for dataset in args.datasets
        ]
        all_tasks.extend(collect_tasks)

        print(f"  Generated {len(collect_tasks)} collection tasks")

        # Run collection tasks in parallel
        with Pool(num_workers) as pool:
            results = pool.map(run_task_wrapper, collect_tasks)

        # Report results
        success_count = sum(1 for success, _ in results if success)
        for success, msg in results:
            print(f"  {msg}")

        print(f"\n  Collection: {success_count}/{len(collect_tasks)} tasks succeeded")

        if success_count < len(collect_tasks):
            print("  Warning: Some collection tasks failed. Analysis may be incomplete.")

    # Step 2: Generate analysis tasks (JSON generation)
    if not args.skip_analyze:
        print("\n[STEP 2] Analyzing data (JSON generation)...")
        analyze_tasks = [
            AnalysisTask(agent=args.agent, model=model, dataset=dataset, step='analyze', config=config)
            for model in args.models
            for dataset in args.datasets
            for config in args.configs
        ]

        print(f"  Generated {len(analyze_tasks)} analysis tasks")

        # Run analysis tasks in parallel
        with Pool(num_workers) as pool:
            results = pool.map(run_task_wrapper, analyze_tasks)

        # Report results
        success_count = sum(1 for success, _ in results if success)
        for success, msg in results:
            print(f"  {msg}")

        print(f"\n  Analysis: {success_count}/{len(analyze_tasks)} tasks succeeded")

    print("\n" + "="*80)
    print("PIPELINE COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
