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


def has_planner_trigger(agent_dir: Path, config: str, dataset: str, model: str,
                        instance_id: str, run_id: int, version: str = '5') -> bool:
    """
    Check if an instance has a planner.json file (i.e., was triggered).

    Returns:
        True if planner.json exists, False otherwise
    """
    # Configs without planner: all instances are considered "triggered"
    if config in ['default', 'sage']:
        return True

    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # Map config to trajectory path
    if config in ['refiner', 'refiner-only'] and version:
        planner_path = (agent_dir / "trajectories" / config / f"version-{version}" /
                      dataset_path / model / f"run-{run_id}" / instance_id / f"{instance_id}.planner.json")
    else:
        planner_path = (agent_dir / "trajectories" / config / dataset_path /
                      model / f"run-{run_id}" / instance_id / f"{instance_id}.planner.json")

    return planner_path.exists()


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


def get_all_instance_ids(agent_dir: Path, dataset: str, model: str, run_id: int) -> Set[str]:
    """
    Get all instance IDs for a dataset from the default config report.

    Returns:
        Set of all instance IDs
    """
    dataset_path = dataset if dataset != 'swebench-pro' else f"{dataset}/python"

    # For swebench-pro, get from eval_results.json
    if dataset == 'swebench-pro':
        report_path = agent_dir / "reports" / "default" / dataset_path / model / f"run-{run_id}" / "eval_results.json"
        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    data = json.load(f)
                    return set(data.keys())
            except Exception as e:
                print(f"Warning: Error loading {report_path}: {e}")

    # For swebench, get from report json
    reports_dir = agent_dir / "reports" / "default" / dataset_path / model
    if reports_dir.exists():
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
                        resolved = set(data.get('resolved_ids', []))
                        unresolved = set(data.get('unresolved_ids', []))
                        return resolved | unresolved
                except Exception as e:
                    print(f"Warning: Error loading {report_path}: {e}")

    # Fallback to full dataset size
    return set()


def compute_transitions(baseline_resolved: Set[str], config_resolved: Set[str],
                       triggered_instances: Set[str], dataset: str) -> Dict[str, int]:
    """
    Compute R-R, R-U, U-R, U-U transitions on triggered instances only.
    Incomplete instances are treated as unresolved.

    Args:
        baseline_resolved: Resolved IDs from baseline (default) config
        config_resolved: Resolved IDs from comparison config
        triggered_instances: Instance IDs that have planner.json (triggered)
        dataset: Dataset name (for reference)

    Returns:
        Dict with counts for R-R, R-U, U-R, U-U
    """
    # Only consider triggered instances
    r_r = len(triggered_instances & baseline_resolved & config_resolved)
    r_u = len(triggered_instances & baseline_resolved - config_resolved)
    u_r = len(triggered_instances & config_resolved - baseline_resolved)
    u_u = len(triggered_instances - baseline_resolved - config_resolved)

    total = r_r + r_u + u_r + u_u

    return {
        'R-R': r_r,
        'R-U': r_u,
        'U-R': u_r,
        'U-U': u_u,
        'total': total
    }


