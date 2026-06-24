"""
Load resolved instance IDs from the reports, and generate a Venn diagram to visualize the overlap of the resolved instances between different configurations for each model.

default config list: ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']

Skip if a corresponding config data is unavailable; we'll still visualize the remaining available configs as venn.
The generated figure will be saved in "analysis/figures/venn_resolved/"; each subplot will be a model in a dataset, 2 (dataset) * 3 (model).

Example usage:
python analysis/visualize/venn_resolved_plot.py --dataset swebench --models deepseek-chat-v3-0324 gemini-2.5-flash --configs default monitor refiner
python analysis/visualize/venn_resolved_plot.py --all
"""
import json
import argparse
from pathlib import Path
from typing import Set, Dict, List
from itertools import combinations
from collections import OrderedDict
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np

try:
    from venn import venn as venn_draw
except ImportError:
    print("Error: 'venn' package not found. Install with: pip install venn")
    raise

# Load visualization name mappings
def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()

# Config color mapping (green for refiner)
CONFIG_COLORS = {
    "default": "#FFD3B6",      # peach
    "sage": "#a0c4ff",         # blue
    "monitor": "#E6A8C2",      # pink
    "refiner-only": "#bc5090", # purple
    "refiner": "#A8E6CF",      # green
}

ALPHA = 0.65

def load_report(agent_dir: Path, config: str, dataset: str, model: str, run_id: int, version: str = None) -> Set[str]:
    """Load resolved instance IDs from report file."""
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


def load_all_configs(agent_dir: Path, dataset: str, model: str, configs: List[str],
                     run_id: int = 1, version: str = '5') -> Dict[str, Set[str]]:
    """Load resolved IDs for all specified configs."""
    config_data = {}
    for config in configs:
        resolved_ids = load_report(agent_dir, config, dataset, model, run_id, version)
        if resolved_ids:
            config_data[config] = resolved_ids
            print(f"  {config}: {len(resolved_ids)} resolved")
        else:
            print(f"  {config}: No data found, skipping")
    return config_data


# ----------------------- Label utilities -----------------------
def _hide_zero_labels(ax: plt.Axes) -> None:
    """Hide labels that show 0 or empty values."""
    for t in ax.texts:
        if t.get_text() in ("0", "0.0", ""):
            t.set_visible(False)


def _repel_labels(ax: plt.Axes, max_iter: int = 280, step: float = 1.0) -> None:
    """
    Minimal overlap avoidance for Venn diagram labels.
    Only applies tiny adjustments when labels truly overlap, preserving correct region positioning.
    """
    fig = ax.figure
    fig.canvas.draw()
    texts = [t for t in ax.texts if t.get_visible()]
    if len(texts) < 2:
        return

    # Only do minimal adjustment to avoid obscuring each other
    for iteration in range(max_iter):
        moved = False
        bboxes = [t.get_window_extent(fig.canvas.get_renderer()).expanded(1.05, 1.1) for t in texts]
        for i in range(len(texts)):
            for j in range(i+1, len(texts)):
                if not bboxes[i].overlaps(bboxes[j]):
                    continue
                moved = True
                # Very small nudges to avoid obscuring, not relocate
                dx = step * 0.5 if (i % 2 == 0) else -step * 0.5
                dy = (step * 0.3) if (j % 2 == 0) else -(step * 0.3)
                for t, ddx, ddy in ((texts[i], dx, dy), (texts[j], -dx, -dy)):
                    x, y = t.get_position()
                    inv = ax.transData.inverted()
                    new_disp = ax.transData.transform((x, y)) + np.array([ddx, ddy])
                    new_xy = inv.transform(new_disp)
                    t.set_position(new_xy)
        if not moved:
            break

    # Keep labels within visible area
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    for t in texts:
        x, y = t.get_position()
        x = min(max(x, x0 + 0.01*(x1-x0)), x1 - 0.01*(x1-x0))
        y = min(max(y, y0 + 0.01*(y1-y0)), y1 - 0.01*(y1-y0))
        t.set_position((x, y))


