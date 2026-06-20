"""
Compare cost, steps, and resolution rates between vanilla (default) and planner configs (monitor, refiner-only, refiner).

Executor agent cost from .traj + planner cost from .planner.json
Latency from the .planner.json
Resolution rates from reports
Trigger statistics (instances with .planner.json)

Example usage:
python analysis/compare_cost_w_wo_planner.py --model deepseek-chat-v3-0324 --dataset swebench --config refiner --version 5 --run_id 1 --reproducible
python analysis/compare_cost_w_wo_planner.py --model deepseek-chat-v3-0324 --dataset swebench --agent SWE-agent --config monitor --run_id 1 --reproducible

Input args:
  --agent (default: SWE-agent)
  --config (default: loads all available configs - monitor, refiner-only, refiner)
  --version (default: 5, for refiner and refiner-only configs)
  --run_id (default: 1)
  --reproducible (flag: discover available vanilla runs)

When --dataset is swebench, agent dir is PROJECT_DIR/SWE-agent
When --dataset is swebench-pro, agent dir is PROJECT_DIR/SWE-bench_Pro-os/SWE-agent

Config traj paths:
  - Vanilla (default): {agent_dir}/trajectories/default/{dataset}/{model}/run-{X}/
  - Monitor: {agent_dir}/trajectories/monitor/{dataset}/{model}/run-{run_id}/
  - Refiner-only: {agent_dir}/trajectories/refiner-only/version-{version}/{dataset}/{model}/run-{run_id}/
  - Refiner: {agent_dir}/trajectories/refiner/version-{version}/{dataset}/{model}/run-{run_id}/

Data extracted:
  From .traj: instance_cost, api_calls
  From .planner.json: refiner_total_cost, monitor_total_latency_ms, refiner_total_latency_ms, interventions
  From reports: resolved instance IDs (resolution rate)
  Trigger distribution: type (monitor/refiner), rule_id (plan_compliance if empty for refiner)
  Instances with triggers: count of instances with .planner.json file
"""
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from typing import Set
import numpy as np


def load_report(agent_dir: Path, config: str, dataset: str, model: str, run_id: int, version: str = None) -> Set[str]:
    """Load resolved instance IDs from report file (from collect_pattern_resolution.py)."""
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # For swebench-pro, report is eval_results.json in the run folder
    if dataset == 'swebench-pro':
        if config in ['refiner', 'refiner-only'] and version:
            report_path = agent_dir / "reports" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}" / "eval_results.json"
        else:
            report_path = agent_dir / "reports" / config / dataset_path / model / f"run-{run_id}" / "eval_results.json"

        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    data = json.load(f)
                    return {inst_id for inst_id, resolved in data.items() if resolved}
            except Exception as e:
                print(f"Error loading report {report_path}: {e}")
        return set()

    # For swebench, report is in model directory
    if config in ['refiner', 'refiner-only'] and version:
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


def load_instance_data(instance_dir: Path, instance_id: str, config: str, resolved_ids: Set[str]) -> dict:
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
        'resolved': instance_id in resolved_ids,
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
        'triggers': [],
        'has_planner': False
    }

    # Load planner stats if available (for non-default configs)
    if config != 'default' and planner_file.exists():
        result['has_planner'] = True
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

                # Load resolved IDs for this run
                resolved_ids = load_report(agent_dir, config, dataset, model, run, version)

                for instance_dir in base_path.iterdir():
                    if not instance_dir.is_dir():
                        continue

                    instance_id = instance_dir.name
                    data = load_instance_data(instance_dir, instance_id, config, resolved_ids)
                    if data:
                        all_data.append(data)
        else:
            # Single run mode
            base_path = agent_dir / "trajectories" / "default" / dataset_path / model / "run-1"
            resolved_ids = load_report(agent_dir, config, dataset, model, 1, version)

            if base_path.exists():
                for instance_dir in base_path.iterdir():
                    if not instance_dir.is_dir():
                        continue

                    instance_id = instance_dir.name
                    data = load_instance_data(instance_dir, instance_id, config, resolved_ids)
                    if data:
                        all_data.append(data)
    else:
        # Config trajectories (monitor/refiner-only/refiner)
        # Version is used for refiner and refiner-only configs
        if config in ['refiner', 'refiner-only'] and version:
            base_path = agent_dir / "trajectories" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}"
        else:
            base_path = agent_dir / "trajectories" / config / dataset_path / model / f"run-{run_id}"

        # Load resolved IDs for this config
        resolved_ids = load_report(agent_dir, config, dataset, model, run_id, version)

        if base_path.exists():
            for instance_dir in base_path.iterdir():
                if not instance_dir.is_dir():
                    continue

                instance_id = instance_dir.name
                data = load_instance_data(instance_dir, instance_id, config, resolved_ids)
                if data:
                    all_data.append(data)

    return all_data


