"""
Design a table to report the number of R-R, R-U, U-R, U-U instances compared with the "default" config.
config list default to ['sage', 'monitor', 'refiner-only', 'refiner']
default dataset list: ['swebench', 'swebench-pro']
default model list: ['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5']
use the name_map.

for swebench, the resolved instances can be found in "resolved_ids" in the report and others will fall into "unresolved", R-R/R-U;U-R;U-U add up to 500; for swebench-pro, the resolved instances are "true", add up to 264.
"""

import json
import argparse
from pathlib import Path
from typing import Set, Dict, Tuple


def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()


def load_report(agent_dir: Path, config: str, dataset: str, model: str,
                run_id: int, version: str = '5'):
    """
    Load resolved instance IDs from report file.
    Incomplete instances are treated as unresolved.

    Returns:
        Set of resolved instance IDs, or None if report doesn't exist
    """
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
                    resolved = {inst_id for inst_id, is_resolved in data.items() if is_resolved}
                    return resolved
            except Exception as e:
                print(f"Warning: Error loading {report_path}: {e}")
        return None

    # For swebench, report is in model directory
    if config in ['refiner', 'refiner-only'] and version:
        reports_dir = agent_dir / "reports" / config / f"version-{version}" / dataset_path / model
    else:
        reports_dir = agent_dir / "reports" / config / dataset_path / model

    if not reports_dir.exists():
        return None

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
                    # Only resolved instances are marked as resolved
                    # Incomplete instances are implicitly unresolved
                    resolved = set(data.get('resolved_ids', []))
                    return resolved
            except Exception as e:
                print(f"Warning: Error loading {report_path}: {e}")

    return None


def compute_transitions(baseline_resolved: Set[str], config_resolved: Set[str],
                       dataset: str) -> Dict[str, int]:
    """
    Compute R-R, R-U, U-R, U-U transitions on all instances in the dataset.
    Incomplete instances are treated as unresolved.

    Args:
        baseline_resolved: Resolved IDs from baseline (default) config
        config_resolved: Resolved IDs from comparison config
        dataset: Dataset name (to determine total instances)

    Returns:
        Dict with counts for R-R, R-U, U-R, U-U
    """
    # Total instances in dataset
    total = 264 if dataset == 'swebench-pro' else 500

    # All instances that are resolved in either config
    all_resolved = baseline_resolved | config_resolved

    # Compute transitions
    r_r = len(baseline_resolved & config_resolved)
    r_u = len(baseline_resolved - config_resolved)
    u_r = len(config_resolved - baseline_resolved)
    u_u = total - r_r - r_u - u_r  # All remaining instances are unresolved by both

    return {
        'R-R': r_r,
        'R-U': r_u,
        'U-R': u_r,
        'U-U': u_u,
        'total': total
    }


