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
import matplotlib.pyplot as plt
from matplotlib_venn import venn2, venn3


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


def plot_venn_diagram(config_data: Dict[str, Set[str]], title: str, ax):
    """Plot Venn diagram for 2-5 configs."""
    n_configs = len(config_data)

    if n_configs == 0:
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', fontsize=12)
        ax.set_title(title, fontsize=11, fontweight='bold')
        ax.axis('off')
        return

    if n_configs == 1:
        config_name = list(config_data.keys())[0]
        count = len(list(config_data.values())[0])
        ax.text(0.5, 0.5, f'{config_name}\n{count}', ha='center', va='center',
                fontsize=12, bbox=dict(boxstyle='circle', facecolor='lightblue', alpha=0.5))
        ax.set_title(title, fontsize=11, fontweight='bold')
        ax.axis('off')
        return

    config_names = list(config_data.keys())
    config_sets = list(config_data.values())

    if n_configs == 2:
        v = venn2(config_sets, set_labels=config_names, ax=ax, alpha=0.6)
    elif n_configs == 3:
        v = venn3(config_sets, set_labels=config_names, ax=ax, alpha=0.6)
    else:
        # For 4+ configs, show pairwise overlaps in text
        ax.axis('off')
        info_lines = [f"Total configs: {n_configs}"]
        for name, ids in config_data.items():
            info_lines.append(f"{name}: {len(ids)}")

        # Show pairwise intersections for first few pairs
        pairs = list(combinations(config_names, 2))[:6]
        info_lines.append("\nTop overlaps:")
        for c1, c2 in pairs:
            overlap = len(config_data[c1] & config_data[c2])
            info_lines.append(f"{c1} ∩ {c2}: {overlap}")

        ax.text(0.1, 0.5, '\n'.join(info_lines), ha='left', va='center',
                fontsize=9, family='monospace')

    ax.set_title(title, fontsize=11, fontweight='bold', pad=10)


def generate_venn_plots(datasets: List[str], models: List[str], configs: List[str],
                        run_id: int = 1, version: str = '5', output_dir: Path = None):
    """Generate Venn diagram plots for all dataset-model combinations."""
    script_dir = Path(__file__).parent.parent.parent

    if output_dir is None:
        output_dir = script_dir / "analysis" / "figures" / "venn_resolved"
    output_dir.mkdir(parents=True, exist_ok=True)

    n_datasets = len(datasets)
    n_models = len(models)

    fig, axes = plt.subplots(n_datasets, n_models, figsize=(6 * n_models, 5 * n_datasets))
    if n_datasets == 1 and n_models == 1:
        axes = [[axes]]
    elif n_datasets == 1:
        axes = [axes]
    elif n_models == 1:
        axes = [[ax] for ax in axes]

    for i, dataset in enumerate(datasets):
        # Determine agent directory
        if dataset == 'swebench':
            agent_dir = script_dir / "SWE-agent"
        elif dataset == 'swebench-pro':
            agent_dir = script_dir / "SWE-bench_Pro-os" / "SWE-agent"
        else:
            print(f"Unknown dataset: {dataset}")
            continue

        for j, model in enumerate(models):
            print(f"\nProcessing {dataset} - {model}:")
            config_data = load_all_configs(agent_dir, dataset, model, configs, run_id, version)

            title = f"{dataset}\n{model}"
            plot_venn_diagram(config_data, title, axes[i][j])

    plt.tight_layout()
    output_file = output_dir / f"venn_resolved.pdf"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Generate Venn diagrams for resolved instances across configs')
    parser.add_argument('--datasets', nargs='+', default=['swebench', 'swebench-pro'],
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