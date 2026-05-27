"""
Sample instances that are consistently resolved or unresolved across runs based on model reports.
100 samples are selected, equally split between resolved and unresolved, try to maintain similar distribution for easy, medium, hard, very hard levels.

Record the selected results in a json file (each data: instance_id, difficulty, original_resolved (True/False)) under samples/swebench/{model_name}/{sample_id}/sampled_instances.json

Usage:
    python sample_reproducible_outcome.py --config <config_name> --model <model_name> --sample_id <sample_id>

e.g:
    python sample_reproducible_outcome.py --config default --model deepseek-chat-v3-0324

Reproducibility:
    To ensure the same samples across runs, use the same sample_id (1, 2, or 3).
    Each sample_id uses a deterministic seed: seed = 42 + sample_id.
    sample_id by default is 1.
"""
import os
import json
import random
import argparse
from pathlib import Path
from datasets import load_dataset

# Mapping from SWE-bench difficulty labels to simplified categories
DIFFICULTY_KEYS = {
    '<15 min fix': 'easy',
    '15 min - 1 hour': 'medium',
    '1-4 hours': 'hard',
    '>4 hours': 'very_hard'
}

# Configuration for sampling
TOTAL_SAMPLES = 60
SAMPLES_PER_STATUS = TOTAL_SAMPLES // 2  # 50 resolved, 50 unresolved


def load_swebench_dataset():
    """Load and group SWE-bench instances by difficulty."""
    dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")

    grouped = {
        'easy': [],
        'medium': [],
        'hard': [],
        'very_hard': []
    }

    for item in dataset:
        diff = DIFFICULTY_KEYS.get(item['difficulty'])
        if diff:
            grouped[diff].append(item)

    return grouped


def load_model_report(config, model_name, run_id, project_root):
    """Load resolution status from model report."""
    report_path = project_root / "reports" / config / "swebench" / model_name / f"{model_name}.run_{run_id}.json"

    if not report_path.exists():
        raise FileNotFoundError(
            f"Report not found: {report_path}\n"
            f"Please ensure the report exists at the specified path."
        )

    with open(report_path, 'r') as f:
        report = json.load(f)

    return report


def find_consistent_instances(grouped, reports):
    """
    Find instances that have consistent resolution status across all runs.
    Returns two dicts: consistently resolved and consistently unresolved instances,
    grouped by difficulty.
    """
    consistent_resolved = {
        'easy': [],
        'medium': [],
        'hard': [],
        'very_hard': []
    }

    consistent_unresolved = {
        'easy': [],
        'medium': [],
        'hard': [],
        'very_hard': []
    }

    # Check each difficulty level
    for diff in ['easy', 'medium', 'hard', 'very_hard']:
        for item in grouped[diff]:
            instance_id = item['instance_id']

            # Check if instance exists in all reports
            if not all(instance_id in report.get('completed_ids', []) for report in reports):
                continue

            # Get resolution status from all runs
            statuses = []
            for report in reports:
                # Check if instance is in resolved_ids
                resolved = instance_id in report.get('resolved_ids', [])
                statuses.append(resolved)

            # Check if all statuses are the same
            if len(set(statuses)) == 1:  # All statuses are identical
                if statuses[0]:  # All resolved
                    consistent_resolved[diff].append(item)
                else:  # All unresolved
                    consistent_unresolved[diff].append(item)

    return consistent_resolved, consistent_unresolved


def stratified_sample_consistent(consistent_resolved, consistent_unresolved, sample_id):
    """
    Sample SAMPLES_PER_STATUS (50) from each status, maintaining similar difficulty distribution.
    If a difficulty lacks instances, compensate by sampling more from other difficulties.
    """
    random.seed(42 + sample_id)

    difficulties = ['easy', 'medium', 'hard', 'very_hard']

    def sample_with_distribution(instances_by_diff, target_total):
        """Sample target_total instances with balanced difficulty distribution."""
        # Calculate target per difficulty
        target_per_diff = target_total // len(difficulties)

        sampled = []
        remaining = target_total

        # First pass: take target amount from each difficulty if available
        shortfall_diffs = []
        for diff in difficulties:
            available = instances_by_diff[diff]
            if len(available) >= target_per_diff:
                sampled.extend(random.sample(available, target_per_diff))
                remaining -= target_per_diff
            else:
                sampled.extend(available)
                remaining -= len(available)
                shortfall_diffs.append(diff)

        # Second pass: if we're short, sample more from difficulties with extras
        if remaining > 0:
            extra_pool = []
            for diff in difficulties:
                if diff not in shortfall_diffs:
                    available = instances_by_diff[diff]
                    # Add instances not yet sampled
                    already_sampled = [x for x in sampled if DIFFICULTY_KEYS.get(x['difficulty']) == diff]
                    extra = [x for x in available if x not in already_sampled]
                    extra_pool.extend(extra)

            if len(extra_pool) >= remaining:
                sampled.extend(random.sample(extra_pool, remaining))
            else:
                sampled.extend(extra_pool)

        random.shuffle(sampled)
        return sampled

    sampled_resolved = sample_with_distribution(consistent_resolved, SAMPLES_PER_STATUS)
    sampled_unresolved = sample_with_distribution(consistent_unresolved, SAMPLES_PER_STATUS)

    return sampled_resolved, sampled_unresolved


