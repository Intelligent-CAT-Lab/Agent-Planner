"""
Run the pattern-resolution pipeline over all collected data. ``collect_pattern_resolution``
first replays trajectories into the tidy long table (one per agent/model/dataset), then
``analyze_pattern_resolution`` reads that table and writes the analysis JSON/markdown.
default agent: SWE-agent
default config: ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
Collect is itself CPU-bound and internally parallel (``--jobs``), so the collect tasks run
*sequentially* here — each gets the whole machine — rather than nesting pools and starving
every task of cores. Analyze is cheap and single-process, so those tasks run in parallel.
Analyze runs once per (model, dataset) with all target configs (the analyzer writes a single
multi-config report per table).
"""
import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple
from multiprocessing import Pool, cpu_count
from dataclasses import dataclass


# PID == process-group id of the collect task currently running (``start_new_session``
# makes the child a group leader), or None between tasks. A signal handler reads this to
# reap that group — the collect process AND its whole replay-worker pool — on interruption.
_active_pgid = None


def _reap(pgid: int) -> None:
    """SIGKILL an entire process group, tolerating an already-gone group."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_capture(cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
    """Run ``cmd`` capturing output, in its own process group.

    On timeout (or interruption) the whole group is killed, not just the launched
    process — a ``collect`` task spawns a ``ProcessPoolExecutor`` of replay workers, and
    killing only the parent (as ``subprocess.run(timeout=)`` does) leaves those workers
    as orphans that keep burning cores across later runs. ``start_new_session=True`` makes
    the child a group leader, so its pid doubles as the group id for :func:`_reap`.
    """
    global _active_pgid
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    _active_pgid = proc.pid  # == pgid (group leader); no getpgid race
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        _reap(proc.pid)
        proc.communicate()  # reap the killed group
        raise
    finally:
        _active_pgid = None


@dataclass
class AnalysisTask:
    """Represents a single analysis task."""
    agent: str
    model: str
    dataset: str
    step: str  # 'collect' or 'analyze'
    configs: List[str] = None  # target configs for the analyze step (one call, all configs)
    jobs: int = None  # replay parallelism for the collect step (passed to --jobs)


def long_table_path(agent: str, model: str, dataset: str) -> Path:
    """The long table collect writes for a given (agent, model, dataset)."""
    return (Path(__file__).resolve().parent / "analysis-results" / "pattern-resolution"
            / f"{agent}-{model}-{dataset}.long.json")


def run_collect_task(task: AnalysisTask) -> Tuple[bool, str]:
    """Run collect_pattern_resolution.py for a given agent/model/dataset."""
    script_path = Path(__file__).parent / "collect_pattern_resolution.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--agent", task.agent,
        "--model", task.model,
        "--dataset", task.dataset,
    ]
    if task.jobs:
        cmd += ["--jobs", str(task.jobs)]

    task_id = f"collect-{task.agent}-{task.model}-{task.dataset}"

    # 60 min: collects run one-at-a-time with the whole machine, so this is a safety
    # net, not the common case. run_capture kills the whole process group on timeout so
    # the replay worker pool can never outlive its parent as orphaned, core-hogging CPU.
    try:
        result = run_capture(cmd, timeout=3600)
        if result.returncode == 0:
            return True, f"✓ {task_id}"
        else:
            return False, f"✗ {task_id}\n  Error: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"✗ {task_id}\n  Error: Timeout after 60 minutes (worker group killed)"
    except Exception as e:
        return False, f"✗ {task_id}\n  Error: {str(e)[:200]}"


def run_analyze_task(task: AnalysisTask) -> Tuple[bool, str]:
    """Run analyze_pattern_resolution.py once for all target configs of a model/dataset."""
    script_path = Path(__file__).parent / "analyze_pattern_resolution.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--agent", task.agent,
        "--model", task.model,
        "--dataset", task.dataset,
        "--config", *task.configs,
    ]

    task_id = f"analyze-{task.agent}-{task.model}-{task.dataset}-[{','.join(task.configs)}]"

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
    parser.add_argument('--skip-collect', action='store_true',
                       help='Incremental collect: skip (model,dataset) pairs whose long '
                            'table already exists; still collect the missing ("new") ones')
    parser.add_argument('--skip-analyze', action='store_true',
                       help='Skip analysis step (JSON generation)')
    parser.add_argument('--workers', type=int, default=8,
                       help='Parallel workers for the analyze step (default: 8)')
    parser.add_argument('--collect-jobs', type=int, default=max(2, cpu_count() - 4),
                       help='Replay parallelism per collect task; collects run one at a '
                            'time, so this is the whole machine (default: cpu_count - 4)')

    args = parser.parse_args()

    # Free every spawned process on interruption, not just on normal exit (where the
    # `with Pool`/`with ProcessPoolExecutor` context managers already reap workers): reap
    # the in-flight collect group, then exit so those context managers still run.
    def _on_interrupt(signum, _frame):
        if _active_pgid is not None:
            _reap(_active_pgid)
        sys.exit(128 + signum)
    signal.signal(signal.SIGINT, _on_interrupt)
    signal.signal(signal.SIGTERM, _on_interrupt)

    # Determine number of workers for the analyze step
    num_workers = args.workers if args.workers is not None else max(1, cpu_count() - 1)

    print("="*80)
    print("ANALYSIS PIPELINE")
    print("="*80)
    print(f"Agent: {args.agent}")
    print(f"Models: {', '.join(args.models)}")
    print(f"Datasets: {', '.join(args.datasets)}")
    print(f"Analyze configs: {', '.join(args.configs)}")
    print(f"Analyze workers: {num_workers}")
    print(f"Collect jobs (per task): {args.collect_jobs}")
    print(f"Skip collect: {args.skip_collect}")
    print(f"Skip analyze: {args.skip_analyze}")
    print("="*80)

    # Step 1: Collect long tables. --skip-collect is incremental: skip (model,dataset)
    # pairs whose table already exists, but still collect the missing ("new") ones.
    # Collects are CPU-bound and internally parallel, so they run sequentially (each with
    # the whole machine via --collect-jobs) rather than nested in a pool that would starve
    # every task of cores and trip the per-task timeout.
    print("\n[STEP 1] Collecting data (long table generation)...")
    collect_tasks = [
        AnalysisTask(agent=args.agent, model=model, dataset=dataset, step='collect',
                     jobs=args.collect_jobs)
        for model in args.models
        for dataset in args.datasets
    ]
    if args.skip_collect:
        present = [t for t in collect_tasks
                   if long_table_path(t.agent, t.model, t.dataset).is_file()]
        collect_tasks = [t for t in collect_tasks
                         if not long_table_path(t.agent, t.model, t.dataset).is_file()]
        print(f"  --skip-collect: {len(present)} existing table(s) skipped, "
              f"{len(collect_tasks)} missing to collect")

    if collect_tasks:
        print(f"  Running {len(collect_tasks)} collection task(s) sequentially "
              f"(jobs={args.collect_jobs} each)...")
        success_count = 0
        for task in collect_tasks:
            success, msg = run_task_wrapper(task)
            print(f"  {msg}")
            success_count += int(success)

        print(f"\n  Collection: {success_count}/{len(collect_tasks)} task(s) succeeded")
        if success_count < len(collect_tasks):
            print("  Warning: Some collection tasks failed. Analysis may be incomplete.")
    else:
        print("  Nothing to collect — all requested tables already present.")

    # Step 2: Generate analysis tasks (JSON generation)
    if not args.skip_analyze:
        print("\n[STEP 2] Analyzing data (JSON generation)...")
        analyze_tasks = [
            AnalysisTask(agent=args.agent, model=model, dataset=dataset, step='analyze',
                         configs=args.configs)
            for model in args.models
            for dataset in args.datasets
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
