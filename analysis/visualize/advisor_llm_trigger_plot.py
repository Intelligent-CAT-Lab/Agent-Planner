"""
Compute and compare the 1. avg. number of refiner LLM interventions 2. percentage of instances with .planner.json out of the total instances (264 if swebench-pro; 500 if swebench) between the configs (default to ['refiner-only', 'refiner'])
Generate the figure under figures/: each subplot is a bar chart of a <model, dataset> comparing the config statistics.
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
skip if one of a corresponding config is unavailable; for example, we only have swebench-pro for all models and only deepseek-chat-v3-0324 on swebench. Detect smartly.
hint: the difference between the absolute number of avg. number of intervention and percentage number may be high; ensure the visualization is readable and clear (e.g. use different y-ordinate value for the two numbers.). Put the config stats side by side for better comparison.
"""
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# Load visualization name mappings
def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']

MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()


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
        return None

    total_instances = 0
    instances_with_interventions = 0
    total_interventions = 0

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

    if total_instances == 0:
        return None

    avg_per_instance = total_interventions / total_instances
    percentage_with_planner = (total_instances / (264 if dataset == 'swebench-pro' else 500)) * 100

    return {
        'config': config,
        'total_instances': total_instances,
        'instances_with_interventions': instances_with_interventions,
        'total_interventions': total_interventions,
        'avg_interventions_per_instance': avg_per_instance,
        'percentage_with_planner': percentage_with_planner
    }


