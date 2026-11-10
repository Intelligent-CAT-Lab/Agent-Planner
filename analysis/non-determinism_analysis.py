"""Evaluate each configuration on its own deterministic subset of runs 1 and 2.

An instance is deterministic when it has the same outcome in both runs.
Success rate = both resolved / (both resolved + both unresolved).

SWE-bench Pro uses only instances graded in both reports. SWE-bench reports
provide resolved IDs only, so an existing report is assumed to cover the full
Verified test set; IDs absent from resolved_ids are treated as unresolved.
"""

import argparse
import json
from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ConfigResult:
    config: str
    run1: Dict[str, bool]
    run2: Dict[str, bool]
    both_resolved: Set[str]
    both_unresolved: Set[str]
    inconsistent: Set[str]

    @property
    def deterministic(self) -> Set[str]:
        return self.both_resolved | self.both_unresolved


def load_report_map(
    agent_dir: Path,
    config: str,
    dataset: str,
    model: str,
    run_id: int,
    version: Optional[str] = None,
    all_instances: Optional[Set[str]] = None,
) -> Dict[str, bool]:
    """Load explicit outcomes, raising on missing or invalid reports.

    An empty report is valid and is distinct from a missing report.
    """
    reports_dir = agent_dir / "reports" / config
    if config in {"refiner", "refiner-only"} and version:
        reports_dir /= f"version-{version}"

    if dataset == "swebench-pro":
        candidates = [
            reports_dir / dataset / "python" / model
            / f"run-{run_id}" / "eval_results.json"
        ]
    elif dataset == "swebench":
        reports_dir = reports_dir / dataset / model
        candidates = [
            reports_dir / name
            for name in (
                f"{model}.run_{run_id}.json",
                f"{model}.run-{run_id}.json",
                f"{model}.{run_id}.json",
            )
        ]
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    report_path = next((path for path in candidates if path.is_file()), None)
    if report_path is None:
        raise FileNotFoundError(
            "No report found; tried: " + ", ".join(str(p) for p in candidates)
        )
    with report_path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {report_path}")

    if dataset == "swebench-pro":
        if any(not isinstance(value, bool) for value in data.values()):
            raise ValueError(f"Expected boolean outcomes in {report_path}")
        return data

    if all_instances is None:
        raise ValueError("SWE-bench requires the full instance set")
    resolved_ids = data.get("resolved_ids")
    if not isinstance(resolved_ids, list) or any(
        not isinstance(instance_id, str) for instance_id in resolved_ids
    ):
        raise ValueError(f"Expected a resolved_ids list of strings in {report_path}")
    resolved = set(resolved_ids)
    if resolved - all_instances:
        raise ValueError(f"Report contains IDs outside the dataset: {report_path}")
    return {instance_id: instance_id in resolved for instance_id in all_instances}


def summarize_config(
    config: str, run1: Dict[str, bool], run2: Dict[str, bool]
) -> ConfigResult:
    """Partition instances observed in both runs by their paired outcomes."""
    common = run1.keys() & run2.keys()
    return ConfigResult(
        config=config,
        run1=run1,
        run2=run2,
        both_resolved={i for i in common if run1[i] and run2[i]},
        both_unresolved={i for i in common if not run1[i] and not run2[i]},
        inconsistent={i for i in common if run1[i] != run2[i]},
    )


def load_config_names() -> Dict[str, str]:
    """Load CONFIG_NAME_MAP; fall back to raw names if the file is absent."""
    name_map = Path(__file__).resolve().parent / "visualize" / "name_map.json"
    try:
        with name_map.open(encoding="utf-8") as stream:
            return json.load(stream).get("CONFIG_NAME_MAP", {})
    except (OSError, ValueError):
        return {}


def format_rate(resolved: int, total: int) -> str:
    return f"{resolved / total:.2%}" if total else "N/A"


def pass_k_metrics(
    result: ConfigResult, total: int, k: int = 2
) -> Tuple[float, float]:
    """Pass@k (Reach) and pass^k (Consistency) averaged over `total` instances.

    With n=2 runs per instance and c resolved, per-instance estimates are
    pass@k = 1 - C(n-c, k)/C(n, k) and pass^k = C(c, k)/C(n, k). `total` is a
    shared dividend across configs (the largest paired count); instances absent
    from a config's report count as c=0, so they add nothing to either sum but
    still occupy the denominator -- i.e. treated as both-unresolved.
    """
    n = 2
    denom = comb(n, k)
    if not total or denom == 0:
        return float("nan"), float("nan")
    reach = consistency = 0.0
    for instance in result.run1.keys() & result.run2.keys():
        c = int(result.run1[instance]) + int(result.run2[instance])
        reach += 1 - comb(n - c, k) / denom
        consistency += comb(c, k) / denom
    return reach / total, consistency / total


def format_fraction(value: float) -> str:
    return "N/A" if value != value else f"{value:.2%}"


