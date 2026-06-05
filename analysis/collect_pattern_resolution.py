"""
Scan the statistics of resolution outcome, patterns, cost, and steps, and compare the vanilla run (default run-1), vanilla rerun (default run-2), and refiner run.
Example output format: refer to Live-Plan Evaluation  - [SWE-agent]-[DS-V3]-[Verified].csv
Skip if the corresponding method data does not exist and leave the entry blank.
Collect and compute the report and traj files (refer to plan_monitor/simulator/compute_reproducible_patterns.py)
1 means true, 0 means false, and empty means data not available.
For example, for vanilla run-1, for the instance astropy__astropy-12907, the resolution is 1 (resolved), if any pattern exists, then has_issue should be 1, and the corresponding pattern types should be marked as 1, otherwise 0. record the cost and steps from the .traj file.

For the vanilla rerun (default run-2), additionally track the overlapping_issues (compared to run-1) as a list.
For the refiner run, additionally record the trigger status (whether the planner.json exists).
save the csv as {agent}-{model}-{dataset}.csv.
Example usage:
python analysis/collect_pattern_resolution.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench
"""
import json
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.simulator import swe_extractor


def load_report(agent_dir: Path, config: str, dataset: str, model: str, run_id: int, version: str = None) -> Set[str]:
    """Load resolved instance IDs from report file."""
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # For swebench-pro, report is eval_results.json in the run folder
    if dataset == 'swebench-pro':
        if config == 'refiner' and version:
            report_path = agent_dir / "reports" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}" / "eval_results.json"
        else:
            report_path = agent_dir / "reports" / config / dataset_path / model / f"run-{run_id}" / "eval_results.json"

        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    data = json.load(f)
                    # data is dict: instance_id -> bool (true=resolved)
                    return {inst_id for inst_id, resolved in data.items() if resolved}
            except Exception as e:
                print(f"Error loading report {report_path}: {e}")
        return set()

    # For swebench, report is in model directory
    if config == 'refiner' and version:
        reports_dir = agent_dir / "reports" / config / f"version-{version}" / dataset_path / model
    else:
        reports_dir = agent_dir / "reports" / config / dataset_path / model

    if not reports_dir.exists():
        return set()

    possible_names = [
        f"{model}.run_{run_id}.json",
        f"{model}.run-{run_id}.json",
        f"{model}.{run_id}.json",
    ]

    for name in possible_names:
        report_path = reports_dir / name
        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    data = json.load(f)
                    return set(data.get('resolved_ids', []))
            except Exception as e:
                print(f"Error loading report {report_path}: {e}")

    return set()


def phase_sequence_to_subscript(phases: List[str]) -> str:
    """
    Convert phase sequence to run-length encoded format with subscripts.

    Args:
        phases: List of phases (e.g., ['L_navigate', 'L_navigate', 'P', 'V'])

    Returns:
        Subscript-encoded string (e.g., 'L_navigate₂P₁V₁')
    """
    if not phases:
        return ''

    subscripts = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
    result = []
    prev_phase = None
    count = 0

    for phase in phases:
        if phase == prev_phase:
            count += 1
        else:
            if prev_phase is not None:
                result.append(f"{prev_phase}{str(count).translate(subscripts)}")
            prev_phase = phase
            count = 1

    if prev_phase is not None:
        result.append(f"{prev_phase}{str(count).translate(subscripts)}")

    return ''.join(result)


