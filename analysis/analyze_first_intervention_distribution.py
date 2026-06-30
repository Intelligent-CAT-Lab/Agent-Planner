"""
Parse the analysis-results/comparison/detailed-analysis/{config}(default to 'refiner')/{agent}-{model}-{dataset}-{config}-analysis.json
agent default to SWE-agent. Per each dataset-model pair, get the U-R instances. (an arg, default to 'U-R'). Per instance, get the step of the first intervention, divide by the total number of steps in the instance. Compute the average. Also get the overall avg across all pairs.
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'].
"""
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np


def load_analysis_file(analysis_dir: Path, agent: str, model: str, dataset: str, config: str) -> Dict:
    """Load analysis JSON file."""
    filename = f"{agent}-{model}-{dataset}-{config}-analysis.json"
    filepath = analysis_dir / config / filename

    if not filepath.exists():
        print(f"Warning: File not found: {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None


def analyze_first_intervention(data: Dict, instance_type: str = 'U-R') -> Tuple[List[float], int]:
    """
    Analyze first intervention timing for specified instance type.

    Returns:
        Tuple of (list of normalized positions, count of instances)
    """
    if not data:
        return [], 0

    # Navigate to category_details
    category_details = data.get('category_details', {})
    category_data = category_details.get(instance_type, {})

    if not category_data:
        return [], 0

    instances = category_data.get('instances', [])
    if not instances:
        return [], 0

    normalized_positions = []

    for instance in instances:
        # Get refiner data
        refiner_data = instance.get('refiner', {})

        # Check if has planner
        if not refiner_data.get('has_planner', False):
            continue

        # Get planner stats
        planner_stats = refiner_data.get('planner_stats', {})
        interventions = planner_stats.get('interventions', [])

        if not interventions:
            continue

        # Get first intervention step
        first_intervention_step = interventions[0].get('step')
        if first_intervention_step is None:
            continue

        # Get total steps from refiner
        total_steps = refiner_data.get('steps')
        if not total_steps or total_steps == 0:
            continue

        # Compute normalized position
        normalized_pos = first_intervention_step / total_steps
        normalized_positions.append(normalized_pos)

    return normalized_positions, len(normalized_positions)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze first intervention timing distribution'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name (default: SWE-agent)')
    parser.add_argument('--config', type=str, default='refiner',
                       help='Config name (default: refiner)')
    parser.add_argument('--datasets', nargs='+',
                       default=['swebench', 'swebench-pro'],
                       help='Dataset names')
    parser.add_argument('--models', nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='Model names')
    parser.add_argument('--instance-type', type=str, default='U-R',
                       help='Instance type to analyze (default: U-R)')

    args = parser.parse_args()

    # Determine analysis directory
    script_dir = Path(__file__).parent
    analysis_dir = script_dir / "analysis-results" / "comparison" / "detailed-analysis"

    if not analysis_dir.exists():
        print(f"Error: Analysis directory not found: {analysis_dir}")
        return

    print(f"\n{'='*70}")
    print(f"First Intervention Timing Analysis")
    print(f"{'='*70}")
    print(f"Agent: {args.agent}")
    print(f"Config: {args.config}")
    print(f"Instance type: {args.instance_type}")
    print(f"Datasets: {args.datasets}")
    print(f"Models: {args.models}")
    print(f"{'='*70}\n")

    # Collect data for all dataset-model pairs
    all_positions = []
    results = {}

    for dataset in args.datasets:
        for model in args.models:
            print(f"Processing {dataset} - {model}...")

            # Load analysis file
            data = load_analysis_file(analysis_dir, args.agent, model, dataset, args.config)

            if data is None:
                print(f"  No data available")
                continue

            # Analyze first intervention timing
            positions, count = analyze_first_intervention(data, args.instance_type)

            if count == 0:
                print(f"  No {args.instance_type} instances with interventions")
                continue

            # Compute statistics
            avg_position = np.mean(positions)
            median_position = np.median(positions)
            std_position = np.std(positions)

            results[(dataset, model)] = {
                'positions': positions,
                'count': count,
                'avg': avg_position,
                'median': median_position,
                'std': std_position
            }

            all_positions.extend(positions)

            print(f"  Instances: {count}")
            print(f"  Avg normalized position: {avg_position:.3f}")
            print(f"  Median normalized position: {median_position:.3f}")
            print(f"  Std dev: {std_position:.3f}")
            print()

    # Compute overall statistics
    if all_positions:
        overall_avg = np.mean(all_positions)
        overall_median = np.median(all_positions)
        overall_std = np.std(all_positions)
        total_instances = len(all_positions)

        print(f"\n{'='*70}")
        print(f"Overall Statistics (across all dataset-model pairs)")
        print(f"{'='*70}")
        print(f"Total instances: {total_instances}")
        print(f"Avg normalized position: {overall_avg:.3f}")
        print(f"Median normalized position: {overall_median:.3f}")
        print(f"Std dev: {overall_std:.3f}")

        # Distribution statistics
        print(f"\nDistribution:")
        print(f"  First quartile (25%): {np.percentile(all_positions, 25):.3f}")
        print(f"  Second quartile (50%): {np.percentile(all_positions, 50):.3f}")
        print(f"  Third quartile (75%): {np.percentile(all_positions, 75):.3f}")
        print(f"  Min: {np.min(all_positions):.3f}")
        print(f"  Max: {np.max(all_positions):.3f}")

        # Timing categories
        early = sum(1 for p in all_positions if p < 0.33)
        middle = sum(1 for p in all_positions if 0.33 <= p < 0.67)
        late = sum(1 for p in all_positions if p >= 0.67)

        print(f"\nTiming Categories:")
        print(f"  Early (< 33%): {early} ({early/total_instances*100:.1f}%)")
        print(f"  Middle (33-67%): {middle} ({middle/total_instances*100:.1f}%)")
        print(f"  Late (>= 67%): {late} ({late/total_instances*100:.1f}%)")

    else:
        print("\nNo data found for the specified configuration")

    # Per-dataset summary
    if results:
        print(f"\n{'='*70}")
        print(f"Per-Dataset Summary")
        print(f"{'='*70}")

        for dataset in args.datasets:
            dataset_positions = []
            dataset_count = 0

            for model in args.models:
                key = (dataset, model)
                if key in results:
                    dataset_positions.extend(results[key]['positions'])
                    dataset_count += results[key]['count']

            if dataset_positions:
                dataset_avg = np.mean(dataset_positions)
                print(f"\n{dataset}:")
                print(f"  Total instances: {dataset_count}")
                print(f"  Avg normalized position: {dataset_avg:.3f}")


if __name__ == "__main__":
    main()