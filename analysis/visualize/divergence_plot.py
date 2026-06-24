"""
Generate figure for divergence analysis. Each subplot is a boxplot showing the median-iqr values of the similarity.
Two rows (subplots): dataset (default to ['swebench-pro', 'swebench']). Per model (default to ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']) has value of action similarity and phase similarity.
Default config: ['refiner'].
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from tqdm import tqdm

# Add analysis directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze_divergence import analyze_divergence


def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()


def get_cache_path(analysis_dir: Path, agent: str, config: str, model: str, dataset: str, version: Optional[int]) -> Path:
    """Get cache file path for divergence analysis results."""
    version_str = f"-v{version}" if version else ""
    cache_dir = analysis_dir / "comparison" / "divergence"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{config}-{agent}-{model}-{dataset}{version_str}-divergence.json"


def run_analysis_worker(args):
    """Worker function for parallel analysis execution."""
    agent, config, version, model, dataset, run_id, analysis_dir = args
    try:
        results = analyze_divergence(
            agent=agent,
            model=model,
            dataset=dataset,
            config=config,
            version=version,
            run_id=run_id,
            analysis_dir=analysis_dir
        )
        cache_path = get_cache_path(analysis_dir, agent, config, model, dataset, version)
        with open(cache_path, 'w') as f:
            json.dump(results, f, indent=2)
        return cache_path, None
    except Exception as e:
        return None, str(e)


def load_or_compute_divergence(
    agent: str,
    configs: List[str],
    models: List[str],
    datasets: List[str],
    version: int,
    run_id: int,
    analysis_dir: Path,
    skip_analysis: bool = False,
    num_workers: int = 8
) -> Dict:
    """
    Load cached divergence results or compute them if needed.

    Returns:
        Dictionary mapping (config, model, dataset) -> divergence results
    """
    results = {}

    # Prepare work items
    work_items = []
    for config in configs:
        for model in models:
            for dataset in datasets:
                v = version if config == 'refiner' else None
                cache_path = get_cache_path(analysis_dir, agent, config, model, dataset, v)

                if cache_path.exists():
                    # Load from cache
                    try:
                        with open(cache_path) as f:
                            data = json.load(f)
                        results[(config, model, dataset)] = data
                    except Exception as e:
                        print(f"Warning: Failed to load cache {cache_path}: {e}")
                        if not skip_analysis:
                            work_items.append((agent, config, v, model, dataset, run_id, analysis_dir))
                else:
                    if not skip_analysis:
                        work_items.append((agent, config, v, model, dataset, run_id, analysis_dir))
                    else:
                        print(f"Warning: Cache not found for {config}/{model}/{dataset} and --skip-analysis is set")

    # Run analysis for missing data
    if work_items:
        print(f"\nRunning divergence analysis for {len(work_items)} configurations...")

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(run_analysis_worker, args): args for args in work_items}

            for future in tqdm(as_completed(futures), total=len(futures), desc="Analyzing"):
                cache_path, error = future.result()
                work_args = futures[future]

                if error:
                    print(f"Error analyzing {work_args[1]}/{work_args[3]}/{work_args[4]}: {error}")
                elif cache_path:
                    # Load the newly computed result
                    try:
                        with open(cache_path) as f:
                            data = json.load(f)
                        config, model, dataset = work_args[1], work_args[3], work_args[4]
                        results[(config, model, dataset)] = data
                    except Exception as e:
                        print(f"Warning: Failed to load newly computed result: {e}")

    return results


def extract_similarity_data(results: Dict, configs: List[str], models: List[str], datasets: List[str]) -> Dict:
    """
    Extract similarity values for boxplot visualization.

    Returns:
        Dictionary with structure:
        {
            (config, dataset, model): {
                'prefix_action': [values],
                'prefix_phase': [values],
                'full_action': [values],
                'full_phase': [values]
            }
        }
    """
    similarity_data = {}

    for config in configs:
        for dataset in datasets:
            for model in models:
                key = (config, model, dataset)
                if key not in results:
                    continue

                data = results[key]
                instances = data.get('instances', {})

                # Collect all instance-level similarities
                prefix_action = []
                prefix_phase = []
                full_action = []
                full_phase = []

                for category_instances in instances.values():
                    for inst in category_instances:
                        prefix_sim = inst.get('prefix_similarity', {})
                        full_sim = inst.get('full_similarity', {})

                        prefix_action.append(prefix_sim.get('action_lcs', 0))
                        prefix_phase.append(prefix_sim.get('phase_lcs', 0))
                        full_action.append(full_sim.get('action_lcs', 0))
                        full_phase.append(full_sim.get('phase_lcs', 0))

                if prefix_action:  # Only add if we have data
                    similarity_data[(config, dataset, model)] = {
                        'prefix_action': prefix_action,
                        'prefix_phase': prefix_phase,
                        'full_action': full_action,
                        'full_phase': full_phase
                    }

    return similarity_data


def create_divergence_boxplot(
    similarity_data: Dict,
    configs: List[str],
    models: List[str],
    datasets: List[str],
    output_path: Path
):
    """
    Create boxplot figure showing divergence across datasets and models.

    Layout: 2 rows (datasets) x 1 column
    Each subplot shows boxplots for each model with prefix/full action/phase similarities
    Order per model: prefix action, full action, prefix phase, full phase
    """
    # Reorder datasets: swebench-pro first
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    if not ordered_datasets:
        print("No datasets to plot")
        return

    # Create figure with subplots - more compact
    n_rows = len(ordered_datasets)
    fig, axes = plt.subplots(n_rows, 1, figsize=(15, 5 * n_rows))

    if n_rows == 1:
        axes = [axes]

    # Colors: more differentiable while keeping similar tones
    # Action: blues (dark for prefix, lighter for full)
    # Phase: oranges (dark for prefix, lighter for full)
    colors = {
        'prefix_action': '#08519c',  # dark blue
        'full_action': '#6baed6',    # light blue
        'prefix_phase': '#d94801',   # dark orange
        'full_phase': '#fdae6b'      # light orange
    }

    for row_idx, dataset in enumerate(ordered_datasets):
        ax = axes[row_idx]

        # Collect data for this dataset across all models and configs
        plot_data = []
        positions = []
        pos_counter = 0

        model_tick_positions = []
        model_tick_labels = []

        for model in models:
            for config in configs:
                key = (config, dataset, model)
                if key not in similarity_data:
                    continue

                data = similarity_data[key]

                # Order: prefix action, full action, prefix phase, full phase
                plot_data.append(data['prefix_action'])
                plot_data.append(data['full_action'])
                plot_data.append(data['prefix_phase'])
                plot_data.append(data['full_phase'])

                # Positions: tighter spacing within group, larger gap between models
                positions.extend([pos_counter, pos_counter + 0.4, pos_counter + 0.9, pos_counter + 1.3])

                # Mark model center position
                model_tick_positions.append(pos_counter + 0.65)
                model_display = MODEL_NAME_MAP.get(model, model)
                model_tick_labels.append(model_display)

                pos_counter += 2.5  # Gap between models

        if not plot_data:
            continue

        # Create boxplot with thinner boxes
        bp = ax.boxplot(plot_data,
                       positions=positions,
                       widths=0.35,  # Thinner boxes
                       patch_artist=True,
                       showfliers=False,
                       medianprops=dict(color='black', linewidth=3),
                       boxprops=dict(linewidth=1.5),
                       whiskerprops=dict(linewidth=1.5),
                       capprops=dict(linewidth=1.5))

        # Color boxes by similarity type
        sim_order = ['prefix_action', 'full_action', 'prefix_phase', 'full_phase']
        for i, box in enumerate(bp['boxes']):
            sim_type_idx = i % 4
            sim_type = sim_order[sim_type_idx]
            box.set_facecolor(colors[sim_type])
            box.set_alpha(0.8)
            box.set_edgecolor('black')

        # Set x-axis labels (model names)
        ax.set_xticks(model_tick_positions)
        ax.set_xticklabels(model_tick_labels, fontsize=24, fontweight='bold')

        # Y-axis
        ax.set_ylabel('LCS Similarity', fontsize=26, fontweight='bold')
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis='y', labelsize=22)
        ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.8)

        # Dataset title
        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)
        ax.set_title(dataset_display, fontsize=28, fontweight='bold', pad=15)

        # Add vertical lines to separate models - correct position
        for i in range(1, len(model_tick_positions)):
            separator_pos = (model_tick_positions[i-1] + model_tick_positions[i]) / 2
            ax.axvline(x=separator_pos, color='gray', linestyle=':', linewidth=1.5, alpha=0.6)

    # Add legend to the bottom with better spacing
    legend_elements = [
        mpatches.Patch(facecolor=colors['prefix_action'], edgecolor='black', alpha=0.8, label='Prefix Action'),
        mpatches.Patch(facecolor=colors['full_action'], edgecolor='black', alpha=0.8, label='Full Action'),
        mpatches.Patch(facecolor=colors['prefix_phase'], edgecolor='black', alpha=0.8, label='Prefix Phase'),
        mpatches.Patch(facecolor=colors['full_phase'], edgecolor='black', alpha=0.8, label='Full Phase')
    ]

    fig.legend(handles=legend_elements, loc='lower center', ncol=4,
              fontsize=22, frameon=True, bbox_to_anchor=(0.5, -0.01),
              edgecolor='black', fancybox=False)

    # Adjust layout to be more compact and prevent text overlap
    plt.tight_layout(rect=[0, 0.06, 1, 0.98])
    plt.subplots_adjust(hspace=0.3)  # Vertical spacing between subplots

    # Save figure
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_path}")

    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate divergence analysis boxplot visualization"
    )
    parser.add_argument("--agent", default="SWE-agent", help="Agent name")
    parser.add_argument("--configs", nargs="+", default=["refiner"],
                       help="Configs to analyze (default: refiner)")
    parser.add_argument("--models", nargs="+",
                       default=["deepseek-chat-v3-0324", "gemini-2.5-flash", "minimax-m2.5"],
                       help="Models to analyze")
    parser.add_argument("--datasets", nargs="+",
                       default=["swebench-pro", "swebench"],
                       help="Datasets to analyze")
    parser.add_argument("--version", type=int, default=5,
                       help="Refiner version (default: 5)")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    parser.add_argument("--analysis-dir", type=Path,
                       default=Path("analysis/analysis-results"),
                       help="Analysis results directory")
    parser.add_argument("--output", type=Path,
                       default=Path("analysis/figures/divergence_boxplot.pdf"),
                       help="Output figure path")
    parser.add_argument("--skip-analysis", action="store_true",
                       help="Skip analysis and only use cached results")
    parser.add_argument("--num-workers", type=int, default=8,
                       help="Number of parallel workers for analysis")

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print("Divergence Boxplot Visualization")
    print(f"{'='*70}")
    print(f"Agent:        {args.agent}")
    print(f"Configs:      {args.configs}")
    print(f"Models:       {args.models}")
    print(f"Datasets:     {args.datasets}")
    print(f"Version:      {args.version}")
    print(f"Skip analysis: {args.skip_analysis}")
    print(f"Workers:      {args.num_workers}")
    print(f"Output:       {args.output}")
    print(f"{'='*70}\n")

    # Load or compute divergence results
    results = load_or_compute_divergence(
        agent=args.agent,
        configs=args.configs,
        models=args.models,
        datasets=args.datasets,
        version=args.version,
        run_id=args.run_id,
        analysis_dir=args.analysis_dir,
        skip_analysis=args.skip_analysis,
        num_workers=args.num_workers
    )

    if not results:
        print("No results available. Exiting.")
        return

    print(f"\nLoaded {len(results)} configurations")

    # Extract similarity data for plotting
    similarity_data = extract_similarity_data(
        results,
        args.configs,
        args.models,
        args.datasets
    )

    if not similarity_data:
        print("No similarity data to plot. Exiting.")
        return

    # Create boxplot
    create_divergence_boxplot(
        similarity_data,
        args.configs,
        args.models,
        args.datasets,
        args.output
    )

    print(f"\n{'='*70}")
    print("Divergence boxplot generation complete!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