def _recolor_patches_to_labels(ax: plt.Axes, labels_in_order: List[str], color_map: Dict[str, str]) -> None:
    """Match patch colors to our label→color mapping; remove edges; round joins."""
    patches = list(ax.patches)
    n = min(len(patches), len(labels_in_order))
    for i in range(n):
        p = patches[i]
        c = color_map[labels_in_order[i]]
        try:
            p.set_facecolor(c)
            p.set_alpha(ALPHA)
            p.set_edgecolor("none")
            if hasattr(p, "set_joinstyle"):
                p.set_joinstyle("round")
            if hasattr(p, "set_capstyle"):
                p.set_capstyle("round")
        except Exception:
            pass


# ----------------------- Drawing -----------------------
def plot_venn_diagram(config_data: Dict[str, Set[str]], ax, color_map: Dict[str, str]):
    """Plot beautiful Venn diagram for 2+ configs using venn library."""
    n_configs = len(config_data)

    if n_configs == 0:
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', fontsize=28)
        ax.axis('off')
        return

    if n_configs == 1:
        config_name = list(config_data.keys())[0]
        display_name = CONFIG_NAME_MAP.get(config_name, config_name)
        count = len(list(config_data.values())[0])
        ax.text(0.5, 0.5, f'{display_name}\n{count}', ha='center', va='center',
                fontsize=32, bbox=dict(boxstyle='circle',
                                      facecolor=color_map.get(config_name, CONFIG_COLORS.get(config_name, "#A8E6CF")),
                                      alpha=ALPHA, edgecolor='none'))
        ax.axis('off')
        return

    # Prepare ordered dict with display names
    config_names = list(config_data.keys())
    ordered = OrderedDict()
    for config_name in config_names:
        display_name = CONFIG_NAME_MAP.get(config_name, config_name)
        ordered[display_name] = config_data[config_name]

    # Draw venn using the venn library
    try:
        venn_draw(ordered, ax=ax)

        # Remove default legend
        if (leg := ax.get_legend()) is not None:
            try:
                leg.remove()
            except Exception:
                pass

        # Apply custom colors
        _recolor_patches_to_labels(ax, config_names, color_map)

        # Hide zero labels
        _hide_zero_labels(ax)

        # Emphasize region counts - larger text
        # The venn library positions labels correctly in each region
        # We only style them, not move them
        for t in ax.texts:
            t.set_fontsize(38)
            t.set_fontweight('bold')
            t.set_color("#1d232a")
            t.set_path_effects([pe.withStroke(linewidth=3.0, foreground="white")])

        # Only repel if there are actual overlaps causing readability issues
        # Use minimal repelling to preserve correct region positioning
        _repel_labels(ax, max_iter=50, step=0.5)

        # Clean frame
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])

    except Exception as e:
        # Fallback to text display for 4+ configs
        ax.axis('off')
        info_lines = [f"Total configs: {n_configs}"]
        for name, ids in config_data.items():
            display_name = CONFIG_NAME_MAP.get(name, name)
            info_lines.append(f"{display_name}: {len(ids)}")

        # Show pairwise intersections
        pairs = list(combinations(config_names, 2))[:6]
        info_lines.append("\nTop overlaps:")
        for c1, c2 in pairs:
            d1 = CONFIG_NAME_MAP.get(c1, c1)
            d2 = CONFIG_NAME_MAP.get(c2, c2)
            overlap = len(config_data[c1] & config_data[c2])
            info_lines.append(f"{d1} ∩ {d2}: {overlap}")

        ax.text(0.1, 0.5, '\n'.join(info_lines), ha='left', va='center',
                fontsize=13, family='monospace')


