"""
Generate Langutory for agent trajectories in a post-hoc manner for analysis.
default agent: SWE-agent
default config: ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
Read trajectory files (under {agent_dir}/trajectories/{config}/{dataset}(/python (if dataset == 'swebench-pro'))/{model}/run-{run_id}/),
extract actions step-by-step, build the Langutory.
Get resolution status from reports.
Langutory saved under similar structure (change 'trajectories' to 'langutory'), and filename to langutory.json (list).
Example entry:
  {
    "instance_id": "astropy__astropy-12907",
    "resolution_status": "resolved",
    "languatory": [
      "L_navigate_3",
      "L_reproduce_newly_generated_test_2",
      "P_1",
      "V_newly_generated_test_2"
    ],
    "compliance_score": {
      "s1_vocabulary": 1.0,
      "s2_coverage": 1.0,
      "s3_order": 1.0,
      "final_score": 1.0
    }
  }
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Set, List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from plan_monitor.commandParser import CommandParser
from analysis.lang_generator.buildLang import build_lang_sequence, build_lang_sequence_rle
from analysis.lang_generator.continuous_plan_compliance_score import compute_compliance_score


def get_resolution_status(report_path: Path, instance_id: str, dataset: str) -> str:
    """
    Get resolution status for an instance from the report.

    Args:
        report_path: Path to the report file
        instance_id: Instance ID to check
        dataset: Dataset name (swebench or swebench-pro)

    Returns:
        'resolved' or 'unresolved'
    """
    if not report_path.exists():
        return 'unresolved'

    try:
        with open(report_path) as f:
            report = json.load(f)

        if dataset == 'swebench-pro':
            # eval_results.json format: {instance_id: true/false}
            # resolved is true, all others are unresolved
            return 'resolved' if report.get(instance_id) is True else 'unresolved'
        else:
            # swebench format: has resolved_ids list
            # resolved is in "resolved_ids", all others are "unresolved"
            resolved_ids = set(report.get('resolved_ids', []))
            return 'resolved' if instance_id in resolved_ids else 'unresolved'

    except Exception:
        return 'unresolved'


def build_report_path(agent_dir: Path, config: str, version: int, dataset: str,
                      model: str, run_id: int) -> Path:
    """
    Build the report path based on configuration.

    Args:
        agent_dir: Base agent directory
        config: Config name
        version: Version number (for refiner/refiner-only)
        dataset: Dataset name
        model: Model name
        run_id: Run ID

    Returns:
        Path to the report file
    """
    if config in ["refiner", "refiner-only"]:
        base = agent_dir / "reports" / config / f"version-{version}" / dataset
    else:
        base = agent_dir / "reports" / config / dataset

    if dataset == "swebench-pro":
        base = base / "python"
        return base / model / f"run-{run_id}" / "eval_results.json"
    else:
        return base / model / f"{model}.run-{run_id}.json"


def process_instance(
    instance_dir: Path,
    report_path: Path,
    dataset: str,
    output_dir: Path,
    parser: CommandParser,
    use_rle: bool = True
) -> Optional[Dict]:
    """
    Process a single instance trajectory and generate langutory.

    Args:
        instance_dir: Directory containing the instance trajectory
        report_path: Path to the report file
        dataset: Dataset name
        output_dir: Output directory for langutory
        parser: CommandParser instance
        use_rle: Whether to use run-length encoding

    Returns:
        Dictionary with instance_id, resolution_status, langutory, and compliance_score
    """
    instance_id = instance_dir.name
    traj_file = instance_dir / f"{instance_id}.traj"

    if not traj_file.exists():
        return None

    try:
        # Load trajectory JSON directly
        with open(traj_file, 'r', encoding='utf-8') as f:
            traj_data = json.load(f)

        trajectory = traj_data.get('trajectory', [])
        if not trajectory:
            return None

        # Parse actions directly from trajectory steps
        step_nodes = []
        step_index = 1

        for step in trajectory:
            if not isinstance(step, dict):
                continue

            action = step.get('action', '')
            if not action:
                continue

            # Parse action into nodes
            parsed_commands = parser.parse(action)

            for parsed in parsed_commands:
                if parsed.get('__complex__'):
                    node = {
                        'tool': None,
                        'command': parsed.get('command'),
                        'subcommand': None,
                        'args': {},
                        'flags': {'__complex__': True}
                    }
                elif parsed.get('tool'):
                    node = {
                        'tool': parsed.get('tool'),
                        'command': None,
                        'subcommand': parsed.get('subcommand'),
                        'args': parsed.get('args', {}),
                        'flags': {}
                    }
                else:
                    node = {
                        'tool': None,
                        'command': parsed.get('command'),
                        'subcommand': None,
                        'args': parsed.get('args', []),
                        'flags': parsed.get('flags', {})
                    }

                step_nodes.append((step_index, node))

            step_index += 1

        # Build lang sequence
        if use_rle:
            roles, lens = build_lang_sequence_rle(step_nodes)
            # Format with counts: L_navigate_3 means 3 consecutive L_navigate
            langutory = [
                f"{role}_{count}" if count > 1 else role
                for role, count in zip(roles, lens)
            ]
        else:
            langutory = build_lang_sequence(step_nodes)

        # Get resolution status
        resolution_status = get_resolution_status(report_path, instance_id, dataset)

        # Compute compliance score with default expected order
        expected_order = ("L_navigate", "L_reproduce", "P", "V")
        score = compute_compliance_score(langutory, expected_order)

        return {
            'instance_id': instance_id,
            'resolution_status': resolution_status,
            'langutory': langutory,
            'compliance_score': {
                's1_vocabulary': score.s1_vocabulary,
                's2_coverage': score.s2_coverage,
                's3_order': score.s3_order,
                'final_score': score.final_score
            }
        }

    except Exception as e:
        print(f"Error processing {instance_id}: {e}")
        return None


def process_instance_wrapper(args):
    """Wrapper for multiprocessing."""
    instance_dir, report_path, dataset, output_dir, tool_yamls, use_rle = args

    # Create parser in worker process
    parser = CommandParser()
    if tool_yamls:
        parser.load_tool_yaml_files(tool_yamls)

    return process_instance(instance_dir, report_path, dataset, output_dir, parser, use_rle)


def process_config(
    agent_dir: Path,
    config: str,
    version: int,
    dataset: str,
    model: str,
    run_id: int,
    tool_yamls: List[str],
    num_workers: int = 8,
    use_rle: bool = True
):
    """
    Process all instances for a specific configuration.

    Args:
        agent_dir: Base agent directory
        config: Config name
        version: Version number
        dataset: Dataset name
        model: Model name
        run_id: Run ID
        tool_yamls: List of tool YAML file paths
        num_workers: Number of parallel workers
        use_rle: Whether to use run-length encoding
    """
    # Build trajectory directory path
    if config in ["refiner", "refiner-only"]:
        traj_base = agent_dir / "trajectories" / config / f"version-{version}" / dataset
    else:
        traj_base = agent_dir / "trajectories" / config / dataset

    if dataset == "swebench-pro":
        traj_base = traj_base / "python"

    traj_dir = traj_base / model / f"run-{run_id}"

    if not traj_dir.exists():
        print(f"  Trajectory directory not found: {traj_dir}")
        return

    # Build report path
    report_path = build_report_path(agent_dir, config, version, dataset, model, run_id)

    # Build output directory
    if config in ["refiner", "refiner-only"]:
        output_base = agent_dir / "langutory" / config / f"version-{version}" / dataset
    else:
        output_base = agent_dir / "langutory" / config / dataset

    if dataset == "swebench-pro":
        output_base = output_base / "python"

    output_dir = output_base / model / f"run-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get all instance directories
    instance_dirs = [d for d in traj_dir.iterdir() if d.is_dir()]

    if not instance_dirs:
        print(f"  No instances found in {traj_dir}")
        return

    print(f"  Processing {len(instance_dirs)} instances...")

    # Prepare arguments for workers
    worker_args = [
        (instance_dir, report_path, dataset, output_dir, tool_yamls, use_rle)
        for instance_dir in instance_dirs
    ]

    # Process instances in parallel
    results = []
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_instance_wrapper, args): args[0]
                  for args in worker_args}

        for future in tqdm(as_completed(futures), total=len(futures), desc="  Instances"):
            result = future.result()
            if result:
                results.append(result)

    # Save results
    output_file = output_dir / "langutory.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"  Saved {len(results)} langutories to {output_file}")

    # Print statistics
    resolved = sum(1 for r in results if r['resolution_status'] == 'resolved')
    unresolved = sum(1 for r in results if r['resolution_status'] == 'unresolved')

    print(f"  Resolution status: {resolved} resolved, {unresolved} unresolved")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Langutory for agent trajectories"
    )
    parser.add_argument("--agent", default="SWE-agent", help="Agent directory name")
    parser.add_argument("--datasets", nargs="+",
                       default=['swebench', 'swebench-pro'],
                       help="Datasets to process")
    parser.add_argument("--models", nargs="+",
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help="Models to process")
    parser.add_argument("--configs", nargs="+",
                       default=['default', 'sage', 'monitor', 'refiner-only', 'refiner'],
                       help="Configs to process")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    parser.add_argument("--version", type=int, default=5,
                       help="Version for refiner configs")
    parser.add_argument("--num-workers", type=int, default=8,
                       help="Number of parallel workers")
    parser.add_argument("--no-rle", action="store_true",
                       help="Disable run-length encoding (full sequence)")
    parser.add_argument("--tool-yamls", nargs="+",
                       help="Paths to tool YAML files (for SWE-agent tools)")

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent.parent.resolve()

    # Default tool YAMLs for SWE-agent if not specified
    if not args.tool_yamls:
        swe_agent_tools = base_dir / args.agent / "tools"
        if swe_agent_tools.exists():
            # Collect all config.yaml files from tools subdirectories
            args.tool_yamls = [str(p) for p in swe_agent_tools.rglob("config.yaml")]
        else:
            args.tool_yamls = []

    print(f"\n{'='*70}")
    print("Langutory Generation")
    print(f"{'='*70}")
    print(f"Agent:       {args.agent}")
    print(f"Datasets:    {args.datasets}")
    print(f"Models:      {args.models}")
    print(f"Configs:     {args.configs}")
    print(f"Run ID:      {args.run_id}")
    print(f"Version:     {args.version}")
    print(f"Workers:     {args.num_workers}")
    print(f"RLE:         {not args.no_rle}")
    print(f"Tool YAMLs:  {len(args.tool_yamls)} files")
    print(f"{'='*70}\n")

    for dataset in args.datasets:
        # Determine agent directory
        if dataset == "swebench":
            agent_dir = base_dir / args.agent
        elif dataset == "swebench-pro":
            agent_dir = base_dir / "SWE-bench_Pro-os" / args.agent
        else:
            print(f"Unknown dataset: {dataset}")
            continue

        print(f"\n{'='*70}")
        print(f"Dataset: {dataset}")
        print(f"Agent directory: {agent_dir}")
        print(f"{'='*70}\n")

        for model in args.models:
            print(f"\nModel: {model}")

            for config in args.configs:
                print(f"\n  Config: {config}")

                try:
                    process_config(
                        agent_dir,
                        config,
                        args.version,
                        dataset,
                        model,
                        args.run_id,
                        args.tool_yamls,
                        args.num_workers,
                        use_rle=not args.no_rle
                    )
                except Exception as e:
                    print(f"  Error processing {config}: {e}")
                    import traceback
                    traceback.print_exc()

    print(f"\n{'='*70}")
    print("Langutory Generation Complete!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