def create_visualization(data: Dict[Tuple[str, str], Dict[str, Dict]],
                        datasets: List[str],
                        models: List[str],
                        configs: List[str],
                        output_path: Path):
    """
    Create a compact grid visualization with dual y-axes for each subplot.
    Only includes subplots where multiple configs are available.

    Args:
        data: Nested dict {(dataset, model): {config: stats}}
        datasets: List of datasets
        models: List of models
        configs: List of configs
        output_path: Path to save the figure
    """
    # Filter to only include dataset-model pairs with multiple configs
    valid_pairs = [
        (d, m) for d in datasets for m in models
        if (d, m) in data and len(data[(d, m)]) > 1
    ]

    if not valid_pairs:
        print("No valid data to plot (need at least 2 configs per dataset-model pair)")
        return

    # Create figure with adaptive layout: 1 row if 3 or fewer subplots, otherwise 2 columns
    n_pairs = len(valid_pairs)

    if n_pairs <= 3:
        # Use 1 row layout for 3 or fewer subplots
        ncols = n_pairs
        nrows = 1
        fig, axes = plt.subplots(nrows, ncols, figsize=(15 * ncols, 12))
        fig.subplots_adjust(hspace=0.30, wspace=0.20, left=0.09, right=0.92, top=0.92, bottom=0.22)

        # Ensure axes is always 2D array
        if ncols == 1:
            axes = np.array([[axes]])
        else:
            axes = axes.reshape(1, -1)
    else:
        # Use 2-column layout for more subplots
        ncols = 2
        nrows = (n_pairs + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5.2 * nrows))
        fig.subplots_adjust(hspace=0.30, wspace=0.15, left=0.09, right=0.91, top=0.88, bottom=0.08)

        # Ensure axes is always 2D array
        if nrows == 1:
            axes = axes.reshape(1, -1)

    # Colors for configs
    colors = {'refiner-only': '#3b82f6', 'refiner': '#10b981'}

    # Track global min/max for shared y-axes
    all_avg_interventions = []
    all_percentages = []
    for (d, m), model_data in data.items():
        if (d, m) in valid_pairs:
            for config, stats in model_data.items():
                all_avg_interventions.append(stats['avg_interventions_per_instance'])
                all_percentages.append(stats['percentage_with_planner'])

    # Set shared y-axis limits
    max_avg = max(all_avg_interventions) if all_avg_interventions else 1
    y1_max = max_avg * 1.25
    y2_max = 100  # Percentage should always be 0-100

    # Check if all pairs have the same dataset (for title display logic)
    unique_datasets = set(d for d, m in valid_pairs)
    single_dataset = len(unique_datasets) == 1

    # Track twin axes for each subplot
    twin_axes = {}

    for idx, (dataset, model) in enumerate(valid_pairs):
        row = idx // ncols
        col = idx % ncols
        ax1 = axes[row, col]
        ax2 = ax1.twinx()
        twin_axes[(row, col)] = ax2

        model_data = data[(dataset, model)]
        available_configs = [c for c in configs if c in model_data]

        if not available_configs:
            ax1.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax1.transAxes)
            # ax1.set_title(f"{model}\n{dataset}", fontsize=12, fontweight='bold')
            ax1.set_title(f"{model}", fontsize=12, fontweight='bold')
            continue

        x_pos = np.arange(len(available_configs))
        width = 0.35

        # Bar 1: Average interventions per instance (left y-axis)
        avg_interventions = [model_data[c]['avg_interventions_per_instance'] for c in available_configs]
        bars1 = ax1.bar(x_pos - width/2, avg_interventions, width,
                       label='Avg. Interventions',
                       color=[colors[c] for c in available_configs],
                       alpha=0.8, edgecolor='black', linewidth=0.5)

        # Bar 2: Percentage with planner (right y-axis)
        percentages = [model_data[c]['percentage_with_planner'] for c in available_configs]
        bars2 = ax2.bar(x_pos + width/2, percentages, width,
                       label='% with Planner',
                       color=[colors[c] for c in available_configs],
                       alpha=0.4, edgecolor='black', linewidth=0.5, hatch='//')

        # Add value labels inside bars
        for i, (bar, val) in enumerate(zip(bars1, avg_interventions)):
            height = bar.get_height()
            # Place text inside the bar
            ax1.text(bar.get_x() + bar.get_width()/2., height * 0.5,
                    f'{val:.2f}', ha='center', va='center', fontsize=48, fontweight='bold',
                    color='black')

        for i, (bar, val) in enumerate(zip(bars2, percentages)):
            height = bar.get_height()
            # Place text inside the bar
            ax2.text(bar.get_x() + bar.get_width()/2., height * 0.5,
                    f'{val:.1f}%', ha='center', va='center', fontsize=48, fontweight='bold',
                    color='black')

        # Configure axes
        ax1.set_xticks(x_pos)
        # Map config names for display
        display_configs = [CONFIG_NAME_MAP.get(c, c) for c in available_configs]
        ax1.set_xticklabels(display_configs, fontsize=46, fontweight='bold')

        # Only show y-axis labels on leftmost (col 0) and rightmost (last col) subplots
        if col == 0:
            ax1.set_ylabel('Avg. Interventions\nper Instance', fontsize=46, fontweight='bold', color='black')
        else:
            ax1.set_ylabel('')
            ax1.tick_params(axis='y', labelleft=False)

        if col == ncols - 1:
            ax2.set_ylabel('% Instances\nwith Advisor', fontsize=46, fontweight='bold', color='black')
        else:
            ax2.set_ylabel('')
            ax2.tick_params(axis='y', labelright=False)

        ax1.tick_params(axis='y', labelsize=44)
        ax2.tick_params(axis='y', labelsize=44)

        # Use shared y-axis limits
        ax1.set_ylim(0, y1_max)
        ax2.set_ylim(0, y2_max)

        ax1.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.5)
        ax1.set_axisbelow(True)

        # Title with mapped names
        model_display = MODEL_NAME_MAP.get(model, model)
        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)

        # Only show dataset in title if there are multiple datasets
        if single_dataset:
            ax1.set_title(f"{model_display}", fontsize=48, fontweight='bold', pad=20)
        else:
            ax1.set_title(f"{model_display}\n{dataset_display}", fontsize=48, fontweight='bold', pad=20)

    # Hide unused subplots
    for row in range(nrows):
        for col in range(ncols):
            idx = row * ncols + col
            if idx >= n_pairs:
                axes[row, col].axis('off')
                if (row, col) in twin_axes:
                    twin_axes[(row, col)].axis('off')

    # Create custom legend with mapped config names
    legend_elements = [
        mpatches.Patch(facecolor=colors['refiner-only'], edgecolor='black', linewidth=0.5,
                      label=CONFIG_NAME_MAP.get('refiner-only', 'Refiner-only'), alpha=0.8),
        mpatches.Patch(facecolor=colors['refiner'], edgecolor='black', linewidth=0.5,
                      label=CONFIG_NAME_MAP.get('refiner', 'Refiner'), alpha=0.8),
        mpatches.Patch(facecolor='gray', edgecolor='black', linewidth=0.5,
                      label='Avg. Interventions (solid)', alpha=0.8),
        mpatches.Patch(facecolor='gray', edgecolor='black', linewidth=0.5, hatch='//',
                      label='% with Advisor (hatched)', alpha=0.4)
    ]

    # Place legend below the plot for single-row layout, above for multi-row
    if n_pairs <= 3:
        fig.legend(handles=legend_elements, loc='lower center', ncol=4,
                  frameon=True, fontsize=46, bbox_to_anchor=(0.5, 0.03), edgecolor='black')
    else:
        fig.legend(handles=legend_elements, loc='upper center', ncol=4,
                  frameon=True, fontsize=46, bbox_to_anchor=(0.5, 0.98), edgecolor='black')

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Visualize refiner LLM intervention statistics"
    )
    parser.add_argument("--datasets", nargs="+",
                       default=['swebench-pro'],
                       help="Datasets to analyze")
    parser.add_argument("--models", nargs="+",
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help="Models to analyze")
    parser.add_argument("--configs", nargs="+",
                       default=['refiner-only', 'refiner'],
                       help="Configs to compare")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    parser.add_argument("--version", default='5', help="Version for refiner configs")
    parser.add_argument("--output-dir", default="analysis/figures",
                       help="Output directory for figures")

    args = parser.parse_args()

    base_dir = Path("/home/shuyang/Agent-Planner")
    output_dir = base_dir / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Computing refiner intervention statistics...")
    print(f"Datasets: {args.datasets}")
    print(f"Models: {args.models}")
    print(f"Configs: {args.configs}\n")

    # Collect data
    data = {}
    for dataset in args.datasets:
        agent_dir = base_dir / "SWE-agent" if dataset == "swebench" else base_dir / "SWE-bench_Pro-os" / "SWE-agent"

        for model in args.models:
            print(f"Processing {dataset} - {model}:")
            model_data = {}

            for config in args.configs:
                stats = compute_frequency(agent_dir, config, dataset, model, args.run_id, args.version)
                if stats:
                    model_data[config] = stats
                    print(f"  {config}: {stats['total_instances']} instances, "
                          f"{stats['avg_interventions_per_instance']:.2f} avg interventions, "
                          f"{stats['percentage_with_planner']:.1f}% with planner")
                else:
                    print(f"  {config}: No data found")

            if model_data:
                data[(dataset, model)] = model_data
            print()

    if not data:
        print("No data collected. Exiting.")
        return

    # Report which pairs will be skipped (only 1 config)
    print("\n" + "="*70)
    print("Data availability check:")
    print("="*70)
    for dataset in args.datasets:
        for model in args.models:
            if (dataset, model) in data:
                num_configs = len(data[(dataset, model)])
                status = "✓ Included" if num_configs > 1 else "✗ Skipped (only 1 config)"
                print(f"{DATASET_NAME_MAP.get(dataset, dataset)} - {MODEL_NAME_MAP.get(model, model)}: "
                      f"{num_configs} config(s) - {status}")
            else:
                print(f"{DATASET_NAME_MAP.get(dataset, dataset)} - {MODEL_NAME_MAP.get(model, model)}: "
                      f"0 configs - ✗ Skipped (no data)")

    # Create visualization
    output_path = output_dir / "advisor_llm_trigger_stats.pdf"
    create_visualization(data, args.datasets, args.models, args.configs, output_path)

    # Print summary
    print("\n" + "="*70)
    print("Summary Statistics")
    print("="*70)
    for (dataset, model), model_data in data.items():
        print(f"\n{DATASET_NAME_MAP.get(dataset, dataset)} - {MODEL_NAME_MAP.get(model, model)}:")
        for config, stats in model_data.items():
            print(f"  {config}:")
            print(f"    Instances with planner: {stats['total_instances']}")
            print(f"    Avg. interventions: {stats['avg_interventions_per_instance']:.2f}")
            print(f"    % with planner: {stats['percentage_with_planner']:.1f}%")


if __name__ == "__main__":
    main()
