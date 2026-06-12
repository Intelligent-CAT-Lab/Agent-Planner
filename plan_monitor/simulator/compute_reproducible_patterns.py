#!/usr/bin/env python3
"""
Compute Reproducible Patterns across multiple runs.

Analyzes trajectory files across multiple runs to identify patterns
in rule triggers and outcomes, generating a CSV report.

Output CSV format:
- Row: instance_id
- Columns for each run_id:
  - outcome: resolved/unresolved
  - patterns: triggered rule types (concatenated by comma)
  - step: number of API calls
  - cost: instance cost
"""

from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Optional

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.simulator import mini_extractor, swe_extractor


def get_agent_base_dir(agent: str, dataset: str = "swebench", base_dir: Optional[Path] = None) -> Path:
    """Get the agent base directory."""
    if base_dir is None:
        current = Path(__file__).resolve()

        # Determine the directory name to search for
        if dataset == "swebench-pro" and agent == "SWE-agent":
            # For SWE-bench Pro, use SWE-bench_Pro-os/SWE-agent
            agent_dir_name = "SWE-bench_Pro-os/SWE-agent"
        else:
            # For regular swebench or mini-swe-agent, use agent name directly
            agent_dir_name = agent

        for parent in current.parents:
            # Handle nested path (e.g., "SWE-bench_Pro-os/SWE-agent")
            if "/" in agent_dir_name:
                parts = agent_dir_name.split("/")
                candidate = parent
                for part in parts:
                    candidate = candidate / part
            else:
                candidate = parent / agent_dir_name

            # For mini-swe-agent: check for "outputs", for SWE-agent: check for "trajectories"
            required_subdir = "outputs" if agent == "mini-swe-agent" else "trajectories"
            if candidate.exists() and (candidate / required_subdir).exists():
                return candidate

        raise ValueError(f"Could not find {agent_dir_name} directory. Please specify base_dir.")
    return Path(base_dir)


def load_report(report_path: Path, dataset: str = "swebench") -> Optional[Dict]:
    """
    Load report JSON file.

    For swebench-pro: eval_results.json contains dict mapping instance_id -> bool
    For standard: report contains 'resolved_ids' list
    """
    if not report_path.exists():
        return None
    try:
        with open(report_path, 'r') as f:
            data = json.load(f)

            # Check if this is SWE-bench Pro format (dict with bool values)
            if dataset == "swebench-pro" and isinstance(data, dict) and all(isinstance(v, bool) for v in data.values()):
                # Convert to standard format with 'resolved_ids' list
                resolved_ids = [inst_id for inst_id, is_resolved in data.items() if is_resolved]
                return {'resolved_ids': resolved_ids}

            # Standard format
            return data
    except Exception as e:
        print(f"Warning: Failed to load report {report_path}: {e}")
        return None


def find_report_file(
    agent_base: Path,
    config: str,
    dataset: str,
    model: str,
    run_id: str,
    sample_approach: Optional[str] = None
) -> Optional[Path]:
    """
    Find report file for a given run.

    Report path formats:
    - Standard: {agent}/reports/{config}/{dataset}/{model}/{model}.run_{run-id}.json
    - SWE-bench Pro: {agent}/reports/{config}/{dataset}/{sample-approach}/{model}/run-{run-id}/eval_results.json
    """
    # Check for SWE-bench Pro format first
    if sample_approach and dataset == "swebench-pro":
        # run_id may already have "run-" prefix, so normalize it
        if run_id.startswith("run-") or run_id.startswith("run_"):
            normalized_run_id = run_id
        else:
            normalized_run_id = f"run-{run_id}"

        pro_report_path = agent_base / "reports" / config / dataset / sample_approach / model / normalized_run_id / "eval_results.json"
        if pro_report_path.exists():
            return pro_report_path

    # Standard format
    reports_dir = agent_base / "reports" / config / dataset / model

    if not reports_dir.exists():
        return None

    # Try different run_id formats
    possible_names = [
        f"{model}.run_{run_id}.json",
        f"{model}.run-{run_id}.json",
        f"{model}.{run_id}.json",
    ]

    # Handle run_id that already has "run-" or "run_" prefix
    if run_id.startswith("run-") or run_id.startswith("run_"):
        run_num = run_id.split("-")[-1].split("_")[-1]
        possible_names.extend([
            f"{model}.run_{run_num}.json",
            f"{model}.run-{run_num}.json",
            f"{model}.{run_num}.json",
        ])

    for report_name in possible_names:
        report_path = reports_dir / report_name
        if report_path.exists():
            return report_path

    return None


def extract_instance_id(traj_path: Path) -> str:
    """Extract instance ID from trajectory path."""
    # Remove .traj.json extension
    stem = traj_path.stem.replace('.traj', '')
    if not stem or stem == '.traj':
        return traj_path.parent.name
    return stem


