"""
Parse the langutory.json to get the resolution status and compliance_score (final score) for each config on (model, dataset).
Generate the heatmap. Row name (dataset (merge) - model), column name: config. Per setting: split to resolved (R) and unresolved (U), each cell is the average compliance_score for that setting.
default config list: ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench-pro', 'swebench']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
Get the available data. If some setting is missing, mark it in the heatmap (e.g., with a - in grey).
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
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()


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


def compute_average_scores(data: List[Dict]) -> Dict[str, float]:
    """Compute average compliance scores for resolved and unresolved instances."""
    resolved_scores = []
    unresolved_scores = []

    for entry in data:
        score = entry.get('compliance_score', {}).get('final_score')
        if score is None:
            continue

        if entry.get('resolution_status') == 'resolved':
            resolved_scores.append(score)
        else:
            unresolved_scores.append(score)

    return {
        'resolved': np.mean(resolved_scores) if resolved_scores else None,
        'unresolved': np.mean(unresolved_scores) if unresolved_scores else None
    }


def collect_data(base_dir: Path, datasets: List[str], models: List[str],
                 configs: List[str], run_id: int, version: int) -> Dict:
    """Collect all compliance score data."""
    data = {}

    for dataset in datasets:
        if dataset == "swebench":
            agent_dir = base_dir / "SWE-agent"
        elif dataset == "swebench-pro":
            agent_dir = base_dir / "SWE-bench_Pro-os" / "SWE-agent"
        else:
            continue

        for model in models:
            key = (dataset, model)
            data[key] = {}

            for config in configs:
                langutory_data = load_langutory_data(
                    agent_dir, config, version, dataset, model, run_id
                )

                if langutory_data:
                    data[key][config] = compute_average_scores(langutory_data)
                else:
                    data[key][config] = {'resolved': None, 'unresolved': None}

    return data


def generate_heatmap(data: Dict, configs: List[str], output_path: Path):
    """Generate heatmap visualization."""
    # Define order: swebench-pro first, then swebench
    dataset_order = ['swebench-pro', 'swebench']

    # Build rows in specific order
    rows = []
    row_labels = []

    for dataset in dataset_order:
        for model in sorted([m for d, m in data.keys() if d == dataset]):
            rows.append((dataset, model, 'resolved'))
            row_labels.append('R')
            rows.append((dataset, model, 'unresolved'))
            row_labels.append('U')

    col_labels = [CONFIG_NAME_MAP.get(c, c) for c in configs]

    # Build data matrix
    matrix = np.full((len(rows), len(configs)), np.nan)

    for i, (dataset, model, status) in enumerate(rows):
        key = (dataset, model)
        if key in data:
            for j, config in enumerate(configs):
                if config in data[key]:
                    score = data[key][config].get(status)
                    if score is not None:
                        matrix[i, j] = score

    # Create figure with compact layout
    fig, ax = plt.subplots(figsize=(len(configs) * 2.0 + 2.5, len(rows) * 0.5 + 0.8))

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
        cbar_kws={'shrink': 0.7, 'pad': 0.02},
        xticklabels=False,
        yticklabels=False,
        linewidths=1.5,
        linecolor='white',
        ax=ax,
        mask=np.isnan(matrix),
        square=False,
        annot_kws={'size': 18, 'weight': 'bold'}
    )

    # Handle missing data
    for i in range(len(rows)):
        for j in range(len(configs)):
            if np.isnan(matrix[i, j]):
                ax.text(j + 0.5, i + 0.5, '-',
                       ha='center', va='center',
                       color='gray', fontsize=16, fontweight='bold')

    # Add config names at the top (horizontal, bold, larger)
    for j, config_name in enumerate(col_labels):
        ax.text(j + 0.5, -0.25, config_name,
               ha='center', va='bottom',
               fontsize=13, fontweight='bold',
               transform=ax.transData)

    # Remove axis labels and ticks
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.set_xticks([])
    ax.set_yticks([])

    # Add hierarchical row labels on the left
    prev_dataset = None

    for i, (dataset, model, status) in enumerate(rows):
        dataset_name = DATASET_NAME_MAP.get(dataset, dataset)
        model_name = MODEL_NAME_MAP.get(model, model)

        # Add dataset label vertically on far left (spans multiple models)
        if dataset != prev_dataset:
            # Count rows for this dataset
            dataset_rows = sum(1 for d, _, _ in rows if d == dataset)
            dataset_y = i + dataset_rows / 2 - 0.5
            ax.text(-0.3, dataset_y, dataset_name,
                   ha='center', va='center',
                   fontsize=18, fontweight='bold',
                   rotation=90,
                   transform=ax.transData)
            prev_dataset = dataset

        # Add model label exactly centered between R (row i) and U (row i+1)
        if status == 'resolved':
            # Position at i+1.0 to be exactly between row i and row i+1
            model_y = i + 1.0
            ax.text(-0.45, model_y, model_name,
                   ha='right', va='center',
                   fontsize=18, fontweight='bold',
                   transform=ax.transData)

        # Add status label (R/U)
        status_label = 'R' if status == 'resolved' else 'U'
        ax.text(-0.1, i + 0.5, status_label,
               ha='right', va='center',
               fontsize=18,
               transform=ax.transData)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.5)
    print(f"Heatmap saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate plan compliance heatmap"
    )
    parser.add_argument("--datasets", nargs="+",
                       default=['swebench', 'swebench-pro'],
                       help="Datasets to include")
    parser.add_argument("--models", nargs="+",
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help="Models to include")
    parser.add_argument("--configs", nargs="+",
                       default=['default', 'sage', 'monitor', 'refiner-only', 'refiner'],
                       help="Configs to include")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    parser.add_argument("--version", type=int, default=5, help="Version for refiner configs")
    parser.add_argument("--output", type=str, default="analysis/figures/plan_compliance_heatmap.pdf",
                       help="Output file path")

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent.parent.resolve()
    output_path = base_dir / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Collecting data...")
    data = collect_data(base_dir, args.datasets, args.models, args.configs,
                       args.run_id, args.version)

    print("Generating heatmap...")
    generate_heatmap(data, args.configs, output_path)

    print("Done!")


if __name__ == "__main__":
    main()