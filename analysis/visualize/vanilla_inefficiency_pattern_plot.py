"""
Analyze inefficiency patterns for Vanilla (default config) only.
Generate heatmap showing pattern prevalence across datasets and models.
Layout: datasets (stacked vertically) × models (columns), with patterns as rows within each dataset.
"""
import csv
import argparse
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt
import json


# Load name mappings
def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()


class CSVParser:
    """Smart CSV parser for vanilla config."""

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.header_rows = []
        self.data_rows = []
        self.vanilla_start = None
        self._load_csv()
        self._detect_structure()

    def _load_csv(self):
        """Load CSV and separate headers from data."""
        with open(self.csv_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # First 3 rows are headers
        self.header_rows = rows[:3]
        self.data_rows = rows[3:]

    def _detect_structure(self):
        """Detect vanilla config column start."""
        header1 = self.header_rows[0]

        for col_idx, section_name in enumerate(header1):
            if 'Vanilla Run' in section_name:
                self.vanilla_start = col_idx
                break

    def has_vanilla(self) -> bool:
        """Check if vanilla section exists."""
        return self.vanilla_start is not None

    def parse_vanilla_patterns(self, row: List[str]) -> Dict:
        """Parse pattern data from a row for vanilla config."""
        if self.vanilla_start is None:
            return None

        start = self.vanilla_start

        # Vanilla: patterns at columns 2-8, resolved at column 0
        if len(row) <= start + 8:
            return None

        patterns = {
            'resolved': row[start] == '1' if len(row) > start else False,
            'plan_violation': row[start + 2] == '1' if len(row) > start + 2 else False,
            'oscillation': row[start + 3] == '1' if len(row) > start + 3 else False,
            'dwell_L_navigate': row[start + 4] == '1' if len(row) > start + 4 else False,
            'dwell_L_reproduce': row[start + 5] == '1' if len(row) > start + 5 else False,
            'dwell_P': row[start + 6] == '1' if len(row) > start + 6 else False,
            'dwell_V': row[start + 7] == '1' if len(row) > start + 7 else False,
            'repeated_view': row[start + 8] == '1' if len(row) > start + 8 else False
        }

        return patterns


def count_vanilla_patterns(csv_path: Path) -> Dict:
    """Count pattern instances for vanilla config."""
    if not csv_path.exists():
        return None

    parser = CSVParser(csv_path)

    if not parser.has_vanilla():
        return None

    pattern_instances = defaultdict(set)
    all_with_pattern = set()
    total_instances = 0

    for row in parser.data_rows:
        if not row or not row[0]:
            continue

        instance_id = row[0]
        total_instances += 1

        patterns = parser.parse_vanilla_patterns(row)
        if not patterns:
            continue

        for pattern_name, has_pattern in patterns.items():
            if pattern_name == 'resolved':
                continue

            if has_pattern:
                pattern_instances[pattern_name].add(instance_id)
                all_with_pattern.add(instance_id)

    return {
        'plan_violation': len(pattern_instances['plan_violation']),
        'oscillation': len(pattern_instances['oscillation']),
        'dwell_L_navigate': len(pattern_instances['dwell_L_navigate']),
        'dwell_L_reproduce': len(pattern_instances['dwell_L_reproduce']),
        'dwell_P': len(pattern_instances['dwell_P']),
        'dwell_V': len(pattern_instances['dwell_V']),
        'repeated_view': len(pattern_instances['repeated_view']),
        'total_instances': total_instances
    }


def collect_vanilla_data(comparison_dir: Path, agent: str, datasets: List[str],
                         models: List[str]) -> Dict:
    """Collect vanilla pattern data for all dataset-model combinations."""
    data = {}

    for dataset in datasets:
        for model in models:
            csv_path = comparison_dir / f"{agent}-{model}-{dataset}.csv"

            if not csv_path.exists():
                print(f"CSV not found: {csv_path}")
                continue

            pattern_counts = count_vanilla_patterns(csv_path)

            if pattern_counts:
                key = (dataset, model)
                data[key] = pattern_counts
                print(f"  {dataset} - {model}: {pattern_counts['total_instances']} instances")

    return data


def generate_vanilla_heatmap(data: Dict, datasets: List[str], models: List[str],
                              output_path: Path):
    """Generate heatmap for vanilla config only."""

    # Model abbreviations
    MODEL_ABBR = {
        'deepseek-chat-v3-0324': 'DS',
        'gemini-2.5-flash': 'GF',
        'minimax-m2.5': 'MM'
    }

    # Dataset abbreviations
    DATASET_ABBR = {
        'swebench-pro': 'Pro',
        'swebench': 'Verified'
    }

    # Define patterns with blocking/non-blocking markers
    patterns = [
        ("[B] Plan Violation", "plan_violation"),
        ("[B] Oscillation", "oscillation"),
        ("[N] Dwell Navigate", "dwell_L_navigate"),
        ("[N] Dwell Reproduce", "dwell_L_reproduce"),
        ("[N] Dwell Edit", "dwell_P"),
        ("[N] Dwell Validate", "dwell_V"),
        ("[N] Repeated Action", "repeated_view")
    ]

    n_patterns = len(patterns)
    n_datasets = len(datasets)
    n_models = len(models)
    n_rows = n_patterns * n_datasets
    n_cols = n_models

    # Build data matrix (percentages)
    matrix = np.zeros((n_rows, n_cols))
    row_labels = []

    for dataset_idx, dataset in enumerate(datasets):
        for pattern_idx, (pattern_label, pattern_key) in enumerate(patterns):
            row_idx = dataset_idx * n_patterns + pattern_idx
            row_labels.append(pattern_label)

            # Fill data for this row
            for col_idx, model in enumerate(models):
                key = (dataset, model)
                if key in data:
                    count = data[key].get(pattern_key, 0)
                    total = data[key].get('total_instances', 1)
                    pct = (count / total * 100) if total > 0 else 0
                    matrix[row_idx, col_idx] = pct

    # Create figure: adjust width for fewer columns
    fig_width = max(14, 6 * n_models)
    fig, ax = plt.subplots(figsize=(fig_width, 10))

    # Use green to red colormap
    cmap = plt.cm.RdYlGn_r  # Reversed: green=low, red=high

    # Plot heatmap
    im = ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=0, vmax=100)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, pad=0.02, fraction=0.03)
    cbar.set_label('Percentage (%)', fontsize=34, fontweight='bold')
    cbar.ax.tick_params(labelsize=32)

    # Set ticks and labels
    ax.set_xticks(np.arange(n_cols))
    ax.set_yticks(np.arange(n_rows))

    # Remove x-axis tick labels (model names only at top)
    ax.set_xticklabels([])
    ax.xaxis.set_visible(False)

    # Row labels (pattern names)
    ax.set_yticklabels(row_labels, fontsize=32, fontweight='bold')

    # Add text annotations
    for i in range(n_rows):
        for j in range(n_cols):
            value = matrix[i, j]
            ax.text(j, i, f'{value:.1f}', ha='center', va='center',
                   fontsize=34, fontweight='bold', color='black')

    # Add model headers at top with abbreviations
    for col_idx, model in enumerate(models):
        model_abbr = MODEL_ABBR.get(model, model)
        ax.text(col_idx, -1.0, model_abbr, ha='center', va='center',
               fontsize=42, fontweight='bold', transform=ax.transData)

    # Add dataset labels on the right (vertical orientation)
    for dataset_idx, dataset in enumerate(datasets):
        dataset_abbr = DATASET_ABBR.get(dataset, dataset)
        mid_row = dataset_idx * n_patterns + (n_patterns - 1) / 2
        ax.text(n_cols + 0.5, mid_row, dataset_abbr, ha='center', va='center',
               fontsize=38, fontweight='bold', rotation=90, transform=ax.transData)

    # Draw horizontal separators between datasets
    for dataset_idx in range(1, n_datasets):
        ax.axhline(y=dataset_idx * n_patterns - 0.5, color='black', linewidth=3, linestyle='-')

    # Draw horizontal separators between pattern groups within each dataset
    for dataset_idx in range(n_datasets):
        base = dataset_idx * n_patterns
        # Separator after blocking patterns (after oscillation, before dwell_L_navigate)
        ax.axhline(y=base + 1.5, color='gray', linewidth=1.5, linestyle='--', alpha=0.6)

    # Styling
    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(n_rows - 0.5, -1.8)  # Extra space at top for model names

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)

    plt.tight_layout()

    # Save figure
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.1)
    plt.close()

    print(f"Vanilla heatmap saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate vanilla inefficiency pattern heatmap')
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name')
    parser.add_argument('--datasets', nargs='+', default=['swebench-pro', 'swebench'],
                       help='List of datasets')
    parser.add_argument('--models', nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='List of models')

    args = parser.parse_args()

    # Determine project root
    script_dir = Path(__file__).parent.parent.parent
    comparison_dir = script_dir / "analysis" / "analysis-results" / "comparison"

    if not comparison_dir.exists():
        print(f"Comparison directory not found: {comparison_dir}")
        return

    # Collect vanilla data
    print("Collecting vanilla pattern data from CSV files...")
    data = collect_vanilla_data(comparison_dir, args.agent, args.datasets, args.models)

    if not data:
        print("No data found. Check paths and configurations.")
        return

    print(f"\nCollected data for {len(data)} dataset-model combinations")

    # Generate heatmap
    figures_dir = script_dir / "analysis" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    heatmap_path = figures_dir / "vanilla_inefficiency_patterns_heatmap.pdf"
    generate_vanilla_heatmap(data, args.datasets, args.models, heatmap_path)

    print("\nVanilla pattern heatmap generation complete!")


if __name__ == "__main__":
    main()
