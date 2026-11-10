"""
Select consistent-outcome instances for SWE-bench-Pro.

For each model, compare two vanilla (default) run reports and keep the instances
whose outcome agrees across both runs -- i.e. resolved in both runs, or
unresolved in both runs. Instances missing from either run (no outcome) or that
flip between runs are dropped, since only agreeing instances give a stable
baseline to compare monitor / refiner configs against.

Mirrors the consistency logic in analysis/non-determinism_analysis.py, but
restricted to the two-run intersection and writing the surviving instances to a
per-model YAML subset of sampled_instances.yaml that the rerun_*.sh scripts read.

Default config/report layout (swebench-pro):
  reports/default/<dataset>/<lang>/<model>/run-<id>/eval_results.json   # {instance_id: bool}
  script/sample-data/samples/<lang>/<dataset>/sampled_instances.yaml    # full sample

Output:
  script/sample-data/samples/<lang>/<dataset>/consistent/<model>/sampled_instances.yaml
"""
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml

# script/sample-data/select_consistent_outcome_instances.py -> SWE-agent/
AGENT_DIR = Path(__file__).resolve().parents[2]


def load_eval_results(agent_dir: Path, config: str, dataset: str, lang: str,
                      model: str, run_id: int) -> Dict[str, bool]:
    """Load {instance_id: resolved} from a run's eval_results.json, or {} if absent."""
    report_path = (agent_dir / "reports" / config / dataset / lang / model
                   / f"run-{run_id}" / "eval_results.json")
    if not report_path.exists():
        return {}
    with open(report_path, "r") as f:
        return json.load(f)


def load_sampled_instances(agent_dir: Path, dataset: str, lang: str) -> List[dict]:
    """Load the full sampled_instances.yaml list for a dataset/language."""
    sampled_file = (agent_dir / "script" / "sample-data" / "samples"
                    / lang / dataset / "sampled_instances.yaml")
    with open(sampled_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def select_consistent(run1: Dict[str, bool], run2: Dict[str, bool]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Given two {instance_id: resolved} maps, partition their common instances.

    Returns (both_resolved, both_unresolved, inconsistent) where consistent =
    both_resolved | both_unresolved. Instances absent from either run are excluded.
    """
    common = set(run1) & set(run2)
    both_resolved = {i for i in common if run1[i] and run2[i]}
    both_unresolved = {i for i in common if not run1[i] and not run2[i]}
    inconsistent = common - both_resolved - both_unresolved
    return both_resolved, both_unresolved, inconsistent


def write_subset(agent_dir: Path, dataset: str, lang: str, model: str,
                 sampled: List[dict], keep_ids: Set[str]) -> Path:
    """Write the sampled entries whose instance_id is in keep_ids, preserving order/format."""
    out_dir = (agent_dir / "script" / "sample-data" / "samples"
               / lang / dataset / "consistent" / model)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "sampled_instances.yaml"

    subset = [inst for inst in sampled if inst.get("instance_id") in keep_ids]
    with open(out_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(subset, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return out_file


def discover_models(agent_dir: Path, config: str, dataset: str, lang: str,
                    run_ids: Tuple[int, int]) -> List[str]:
    """Find models that have an eval_results.json for both requested runs."""
    base = agent_dir / "reports" / config / dataset / lang
    if not base.exists():
        return []
    models = []
    for model_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if all((model_dir / f"run-{rid}" / "eval_results.json").exists() for rid in run_ids):
            models.append(model_dir.name)
    return models


def process_model(agent_dir: Path, config: str, dataset: str, lang: str,
                  model: str, run_ids: Tuple[int, int], sampled: List[dict]) -> None:
    run1 = load_eval_results(agent_dir, config, dataset, lang, model, run_ids[0])
    run2 = load_eval_results(agent_dir, config, dataset, lang, model, run_ids[1])

    print(f"\n{'='*70}\nModel: {model}\n{'='*70}")
    if not run1 or not run2:
        print(f"  Skipping: missing run-{run_ids[0] if not run1 else run_ids[1]} eval_results.json")
        return

    both_resolved, both_unresolved, inconsistent = select_consistent(run1, run2)
    consistent = both_resolved | both_unresolved
    common = both_resolved | both_unresolved | inconsistent

    print(f"  run-{run_ids[0]}: {len(run1)} graded, {sum(run1.values())} resolved")
    print(f"  run-{run_ids[1]}: {len(run2)} graded, {sum(run2.values())} resolved")
    print(f"  Common (graded in both): {len(common)}")
    print(f"  Both resolved:   {len(both_resolved)}")
    print(f"  Both unresolved: {len(both_unresolved)}")
    print(f"  Consistent:      {len(consistent)} "
          f"({len(consistent)/len(common)*100:.1f}% of common)" if common else "  Consistent: 0")
    print(f"  Inconsistent (dropped): {len(inconsistent)}")

    out_file = write_subset(agent_dir, dataset, lang, model, sampled, consistent)
    written = len(yaml.safe_load(open(out_file, encoding="utf-8")) or [])
    print(f"  Wrote {written} instances -> {out_file.relative_to(agent_dir)}")


def main():
    parser = argparse.ArgumentParser(
        description="Select instances with consistent outcomes across two vanilla runs.")
    parser.add_argument("--dataset", default="swebench-pro", help="Dataset name")
    parser.add_argument("--lang", default="python", help="Language subset")
    parser.add_argument("--config", default="default", help="Baseline config to read runs from")
    parser.add_argument("--run-ids", type=int, nargs=2, default=(1, 2),
                        metavar=("RUN_A", "RUN_B"), help="The two run ids to compare")
    parser.add_argument("--models", nargs="+", default=None,
                        help="Models to process (default: auto-discover models with both runs)")
    args = parser.parse_args()

    run_ids = tuple(args.run_ids)
    models = args.models or discover_models(AGENT_DIR, args.config, args.dataset, args.lang, run_ids)
    if not models:
        print(f"No models with both run-{run_ids[0]} and run-{run_ids[1]} under "
              f"reports/{args.config}/{args.dataset}/{args.lang}")
        return

    print(f"Dataset: {args.dataset} | Lang: {args.lang} | Config: {args.config} | "
          f"Runs: {run_ids[0]} vs {run_ids[1]}")
    print(f"Models: {', '.join(models)}")

    sampled = load_sampled_instances(AGENT_DIR, args.dataset, args.lang)
    print(f"Full sample size: {len(sampled)}")

    for model in models:
        process_model(AGENT_DIR, args.config, args.dataset, args.lang, model, run_ids, sampled)


if __name__ == "__main__":
    main()
