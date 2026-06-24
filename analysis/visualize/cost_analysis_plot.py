"""
Compare the 1. avg. number of trajectory steps 2. cost (if configs in ['refiner-only', 'refiner'], break down into the executor's cost (from .traj) and advisor's cost (from .planner.json)) 3. latency (applicable for the configs other than 'default' and 'sage') between the configs (default to ['default', 'refiner'])
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']

Use 2 (dataset) * 3 (models) bar chart (use a horizontal separator in the bar if we have break-down data) to present the results. For each type of data, put the config data side by side for comparison. Use shared row (dataset) title, column (model) title. Legend should be the color of the config.
"""
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from multiprocessing import Pool
from functools import partial
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

# Config color mapping
CONFIG_COLORS = {
    "default": "#FFD3B6",      # peach
    "sage": "#a0c4ff",         # blue
    "monitor": "#E6A8C2",      # pink
    "refiner-only": "#bc5090", # purple
    "refiner": "#A8E6CF",      # green
}


def load_traj_stats(traj_file: Path) -> Optional[Dict]:
    """Load cost and API call stats from .traj file."""
    try:
        with open(traj_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        model_stats = data.get("info", {}).get("model_stats", {})
        return {
            'instance_cost': model_stats.get("instance_cost", 0),
            'api_calls': model_stats.get("api_calls", 0)
        }
    except Exception:
        return None


def load_planner_stats(planner_file: Path) -> Optional[Dict]:
    """Load refiner cost and latency from .planner.json file."""
    try:
        with open(planner_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        summary = data.get("summary", {})
        return {
            'refiner_cost': summary.get("refiner_total_cost", 0),
            'monitor_latency_ms': summary.get("monitor_total_latency_ms", 0),
            'refiner_latency_ms': summary.get("refiner_total_latency_ms", 0),
            'total_latency_ms': summary.get("monitor_total_latency_ms", 0) + summary.get("refiner_total_latency_ms", 0),
            'monitor_count': summary.get("monitor_count", 0),
            'refiner_count': summary.get("refiner_count", 0)
        }
    except Exception:
        return None


def process_instance(instance_dir: Path, config: str) -> Optional[Dict]:
    """Process a single instance directory."""
    if not instance_dir.is_dir():
        return None

    instance_id = instance_dir.name
    traj_file = instance_dir / f"{instance_id}.traj"
    planner_file = instance_dir / f"{instance_id}.planner.json"

    if not traj_file.exists():
        return None

    traj_stats = load_traj_stats(traj_file)
    if not traj_stats:
        return None

    refiner_cost = 0
    monitor_latency = 0
    refiner_latency = 0
    total_latency = 0

    # Load planner stats if available (for non-default/sage configs)
    if config not in ['default', 'sage'] and planner_file.exists():
        planner_stats = load_planner_stats(planner_file)
        if planner_stats:
            refiner_cost = planner_stats['refiner_cost']
            monitor_latency = planner_stats['monitor_latency_ms']
            refiner_latency = planner_stats['refiner_latency_ms']
            total_latency = planner_stats['total_latency_ms']

    return {
        'steps': traj_stats['api_calls'],
        'executor_cost': traj_stats['instance_cost'],
        'refiner_cost': refiner_cost,
        'total_cost': traj_stats['instance_cost'] + refiner_cost,
        'monitor_latency': monitor_latency,
        'refiner_latency': refiner_latency,
        'total_latency': total_latency
    }


def compute_config_stats(agent_dir: Path, config: str, dataset: str, model: str,
                        run_id: int = 1, version: str = '5', num_workers: int = 8) -> Optional[Dict]:
    """
    Compute statistics for a given configuration using parallel processing.

    Returns:
        Dict with avg_steps, avg_executor_cost, avg_refiner_cost, avg_total_cost, avg_latency_ms
    """
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # Build trajectory base path
    if config in ['refiner', 'refiner-only'] and version:
        traj_base = agent_dir / "trajectories" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}"
    elif config == 'sage':
        traj_base = agent_dir / "trajectories" / "sage" / dataset_path / model / f"run-{run_id}"
    else:
        traj_base = agent_dir / "trajectories" / config / dataset_path / model / f"run-{run_id}"

    if not traj_base.exists():
        return None

    # Get all instance directories
    instance_dirs = [d for d in traj_base.iterdir() if d.is_dir()]
    if not instance_dirs:
        return None

    # Process instances in parallel
    process_fn = partial(process_instance, config=config)
    with Pool(processes=num_workers) as pool:
        results = pool.map(process_fn, instance_dirs)

    # Filter out None results
    results = [r for r in results if r is not None]

    if not results:
        return None

    return {
        'config': config,
        'avg_steps': np.mean([r['steps'] for r in results]),
        'avg_executor_cost': np.mean([r['executor_cost'] for r in results]),
        'avg_refiner_cost': np.mean([r['refiner_cost'] for r in results]),
        'avg_total_cost': np.mean([r['total_cost'] for r in results]),
        'avg_monitor_latency_ms': np.mean([r['monitor_latency'] for r in results]),
        'avg_refiner_latency_ms': np.mean([r['refiner_latency'] for r in results]),
        'avg_total_latency_ms': np.mean([r['total_latency'] for r in results]),
        'n_instances': len(results)
    }


def create_visualization(data: Dict[Tuple[str, str], Dict[str, Dict]],
                        datasets: List[str],
                        models: List[str],
                        configs: List[str],
                        output_path: Path):
    """
    Create a 2x3 grid visualization (2 datasets x 3 models) with three metrics: steps, cost, latency.
    Each metric uses its own y-axis scale.

    Args:
        data: Nested dict {(dataset, model): {config: stats}}
        datasets: List of datasets
        models: List of models
        configs: List of configs
        output_path: Path to save the figure
    """
    from matplotlib.gridspec import GridSpec

    # Create 2x3 grid for datasets x models, each cell has 3 subplots (one per metric)
    fig = plt.figure(figsize=(21, 10))
    gs = GridSpec(2, 9, figure=fig, hspace=0.35, wspace=0.15, left=0.04, right=0.97, top=0.92, bottom=0.08)

    for row_idx, dataset in enumerate(datasets):
        for col_idx, model in enumerate(models):
            key = (dataset, model)
            if key not in data or not data[key]:
                continue

            # Get available configs for this dataset-model pair
            available_configs = [c for c in configs if c in data[key]]
            if not available_configs:
                continue

            n_configs = len(available_configs)
            bar_width = 0.6

            # Create 3 subplots for this dataset-model pair (steps, cost, latency)
            for metric_idx, (metric_name, metric_key, ylabel) in enumerate([
                ('Steps', 'avg_steps', 'Steps'),
                ('Cost', 'avg_total_cost', 'Cost ($)'),
                ('Latency', 'avg_total_latency_ms', 'Latency (s)')
            ]):
                ax = fig.add_subplot(gs[row_idx, col_idx * 3 + metric_idx])

                x_positions = np.arange(n_configs)

                for i, config in enumerate(available_configs):
                    stats = data[key][config]
                    color = CONFIG_COLORS.get(config, '#888888')

                    if metric_name == 'Cost' and config in ['refiner', 'refiner-only'] and stats['avg_refiner_cost'] > 0:
                        # Stacked bar for cost breakdown
                        executor_cost = stats['avg_executor_cost']
                        refiner_cost = stats['avg_refiner_cost']
                        total_cost = stats['avg_total_cost']

                        b1 = ax.bar(x_positions[i], executor_cost, bar_width, color=color, alpha=0.85,
                                   edgecolor='black', linewidth=0.8)
                        b2 = ax.bar(x_positions[i], refiner_cost, bar_width, bottom=executor_cost,
                                   color=color, alpha=0.5, edgecolor='black', linewidth=0.8, hatch='//')

                        # Add total value on top
                        ax.text(x_positions[i], total_cost, f'{total_cost:.2f}',
                               ha='center', va='bottom', fontsize=11, fontweight='bold')
                    else:
                        # Regular bar
                        value = stats[metric_key]
                        if metric_name == 'Latency':
                            value = value / 1000  # Convert ms to seconds

                        bars = ax.bar(x_positions[i], value, bar_width, color=color, alpha=0.85,
                                     edgecolor='black', linewidth=0.8)

                        # Add value on top
                        if metric_name == 'Steps':
                            label_text = f'{value:.0f}'
                        elif metric_name == 'Cost':
                            label_text = f'{value:.2f}'
                        else:  # Latency
                            label_text = f'{value:.1f}'

                        ax.text(x_positions[i], value, label_text,
                               ha='center', va='bottom', fontsize=11, fontweight='bold')

                # Styling
                ax.set_xticks(x_positions)
                ax.set_xticklabels([CONFIG_NAME_MAP.get(c, c) for c in available_configs],
                                  fontsize=11, rotation=15, ha='right')
                ax.tick_params(axis='y', labelsize=11)
                ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.8)
                ax.set_axisbelow(True)
                ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')

                # Title: metric name for first row
                if row_idx == 0 and col_idx == 0:
                    ax.text(0.5, 1.15, metric_name, transform=ax.transAxes,
                           ha='center', fontsize=14, fontweight='bold')

                # Super title: model name (column title) for first row
                if row_idx == 0 and metric_idx == 1:
                    ax.set_title(MODEL_NAME_MAP.get(model, model), fontsize=16, fontweight='bold', pad=35)

                # Super Y-axis label: dataset name (row title) for first column
                if col_idx == 0 and metric_idx == 0:
                    ax.text(-0.45, 0.5, DATASET_NAME_MAP.get(dataset, dataset),
                           transform=ax.transAxes, rotation=90, va='center',
                           fontsize=15, fontweight='bold')

    # Create legend
    legend_elements = [
        mpatches.Patch(facecolor=CONFIG_COLORS[c], edgecolor='black', linewidth=0.8, alpha=0.85,
                      label=CONFIG_NAME_MAP.get(c, c))
        for c in configs if any(c in data.get((d, m), {}) for d in datasets for m in models)
    ]

    # Add breakdown pattern to legend if applicable
    if any(c in ['refiner', 'refiner-only'] for c in configs):
        legend_elements.append(
            mpatches.Patch(facecolor='grey', edgecolor='black', linewidth=0.8, hatch='//', alpha=0.5,
                          label='Advisor Cost')
        )

    fig.legend(handles=legend_elements, loc='upper center', ncol=len(legend_elements),
              fontsize=13, frameon=True, edgecolor='black', fancybox=False,
              bbox_to_anchor=(0.5, 0.98))

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Figure saved to: {output_path}")


