"""
Compute the average number of refiner interventions across all instances.

.planner.json is stored under:
{agent-dir}/trajectories/{config}/(version-{version} if config is refiner or refiner-only)/{dataset}(/python if dataset is swebench-pro)/{model}/run-{run_id}/

- agent: default SWE-agent
- agent-dir: SWE-bench_Pro-os/SWE-agent/ if dataset is swebench-pro
- version: default 5
- config: refiner, refiner-only (when available)
- Only count interventions where "planner_type" is "refiner" AND content contains "[Plan Refiner Guidance]"

Usage:
    python analysis/compute_refine_frequency.py --model deepseek-chat-v3-0324 --dataset swebench
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List


def count_refiner_interventions(planner_path: Path) -> int:
    """
    Count refiner interventions in a planner.json file.
    Only counts interventions where planner_type is 'refiner' AND content contains '[Plan Refiner Guidance]'.
    """
    try:
        with open(planner_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        interventions = data.get('interventions', [])
        count = 0

        for intervention in interventions:
            planner_type = intervention.get('planner_type')
            content = intervention.get('content', '')

            if planner_type == 'refiner' and '[Plan Refiner Guidance]' in content:
                count += 1

        return count
    except Exception as e:
        print(f"Warning: Error processing {planner_path}: {e}")
        return 0


def compute_frequency(agent_dir: Path, config: str, dataset: str, model: str,
                     run_id: int, version: str = '5') -> Dict:
    """
    Compute refiner intervention frequency for a given configuration.

    Returns:
        Dict with statistics including total instances, instances with interventions,
        total interventions, and average interventions per instance.
    """
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # Build trajectory base path
    if config in ['refiner', 'refiner-only'] and version:
        traj_base = agent_dir / "trajectories" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}"
    else:
        traj_base = agent_dir / "trajectories" / config / dataset_path / model / f"run-{run_id}"

    if not traj_base.exists():
        return {
            'config': config,
            'total_instances': 0,
            'instances_with_interventions': 0,
            'total_interventions': 0,
            'avg_interventions_per_instance': 0.0,
            'avg_interventions_per_triggered': 0.0,
            'error': f'Path not found: {traj_base}'
        }

    total_instances = 0
    instances_with_interventions = 0
    total_interventions = 0
    intervention_counts = []

    for instance_dir in traj_base.iterdir():
        if not instance_dir.is_dir():
            continue

        instance_id = instance_dir.name
        planner_path = instance_dir / f"{instance_id}.planner.json"

        if not planner_path.exists():
            continue

        total_instances += 1
        count = count_refiner_interventions(planner_path)

        if count > 0:
            instances_with_interventions += 1
            total_interventions += count
            intervention_counts.append(count)

    avg_per_instance = total_interventions / total_instances if total_instances > 0 else 0.0
    avg_per_triggered = total_interventions / instances_with_interventions if instances_with_interventions > 0 else 0.0

    return {
        'config': config,
        'total_instances': total_instances,
        'instances_with_interventions': instances_with_interventions,
        'total_interventions': total_interventions,
        'avg_interventions_per_instance': avg_per_instance,
        'avg_interventions_per_triggered': avg_per_triggered,
        'intervention_counts': intervention_counts
    }


def print_statistics(stats: Dict):
    """Print formatted statistics."""
    config = stats['config'].upper()
    print(f"\n{'='*80}")
    print(f"REFINER INTERVENTION FREQUENCY - {config}")
    print(f"{'='*80}")

    if 'error' in stats:
        print(f"Error: {stats['error']}")
        return

    print(f"\nTotal instances: {stats['total_instances']}")
    print(f"Instances with refiner interventions: {stats['instances_with_interventions']} "
          f"({stats['instances_with_interventions']/stats['total_instances']*100:.1f}%)")
    print(f"Total refiner interventions: {stats['total_interventions']}")
    print(f"\nAverage interventions per instance (all): {stats['avg_interventions_per_instance']:.2f}")
    print(f"Average interventions per triggered instance: {stats['avg_interventions_per_triggered']:.2f}")

    if stats['intervention_counts']:
        counts = stats['intervention_counts']
        print(f"\nIntervention count distribution:")
        print(f"  Min: {min(counts)}")
        print(f"  Max: {max(counts)}")
        print(f"  Median: {sorted(counts)[len(counts)//2]}")


def main():
    parser = argparse.ArgumentParser(
        description='Compute average number of refiner interventions across instances'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name (default: SWE-agent)')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., deepseek-chat-v3-0324)')
    parser.add_argument('--dataset', type=str, default='swebench',
                       help='Dataset name (default: swebench)')
    parser.add_argument('--run-id', type=int, default=1,
                       help='Run ID (default: 1)')
    parser.add_argument('--version', type=str, default='5',
                       help='Version for refiner/refiner-only (default: 5)')
    parser.add_argument('--configs', type=str, nargs='+', default=['refiner', 'refiner-only'],
                       help='Configs to analyze (default: refiner refiner-only)')

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
    print(f"Run ID: {args.run_id}")
    print(f"Version: {args.version}")

    # Compute statistics for each config
    all_stats = []
    for config in args.configs:
        stats = compute_frequency(
            agent_dir=agent_dir,
            config=config,
            dataset=args.dataset,
            model=args.model,
            run_id=args.run_id,
            version=args.version
        )
        all_stats.append(stats)
        print_statistics(stats)

    # Summary comparison if multiple configs
    if len(all_stats) > 1:
        print(f"\n{'='*80}")
        print("COMPARISON SUMMARY")
        print(f"{'='*80}\n")

        for stats in all_stats:
            if 'error' not in stats and stats['total_instances'] > 0:
                print(f"{stats['config']:15s}: {stats['avg_interventions_per_triggered']:.2f} interventions/triggered instance "
                      f"({stats['instances_with_interventions']}/{stats['total_instances']} triggered)")


if __name__ == "__main__":
    main()