def generate_venn_plots(datasets: List[str], models: List[str], configs: List[str],
                        run_id: int = 1, version: str = '5', output_dir: Path = None):
    """Generate Venn diagram plots for all dataset-model combinations."""
    script_dir = Path(__file__).parent.parent.parent

    if output_dir is None:
        output_dir = script_dir / "analysis" / "figures" 
    output_dir.mkdir(parents=True, exist_ok=True)

    n_datasets = len(datasets)
    n_models = len(models)

    # Create color map for configs using predefined colors
    color_map = {config: CONFIG_COLORS.get(config, "#A8E6CF") for config in configs}

    # Larger figure with compact spacing
    fig_width = 10 * n_models
    fig_height = 9 * n_datasets
    fig, axes = plt.subplots(n_datasets, n_models, figsize=(fig_width, fig_height),
                             squeeze=False)

    for i, dataset in enumerate(datasets):
        # Determine agent directory
        if dataset == 'swebench':
            agent_dir = script_dir / "SWE-agent"
        elif dataset == 'swebench-pro':
            agent_dir = script_dir / "SWE-bench_Pro-os" / "SWE-agent"
        else:
            print(f"Unknown dataset: {dataset}")
            continue

        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)

        for j, model in enumerate(models):
            ax = axes[i, j]

            print(f"\nProcessing {dataset} - {model}:")
            config_data = load_all_configs(agent_dir, dataset, model, configs, run_id, version)

            plot_venn_diagram(config_data, ax, color_map)

            # Add column title (model) on top row
            if i == 0:
                model_display = MODEL_NAME_MAP.get(model, model)
                ax.set_title(model_display, fontsize=38, fontweight='bold', pad=5)

            # Add row label (dataset) on left column
            if j == 0:
                ax.set_ylabel(dataset_display, fontsize=38, fontweight='bold',
                             rotation=90, labelpad=10)

    # Create legend for configs
    from matplotlib.patches import Patch
    active_configs = [c for c in configs if c in color_map]
    legend_handles = [
        Patch(facecolor=color_map[config], edgecolor='none', alpha=ALPHA,
              label=CONFIG_NAME_MAP.get(config, config))
        for config in active_configs
    ]

    fig.legend(handles=legend_handles, loc='lower center', ncol=len(active_configs),
              frameon=False, fontsize=36, bbox_to_anchor=(0.5, 0.05),
              columnspacing=2.2, handlelength=2.2,
              prop={'weight': 'bold', 'size': 36})

    # Minimal spacing between subplots for compactness
    plt.subplots_adjust(left=0.08, right=0.99, top=0.97, bottom=0.08,
                       wspace=0.03, hspace=0.08)

    output_file = output_dir / f"venn_resolved.pdf"
    plt.savefig(output_file, format="pdf", dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Generate Venn diagrams for resolved instances across configs')
    parser.add_argument('--datasets', nargs='+', default=['swebench-pro', 'swebench'],
                       help='Dataset names (default: swebench swebench-pro)')
    parser.add_argument('--models', nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='Model names')
    parser.add_argument('--configs', nargs='+',
                       default=['default', 'sage', 'monitor', 'refiner-only', 'refiner'],
                       help='Config names')
    parser.add_argument('--run_id', type=int, default=1, help='Run ID (default: 1)')
    parser.add_argument('--version', type=str, default='5',
                       help='Version for refiner configs (default: 5)')
    parser.add_argument('--all', action='store_true',
                       help='Use all default datasets, models, and configs')

    args = parser.parse_args()

    if args.all:
        datasets = ['swebench', 'swebench-pro']
        models = ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
        configs = ['default', 'sage', 'monitor', 'refiner-only', 'refiner']
    else:
        datasets = args.datasets
        models = args.models
        configs = args.configs

    print(f"Generating Venn diagrams:")
    print(f"  Datasets: {datasets}")
    print(f"  Models: {models}")
    print(f"  Configs: {configs}")
    print(f"  Run ID: {args.run_id}")
    print(f"  Version: {args.version}")

    generate_venn_plots(datasets, models, configs, args.run_id, args.version)


if __name__ == "__main__":
    main()