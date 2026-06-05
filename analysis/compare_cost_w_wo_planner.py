"""
Compare the number of trajectory steps and cost (for refiner: executor agent cost from .traj + refiner cost from .planner.json)
Latency from the .planner.json
Example usage:
python analysis/compare_cost_w_wo_planner.py --dataset swebench --agent SWE-agent --model deepseek-chat-v3-0324 --config refiner --version 5 --run_id 1 --reproducible
Input args: --agent (default to SWE-agent),, --config (default to refiner), --version (default to 5), --run_id (default to 1)
When --dataset is swebench, the agent dir is PROJECT_DIR/SWE-agent; when --dataset is swebench-pro, the agent dir is PROJECT_DIR/SWE-bench_Pro-os/SWE-agent.
The default traj can be found under: {agent_dir}/trajectories/{config}(set to default)/{dataset}/{model}/; when --reproducible is set, discover the available runs under this folder, otherwise, find the trajs under 1/.
The config traj can be found under {agent_dir}/trajectories/{config}/(version-{version_id})(this is included when the config is refiner)/{dataset}/{model}/run-{run_id}/.
Executor agent steps and cost (from .traj):
    cost = data.get("info", {}).get("model_stats", {}).get("instance_cost", 0)
    api_calls = data.get("info", {}).get("model_stats", {}).get("api_calls", 0)
Refiner cost and latency (from .planner.json):
    refiner_cost = data.get("summary", {}).get("refiner_total_cost", 0)
    latency = data.get("summary", {}).get("monitor_total_latency_ms", 0) + data.get("summary", {}).get("refiner_total_latency_ms", 0)
Analyze the trigger distribution (from .planner.json) and present the results (include the triggering type/frequency, rule type (when empty, the rule is actually "plan_compliance"), and monitor/refiner time breakdown ) appropriately.
"""
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np


