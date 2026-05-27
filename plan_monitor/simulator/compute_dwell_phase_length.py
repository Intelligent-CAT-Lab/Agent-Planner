#!/usr/bin/env python3
"""
Compute longest consecutive dwell phase lengths from trajectories.

Scans trajectory files, processes them through the phase monitor,
and computes statistics on consecutive dwell phases for each phase type
defined in default_rules.json (L_navigate, L_reproduce, P, V).
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.simulator import mini_extractor, swe_extractor
from plan_monitor.phases import Phase


def phase_matches(phase: Phase, target: str) -> bool:
    """
    Check if a phase matches the target using asymmetric prefix matching.

    Rules:
    - If target has underscore (e.g., 'L_navigate', 'L_reproduce'): exact match
    - If target is single letter or no underscore (e.g., 'P', 'V'): prefix match

    Args:
        phase: Phase object to check
        target: Target phase type (e.g., 'L_navigate', 'P', 'V')

    Returns:
        True if phase matches target

    Examples:
        phase_matches(Phase('L_navigate'), 'L_navigate') -> True
        phase_matches(Phase('L_reproduce'), 'L_navigate') -> False
        phase_matches(Phase('P'), 'P') -> True
        phase_matches(Phase('P_refactor'), 'P') -> True
        phase_matches(Phase('V_newly_generated_test'), 'V') -> True
        phase_matches(Phase('V_regression_test'), 'V') -> True
    """
    if '_' in target:
        # Exact match for specific phases like L_navigate, L_reproduce
        return phase.value == target
    else:
        # Prefix match for category-level phases like P, V
        return phase.prefix == target


def compute_consecutive_dwell_lengths(
    phase_sequence: List[str],
    phase_types: List[str]
) -> Dict[str, int]:
    """
    Compute longest consecutive dwell length for each phase type from role history.

    Uses asymmetric prefix matching:
    - 'L_navigate', 'L_reproduce': exact match only
    - 'P': matches P, P_refactor, etc. (all phases with prefix 'P')
    - 'V': matches V_newly_generated_test, V_regression_test, etc. (all phases with prefix 'V')

    Args:
        phase_sequence: List of phase labels from role_history
                       (e.g., ['L_navigate', 'L_navigate', 'L_navigate', 'P', 'L_navigate', 'L_navigate'])
        phase_types: List of phase types to track (e.g., ['L_navigate', 'L_reproduce', 'P', 'V'])

    Returns:
        Dict mapping phase type to longest consecutive length
        Example: For ['L_navigate', 'L_navigate', 'L_navigate', 'P', 'L_navigate', 'L_navigate']
                 returns {'L_navigate': 3, 'L_reproduce': 0, 'P': 1, 'V': 0}
    """
    if not phase_sequence:
        return {pt: 0 for pt in phase_types}

    # Convert string sequence to Phase objects
    phase_objects = [Phase(p) for p in phase_sequence]

    # Track max consecutive length for each phase type
    max_lengths: Dict[str, int] = {pt: 0 for pt in phase_types}

    # For each phase type, compute its longest consecutive streak
    for phase_type in phase_types:
        current_length = 0

        for phase in phase_objects:
            if phase_matches(phase, phase_type):
                current_length += 1
                max_lengths[phase_type] = max(max_lengths[phase_type], current_length)
            else:
                current_length = 0

    return max_lengths


def process_trajectory(
    traj_path: Path,
    phase_types: List[str],
    enable_rules: bool = False,
    agent: str = "mini-swe-agent"
) -> Optional[Dict[str, int]]:
    """
    Process a single trajectory file and return dwell lengths.

    Args:
        traj_path: Path to .traj.json or .traj file
        phase_types: List of phase types to track (e.g., ['L_navigate', 'L_reproduce', 'P', 'V'])
        enable_rules: Whether to enable rules (not needed for dwell computation)
        agent: Agent type ("mini-swe-agent" or "SWE-agent")

    Returns:
        Dict mapping phase names to longest consecutive dwell lengths, or None on error
    """
    try:
        monitor = StatefulPhaseMonitor(enable_rules=enable_rules)

        # Choose appropriate extractor based on agent type
        if agent == "SWE-agent":
            extractor = swe_extractor.ActionExtractor(traj_path)
        else:  # mini-swe-agent
            extractor = mini_extractor.ActionExtractor(traj_path)

        # Track phase at each step (not just transitions)
        phase_sequence_per_step: List[str] = []

        # Process all steps through the monitor
        # Use on_step instead of check_step_pre_emptively to avoid rollback from blocking rules
        for event, thought, observation in extractor.extract_actions():
            monitor.on_step(event, thought=thought, observation=observation)
            # Get current phase after this step
            current_phase = monitor.get_current_phase()
            if current_phase is not None:
                phase_sequence_per_step.append(current_phase.value)

        # Compute consecutive dwell lengths using asymmetric prefix matching
        dwell_lengths = compute_consecutive_dwell_lengths(phase_sequence_per_step, phase_types)

        return dwell_lengths

    except Exception as e:
        print(f"Error processing {traj_path}: {e}")
        return None

def get_agent_base_dir(agent: str, dataset: str = "swebench", base_dir: Optional[Path] = None) -> Path:
    """Get the agent base directory."""
    if base_dir is None:
        current = Path(__file__).resolve()

        # Determine the directory name to search for
        if dataset == "swebench-pro" and agent == "SWE-agent":
            # For SWE-bench Pro, use SWE-bench_Pro-os/SWE-agent
            agent_dir_name = "SWE-bench_Pro-os/SWE-agent"
        else:
            # For regular swebench or mini-swe-agent, use agent name directly
            agent_dir_name = agent

        for parent in current.parents:
            # Handle nested path (e.g., "SWE-bench_Pro-os/SWE-agent")
            if "/" in agent_dir_name:
                parts = agent_dir_name.split("/")
                candidate = parent
                for part in parts:
                    candidate = candidate / part
            else:
                candidate = parent / agent_dir_name

            # For mini-swe-agent: check for "outputs", for SWE-agent: check for "trajectories"
            required_subdir = "outputs" if agent == "mini-swe-agent" else "trajectories"
            if candidate.exists() and (candidate / required_subdir).exists():
                return candidate

        raise ValueError(f"Could not find {agent_dir_name} directory. Please specify base_dir.")
    return Path(base_dir)

def find_trajectory_files(
    agent: str = "mini-swe-agent",
    config: str = "default",
    dataset: str = "swebench",
    model: Optional[str] = None,
    base_dir: Optional[Path] = None,
    sample_approach: Optional[str] = None
) -> List[Path]:
    """
    Find all trajectory files matching the given parameters.

    Args:
        agent: Agent name (default: "mini-swe-agent")
        config: Config name (default: "default")
        dataset: Dataset name (default: "swebench")
        model: Model name (e.g., "gpt-5-mini", "deepseek-chat-v3-0324"). If None, scan all models.
        base_dir: Base directory (default: auto-detect Agent-Planner/mini-swe-agent)
        sample_approach: Sample approach (e.g., "python" for swebench-pro). If provided, path includes this.

    Returns:
        List of paths to trajectory files
    """
    agent_base = get_agent_base_dir(agent, dataset, base_dir)

    # Different path structures for different agents
    if agent == "SWE-agent":
        outputs_dir = agent_base / "trajectories" / config / dataset
        # Add sample_approach to path if provided (for swebench-pro)
        if sample_approach:
            outputs_dir = outputs_dir / sample_approach
        pattern = "**/*.traj"
    else:  # mini-swe-agent
        outputs_dir = agent_base / "outputs" / config / dataset
        pattern = "**/*.traj.json"

    if not outputs_dir.exists():
        raise ValueError(f"Directory not found: {outputs_dir}")

    # Scan for trajectory files
    traj_files = []

    if model:
        # Scan specific model directory
        model_dir = outputs_dir / model
        if model_dir.exists():
            traj_files.extend(model_dir.glob(pattern))
    else:
        # Scan all models
        traj_files.extend(outputs_dir.glob(pattern))

    return sorted(traj_files)


def load_resolved_ids_from_report(
    agent_base: Path,
    config: str,
    dataset: str,
    model: str,
    run_id: str,
    sample_approach: Optional[str] = None
) -> Optional[set]:
    """
    Load resolved instance IDs from report file.

    Report path formats:
    - mini-swe-agent: {agent}/reports/{config}/{dataset}/{model}/{model}.run_{run-id}.json
    - SWE-agent (swebench): {agent}/reports/{config}/{dataset}/{model}/{model}.run_{run-id}.json
    - SWE-agent (swebench-pro): {agent}/reports/{config}/{dataset}/{sample-approach}/{model}/run-{run-id}/eval_results.json

    Args:
        agent_base: Base directory for agent
        config: Config name
        dataset: Dataset name
        model: Model name
        run_id: Run ID (e.g., "1", "run-1", "run_1")
        sample_approach: Sample approach (e.g., "python" for swebench-pro)

    Returns:
        Set of resolved instance IDs, or None if report not found
    """
    # Check for SWE-bench Pro format first (has sample_approach and uses eval_results.json)
    if sample_approach and dataset == "swebench-pro":
        # Path: reports/{config}/{dataset}/{sample-approach}/{model}/{run-id}/eval_results.json
        # run_id may already have "run-" prefix, so normalize it
        if run_id.startswith("run-") or run_id.startswith("run_"):
            normalized_run_id = run_id
        else:
            normalized_run_id = f"run-{run_id}"

        pro_report_path = agent_base / "reports" / config / dataset / sample_approach / model / normalized_run_id / "eval_results.json"

        if pro_report_path.exists():
            try:
                with open(pro_report_path, 'r') as f:
                    report_data = json.load(f)
                    # SWE-bench Pro format: dict mapping instance_id -> bool (true=resolved, false=unresolved)
                    if isinstance(report_data, dict):
                        resolved_ids = {inst_id for inst_id, is_resolved in report_data.items() if is_resolved}
                        return resolved_ids
            except Exception as e:
                print(f"Warning: Failed to load SWE-bench Pro report {pro_report_path}: {e}")
                return None

    # Standard mini-swe-agent or SWE-agent format
    reports_dir = agent_base / "reports" / config / dataset / model

    if not reports_dir.exists():
        return None

    # Try different run_id formats
    # Pattern: {model}.run_{run-id}.json or {model}.run-{run-id}.json or {model}.{run-id}.json
    possible_names = [
        f"{model}.run_{run_id}.json",
        f"{model}.run-{run_id}.json",
        f"{model}.{run_id}.json",
    ]

    # Also handle run_id that already has "run-" prefix
    if run_id.startswith("run-") or run_id.startswith("run_"):
        run_num = run_id.split("-")[-1].split("_")[-1]
        possible_names.extend([
            f"{model}.run_{run_num}.json",
            f"{model}.run-{run_num}.json",
            f"{model}.{run_num}.json",
        ])

    for report_name in possible_names:
        report_path = reports_dir / report_name
        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    report_data = json.load(f)
                    # Standard format: has 'resolved_ids' list
                    resolved_ids = report_data.get('resolved_ids', [])
                    return set(resolved_ids)
            except Exception as e:
                print(f"Warning: Failed to load report {report_path}: {e}")
                return None

    return None


def group_by_run_id(traj_files: List[Path], agent: str = "mini-swe-agent", sample_approach: Optional[str] = None) -> Dict[str, List[Path]]:
    """
    Group trajectory files by run-id.

    Extracts run-id from path structure:
    - mini-swe-agent: outputs/{config}/{dataset}/{model}/{run-id}/{instance}.traj.json
    - SWE-agent (standard): trajectories/{config}/{dataset}/{model}/{run-id}/{instance}/{instance}.traj
    - SWE-agent (with sample-approach): trajectories/{config}/{dataset}/{sample-approach}/{model}/{run-id}/{instance}/{instance}.traj

    Args:
        traj_files: List of trajectory file paths
        agent: Agent type ("mini-swe-agent" or "SWE-agent")
        sample_approach: Sample approach (adds extra directory level for swebench-pro)

    Returns:
        Dict mapping run-id to list of trajectory paths
    """
    grouped: Dict[str, List[Path]] = defaultdict(list)

    # Determine which directory to look for based on agent type
    dir_name = "trajectories" if agent == "SWE-agent" else "outputs"

    for traj_path in traj_files:
        # Extract run-id from path
        parts = traj_path.parts

        # Find directory name in path
        try:
            dir_idx = parts.index(dir_name)
            # Path structure depends on whether sample_approach is used
            # Standard: dir_name/config/dataset/model/run-id/...
            # With sample-approach: dir_name/config/dataset/sample-approach/model/run-id/...
            if sample_approach:
                # Extra level: dir_idx + 5 = run-id
                if dir_idx + 5 < len(parts):
                    run_id = parts[dir_idx + 5]
                else:
                    run_id = "default"
            else:
                # Standard: dir_idx + 4 = run-id
                if dir_idx + 4 < len(parts):
                    run_id = parts[dir_idx + 4]
                else:
                    run_id = "default"
        except (ValueError, IndexError):
            run_id = "default"

        grouped[run_id].append(traj_path)

    return dict(grouped)


def extract_instance_id(traj_path: Path) -> str:
    """
    Extract instance ID from trajectory file path.

    Handles patterns like:
    - .../instance_id/instance_id.traj.json
    - .../instance_id.traj.json

    Args:
        traj_path: Path to trajectory file

    Returns:
        Instance ID (e.g., "django__django-14631")
    """
    # Remove .traj.json extension
    stem = traj_path.stem.replace('.traj', '')

    # If stem is empty, use parent directory name
    if not stem or stem == '.traj':
        return traj_path.parent.name

    return stem


def compute_statistics(
    all_dwell_lengths: List[Dict[str, int]],
    phase_types: List[str]
) -> Dict[str, Dict[str, float]]:
    """
    Compute statistics across all trajectories including median and standard deviation.

    Args:
        all_dwell_lengths: List of dwell length dicts from each trajectory
        phase_types: List of phase types to compute stats for (e.g., ['L_navigate', 'L_reproduce', 'P', 'V'])

    Returns:
        Dict mapping phase type to {max, avg, median, std, count} statistics
    """
    stats: Dict[str, Dict[str, float]] = {}

    for phase_type in phase_types:
        # Collect all lengths for this phase type
        lengths = []
        for dwell_dict in all_dwell_lengths:
            if phase_type in dwell_dict:
                lengths.append(dwell_dict[phase_type])

        if lengths:
            n = len(lengths)
            avg = sum(lengths) / n

            # Compute standard deviation
            if n > 1:
                variance = sum((x - avg) ** 2 for x in lengths) / n
                std = variance ** 0.5
            else:
                std = 0.0

            # Compute median
            sorted_lengths = sorted(lengths)
            if n % 2 == 0:
                median = (sorted_lengths[n // 2 - 1] + sorted_lengths[n // 2]) / 2.0
            else:
                median = float(sorted_lengths[n // 2])

            stats[phase_type] = {
                'max': max(lengths),
                'avg': avg,
                'median': median,
                'std': std,
                'count': n
            }
        else:
            stats[phase_type] = {
                'max': 0,
                'avg': 0.0,
                'median': 0.0,
                'std': 0.0,
                'count': 0
            }

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compute longest consecutive dwell phase lengths from trajectories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan default config with gpt-5-mini model
  python plan_monitor/simulator/compute_dwell_phase_length.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench-pro --sample-approach python

  # Scan monitor config with deepseek model
  python plan_monitor/simulator/compute_dwell_phase_length.py --config monitor --model deepseek-chat-v3-0324

  # Scan all models in default config
  python plan_monitor/simulator/compute_dwell_phase_length.py
        """
    )

    parser.add_argument(
        '--agent',
        type=str,
        choices=['mini-swe-agent', 'SWE-agent'],
        default='mini-swe-agent',
        help='Agent type: mini-swe-agent or SWE-agent (default: mini-swe-agent)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='default',
        help='Config name (default: default)'
    )

    parser.add_argument(
        '--dataset',
        type=str,
        default='swebench',
        help='Dataset name (default: swebench)'
    )

    parser.add_argument(
        '--sample-approach',
        type=str,
        default=None,
        help='Sample approach (e.g., "python" for swebench-pro). If provided, path includes this directory level.'
    )

    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (e.g., gpt-5-mini, deepseek-chat-v3-0324). If not specified, scan all models.'
    )

    parser.add_argument(
        '--base-dir',
        type=Path,
        default=None,
        help='Base directory for agent outputs (default: auto-detect)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Output JSON file for results (optional)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed per-trajectory information'
    )

    args = parser.parse_args()

    # Find trajectory files
    print(f"Scanning trajectories:")
    print(f"  Agent: {args.agent}")
    print(f"  Config: {args.config}")
    print(f"  Dataset: {args.dataset}")
    if args.sample_approach:
        print(f"  Sample approach: {args.sample_approach}")
    print(f"  Model: {args.model or 'all'}")
    print()

    try:
        traj_files = find_trajectory_files(
            agent=args.agent,
            config=args.config,
            dataset=args.dataset,
            model=args.model,
            base_dir=args.base_dir,
            sample_approach=args.sample_approach
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if not traj_files:
        print("No trajectory files found.")
        return 1

    print(f"Found {len(traj_files)} trajectory files")
    print()

    # Get agent base directory
    agent_base = get_agent_base_dir(args.agent, args.dataset, args.base_dir)

    # Group by run-id
    grouped_trajs = group_by_run_id(traj_files, agent=args.agent, sample_approach=args.sample_approach)
    print(f"Run IDs found: {', '.join(sorted(grouped_trajs.keys()))}")
    print()

    # Define phase types from default_rules.json
    phase_types = ['L_navigate', 'L_reproduce', 'P', 'V']

    # Process trajectories and collect results per run-id
    all_run_stats: Dict[str, Dict] = {}

    for run_id, run_trajs in sorted(grouped_trajs.items()):
        print(f"Processing run-id: {run_id} ({len(run_trajs)} trajectories)")

        # Load resolved IDs for this run from report
        resolved_ids = None
        if args.model:
            resolved_ids = load_resolved_ids_from_report(
                agent_base, args.config, args.dataset, args.model, run_id, args.sample_approach
            )
            if resolved_ids:
                print(f"  Loaded {len(resolved_ids)} resolved IDs from report")
            else:
                print(f"  Warning: No report found for run-id '{run_id}'")

        # Separate trajectories into resolved/unresolved
        resolved_dwell_lengths: List[Dict[str, int]] = []
        unresolved_dwell_lengths: List[Dict[str, int]] = []

        for traj_path in run_trajs:
            if args.verbose:
                print(f"  Processing: {traj_path.name}")

            dwell_lengths = process_trajectory(traj_path, phase_types, enable_rules=False, agent=args.agent)
            if dwell_lengths is not None:
                # Determine if this trajectory is resolved
                if resolved_ids is not None:
                    instance_id = extract_instance_id(traj_path)
                    if instance_id in resolved_ids:
                        resolved_dwell_lengths.append(dwell_lengths)
                        if args.verbose:
                            print(f"    [RESOLVED] Dwell lengths: {dwell_lengths}")
                    else:
                        unresolved_dwell_lengths.append(dwell_lengths)
                        if args.verbose:
                            print(f"    [UNRESOLVED] Dwell lengths: {dwell_lengths}")
                else:
                    # No report available, treat all as overall
                    resolved_dwell_lengths.append(dwell_lengths)
                    if args.verbose:
                        print(f"    Dwell lengths: {dwell_lengths}")

        # Compute statistics for this run
        run_stats = {}

        if resolved_ids is not None:
            # Compute separate statistics for resolved/unresolved
            if resolved_dwell_lengths:
                resolved_stats = compute_statistics(resolved_dwell_lengths, phase_types)
                run_stats['resolved'] = resolved_stats
                print(f"  Statistics for run-id '{run_id}' (RESOLVED, n={len(resolved_dwell_lengths)}):")
                print(f"    {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"    {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = resolved_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"    {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

            if unresolved_dwell_lengths:
                unresolved_stats = compute_statistics(unresolved_dwell_lengths, phase_types)
                run_stats['unresolved'] = unresolved_stats
                print(f"  Statistics for run-id '{run_id}' (UNRESOLVED, n={len(unresolved_dwell_lengths)}):")
                print(f"    {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"    {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = unresolved_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"    {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

            # Overall for this run
            all_run_dwell_lengths = resolved_dwell_lengths + unresolved_dwell_lengths
            if all_run_dwell_lengths:
                overall_stats = compute_statistics(all_run_dwell_lengths, phase_types)
                run_stats['overall'] = overall_stats
                print(f"  Statistics for run-id '{run_id}' (OVERALL, n={len(all_run_dwell_lengths)}):")
                print(f"    {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"    {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = overall_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"    {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")
        else:
            # No report, only compute overall
            if resolved_dwell_lengths:
                overall_stats = compute_statistics(resolved_dwell_lengths, phase_types)
                run_stats['overall'] = overall_stats
                print(f"  Statistics for run-id '{run_id}':")
                print(f"    {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"    {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = overall_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"    {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

        all_run_stats[run_id] = run_stats
        print()

    # Compute overall statistics across all runs
    if len(all_run_stats) > 1:
        print("="*80)
        print("Overall Statistics (across all run-ids):")
        print("="*80)

        # Check if we have report-based separation
        has_reports = args.model and any(
            load_resolved_ids_from_report(agent_base, args.config, args.dataset, args.model, run_id, args.sample_approach) is not None
            for run_id in grouped_trajs.keys()
        )

        if has_reports:
            # Flatten all dwell lengths from all runs, separated by resolved/unresolved
            all_resolved_dwell_lengths: List[Dict[str, int]] = []
            all_unresolved_dwell_lengths: List[Dict[str, int]] = []

            for run_id, run_trajs in grouped_trajs.items():
                resolved_ids = load_resolved_ids_from_report(
                    agent_base, args.config, args.dataset, args.model, run_id, args.sample_approach
                )

                for traj_path in run_trajs:
                    dwell_lengths = process_trajectory(traj_path, phase_types, enable_rules=False, agent=args.agent)
                    if dwell_lengths is not None:
                        if resolved_ids is not None:
                            instance_id = extract_instance_id(traj_path)
                            if instance_id in resolved_ids:
                                all_resolved_dwell_lengths.append(dwell_lengths)
                            else:
                                all_unresolved_dwell_lengths.append(dwell_lengths)
                        else:
                            # Fallback to overall if no report for this run
                            all_resolved_dwell_lengths.append(dwell_lengths)

            # Compute overall statistics
            overall_stats = {}

            if all_resolved_dwell_lengths:
                resolved_stats = compute_statistics(all_resolved_dwell_lengths, phase_types)
                overall_stats['resolved'] = resolved_stats
                print(f"Overall RESOLVED (n={len(all_resolved_dwell_lengths)}):")
                print(f"  {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"  {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = resolved_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"  {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

            if all_unresolved_dwell_lengths:
                unresolved_stats = compute_statistics(all_unresolved_dwell_lengths, phase_types)
                overall_stats['unresolved'] = unresolved_stats
                print(f"Overall UNRESOLVED (n={len(all_unresolved_dwell_lengths)}):")
                print(f"  {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"  {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = unresolved_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"  {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

            # Overall across all trajectories
            all_dwell_lengths = all_resolved_dwell_lengths + all_unresolved_dwell_lengths
            if all_dwell_lengths:
                overall_all_stats = compute_statistics(all_dwell_lengths, phase_types)
                overall_stats['overall'] = overall_all_stats
                print(f"Overall ALL (n={len(all_dwell_lengths)}):")
                print(f"  {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
                print(f"  {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
                for phase_type in phase_types:
                    stats = overall_all_stats[phase_type]
                    avg_minus_std = max(0, stats['avg'] - stats['std'])
                    avg_plus_std = stats['avg'] + stats['std']
                    print(f"  {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

            all_run_stats['overall'] = overall_stats
        else:
            # No reports, compute overall only
            all_dwell_lengths_list: List[Dict[str, int]] = []
            for run_id, run_trajs in grouped_trajs.items():
                for traj_path in run_trajs:
                    dwell_lengths = process_trajectory(traj_path, phase_types, enable_rules=False, agent=args.agent)
                    if dwell_lengths is not None:
                        all_dwell_lengths_list.append(dwell_lengths)

            overall_stats = compute_statistics(all_dwell_lengths_list, phase_types)

            print(f"  {'Phase':<15} {'Max':>5} {'Avg':>6} {'Median':>6} {'Std':>6} {'Avg-Std':>7} {'Avg+Std':>7} {'n':>5}")
            print(f"  {'-'*15} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*5}")
            for phase_type in phase_types:
                stats = overall_stats[phase_type]
                avg_minus_std = max(0, stats['avg'] - stats['std'])
                avg_plus_std = stats['avg'] + stats['std']
                print(f"  {phase_type:<15} {stats['max']:5.0f} {stats['avg']:6.2f} {stats['median']:6.1f} {stats['std']:6.2f} {avg_minus_std:7.2f} {avg_plus_std:7.2f} {stats['count']:5.0f}")

            all_run_stats['overall'] = {'overall': overall_stats}

        print()

    # Save results if output file specified
    if args.output:
        output_data = {
            'agent': args.agent,
            'config': args.config,
            'dataset': args.dataset,
            'model': args.model or 'all',
            'total_trajectories': len(traj_files),
            'run_ids': list(grouped_trajs.keys()),
            'statistics': all_run_stats
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"Results saved to: {args.output}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