def generate_latex_table(results: Dict, datasets: list, models: list, configs: list, output_path: Path):
    """Generate a compact LaTeX table with configs as rows and hierarchical dataset-model columns."""

    # Reorder datasets: swebench-pro first, then swebench
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    # Build dataset -> models mapping (only pairs with data)
    dataset_models = {}
    for dataset in ordered_datasets:
        dataset_models[dataset] = []
        for model in models:
            if (dataset, model) in results and results[(dataset, model)]:
                dataset_models[dataset].append(model)

    # Filter to datasets that have at least one model
    dataset_models = {d: ms for d, ms in dataset_models.items() if ms}

    if not dataset_models:
        print("No data found")
        return

    # Determine which configs are actually used
    used_configs = set()
    for (dataset, model), model_data in results.items():
        used_configs.update(model_data.keys())

    available_configs = [c for c in configs if c in used_configs]

    if not available_configs:
        print("No configs with data found")
        return

    lines = []
    lines.append("\\begin{table*}[t]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append("\\caption{Resolution Transition Matrix comparing methods against Vanilla actor baseline. "
                 "RR: both resolved, UU: both unresolved, RU: baseline only, UR: config only. "
                 "Total: 264 for SWE-bench Pro, 500 for SWE-bench Verified. SR denotes Success Rate (\%).}")
    lines.append("\\label{tab:ru_transition}")

    # Column spec: Config | Metric | [models per dataset] with | separators between datasets
    col_spec = "ll"
    for i, (dataset, ms) in enumerate(dataset_models.items()):
        if i > 0:
            col_spec += "|"  # Separator between datasets
        col_spec += "r" * len(ms)  # One column per model
    lines.append(f"\\begin{{tabular}}{{@{{}}{col_spec}@{{}}}}")
    lines.append("\\toprule")

    # Two-level header: Dataset (spanning models) and Model sub-headers
    header1 = "\\textbf{Method} & \\textbf{Metric}"
    for dataset, ms in dataset_models.items():
        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)
        header1 += f" & \\multicolumn{{{len(ms)}}}{{c}}{{\\textbf{{{dataset_display}}}}}"
    header1 += " \\\\"
    lines.append(header1)

    # Second header row with model names
    header2 = " & "
    for dataset, ms in dataset_models.items():
        for model in ms:
            model_display = MODEL_NAME_MAP.get(model, model)
            header2 += f" & \\textbf{{{model_display}}}"
    header2 += " \\\\"
    lines.append(header2)
    lines.append("\\midrule")

    # Metric order: R-R, U-U, R-U, U-R
    metrics = ['R-R', 'U-U', 'R-U', 'U-R']

    # Data rows - one config at a time with 5 rows (4 metrics + SR)
    for i, config in enumerate(available_configs):
        config_display = CONFIG_NAME_MAP.get(config, config)

        # Add separator between configs
        if i > 0:
            lines.append("\\midrule")

        # Four rows for metrics
        for j, metric in enumerate(metrics):
            if j == 0:
                # First row shows config name with rowspan 5 (4 metrics + 1 SR row)
                row = f"\\multirow{{5}}{{*}}{{{config_display}}} & {metric}"
            else:
                row = f" & {metric}"

            # Add data for each dataset-model pair
            for dataset, ms in dataset_models.items():
                for model in ms:
                    if (dataset, model) in results and config in results[(dataset, model)]:
                        stats = results[(dataset, model)][config]
                        row += f" & {stats[metric]}"
                    else:
                        row += " & --"

            row += " \\\\"
            lines.append(row)

        # Success Rate row (after the 4 metrics)
        sr_row = " & \\textbf{SR (\\%)}"
        for dataset, ms in dataset_models.items():
            total = 264 if dataset == 'swebench-pro' else 500

            # Add SR for each model in this dataset
            for model in ms:
                if (dataset, model) in results and config in results[(dataset, model)]:
                    stats = results[(dataset, model)][config]
                    resolved = stats['R-R'] + stats['U-R']
                    sr = resolved / total * 100
                    sr_row += f" & {sr:.1f}"
                else:
                    sr_row += " & --"

        sr_row += " \\\\"
        lines.append(sr_row)

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table*}")

    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"\nLaTeX table saved to: {output_path}")