def load_traj_stats(traj_file: Path) -> dict:
    """Load cost and API call stats from .traj file."""
    try:
        with open(traj_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        model_stats = data.get("info", {}).get("model_stats", {})
        return {
            'instance_cost': model_stats.get("instance_cost", 0),
            'api_calls': model_stats.get("api_calls", 0)
        }
    except Exception as e:
        print(f"Error loading {traj_file.name}: {e}")
        return None


def load_planner_stats(planner_file: Path) -> dict:
    """Load refiner cost, latency, and trigger stats from .planner.json file."""
    try:
        with open(planner_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        summary = data.get("summary", {})
        interventions = data.get("interventions", [])

        # Extract basic stats
        stats = {
            'refiner_cost': summary.get("refiner_total_cost", 0),
            'monitor_latency_ms': summary.get("monitor_total_latency_ms", 0),
            'refiner_latency_ms': summary.get("refiner_total_latency_ms", 0),
            'total_latency_ms': summary.get("monitor_total_latency_ms", 0) + summary.get("refiner_total_latency_ms", 0),
            'total_interventions': summary.get("total_interventions", 0),
            'monitor_count': summary.get("monitor_count", 0),
            'refiner_count': summary.get("refiner_count", 0),
            'triggers': []
        }

        # Extract trigger information
        for intervention in interventions:
            planner_type = intervention.get('planner_type')

            if planner_type == 'refiner':
                state_summary = intervention.get('state_summary', {})
                rule_triggers = state_summary.get('rule_triggers', [])
                if rule_triggers:
                    last_rule = rule_triggers[-1]
                    rule_id = last_rule.get('rule_id', 'plan_compliance')
                    rule_id = rule_id if rule_id else 'plan_compliance'
                else:
                    # When rule_triggers is empty, default to plan_compliance
                    rule_id = 'plan_compliance'
                stats['triggers'].append({
                    'type': 'refiner',
                    'rule_id': rule_id
                })
            elif planner_type == 'monitor':
                stats['triggers'].append({
                    'type': 'monitor',
                    'rule_id': 'monitor'
                })

        return stats
    except Exception as e:
        print(f"Error loading {planner_file.name}: {e}")
        return None


def load_instance_data(instance_dir: Path, instance_id: str, config: str) -> dict:
    """Load data for a single instance."""
    traj_file = instance_dir / f"{instance_id}.traj"
    planner_file = instance_dir / f"{instance_id}.planner.json"

    if not traj_file.exists():
        return None

    traj_stats = load_traj_stats(traj_file)
    if not traj_stats:
        return None

    result = {
        'instance_id': instance_id,
        'executor_cost': traj_stats['instance_cost'],
        'api_calls': traj_stats['api_calls'],
        'refiner_cost': 0,
        'total_cost': traj_stats['instance_cost'],
        'latency_ms': 0,
        'monitor_latency_ms': 0,
        'refiner_latency_ms': 0,
        'total_interventions': 0,
        'monitor_count': 0,
        'refiner_count': 0,
        'triggers': []
    }

    # Load planner stats if available (for refiner/monitor configs)
    if config != 'default' and planner_file.exists():
        planner_stats = load_planner_stats(planner_file)
        if planner_stats:
            result['refiner_cost'] = planner_stats['refiner_cost']
            result['total_cost'] = result['executor_cost'] + result['refiner_cost']
            result['latency_ms'] = planner_stats['total_latency_ms']
            result['monitor_latency_ms'] = planner_stats['monitor_latency_ms']
            result['refiner_latency_ms'] = planner_stats['refiner_latency_ms']
            result['total_interventions'] = planner_stats['total_interventions']
            result['monitor_count'] = planner_stats['monitor_count']
            result['refiner_count'] = planner_stats['refiner_count']
            result['triggers'] = planner_stats['triggers']

    return result


def load_trajectory_data(agent_dir: Path, dataset: str, model: str, config: str,
                        version: str = None, run_id: int = None, runs: list = None) -> list:
    """Load trajectory data from specified directory."""
    all_data = []

    # Add "python" subdirectory for swebench-pro
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    if config == 'default':
        # Default (vanilla) trajectories
        if runs:
            # Reproducible mode: load from multiple runs
            for run in runs:
                base_path = agent_dir / "trajectories" / "default" / dataset_path / model / f"run-{str(run)}"
                if not base_path.exists():
                    continue

                for instance_dir in base_path.iterdir():
                    if not instance_dir.is_dir():
                        continue

                    instance_id = instance_dir.name
                    data = load_instance_data(instance_dir, instance_id, config)
                    if data:
                        all_data.append(data)
        else:
            # Single run mode
            base_path = agent_dir / "trajectories" / "default" / dataset_path / model / "run-1"
            if base_path.exists():
                for instance_dir in base_path.iterdir():
                    if not instance_dir.is_dir():
                        continue

                    instance_id = instance_dir.name
                    data = load_instance_data(instance_dir, instance_id, config)
                    if data:
                        all_data.append(data)
    else:
        # Config trajectories (monitor/refiner)
        # Version is only used for refiner config
        if config == 'refiner' and version:
            base_path = agent_dir / "trajectories" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}"
        else:
            base_path = agent_dir / "trajectories" / config / dataset_path / model / f"run-{run_id}"

        if base_path.exists():
            for instance_dir in base_path.iterdir():
                if not instance_dir.is_dir():
                    continue

                instance_id = instance_dir.name
                data = load_instance_data(instance_dir, instance_id, config)
                if data:
                    all_data.append(data)

    return all_data


def compute_averages(data: list) -> dict:
    """Compute average statistics across instances."""
    if not data:
        return {
            'instance_count': 0,
            'avg_executor_cost': 0,
            'avg_refiner_cost': 0,
            'avg_total_cost': 0,
            'avg_api_calls': 0,
            'avg_latency_ms': 0,
            'avg_monitor_latency_ms': 0,
            'avg_refiner_latency_ms': 0,
            'avg_interventions': 0,
            'avg_monitor_count': 0,
            'avg_refiner_count': 0
        }

    return {
        'instance_count': len(data),
        'avg_executor_cost': float(np.mean([d['executor_cost'] for d in data])),
        'avg_refiner_cost': float(np.mean([d['refiner_cost'] for d in data])),
        'avg_total_cost': float(np.mean([d['total_cost'] for d in data])),
        'avg_api_calls': float(np.mean([d['api_calls'] for d in data])),
        'avg_latency_ms': float(np.mean([d['latency_ms'] for d in data])),
        'avg_monitor_latency_ms': float(np.mean([d['monitor_latency_ms'] for d in data])),
        'avg_refiner_latency_ms': float(np.mean([d['refiner_latency_ms'] for d in data])),
        'avg_interventions': float(np.mean([d['total_interventions'] for d in data])),
        'avg_monitor_count': float(np.mean([d['monitor_count'] for d in data])),
        'avg_refiner_count': float(np.mean([d['refiner_count'] for d in data]))
    }


def analyze_trigger_distribution(data: list) -> dict:
    """Analyze trigger distribution from planner data."""
    trigger_counter = Counter()
    type_counter = Counter()

    total_monitor_latency = 0
    total_refiner_latency = 0
    instances_with_triggers = 0
    total_trigger_count = 0

    for instance in data:
        if instance['total_interventions'] > 0:
            instances_with_triggers += 1

        total_monitor_latency += instance['monitor_latency_ms']
        total_refiner_latency += instance['refiner_latency_ms']
        total_trigger_count += instance['total_interventions']

        for trigger in instance['triggers']:
            trigger_type = trigger['type']
            rule_id = trigger['rule_id']

            type_counter[trigger_type] += 1
            trigger_counter[rule_id] += 1

    # Calculate average triggers per instance
    avg_triggers_per_instance = total_trigger_count / len(data) if len(data) > 0 else 0
    avg_triggers_per_triggered_instance = total_trigger_count / instances_with_triggers if instances_with_triggers > 0 else 0

    return {
        'trigger_distribution': dict(trigger_counter),
        'type_distribution': dict(type_counter),
        'instances_with_triggers': instances_with_triggers,
        'total_instances': len(data),
        'trigger_rate': (instances_with_triggers / len(data) * 100) if len(data) > 0 else 0,
        'total_trigger_count': total_trigger_count,
        'avg_triggers_per_instance': avg_triggers_per_instance,
        'avg_triggers_per_triggered_instance': avg_triggers_per_triggered_instance,
        'total_monitor_latency_ms': total_monitor_latency,
        'total_refiner_latency_ms': total_refiner_latency,
        'monitor_latency_pct': (total_monitor_latency / (total_monitor_latency + total_refiner_latency) * 100)
                               if (total_monitor_latency + total_refiner_latency) > 0 else 0,
        'refiner_latency_pct': (total_refiner_latency / (total_monitor_latency + total_refiner_latency) * 100)
                               if (total_monitor_latency + total_refiner_latency) > 0 else 0
    }


def generate_comparison_report(vanilla_data: list, config_data: list,
                              config: str, model: str, version: str, run_id: int, vanilla_run_id: int = None) -> dict:
    """Generate comparison report."""
    vanilla_avg = compute_averages(vanilla_data)
    config_avg = compute_averages(config_data)

    report = {
        'config_name': config,
        'model': model,
        'version': version,
        'run_id': run_id,
        'vanilla_run_id': vanilla_run_id,
        'vanilla': vanilla_avg,
        'config': config_avg,
        'comparison': {}
    }

    # Cost comparison
    if vanilla_avg['avg_total_cost'] > 0:
        cost_increase = config_avg['avg_total_cost'] - vanilla_avg['avg_total_cost']
        cost_increase_pct = (cost_increase / vanilla_avg['avg_total_cost']) * 100

        report['comparison']['cost'] = {
            'vanilla_avg': vanilla_avg['avg_total_cost'],
            'config_avg': config_avg['avg_total_cost'],
            'increase': cost_increase,
            'increase_pct': cost_increase_pct,
            'executor_avg': config_avg['avg_executor_cost'],
            'refiner_avg': config_avg['avg_refiner_cost']
        }

    # API calls comparison
    if vanilla_avg['avg_api_calls'] > 0:
        api_diff = config_avg['avg_api_calls'] - vanilla_avg['avg_api_calls']
        api_diff_pct = (api_diff / vanilla_avg['avg_api_calls']) * 100

        report['comparison']['api_calls'] = {
            'vanilla_avg': vanilla_avg['avg_api_calls'],
            'config_avg': config_avg['avg_api_calls'],
            'difference': api_diff,
            'difference_pct': api_diff_pct
        }

    # Trigger analysis
    if config != 'default':
        trigger_stats = analyze_trigger_distribution(config_data)
        report['trigger_analysis'] = trigger_stats

    return report


def print_cost_comparison(report: dict):
    """Print cost comparison summary (separate for each vanilla run)."""
    config_name = report['config_name']
    print("\n" + "="*80)
    if report.get('vanilla_run_id'):
        print(f"Cost Comparison: {config_name.upper()} (run-{report['run_id']}) vs Vanilla (run-{report['vanilla_run_id']})")
    else:
        print(f"Cost Comparison: {config_name.upper()} (run-{report['run_id']}) vs Vanilla")
    print(f"Model: {report['model']}")
    if report['version']:
        print(f"Version: {report['version']}")
    print("="*80)

    print(f"\nInstance Count:")
    print(f"  Vanilla: {report['vanilla']['instance_count']}")
    print(f"  {config_name.capitalize()}: {report['config']['instance_count']}")

    # Cost comparison
    if 'cost' in report['comparison']:
        cost_comp = report['comparison']['cost']
        print(f"\nCost Analysis:")
        print(f"  Vanilla Average:     ${cost_comp['vanilla_avg']:.6f}")
        print(f"  {config_name.capitalize()} Average:    ${cost_comp['config_avg']:.6f}")
        print(f"    - Executor:        ${cost_comp['executor_avg']:.6f}")
        print(f"    - Refiner:         ${cost_comp['refiner_avg']:.6f}")
        print(f"  Cost Increase:       ${cost_comp['increase']:+.6f} ({cost_comp['increase_pct']:+.2f}%)")

    # API calls comparison
    if 'api_calls' in report['comparison']:
        api_comp = report['comparison']['api_calls']
        print(f"\nAPI Calls:")
        print(f"  Vanilla Average:     {api_comp['vanilla_avg']:.2f}")
        print(f"  {config_name.capitalize()} Average:    {api_comp['config_avg']:.2f}")
        print(f"  Difference:          {api_comp['difference']:+.2f} ({api_comp['difference_pct']:+.2f}%)")

    print("="*80)


def print_trigger_analysis(config_data: list, config_name: str, model: str, version: str, run_id: int):
    """Print trigger analysis (same for all vanilla comparisons)."""
    config_avg = compute_averages(config_data)
    trigger_stats = analyze_trigger_distribution(config_data)

    print("\n" + "="*80)
    print(f"Trigger & Latency Analysis: {config_name.upper()} (run-{run_id})")
    print(f"Model: {model}")
    if version:
        print(f"Version: {version}")
    print("="*80)

    print(f"\nConfig Instances: {config_avg['instance_count']}")

    # Latency
    print(f"\nLatency:")
    print(f"  Average Total:       {config_avg['avg_latency_ms']:.2f} ms")
    print(f"  Average Monitor:     {config_avg['avg_monitor_latency_ms']:.2f} ms")
    print(f"  Average Refiner:     {config_avg['avg_refiner_latency_ms']:.2f} ms")

    # Trigger analysis
    print(f"\nIntervention Statistics:")
    print(f"  Instances with Triggers:       {trigger_stats['instances_with_triggers']}/{trigger_stats['total_instances']} ({trigger_stats['trigger_rate']:.1f}%)")
    print(f"  Total Trigger Count:           {trigger_stats['total_trigger_count']}")
    print(f"  Avg Triggers per Instance:     {trigger_stats['avg_triggers_per_instance']:.2f}")
    print(f"  Avg Triggers (triggered only): {trigger_stats['avg_triggers_per_triggered_instance']:.2f}")
    print(f"  Avg Monitor Count:             {config_avg['avg_monitor_count']:.2f}")
    print(f"  Avg Refiner Count:             {config_avg['avg_refiner_count']:.2f}")

    print(f"\nLatency Breakdown:")
    print(f"  Monitor: {trigger_stats['total_monitor_latency_ms']:.2f} ms ({trigger_stats['monitor_latency_pct']:.1f}%)")
    print(f"  Refiner: {trigger_stats['total_refiner_latency_ms']:.2f} ms ({trigger_stats['refiner_latency_pct']:.1f}%)")

    if trigger_stats['type_distribution']:
        print(f"\nTrigger Type Distribution:")
        total_triggers = sum(trigger_stats['type_distribution'].values())
        for ttype, count in sorted(trigger_stats['type_distribution'].items()):
            pct = (count / total_triggers * 100) if total_triggers > 0 else 0
            print(f"  {ttype.capitalize()}: {count} ({pct:.1f}%)")

    if trigger_stats['trigger_distribution']:
        print(f"\nRule Distribution:")
        sorted_rules = sorted(trigger_stats['trigger_distribution'].items(),
                            key=lambda x: x[1], reverse=True)
        total_rules = sum(trigger_stats['trigger_distribution'].values())
        for rule_id, count in sorted_rules[:10]:
            pct = (count / total_rules * 100) if total_rules > 0 else 0
            display_id = rule_id if len(rule_id) <= 60 else rule_id[:57] + '...'
            print(f"  {display_id}: {count} ({pct:.1f}%)")

        if len(sorted_rules) > 10:
            print(f"  ... and {len(sorted_rules) - 10} more rules")

    print("="*80)


def save_combined_report(comparisons: list, trigger_analysis: dict, config_name: str,
                        model: str, version: str, run_id: int, output_dir: Path):
    """Save combined report with all vanilla comparisons and trigger analysis to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    version_suffix = f"_version-{version}" if (config_name == 'refiner' and version) else ""
    output_file = output_dir / f"{config_name}_{model.split('/')[-1]}_run{run_id}{version_suffix}_cost_comparison.json"

    combined_report = {
        'config_name': config_name,
        'model': model,
        'version': version,
        'run_id': run_id,
        'trigger_analysis': trigger_analysis,
        'vanilla_comparisons': comparisons
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(combined_report, f, indent=2)

    print(f"\nCombined report saved to: {output_file}")
    return output_file


def discover_available_runs(agent_dir: Path, dataset: str, model: str) -> list:
    """Discover available run directories for vanilla trajectories."""
    # Add "python" subdirectory for swebench-pro
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"
    base_path = agent_dir / "trajectories" / "default" / dataset_path / model

    if not base_path.exists():
        return []

    available_runs = []
    for item in base_path.iterdir():
        if item.is_dir():
            if item.name.startswith("run-") and item.name[4:].isdigit():
                available_runs.append(int(item.name[4:]))
            elif item.name.isdigit():
                available_runs.append(int(item.name))

    return sorted(available_runs)


def main():
    parser = argparse.ArgumentParser(description='Compare cost and steps between vanilla and planner configs')
    parser.add_argument('--dataset', type=str, default='swebench',
                       help='Dataset name (swebench or swebench-pro)')
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent directory name')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., deepseek-chat-v3-0324)')
    parser.add_argument('--config', type=str, default='refiner',
                       help='Config type (monitor or refiner)')
    parser.add_argument('--version', type=str, default='5',
                       help='Version ID (only for refiner config, default: 5)')
    parser.add_argument('--run_id', type=int, default=1,
                       help='Run ID for config trajectories')
    parser.add_argument('--reproducible', action='store_true',
                       help='Use reproducible mode with all available vanilla runs')

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

    # Load config data once
    print(f"Loading {args.config} trajectories...")
    if args.config == 'refiner' and args.version:
        print(f"  Version: {args.version}, Run: {args.run_id}")
    else:
        print(f"  Run: {args.run_id}")
    config_data = load_trajectory_data(
        agent_dir, args.dataset, args.model, args.config,
        version=args.version, run_id=args.run_id
    )
    print(f"Loaded {len(config_data)} {args.config} instances")

    if not config_data:
        print("\nError: No config data loaded. Please check the paths and file availability.")
        return

    # Determine vanilla runs to compare
    print(f"\nLoading vanilla trajectories...")
    if args.reproducible:
        vanilla_runs = discover_available_runs(agent_dir, args.dataset, args.model)
        if not vanilla_runs:
            print(f"Warning: No vanilla runs found, falling back to run 1")
            vanilla_runs = [1]
        else:
            print(f"  Discovered runs: {vanilla_runs}")
    else:
        vanilla_runs = [1]
        print(f"  Using run: 1")

    # Print trigger analysis once (same for all vanilla comparisons)
    trigger_analysis = None
    if args.config != 'default':
        print_trigger_analysis(config_data, args.config, args.model, args.version, args.run_id)
        trigger_analysis = analyze_trigger_distribution(config_data)

    # Compare each vanilla run separately with config
    comparisons = []

    for vanilla_run in vanilla_runs:
        print(f"\n{'='*80}")
        print(f"Processing Vanilla Run {vanilla_run}")
        print(f"{'='*80}")

        # Load vanilla data for this run
        vanilla_data = load_trajectory_data(
            agent_dir, args.dataset, args.model, 'default',
            runs=[vanilla_run]
        )

        if not vanilla_data:
            print(f"Warning: No data loaded for vanilla run {vanilla_run}, skipping...")
            continue

        print(f"Loaded {len(vanilla_data)} vanilla instances from run {vanilla_run}")

        # Generate report for this vanilla run vs config
        report = generate_comparison_report(
            vanilla_data, config_data, args.config, args.model,
            args.version, args.run_id, vanilla_run_id=vanilla_run
        )

        # Print cost comparison only (trigger analysis already printed)
        print_cost_comparison(report)
        comparisons.append(report)

    # Save combined report
    if comparisons:
        output_dir = script_dir / "analysis" / "analysis-results" / "cost"
        save_combined_report(comparisons, trigger_analysis, args.config, args.model,
                           args.version, args.run_id, output_dir)


if __name__ == "__main__":
    main()