def compute_averages(data: list, total_instances: int = None) -> dict:
    """Compute average statistics across instances.

    Args:
        data: List of instance data
        total_instances: Total dataset size for resolution rate calculation (500 for swebench, 264 for swebench-pro)
    """
    if not data:
        return {
            'instance_count': 0,
            'resolved_count': 0,
            'resolution_rate': 0.0,
            'instances_with_triggers': 0,
            'trigger_rate': 0.0,
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

    resolved_count = sum(1 for d in data if d.get('resolved', False))
    instances_with_triggers = sum(1 for d in data if d.get('has_planner', False))

    # Use total_instances for resolution rate if provided, otherwise use len(data)
    rate_denominator = total_instances if total_instances else len(data)

    return {
        'instance_count': len(data),
        'resolved_count': resolved_count,
        'resolution_rate': (resolved_count / rate_denominator * 100) if rate_denominator > 0 else 0.0,
        'instances_with_triggers': instances_with_triggers,
        'trigger_rate': (instances_with_triggers / len(data) * 100) if len(data) > 0 else 0.0,
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
    """Analyze trigger distribution from planner data, separated by monitor/refiner."""
    # Separate counters for monitor and refiner
    monitor_rule_counter = Counter()
    refiner_rule_counter = Counter()
    type_counter = Counter()

    total_monitor_latency = 0
    total_refiner_latency = 0
    instances_with_triggers = 0
    total_trigger_count = 0
    monitor_trigger_count = 0
    refiner_trigger_count = 0

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

            if trigger_type == 'monitor':
                monitor_rule_counter[rule_id] += 1
                monitor_trigger_count += 1
            elif trigger_type == 'refiner':
                refiner_rule_counter[rule_id] += 1
                refiner_trigger_count += 1

    avg_triggers_per_instance = total_trigger_count / len(data) if len(data) > 0 else 0
    avg_triggers_per_triggered_instance = total_trigger_count / instances_with_triggers if instances_with_triggers > 0 else 0

    return {
        'monitor_rule_distribution': dict(monitor_rule_counter),
        'refiner_rule_distribution': dict(refiner_rule_counter),
        'type_distribution': dict(type_counter),
        'instances_with_triggers': instances_with_triggers,
        'total_instances': len(data),
        'trigger_rate': (instances_with_triggers / len(data) * 100) if len(data) > 0 else 0,
        'total_trigger_count': total_trigger_count,
        'monitor_trigger_count': monitor_trigger_count,
        'refiner_trigger_count': refiner_trigger_count,
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
                              config: str, model: str, version: str, run_id: int,
                              vanilla_run_id: int = None, total_instances: int = None) -> dict:
    """Generate comparison report."""
    vanilla_avg = compute_averages(vanilla_data, total_instances)
    config_avg = compute_averages(config_data, total_instances)

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


def print_trigger_analysis(config_data: list, config_name: str, model: str, version: str, run_id: int, total_instances: int = None):
    """Print trigger analysis with monitor/refiner separation."""
    config_avg = compute_averages(config_data, total_instances)
    trigger_stats = analyze_trigger_distribution(config_data)

    print("\n" + "="*80)
    print(f"Trigger & Latency Analysis: {config_name.upper()} (run-{run_id})")
    print(f"Model: {model}")
    if version:
        print(f"Version: {version}")
    print("="*80)

    print(f"\nConfig Instances: {config_avg['instance_count']}")
    print(f"Resolved: {config_avg['resolved_count']} ({config_avg['resolution_rate']:.2f}%)")
    print(f"Instances with Triggers: {config_avg['instances_with_triggers']} ({config_avg['trigger_rate']:.1f}%)")

    # Latency
    print(f"\nLatency:")
    print(f"  Average Total:       {config_avg['avg_latency_ms']:.2f} ms")
    if config_name == 'monitor':
        print(f"  Average Monitor:     {config_avg['avg_monitor_latency_ms']:.2f} ms")
    else:
        print(f"  Average Monitor:     {config_avg['avg_monitor_latency_ms']:.2f} ms")
        print(f"  Average Refiner:     {config_avg['avg_refiner_latency_ms']:.2f} ms")

    # Trigger analysis
    print(f"\nIntervention Statistics:")
    print(f"  Instances with Triggers:       {trigger_stats['instances_with_triggers']}/{trigger_stats['total_instances']} ({trigger_stats['trigger_rate']:.1f}%)")
    print(f"  Total Trigger Count:           {trigger_stats['total_trigger_count']}")
    print(f"  Avg Triggers per Instance:     {trigger_stats['avg_triggers_per_instance']:.2f}")
    print(f"  Avg Triggers (triggered only): {trigger_stats['avg_triggers_per_triggered_instance']:.2f}")

    if config_name == 'monitor':
        print(f"  Monitor Trigger Count:         {trigger_stats['monitor_trigger_count']}")
        print(f"  Avg Monitor Count:             {config_avg['avg_monitor_count']:.2f}")
    else:
        print(f"  Monitor Trigger Count:         {trigger_stats['monitor_trigger_count']}")
        print(f"  Refiner Trigger Count:         {trigger_stats['refiner_trigger_count']}")
        print(f"  Avg Monitor Count:             {config_avg['avg_monitor_count']:.2f}")
        print(f"  Avg Refiner Count:             {config_avg['avg_refiner_count']:.2f}")

    print(f"\nLatency Breakdown:")
    if config_name == 'monitor':
        print(f"  Monitor: {trigger_stats['total_monitor_latency_ms']:.2f} ms (100.0%)")
    else:
        print(f"  Monitor: {trigger_stats['total_monitor_latency_ms']:.2f} ms ({trigger_stats['monitor_latency_pct']:.1f}%)")
        print(f"  Refiner: {trigger_stats['total_refiner_latency_ms']:.2f} ms ({trigger_stats['refiner_latency_pct']:.1f}%)")

    if trigger_stats['type_distribution']:
        print(f"\nTrigger Type Distribution:")
        total_triggers = sum(trigger_stats['type_distribution'].values())
        for ttype, count in sorted(trigger_stats['type_distribution'].items()):
            pct = (count / total_triggers * 100) if total_triggers > 0 else 0
            print(f"  {ttype.capitalize()}: {count} ({pct:.1f}%)")

    # Print rule distribution based on config type
    if config_name == 'monitor' and trigger_stats['monitor_rule_distribution']:
        print(f"\nMonitor Rule Distribution:")
        sorted_rules = sorted(trigger_stats['monitor_rule_distribution'].items(),
                            key=lambda x: x[1], reverse=True)
        total_rules = sum(trigger_stats['monitor_rule_distribution'].values())
        for rule_id, count in sorted_rules[:10]:
            pct = (count / total_rules * 100) if total_rules > 0 else 0
            display_id = rule_id if len(rule_id) <= 60 else rule_id[:57] + '...'
            print(f"  {display_id}: {count} ({pct:.1f}%)")
        if len(sorted_rules) > 10:
            print(f"  ... and {len(sorted_rules) - 10} more rules")
    elif config_name == 'refiner' and trigger_stats['refiner_rule_distribution']:
        print(f"\nRefiner Rule Distribution:")
        sorted_rules = sorted(trigger_stats['refiner_rule_distribution'].items(),
                            key=lambda x: x[1], reverse=True)
        total_rules = sum(trigger_stats['refiner_rule_distribution'].values())
        for rule_id, count in sorted_rules[:10]:
            pct = (count / total_rules * 100) if total_rules > 0 else 0
            display_id = rule_id if len(rule_id) <= 60 else rule_id[:57] + '...'
            print(f"  {display_id}: {count} ({pct:.1f}%)")
        if len(sorted_rules) > 10:
            print(f"  ... and {len(sorted_rules) - 10} more rules")

    print("="*80)


def save_combined_report(comparisons: list, trigger_analysis: dict, dataset: str, config_name: str,
                        model: str, version: str, run_id: int, output_dir: Path):
    """Save combined report with all vanilla comparisons and trigger analysis to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    version_suffix = f"_version-{version}" if (config_name == 'refiner' and version) else ""
    output_file = output_dir / f"{dataset}_{config_name}_{model.split('/')[-1]}_run{run_id}{version_suffix}_cost_comparison.json"

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


def process_config(agent_dir: Path, dataset: str, model: str, config: str,
                   version: str, run_id: int, vanilla_runs: list, script_dir: Path):
    """Process a single planner config (monitor, refiner-only, or refiner) and compare with vanilla runs."""
    # Load config data
    print(f"\nLoading {config} trajectories...")
    if config in ['refiner', 'refiner-only'] and version:
        print(f"  Version: {version}, Run: {run_id}")
    else:
        print(f"  Run: {run_id}")

    config_data = load_trajectory_data(
        agent_dir, dataset, model, config,
        version=version if config in ['refiner', 'refiner-only'] else None,
        run_id=run_id
    )

    if not config_data:
        print(f"  No {config} data found, skipping...")
        return None

    print(f"  Loaded {len(config_data)} {config} instances")

    # Load all vanilla data to determine total_instances
    all_vanilla_data = []
    for vanilla_run in vanilla_runs:
        vanilla_data = load_trajectory_data(
            agent_dir, dataset, model, 'default',
            version=None, run_id=None, runs=[vanilla_run]
        )
        if vanilla_data:
            all_vanilla_data.append(vanilla_data)

    # Determine total instances: max of config and all vanilla runs
    total_instances = max(len(config_data), max((len(vd) for vd in all_vanilla_data), default=0))

    # Compute and print cost breakdown for the config
    config_avg = compute_averages(config_data, total_instances)
    print(f"\nConfig Cost Breakdown:")
    print(f"  Executor Cost:  ${config_avg['avg_executor_cost']:.6f}")
    if 'refiner' in config:
        print(f"  Refiner Cost:   ${config_avg['avg_refiner_cost']:.6f}")
    print(f"  Total Cost:     ${config_avg['avg_total_cost']:.6f}")

    # Print trigger analysis for planner configs only
    print_trigger_analysis(config_data, config, model, version if config in ['refiner', 'refiner-only'] else None, run_id, total_instances)
    trigger_analysis = analyze_trigger_distribution(config_data)

    # Compare each vanilla run with config
    comparisons = []
    for vanilla_run, vanilla_data in zip(vanilla_runs, all_vanilla_data):
        if not vanilla_data:
            print(f"\n  Warning: No data loaded for vanilla run {vanilla_run}, skipping...")
            continue

        print(f"\n{'='*80}")
        print(f"Comparing with Vanilla Run {vanilla_run}")
        print(f"{'='*80}")
        print(f"  Loaded {len(vanilla_data)} vanilla instances from run {vanilla_run}")

        report = generate_comparison_report(
            vanilla_data, config_data, config, model,
            version if config in ['refiner', 'refiner-only'] else None,
            run_id, vanilla_run_id=vanilla_run, total_instances=total_instances
        )

        print_cost_comparison(report)
        comparisons.append(report)

    # Save combined report
    if comparisons:
        output_dir = script_dir / "analysis" / "analysis-results" / "cost"
        save_combined_report(comparisons, trigger_analysis, dataset, config, model,
                           version if config in ['refiner', 'refiner-only'] else None,
                           run_id, output_dir)

    return True


def main():
    parser = argparse.ArgumentParser(description='Compare cost and steps between vanilla and planner configs')
    parser.add_argument('--dataset', type=str, default='swebench',
                       help='Dataset name (swebench or swebench-pro)')
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent directory name')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., deepseek-chat-v3-0324)')
    parser.add_argument('--config', type=str, default=None,
                       help='Config type (monitor or refiner, default: both)')
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

    # Discover vanilla runs
    print("Loading vanilla trajectories...")
    if args.reproducible:
        vanilla_runs = discover_available_runs(agent_dir, args.dataset, args.model)
        if not vanilla_runs:
            print("  Warning: No vanilla runs found, falling back to run-1")
            vanilla_runs = [1]
        else:
            print(f"  Discovered vanilla runs: {vanilla_runs}")
    else:
        vanilla_runs = [1]
        print("  Using run-1")

    # Determine which configs to process
    if args.config:
        configs_to_process = [args.config]
    else:
        # Try all planner configs: monitor, refiner-only, refiner
        configs_to_process = ['monitor', 'refiner-only', 'refiner']

    # Process each config
    processed_count = 0
    for config in configs_to_process:
        print(f"\n{'#'*80}")
        print(f"Processing Config: {config.upper()}")
        print(f"{'#'*80}")

        result = process_config(
            agent_dir, args.dataset, args.model, config,
            args.version, args.run_id, vanilla_runs, script_dir
        )

        if result:
            processed_count += 1

    if processed_count == 0:
        print("\nNo data processed. Please check the paths and file availability.")
    else:
        print(f"\n\nProcessed {processed_count} config(s) successfully.")


if __name__ == "__main__":
    main()