def generate_latex_table(results: Dict, datasets: list, models: list, configs: list, output_path: Path):
    """Generate a compact LaTeX table with dataset-method rows and metric-model columns."""

    # Reorder datasets: swebench-pro first, then swebench
    ordered_datasets = ['swebench-pro', 'swebench']
    ordered_datasets = [d for d in ordered_datasets if d in datasets]

    # Determine which configs are actually used for each dataset
    dataset_configs = {}
    for dataset in ordered_datasets:
        dataset_configs[dataset] = []
        for config in configs:
            # Check if this config has data for any model in this dataset
            has_data = False
            for model in models:
                if (dataset, model) in results and config in results[(dataset, model)]:
                    has_data = True
                    break
            if has_data:
                dataset_configs[dataset].append(config)

    if not dataset_configs or all(not cs for cs in dataset_configs.values()):
        print("No data found")
        return

    # Determine which models actually have data
    models_with_data = []
    for model in models:
        has_data = False
        for dataset in ordered_datasets:
            if (dataset, model) in results and results[(dataset, model)]:
                has_data = True
                break
        if has_data:
            models_with_data.append(model)

    num_models = len(models_with_data)

    # Model abbreviation mapping
    model_abbrev_map = {
        'deepseek-chat-v3-0324': 'DS',
        'gemini-2.5-flash': 'GF',
        'minimax-m2.5': 'MM'
    }

    lines = []
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append("\\caption{Resolution Transition Matrix comparing methods against Vanilla baseline. "
                 "R$\\rightarrow$U: baseline resolved only (regression), U$\\rightarrow$R: compared method resolved only (improvement).}")
    lines.append("\\label{tab:ru_transition}")

    # Column spec: Dataset | Method | R→U (N models) | U→R (N models)
    col_spec = f"ll{'r' * num_models}{'r' * num_models}"
    lines.append(f"\\begin{{tabular}}{{@{{}}{col_spec}@{{}}}}")
    lines.append("\\toprule")

    # Two-level header
    # Level 1: Metrics (R→U and U→R spanning N columns each)
    header1 = "\\textbf{Dataset} & \\textbf{Method}"
    header1 += f" & \\multicolumn{{{num_models}}}{{c}}{{\\textbf{{R$\\rightarrow$U $\\downarrow$}}}}"
    header1 += f" & \\multicolumn{{{num_models}}}{{c}}{{\\textbf{{U$\\rightarrow$R $\\uparrow$}}}}"
    header1 += " \\\\"
    lines.append(header1)

    # Level 2: Model abbreviations
    header2 = " & "
    for _ in range(2):  # Two metric groups
        for model in models_with_data:
            abbrev = model_abbrev_map.get(model, model[:3].upper())
            header2 += f" & \\textbf{{{abbrev}}}"
    header2 += " \\\\"
    lines.append(header2)
    lines.append("\\midrule")

    # Data rows - grouped by dataset
    first_dataset = True
    for dataset in ordered_datasets:
        if dataset not in dataset_configs or not dataset_configs[dataset]:
            continue

        dataset_display = DATASET_NAME_MAP.get(dataset, dataset)
        configs_in_dataset = dataset_configs[dataset]

        # First row of dataset shows dataset name with rowspan
        for i, config in enumerate(configs_in_dataset):
            config_display = CONFIG_NAME_MAP.get(config, config)

            row = ""
            if i == 0:
                # First config row shows dataset name
                row = f"\\multirow{{{len(configs_in_dataset)}}}{{*}}{{\\textbf{{{dataset_display}}}}} & {config_display}"
            else:
                row = f" & {config_display}"

            # Add R-U values for all models
            for model in models_with_data:
                if (dataset, model) in results and config in results[(dataset, model)]:
                    stats = results[(dataset, model)][config]
                    row += f" & {stats['R-U']}"
                else:
                    row += " & --"

            # Add U-R values for all models
            for model in models_with_data:
                if (dataset, model) in results and config in results[(dataset, model)]:
                    stats = results[(dataset, model)][config]
                    row += f" & {stats['U-R']}"
                else:
                    row += " & --"

            row += " \\\\"
            lines.append(row)

        # Add separator between datasets (but not after the last one)
        if dataset != ordered_datasets[-1]:
            lines.append("\\midrule")

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

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
    lines.append("- **RU**: Baseline resolved only (regression)")
    lines.append("- **UR**: Config resolved only (improvement)")
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

        # Two rows for each metric
        for metric in ['RU', 'UR']:
            if metric == 'RU':
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
    parser.add_argument("--all", action='store_true',
                       help="Compute transitions for all instances (default: only triggered instances)")
    parser.add_argument("--output-dir", default="analysis/tables",
                       help="Output directory for tables")

    args = parser.parse_args()

    # Determine base directory (project root)
    base_dir = Path(__file__).parent.parent.parent
    output_dir = base_dir / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = "all instances" if args.all else "triggered instances only"
    print(f"Computing resolution transitions ({mode})...")
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

            if baseline_resolved is None:
                print(f"  No baseline data found, skipping")
                continue

            # Get all instance IDs for this dataset
            all_instances = get_all_instance_ids(agent_dir, dataset, model, args.run_id)
            if not all_instances:
                # Fallback: use resolved + unresolved from both configs
                all_instances = baseline_resolved.copy()

            print(f"  Baseline (Vanilla actor): {len(baseline_resolved)}/{len(all_instances)} resolved")

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

                # Find instances to compute transitions on
                if args.all:
                    # Use all instances
                    instances_to_compute = all_instances
                else:
                    # Find triggered instances (instances with planner.json)
                    # For configs without planner (sage), all instances are considered triggered
                    instances_to_compute = set()
                    for instance_id in all_instances:
                        if has_planner_trigger(agent_dir, config, dataset, model, instance_id, args.run_id, args.version):
                            instances_to_compute.add(instance_id)

                # Compute transitions
                transitions = compute_transitions(
                    baseline_resolved, config_resolved, instances_to_compute, dataset
                )

                model_results[config] = transitions

                total_computed = transitions['total']
                resolved_in_config = len(config_resolved & instances_to_compute)
                scope = f"Total: {total_computed}" if args.all else f"Triggered: {total_computed}"
                print(f"  {CONFIG_NAME_MAP.get(config, config)}: "
                      f"{scope}, "
                      f"R-U={transitions['R-U']}, U-R={transitions['U-R']} "
                      f"(Resolved: {resolved_in_config}/{total_computed})")

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