def print_comparison(
    baseline: ConfigResult,
    comparison: ConfigResult,
    names: Dict[str, str],
) -> None:
    """Compare outcomes only where both configurations are deterministic."""
    base_name = names.get(baseline.config, baseline.config)
    comp_name = names.get(comparison.config, comparison.config)
    shared = baseline.deterministic & comparison.deterministic
    baseline_resolved = baseline.both_resolved & shared
    comparison_resolved = comparison.both_resolved & shared
    baseline_unresolved = baseline.both_unresolved & shared

    print(f"\nDetailed comparison: {base_name} vs {comp_name}")
    print(f"Intersection of their deterministic subsets: {len(shared)}")
    if not shared:
        print("No shared deterministic instances to compare.")
        return

    print(f"Both resolved: {len(baseline_resolved & comparison_resolved)}")
    print(f"Only {base_name} resolved: {len(baseline_resolved - comparison_resolved)}")
    print(f"Only {comp_name} resolved: {len(comparison_resolved - baseline_resolved)}")
    print(f"Both unresolved: {len(shared - baseline_resolved - comparison_resolved)}")
    for label, subset in (
        (f"{base_name} resolved", baseline_resolved),
        (f"{base_name} unresolved", baseline_unresolved),
    ):
        count = len(comparison_resolved & subset)
        print(
            f"{comp_name} success where {label}: "
            f"{count}/{len(subset)} ({format_rate(count, len(subset))})"
        )


def analyze_non_determinism(
    dataset: str = "swebench-pro",
    model: str = "deepseek-chat-v3-0324",
    baseline_config: str = "default",
    comparison_config: str = "refiner",
    configs_to_compare: Optional[List[str]] = None,
    version: str = "5",
    project_root: Optional[Path] = None,
) -> Dict[str, ConfigResult]:
    """Load two runs per config and report each config's own subset rate."""
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parent.parent
    if dataset == "swebench":
        from datasets import load_dataset

        agent_dir = root / "SWE-agent"
        all_instances = set(
            load_dataset("princeton-nlp/SWE-bench_Verified", split="test")["instance_id"]
        )
    elif dataset == "swebench-pro":
        agent_dir = root / "SWE-bench_Pro-os" / "SWE-agent"
        all_instances = None
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    if configs_to_compare is None:
        configs_to_compare = ["sage", "monitor", "refiner-only", "refiner"]
    configs = list(dict.fromkeys([baseline_config, *configs_to_compare]))
    names = load_config_names()
    results = {}
    errors = {}
    for config in configs:
        try:
            runs = [
                load_report_map(
                    agent_dir, config, dataset, model, run_id, version, all_instances
                )
                for run_id in (1, 2)
            ]
            results[config] = summarize_config(config, *runs)
        except (OSError, ValueError) as error:
            errors[config] = str(error)

    print(f"Dataset: {dataset} | Model: {model} | Refiner version: {version}")
    print("Each row uses that configuration's own deterministic subset (runs 1 and 2).")
    if dataset == "swebench":
        print("Assumption: each existing report covers the full Verified test set.")
    print(
        f"\n{'Config':<20} {'Subset':>7} {'Resolved':>9} {'Success':>9} "
        f"{'pass@2':>9} {'pass^2':>9}"
    )
    print("-" * 92)
    shared_total = max(
        (len(r.run1.keys() & r.run2.keys()) for r in results.values()), default=0
    )
    for config in configs:
        name = names.get(config, config)
        if config in errors:
            print(f"{name:<20} unavailable")
            continue
        result = results[config]
        size = len(result.deterministic)
        resolved = len(result.both_resolved)
        reach, consistency = pass_k_metrics(result, shared_total, k=2)
        print(
            f"{name:<20} {size:>7} {resolved:>9} "
            f"{format_rate(resolved, size):>9} "
            f"{format_fraction(reach):>9} {format_fraction(consistency):>9}"
        )
    print("Subset = both resolved + both unresolved; success = resolved / subset.")
    print("Subset membership and size can differ across configurations.")
    print(
        f"pass@2 (Reach) / pass^2 (Consistency) share one dividend "
        f"({shared_total}, the largest paired count); missing = unresolved (k=2, n=2)."
    )
    for config, error in errors.items():
        print(f"\n{names.get(config, config)}: {error}")

    if baseline_config in results and comparison_config in results:
        print_comparison(
            results[baseline_config], results[comparison_config], names
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="swebench-pro", choices=["swebench", "swebench-pro"])
    parser.add_argument("--model", default="deepseek-chat-v3-0324")
    parser.add_argument("--baseline", default="default", help="Config shown first and used for detailed comparison")
    parser.add_argument("--configs", nargs="+", default=["sage", "monitor", "refiner-only", "refiner"])
    parser.add_argument("--comparison", default="refiner", help="Detailed comparison config; must also be in --configs")
    parser.add_argument("--version", default="5", help="Version for refiner and refiner-only")
    parser.add_argument("--project-root", type=Path, help="Directory containing SWE-agent and SWE-bench_Pro-os (default: script's grandparent)")
    args = parser.parse_args()
    analyze_non_determinism(
        dataset=args.dataset,
        model=args.model,
        baseline_config=args.baseline,
        comparison_config=args.comparison,
        configs_to_compare=args.configs,
        version=args.version,
        project_root=args.project_root,
    )


if __name__ == "__main__":
    main()