def load_cache(cache_path: Path) -> Optional[Dict]:
    """Load cached data."""
    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load cache: {e}")
    return None


def save_cache(data: Dict, cache_path: Path):
    """Save data to cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Data cached to: {cache_path}")


def generate_latex_table(data: Dict[Tuple[str, str], Dict[str, Dict]],
                         datasets: List[str],
                         models: List[str],
                         configs: List[str],
                         output_path: Path):
    """
    Generate a LaTeX table with metrics as rows and datasets-models-configs as columns.
    Layout matches inefficiency patterns table.
    """
    lines = []
    lines.append(r"\begin{table*}[h!]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\setlength{\tabcolsep}{2.5pt}")
    lines.append(r"\caption{Cost and latency comparison across datasets, models, and methods. "
                r"Exec.: executor cost, Adv.: advisor cost, Mon.: monitor latency, Adv.: advisor latency. "
                r"--- indicates not applicable.}")

    # Build dataset-model-config tuples
    dataset_model_config_tuples = []
    for dataset in datasets:
        for model in models:
            for config in configs:
                if (dataset, model) in data and config in data[(dataset, model)]:
                    dataset_model_config_tuples.append((dataset, model, config))

    if not dataset_model_config_tuples:
        return

    n_cols = len(dataset_model_config_tuples)
    col_spec = "l|" + "r" * n_cols
    lines.append(f"\\begin{{tabular}}{{{col_spec}}}")
    lines.append(r"\toprule")

    # Header row 1: Dataset names with multicolumn
    header1 = r"\textbf{Metric}"
    dataset_groups = []
    current_dataset = None
    start_idx = 0

    for idx, (dataset, _, _) in enumerate(dataset_model_config_tuples):
        if dataset != current_dataset:
            if current_dataset is not None:
                dataset_groups.append((current_dataset, start_idx, idx))
            current_dataset = dataset
            start_idx = idx

    if current_dataset is not None:
        dataset_groups.append((current_dataset, start_idx, len(dataset_model_config_tuples)))

    for dataset, start, end in dataset_groups:
        dataset_name = DATASET_NAME_MAP.get(dataset, dataset)
        span = end - start
        header1 += f" & \\multicolumn{{{span}}}{{c}}{{\\textbf{{{dataset_name}}}}}"

    lines.append(header1 + r" \\")

    # Header row 2: Model names with multicolumn (each model spans len(configs))
    header2 = ""
    current_dataset = None
    current_model = None
    start_idx = 0

    model_groups = []
    for idx, (dataset, model, _) in enumerate(dataset_model_config_tuples):
        if dataset != current_dataset or model != current_model:
            if current_model is not None:
                model_groups.append((current_dataset, current_model, start_idx, idx))
            current_dataset = dataset
            current_model = model
            start_idx = idx

    if current_model is not None:
        model_groups.append((current_dataset, current_model, start_idx, len(dataset_model_config_tuples)))

    for dataset, model, start, end in model_groups:
        model_name = MODEL_NAME_MAP.get(model, model)
        span = end - start
        if span > 1:
            header2 += f" & \\multicolumn{{{span}}}{{c}}{{\\textit{{{model_name}}}}}"
        else:
            header2 += f" & \\textit{{{model_name}}}"

    lines.append(header2 + r" \\")

    # Header row 3: Config names
    subheader_parts = [""]
    for _, _, config in dataset_model_config_tuples:
        config_name = CONFIG_NAME_MAP.get(config, config)
        subheader_parts.append(f"\\scriptsize {config_name}")
    lines.append(" & ".join(subheader_parts) + r" \\")
    lines.append(r"\midrule")

    # Metric rows
    metrics = [
        (r"\textbf{Steps}", "avg_steps", "{:.0f}", False),
        (r"\textbf{Cost (\$)}", None, None, False),
        (r"$\quad$ Exec.", "avg_executor_cost", "{:.2f}", False),
        (r"$\quad$ Adv.", "avg_refiner_cost", "{:.2f}", False),
        (r"$\quad$ Total", "avg_total_cost", "{:.2f}", True),
        (r"\textbf{Latency (s)}", None, None, False),
        (r"$\quad$ Mon.", "avg_monitor_latency_ms", "{:.1f}", False),
        (r"$\quad$ Adv.", "avg_refiner_latency_ms", "{:.1f}", False),
    ]

    for metric_label, metric_key, format_str, add_line in metrics:
        row_parts = [metric_label]

        # Add values for each dataset-model-config tuple
        for dataset, model, config in dataset_model_config_tuples:
            key = (dataset, model)
            if metric_key is None:
                # Category header row, no data
                row_parts.append("")
            elif key in data and config in data[key]:
                stats = data[key][config]
                value = stats.get(metric_key, 0)

                # Convert latency from ms to s
                if "latency_ms" in metric_key:
                    value = value / 1000

                # Check if value should be shown
                if value > 0.0001:
                    formatted_value = format_str.format(value)
                    row_parts.append(formatted_value)
                else:
                    row_parts.append(r"---")
            else:
                row_parts.append(r"---")

        lines.append(" & ".join(row_parts) + r" \\")

        # Add line after cost total
        if add_line:
            lines.append(r"\cmidrule{1-" + str(n_cols + 1) + "}")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\label{tab:cost_analysis}")
    lines.append(r"\end{table*}")

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"LaTeX table saved to: {output_path}")


def generate_markdown_table(data: Dict[Tuple[str, str], Dict[str, Dict]],
                            datasets: List[str],
                            models: List[str],
                            configs: List[str],
                            output_path: Path):
    """
    Generate a Markdown table comparing configs across datasets and models.
    """
    lines = []
    lines.append("# Cost Analysis Comparison\n")

    # Header
    header = "| Dataset | Model | Method | Steps | Executor Cost ($) | Advisor Cost ($) | Total Cost ($) | Monitor Latency (s) | Refiner Latency (s) |"
    separator = "|---------|-------|--------|------:|------------------:|-----------------:|---------------:|--------------------:|--------------------:|"
    lines.append(header)
    lines.append(separator)

    # Data rows
    for dataset in datasets:
        dataset_name = DATASET_NAME_MAP.get(dataset, dataset)

        for model in models:
            key = (dataset, model)
            if key not in data or not data[key]:
                continue

            model_name = MODEL_NAME_MAP.get(model, model)
            available_configs = [c for c in configs if c in data[key]]

            for config_idx, config in enumerate(available_configs):
                stats = data[key][config]
                config_name = CONFIG_NAME_MAP.get(config, config)

                # Format values
                steps = f"{stats['avg_steps']:.0f}"
                executor_cost = f"{stats['avg_executor_cost']:.2f}"
                advisor_cost = f"{stats['avg_refiner_cost']:.2f}" if stats['avg_refiner_cost'] > 0 else "--"
                total_cost = f"{stats['avg_total_cost']:.2f}"
                monitor_latency = f"{stats['avg_monitor_latency_ms'] / 1000:.1f}" if stats['avg_monitor_latency_ms'] > 0 else "--"
                refiner_latency = f"{stats['avg_refiner_latency_ms'] / 1000:.1f}" if stats['avg_refiner_latency_ms'] > 0 else "--"

                # Row with dataset and model names only on first config
                if config_idx == 0:
                    row = f"| {dataset_name} | {model_name} | {config_name} | {steps} | "
                else:
                    row = f"| | | {config_name} | {steps} | "

                row += f"{executor_cost} | {advisor_cost} | {total_cost} | {monitor_latency} | {refiner_latency} |"
                lines.append(row)

    # Add summary statistics
    lines.append("\n## Summary Statistics\n")
    for dataset in datasets:
        dataset_name = DATASET_NAME_MAP.get(dataset, dataset)
        lines.append(f"\n### {dataset_name}\n")

        for config in configs:
            config_name = CONFIG_NAME_MAP.get(config, config)

            # Collect stats for this config across all models in this dataset
            config_stats = []
            for model in models:
                key = (dataset, model)
                if key in data and config in data[key]:
                    config_stats.append(data[key][config])

            if not config_stats:
                continue

            # Compute averages
            avg_steps = np.mean([s['avg_steps'] for s in config_stats])
            avg_total_cost = np.mean([s['avg_total_cost'] for s in config_stats])
            avg_executor_cost = np.mean([s['avg_executor_cost'] for s in config_stats])
            avg_advisor_cost = np.mean([s['avg_refiner_cost'] for s in config_stats])

            lines.append(f"**{config_name}**: Avg Steps: {avg_steps:.1f}, "
                        f"Avg Total Cost: ${avg_total_cost:.2f}, "
                        f"Avg Executor Cost: ${avg_executor_cost:.2f}, "
                        f"Avg Advisor Cost: ${avg_advisor_cost:.2f}")

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Markdown table saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate cost analysis visualization')
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent directory name')
    parser.add_argument('--datasets', nargs='+', default=['swebench', 'swebench-pro'],
                       help='List of datasets')
    parser.add_argument('--models', nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='List of models')
    parser.add_argument('--configs', nargs='+', default=['default', 'refiner'],
                       help='List of configs to compare')
    parser.add_argument('--version', type=str, default='5',
                       help='Version for refiner config')
    parser.add_argument('--run_id', type=int, default=1,
                       help='Run ID')
    parser.add_argument('--num_workers', type=int, default=8,
                       help='Number of parallel workers')
    parser.add_argument('--output', type=str, default=None,
                       help='Output path (default: figures/cost_analysis.pdf)')
    parser.add_argument('--no_cache', action='store_true',
                       help='Disable cache loading/saving')
    parser.add_argument('--cache_path', type=str, default=None,
                       help='Cache file path (default: analysis/cache/cost_analysis_data.json)')

    args = parser.parse_args()

    # Determine project root
    script_dir = Path(__file__).parent.parent.parent

    # Setup cache
    cache_path = Path(args.cache_path) if args.cache_path else script_dir / "analysis" / "cache" / "cost_analysis_data.json"

    # Try to load from cache
    data = None
    if not args.no_cache:
        data = load_cache(cache_path)
        if data:
            print(f"Loaded data from cache: {cache_path}")
            # Convert string keys back to tuples
            data = {eval(k) if isinstance(k, str) and k.startswith('(') else k: v
                   for k, v in data.items()}

    # Compute data if not loaded from cache
    if data is None:
        print("Computing data from trajectories...")
        data = {}

        for dataset in args.datasets:
            # Determine agent directory based on dataset
            if dataset == 'swebench':
                agent_dir = script_dir / args.agent
            elif dataset == 'swebench-pro':
                agent_dir = script_dir / "SWE-bench_Pro-os" / args.agent
            else:
                print(f"Unknown dataset: {dataset}")
                continue

            if not agent_dir.exists():
                print(f"Agent directory not found: {agent_dir}")
                continue

            for model in args.models:
                print(f"Processing {dataset} - {model}")

                config_data = {}
                for config in args.configs:
                    stats = compute_config_stats(
                        agent_dir, config, dataset, model,
                        run_id=args.run_id, version=args.version,
                        num_workers=args.num_workers
                    )

                    if stats:
                        config_data[config] = stats
                        print(f"  {config}: {stats['n_instances']} instances, "
                              f"avg_cost=${stats['avg_total_cost']:.6f}, "
                              f"avg_steps={stats['avg_steps']:.1f}")
                    else:
                        print(f"  {config}: No data found")

                if config_data:
                    data[(dataset, model)] = config_data

        if not data:
            print("No data found. Check paths and configurations.")
            return

        # Save to cache
        if not args.no_cache:
            # Convert tuple keys to strings for JSON serialization
            cache_data = {str(k): v for k, v in data.items()}
            save_cache(cache_data, cache_path)

    # Generate visualization
    output_path = Path(args.output) if args.output else script_dir / "analysis" / "figures" / "cost_analysis.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    create_visualization(data, args.datasets, args.models, args.configs, output_path)

    # Generate LaTeX table
    table_path = Path(args.output) if args.output else script_dir / "analysis" / "tables" / "cost_analysis.tex"
    generate_latex_table(data, args.datasets, args.models, args.configs, table_path)

    # Generate Markdown table
    md_path = table_path.with_suffix('.md')
    generate_markdown_table(data, args.datasets, args.models, args.configs, md_path)


if __name__ == "__main__":
    main()
