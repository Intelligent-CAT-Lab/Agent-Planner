"""
Analyze planner trigger statistics from .planner.json files.
Example usage:
python analyze_planner_trigger.py \
  --config refiner \
  --model deepseek-chat-v3-0324 \
  --run-id 1 \
  --version-id 1
"""
import json
import argparse
import re
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np


def load_planner_files(config: str, model: str, run_id: int, dataset: str = "swebench",
                       version_id: str = None) -> list:
    """Load all .planner.json files from the output directory."""
    script_dir = Path(__file__).parent.parent.parent

    if version_id:
        output_path = script_dir / "outputs" / config / f"version-{version_id}" / dataset / model / f"run-{run_id}"
    else:
        output_path = script_dir / "outputs" / config / dataset / model / f"run-{run_id}"

    if not output_path.exists():
        raise FileNotFoundError(f"Output path not found: {output_path}")

    planner_files = list(output_path.rglob("*.planner.json"))
    return planner_files


def load_report_data(config: str, model: str, run_id: int, version_id: str = None) -> dict:
    """Load resolution report data."""
    script_dir = Path(__file__).parent.parent.parent

    if version_id:
        report_path = script_dir / "reports" / config / f"version-{version_id}" / "swebench" / model / f"{model.split('/')[-1]}.run-{run_id}.json"
    else:
        # Try without version first, then with common patterns
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

        if not report_path:
            raise FileNotFoundError(f"Report not found for {config}/{model}/run-{run_id}")

    if not report_path.exists():
        raise FileNotFoundError(f"Report not found at: {report_path}")

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    # Extract resolved instance IDs
    resolved_ids = set(report.get('resolved_ids', []))
    return {'resolved_ids': resolved_ids, 'report': report}


def extract_plan_compliance_details(message: str) -> tuple:
    """Extract violation and skipped details from plan compliance message."""
    if 'Plan compliance violation:' not in message:
        return None, None

    # Extract violation
    violation_match = re.search(r'violation: ([^.]+?)\.', message)
    if not violation_match:
        violation_match = re.search(r'violation: (.+?)(?:Expected|Skipped)', message)

    # Extract skipped phases
    skipped_match = re.search(r'Skipped phases?: ([^.]+?)\.', message)

    violation = violation_match.group(1).strip() if violation_match else 'unknown'
    skipped = skipped_match.group(1).strip() if skipped_match else 'none'

    return violation, skipped


def parse_monitor_rule(content: str) -> tuple:
    """Parse monitor content to extract rule type and key information."""
    if not content:
        return 'unknown', content

    # Plan compliance violation pattern
    if content.startswith('Plan compliance violation:'):
        violation, skipped = extract_plan_compliance_details(content)
        rule_id = f"plan_compliance: violation={violation}, skipped={skipped}"
        return rule_id, content

    # Navigation stuck patterns
    elif 'stuck in navigation' in content.lower() or 'may get stuck in navigation' in content.lower():
        return 'dwell_L_navigate', content

    # Reproducing patterns
    elif 'long reproducing process' in content.lower():
        return 'dwell_L_reproduce', content

    # Validation patterns
    elif 'long validation process' in content.lower():
        return 'dwell_V', content

    # Repeating cycle
    elif 'repeating cycle' in content.lower():
        return 'cycle_detected', content

    # Generic stuck patterns
    elif 'may get stuck' in content.lower() or 'stuck in' in content.lower():
        stuck_match = re.search(r'stuck in ([^.]+)', content, re.IGNORECASE)
        if stuck_match:
            phase = stuck_match.group(1).strip().lower()
            return f'dwell_{phase}', content
        return 'dwell_unknown', content

    # Generic monitor rules
    else:
        first_sentence = content.split('.')[0].strip() if '.' in content else content.strip()
        if len(first_sentence) > 50:
            first_sentence = first_sentence[:50] + '...'
        return f'other: {first_sentence}', content


