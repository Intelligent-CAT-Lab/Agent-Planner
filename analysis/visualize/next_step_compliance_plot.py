"""
Compute the next step compliance score (the number of "true" "follows_guidance" / total interventions of this instance)
The intervention and resolution details are in analysis/analysis-results/comparison/detailed-analysis/refiner/{agent}-{model}-{dataset}-analysis.json.
Generate median-iqr boxplot (green: resolved; red: unresolved) per agent-model pair. layout: 2 (dataset, default to ['swebench-pro', 'swebench']) rows * 3 (model, default to ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']) columns.
Default config: ['refiner'].
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()


def load_analysis_data(analysis_dir: Path, agent: str, model: str, dataset: str, config: str) -> Dict:
    """Load detailed analysis data for a specific configuration."""
    analysis_file = analysis_dir / "comparison" / "detailed-analysis" / config / f"{agent}-{model}-{dataset}-{config}-analysis.json"

    if not analysis_file.exists():
        print(f"Warning: Analysis file not found: {analysis_file}")
        return None

    try:
        with open(analysis_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {analysis_file}: {e}")
        return None


def compute_compliance_scores(data: Dict, transition: str = None) -> Tuple[List[float], List[float]]:
    """
    Compute next step compliance scores for resolved and unresolved instances.

    The data structure has categories: R-R, R-U, U-R, U-U
    - Resolved: R-R (vanilla resolved, config resolved) and U-R (vanilla unresolved, config resolved)
    - Unresolved: U-U (both unresolved) and R-U (vanilla resolved, config unresolved)

    Args:
        data: Analysis data containing category_details
        transition: If specified (e.g., 'U-R'), only compute for that specific transition category

    Returns:
        Tuple of (resolved_scores, unresolved_scores)
    """
    resolved_scores = []
    unresolved_scores = []

    category_details = data.get('category_details', {})

    # If transition is specified, only process that category
    if transition:
        if transition not in category_details:
            return [], []

        # Determine if this transition results in resolved or unresolved
        # U-R and R-R: config resolved
        # U-U and R-U: config unresolved
        is_resolved_transition = transition in ['R-R', 'U-R']

        instances = category_details[transition].get('instances', [])
        for instance in instances:
            if not isinstance(instance, dict):
                continue

            config_data = instance.get('refiner', {})
            if not config_data:
                continue

            # Verify resolution status matches transition
            is_resolved = config_data.get('resolved', False)
            if is_resolved != is_resolved_transition:
                continue

            planner_stats = config_data.get('planner_stats', {})
            if not planner_stats:
                continue

            interventions = planner_stats.get('interventions', [])
            if not interventions:
                continue

            # Count only interventions with follows_guidance field
            valid_interventions = [i for i in interventions if 'follows_guidance' in i]
            if not valid_interventions:
                continue

            total = len(valid_interventions)
            follows = sum(1 for i in valid_interventions if i.get('follows_guidance') is True)

            score = follows / total

            if is_resolved_transition:
                resolved_scores.append(score)
            else:
                unresolved_scores.append(score)

        return resolved_scores, unresolved_scores

    # Categories where config resolved (R-R, U-R)
    resolved_categories = ['R-R', 'U-R']
    # Categories where config unresolved (R-U, U-U)
    unresolved_categories = ['R-U', 'U-U']

    for category in resolved_categories:
        if category not in category_details:
            continue

        instances = category_details[category].get('instances', [])
        for instance in instances:
            if not isinstance(instance, dict):
                continue

            # Get config data
            config_data = instance.get('refiner', {})
            if not config_data:
                continue

            # Verify resolution status
            is_resolved = config_data.get('resolved', False)
            if not is_resolved:
                continue

            # Get interventions from planner_stats
            planner_stats = config_data.get('planner_stats', {})
            if not planner_stats:
                continue

            interventions = planner_stats.get('interventions', [])
            if not interventions:
                continue

            # Count only interventions with follows_guidance field
            valid_interventions = [i for i in interventions if 'follows_guidance' in i]
            if not valid_interventions:
                continue

            total = len(valid_interventions)
            follows = sum(1 for i in valid_interventions if i.get('follows_guidance') is True)

            score = follows / total
            resolved_scores.append(score)

    for category in unresolved_categories:
        if category not in category_details:
            continue

        instances = category_details[category].get('instances', [])
        for instance in instances:
            if not isinstance(instance, dict):
                continue

            # Get config data
            config_data = instance.get('refiner', {})
            if not config_data:
                continue

            # Verify resolution status
            is_resolved = config_data.get('resolved', False)
            if is_resolved:
                continue

            # Get interventions from planner_stats
            planner_stats = config_data.get('planner_stats', {})
            if not planner_stats:
                continue

            interventions = planner_stats.get('interventions', [])
            if not interventions:
                continue

            # Count only interventions with follows_guidance field
            valid_interventions = [i for i in interventions if 'follows_guidance' in i]
            if not valid_interventions:
                continue

            total = len(valid_interventions)
            follows = sum(1 for i in valid_interventions if i.get('follows_guidance') is True)

            score = follows / total
            unresolved_scores.append(score)

    return resolved_scores, unresolved_scores


def generate_latex_table(
    data: Dict[Tuple[str, str], Tuple[List[float], List[float]]],
    datasets: List[str],
    models: List[str],
    config: str,
    output_path: Path
):
    """
    Generate LaTeX table reporting average compliance score per instance.
    Combines resolved and unresolved instances.
    """
    # Reorder datasets
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    # Compute average scores
    avg_scores = {}
    for dataset in ordered_datasets:
        for model in models:
            key = (dataset, model)
            if key in data:
                resolved_scores, unresolved_scores = data[key]
                all_scores = resolved_scores + unresolved_scores
                if all_scores:
                    avg_scores[(dataset, model)] = np.mean(all_scores)
                else:
                    avg_scores[(dataset, model)] = None

    # Generate LaTeX table
    lines = []
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append("\\caption{Average Next step compliance scores.}")
    lines.append("\\label{tab:next_step_compliance}")

    # Table header with dataset columns
    n_cols = len(ordered_datasets) + 1  # +1 for Model column
    col_spec = "l" + "c" * len(ordered_datasets)
    lines.append(f"\\begin{{tabular}}{{{col_spec}}}")
    lines.append("\\toprule")

    # Column headers
    dataset_headers = " & ".join([f"\\textbf{{{DATASET_NAME_MAP.get(d, d)}}}" for d in ordered_datasets])
    lines.append(f"\\textbf{{Model}} & {dataset_headers} \\\\")
    lines.append("\\midrule")

    # Data rows
    for model in models:
        model_display = MODEL_NAME_MAP.get(model, model)
        # Handle line breaks in model names
        model_display = model_display.replace('\n', '\\\\')
        if '\\\\' in model_display:
            model_display = f"\\shortstack{{{model_display}}}"

        values = []
        for dataset in ordered_datasets:
            key = (dataset, model)
            if key in avg_scores and avg_scores[key] is not None:
                values.append(f"{avg_scores[key]:.2f}")
            else:
                values.append("--")

        row = f"{model_display} & " + " & ".join(values) + " \\\\"
        lines.append(row)

        # Add midrule between models except after last
        if model != models[-1]:
            lines.append("\\midrule")

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    # Save to file in tables/ directory
    table_dir = output_path.parent.parent / 'tables'
    table_dir.mkdir(parents=True, exist_ok=True)
    latex_output = table_dir / output_path.name.replace('.pdf', '.tex')
    with open(latex_output, 'w') as f:
        f.write('\n'.join(lines))

    print(f"LaTeX table saved to: {latex_output}")


def generate_latex_table_split(
    data: Dict[Tuple[str, str], Tuple[List[float], List[float]]],
    datasets: List[str],
    models: List[str],
    config: str,
    output_path: Path
):
    """
    Generate LaTeX table reporting average compliance scores split by resolved/unresolved.
    Columns: Dataset (multicolumn) -> R/U split
    Rows: Model
    """
    # Reorder datasets
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    # Compute average scores for R and U separately
    split_scores = {}
    for dataset in ordered_datasets:
        for model in models:
            key = (dataset, model)
            if key in data:
                resolved_scores, unresolved_scores = data[key]
                split_scores[(dataset, model, 'R')] = np.mean(resolved_scores) if resolved_scores else None
                split_scores[(dataset, model, 'U')] = np.mean(unresolved_scores) if unresolved_scores else None

    # Generate LaTeX table
    lines = []
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append("\\caption{Average Next step compliance scores (split by resolution status).}")
    lines.append("\\label{tab:next_step_compliance_split}")

    # Table header: Model + (R, U) for each dataset
    n_data_cols = len(ordered_datasets) * 2  # R and U for each dataset
    col_spec = "l" + "cc" * len(ordered_datasets)
    lines.append(f"\\begin{{tabular}}{{{col_spec}}}")
    lines.append("\\toprule")

    # First header row: dataset names with multicolumn
    header_parts = ["\\textbf{Model}"]
    for dataset in ordered_datasets:
        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)
        header_parts.append(f"\\multicolumn{{2}}{{c}}{{\\textbf{{{dataset_display}}}}}")
    lines.append(" & ".join(header_parts) + " \\\\")

    # Second header row: R/U labels
    subheader_parts = [""]
    for _ in ordered_datasets:
        subheader_parts.extend(["\\textbf{R}", "\\textbf{U}"])
    lines.append(" & ".join(subheader_parts) + " \\\\")
    lines.append("\\midrule")

    # Data rows
    for model in models:
        model_display = MODEL_NAME_MAP.get(model, model)
        # Handle line breaks in model names
        model_display = model_display.replace('\n', '\\\\')
        if '\\\\' in model_display:
            model_display = f"\\shortstack{{{model_display}}}"

        values = [model_display]
        for dataset in ordered_datasets:
            for status in ['R', 'U']:
                key = (dataset, model, status)
                if key in split_scores and split_scores[key] is not None:
                    values.append(f"{split_scores[key]:.2f}")
                else:
                    values.append("--")

        row = " & ".join(values) + " \\\\"
        lines.append(row)

        # Add midrule between models except after last
        if model != models[-1]:
            lines.append("\\midrule")

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    # Save to file in tables/ directory
    table_dir = output_path.parent.parent / 'tables'
    table_dir.mkdir(parents=True, exist_ok=True)
    latex_output = table_dir / output_path.name.replace('.pdf', '_split.tex')
    with open(latex_output, 'w') as f:
        f.write('\n'.join(lines))

    print(f"LaTeX table (split) saved to: {latex_output}")


def create_compliance_boxplot(
    data: Dict[Tuple[str, str], Tuple[List[float], List[float]]],
    datasets: List[str],
    models: List[str],
    output_path: Path
):
    """
    Create boxplot figure showing next step compliance across datasets and models.

    Layout: 2 rows (datasets) x 3 columns (models)
    Each subplot shows boxplots for resolved (green) and unresolved (red) instances
    """
    # Reorder datasets: swebench-pro first
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    if not ordered_datasets:
        print("No datasets to plot")
        return

    n_rows = len(ordered_datasets)
    n_cols = len(models)

    # Create figure - match divergence plot style with shared y-axis
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 6 * n_rows), sharey=True)
    fig.subplots_adjust(hspace=0.3, wspace=0.15, left=0.08, right=0.98, top=0.92, bottom=0.08)

    # Ensure axes is always 2D
    if n_rows == 1 and n_cols == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)
    elif n_cols == 1:
        axes = axes.reshape(-1, 1)

    # Colors matching divergence plot style
    colors = {
        'resolved': '#10b981',   # green
        'unresolved': '#ef4444'  # red
    }

    for row_idx, dataset in enumerate(ordered_datasets):
        for col_idx, model in enumerate(models):
            ax = axes[row_idx, col_idx]

            key = (dataset, model)
            if key not in data:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center',
                       transform=ax.transAxes, fontsize=24)
                ax.set_xticks([])
                ax.set_yticks([])
                continue

            resolved_scores, unresolved_scores = data[key]

            if not resolved_scores and not unresolved_scores:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center',
                       transform=ax.transAxes, fontsize=24)
                ax.set_xticks([])
                ax.set_yticks([])
                continue

            # Prepare data for boxplot
            plot_data = []
            positions = []
            box_colors = []

            if resolved_scores:
                plot_data.append(resolved_scores)
                positions.append(1)
                box_colors.append(colors['resolved'])

            if unresolved_scores:
                plot_data.append(unresolved_scores)
                positions.append(2)
                box_colors.append(colors['unresolved'])

            # Create boxplot
            bp = ax.boxplot(plot_data,
                           positions=positions,
                           widths=0.6,
                           patch_artist=True,
                           showfliers=False,
                           medianprops=dict(color='black', linewidth=3.5),
                           boxprops=dict(linewidth=2),
                           whiskerprops=dict(linewidth=2),
                           capprops=dict(linewidth=2))

            # Color boxes
            for i, (box, color) in enumerate(zip(bp['boxes'], box_colors)):
                box.set_facecolor(color)
                box.set_alpha(0.8)
                box.set_edgecolor('black')

            # Set x-axis - only show labels on bottom row
            ax.set_xticks(positions)
            if row_idx == n_rows - 1:
                labels = []
                if resolved_scores:
                    labels.append('R')
                if unresolved_scores:
                    labels.append('U')
                ax.set_xticklabels(labels, fontsize=32, fontweight='bold')
            else:
                ax.set_xticklabels([])

            # Y-axis - only show label on leftmost column
            if col_idx == 0:
                ax.set_ylabel('Compliance Score', fontsize=34, fontweight='bold')
            ax.set_ylim(-0.05, 1.05)
            ax.tick_params(axis='y', labelsize=30)
            ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=1)
            ax.set_axisbelow(True)

            # Title - show model name on top row, dataset name on left
            if row_idx == 0:
                model_display = MODEL_NAME_MAP.get(model, model)
                ax.set_title(model_display, fontsize=36, fontweight='bold', pad=20)

            # Dataset label on rightmost column
            if col_idx == n_cols - 1:
                dataset_display = DATASET_NAME_MAP.get(dataset, dataset)
                ax.text(1.15, 0.5, dataset_display, transform=ax.transAxes,
                       rotation=90, va='center', ha='center',
                       fontsize=36, fontweight='bold')

    # Add legend with updated labels
    legend_elements = [
        mpatches.Patch(facecolor=colors['resolved'], edgecolor='black', alpha=0.8, linewidth=2,
                      label='Resolved (R)'),
        mpatches.Patch(facecolor=colors['unresolved'], edgecolor='black', alpha=0.8, linewidth=2,
                      label='Unresolved (U)')
    ]

    fig.legend(handles=legend_elements, loc='lower center', ncol=2,
              fontsize=30, frameon=True, bbox_to_anchor=(0.5, -0.04),
              edgecolor='black', fancybox=False)

    # Save figure
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate next step compliance boxplot visualization"
    )
    parser.add_argument("--agent", default="SWE-agent", help="Agent name")
    parser.add_argument("--datasets", nargs="+",
                       default=["swebench-pro", "swebench"],
                       help="Datasets to analyze")
    parser.add_argument("--models", nargs="+",
                       default=["deepseek-chat-v3-0324", "gemini-2.5-flash", "minimax-m2.5"],
                       help="Models to analyze")
    parser.add_argument("--config", type=str,
                        default="refiner",
                        help="Config to analyze")
    parser.add_argument("--analysis-dir", type=Path,
                       default=Path("analysis/analysis-results"),
                       help="Analysis results directory")
    parser.add_argument("--output", type=Path,
                       default=Path("analysis/figures/next_step_compliance.pdf"),
                       help="Output figure path")
    parser.add_argument("--transition", type=str,
                       choices=["R-R", "R-U", "U-R", "U-U"],
                       help="Specific transition category to analyze (e.g., U-R)")

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print("Next Step Compliance Boxplot Visualization")
    print(f"{'='*70}")
    print(f"Agent:      {args.agent}")
    print(f"Datasets:   {args.datasets}")
    print(f"Models:     {args.models}")
    print(f"Config:     {args.config}")
    print(f"Transition: {args.transition if args.transition else 'All (R/U split)'}")
    print(f"Output:     {args.output}")
    print(f"{'='*70}\n")

    # Collect data
    data = {}
    for dataset in args.datasets:
        for model in args.models:
            print(f"Loading data for {dataset} - {model}")
            analysis_data = load_analysis_data(args.analysis_dir, args.agent, model, dataset, args.config)

            if analysis_data:
                resolved_scores, unresolved_scores = compute_compliance_scores(analysis_data, args.transition)
                data[(dataset, model)] = (resolved_scores, unresolved_scores)

                if args.transition:
                    # For specific transition, show which category it belongs to
                    is_resolved = args.transition in ['R-R', 'U-R']
                    if is_resolved:
                        print(f"  {args.transition}: {len(resolved_scores)} instances")
                    else:
                        print(f"  {args.transition}: {len(unresolved_scores)} instances")
                else:
                    print(f"  Resolved: {len(resolved_scores)} instances, "
                          f"Unresolved: {len(unresolved_scores)} instances")
            else:
                print(f"  No data found")

    if not data:
        print("\nNo data available. Exiting.")
        return

    print(f"\nLoaded data for {len(data)} dataset-model pairs")

    # If transition is specified, print average scores per model-dataset pair
    if args.transition:
        print(f"\nAverage compliance scores for transition {args.transition}:")
        print(f"{'='*70}")
        for dataset in args.datasets:
            print(f"\n{DATASET_NAME_MAP.get(dataset, dataset)}:")
            for model in args.models:
                key = (dataset, model)
                if key in data:
                    resolved_scores, unresolved_scores = data[key]
                    scores = resolved_scores if args.transition in ['R-R', 'U-R'] else unresolved_scores
                    if scores:
                        avg_score = np.mean(scores)
                        print(f"  {MODEL_NAME_MAP.get(model, model):20s}: {avg_score:.4f} (n={len(scores)})")
                    else:
                        print(f"  {MODEL_NAME_MAP.get(model, model):20s}: No data")
        print(f"{'='*70}\n")

    # Generate LaTeX tables (skip if transition-specific)
    if not args.transition:
        generate_latex_table(data, args.datasets, args.models, args.config, args.output)
        generate_latex_table_split(data, args.datasets, args.models, args.config, args.output)

    # Create boxplot
    create_compliance_boxplot(data, args.datasets, args.models, args.output)

    completion_msg = "Next step compliance boxplot generation complete!"
    if not args.transition:
        completion_msg = "Next step compliance boxplot and LaTeX tables generation complete!"

    print(f"\n{'='*70}")
    print(completion_msg)
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