def generate_markdown_table(results: Dict, datasets: list, models: list, configs: list, output_path: Path):
    """Generate a markdown table with configs as rows and hierarchical dataset-model columns."""

    # Reorder datasets: swebench-pro first, then swebench
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    # Build list of dataset-model pairs that have data (ordered by dataset first)
    dataset_model_pairs = []
    for dataset in ordered_datasets:
        for model in models:
            if (dataset, model) in results and results[(dataset, model)]:
                dataset_model_pairs.append((dataset, model))

    if not dataset_model_pairs:
        print("No data found")
        return

    # Determine which configs are actually used
    used_configs = set()
    for (dataset, model), model_data in results.items():
        used_configs.update(model_data.keys())

    available_configs = [c for c in configs if c in used_configs]

    if not available_configs:
        print("No configs with data found")
        return

    lines = []
    lines.append("# Resolution Transition Matrix")
    lines.append("")
    lines.append("Comparing configurations against Vanilla actor baseline:")
    lines.append("- **RR**: Both resolved")
    lines.append("- **RU**: Baseline resolved only")
    lines.append("- **UR**: Config resolved only")
    lines.append("- **UU**: Both unresolved")
    lines.append("")
    lines.append("Incomplete instances are treated as unresolved.")
    lines.append("Total: 264 for SWE-bench Pro, 500 for SWE-bench Verified.")
    lines.append("")

    # Build table header with full names
    header = "| Config | Metric |"
    separator = "|--------|--------|"
    for dataset, model in dataset_model_pairs:
        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)
        model_display = MODEL_NAME_MAP.get(model, model)
        header += f" {dataset_display} / {model_display} |"
        separator += "---------|"

    lines.append(header)
    lines.append(separator)

    # Data rows
    for config in available_configs:
        config_display = CONFIG_NAME_MAP.get(config, config)

        # Four rows for each metric
        for metric in ['RR', 'RU', 'UR', 'UU']:
            if metric == 'RR':
                row = f"| {config_display} | {metric} |"
            else:
                row = f"|  | {metric} |"

            # Add data for each dataset-model pair
            for dataset, model in dataset_model_pairs:
                metric_key = f"{metric[0]}-{metric[1]}"  # Convert RR to R-R
                if (dataset, model) in results and config in results[(dataset, model)]:
                    stats = results[(dataset, model)][config]
                    row += f" {stats[metric_key]} |"
                else:
                    row += " -- |"

            lines.append(row)

        # Add separator between configs
        lines.append(separator)

    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Markdown table saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate resolution transition tables comparing configs against default baseline"
    )
    parser.add_argument("--datasets", nargs="+",
                       default=['swebench', 'swebench-pro'],
                       help="Datasets to analyze")
    parser.add_argument("--models", nargs="+",
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help="Models to analyze")
    parser.add_argument("--configs", nargs="+",
                       default=['sage', 'monitor', 'refiner-only', 'refiner'],
                       help="Configs to compare against default")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    parser.add_argument("--version", default='5', help="Version for refiner configs")
    parser.add_argument("--output-dir", default="analysis/tables",
                       help="Output directory for tables")

    args = parser.parse_args()

    base_dir = Path("/home/shuyang/Agent-Planner")
    output_dir = base_dir / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Computing resolution transitions...")
    print(f"Datasets: {args.datasets}")
    print(f"Models: {args.models}")
    print(f"Configs: {args.configs}\n")

    # Collect data
    results = {}

    for dataset in args.datasets:
        agent_dir = base_dir / "SWE-agent" if dataset == "swebench" else base_dir / "SWE-bench_Pro-os" / "SWE-agent"

        for model in args.models:
            print(f"Processing {DATASET_NAME_MAP.get(dataset, dataset)} - {MODEL_NAME_MAP.get(model, model)}:")

            # Load baseline (default) config - only resolved IDs
            baseline_resolved = load_report(
                agent_dir, 'default', dataset, model, args.run_id, args.version
            )

            total = 264 if dataset == 'swebench-pro' else 500

            if baseline_resolved is None:
                print(f"  No baseline data found, skipping")
                continue

            print(f"  Baseline (Vanilla actor): {len(baseline_resolved)}/{total} resolved")

            model_results = {}

            for config in args.configs:
                # Load config - only resolved IDs (None if no report exists)
                config_resolved = load_report(
                    agent_dir, config, dataset, model, args.run_id, args.version
                )

                if config_resolved is None:
                    print(f"  {CONFIG_NAME_MAP.get(config, config)}: No data found")
                    # Don't add to model_results - this will show as -- in table
                    continue

                # Compute transitions on all instances in dataset
                transitions = compute_transitions(
                    baseline_resolved, config_resolved, dataset
                )

                model_results[config] = transitions

                print(f"  {CONFIG_NAME_MAP.get(config, config)}: "
                      f"R-R={transitions['R-R']}, R-U={transitions['R-U']}, "
                      f"U-R={transitions['U-R']}, U-U={transitions['U-U']} "
                      f"({len(config_resolved)}/{total} resolved)")

            if model_results:
                results[(dataset, model)] = model_results

            print()

    if not results:
        print("No data collected. Exiting.")
        return

    # Generate tables
    latex_output = output_dir / "ru_transition.tex"
    markdown_output = output_dir / "ru_transition.md"

    generate_latex_table(results, args.datasets, args.models, args.configs, latex_output)
    generate_markdown_table(results, args.datasets, args.models, args.configs, markdown_output)

    print(f"\nTables generated successfully!")


if __name__ == "__main__":
    main()