def analyze_planner_file(file_path: Path) -> dict:
    """Analyze a single planner.json file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        summary = data.get('summary', {})
        interventions = data.get('interventions', [])

        # Extract summary stats
        stats = {
            'instance_id': file_path.stem.replace('.planner', ''),
            'total_interventions': summary.get('total_interventions', 0),
            'monitor_count': summary.get('monitor_count', 0),
            'refiner_count': summary.get('refiner_count', 0),
            'triggered_rules': []
        }

        # Extract triggered rules from interventions
        for intervention in interventions:
            planner_type = intervention.get('planner_type')

            if planner_type == 'refiner':
                # Get from state_summary.rule_triggers (last rule message)
                state_summary = intervention.get('state_summary', {})
                rule_triggers = state_summary.get('rule_triggers', [])
                if rule_triggers:
                    # Get the last rule trigger
                    last_rule = rule_triggers[-1]
                    rule_id = last_rule.get('rule_id')
                    message = last_rule.get('message')

                    # Normalize plan_compliance rules by extracting details from message
                    if rule_id == 'plan_compliance':
                        violation, skipped = extract_plan_compliance_details(message)
                        if violation and skipped:
                            rule_id = f"plan_compliance: violation={violation}, skipped={skipped}"

                    stats['triggered_rules'].append({
                        'type': 'refiner',
                        'rule_id': rule_id,
                        'message': message,
                        'step': intervention.get('step')
                    })

            elif planner_type == 'monitor':
                # Parse monitor content to extract specific rule
                content = intervention.get('content', '')
                rule_id, message = parse_monitor_rule(content)
                stats['triggered_rules'].append({
                    'type': 'monitor',
                    'rule_id': rule_id,
                    'message': message,
                    'step': intervention.get('step')
                })

        return stats

    except Exception as e:
        print(f"Error analyzing {file_path.name}: {e}")
        return None


def aggregate_statistics(all_stats: list, resolved_ids: set = None) -> dict:
    """Aggregate statistics across all instances."""
    if not all_stats:
        return {}

    total_interventions = [s['total_interventions'] for s in all_stats]
    monitor_counts = [s['monitor_count'] for s in all_stats]
    refiner_counts = [s['refiner_count'] for s in all_stats]

    # Collect all triggered rules with breakdown by type
    rule_counter = Counter()
    rule_breakdown = defaultdict(lambda: {'monitor': 0, 'refiner': 0})
    rule_messages = {}

    # Resolution-based breakdown
    resolution_stats = {
        'resolved': {'count': 0, 'with_triggers': 0, 'total_triggers': 0},
        'unresolved': {'count': 0, 'with_triggers': 0, 'total_triggers': 0}
    }

    for stats in all_stats:
        instance_id = stats['instance_id']
        has_triggers = stats['total_interventions'] > 0

        # Determine resolution status
        if resolved_ids is not None:
            is_resolved = instance_id in resolved_ids
            status = 'resolved' if is_resolved else 'unresolved'

            resolution_stats[status]['count'] += 1
            if has_triggers:
                resolution_stats[status]['with_triggers'] += 1
                resolution_stats[status]['total_triggers'] += stats['total_interventions']

        for rule in stats['triggered_rules']:
            rule_id = rule['rule_id']
            planner_type = rule['type']

            # Count overall
            rule_counter[rule_id] += 1

            # Count by type
            rule_breakdown[rule_id][planner_type] += 1

            # Store the message (keep first occurrence)
            if rule_id not in rule_messages:
                rule_messages[rule_id] = rule['message']

    # Convert defaultdict to regular dict
    rule_breakdown_dict = {k: dict(v) for k, v in rule_breakdown.items()}

    aggregated = {
        'instance_count': len(all_stats),
        'avg_total_interventions': float(np.mean(total_interventions)) if total_interventions else 0.0,
        'avg_monitor_count': float(np.mean(monitor_counts)) if monitor_counts else 0.0,
        'avg_refiner_count': float(np.mean(refiner_counts)) if refiner_counts else 0.0,
        'total_interventions_sum': sum(total_interventions),
        'total_monitor_sum': sum(monitor_counts),
        'total_refiner_sum': sum(refiner_counts),
        'rule_distribution': dict(rule_counter),
        'rule_breakdown': rule_breakdown_dict,
        'rule_messages': rule_messages,
        'instances_with_interventions': sum(1 for s in all_stats if s['total_interventions'] > 0),
        'instances_with_monitor': sum(1 for s in all_stats if s['monitor_count'] > 0),
        'instances_with_refiner': sum(1 for s in all_stats if s['refiner_count'] > 0)
    }

    # Add resolution stats if available
    if resolved_ids is not None:
        aggregated['resolution_stats'] = resolution_stats

    return aggregated


def print_summary(aggregated: dict, config: str, model: str, run_id: int, version_id: str = None):
    """Print summary statistics."""
    print("\n" + "="*80)
    print(f"Planner Trigger Analysis: {config.upper()}")
    print(f"Model: {model}, Run: {run_id}")
    if version_id:
        print(f"Version: {version_id}")
    print("="*80)

    print(f"\nInstance Count: {aggregated['instance_count']}")
    print(f"Instances with Interventions: {aggregated['instances_with_interventions']}")
    print(f"Instances with Monitor: {aggregated['instances_with_monitor']}")
    print(f"Instances with Refiner: {aggregated['instances_with_refiner']}")

    # Print resolution statistics if available
    if 'resolution_stats' in aggregated:
        print(f"\n{'='*80}")
        print("Resolution Status Analysis:")
        print(f"{'='*80}")

        res_stats = aggregated['resolution_stats']
        resolved = res_stats['resolved']
        unresolved = res_stats['unresolved']

        total = resolved['count'] + unresolved['count']
        resolved_rate = (resolved['count'] / total * 100) if total > 0 else 0

        print(f"\nOverall Resolution:")
        print(f"  Resolved: {resolved['count']}/{total} ({resolved_rate:.2f}%)")
        print(f"  Unresolved: {unresolved['count']}/{total} ({100-resolved_rate:.2f}%)")

        print(f"\nTrigger Statistics by Resolution Status:")
        print(f"{'Status':<15} {'Total':>8} {'With Triggers':>15} {'Trigger %':>12} {'Avg Triggers':>15}")
        print("-" * 70)

        for status in ['resolved', 'unresolved']:
            stats = res_stats[status]
            trigger_pct = (stats['with_triggers'] / stats['count'] * 100) if stats['count'] > 0 else 0
            avg_triggers = (stats['total_triggers'] / stats['count']) if stats['count'] > 0 else 0
            print(f"{status.capitalize():<15} {stats['count']:>8} {stats['with_triggers']:>15} "
                  f"{trigger_pct:>11.1f}% {avg_triggers:>15.2f}")

        # Calculate comparative metrics
        if resolved['count'] > 0 and unresolved['count'] > 0:
            resolved_trigger_rate = resolved['with_triggers'] / resolved['count']
            unresolved_trigger_rate = unresolved['with_triggers'] / unresolved['count']
            resolved_avg_triggers = resolved['total_triggers'] / resolved['count']
            unresolved_avg_triggers = unresolved['total_triggers'] / unresolved['count']

            print(f"\nComparative Analysis:")
            print(f"  Resolved instances have {resolved_trigger_rate/unresolved_trigger_rate:.2f}x the trigger rate of unresolved")
            print(f"  Resolved instances have {resolved_avg_triggers/unresolved_avg_triggers:.2f}x the average triggers of unresolved")

    print(f"\nAverage Counts per Instance:")
    print(f"  Total Interventions: {aggregated['avg_total_interventions']:.2f}")
    print(f"  Monitor Count: {aggregated['avg_monitor_count']:.2f}")
    print(f"  Refiner Count: {aggregated['avg_refiner_count']:.2f}")

    print(f"\nTotal Counts:")
    print(f"  Total Interventions: {aggregated['total_interventions_sum']}")
    print(f"  Monitor: {aggregated['total_monitor_sum']}")
    print(f"  Refiner: {aggregated['total_refiner_sum']}")

    print(f"\nTriggered Rule Distribution:")
    sorted_rules = sorted(aggregated['rule_distribution'].items(), key=lambda x: x[1], reverse=True)
    print(f"{'Rule ID':<50} {'Total':>8} {'Monitor':>10} {'Refiner':>10} {'%':>8}")
    print("-" * 90)

    total_rules = sum(aggregated['rule_distribution'].values())
    for rule_id, count in sorted_rules:
        percentage = (count / total_rules * 100) if total_rules > 0 else 0
        breakdown = aggregated['rule_breakdown'][rule_id]
        monitor_count = breakdown.get('monitor', 0)
        refiner_count = breakdown.get('refiner', 0)

        # Truncate long rule IDs for display
        display_id = rule_id if len(rule_id) <= 50 else rule_id[:47] + '...'
        print(f"{display_id:<50} {count:>8} {monitor_count:>10} {refiner_count:>10} {percentage:>7.1f}%")

    # Print total summary
    total_monitor = sum(bd.get('monitor', 0) for bd in aggregated['rule_breakdown'].values())
    total_refiner = sum(bd.get('refiner', 0) for bd in aggregated['rule_breakdown'].values())
    print(f"\nTotal Rule Triggers: {total_rules}")
    print(f"  Monitor: {total_monitor} ({total_monitor/total_rules*100:.1f}%)")
    print(f"  Refiner: {total_refiner} ({total_refiner/total_rules*100:.1f}%)")

    print("\n" + "="*80)
    print("\nRule Messages:")
    print("="*80)

    # Show all rule messages sorted by count
    for rule_id, count in sorted_rules:
        breakdown = aggregated['rule_breakdown'][rule_id]
        message = aggregated['rule_messages'].get(rule_id, 'N/A')

        print(f"\n[{rule_id}] (Total: {count}, Monitor: {breakdown.get('monitor', 0)}, Refiner: {breakdown.get('refiner', 0)})")
        # Truncate long messages
        display_msg = message if len(message) <= 200 else message[:197] + '...'
        print(f"  {display_msg}")
        print("-" * 80)

    print("\n" + "="*80)


def save_report(aggregated: dict, all_stats: list, config: str, model: str,
                run_id: int, version_id: str, output_dir: Path):
    """Save detailed report to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    version_suffix = f"_version-{version_id}" if version_id else ""
    output_file = output_dir / f"{config}_{model.split('/')[-1]}_run{run_id}{version_suffix}_trigger_analysis.json"

    report = {
        'config': config,
        'model': model,
        'run_id': run_id,
        'version_id': version_id,
        'aggregated': aggregated,
        'instances': all_stats
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print(f"\nDetailed report saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Analyze planner trigger statistics')
    parser.add_argument('--config', type=str, required=True, choices=['monitor', 'refiner'],
                       help='Config type: monitor or refiner')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., gpt-5-mini, deepseek-chat-v3-0324)')
    parser.add_argument('--run-id', type=int, required=True,
                       help='Run ID')
    parser.add_argument('--version-id', type=str, default=None,
                       help='Version ID (optional)')
    parser.add_argument('--dataset', type=str, default='swebench',
                       help='Dataset name (default: swebench)')

    args = parser.parse_args()

    # Load planner files
    print(f"Loading planner files for {args.config}/{args.model}/run-{args.run_id}...")
    planner_files = load_planner_files(args.config, args.model, args.run_id,
                                       args.dataset, args.version_id)
    print(f"Found {len(planner_files)} planner files")

    # Load resolution report data
    resolved_ids = None
    try:
        print(f"\nLoading resolution report...")
        report_data = load_report_data(args.config, args.model, args.run_id, args.version_id)
        resolved_ids = report_data['resolved_ids']
        print(f"Found {len(resolved_ids)} resolved instances in report")
    except FileNotFoundError as e:
        print(f"Warning: Could not load report data: {e}")
        print("Continuing without resolution statistics...")

    # Analyze each file
    print(f"\nAnalyzing planner files...")
    all_stats = []
    for file_path in planner_files:
        stats = analyze_planner_file(file_path)
        if stats:
            all_stats.append(stats)

    print(f"Successfully analyzed {len(all_stats)} files")

    # Aggregate statistics
    aggregated = aggregate_statistics(all_stats, resolved_ids)

    # Print summary
    print_summary(aggregated, args.config, args.model, args.run_id, args.version_id)

    # Save report
    output_dir = Path(__file__).parent / "analysis-results" / "trigger"
    save_report(aggregated, all_stats, args.config, args.model,
                args.run_id, args.version_id, output_dir)


if __name__ == "__main__":
    main()