def process_trajectory(traj_path: Path) -> Dict:
    """
    Process trajectory file to extract patterns, cost, steps, langutory, and unique phases.

    Returns:
        Dict with keys: patterns, cost, steps, lang, unique_phases
    """
    try:
        with open(traj_path, 'r') as f:
            traj_data = json.load(f)

        # Extract cost and steps
        info = traj_data.get('info', {})
        model_stats = info.get('model_stats', {})
        api_calls = model_stats.get('api_calls', 0)
        instance_cost = model_stats.get('instance_cost', 0.0)

        # Detect patterns and extract langutory using monitor
        monitor = StatefulPhaseMonitor(enable_rules=True)
        extractor = swe_extractor.ActionExtractor(traj_path)

        triggered_patterns = {
            'plan_violation': False,
            'oscillation': False,
            'long_stagnation': False,
            'repeated_view': False
        }

        for event, thought, observation in extractor.extract_actions():
            result = monitor.check_step_pre_emptively(event, thought=thought)

            if result and result.rule_matches:
                for match in result.rule_matches:
                    rule_id = match.rule_id

                    if 'plan_compliance' in rule_id:
                        triggered_patterns['plan_violation'] = True
                    elif 'oscillation' in rule_id or 'cycle' in rule_id:
                        triggered_patterns['oscillation'] = True
                    elif 'dwell' in rule_id:
                        triggered_patterns['long_stagnation'] = True
                    elif 'repeated' in rule_id:
                        triggered_patterns['repeated_view'] = True

        # Get langutory sequence with subscripts and unique phases
        phase_history = monitor.get_phase_history()
        langutory = phase_sequence_to_subscript(phase_history)
        unique_phases = ','.join(monitor.get_unique_phases())

        return {
            'patterns': triggered_patterns,
            'cost': instance_cost,
            'steps': api_calls,
            'lang': langutory,
            'unique_phases': unique_phases
        }

    except Exception as e:
        print(f"Error processing {traj_path}: {e}")
        return {
            'patterns': {
                'plan_violation': False,
                'oscillation': False,
                'long_stagnation': False,
                'repeated_view': False
            },
            'cost': 0.0,
            'steps': 0,
            'lang': '',
            'unique_phases': ''
        }


def load_run_data(agent_dir: Path, config: str, dataset: str, model: str, run_id: int, version: str = None) -> Dict[str, Dict]:
    """
    Load data for a single run.

    Returns:
        Dict mapping instance_id -> {resolved, patterns, cost, steps, has_planner}
    """
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # Determine trajectory path based on config
    if config == 'default':
        traj_base = agent_dir / "trajectories" / "default" / dataset_path / model / f"run-{run_id}"
    elif config == 'refiner' and version:
        traj_base = agent_dir / "trajectories" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}"
    else:
        traj_base = agent_dir / "trajectories" / config / dataset_path / model / f"run-{run_id}"

    if not traj_base.exists():
        return {}

    # Load resolved IDs
    resolved_ids = load_report(agent_dir, config, dataset, model, run_id, version)

    data = {}
    for instance_dir in traj_base.iterdir():
        if not instance_dir.is_dir():
            continue

        instance_id = instance_dir.name
        traj_file = instance_dir / f"{instance_id}.traj"
        planner_file = instance_dir / f"{instance_id}.planner.json"

        if not traj_file.exists():
            continue

        # Process trajectory
        traj_result = process_trajectory(traj_file)

        data[instance_id] = {
            'resolved': instance_id in resolved_ids,
            'patterns': traj_result['patterns'],
            'lang': traj_result['lang'],
            'unique_phases': traj_result['unique_phases'],
            'cost': traj_result['cost'],
            'steps': traj_result['steps'],
            'has_planner': planner_file.exists()
        }

    return data


def compute_overlapping_issues(run1_patterns: Dict, run2_patterns: Dict) -> List[str]:
    """Compute overlapping pattern issues between two runs."""
    if not run1_patterns or not run2_patterns:
        return []

    overlaps = []
    pattern_names = ['plan_violation', 'oscillation', 'long_stagnation', 'repeated_view']

    for pattern in pattern_names:
        if run1_patterns.get(pattern, False) and run2_patterns.get(pattern, False):
            overlaps.append(pattern)

    return overlaps


