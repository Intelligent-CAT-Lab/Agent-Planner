#!/usr/bin/env python3
"""
Rule Trigger Scanner for Trajectory Files.

Scans a directory of trajectory files and counts how many times each rule
would be satisfied using check_step_pre_emptively. Does not actually trigger
the monitor/refiner - only counts potential rule satisfactions.

usage:
    python scan_rule_triggers.py /path/to/trajectories/ --agent mini-swe-agent --verbose --output
e.g.:
    python plan_monitor/simulator/scan_rule_triggers.py mini-swe-agent/outputs/default/swebench/gpt-5-mini/1 --agent mini-swe-agent --output plan_monitor/simulator/stats/swebv_mini-swe-agent_gpt-5-mini_1.json
    python plan_monitor/simulator/scan_rule_triggers.py swe-agent/trajectories --agent swe-agent --output results.json
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
import os

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.simulator import mini_extractor, swe_extractor


@dataclass
class RuleTriggerStats:
    """Statistics for rule triggers across trajectories."""

    # Overall counts
    total_trajectories: int = 0
    total_steps: int = 0
    trajectories_with_triggers: int = 0

    # Rule category counts (across all trajectories)
    plan_compliance_count: int = 0
    dwell_count: int = 0
    oscillation_count: int = 0
    repeated_action_count: int = 0

    # Trajectories with each category
    trajs_with_plan_compliance: int = 0
    trajs_with_dwell: int = 0
    trajs_with_oscillation: int = 0
    trajs_with_repeated_action: int = 0

    # Detailed rule counts
    rule_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Per-trajectory statistics
    trajectory_stats: List[Dict] = field(default_factory=list)

    # Blocking vs non-blocking
    blocking_count: int = 0
    non_blocking_count: int = 0

    def add_trigger(self, rule_id: str, blocking: bool = False):
        """Add a rule trigger to statistics."""
        self.rule_counts[rule_id] += 1

        # Categorize by rule type
        if "plan_compliance" in rule_id:
            self.plan_compliance_count += 1
        elif "dwell" in rule_id:
            self.dwell_count += 1
        elif "oscillation" in rule_id:
            self.oscillation_count += 1
        elif "repeated" in rule_id:
            self.repeated_action_count += 1

        # Track blocking status
        if blocking:
            self.blocking_count += 1
        else:
            self.non_blocking_count += 1


class RuleTriggerScanner:
    """
    Scans trajectory files and counts rule triggers using check_step_pre_emptively.

    This scanner processes trajectories without actually executing the monitor/refiner,
    allowing for analysis of how often rules would be triggered across a dataset.
    """

    def __init__(self, trajectory_dir: str | Path, verbose: bool = False, agent: str = "mini-swe-agent"):
        """
        Initialize the scanner.

        Args:
            trajectory_dir: Directory containing trajectory JSON files
            verbose: Print detailed per-trajectory information
            agent: Agent type ("mini-swe-agent" or "swe-agent")
        """
        self.trajectory_dir = Path(trajectory_dir)
        self.verbose = verbose
        self.agent = agent
        self.stats = RuleTriggerStats()

    def scan(self) -> RuleTriggerStats:
        """
        Scan all trajectory files in the directory.

        Returns:
            RuleTriggerStats with aggregated statistics
        """
        # Find all trajectory files based on agent type
        if self.agent == "swe-agent":
            pattern = "**/*.traj"
        else:  # mini-swe-agent
            pattern = "**/*.traj.json"

        traj_files = sorted(self.trajectory_dir.glob(pattern))

        if not traj_files:
            print(f"No trajectory files found in {self.trajectory_dir}")
            return self.stats

        print(f"Found {len(traj_files)} trajectory files")
        print("=" * 80)

        # Process each trajectory
        for traj_file in traj_files:
            self._process_trajectory(traj_file)

        return self.stats

    def _process_trajectory(self, traj_path: Path):
        """
        Process a single trajectory file.

        Args:
            traj_path: Path to trajectory JSON file
        """
        try:
            # Initialize monitor with rules enabled
            monitor = StatefulPhaseMonitor(enable_rules=True)

            # Choose appropriate extractor based on agent type
            if self.agent == "swe-agent":
                extractor = swe_extractor.ActionExtractor(traj_path)
            else:  # mini-swe-agent
                extractor = mini_extractor.ActionExtractor(traj_path)

            instance_id = extractor.get_instance_id()

            # Track per-trajectory statistics
            traj_stats = {
                'instance_id': instance_id,
                'file': traj_path.name,
                'steps': 0,
                'rule_triggers': 0,
                'blocking_triggers': 0,
                'rule_breakdown': defaultdict(int),
                'step_rule_triggers': [],  # Track which step triggered which rule
                'languatory_sequence': []  # Track phase/role sequence
            }

            # Process each action using check_step_pre_emptively
            for event, thought, observation in extractor.extract_actions():
                traj_stats['steps'] += 1

                # Use check_step_pre_emptively to detect rule triggers without committing state
                result = monitor.check_step_pre_emptively(event, thought=thought)

                if result and result.rule_matches:
                    traj_stats['rule_triggers'] += len(result.rule_matches)

                    # Count each rule match
                    for match in result.rule_matches:
                        self.stats.add_trigger(match.rule_id, blocking=match.block_execution)
                        traj_stats['rule_breakdown'][match.rule_id] += 1

                        # Track step-level rule trigger
                        traj_stats['step_rule_triggers'].append({
                            'step_index': event.step_index,
                            'rule_id': match.rule_id,
                            'blocking': match.block_execution,
                            'message': match.message
                        })

                        if match.block_execution:
                            traj_stats['blocking_triggers'] += 1

                        if self.verbose:
                            print(f"  [{instance_id}] Step {event.step_index}: {match.rule_id}")
                            print(f"    Message: {match.message[:100]}...")

            # After processing all steps, capture the languatory sequence
            traj_stats['languatory_sequence'] = monitor.get_phase_history()

            # Convert defaultdict to dict for JSON serialization
            traj_stats['rule_breakdown'] = dict(traj_stats['rule_breakdown'])

            # Update overall statistics
            self.stats.total_trajectories += 1
            self.stats.total_steps += traj_stats['steps']

            if traj_stats['rule_triggers'] > 0:
                self.stats.trajectories_with_triggers += 1

            # Count trajectories with each rule category
            has_plan_compliance = any("plan_compliance" in rule_id for rule_id in traj_stats['rule_breakdown'])
            has_dwell = any("dwell" in rule_id for rule_id in traj_stats['rule_breakdown'])
            has_oscillation = any("oscillation" in rule_id for rule_id in traj_stats['rule_breakdown'])
            has_repeated = any("repeated" in rule_id for rule_id in traj_stats['rule_breakdown'])

            if has_plan_compliance:
                self.stats.trajs_with_plan_compliance += 1
            if has_dwell:
                self.stats.trajs_with_dwell += 1
            if has_oscillation:
                self.stats.trajs_with_oscillation += 1
            if has_repeated:
                self.stats.trajs_with_repeated_action += 1

            # Save trajectory stats
            self.stats.trajectory_stats.append(traj_stats)

            # Print trajectory summary
            if traj_stats['rule_triggers'] > 0 or self.verbose:
                print(f"\n{instance_id}:")
                print(f"  Steps: {traj_stats['steps']}")
                print(f"  Rule triggers: {traj_stats['rule_triggers']} ({traj_stats['blocking_triggers']} blocking)")
                if traj_stats['rule_breakdown']:
                    print(f"  Breakdown: {dict(traj_stats['rule_breakdown'])}")

        except Exception as e:
            print(f"Error processing {traj_path.name}: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()

    def print_summary(self):
        """Print a comprehensive summary table of rule trigger statistics."""
        print("\n" + "=" * 80)
        print("RULE TRIGGER SUMMARY")
        print("=" * 80)

        # Overall statistics
        print("\n[Overall Statistics]")
        print(f"  Total trajectories: {self.stats.total_trajectories}")
        print(f"  Trajectories with triggers: {self.stats.trajectories_with_triggers} "
              f"({self.stats.trajectories_with_triggers/self.stats.total_trajectories*100:.1f}%)")
        print(f"  Total steps: {self.stats.total_steps}")
        print(f"  Average steps per trajectory: {self.stats.total_steps/self.stats.total_trajectories:.1f}")

        # Total triggers
        total_triggers = sum(self.stats.rule_counts.values())
        print(f"\n  Total rule triggers: {total_triggers}")
        print(f"  Average triggers per trajectory: {total_triggers/self.stats.total_trajectories:.2f}")
        print(f"  Blocking triggers: {self.stats.blocking_count}")
        print(f"  Non-blocking triggers: {self.stats.non_blocking_count}")

        # Rule category breakdown
        print("\n[Rule Category Breakdown]")
        categories = [
            ("Plan Compliance", self.stats.plan_compliance_count, self.stats.trajs_with_plan_compliance),
            ("Dwell Times", self.stats.dwell_count, self.stats.trajs_with_dwell),
            ("Oscillations", self.stats.oscillation_count, self.stats.trajs_with_oscillation),
            ("Repeated Actions", self.stats.repeated_action_count, self.stats.trajs_with_repeated_action)
        ]

        for category, count, traj_count in categories:
            percentage = count / total_triggers * 100 if total_triggers > 0 else 0
            traj_percentage = traj_count / self.stats.total_trajectories * 100 if self.stats.total_trajectories > 0 else 0
            print(f"  {category:20s}: {count:6d} ({percentage:5.1f}%) | {traj_count} trajs ({traj_percentage:.1f}%)")

        # Detailed rule breakdown
        print("\n[Detailed Rule Breakdown]")
        print(f"{'Rule ID':<35s} {'Count':>8s} {'% of Total':>10s} {'Avg/Traj':>10s}")
        print("-" * 80)

        sorted_rules = sorted(self.stats.rule_counts.items(), key=lambda x: x[1], reverse=True)
        for rule_id, count in sorted_rules:
            percentage = count / total_triggers * 100 if total_triggers > 0 else 0
            avg_per_traj = count / self.stats.total_trajectories
            print(f"{rule_id:<35s} {count:8d} {percentage:9.1f}% {avg_per_traj:10.2f}")

        # Top trajectories with most triggers
        print("\n[Top 10 Trajectories by Rule Triggers]")
        print(f"{'Instance ID':<45s} {'Steps':>6s} {'Triggers':>9s} {'Blocking':>9s}")
        print("-" * 80)

        sorted_trajs = sorted(
            self.stats.trajectory_stats,
            key=lambda x: x['rule_triggers'],
            reverse=True
        )[:10]

        for traj in sorted_trajs:
            print(f"{traj['instance_id']:<45s} {traj['steps']:6d} {traj['rule_triggers']:9d} {traj['blocking_triggers']:9d}")

        # Trajectories without triggers
        no_trigger_count = self.stats.total_trajectories - self.stats.trajectories_with_triggers
        if no_trigger_count > 0:
            print(f"\n[Trajectories Without Triggers: {no_trigger_count}]")
            no_trigger_trajs = [t for t in self.stats.trajectory_stats if t['rule_triggers'] == 0]
            for traj in no_trigger_trajs[:10]:  # Show first 10
                print(f"  {traj['instance_id']}")
            if no_trigger_count > 10:
                print(f"  ... and {no_trigger_count - 10} more")

        print("\n" + "=" * 80)

    def save_results(self, output_path: str | Path):
        """
        Save detailed results to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        output_data = {
            'summary': {
                'total_trajectories': self.stats.total_trajectories,
                'trajectories_with_triggers': self.stats.trajectories_with_triggers,
                'total_steps': self.stats.total_steps,
                'total_triggers': sum(self.stats.rule_counts.values()),
                'blocking_count': self.stats.blocking_count,
                'non_blocking_count': self.stats.non_blocking_count
            },
            'rule_category_counts': {
                'plan_compliance': self.stats.plan_compliance_count,
                'dwell_times': self.stats.dwell_count,
                'oscillations': self.stats.oscillation_count,
                'repeated_actions': self.stats.repeated_action_count
            },
            'trajectories_per_category': {
                'plan_compliance': self.stats.trajs_with_plan_compliance,
                'dwell_times': self.stats.trajs_with_dwell,
                'oscillations': self.stats.trajs_with_oscillation,
                'repeated_actions': self.stats.trajs_with_repeated_action
            },
            'detailed_rule_counts': dict(self.stats.rule_counts),
            'trajectory_stats': self.stats.trajectory_stats
        }

        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\nResults saved to: {output_path}")


