"""
SWE-Bench Verified difficulty distribution:
Easy: 194, Medium: 261, Hard: 42, Very Hard: 3; Total: 500

Usage:
    python sample_swebench.py [--model MODEL_NAME]

Arguments:
    --model: Optional. If not provided, samples equally from difficulty levels.
                  If provided, samples based on resolution status from model reports
                  and includes original_graphectory path.

Reproducibility:
    To ensure the same samples across runs, use the same run_id (1, 2, or 3).
    Each run_id uses a deterministic seed: seed = 42 + run_id.
    The script runs 3 times (run_id 1-3) by default for reproducibility testing.
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
SAMPLES_PER_DIFFICULTY = 20  # Number of samples per difficulty level
SAMPLES_PER_CATEGORY = SAMPLES_PER_DIFFICULTY // 2  # Split by resolution status


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


def load_model_report(model_name, project_root):
    """Load resolution status from model report."""
    report_path = project_root / "reports" / "default" / "swebench" / model_name / "per_instance_details.json"

    if not report_path.exists():
        raise FileNotFoundError(
            f"Report not found: {report_path}\n"
            f"Please ensure the report exists at the specified path."
        )

    with open(report_path, 'r') as f:
        report = json.load(f)

    return report


def stratified_sample_general(grouped, run_id):
    """
    Sample equally from difficulty levels.
    Samples SAMPLES_PER_DIFFICULTY from each of: easy, medium, hard.
    """
    random.seed(42 + run_id)

    sampled = []
    for diff in ['easy', 'medium', 'hard']:
        count = SAMPLES_PER_DIFFICULTY
        if len(grouped[diff]) < count:
            print(f"  Warning: Not enough {diff} instances. "
                  f"Requested {count}, available {len(grouped[diff])}")
            sampled.extend(grouped[diff])
        else:
            sampled.extend(random.sample(grouped[diff], count))

    random.shuffle(sampled)
    return sampled


def stratified_sample_by_resolution(grouped, report, run_id):
    """
    Sample based on difficulty and resolution status.
    Samples SAMPLES_PER_CATEGORY from each of:
    (easy/medium/hard) × (resolved/unresolved).
    """
    random.seed(42 + run_id)

    # Group instances by difficulty and resolution status
    categorized = {}
    for diff in ['easy', 'medium', 'hard']:
        for status in ['resolved', 'unresolved']:
            categorized[(diff, status)] = []

    for diff in ['easy', 'medium', 'hard']:
        for item in grouped[diff]:
            instance_id = item['instance_id']

            # Check resolution status from report
            if instance_id in report:
                resolved = report[instance_id].get('resolved', False)
                status = 'resolved' if resolved else 'unresolved'
                categorized[(diff, status)].append(item)

    # Sample from each category
    sampled = []
    for diff in ['easy', 'medium', 'hard']:
        for status in ['resolved', 'unresolved']:
            category = (diff, status)
            available = categorized[category]
            count = SAMPLES_PER_CATEGORY

            if len(available) < count:
                print(f"  Warning: Not enough {diff} {status} instances. "
                      f"Requested {count}, available {len(available)}")
                sampled.extend(available)
            else:
                sampled.extend(random.sample(available, count))

    random.shuffle(sampled)
    return sampled


def save_samples(sampled, output_dir, report=None, model_name=None):
    """Save sampled instances to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    output = []
    for x in sampled:
        instance_data = {
            "instance_id": x["instance_id"],
            "difficulty": DIFFICULTY_KEYS.get(x["difficulty"]),
            "repo": x.get("repo", None)
        }

        # Add resolved status and graph path if model is provided
        if report is not None and model_name is not None:
            instance_id = x["instance_id"]
            if instance_id in report:
                instance_data["original_resolved"] = report[instance_id].get('resolved', False)

            # Construct original_graphectory path
            # Format: https://github.com/Intelligent-CAT-Lab/Agent-Planner/tree/main/mini-swe-agent/graphs/swebench/{model}/{instance_id}
            instance_data["original_graphectory"] = (
                f"https://github.com/Intelligent-CAT-Lab/Agent-Planner/tree/main/"
                f"mini-swe-agent/graphs/swebench/{model_name}/{instance_id}"
            )

        output.append(instance_data)

    output_path = output_dir / "sampled_instances.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    return output_path, len(output)


def main():
    parser = argparse.ArgumentParser(
        description="Sample instances from SWE-bench dataset"
    )
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name for resolution-based sampling. If not provided, samples equally from difficulty levels.'
    )
    parser.add_argument(
        '--run_id',
        type=int,
        default=1,
        choices=[1, 2, 3],
        help='Run ID for reproducibility (1, 2, or 3). Each run uses a different seed.'
    )
    parser.add_argument(
        '--dataset',
        type=str,
        default="swebench",
        help='Dataset name (default: swebench). Currently only supports swebench.'
    )

    args = parser.parse_args()

    # Get project paths
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent.parent  # mini-swe-agent root
    samples_dir = script_dir / "samples"

    # Load SWE-bench dataset
    print("Loading SWE-bench dataset...")
    grouped = load_swebench_dataset()

    # Load model report if needed (only once)
    report = None
    if args.model:
        print(f"Loading model report: {args.model}")
        report = load_model_report(args.model, project_root)

    # Run 3 times with different seeds for reproducibility
    for run_id in range(1, 4):
        print(f"\n{'='*60}")
        print(f"Run {run_id}/3")
        print('='*60)

        if args.model:
            # Model-specific sampling based on resolution status
            print(f"Mode: Model-based sampling")
            print(f"Model: {args.model}")
            print(f"Distribution: {SAMPLES_PER_CATEGORY} from each category")
            print(f"  Categories: (easy/medium/hard) × (resolved/unresolved)")

            sampled = stratified_sample_by_resolution(grouped, report, run_id)
            output_dir = samples_dir / args.dataset / args.model / str(run_id)
        else:
            # General sampling: equal distribution across difficulty levels
            print(f"Mode: General sampling")
            print(f"Distribution: {SAMPLES_PER_DIFFICULTY} from each difficulty")
            print(f"  Difficulties: easy, medium, hard")

            sampled = stratified_sample_general(grouped, run_id)
            output_dir = samples_dir / "general" / str(run_id)

        # Save samples
        output_path, count = save_samples(sampled, output_dir, report, args.model)
        print(f"✓ Saved {count} instances to {output_path}")

    print(f"\n{'='*60}")
    print("All runs completed successfully!")
    print('='*60)


if __name__ == "__main__":
    main()
