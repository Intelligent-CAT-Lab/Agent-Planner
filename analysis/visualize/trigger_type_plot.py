"""
Generate trigger type distribution tables from monitor/refiner analysis results.

Loads analysis files from:
  analysis/analysis-results/comparison/detailed-analysis/{config}/{agent}-{model}-{dataset}-{config}-analysis.json

Generates compact tables showing percentage of total instances with each trigger type.
Supports hierarchical display with selective splitting of categories.

Usage:
  python analysis/visualize/trigger_type_plot.py --config refiner --split-mode partial
  python analysis/visualize/trigger_type_plot.py --config refiner --split-mode none
  python analysis/visualize/trigger_type_plot.py --config refiner --split-mode all
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


def load_name_maps(name_map_path: Path) -> Dict:
    """Load display name mappings."""
    with open(name_map_path) as f:
        return json.load(f)


def map_to_coarse_type(fine_type: str) -> str:
    """Map fine-grained trigger types to coarse categories."""
    if fine_type == 'plan_violation':
        return 'plan_violation'
    if fine_type.startswith('dwell_'):
        return 'dwell_times'
    if fine_type.startswith('oscillation_') and 'thought' not in fine_type:
        return 'oscillations'
    if fine_type.startswith('thought_oscillation_'):
        return 'thought_oscillation'
    if fine_type == 'repeated_view':
        return 'repeated_view'
    return fine_type


def extract_trigger_types_from_instance(instance_data: Dict, config: str) -> Set[str]:
    """Extract trigger types from a single instance by scanning its interventions."""
    trigger_types = set()
    planner_stats = instance_data.get(config, {}).get('planner_stats')
    if not planner_stats:
        return trigger_types

    interventions = planner_stats.get('interventions', [])
    for intervention in interventions:
        planner_type = intervention.get('planner_type')

        if planner_type == 'monitor':
            pattern = intervention.get('pattern')
            if pattern and pattern != 'unknown':
                trigger_types.add(pattern)
        elif planner_type == 'refiner':
            rule_ids = intervention.get('rule_ids', [])
            for rule_id in rule_ids:
                if rule_id and rule_id != 'unknown':
                    trigger_types.add(rule_id)

    return trigger_types


def compute_trigger_distribution(analysis_path: Path, config: str) -> Dict:
    """Compute trigger type distribution by scanning all instances."""
    if not analysis_path.exists():
        return {'trigger_counts': {}, 'total_instances': 0}

    with open(analysis_path) as f:
        data = json.load(f)

    total_instances = data['summary']['total_instances']
    trigger_counts = defaultdict(int)

    for category in ['R-R', 'R-U', 'U-R', 'U-U']:
        instances = data['category_details'][category]['instances']
        for instance in instances:
            trigger_types = extract_trigger_types_from_instance(instance, config)
            for tt in trigger_types:
                trigger_counts[tt] += 1

    return {
        'trigger_counts': dict(trigger_counts),
        'total_instances': total_instances
    }


def build_table_structure(all_trigger_types: Set[str], split_mode: str, name_maps: Dict) -> List[Tuple]:
    """
    Build hierarchical table structure.

    Returns list of (coarse_type, fine_types, is_split) tuples.
    - split_mode='none': all coarse, no splitting
    - split_mode='partial': split only categories in SPLIT_CATEGORIES
    - split_mode='all': split all categories into fine-grained
    """
    split_categories = name_maps.get('SPLIT_CATEGORIES', [])
    coarse_to_fine = name_maps.get('COARSE_TO_FINE_MAP', {})

    # Group triggers by coarse type
    coarse_groups = defaultdict(set)
    for tt in all_trigger_types:
        coarse = map_to_coarse_type(tt)
        coarse_groups[coarse].add(tt)

    # Order coarse types
    coarse_order = ['plan_violation', 'dwell_times', 'oscillations', 'thought_oscillation', 'repeated_view']
    ordered_coarse = [c for c in coarse_order if c in coarse_groups]

    # Build structure
    structure = []
    for coarse in ordered_coarse:
        fine_types = sorted(coarse_groups[coarse], key=lambda t: coarse_to_fine.get(coarse, []).index(t) if t in coarse_to_fine.get(coarse, []) else 99)

        if split_mode == 'none':
            # No splitting: show only coarse
            structure.append((coarse, [coarse], False))
        elif split_mode == 'partial':
            # Partial: split only if in SPLIT_CATEGORIES
            if coarse in split_categories and len(fine_types) > 1:
                structure.append((coarse, fine_types, True))
            else:
                structure.append((coarse, [coarse], False))
        elif split_mode == 'all':
            # All: split everything that has multiple fine types
            if len(fine_types) > 1:
                structure.append((coarse, fine_types, True))
            else:
                structure.append((coarse, [coarse], False))

    return structure


def generate_table(datasets: List[str], models: List[str], config: str,
                   split_mode: str, agent: str, analysis_dir: Path,
                   name_maps: Dict) -> None:
    """Generate compact LaTeX and Markdown tables."""

    # Collect all data
    data = {}
    total_instances = {}

    for dataset in datasets:
        for model in models:
            analysis_file = analysis_dir / config / f"{agent}-{model}-{dataset}-{config}-analysis.json"
            if analysis_file.exists():
                result = compute_trigger_distribution(analysis_file, config)
                data[(dataset, model)] = result['trigger_counts']
                total_instances[(dataset, model)] = result['total_instances']

    if not data:
        print(f"No data found for config: {config}")
        return

    # Get all trigger types
    all_trigger_types = set()
    for trigger_counts in data.values():
        all_trigger_types.update(trigger_counts.keys())

    if not all_trigger_types:
        print(f"No trigger types found for config: {config}")
        return

    # Build table structure
    structure = build_table_structure(all_trigger_types, split_mode, name_maps)

    # Flatten structure to get column list
    columns = []
    for coarse, fine_list, is_split in structure:
        if is_split:
            columns.extend(fine_list)
        else:
            columns.append(coarse)

    model_name_map = name_maps['MODEL_NAME_MAP']
    dataset_name_map = name_maps['DATASET_NAME_MAP']
    rule_name_map = name_maps['RULE_NAME_MAP']
    fine_rule_name_map = name_maps['FINE_RULE_NAME_MAP']

    output_dir = Path('analysis/tables')
    output_dir.mkdir(parents=True, exist_ok=True)

    # LaTeX table
    latex_path = output_dir / f"trigger_type_{config}_{split_mode}.tex"
    with open(latex_path, 'w') as f:
        f.write("\\begin{table*}[t]\n")
        f.write("\\caption{Trigger type distribution for " + name_maps['CONFIG_NAME_MAP'][config] + ". ")
        f.write("Values show percentage of instances containing each trigger type.}\n")
        # f.write("\\label{tab:trigger_" + config + "_" + split_mode + "}\n")
        f.write("\\label{tab:trigger_distribution}\n")
        f.write("\\centering\n")
        f.write("\\scriptsize\n")

        # Column spec
        num_cols = len(columns)
        f.write(f"\\begin{{tabular}}{{@{{}}ll{'r' * num_cols}@{{}}}}\n")
        f.write("\\toprule\n")

        # Header row 1: Coarse categories (with multicolumn for split categories)
        f.write("\\multirow{2}{*}{\\textbf{Dataset}} & \\multirow{2}{*}{\\textbf{Model}}")
        for coarse, fine_list, is_split in structure:
            coarse_name = rule_name_map.get(coarse, coarse)
            if is_split:
                f.write(f" & \\multicolumn{{{len(fine_list)}}}{{c}}{{\\textbf{{{coarse_name}}}}}")
            else:
                f.write(f" & \\multirow{{2}}{{*}}{{\\textbf{{{coarse_name}}}}}")
        f.write(" \\\\\n")

        # Cmidrules for split categories
        cmidrules = []
        col_idx = 3
        for coarse, fine_list, is_split in structure:
            if is_split:
                cmidrules.append(f"\\cmidrule(lr){{{col_idx}-{col_idx + len(fine_list) - 1}}}")
                col_idx += len(fine_list)
            else:
                col_idx += 1
        if cmidrules:
            f.write(" ".join(cmidrules) + "\n")

        # Header row 2: Fine-grained names (only for split categories)
        f.write(" &")
        for coarse, fine_list, is_split in structure:
            if is_split:
                for fine in fine_list:
                    fine_name = fine_rule_name_map.get(fine, fine)
                    f.write(f" & {fine_name}")
            else:
                f.write(" &")  # Empty for non-split (handled by multirow)
        f.write(" \\\\\n")
        f.write("\\midrule\n")

        # Data rows
        for i_dataset, dataset in enumerate(datasets):
            dataset_models = [m for m in models if (dataset, m) in data]

            for i_model, model in enumerate(dataset_models):
                key = (dataset, model)
                trigger_counts = data[key]
                total = total_instances[key]

                # Row label
                if i_model == 0:
                    f.write(f"\\multirow{{{len(dataset_models)}}}{{*}}{{{dataset_name_map[dataset]}}} & {model_name_map[model]}")
                else:
                    f.write(f" & {model_name_map[model]}")

                # Data
                for col in columns:
                    if col in trigger_counts:
                        count = trigger_counts[col]
                    else:
                        # For coarse column, sum all fine-grained counts
                        count = sum(trigger_counts.get(ft, 0) for ft in all_trigger_types if map_to_coarse_type(ft) == col)

                    pct = (count / total * 100) if total > 0 else 0
                    f.write(f" & {pct:.1f}")

                f.write(" \\\\\n")

            if i_dataset < len(datasets) - 1:
                f.write("\\midrule\n")

        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table*}\n")

    # Markdown table
    md_path = output_dir / f"trigger_type_{config}_{split_mode}.md"
    with open(md_path, 'w') as f:
        f.write(f"# Trigger Type Distribution - {name_maps['CONFIG_NAME_MAP'][config]} ({split_mode} split)\n\n")

        # Header
        f.write("| Dataset | Model |")
        for coarse, fine_list, is_split in structure:
            coarse_name = rule_name_map.get(coarse, coarse)
            if is_split:
                for fine in fine_list:
                    fine_name = fine_rule_name_map.get(fine, fine)
                    f.write(f" {fine_name} |")
            else:
                f.write(f" {coarse_name} |")
        f.write("\n")

        # Separator
        f.write("|:---|:---|" + ":---:|" * len(columns) + "\n")

        # Data rows
        for dataset in datasets:
            for model in models:
                key = (dataset, model)
                if key not in data:
                    continue

                trigger_counts = data[key]
                total = total_instances[key]

                f.write(f"| {dataset_name_map[dataset]} | {model_name_map[model]} |")

                for col in columns:
                    if col in trigger_counts:
                        count = trigger_counts[col]
                    else:
                        # For coarse column, sum all fine-grained counts
                        count = sum(trigger_counts.get(ft, 0) for ft in all_trigger_types if map_to_coarse_type(ft) == col)

                    pct = (count / total * 100) if total > 0 else 0
                    f.write(f" {pct:.1f} |")

                f.write("\n")

        f.write(f"\n*Values show percentage of instances containing each trigger type.*\n")

    print(f"\n✓ Generated tables for {config} ({split_mode} split):")
    print(f"  LaTeX: {latex_path}")
    print(f"  Markdown: {md_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate trigger type distribution tables'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name (default: SWE-agent)')
    parser.add_argument('--datasets', type=str, nargs='+',
                       default=['swebench', 'swebench-pro'],
                       help='Dataset names (default: swebench swebench-pro)')
    parser.add_argument('--models', type=str, nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='Model names')
    parser.add_argument('--config', type=str, default='refiner',
                       choices=['monitor', 'refiner-only', 'refiner'],
                       help='Config to analyze (default: refiner)')
    parser.add_argument('--split-mode', type=str, default='partial',
                       choices=['none', 'partial', 'all'],
                       help='Split mode: none (coarse only), partial (split SPLIT_CATEGORIES), all (split everything)')
    parser.add_argument('--analysis-dir', type=Path,
                       default=Path('analysis/analysis-results/comparison/detailed-analysis'),
                       help='Directory containing analysis JSON files')
    parser.add_argument('--name-map', type=Path,
                       default=Path('analysis/visualize/name_map.json'),
                       help='Path to name mapping JSON file')

    args = parser.parse_args()

    # Load name maps
    name_maps = load_name_maps(args.name_map)

    # Generate table
    generate_table(
        datasets=args.datasets,
        models=args.models,
        config=args.config,
        split_mode=args.split_mode,
        agent=args.agent,
        analysis_dir=args.analysis_dir,
        name_maps=name_maps
    )


if __name__ == "__main__":
    main()