def process_trajectory(
    traj_path: Path,
    agent: str = "mini-swe-agent"
) -> Dict:
    """
    Process a single trajectory file to extract patterns and metadata.

    Args:
        traj_path: Path to .traj.json or .traj file
        agent: Agent type ("mini-swe-agent" or "SWE-agent")

    Returns:
        Dict with keys: instance_id, patterns, step, cost
    """
    try:
        # Load trajectory data
        with open(traj_path, 'r') as f:
            traj_data = json.load(f)

        instance_id = traj_data.get('instance_id', extract_instance_id(traj_path))

        # Extract model_stats from info field
        info = traj_data.get('info', {})
        model_stats = info.get('model_stats', {})
        api_calls = model_stats.get('api_calls', 0)
        instance_cost = model_stats.get('instance_cost', 0.0)

        # Process trajectory to detect rule triggers
        monitor = StatefulPhaseMonitor(enable_rules=True)

        # Choose appropriate extractor based on agent type
        if agent == "SWE-agent":
            extractor = swe_extractor.ActionExtractor(traj_path)
        else:  # mini-swe-agent
            extractor = mini_extractor.ActionExtractor(traj_path)

        # Track triggered rule types (categories)
        triggered_rule_types: Set[str] = set()

        # Process each action to detect rule triggers
        for event, thought, observation in extractor.extract_actions():
            result = monitor.check_step_pre_emptively(event, thought=thought)

            if result and result.rule_matches:
                for match in result.rule_matches:
                    # Categorize rule by type
                    rule_id = match.rule_id

                    if "plan_compliance" in rule_id:
                        triggered_rule_types.add("plan_compliance")
                    elif "dwell" in rule_id:
                        # Extract specific dwell type (e.g., dwell_L_navigate)
                        triggered_rule_types.add(rule_id)
                    elif "oscillation" in rule_id:
                        triggered_rule_types.add(rule_id)
                    elif "repeated" in rule_id:
                        triggered_rule_types.add(rule_id)
                    else:
                        triggered_rule_types.add(rule_id)

        return {
            'instance_id': instance_id,
            'patterns': sorted(triggered_rule_types),
            'step': api_calls,
            'cost': instance_cost
        }

    except Exception as e:
        print(f"Error processing {traj_path}: {e}")
        return {
            'instance_id': extract_instance_id(traj_path),
            'patterns': [],
            'step': 0,
            'cost': 0.0
        }


def collect_data(
    agent_base: Path,
    config: str,
    dataset: str,
    model: str,
    agent: str = "mini-swe-agent",
    sample_approach: Optional[str] = None
) -> Dict[str, Dict[str, Dict]]:
    """
    Collect data from all runs for a given configuration.

    Args:
        agent_base: Base directory for agent
        config: Config name
        dataset: Dataset name
        model: Model name
        agent: Agent type ("mini-swe-agent" or "SWE-agent")
        sample_approach: Sample approach (e.g., "python" for swebench-pro)

    Returns:
        Dict mapping instance_id -> run_id -> {outcome, patterns, step, cost}
    """
    # Different path structures for different agents
    if agent == "SWE-agent":
        outputs_dir = agent_base / "trajectories" / config / dataset
        # Add sample_approach to path if provided (for swebench-pro)
        if sample_approach:
            outputs_dir = outputs_dir / sample_approach
        outputs_dir = outputs_dir / model
    else:  # mini-swe-agent
        outputs_dir = agent_base / "outputs" / config / dataset / model

    if not outputs_dir.exists():
        raise ValueError(f"Directory not found: {outputs_dir}")

    # Find all run directories
    run_dirs = [d for d in outputs_dir.iterdir() if d.is_dir()]

    if not run_dirs:
        raise ValueError(f"No run directories found in {outputs_dir}")

    print(f"Found {len(run_dirs)} run directories")

    # Data structure: instance_id -> run_id -> data
    data: Dict[str, Dict[str, Dict]] = defaultdict(dict)

    for run_dir in sorted(run_dirs):
        run_id = run_dir.name
        print(f"\nProcessing run: {run_id}")

        # Load report for this run
        report_path = find_report_file(agent_base, config, dataset, model, run_id, sample_approach)

        resolved_ids: Set[str] = set()
        if report_path:
            report = load_report(report_path, dataset)
            if report:
                resolved_ids = set(report.get('resolved_ids', []))
                print(f"  Loaded report: {len(resolved_ids)} resolved instances")
        else:
            print(f"  Warning: No report found for run {run_id}")

        # Process all trajectory files in this run
        pattern = "**/*.traj" if agent == "SWE-agent" else "**/*.traj.json"
        traj_files = list(run_dir.glob(pattern))
        print(f"  Processing {len(traj_files)} trajectories")

        for traj_path in traj_files:
            result = process_trajectory(traj_path, agent=agent)
            instance_id = result['instance_id']

            # Determine outcome
            outcome = "resolved" if instance_id in resolved_ids else "unresolved"

            # Store data for this instance and run
            data[instance_id][run_id] = {
                'outcome': outcome,
                'patterns': ','.join(result['patterns']) if result['patterns'] else '',
                'step': result['step'],
                'cost': result['cost']
            }

    return data