def generate_csv(
    vanilla_run1: Dict[str, Dict],
    vanilla_run2: Dict[str, Dict],
    refiner_run: Dict[str, Dict],
    output_path: Path
):
    """Generate CSV file in the specified format."""
    # Determine which runs have data
    has_vanilla1 = bool(vanilla_run1)
    has_vanilla2 = bool(vanilla_run2)
    has_refiner = bool(refiner_run)

    # Get all instance IDs
    all_instances = set(vanilla_run1.keys()) | set(vanilla_run2.keys()) | set(refiner_run.keys())

    if not all_instances:
        print("Warning: No instances found in any run")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)

        # Build header rows dynamically based on available data
        header_row1 = ['Instance ID']
        header_row2 = ['']
        header_row3 = ['']

        if has_vanilla1:
            header_row1.extend(['Vanilla Run', '', '', '', '', '', '', '', '', '', ''])
            header_row2.extend(['Resolution \nStatus', 'Has Issue?', 'Trajecotry Issue', '', '', '', 'Lang', 'Unique Phases', 'Cost\n($)', 'Steps'])
            header_row3.extend(['', '', 'plan_violation', 'oscillation', 'long_stagnation', 'repeated view', '', '', '', ''])

        if has_vanilla2:
            header_row1.extend(['Vanilla Re-run', '', '', '', '', '', '', '', '', '', '', ''])
            header_row2.extend(['Resolution \nStatus', 'Has Issue?', 'Overlapping \nissues', 'Trajecotry Issue', '', '', '', 'Lang', 'Unique Phases', 'Cost\n($)', 'Steps'])
            header_row3.extend(['', '', '', 'plan_violation', 'oscillation', 'long_stagnation', 'repeated view', '', '', '', ''])

        if has_refiner:
            header_row1.extend(['Live-Plan Run', '', '', '', '', '', '', '', '', '', '', ''])
            header_row2.extend(['Trigger \nStatus', 'Resolution \nStatus', 'Has Issue?', 'Overlapping \nissues', 'Trajecotry Issue', '', '', '', 'Lang', 'Unique Phases', 'Cost\n($)', 'Steps'])
            header_row3.extend(['', '', '', '', 'plan_violation', 'oscillation', 'long_stagnation', 'repeated view', '', '', '', ''])

        # Write header rows
        writer.writerow(header_row1)
        writer.writerow(header_row2)
        writer.writerow(header_row3)

        # Write data rows
        for instance_id in sorted(all_instances):
            row = [instance_id]

            # Vanilla Run 1
            if has_vanilla1:
                if instance_id in vanilla_run1:
                    data = vanilla_run1[instance_id]
                    has_issue = 1 if any(data['patterns'].values()) else 0
                    row.extend([
                        1 if data['resolved'] else 0,
                        has_issue,
                        1 if data['patterns']['plan_violation'] else 0,
                        1 if data['patterns']['oscillation'] else 0,
                        1 if data['patterns']['long_stagnation'] else 0,
                        1 if data['patterns']['repeated_view'] else 0,
                        data['lang'],
                        data['unique_phases'],
                        f"{data['cost']:.6f}",
                        data['steps']
                    ])
                else:
                    row.extend(['', '', '', '', '', '', '', '', '', ''])

            # Vanilla Run 2 (Re-run)
            if has_vanilla2:
                if instance_id in vanilla_run2:
                    data = vanilla_run2[instance_id]
                    has_issue = 1 if any(data['patterns'].values()) else 0

                    # Compute overlapping issues with run 1
                    overlaps = []
                    if has_vanilla1 and instance_id in vanilla_run1:
                        overlaps = compute_overlapping_issues(
                            vanilla_run1[instance_id]['patterns'],
                            data['patterns']
                        )
                    overlapping_str = ','.join(overlaps) if overlaps else ''

                    row.extend([
                        1 if data['resolved'] else 0,
                        has_issue,
                        overlapping_str,
                        1 if data['patterns']['plan_violation'] else 0,
                        1 if data['patterns']['oscillation'] else 0,
                        1 if data['patterns']['long_stagnation'] else 0,
                        1 if data['patterns']['repeated_view'] else 0,
                        data['lang'],
                        data['unique_phases'],
                        f"{data['cost']:.6f}",
                        data['steps']
                    ])
                else:
                    row.extend(['', '', '', '', '', '', '', '', '', '', ''])

            # Refiner Run
            if has_refiner:
                if instance_id in refiner_run:
                    data = refiner_run[instance_id]
                    has_issue = 1 if any(data['patterns'].values()) else 0

                    # Compute overlapping issues with run 1
                    overlaps = []
                    if has_vanilla1 and instance_id in vanilla_run1:
                        overlaps = compute_overlapping_issues(
                            vanilla_run1[instance_id]['patterns'],
                            data['patterns']
                        )
                    overlapping_str = ','.join(overlaps) if overlaps else ''

                    row.extend([
                        1 if data['has_planner'] else 0,  # Trigger status
                        1 if data['resolved'] else 0,
                        has_issue,
                        overlapping_str,
                        1 if data['patterns']['plan_violation'] else 0,
                        1 if data['patterns']['oscillation'] else 0,
                        1 if data['patterns']['long_stagnation'] else 0,
                        1 if data['patterns']['repeated_view'] else 0,
                        data['lang'],
                        data['unique_phases'],
                        f"{data['cost']:.6f}",
                        data['steps']
                    ])
                else:
                    row.extend(['', '', '', '', '', '', '', '', '', '', '', ''])

            writer.writerow(row)

    print(f"\nCSV saved to: {output_path}")