def save_samples(sampled_resolved, sampled_unresolved, output_dir):
    """Save sampled instances to a single JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    output = []

    # Add resolved instances
    for x in sampled_resolved:
        instance_data = {
            "instance_id": x["instance_id"],
            "difficulty": DIFFICULTY_KEYS.get(x["difficulty"]),
            "original_resolved": True
        }
        output.append(instance_data)

    # Add unresolved instances
    for x in sampled_unresolved:
        instance_data = {
            "instance_id": x["instance_id"],
            "difficulty": DIFFICULTY_KEYS.get(x["difficulty"]),
            "original_resolved": False
        }
        output.append(instance_data)

    output_path = output_dir / "sampled_instances.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    return output_path, len(output)


def main():
    parser = argparse.ArgumentParser(
        description="Sample instances that are consistently resolved or unresolved across runs"
    )
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Configuration name (e.g., default, monitor)'
    )
    parser.add_argument(
        '--model',
        type=str,
        required=True,
        help='Model name'
    )
    parser.add_argument(
        '--sample_id',
        type=int,
        default=1,
        choices=[1, 2, 3],
        help='Sample ID for reproducibility (1, 2, or 3). Default is 1.'
    )

    args = parser.parse_args()

    # Get project paths
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent.parent  # mini-swe-agent root
    samples_dir = script_dir / "samples" / "reproducible_outcome"

    print("="*60)
    print(f"Sampling Reproducible Instances")
    print("="*60)
    print(f"Config: {args.config}")
    print(f"Model: {args.model}")
    print(f"Sample ID: {args.sample_id}")
    print(f"Seed: {42 + args.sample_id}")
    print("="*60)

    # Load SWE-bench dataset
    print("\nLoading SWE-bench dataset...")
    grouped = load_swebench_dataset()
    print(f"✓ Dataset loaded")

    # Load reports from all 3 runs
    print(f"\nLoading model reports for runs 1-3...")
    reports = []
    for run_id in range(1, 4):
        try:
            report = load_model_report(args.config, args.model, run_id, project_root)
            reports.append(report)
            resolved_count = len(report.get('resolved_ids', []))
            unresolved_count = len(report.get('unresolved_ids', []))
            print(f"  ✓ Run {run_id}: {resolved_count} resolved, {unresolved_count} unresolved")
        except FileNotFoundError as e:
            print(f"\n❌ Error: {e}")
            return

    # Find instances with consistent resolution status
    print(f"\nFinding instances with consistent resolution status...")
    consistent_resolved, consistent_unresolved = find_consistent_instances(grouped, reports)

    print("\nConsistent instances found:")
    for diff in ['easy', 'medium', 'hard', 'very_hard']:
        resolved_count = len(consistent_resolved[diff])
        unresolved_count = len(consistent_unresolved[diff])
        print(f"  {diff}: {resolved_count} resolved, {unresolved_count} unresolved")

    # Sample instances
    print(f"\nSampling {SAMPLES_PER_STATUS} resolved and {SAMPLES_PER_STATUS} unresolved instances...")
    sampled_resolved, sampled_unresolved = stratified_sample_consistent(
        consistent_resolved, consistent_unresolved, args.sample_id
    )

    # Show sampled distribution
    def show_distribution(sampled, status_name):
        distribution = {'easy': 0, 'medium': 0, 'hard': 0, 'very_hard': 0}
        for item in sampled:
            diff = DIFFICULTY_KEYS.get(item['difficulty'])
            if diff:
                distribution[diff] += 1
        print(f"  {status_name}: {len(sampled)} total - " +
              ", ".join(f"{k}: {v}" for k, v in distribution.items() if v > 0))

    print("\nSampled distribution:")
    show_distribution(sampled_resolved, "Resolved")
    show_distribution(sampled_unresolved, "Unresolved")

    # Save all instances to a single file
    output_dir = samples_dir / "swebench" / args.model / str(args.sample_id)
    output_path, total_count = save_samples(sampled_resolved, sampled_unresolved, output_dir)

    print(f"\n✓ Saved {total_count} instances ({len(sampled_resolved)} resolved, {len(sampled_unresolved)} unresolved) to:")
    print(f"  {output_path}")

    print("\n" + "="*60)
    print(f"Total sampled: {total_count} instances")
    print("Sampling completed successfully!")
    print("="*60)


if __name__ == "__main__":
    main()