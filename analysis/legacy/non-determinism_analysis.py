"""
Get two default runs (run-id 1 and 2), take the instances with consistent results (i.e. both resolved or both unresolved in the two runs). And compare the success rate with the config on this subset.
dataset default to swebench-pro. model default to deepseek-chat-v3-0324.
"""
import json
import argparse
from pathlib import Path
from typing import Set, Dict, List


def load_report(agent_dir: Path, config: str, dataset: str, model: str, run_id: int, version: str = None) -> Set[str]:
    """Load resolved instance IDs from report file (from collect_pattern_resolution.py)."""
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


def load_report_map(agent_dir: Path, config: str, dataset: str, model: str, run_id: int, version: str = None) -> Dict[str, bool]:
    """Load the full {instance_id: resolved_bool} map for a run.

    Only meaningful for swebench-pro (eval_results.json stores a bool per graded
    instance). For swebench we only have resolved_ids lists -- no graded set and
    no explicit unresolved outcomes -- so this returns {} and callers fall back
    to the all-instances universe. Returns {} if the report is absent.
    """
    if dataset != 'swebench-pro':
        return {}
    dataset_path = f"{dataset}/python"
    if config in ['refiner', 'refiner-only'] and version:
        report_path = agent_dir / "reports" / config / f"version-{version}" / dataset_path / model / f"run-{run_id}" / "eval_results.json"
    else:
        report_path = agent_dir / "reports" / config / dataset_path / model / f"run-{run_id}" / "eval_results.json"

    if report_path.exists():
        try:
            with open(report_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading report {report_path}: {e}")
    return {}


def get_all_instances(dataset: str) -> Set[str]:
    """Get all instance IDs for a dataset."""
    if dataset == 'swebench':
        from datasets import load_dataset
        swe_bench = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
        return set(swe_bench['instance_id'])
    elif dataset == 'swebench-pro':
        # Load from sampled instances file
        import yaml
        script_dir = Path(__file__).parent.parent
        sampled_file = script_dir / "SWE-bench_Pro-os" / "SWE-agent" / "script" / "sample-data" / "samples" / "python" / "swebench-pro" / "sampled_instances.yaml"
        with open(sampled_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return set(item['instance_id'] for item in data if 'instance_id' in item)
    else:
        raise ValueError(f"Unknown dataset: {dataset}")


def analyze_non_determinism(dataset: str = 'swebench',
                            model: str = 'deepseek-chat-v3-0324',
                            baseline_config: str = 'default',
                            comparison_config: str = 'refiner',
                            configs_to_compare: List[str] = None,
                            version: str = '5'):
    """
    Analyze non-determinism by comparing two runs of baseline config.
    Then evaluate all configs on the consistent subset.
    """
    script_dir = Path(__file__).parent.parent

    # Determine agent directory
    if dataset == 'swebench':
        agent_dir = script_dir / "SWE-agent"
    elif dataset == 'swebench-pro':
        agent_dir = script_dir / "SWE-bench_Pro-os" / "SWE-agent"
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    if configs_to_compare is None:
        configs_to_compare = ['sage', 'monitor', 'refiner-only', 'refiner']

    print(f"\n{'='*70}")
    print(f"Non-Determinism Analysis")
    print(f"{'='*70}")
    print(f"Dataset: {dataset}")
    print(f"Model: {model}")
    print(f"Baseline config: {baseline_config}")
    print(f"Configs to compare: {configs_to_compare}")
    print(f"Detailed analysis config: {comparison_config}")
    print(f"Version: {version}")
    print(f"{'='*70}\n")

    # Load baseline runs. Prefer the full {id: bool} map so the consistent subset
    # is built exactly like select_consistent_outcome_instances.py (which generated
    # the subset the monitor/refiner-only reruns were actually run on): only
    # instances GRADED in BOTH runs with an agreeing outcome. Falling back to the
    # all-instances universe (swebench) would wrongly treat ungraded instances as
    # "both unresolved" and inflate the subset.
    print(f"Loading {baseline_config} run-1...")
    run1_map = load_report_map(agent_dir, baseline_config, dataset, model, run_id=1, version=version)
    baseline_run1 = load_report(agent_dir, baseline_config, dataset, model, run_id=1, version=version)
    print(f"  Resolved: {len(baseline_run1)}" + (f" (graded: {len(run1_map)})" if run1_map else ""))

    print(f"Loading {baseline_config} run-2...")
    run2_map = load_report_map(agent_dir, baseline_config, dataset, model, run_id=2, version=version)
    baseline_run2 = load_report(agent_dir, baseline_config, dataset, model, run_id=2, version=version)
    print(f"  Resolved: {len(baseline_run2)}" + (f" (graded: {len(run2_map)})" if run2_map else ""))

    if not baseline_run1 or not baseline_run2:
        print("\nError: Missing baseline data for one or both runs")
        return

    # Get all instances
    all_instances = get_all_instances(dataset)
    print(f"\nTotal instances in dataset: {len(all_instances)}")

    # Find consistent instances
    if run1_map and run2_map:
        # Mirror select_consistent_outcome_instances.py: restrict to graded-in-both.
        common = set(run1_map) & set(run2_map)
        both_resolved = {i for i in common if run1_map[i] and run2_map[i]}
        both_unresolved = {i for i in common if not run1_map[i] and not run2_map[i]}
    else:
        # swebench fallback: no per-instance grade map, use the full dataset universe.
        both_resolved = baseline_run1 & baseline_run2
        both_unresolved = (all_instances - baseline_run1) & (all_instances - baseline_run2)
    consistent_instances = both_resolved | both_unresolved

    inconsistent_instances = all_instances - consistent_instances

    print(f"\nConsistency Analysis ({baseline_config}):")
    print(f"  Both resolved: {len(both_resolved)}")
    print(f"  Both unresolved: {len(both_unresolved)}")
    print(f"  Consistent total: {len(consistent_instances)} ({len(consistent_instances)/len(all_instances)*100:.1f}%)")
    print(f"  Inconsistent: {len(inconsistent_instances)} ({len(inconsistent_instances)/len(all_instances)*100:.1f}%)")

    # Load all configs to compare
    print(f"\nLoading configs for comparison:")
    config_results = {}
    config_graded = {}  # instances each config was actually evaluated on (its run scope)

    for config in configs_to_compare:
        print(f"  Loading {config} run-2...")
        resolved = load_report(agent_dir, config, dataset, model, run_id=2, version=version)
        cfg_map = load_report_map(agent_dir, config, dataset, model, run_id=2, version=version)

        # if config == 'refiner':
        #     resolved = load_report(agent_dir, config, dataset, model, run_id=1, version=6)
        #     cfg_map = load_report_map(agent_dir, config, dataset, model, run_id=1, version=6)
        if resolved:
            graded = set(cfg_map) if cfg_map else all_instances
            print(f"    Resolved: {len(resolved)} (graded: {len(graded)})")
            config_results[config] = resolved
            config_graded[config] = graded
        else:
            print(f"    No data found")

    if not config_results:
        print(f"\nError: No config data found")
        return

    # Compute success rates on consistent subset
    baseline_consistent_resolved = both_resolved

    print(f"\n{'='*70}")
    print(f"Results on Consistent Subset ({len(consistent_instances)} instances)")
    print(f"{'='*70}")

    # Print table header
    print(f"\n{'Config':<20} {'Resolved':>10} {'Success Rate':>15} {'Available':>12}")
    print(f"{'-'*60}")

    # Baseline row
    print(f"{baseline_config:<20} {len(baseline_consistent_resolved):>10} "
          f"{len(baseline_consistent_resolved)/len(consistent_instances)*100:>14.2f}% {'Yes':>12}")

    # Other config rows
    for config in configs_to_compare:
        if config in config_results:
            resolved_on_consistent = config_results[config] & consistent_instances
            success_rate = len(resolved_on_consistent) / len(consistent_instances) * 100
            print(f"{config:<20} {len(resolved_on_consistent):>10} {success_rate:>14.2f}% {'Yes':>12}")
        else:
            print(f"{config:<20} {'-':>10} {'-':>15} {'No':>12}")

    # Compare the consistent-subset rate against each config's rate over its own
    # run scope (the instances it was actually evaluated on). For configs rerun
    # ONLY on the consistent subset (monitor, refiner-only), the run scope IS the
    # subset, so the two columns agree -- any divergence here is the bug this table
    # is meant to expose. Dividing by all_instances (266) instead would make those
    # configs look artificially weak since they were never run on the full set.
    print(f"\n{'='*70}")
    print(f"Run-scope Rate vs Consistent-subset Rate")
    print(f"{'='*70}")
    print(f"\n{'Config':<20} {'Run Scope':>12} {'Scope Rate':>12} {'Consistent':>12}")
    print(f"{'-'*58}")

    # Scope rate is a run-2 metric for every config, so the baseline uses run-2
    # too (run-1 is only used, together with run-2, to define the consistent subset).
    baseline_scope = len(run2_map) if run2_map else len(all_instances)
    baseline_full_rate = len(baseline_run2) / baseline_scope * 100
    baseline_consistent_rate = len(baseline_consistent_resolved) / len(consistent_instances) * 100
    print(f"{baseline_config:<20} {baseline_scope:>12} {baseline_full_rate:>11.2f}% "
          f"{baseline_consistent_rate:>11.2f}%")

    for config in configs_to_compare:
        if config in config_results:
            scope = len(config_graded[config])
            full_rate = len(config_results[config]) / scope * 100
            consistent_resolved = config_results[config] & consistent_instances
            consistent_rate = len(consistent_resolved) / len(consistent_instances) * 100
            print(f"{config:<20} {scope:>12} {full_rate:>11.2f}% {consistent_rate:>11.2f}%")

    # Detailed analysis for comparison_config (if available)
    if comparison_config in config_results:
        comparison_resolved = config_results[comparison_config]
        comparison_consistent_resolved = comparison_resolved & consistent_instances

        # Additional analysis: unique resolutions
        unique_to_comparison = comparison_consistent_resolved - baseline_consistent_resolved
        unique_to_baseline = baseline_consistent_resolved - comparison_consistent_resolved
        overlap = baseline_consistent_resolved & comparison_consistent_resolved

        print(f"\n{'='*70}")
        print(f"Resolution Overlap: {baseline_config} vs {comparison_config}")
        print(f"{'='*70}")
        print(f"Both configs resolved: {len(overlap)}")
        print(f"Only {comparison_config} resolved: {len(unique_to_comparison)}")
        print(f"Only {baseline_config} resolved: {len(unique_to_baseline)}")

        # Analysis on subsets: resolved vs unresolved by baseline
        comparison_resolved_on_baseline_resolved = comparison_resolved & both_resolved
        comparison_resolved_on_baseline_unresolved = comparison_resolved & both_unresolved

        print(f"\n{'='*70}")
        print(f"{comparison_config} Performance by Baseline Result")
        print(f"{'='*70}")
        print(f"On instances {baseline_config} resolved (both runs):")
        print(f"  Total: {len(both_resolved)}")
        print(f"  {comparison_config} also resolved: {len(comparison_resolved_on_baseline_resolved)}")
        print(f"  Resolve rate: {len(comparison_resolved_on_baseline_resolved)/len(both_resolved)*100:.2f}%")

        print(f"\nOn instances {baseline_config} failed (both runs):")
        print(f"  Total: {len(both_unresolved)}")
        print(f"  {comparison_config} resolved: {len(comparison_resolved_on_baseline_unresolved)}")
        print(f"  Resolve rate: {len(comparison_resolved_on_baseline_unresolved)/len(both_unresolved)*100:.2f}%")


def main():
    parser = argparse.ArgumentParser(description='Analyze non-determinism and compare configs on consistent subset')
    parser.add_argument('--dataset', type=str, default='swebench-pro',
                       choices=['swebench', 'swebench-pro'],
                       help='Dataset name')
    parser.add_argument('--model', type=str, default='deepseek-chat-v3-0324',
                       help='Model name')
    parser.add_argument('--baseline', type=str, default='default',
                       help='Baseline config (default: default)')
    parser.add_argument('--configs', nargs='+',
                       default=['sage', 'monitor', 'refiner-only', 'refiner'],
                       help='Configs to compare (default: sage monitor refiner-only refiner)')
    parser.add_argument('--comparison', type=str, default='refiner',
                       help='Config for detailed U-R analysis (default: refiner)')
    parser.add_argument('--version', type=str, default='5',
                       help='Version for refiner configs')

    args = parser.parse_args()

    analyze_non_determinism(
        dataset=args.dataset,
        model=args.model,
        baseline_config=args.baseline,
        comparison_config=args.comparison,
        configs_to_compare=args.configs,
        version=args.version
    )


if __name__ == "__main__":
    main()