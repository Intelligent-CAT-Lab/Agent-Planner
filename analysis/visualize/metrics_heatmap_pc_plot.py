"""
Parse the langutory.json to get metrics breakdown (s2_coverage, s3_order, s1_vocabulary, final_score) for each config on (model, dataset).
Generate the heatmap with metrics as rows within each config, model(R/U) as columns, datasets stacked vertically.
For each {model, dataset, config} setting, split into 4 metric rows: PPC, POC, PPF, PC (from high to low priority).
default config list: ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench-pro', 'swebench']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
"""

import argparse
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return (maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'],
            maps['CONFIG_NAME_MAP'], maps['PC_METRICS_MAP'])


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP, PC_METRICS_MAP = load_name_maps()

# Metrics order (from high to low priority as specified)
METRICS_ORDER = ['s2_coverage', 's3_order', 's1_vocabulary', 'final_score']


def load_langutory_data(agent_dir: Path, config: str, version: int, dataset: str,
                        model: str, run_id: int) -> Optional[List[Dict]]:
    """Load langutory data for a specific configuration."""
    if config in ["refiner", "refiner-only"]:
        base = agent_dir / "langutory" / config / f"version-{version}" / dataset
    else:
        base = agent_dir / "langutory" / config / dataset

    if dataset == "swebench-pro":
        base = base / "python"

    langutory_file = base / model / f"run-{run_id}" / "langutory.json"

    if not langutory_file.exists():
        return None

    try:
        with open(langutory_file) as f:
            return json.load(f)
    except Exception:
        return None