def print_summary(vanilla_run1: Dict, vanilla_run2: Dict, refiner_run: Dict):
    """Print summary statistics."""
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)

    for name, data in [('Vanilla Run-1', vanilla_run1), ('Vanilla Run-2', vanilla_run2), ('Refiner Run', refiner_run)]:
        if not data:
            print(f"\n[{name}]: No data")
            continue

        resolved = sum(1 for d in data.values() if d['resolved'])
        with_issues = sum(1 for d in data.values() if any(d['patterns'].values()))
        total = len(data)
        avg_cost = sum(d['cost'] for d in data.values()) / total if total > 0 else 0
        avg_steps = sum(d['steps'] for d in data.values()) / total if total > 0 else 0

        print(f"\n[{name}]")
        print(f"  Total instances: {total}")
        print(f"  Resolved: {resolved} ({resolved/total*100:.1f}%)")
        print(f"  With patterns: {with_issues} ({with_issues/total*100:.1f}%)")
        print(f"  Avg cost: ${avg_cost:.6f}")
        print(f"  Avg steps: {avg_steps:.1f}")

        if name == 'Refiner Run':
            with_planner = sum(1 for d in data.values() if d['has_planner'])
            print(f"  With triggers: {with_planner} ({with_planner/total*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description='Compare resolution outcomes and patterns across vanilla and refiner runs'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent directory name (default: SWE-agent)')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., deepseek-chat-v3-0324)')
    parser.add_argument('--dataset', type=str, default='swebench',
                       help='Dataset name (default: swebench)')
    parser.add_argument('--vanilla-run1', type=int, default=1,
                       help='Vanilla run 1 ID (default: 1)')
    parser.add_argument('--vanilla-run2', type=int, default=2,
                       help='Vanilla run 2 (rerun) ID (default: 2)')
    parser.add_argument('--refiner-run', type=int, default=1,
                       help='Refiner run ID (default: 1)')
    parser.add_argument('--refiner-version', type=str, default='5',
                       help='Refiner version (default: 5)')
    parser.add_argument('--output', type=Path, default=None,
                       help='Output CSV path (default: analysis/analysis-results/{agent}-{model}-{dataset}.csv)')

    args = parser.parse_args()

    # Determine agent directory
    script_dir = Path(__file__).parent.parent
    if args.dataset == 'swebench':
        agent_dir = script_dir / args.agent
    elif args.dataset == 'swebench-pro':
        agent_dir = script_dir / "SWE-bench_Pro-os" / args.agent
    else:
        raise ValueError(f"Unknown dataset: {args.dataset}")

    if not agent_dir.exists():
        raise FileNotFoundError(f"Agent directory not found: {agent_dir}")

    print(f"Agent directory: {agent_dir}")
    print(f"Model: {args.model}")
    print(f"Dataset: {args.dataset}")

    # Load data for each run
    print(f"\nLoading Vanilla Run {args.vanilla_run1}...")
    vanilla_run1 = load_run_data(agent_dir, 'default', args.dataset, args.model, args.vanilla_run1)
    print(f"  Loaded {len(vanilla_run1)} instances")

    print(f"\nLoading Vanilla Run {args.vanilla_run2} (rerun)...")
    vanilla_run2 = load_run_data(agent_dir, 'default', args.dataset, args.model, args.vanilla_run2)
    if vanilla_run2:
        print(f"  Loaded {len(vanilla_run2)} instances")
    else:
        print(f"  No data found for vanilla run {args.vanilla_run2}")

    print(f"\nLoading Refiner Run {args.refiner_run} (version-{args.refiner_version})...")
    refiner_run = load_run_data(agent_dir, 'refiner', args.dataset, args.model, args.refiner_run, version=args.refiner_version)
    if refiner_run:
        print(f"  Loaded {len(refiner_run)} instances")
    else:
        print(f"  No data found for refiner run {args.refiner_run}")

    if not vanilla_run1 and not vanilla_run2 and not refiner_run:
        print("\nError: No data loaded for any run. Please check the paths and file availability.")
        return

    if not vanilla_run1:
        print("\nWarning: Vanilla Run 1 has no data. CSV will only contain available runs.")

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_dir = script_dir / "analysis" / "analysis-results" / "comparison"
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.agent}-{args.model}-{args.dataset}.csv"

    # Generate CSV
    generate_csv(vanilla_run1, vanilla_run2, refiner_run, output_path)

    # Print summary
    print_summary(vanilla_run1, vanilla_run2, refiner_run)


if __name__ == "__main__":
    main()
