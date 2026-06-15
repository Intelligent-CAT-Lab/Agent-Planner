"""
We compare the vanilla and refiner executions using the action prefix before the first refiner intervention. Each action is treated as an atomic token consisting of both the action type and its argument, making the comparison intentionally strict. This isolates divergence caused by execution non-determinism rather than by the refiner itself.
We report exact-prefix agreement and LCS similarity at the action level, and additionally compute compressed phase-sequence similarity as a coarse-grained control.
Low action similarity before the first intervention indicates that the refiner run had already diverged from the vanilla run prior to any intervention, while high phase similarity suggests that the divergence occurred mainly at the concrete action level rather than the strategic phase level.
Report the divergence analysis for R-R, R-U, U-R, and U-U pairs separately. (Get the statistics from analysis-results/comparison/detailed-analysis/{config}/{agent}-{model}-{dataset}-{config}-analysis.json)
The trajectory files can be found under {agent-dir}/trajectories/{config}/(version-{version} if config is refiner)/{dataset}(/python if the dataset is swebench-pro)/{model}/run-{run_id}/.
Input args:
  --agent (default: SWE-agent)
  --config (default: both monitor and refiner)
  --version (default: 5, only for refiner config)
  --run_id (default: 1)
Save the divergence statistics under analysis-results/comparison/divergence/{config}-{agent}-{model}-{dataset}-divergence.json
Example usage:
python analysis/analyze_divergence.py --model deepseek-chat-v3-0324 --config refiner --dataset swebench
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import re


def parse_langutory(lang: str) -> List[str]:
    """
    Parse langutory string to list of phases.
    E.g., 'L_navigate₃P₁V₁' -> ['L_navigate', 'L_navigate', 'L_navigate', 'P', 'V']
    """
    if not lang:
        return []

    subscript_map = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
    normalized = lang.translate(subscript_map)

    pattern = r'([A-Za-z_]+)(\d+)'
    matches = re.findall(pattern, normalized)

    result = []
    for phase, count in matches:
        result.extend([phase] * int(count))

    return result


def load_trajectory(traj_path: Path) -> Optional[List[Dict]]:
    """Load trajectory file and return list of trajectory steps."""
    try:
        with open(traj_path, 'r') as f:
            data = json.load(f)
            return data.get('trajectory', [])
    except Exception as e:
        print(f"Warning: Failed to load trajectory {traj_path}: {e}")
        return None


def extract_actions(trajectory: List[Dict]) -> List[str]:
    """
    Extract action sequences from trajectory.
    Each action is the concatenation of action type and its full argument.
    """
    actions = []
    for step in trajectory:
        action = step.get('action', '')
        if action:
            actions.append(action)
    return actions


def get_first_intervention_step(planner_stats: Dict, config: str) -> Optional[int]:
    """
    Get the step index of the first planner intervention from planner_stats.
    Returns None if no intervention found.
    """
    if not planner_stats or not planner_stats.get('interventions'):
        return None

    interventions = planner_stats['interventions']
    if not interventions:
        return None

    # Return the step of the first intervention
    return interventions[0].get('step')


def compute_lcs_length(seq1: List[str], seq2: List[str]) -> int:
    """Compute the length of longest common subsequence between two sequences."""
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i-1] == seq2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])

    return dp[m][n]


def compute_lcs_similarity(seq1: List[str], seq2: List[str]) -> float:
    """
    Compute LCS-based similarity between two sequences.
    Similarity = 2 * LCS / (len(seq1) + len(seq2))
    """
    if not seq1 and not seq2:
        return 1.0
    if not seq1 or not seq2:
        return 0.0

    lcs_len = compute_lcs_length(seq1, seq2)
    return 2 * lcs_len / (len(seq1) + len(seq2))


def compute_exact_prefix_match(seq1: List[str], seq2: List[str]) -> Tuple[int, float]:
    """
    Compute exact prefix match length and ratio.
    Returns: (prefix_length, prefix_ratio)
    """
    prefix_len = 0
    for i in range(min(len(seq1), len(seq2))):
        if seq1[i] == seq2[i]:
            prefix_len += 1
        else:
            break

    max_len = max(len(seq1), len(seq2))
    prefix_ratio = prefix_len / max_len if max_len > 0 else 1.0

    return prefix_len, prefix_ratio


def analyze_instance_divergence(
    instance_id: str,
    vanilla_traj_path: Path,
    planner_traj_path: Path,
    first_intervention_step: Optional[int],
    vanilla_lang: str = "",
    planner_lang: str = ""
) -> Optional[Dict]:
    """
    Analyze divergence for a single instance.
    Returns divergence metrics or None if analysis fails.
    """
    # Load trajectories
    vanilla_traj = load_trajectory(vanilla_traj_path)
    planner_traj = load_trajectory(planner_traj_path)

    if vanilla_traj is None or planner_traj is None:
        return None

    # Extract actions
    vanilla_actions = extract_actions(vanilla_traj)
    planner_actions = extract_actions(planner_traj)

    # Truncate planner at first intervention, vanilla at min(vanilla_length, first_intervention)
    if first_intervention_step is not None:
        planner_actions_prefix = planner_actions[:first_intervention_step]
        vanilla_actions_prefix = vanilla_actions[:min(len(vanilla_actions), first_intervention_step)]
        intervention_step_ratio = first_intervention_step / len(planner_actions) if planner_actions else 0
    else:
        planner_actions_prefix = planner_actions
        vanilla_actions_prefix = vanilla_actions
        intervention_step_ratio = None

    # Compute action-level metrics
    exact_prefix_len, exact_prefix_ratio = compute_exact_prefix_match(
        vanilla_actions_prefix, planner_actions_prefix
    )
    lcs_similarity = compute_lcs_similarity(vanilla_actions_prefix, planner_actions_prefix)

    # Extract phase sequences from langutory for coarse-grained comparison
    vanilla_phases_full = parse_langutory(vanilla_lang)
    planner_phases_full = parse_langutory(planner_lang)

    # Estimate phase cutoff proportionally to action cutoff
    if len(vanilla_actions) > 0 and len(planner_actions) > 0:
        vanilla_phase_cutoff_ratio = len(vanilla_actions_prefix) / len(vanilla_actions)
        planner_phase_cutoff_ratio = len(planner_actions_prefix) / len(planner_actions)

        vanilla_phase_cutoff = int(len(vanilla_phases_full) * vanilla_phase_cutoff_ratio)
        planner_phase_cutoff = int(len(planner_phases_full) * planner_phase_cutoff_ratio)

        vanilla_phases = vanilla_phases_full[:vanilla_phase_cutoff]
        planner_phases = planner_phases_full[:planner_phase_cutoff]
    else:
        vanilla_phases = vanilla_phases_full
        planner_phases = planner_phases_full

    # Compute phase-level similarity
    phase_lcs_similarity = compute_lcs_similarity(vanilla_phases, planner_phases)
    phase_prefix_len, phase_prefix_ratio = compute_exact_prefix_match(vanilla_phases, planner_phases)

    return {
        'instance_id': instance_id,
        'vanilla_action_count': len(vanilla_actions),
        'planner_action_count': len(planner_actions),
        # 'vanilla_comparison_length': len(vanilla_actions_prefix),
        # 'planner_comparison_length': len(planner_actions_prefix),
        'first_intervention_step': first_intervention_step,
        'intervention_step_ratio': intervention_step_ratio,
        'exact_prefix_length': exact_prefix_len,
        'exact_prefix_ratio': exact_prefix_ratio,
        'action_lcs_similarity': lcs_similarity,
        'vanilla_phase_count': len(vanilla_phases_full),
        'planner_phase_count': len(planner_phases_full),
        'vanilla_comparison_phase_count': len(vanilla_phases),
        'planner_comparison_phase_count': len(planner_phases),
        'phase_exact_prefix_length': phase_prefix_len,
        'phase_exact_prefix_ratio': phase_prefix_ratio,
        'phase_lcs_similarity': phase_lcs_similarity
    }


def aggregate_divergence_stats(divergence_results: List[Dict], include_details: bool = False) -> Dict:
    """Aggregate divergence statistics across instances."""
    if not divergence_results:
        return {}

    total = len(divergence_results)

    # Compute averages
    avg_exact_prefix_ratio = sum(r['exact_prefix_ratio'] for r in divergence_results) / total
    avg_action_lcs_similarity = sum(r['action_lcs_similarity'] for r in divergence_results) / total
    avg_phase_lcs_similarity = sum(r['phase_lcs_similarity'] for r in divergence_results) / total
    avg_phase_prefix_ratio = sum(r['phase_exact_prefix_ratio'] for r in divergence_results) / total

    # Count interventions
    has_intervention = [r for r in divergence_results if r['first_intervention_step'] is not None]
    if has_intervention:
        avg_intervention_step_ratio = sum(r['intervention_step_ratio'] for r in has_intervention) / len(has_intervention)
    else:
        avg_intervention_step_ratio = None

    # Count perfect matches
    perfect_prefix_count = sum(1 for r in divergence_results if r['exact_prefix_ratio'] == 1.0)
    perfect_prefix_ratio = perfect_prefix_count / total

    perfect_phase_prefix_count = sum(1 for r in divergence_results if r['phase_exact_prefix_ratio'] == 1.0)
    perfect_phase_prefix_ratio = perfect_phase_prefix_count / total

    # Distribution of prefix ratios
    prefix_ratio_bins = {
        '0.0-0.2': 0,
        '0.2-0.4': 0,
        '0.4-0.6': 0,
        '0.6-0.8': 0,
        '0.8-1.0': 0,
        '1.0': 0
    }

    for r in divergence_results:
        ratio = r['exact_prefix_ratio']
        if ratio == 1.0:
            prefix_ratio_bins['1.0'] += 1
        elif ratio >= 0.8:
            prefix_ratio_bins['0.8-1.0'] += 1
        elif ratio >= 0.6:
            prefix_ratio_bins['0.6-0.8'] += 1
        elif ratio >= 0.4:
            prefix_ratio_bins['0.4-0.6'] += 1
        elif ratio >= 0.2:
            prefix_ratio_bins['0.2-0.4'] += 1
        else:
            prefix_ratio_bins['0.0-0.2'] += 1

    result = {
        'total_instances': total,
        'instances_with_intervention': len(has_intervention),
        'avg_intervention_step_ratio': avg_intervention_step_ratio,
        'avg_exact_prefix_ratio': avg_exact_prefix_ratio,
        'avg_action_lcs_similarity': avg_action_lcs_similarity,
        'avg_phase_exact_prefix_ratio': avg_phase_prefix_ratio,
        'avg_phase_lcs_similarity': avg_phase_lcs_similarity,
        'perfect_prefix_count': perfect_prefix_count,
        'perfect_prefix_ratio': perfect_prefix_ratio,
        'perfect_phase_prefix_count': perfect_phase_prefix_count,
        'perfect_phase_prefix_ratio': perfect_phase_prefix_ratio,
        'prefix_ratio_distribution': prefix_ratio_bins
    }

    if include_details:
        result['details'] = divergence_results

    return result


def analyze_divergence(
    agent: str,
    model: str,
    dataset: str,
    config: str,
    version: Optional[int],
    run_id: int,
    analysis_dir: Path
) -> Dict:
    """
    Main divergence analysis function.
    Compares vanilla and planner trajectories before first intervention.
    """
    print(f"\nAnalyzing divergence for {config} configuration...")
    print(f"Agent: {agent}, Model: {model}, Dataset: {dataset}")

    # Determine agent directory based on dataset
    if dataset == "swebench-pro":
        agent_dir = Path("SWE-bench_Pro-os") / agent
    else:
        agent_dir = Path(agent)

    # Load detailed analysis JSON to get instance pairs and categories
    analysis_json_path = (
        analysis_dir / "comparison" / "detailed-analysis" / config /
        f"{agent}-{model}-{dataset}-{config}-analysis.json"
    )

    if not analysis_json_path.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_json_path}")

    with open(analysis_json_path, 'r') as f:
        analysis_data = json.load(f)

    # Setup trajectory paths
    if dataset == "swebench-pro":
        vanilla_traj_base = agent_dir / "trajectories" / "default" / dataset / "python"
        if config == "refiner":
            planner_traj_base = agent_dir / "trajectories" / config / f"version-{version}" / dataset / "python"
        else:
            planner_traj_base = agent_dir / "trajectories" / config / dataset / "python"
    else:
        vanilla_traj_base = agent_dir / "trajectories" / "default" / dataset
        if config == "refiner":
            planner_traj_base = agent_dir / "trajectories" / config / f"version-{version}" / dataset
        else:
            planner_traj_base = agent_dir / "trajectories" / config / dataset

    vanilla_traj_dir = vanilla_traj_base / model / f"run-{run_id}"
    planner_traj_dir = planner_traj_base / model / f"run-{run_id}"

    # Analyze divergence by category
    results_by_category = {}

    for category in ['R-R', 'R-U', 'U-R', 'U-U']:
        print(f"\nProcessing category {category}...")

        category_data = analysis_data.get('category_details', {}).get(category, {})
        instances = category_data.get('instances', [])

        if not instances:
            print(f"  No instances found for category {category}")
            continue

        divergence_results = []

        for inst in instances:
            instance_id = inst['instance_id']

            vanilla_traj_path = vanilla_traj_dir / instance_id / f"{instance_id}.traj"
            planner_traj_path = planner_traj_dir / instance_id / f"{instance_id}.traj"

            if not vanilla_traj_path.exists():
                print(f"  Warning: Vanilla trajectory not found for {instance_id}")
                continue

            if not planner_traj_path.exists():
                print(f"  Warning: Planner trajectory not found for {instance_id}")
                continue

            # Get langutory and intervention information from instance data
            vanilla_lang = inst.get('vanilla', {}).get('lang', '')
            planner_key = 'refiner' if config == 'refiner' else 'monitor'
            planner_data = inst.get(planner_key, {})
            planner_lang = planner_data.get('lang', '')

            # Get first intervention step from planner_stats
            planner_stats = planner_data.get('planner_stats', {})
            first_intervention_step = get_first_intervention_step(planner_stats, config)

            result = analyze_instance_divergence(
                instance_id,
                vanilla_traj_path,
                planner_traj_path,
                first_intervention_step,
                vanilla_lang,
                planner_lang
            )

            if result:
                divergence_results.append(result)

        if divergence_results:
            # Store with details for this category
            results_by_category[category] = aggregate_divergence_stats(divergence_results, include_details=True)
            print(f"  Analyzed {len(divergence_results)} instances")

    # Compute overall statistics (without details at overall level)
    all_divergence_results = []
    for cat_results in results_by_category.values():
        all_divergence_results.extend(cat_results.get('details', []))

    overall_stats = aggregate_divergence_stats(all_divergence_results, include_details=False) if all_divergence_results else {}

    return {
        'config': config,
        'agent': agent,
        'model': model,
        'dataset': dataset,
        'version': version,
        'run_id': run_id,
        'overall': overall_stats,
        'by_category': results_by_category
    }


def main():
    parser = argparse.ArgumentParser(
        description='Analyze trajectory divergence before first planner intervention'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name (default: SWE-agent)')
    parser.add_argument('--config', type=str, nargs='+', default=['monitor', 'refiner'],
                       help='Config(s) to analyze (default: monitor refiner)')
    parser.add_argument('--version', type=int, default=5,
                       help='Refiner version (default: 5, only for refiner config)')
    parser.add_argument('--run_id', type=int, default=1,
                       help='Run ID (default: 1)')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., deepseek-chat-v3-0324)')
    parser.add_argument('--dataset', type=str, required=True,
                       help='Dataset name (e.g., swebench, swebench-pro)')
    parser.add_argument('--analysis-dir', type=Path, default='analysis/analysis-results',
                       help='Analysis results directory (default: ./analysis-results)')

    args = parser.parse_args()

    # Set default analysis directory
    if args.analysis_dir is None:
        args.analysis_dir = Path('analysis-results')

    # Ensure output directory exists
    output_dir = args.analysis_dir / "comparison" / "divergence"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Analyze each configuration
    configs = args.config if isinstance(args.config, list) else [args.config]

    for config in configs:
        try:
            version = args.version if config == 'refiner' else None

            results = analyze_divergence(
                agent=args.agent,
                model=args.model,
                dataset=args.dataset,
                config=config,
                version=version,
                run_id=args.run_id,
                analysis_dir=args.analysis_dir
            )

            # Save results
            output_path = output_dir / f"{config}-{args.agent}-{args.model}-{args.dataset}-divergence.json"
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2)

            print(f"\n✓ Divergence analysis saved to: {output_path}")

            # Print summary
            print("\n" + "="*80)
            print(f"DIVERGENCE SUMMARY - {config.upper()}")
            print("="*80)

            overall = results.get('overall', {})
            if overall:
                print(f"\nTotal: {overall.get('total_instances', 0)} instances")
                if overall.get('avg_intervention_step_ratio') is not None:
                    print(f"Intervention timing: {overall.get('avg_intervention_step_ratio', 0):.1%} of trajectory on average")

                print(f"\nAction-level divergence before first intervention:")
                print(f"  Exact prefix: {overall.get('avg_exact_prefix_ratio', 0):.3f} | LCS: {overall.get('avg_action_lcs_similarity', 0):.3f}")
                print(f"  Perfect matches: {overall.get('perfect_prefix_count', 0)} ({overall.get('perfect_prefix_ratio', 0)*100:.1f}%)")

                print(f"\nPhase-level divergence before first intervention:")
                print(f"  Exact prefix: {overall.get('avg_phase_exact_prefix_ratio', 0):.3f} | LCS: {overall.get('avg_phase_lcs_similarity', 0):.3f}")
                print(f"  Perfect matches: {overall.get('perfect_phase_prefix_count', 0)} ({overall.get('perfect_phase_prefix_ratio', 0)*100:.1f}%)")

            by_category = results.get('by_category', {})
            if by_category:
                print("\nBy Category (Action exact prefix | Action LCS | Phase exact prefix | Phase LCS):")
                for category in ['R-R', 'R-U', 'U-R', 'U-U']:
                    cat_results = by_category.get(category)
                    if cat_results:
                        print(f"  {category}: n={cat_results.get('total_instances', 0):3d} | "
                              f"{cat_results.get('avg_exact_prefix_ratio', 0):.3f} | "
                              f"{cat_results.get('avg_action_lcs_similarity', 0):.3f} | "
                              f"{cat_results.get('avg_phase_exact_prefix_ratio', 0):.3f} | "
                              f"{cat_results.get('avg_phase_lcs_similarity', 0):.3f}")

            print("="*80)

        except Exception as e:
            print(f"\nError analyzing {config}: {e}")
            import traceback
            traceback.print_exc()

    print("\n✓ Divergence analysis complete!")


if __name__ == "__main__":
    main()