def compute_average_metrics(data: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Compute average metrics for resolved and unresolved instances."""
    resolved_metrics = defaultdict(list)
    unresolved_metrics = defaultdict(list)

    for entry in data:
        compliance_score = entry.get('compliance_score', {})
        resolution_status = entry.get('resolution_status')

        # Collect metrics for each status
        metrics_dict = resolved_metrics if resolution_status == 'resolved' else unresolved_metrics

        for metric in METRICS_ORDER:
            score = compliance_score.get(metric)
            if score is not None:
                metrics_dict[metric].append(score)

    # Compute averages
    result = {'resolved': {}, 'unresolved': {}}

    for metric in METRICS_ORDER:
        result['resolved'][metric] = (np.mean(resolved_metrics[metric])
                                      if resolved_metrics[metric] else None)
        result['unresolved'][metric] = (np.mean(unresolved_metrics[metric])
                                        if unresolved_metrics[metric] else None)

    return result


def collect_data(base_dir: Path, datasets: List[str], models: List[str],
                 configs: List[str], run_id: int, version: int) -> Dict:
    """Collect all metrics data."""
    data = {}

    for dataset in datasets:
        if dataset == "swebench":
            agent_dir = base_dir / "SWE-agent"
        elif dataset == "swebench-pro":
            agent_dir = base_dir / "SWE-bench_Pro-os" / "SWE-agent"
        else:
            continue

        for model in models:
            for config in configs:
                langutory_data = load_langutory_data(
                    agent_dir, config, version, dataset, model, run_id
                )

                key = (dataset, model, config)
                if langutory_data:
                    data[key] = compute_average_metrics(langutory_data)
                else:
                    data[key] = None

    return data


def generate_metrics_heatmap(data: Dict, configs: List[str], output_path: Path):
    """Generate metrics breakdown heatmap: configs/metrics as rows, model(R/U) as columns, datasets stacked vertically."""
    # Dataset order (use full names from DATASET_NAME_MAP)
    dataset_order = ['swebench-pro', 'swebench']

    # Get models (assume same models for all datasets)
    models = sorted(set([m for d, m, c in data.keys()]))

    # Build columns: model (R/U) pairs
    cols = []
    col_labels = []
    for model in models:
        cols.append((model, 'resolved'))
        col_labels.append('R')
        cols.append((model, 'unresolved'))
        col_labels.append('U')

    # Build rows: dataset-config-metric tuples (datasets stacked vertically)
    rows = []
    row_labels = []

    for dataset in dataset_order:
        for config in configs:
            for metric in METRICS_ORDER:
                rows.append((dataset, config, metric))
                # Use metric display name from PC_METRICS_MAP
                metric_display = PC_METRICS_MAP.get(metric, metric)
                row_labels.append(metric_display)

    # Build data matrix: rows = dataset-config-metric, cols = model-status
    matrix = np.full((len(rows), len(cols)), np.nan)

    for i, (dataset, config, metric) in enumerate(rows):
        for j, (model, status) in enumerate(cols):
            key = (dataset, model, config)
            if key in data and data[key] is not None:
                score = data[key].get(status, {}).get(metric)
                if score is not None:
                    matrix[i, j] = score

    # Create figure: wider cells and taller for readability
    fig, ax = plt.subplots(figsize=(len(cols) * 2.2 + 5, len(rows) * 0.55 + 3))

    # Create colormap: green (high) -> yellow -> orange -> red (low)
    cmap = sns.diverging_palette(10, 130, s=80, l=55, as_cmap=True)

    # Draw heatmap without default labels
    sns.heatmap(
        matrix,
        annot=True,
        fmt='.2f',
        cmap=cmap,
        center=0.75,
        vmin=0.5,
        vmax=1.0,
        cbar=True,
        cbar_kws={'shrink': 0.7, 'pad': 0.02, 'label': 'Score'},
        xticklabels=False,
        yticklabels=False,
        linewidths=1.5,
        linecolor='white',
        ax=ax,
        mask=np.isnan(matrix),
        square=False,
        annot_kws={'size': 26, 'weight': 'bold'}
    )

    # Configure colorbar
    cbar = ax.collections[0].colorbar
    cbar.ax.tick_params(labelsize=28)
    cbar.set_label('Score', fontsize=30, fontweight='bold')

    # Handle missing data
    for i in range(len(rows)):
        for j in range(len(cols)):
            if np.isnan(matrix[i, j]):
                ax.text(j + 0.5, i + 0.5, '-',
                       ha='center', va='center',
                       color='gray', fontsize=20, fontweight='bold')

    # Remove axis labels and ticks
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.set_xticks([])
    ax.set_yticks([])

    # Add R/U labels at the top
    for j, label in enumerate(col_labels):
        ax.text(j + 0.5, -0.25, label,
               ha='center', va='bottom',
               fontsize=28, fontweight='bold',
               transform=ax.transData)

    # Add model names at top (centered between R and U, moved up to avoid overlap)
    for model_idx, model in enumerate(models):
        model_name = MODEL_NAME_MAP.get(model, model)
        col_idx = model_idx * 2
        model_x = col_idx + 1.0
        ax.text(model_x, -1.05, model_name,
               ha='center', va='center',
               fontsize=30, fontweight='bold',
               transform=ax.transData)

    # Add metric names on the left
    for i, (dataset, config, metric) in enumerate(rows):
        metric_display = PC_METRICS_MAP.get(metric, metric)
        ax.text(-0.2, i + 0.5, metric_display,
               ha='right', va='center',
               fontsize=26, fontweight='bold',
               transform=ax.transData)

    # Add config names on the far left (vertically centered for each config section)
    prev_dataset = None
    prev_config = None
    for i, (dataset, config, metric) in enumerate(rows):
        # Only draw config label at the center of the 4-metric block
        if dataset == prev_dataset and config == prev_config:
            continue

        # Count rows for this config (4 metrics)
        config_rows = len(METRICS_ORDER)
        config_y = i + config_rows / 2 - 0.5
        config_name = CONFIG_NAME_MAP.get(config, config)
        ax.text(-1.0, config_y, config_name,
               ha='center', va='center',
               fontsize=28, fontweight='bold',
               rotation=90,
               transform=ax.transData)
        prev_dataset = dataset
        prev_config = config

    # Add dataset labels on the far far left (vertically centered for each dataset section)
    prev_dataset = None
    for i, (dataset, config, metric) in enumerate(rows):
        if dataset != prev_dataset:
            # Count rows for this dataset
            dataset_rows = len(configs) * len(METRICS_ORDER)
            dataset_y = i + dataset_rows / 2 - 0.5
            dataset_name = DATASET_NAME_MAP.get(dataset, dataset)
            ax.text(-1.5, dataset_y, dataset_name,
                   ha='center', va='center',
                   fontsize=32, fontweight='bold',
                   rotation=90,
                   transform=ax.transData)
            prev_dataset = dataset

    # Draw horizontal separators
    # 1. Between datasets (thick black line)
    metrics_per_config = len(METRICS_ORDER)
    configs_per_dataset = len(configs)

    for i in range(1, len(rows)):
        dataset_curr = rows[i][0]
        dataset_prev = rows[i-1][0]
        if dataset_curr != dataset_prev:
            ax.axhline(y=i, color='black', linewidth=3.5, linestyle='-')

    # 2. Between configs within dataset (medium gray line)
    for i in range(1, len(rows)):
        if i % metrics_per_config == 0:
            dataset_curr = rows[i][0]
            dataset_prev = rows[i-1][0]
            if dataset_curr == dataset_prev:
                ax.axhline(y=i, color='gray', linewidth=2.0, linestyle='-', alpha=0.7)

    # 3. Between metrics within config (light dashed line for PC)
    for i in range(1, len(rows)):
        dataset, config, metric = rows[i]
        if metric == 'final_score' and i > 0:
            # Draw separator above PC row
            ax.axhline(y=i, color='gray', linewidth=1.0, linestyle='--', alpha=0.4)

    # Adjust limits to accommodate labels
    ax.set_xlim(-0.5, len(cols) + 0.3)
    ax.set_ylim(len(rows) + 0.3, -1.4)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.6)
    print(f"Metrics heatmap saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate plan compliance metrics breakdown heatmap"
    )
    parser.add_argument("--datasets", nargs="+",
                       default=['swebench-pro', 'swebench'],
                       help="Datasets to include")
    parser.add_argument("--models", nargs="+",
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help="Models to include")
    parser.add_argument("--configs", nargs="+",
                       default=['default', 'refiner'],
                       help="Configs to include")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    parser.add_argument("--version", type=int, default=5, help="Version for refiner configs")
    parser.add_argument("--output", type=str, default="analysis/figures/metrics_plan_compliance_heatmap.pdf",
                       help="Output file path")

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent.parent.resolve()
    output_path = base_dir / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Collecting metrics data...")
    data = collect_data(base_dir, args.datasets, args.models, args.configs,
                       args.run_id, args.version)

    print("Generating metrics heatmap...")
    generate_metrics_heatmap(data, args.configs, output_path)

    print("Done!")


if __name__ == "__main__":
    main()
