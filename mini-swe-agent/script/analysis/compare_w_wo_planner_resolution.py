"""
This script compares the resolution rates of vanilla (no planner) vs a specific config (monitor or refiner) for a given model and run.
Example usage:
python compare_w_wo_planner_resolution.py \
  --config monitor \
  --model gpt-5-mini \
  --run-id 1 \
  --sample-approach reproducible_patterns \
  --pattern dwell \
  --reproducible
"""
import json
import argparse
from pathlib import Path
from collections import defaultdict


def load_sample_data(sample_approach: str, model: str, run_id: int, pattern: str = None) -> dict:
    """Load sampled instances with difficulty and original resolution status."""
    script_dir = Path(__file__).parent.parent
    if model:
        if pattern:
            sample_path = script_dir / "sample-data" / "samples" / sample_approach / "swebench" / model / pattern / "sampled_instances.json"
        else:
            sample_path = script_dir / "sample-data" / "samples" / sample_approach / "swebench" / model / str(run_id) / "sampled_instances.json"
    else:
        sample_path = script_dir / "sample-data" / "samples" / sample_approach / "swebench" / str(run_id) / "sampled_instances.json"
    with open(sample_path, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    return {s['instance_id']: {'difficulty': s['difficulty'], 'original_resolved': s['original_resolved']}
            for s in samples}


def load_config_report(config: str, model: str, run_id: int, version_id: str = None, pattern: str = None) -> dict:
    """Load config report (monitor or refiner)."""
    script_dir = Path(__file__).parent.parent.parent

    if version_id:
        report_path = script_dir / "reports" / config / f"version-{version_id}" / "swebench" / model / f"{model.split('/')[-1]}.run-{run_id}.json"
    elif pattern:
        report_path = script_dir / "reports" / config / "swebench" / pattern / model / f"{model.split('/')[-1]}.run-{run_id}.json"
    else:
        base_path = script_dir / "reports" / config / "swebench" / model

        # Try multiple naming patterns
        patterns = [
            f"{model.split('/')[-1]}.run-{run_id}.json",
            f"{model.split('/')[-1]}.{run_id}.json",
            f"{model.split('/')[-1]}.run_{run_id}.json",
        ]

        report_path = None
        for pattern in patterns:
            candidate = base_path / pattern
            if candidate.exists():
                report_path = candidate
                break

        if not report_path or not report_path.exists():
            raise FileNotFoundError(f"Report not found for {config}/{model}/run_{run_id}")

    with open(report_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compare_resolutions(sample_data: dict, config_report: dict, reproducible: bool, pattern: str = None):
    """Compare vanilla vs config resolution rates."""
    resolved_ids = set(config_report.get('resolved_ids', []))

    # Check if original_resolved is a list (multiple vanilla runs) or single value
    has_multiple_runs = False
    num_vanilla_runs = 1
    if reproducible and sample_data:
        first_sample = next(iter(sample_data.values()))
        if isinstance(first_sample['original_resolved'], list):
            has_multiple_runs = True
            num_vanilla_runs = len(first_sample['original_resolved'])

    difficulties = ['easy', 'medium', 'hard']

    if has_multiple_runs:
        # For multiple vanilla runs, track transitions for each run
        all_transitions = []
        for run_idx in range(num_vanilla_runs):
            transitions = {
                'resolved_to_resolved': defaultdict(list),
                'resolved_to_unresolved': defaultdict(list),
                'unresolved_to_resolved': defaultdict(list),
                'unresolved_to_unresolved': defaultdict(list),
            }

            for instance_id, data in sample_data.items():
                difficulty = data['difficulty']
                original_resolved = data['original_resolved'][run_idx]
                config_resolved = instance_id in resolved_ids

                if original_resolved and config_resolved:
                    transitions['resolved_to_resolved'][difficulty].append(instance_id)
                elif original_resolved and not config_resolved:
                    transitions['resolved_to_unresolved'][difficulty].append(instance_id)
                elif not original_resolved and config_resolved:
                    transitions['unresolved_to_resolved'][difficulty].append(instance_id)
                else:
                    transitions['unresolved_to_unresolved'][difficulty].append(instance_id)

            all_transitions.append(transitions)

        return all_transitions, sample_data
    else:
        # Single vanilla run (original logic)
        transitions = {
            'resolved_to_resolved': defaultdict(list),
            'resolved_to_unresolved': defaultdict(list),
            'unresolved_to_resolved': defaultdict(list),
            'unresolved_to_unresolved': defaultdict(list),
        }

        for instance_id, data in sample_data.items():
            difficulty = data['difficulty']
            original_resolved = data['original_resolved'] if reproducible else None
            config_resolved = instance_id in resolved_ids

            if reproducible:
                if original_resolved and config_resolved:
                    transitions['resolved_to_resolved'][difficulty].append(instance_id)
                elif original_resolved and not config_resolved:
                    transitions['resolved_to_unresolved'][difficulty].append(instance_id)
                elif not original_resolved and config_resolved:
                    transitions['unresolved_to_resolved'][difficulty].append(instance_id)
                else:
                    transitions['unresolved_to_unresolved'][difficulty].append(instance_id)

        return transitions, sample_data


def generate_report(config: str, model: str, run_id: int, transitions,
                   sample_data: dict, reproducible: bool, sample_approach: str = None, pattern: str = None):
    """Generate and save comparison report."""
    report = {
        'config': config,
        'model': model,
        'run_id': run_id,
        'reproducible': reproducible,
        'sample_approach': sample_approach,
        'pattern': pattern,
    }

    if reproducible:
        total = len(sample_data)

        # Check if we have multiple vanilla runs
        is_multiple_runs = isinstance(transitions, list)

        if is_multiple_runs:
            # Multiple vanilla runs - compare each run separately
            report['num_vanilla_runs'] = len(transitions)
            report['vanilla_runs_comparison'] = []

            for run_idx, run_transitions in enumerate(transitions):
                # Calculate stats for this vanilla run
                original_resolved = sum(1 for d in sample_data.values()
                                      if d['original_resolved'][run_idx])
                config_resolved = sum(len(run_transitions['resolved_to_resolved'][diff]) +
                                    len(run_transitions['unresolved_to_resolved'][diff])
                                    for diff in ['easy', 'medium', 'hard'])

                run_report = {
                    'vanilla_run_id': run_idx + 1,
                    'overall': {
                        'total_instances': total,
                        'vanilla_resolved': original_resolved,
                        'vanilla_rate': f"{original_resolved/total*100:.2f}%",
                        'config_resolved': config_resolved,
                        'config_rate': f"{config_resolved/total*100:.2f}%",
                    }
                }

                # Transitions by difficulty
                run_report['transitions_by_difficulty'] = {}
                for diff in ['easy', 'medium', 'hard']:
                    run_report['transitions_by_difficulty'][diff] = {
                        'resolved_to_resolved': len(run_transitions['resolved_to_resolved'][diff]),
                        'resolved_to_unresolved': len(run_transitions['resolved_to_unresolved'][diff]),
                        'unresolved_to_resolved': len(run_transitions['unresolved_to_resolved'][diff]),
                        'unresolved_to_unresolved': len(run_transitions['unresolved_to_unresolved'][diff]),
                    }

                # Instance details for key transitions
                run_report['resolved_to_unresolved_instances'] = [
                    {'instance_id': iid, 'difficulty': sample_data[iid]['difficulty']}
                    for diff in ['easy', 'medium', 'hard']
                    for iid in sorted(run_transitions['resolved_to_unresolved'][diff])
                ]

                run_report['unresolved_to_resolved_instances'] = [
                    {'instance_id': iid, 'difficulty': sample_data[iid]['difficulty']}
                    for diff in ['easy', 'medium', 'hard']
                    for iid in sorted(run_transitions['unresolved_to_resolved'][diff])
                ]

                report['vanilla_runs_comparison'].append(run_report)

        else:
            # Single vanilla run (original logic)
            original_resolved = sum(1 for d in sample_data.values() if d['original_resolved'])
            config_resolved = sum(len(transitions['resolved_to_resolved'][diff]) +
                                len(transitions['unresolved_to_resolved'][diff])
                                for diff in ['easy', 'medium', 'hard'])

            report['overall'] = {
                'total_instances': total,
                'vanilla_resolved': original_resolved,
                'vanilla_rate': f"{original_resolved/total*100:.2f}%",
                'config_resolved': config_resolved,
                'config_rate': f"{config_resolved/total*100:.2f}%",
            }

            # Transitions by difficulty
            report['transitions_by_difficulty'] = {}
            for diff in ['easy', 'medium', 'hard']:
                report['transitions_by_difficulty'][diff] = {
                    'resolved_to_resolved': len(transitions['resolved_to_resolved'][diff]),
                    'resolved_to_unresolved': len(transitions['resolved_to_unresolved'][diff]),
                    'unresolved_to_resolved': len(transitions['unresolved_to_resolved'][diff]),
                    'unresolved_to_unresolved': len(transitions['unresolved_to_unresolved'][diff]),
                }

            # Instance details for key transitions
            report['resolved_to_unresolved_instances'] = [
                {'instance_id': iid, 'difficulty': sample_data[iid]['difficulty']}
                for diff in ['easy', 'medium', 'hard']
                for iid in sorted(transitions['resolved_to_unresolved'][diff])
            ]

            report['unresolved_to_resolved_instances'] = [
                {'instance_id': iid, 'difficulty': sample_data[iid]['difficulty']}
                for diff in ['easy', 'medium', 'hard']
                for iid in sorted(transitions['unresolved_to_resolved'][diff])
            ]

    return report


def save_report(report: dict, output_dir: Path):
    """Save report to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    sample_approach_suffix = f"_{report['sample_approach']}" if report.get('sample_approach') else ""
    pattern_suffix = f"_{report['pattern']}" if report.get('pattern') else ""
    version_suffix = f"_version-{report.get('version_id', '')}" if report.get('version_id') else ""
    output_file = output_dir / f"{report['config']}_{report['model'].split('/')[-1]}_run{report['run_id']}{sample_approach_suffix}{pattern_suffix}{version_suffix}_comparison.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {output_file}")
    return output_file


def print_summary(report: dict):
    """Print summary to console."""
    print("\n" + "="*80)
    print(f"Comparison Report: {report['config'].upper()} vs Vanilla")
    print(f"Model: {report['model']}, Run: {report['run_id']}")
    if report.get('pattern'):
        print(f"Pattern: {report['pattern']}")
    print("="*80)

    if report['reproducible']:
        # Check if we have multiple vanilla runs
        if 'vanilla_runs_comparison' in report:
            # Multiple vanilla runs
            print(f"\nComparing against {report['num_vanilla_runs']} vanilla runs:")

            for run_data in report['vanilla_runs_comparison']:
                print("\n" + "-"*80)
                print(f"Vanilla Run #{run_data['vanilla_run_id']}")
                print("-"*80)

                overall = run_data['overall']
                print(f"\nOverall Resolution Rates:")
                print(f"  Vanilla: {overall['vanilla_resolved']}/{overall['total_instances']} ({overall['vanilla_rate']})")
                print(f"  {report['config'].capitalize()}: {overall['config_resolved']}/{overall['total_instances']} ({overall['config_rate']})")

                print(f"\nTransitions by Difficulty:")
                print(f"{'Difficulty':<12} {'R→R':<8} {'R→U':<8} {'U→R':<8} {'U→U':<8}")
                print("-" * 50)

                # Calculate overall totals
                total_rr = sum(run_data['transitions_by_difficulty'][d]['resolved_to_resolved'] for d in ['easy', 'medium', 'hard'])
                total_ru = sum(run_data['transitions_by_difficulty'][d]['resolved_to_unresolved'] for d in ['easy', 'medium', 'hard'])
                total_ur = sum(run_data['transitions_by_difficulty'][d]['unresolved_to_resolved'] for d in ['easy', 'medium', 'hard'])
                total_uu = sum(run_data['transitions_by_difficulty'][d]['unresolved_to_unresolved'] for d in ['easy', 'medium', 'hard'])

                for diff in ['easy', 'medium', 'hard']:
                    trans = run_data['transitions_by_difficulty'][diff]
                    print(f"{diff.capitalize():<12} {trans['resolved_to_resolved']:<8} "
                          f"{trans['resolved_to_unresolved']:<8} {trans['unresolved_to_resolved']:<8} "
                          f"{trans['unresolved_to_unresolved']:<8}")

                print("-" * 50)
                print(f"{'Overall':<12} {total_rr:<8} {total_ru:<8} {total_ur:<8} {total_uu:<8}")

                print(f"\nResolved → Unresolved ({len(run_data['resolved_to_unresolved_instances'])} instances):")
                for item in run_data['resolved_to_unresolved_instances'][:5]:  # Show first 5
                    print(f"  {item['instance_id']:<50} [{item['difficulty']}]")
                if len(run_data['resolved_to_unresolved_instances']) > 5:
                    print(f"  ... and {len(run_data['resolved_to_unresolved_instances']) - 5} more")

                print(f"\nUnresolved → Resolved ({len(run_data['unresolved_to_resolved_instances'])} instances):")
                for item in run_data['unresolved_to_resolved_instances'][:5]:  # Show first 5
                    print(f"  {item['instance_id']:<50} [{item['difficulty']}]")
                if len(run_data['unresolved_to_resolved_instances']) > 5:
                    print(f"  ... and {len(run_data['unresolved_to_resolved_instances']) - 5} more")

        else:
            # Single vanilla run
            overall = report['overall']
            print(f"\nOverall Resolution Rates:")
            print(f"  Vanilla: {overall['vanilla_resolved']}/{overall['total_instances']} ({overall['vanilla_rate']})")
            print(f"  {report['config'].capitalize()}: {overall['config_resolved']}/{overall['total_instances']} ({overall['config_rate']})")

            print(f"\nTransitions by Difficulty:")
            print(f"{'Difficulty':<12} {'R→R':<8} {'R→U':<8} {'U→R':<8} {'U→U':<8}")
            print("-" * 50)

            # Calculate overall totals
            total_rr = sum(report['transitions_by_difficulty'][d]['resolved_to_resolved'] for d in ['easy', 'medium', 'hard'])
            total_ru = sum(report['transitions_by_difficulty'][d]['resolved_to_unresolved'] for d in ['easy', 'medium', 'hard'])
            total_ur = sum(report['transitions_by_difficulty'][d]['unresolved_to_resolved'] for d in ['easy', 'medium', 'hard'])
            total_uu = sum(report['transitions_by_difficulty'][d]['unresolved_to_unresolved'] for d in ['easy', 'medium', 'hard'])

            for diff in ['easy', 'medium', 'hard']:
                trans = report['transitions_by_difficulty'][diff]
                print(f"{diff.capitalize():<12} {trans['resolved_to_resolved']:<8} "
                      f"{trans['resolved_to_unresolved']:<8} {trans['unresolved_to_resolved']:<8} "
                      f"{trans['unresolved_to_unresolved']:<8}")

            print("-" * 50)
            print(f"{'Overall':<12} {total_rr:<8} {total_ru:<8} {total_ur:<8} {total_uu:<8}")

            print(f"\nResolved → Unresolved ({len(report['resolved_to_unresolved_instances'])} instances):")
            for item in report['resolved_to_unresolved_instances']:
                print(f"  {item['instance_id']:<50} [{item['difficulty']}]")

            print(f"\nUnresolved → Resolved ({len(report['unresolved_to_resolved_instances'])} instances):")
            for item in report['unresolved_to_resolved_instances']:
                print(f"  {item['instance_id']:<50} [{item['difficulty']}]")

    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(description='Compare vanilla vs planner (monitor/refiner) resolution rates')
    parser.add_argument('--config', type=str, required=True, choices=['monitor', 'refiner'],
                       help='Config type: monitor or refiner')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., gpt-5-mini, deepseek-chat-v3-0324)')
    parser.add_argument('--run-id', type=int, required=True, default=1,
                       help='Run ID')
    parser.add_argument('--sample-approach', type=str, required=True,
                       help='Sample approach (e.g., random, stratified)')
    parser.add_argument('--pattern', type=str, default=None,
                       help='Pattern for sample/report path (optional)')
    parser.add_argument('--version-id', type=str, default=None,
                       help='Version ID (optional, e.g., 1, 2)')
    parser.add_argument('--reproducible', action='store_true',
                       help='Use reproducible mode with sampled instances data')

    args = parser.parse_args()

    # Load data
    if args.reproducible:
        sample_data = load_sample_data(args.sample_approach, args.model, args.run_id, args.pattern)
    else:
        print("Non-reproducible mode: only loading config report")
        sample_data = {}

    config_report = load_config_report(args.config, args.model, args.run_id, args.version_id, args.pattern)

    # Compare
    transitions, sample_data = compare_resolutions(sample_data, config_report, args.reproducible, args.pattern)

    # Generate report
    report = generate_report(args.config, args.model, args.run_id, transitions,
                           sample_data, args.reproducible, args.sample_approach, args.pattern)
    if args.version_id:
        report['version_id'] = args.version_id

    # Save and print
    output_dir = Path(__file__).parent / "analysis-results" / "resolution"
    save_report(report, output_dir)
    print_summary(report)


if __name__ == "__main__":
    main()