def generate_csv(
    data: Dict[str, Dict[str, Dict]],
    output_path: Path,
    dataset: str,
    model: str
):
    """
    Generate CSV file from collected data.

    CSV format:
    instance_id, run1_outcome, run1_patterns, run1_step, run1_cost, run2_outcome, ...
    """
    # Get all run_ids (sorted)
    all_run_ids = set()
    for instance_data in data.values():
        all_run_ids.update(instance_data.keys())
    run_ids = sorted(all_run_ids)

    print(f"\nGenerating CSV with {len(data)} instances across {len(run_ids)} runs")

    # Create CSV header
    header = ['instance_id']
    for run_id in run_ids:
        header.extend([
            f'{run_id}_outcome',
            f'{run_id}_patterns',
            f'{run_id}_step',
            f'{run_id}_cost'
        ])

    # Write CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        # Write data rows (sorted by instance_id)
        for instance_id in sorted(data.keys()):
            row = [instance_id]

            for run_id in run_ids:
                if run_id in data[instance_id]:
                    run_data = data[instance_id][run_id]
                    row.extend([
                        run_data['outcome'],
                        run_data['patterns'],
                        run_data['step'],
                        f"{run_data['cost']:.6f}"
                    ])
                else:
                    # Missing data for this run
                    row.extend(['', '', '', ''])

            writer.writerow(row)

    print(f"\nCSV saved to: {output_path}")

    # Print summary statistics
    print_summary(data, run_ids)


def print_summary(data: Dict[str, Dict[str, Dict]], run_ids: List[str]):
    """Print summary statistics."""
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)

    print(f"\nTotal instances: {len(data)}")
    print(f"Total runs: {len(run_ids)}")

    for run_id in run_ids:
        resolved_count = 0
        unresolved_count = 0
        total_patterns = 0
        total_steps = 0
        total_cost = 0.0

        for instance_data in data.values():
            if run_id in instance_data:
                run_data = instance_data[run_id]
                if run_data['outcome'] == 'resolved':
                    resolved_count += 1
                else:
                    unresolved_count += 1

                if run_data['patterns']:
                    total_patterns += 1
                total_steps += run_data['step']
                total_cost += run_data['cost']

        total = resolved_count + unresolved_count
        if total > 0:
            print(f"\n[{run_id}]")
            print(f"  Instances: {total}")
            print(f"  Resolved: {resolved_count} ({resolved_count/total*100:.1f}%)")
            print(f"  Unresolved: {unresolved_count} ({unresolved_count/total*100:.1f}%)")
            print(f"  With patterns: {total_patterns} ({total_patterns/total*100:.1f}%)")
            print(f"  Avg steps: {total_steps/total:.1f}")
            print(f"  Total cost: ${total_cost:.2f}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compute reproducible patterns across multiple runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze SWE-agent (default)
  python plan_monitor/simulator/compute_reproducible_patterns.py --model gpt-5-mini

  # Analyze SWE-agent trajectories
  python plan_monitor/simulator/compute_reproducible_patterns.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench-pro --sample-approach python

  # Specify custom config and output path
  python plan_monitor/simulator/compute_reproducible_patterns.py --agent SWE-agent --config default --model deepseek-chat-v3-0324 --output results.csv
        """
    )

    parser.add_argument(
        '--agent',
        type=str,
        choices=['mini-swe-agent', 'SWE-agent'],
        default='SWE-agent',
        help='Agent type: mini-swe-agent or SWE-agent (default: SWE-agent)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='default',
        help='Config name (default: default)'
    )

    parser.add_argument(
        '--dataset',
        type=str,
        default='swebench',
        help='Dataset name (default: swebench)'
    )

    parser.add_argument(
        '--sample-approach',
        type=str,
        default=None,
        help='Sample approach (e.g., "python" for swebench-pro). If provided, path includes this directory level.'
    )

    parser.add_argument(
        '--model',
        type=str,
        required=True,
        help='Model name (e.g., gpt-5.4-mini, deepseek-chat-v3-0324)'
    )

    parser.add_argument(
        '--base-dir',
        type=Path,
        default=None,
        help='Base directory for agent outputs (default: auto-detect)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Output CSV path (default: stats/vanilla_reproducible_patterns/{dataset}_{agent}_{model}.csv)'
    )

    args = parser.parse_args()

    # Get agent base directory
    try:
        agent_base = get_agent_base_dir(args.agent, args.dataset, args.base_dir)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Agent base directory: {agent_base}")
    print(f"Config: {args.config}")
    print(f"Dataset: {args.dataset}")
    if args.sample_approach:
        print(f"Sample approach: {args.sample_approach}")
    print(f"Model: {args.model}")

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        # Default: stats/vanilla_reproducible_patterns/{dataset}_{agent}_{model}.csv
        output_path = Path("stats") / "vanilla_reproducible_patterns" / f"{args.dataset}_{args.agent}_{args.model}.csv"

    # Collect data
    try:
        data = collect_data(agent_base, args.config, args.dataset, args.model, agent=args.agent, sample_approach=args.sample_approach)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if not data:
        print("No data collected. Exiting.")
        return 1

    # Generate CSV
    generate_csv(data, output_path, args.dataset, args.model)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