def main():
    """CLI entry point for the rule trigger scanner."""
    parser = argparse.ArgumentParser(
        description="Scan trajectory files and count rule triggers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan mini-swe-agent trajectories (default)
  python scan_rule_triggers.py /path/to/trajectories/

  # Scan swe-agent trajectories
  python scan_rule_triggers.py /path/to/trajectories/ --agent swe-agent

  # Scan with verbose output and save results
  python scan_rule_triggers.py /path/to/trajectories/ --agent swe-agent --verbose --output results.json
        """
    )

    parser.add_argument(
        'trajectory_dir',
        type=str,
        help='Directory containing trajectory JSON files'
    )

    parser.add_argument(
        '--agent', '-a',
        type=str,
        choices=['mini-swe-agent', 'swe-agent'],
        default='mini-swe-agent',
        help='Agent type: mini-swe-agent (*.traj.json) or swe-agent (*.traj)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed per-trajectory information'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Save detailed results to JSON file'
    )

    args = parser.parse_args()

    # Validate directory exists
    traj_dir = Path(args.trajectory_dir)
    if not traj_dir.exists():
        print(f"Error: Directory not found: {traj_dir}")
        return 1

    if not traj_dir.is_dir():
        print(f"Error: Not a directory: {traj_dir}")
        return 1

    # Run scanner
    try:
        scanner = RuleTriggerScanner(traj_dir, verbose=args.verbose, agent=args.agent)
        scanner.scan()
        scanner.print_summary()

        # Save results if requested
        if args.output:
            scanner.save_results(args.output)

        return 0

    except Exception as e:
        print(f"Error running scanner: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
