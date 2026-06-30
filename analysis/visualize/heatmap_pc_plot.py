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
    """Generate heatmap visualization with redesigned layout: configs as rows, model(R/U) as columns, datasets stacked vertically."""
    # Define order: swebench-pro first, then swebench
    dataset_order = ['swebench-pro', 'swebench']

    # Dataset abbreviations
    DATASET_ABBR = {
        'swebench-pro': 'Pro',
        'swebench': 'Verified'
    }

    # Get models (assume same models for all datasets)
    models = sorted(set([m for d, m in data.keys()]))

    # Build columns: model (R/U) pairs (no dataset dimension in columns)
    cols = []
    col_labels = []

    for model in models:
        cols.append((model, 'resolved'))
        col_labels.append('R')
        cols.append((model, 'unresolved'))
        col_labels.append('U')

    # Build rows: dataset-config pairs (datasets stacked vertically)
    rows = []
    row_labels = []

    for dataset in dataset_order:
        for config in configs:
            rows.append((dataset, config))
            row_labels.append(CONFIG_NAME_MAP.get(config, config))

    # Build data matrix: rows = dataset-config, cols = model-status
    matrix = np.full((len(rows), len(cols)), np.nan)

    for i, (dataset, config) in enumerate(rows):
        for j, (model, status) in enumerate(cols):
            key = (dataset, model)
            if key in data and config in data[key]:
                score = data[key][config].get(status)
                if score is not None:
                    matrix[i, j] = score

    # Create figure: wider cells and taller for readability
    fig, ax = plt.subplots(figsize=(len(cols) * 2.2 + 5, len(rows) * 1.1 + 3))

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
        cbar_kws={'shrink': 0.7, 'pad': 0.02, 'label': 'Compliance Score'},
        xticklabels=False,
        yticklabels=False,
        linewidths=2,
        linecolor='white',
        ax=ax,
        mask=np.isnan(matrix),
        square=False,
        annot_kws={'size': 32, 'weight': 'bold'}
    )

    # Configure colorbar
    cbar = ax.collections[0].colorbar
    cbar.ax.tick_params(labelsize=28)
    cbar.set_label('Compliance Score', fontsize=30, fontweight='bold')

    # Handle missing data
    for i in range(len(rows)):
        for j in range(len(cols)):
            if np.isnan(matrix[i, j]):
                ax.text(j + 0.5, i + 0.5, '-',
                       ha='center', va='center',
                       color='gray', fontsize=30, fontweight='bold')

    # Remove axis labels and ticks
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.set_xticks([])
    ax.set_yticks([])

    # Add R/U labels at the top (closer to heatmap)
    for j, label in enumerate(col_labels):
        ax.text(j + 0.5, -0.25, label,
               ha='center', va='bottom',
               fontsize=30, fontweight='bold',
               transform=ax.transData)

    # Add model names at top (centered between R and U, with better spacing)
    for model_idx, model in enumerate(models):
        model_name = MODEL_NAME_MAP.get(model, model)
        col_idx = model_idx * 2  # Each model has 2 columns (R, U)
        # Center of R-U pair: column indices are col_idx and col_idx+1
        # So center is at col_idx + 0.5 (middle of R) + 0.5 = col_idx + 1.0? No wait...
        # R is at column col_idx (center at col_idx+0.5)
        # U is at column col_idx+1 (center at col_idx+1.5)
        # Middle of R and U centers: (col_idx+0.5 + col_idx+1.5)/2 = col_idx + 1.0
        model_x = col_idx + 1.0
        ax.text(model_x, -0.85, model_name,
               ha='center', va='center',
               fontsize=30, fontweight='bold',
               transform=ax.transData)

    # Add config names on the left
    for i, (dataset, config) in enumerate(rows):
        config_name = CONFIG_NAME_MAP.get(config, config)
        ax.text(-0.4, i + 0.5, config_name,
               ha='right', va='center',
               fontsize=30, fontweight='bold',
               transform=ax.transData)

    # Add dataset labels on the far left (vertically centered for each dataset section)
    prev_dataset = None
    for i, (dataset, config) in enumerate(rows):
        if dataset != prev_dataset:
            # Count rows for this dataset
            dataset_rows = sum(1 for d, _ in rows if d == dataset)
            dataset_y = i + dataset_rows / 2 - 0.5
            dataset_abbr = DATASET_ABBR.get(dataset, dataset)
            ax.text(-1.5, dataset_y, dataset_abbr,
                   ha='center', va='center',
                   fontsize=36, fontweight='bold',
                   rotation=90,
                   transform=ax.transData)
            prev_dataset = dataset

    # Draw horizontal separator between datasets
    # Debug: print row structure
    # Rows structure: [(dataset, config), ...]
    # With 2 configs: row 0=(Pro, config1), row 1=(Pro, config2), row 2=(Verified, config1), row 3=(Verified, config2)
    # Separator should be between row 1 and row 2, which is at y = 1.5
    # But heatmap cells: row 0 is at y=0 to y=1, row 1 is at y=1 to y=2, etc.
    # So separator between row 1 and row 2 should be at y = 2.0, not y = 1.5
    for i in range(1, len(rows)):
        dataset_curr = rows[i][0]
        dataset_prev = rows[i-1][0]
        if dataset_curr != dataset_prev:
            # In heatmap coordinates, row i starts at y=i, so separator should be at y=i
            ax.axhline(y=i, color='black', linewidth=3.5, linestyle='-')

    # Adjust limits to accommodate labels with proper margins - add extra space on right and bottom
    ax.set_xlim(-0.5, len(cols) + 0.3)  # Extra space on right
    ax.set_ylim(len(rows) + 0.3, -1.4)  # Extra space at top and bottom

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.6)
    print(f"Heatmap saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate plan compliance heatmap"
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