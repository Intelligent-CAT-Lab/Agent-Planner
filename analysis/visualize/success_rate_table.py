#!/usr/bin/env python3
"""Generate the effectiveness table: success rate (%) and average cost per method.

Success rate uses a consistent full-dataset denominator from ``analysis.dataset_info``
(266 for SWE-bench Pro python, 500 for SWE-bench Verified), so configs with different
report coverage are comparable -- the fix for the inflated per-report rates (dividing
resolved by the ~262/264 graded instances instead of the full dataset). It is read
straight from the small report JSON, so it never touches trajectories.

Average cost keeps the existing computation (mean over loaded trajectories): it is reused
from ``analysis/cache/cost_analysis_data.json`` when present, and only falls back to
loading trajectories (via ``compare_cost_w_wo_planner``) on a cache miss.

Rows are grouped by model; success rate is shown with its signed delta vs Vanilla.
Defaults mirror the existing scripts: datasets [swebench-pro, swebench], models
[deepseek-chat-v3-0324, gemini-2.5-flash, minimax-m2.5]; configs default per dataset
([default, sage, monitor, refiner-only, refiner] for Pro; [default, refiner] for Verified).

Example:
  python analysis/visualize/success_rate_table.py
  python analysis/visualize/success_rate_table.py --datasets swebench-pro --models deepseek-chat-v3-0324
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Reuse the report/cost loaders and the canonical denominator from the sibling package.
ANALYSIS_DIR = Path(__file__).resolve().parents[1]
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))
from compare_cost_w_wo_planner import load_report, load_trajectory_data, compute_averages  # noqa: E402
from dataset_info import dataset_size  # noqa: E402

COST_CACHE = ANALYSIS_DIR / "cache" / "cost_analysis_data.json"


def load_name_maps():
    """Load name mappings from name_map.json."""
    with (Path(__file__).parent / "name_map.json").open() as stream:
        maps = json.load(stream)
    return maps["MODEL_NAME_MAP"], maps["DATASET_NAME_MAP"], maps["CONFIG_NAME_MAP"]


MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()

BASELINE = "default"  # Vanilla: the row deltas are measured against
# Default configs per dataset (override with --configs, applied to every dataset).
DATASET_CONFIGS = {
    "swebench-pro": ["default", "sage", "monitor", "refiner-only", "refiner"],
    "swebench": ["default", "refiner"],
}


def load_cost_cache() -> Dict:
    try:
        return json.loads(COST_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def agent_dir_for(root: Path, dataset: str, agent: str) -> Path:
    return root / agent if dataset == "swebench" else root / "SWE-bench_Pro-os" / agent


def success_rate(agent_dir: Path, dataset: str, model: str, config: str,
                 version: str, run_id: int) -> Optional[Dict]:
    """resolved / full-dataset size, from the report alone (no trajectories)."""
    resolved = load_report(agent_dir, config, dataset, model, run_id, version)
    denom = dataset_size(dataset)
    if not resolved and config != BASELINE and not agent_dir.exists():
        return None
    if not denom:
        return None
    return {"resolved": len(resolved), "denom": denom, "rate": len(resolved) / denom * 100}


def avg_cost(cache: Dict, agent_dir: Path, dataset: str, model: str, config: str,
             version: str, run_id: int) -> Optional[float]:
    """Average total cost: cached when present, else computed from trajectories."""
    cell = cache.get(str((dataset, model)), {}).get(config)
    if cell is not None:
        return cell.get("avg_total_cost",
                         cell.get("avg_executor_cost", 0.0) + cell.get("avg_refiner_cost", 0.0))
    ver = version if config in ("refiner", "refiner-only") else None
    if config == BASELINE:
        data = load_trajectory_data(agent_dir, dataset, model, BASELINE, runs=[run_id])
    else:
        data = load_trajectory_data(agent_dir, dataset, model, config, version=ver, run_id=run_id)
    if not data:
        return None
    print(f"    [cost cache miss] computed {config} from trajectories")
    return compute_averages(data)["avg_total_cost"]


def collect(root: Path, agent: str, datasets: List[str], models: List[str],
            configs_override: Optional[List[str]], version: str, run_id: int) -> Dict:
    """results[dataset][model][config] -> {rate, avg_cost, ...}; prints each cell."""
    cache = load_cost_cache()
    results: Dict = {}
    for dataset in datasets:
        configs = configs_override or DATASET_CONFIGS.get(dataset, ["default", "refiner"])
        agent_dir = agent_dir_for(root, dataset, agent)
        print(f"\n{DATASET_NAME_MAP.get(dataset, dataset)} (denominator = {dataset_size(dataset)}):")
        results[dataset] = {}
        for model in models:
            results[dataset][model] = {}
            for config in configs:
                sr = success_rate(agent_dir, dataset, model, config, version, run_id)
                cost = avg_cost(cache, agent_dir, dataset, model, config, version, run_id)
                results[dataset][model][config] = (
                    None if sr is None else {**sr, "avg_cost": cost})
                name = CONFIG_NAME_MAP.get(config, config)
                if sr is None:
                    print(f"  {MODEL_NAME_MAP.get(model, model):<16} {name:<16} no data")
                else:
                    cost_s = "N/A" if cost is None else f"${cost:.2f}"
                    print(f"  {MODEL_NAME_MAP.get(model, model):<16} {name:<16} "
                          f"{sr['resolved']}/{sr['denom']} = {sr['rate']:.2f}%  {cost_s}")
    return results


def _ordered_configs(configs_override, dataset):
    return configs_override or DATASET_CONFIGS.get(dataset, ["default", "refiner"])


def _rate_cell(stats, base_rate, best_rate, markup: str) -> str:
    """Formatted success-rate cell: value, bold-if-best, (signed delta vs Vanilla)."""
    val = f"{stats['rate']:.2f}"
    if best_rate is not None and stats["rate"] == best_rate:
        val = {"md": f"**{val}**", "tex": r"\textbf{%s}" % val}[markup]
    if base_rate is None:  # the Vanilla row itself
        return val
    delta = f"{stats['rate'] - base_rate:+.2f}"
    return f"{val} ({delta})" if markup == "md" else rf"{val} {{\scriptsize({delta})}}"


def _cost_cell(stats) -> str:
    return "N/A" if stats.get("avg_cost") is None else f"{stats['avg_cost']:.2f}"


def generate_markdown(results, datasets, models, configs_override, run_id) -> str:
    lines: List[str] = ["# Effectiveness: success rate and average cost", ""]
    for dataset in datasets:
        configs = _ordered_configs(configs_override, dataset)
        lines += [f"## {DATASET_NAME_MAP.get(dataset, dataset)} (run-{run_id})",
                  f"Success rate = resolved / {dataset_size(dataset)} (full dataset); "
                  f"delta vs {CONFIG_NAME_MAP.get(BASELINE, BASELINE)}.", ""]
        for model in models:
            cells = results.get(dataset, {}).get(model, {})
            base = cells.get(BASELINE)
            base_rate = base["rate"] if base else None
            best = max((c["rate"] for c in cells.values() if c), default=None)
            lines += [f"### {MODEL_NAME_MAP.get(model, model)}",
                      "| Method | Success Rate (%) | Average Cost |", "|---|---|---|"]
            for config in configs:
                stats = cells.get(config)
                method = CONFIG_NAME_MAP.get(config, config)
                if stats is None:
                    lines.append(f"| {method} | — | — |")
                else:
                    br = None if config == BASELINE else base_rate
                    lines.append(f"| {method} | {_rate_cell(stats, br, best, 'md')} "
                                 f"| {_cost_cell(stats)} |")
            lines.append("")
    return "\n".join(lines)


def generate_latex(results, datasets, models, configs_override, run_id) -> str:
    lines: List[str] = []
    for dataset in datasets:
        configs = _ordered_configs(configs_override, dataset)
        lines += [r"\begin{table}[t]", r"\centering",
                  rf"\caption{{Effectiveness on {DATASET_NAME_MAP.get(dataset, dataset)} "
                  rf"(success rate = resolved\,/\,{dataset_size(dataset)}).}}",
                  r"\begin{tabular}{lcc}", r"\toprule",
                  r"Method & Success Rate (\%) & Average Cost \\", r"\midrule"]
        for m_idx, model in enumerate(models):
            cells = results.get(dataset, {}).get(model, {})
            base = cells.get(BASELINE)
            base_rate = base["rate"] if base else None
            best = max((c["rate"] for c in cells.values() if c), default=None)
            if m_idx:
                lines.append(r"\midrule")
            lines.append(rf"\multicolumn{{3}}{{l}}{{\textit{{{MODEL_NAME_MAP.get(model, model)}}}}} \\")
            for config in configs:
                stats = cells.get(config)
                method = CONFIG_NAME_MAP.get(config, config)
                if config == "refiner":
                    method = r"\textsc{%s}" % method
                if stats is None:
                    lines.append(rf"{method} & -- & -- \\")
                else:
                    br = None if config == BASELINE else base_rate
                    lines.append(rf"{method} & {_rate_cell(stats, br, best, 'tex')} "
                                 rf"& {_cost_cell(stats)} \\")
        lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate the success-rate + average-cost effectiveness table")
    parser.add_argument("--datasets", nargs="+", default=["swebench-pro", "swebench"])
    parser.add_argument("--models", nargs="+",
                        default=["deepseek-chat-v3-0324", "gemini-2.5-flash", "minimax-m2.5"])
    parser.add_argument("--configs", nargs="+", default=None,
                        help="Override configs for every dataset (default: per-dataset).")
    parser.add_argument("--agent", default="SWE-agent")
    parser.add_argument("--version", default="5", help="Version for refiner/refiner-only")
    parser.add_argument("--run-id", type=int, default=1)
    parser.add_argument("--output-dir", default="analysis/tables")
    args = parser.parse_args()

    root = ANALYSIS_DIR.parent
    results = collect(root, args.agent, args.datasets, args.models,
                      args.configs, args.version, args.run_id)

    out_dir = root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    md = generate_markdown(results, args.datasets, args.models, args.configs, args.run_id)
    tex = generate_latex(results, args.datasets, args.models, args.configs, args.run_id)
    (out_dir / "success_rate.md").write_text(md, encoding="utf-8")
    (out_dir / "success_rate.tex").write_text(tex, encoding="utf-8")
    print(f"\nSaved: {out_dir / 'success_rate.md'}")
    print(f"Saved: {out_dir / 'success_rate.tex'}")


if __name__ == "__main__":
    main()
