#!/usr/bin/env python3
"""
Sample instances that consistently demonstrate specific patterns across all vanilla runs.

Analyzes the CSV output from compute_reproducible_patterns.py and identifies instances
that consistently show the same pattern category across all runs. For each pattern
category (plan_compliance, oscillation, dwell, repeated_action), saves sampled instances
with their metadata.

Usage:
    python sample_reproducible_patterns.py --agent <agent_name> --model <model_name> --dataset <dataset_name>

e.g:
    python plan_monitor/simulator/sample_reproducible_patterns.py --agent SWE-agent --model gpt-5-mini --dataset swebench
"""

import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Optional
from datasets import load_dataset

# Mapping from SWE-bench difficulty labels to simplified categories
DIFFICULTY_KEYS = {
    '<15 min fix': 'easy',
    '15 min - 1 hour': 'medium',
    '1-4 hours': 'hard',
    '>4 hours': 'very_hard'
}


def load_swebench_difficulties() -> Dict[str, str]:
    """Load difficulty mapping for SWE-bench instances."""
    dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")

    difficulties = {}
    for item in dataset:
        diff = DIFFICULTY_KEYS.get(item['difficulty'])
        if diff:
            difficulties[item['instance_id']] = diff

    return difficulties


def parse_csv(csv_path: Path) -> Dict[str, Dict]:
    """
    Parse the reproducible patterns CSV file.

    Returns:
        Dict mapping instance_id to run data:
        {
            'instance_id': str,
            'runs': {
                'run-1': {'outcome': str, 'patterns': list, 'step': int, 'cost': float},
                ...
            }
        }
    """
    data = {}

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames

        # Extract run_ids from headers
        run_ids = []
        for header in headers:
            if header.endswith('_outcome'):
                run_id = header.replace('_outcome', '')
                run_ids.append(run_id)

        for row in reader:
            instance_id = row['instance_id']

            runs = {}
            for run_id in run_ids:
                outcome = row.get(f'{run_id}_outcome', '')
                patterns_str = row.get(f'{run_id}_patterns', '')
                step = row.get(f'{run_id}_step', '')
                cost = row.get(f'{run_id}_cost', '')

                # Skip if no data for this run
                if not outcome:
                    continue

                # Parse patterns
                patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]

                runs[run_id] = {
                    'outcome': outcome,
                    'patterns': patterns,
                    'step': int(step) if step else 0,
                    'cost': float(cost) if cost else 0.0
                }

            if runs:
                data[instance_id] = {
                    'instance_id': instance_id,
                    'runs': runs
                }

    return data


def categorize_patterns(patterns: List[str]) -> Set[str]:
    """
    Categorize patterns into high-level categories.

    Returns set of categories: plan_compliance, oscillation, dwell, repeated_action
    """
    categories = set()

    for pattern in patterns:
        if 'plan_compliance' in pattern:
            categories.add('plan_compliance')
        elif 'oscillation' in pattern:
            categories.add('oscillation')
        elif 'dwell' in pattern:
            categories.add('dwell')
        elif 'repeated' in pattern:
            categories.add('repeated_action')

    return categories


def find_consistent_patterns(data: Dict[str, Dict]) -> Dict[str, List[Dict]]:
    """
    Find instances with one or more pattern categories appearing consistently across all runs.

    Inclusion criteria:
    - One or more pattern categories appear in ALL runs (intersection >= 1)
    - Other pattern categories may appear in individual runs (not consistent)

    Example INCLUDED:
    - Run 1: ["dwell", "repeated_action"]
    - Run 2: ["dwell"]
    - Run 3: ["dwell"]
    → "dwell" appears in all runs, included in dwell category

    Example INCLUDED (multiple patterns):
    - Run 1: ["dwell", "plan_compliance"]
    - Run 2: ["dwell", "plan_compliance"]
    - Run 3: ["dwell", "plan_compliance"]
    → TWO patterns appear in all runs, included in "dwell-plan_compliance" category

    Returns:
        Dict mapping pattern_category to list of instance data
        - Single categories: "plan_compliance", "dwell", "oscillation", "repeated_action"
        - Combined categories: "dwell-plan_compliance", "dwell-repeated_action", etc.
    """
    # Pattern category -> list of instances (dynamically populated)
    consistent_patterns = defaultdict(list)

    for instance_id, instance_data in data.items():
        runs = instance_data['runs']

        # Skip if not present in all runs (need consistency across ALL runs)
        run_ids = sorted(runs.keys())
        if len(run_ids) == 0:
            continue

        # Get pattern categories for each run
        run_categories = []
        for run_id in run_ids:
            run_data = runs[run_id]
            categories = categorize_patterns(run_data['patterns'])
            run_categories.append(categories)

        # Find patterns that appear in ALL runs (intersection)
        if run_categories:
            # Intersection: pattern categories that appear in ALL runs
            consistent_cats = set.intersection(*run_categories) if run_categories else set()

            # Include instances with one or more consistent pattern categories
            if len(consistent_cats) >= 1:
                # Create category key: single category or sorted hyphenated combination
                if len(consistent_cats) == 1:
                    category_key = list(consistent_cats)[0]
                else:
                    # Multiple categories: sort and join with hyphen
                    category_key = '-'.join(sorted(consistent_cats))

                consistent_patterns[category_key].append({
                    'instance_id': instance_id,
                    'runs': runs,
                    'run_ids': run_ids
                })

    return consistent_patterns


def analyze_and_print_statistics(consistent_patterns: Dict[str, List[Dict]], data: Dict[str, Dict]):
    """Print statistics for each pattern category."""
    print("\n" + "="*80)
    print("CONSISTENT PATTERN ANALYSIS")
    print("="*80)

    # Sort categories: single categories first, then combined
    def category_sort_key(cat):
        # Single categories come first (no hyphen), then combined (with hyphen)
        if '-' in cat:
            return (1, cat)  # Combined categories
        else:
            return (0, cat)  # Single categories

    sorted_categories = sorted(consistent_patterns.keys(), key=category_sort_key)

    # Global rule distribution across all instances
    global_rule_distribution = defaultdict(int)

    for category in sorted_categories:
        instances = consistent_patterns[category]

        if not instances:
            continue

        print(f"\n[{category.upper()}]")
        print(f"  Total instances: {len(instances)}")

        # Break down by specific rule_id (count instances with consistent rule_id across all runs)
        rule_breakdown = defaultdict(int)

        for instance in instances:
            runs = instance['runs']
            run_ids = sorted(runs.keys())

            # Collect patterns per run for this instance
            patterns_per_run = []
            for run_id in run_ids:
                run_patterns = set(runs[run_id]['patterns'])
                patterns_per_run.append(run_patterns)

            # Find specific patterns that appear in ALL runs
            consistent_specific_patterns = set.intersection(*patterns_per_run) if patterns_per_run else set()

            # Count instances with each consistent specific rule
            for pattern in consistent_specific_patterns:
                rule_breakdown[pattern] += 1
                global_rule_distribution[pattern] += 1

        if rule_breakdown:
            print(f"  Rule breakdown:")
            for rule_id, count in sorted(rule_breakdown.items(), key=lambda x: -x[1]):
                print(f"    {rule_id}: {count}")

    # Print pattern class distribution (count unique instances per class)
    if global_rule_distribution:
        print(f"\n[PATTERN CLASS DISTRIBUTION]")
        total_instances_set = set()
        for instances in consistent_patterns.values():
            for instance in instances:
                total_instances_set.add(instance['instance_id'])
        print(f"  Total instances with consistent patterns: {len(total_instances_set)}")
        print(f"  Pattern classes (can co-occur):")

        # Track instances per class and specific patterns within each class
        class_to_instances = defaultdict(set)
        class_to_patterns = defaultdict(lambda: defaultdict(set))

        for category in sorted_categories:
            instances = consistent_patterns[category]
            for instance in instances:
                instance_id = instance['instance_id']
                runs = instance['runs']
                run_ids = sorted(runs.keys())

                # Collect patterns per run
                patterns_per_run = []
                for run_id in run_ids:
                    run_patterns = set(runs[run_id]['patterns'])
                    patterns_per_run.append(run_patterns)

                # Find specific patterns that appear in ALL runs
                consistent_specific_patterns = set.intersection(*patterns_per_run) if patterns_per_run else set()

                # Categorize and track
                for pattern in consistent_specific_patterns:
                    rule_categories = categorize_patterns([pattern])
                    for cat in rule_categories:
                        class_to_instances[cat].add(instance_id)
                        class_to_patterns[cat][pattern].add(instance_id)

        # Print class distribution
        for cat in sorted(class_to_instances.keys(), key=lambda x: -len(class_to_instances[x])):
            count = len(class_to_instances[cat])
            print(f"    {cat}: {count} instances")
            # Print specific patterns within this class
            patterns_in_class = class_to_patterns[cat]
            for pattern, inst_set in sorted(patterns_in_class.items(), key=lambda x: -len(x[1])):
                print(f"      {pattern}: {len(inst_set)}")


def prepare_sample_data(
    consistent_patterns: Dict[str, List[Dict]],
    dataset: str,
    difficulties: Optional[Dict[str, str]] = None
) -> Dict[str, List[Dict]]:
    """
    Prepare sample data for each pattern category.

    Returns:
        Dict mapping pattern_category to list of sample records
    """
    sample_data = {}

    for category, instances in consistent_patterns.items():
        if not instances:
            sample_data[category] = []
            continue

        category_samples = []

        for instance in instances:
            instance_id = instance['instance_id']
            runs = instance['runs']
            run_ids = sorted(runs.keys())

            # Collect data across all runs
            original_resolved = []
            original_steps = []
            original_cost = []
            original_patterns = []

            for run_id in run_ids:
                run_data = runs[run_id]
                original_resolved.append(run_data['outcome'] == 'resolved')
                original_steps.append(run_data['step'])
                original_cost.append(run_data['cost'])
                original_patterns.append(run_data['patterns'])

            # Build sample record
            sample_record = {
                'instance_id': instance_id,
                'original_resolved': original_resolved,
                'original_steps': original_steps,
                'original_cost': original_cost,
                'original_patterns': original_patterns
            }

            # Add difficulty for swebench
            if dataset == 'swebench' and difficulties:
                sample_record['difficulty'] = difficulties.get(instance_id, 'unknown')

            category_samples.append(sample_record)

        sample_data[category] = category_samples

    return sample_data


def save_samples(
    sample_data: Dict[str, List[Dict]],
    agent: str,
    dataset: str,
    model: str
):
    """Save sample data for each pattern category and combined all_patterns."""
    # Determine agent base directory
    current = Path(__file__).resolve()

    # For swebench-pro, use SWE-bench_Pro-os/{agent}
    if dataset == "swebench-pro":
        agent_dir_name = f"SWE-bench_Pro-os/{agent}"
    else:
        agent_dir_name = agent

    agent_base = None
    for parent in current.parents:
        # Handle nested path (e.g., "SWE-bench_Pro-os/SWE-agent")
        if "/" in agent_dir_name:
            parts = agent_dir_name.split("/")
            candidate = parent
            for part in parts:
                candidate = candidate / part
        else:
            candidate = parent / agent_dir_name

        if candidate.exists() and (candidate / "script").exists():
            agent_base = candidate
            break

    if agent_base is None:
        raise ValueError(f"Could not find {agent_dir_name} directory with script/ subdirectory")

    output_base = agent_base / "script" / "sample-data" / "samples" / "reproducible_patterns"

    saved_paths = []

    # Track all unique instances across all categories (union)
    all_instances = {}

    for category, samples in sample_data.items():
        if not samples:
            continue

        # Create output directory
        output_dir = output_base / dataset / model / category
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        output_path = output_dir / "sampled_instances.json"
        with open(output_path, 'w') as f:
            json.dump(samples, f, indent=2)

        saved_paths.append((category, output_path, len(samples)))
        print(f"  ✓ {category}: {len(samples)} instances saved to {output_path}")

        # Add to all_instances (union across all categories)
        for sample in samples:
            instance_id = sample['instance_id']
            if instance_id not in all_instances:
                all_instances[instance_id] = sample

    # Save all_patterns/sampled_instances.json (union of all categories)
    if all_instances:
        all_patterns_dir = output_base / dataset / model / "all_patterns"
        all_patterns_dir.mkdir(parents=True, exist_ok=True)

        all_patterns_path = all_patterns_dir / "sampled_instances.json"
        all_samples = list(all_instances.values())

        with open(all_patterns_path, 'w') as f:
            json.dump(all_samples, f, indent=2)

        saved_paths.append(("all_patterns", all_patterns_path, len(all_samples)))
        print(f"  ✓ all_patterns: {len(all_samples)} instances saved to {all_patterns_path}")

    return saved_paths


def main():
    parser = argparse.ArgumentParser(
        description="Sample instances with consistent patterns across runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze default config with gpt-5-mini
  python plan_monitor/simulator/sample_reproducible_patterns.py --model gpt-5-mini

  # Analyze monitor config with deepseek model
  python plan_monitor/simulator/sample_reproducible_patterns.py --config monitor --model deepseek-chat-v3-0324
        """
    )
    parser.add_argument(
        '--agent',
        type=str,
        default='mini-swe-agent',
        help='Agent name (default: mini-swe-agent)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='default',
        help='Configuration name (default: default)'
    )
    parser.add_argument(
        '--dataset',
        type=str,
        default='swebench',
        help='Dataset name (default: swebench)'
    )
    parser.add_argument(
        '--model',
        type=str,
        required=True,
        help='Model name (e.g., gpt-5-mini)'
    )

    args = parser.parse_args()

    # Input CSV path
    csv_path = Path("stats") / "vanilla_reproducible_patterns" / f"{args.dataset}_{args.agent}_{args.model}.csv"

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        print(f"Please run compute_reproducible_patterns.py first to generate the CSV.")
        return 1

    print("="*80)
    print(f"Sampling Reproducible Patterns")
    print("="*80)
    print(f"Agent: {args.agent}")
    print(f"Config: {args.config}")
    print(f"Dataset: {args.dataset}")
    print(f"Model: {args.model}")
    print(f"Input CSV: {csv_path}")
    print("="*80)

    # Load difficulty mapping for swebench
    difficulties = None
    if args.dataset == 'swebench':
        print("\nLoading SWE-bench difficulty mapping...")
        difficulties = load_swebench_difficulties()
        print(f"✓ Loaded {len(difficulties)} instance difficulties")

    # Parse CSV
    print(f"\nParsing CSV file...")
    data = parse_csv(csv_path)
    print(f"✓ Parsed {len(data)} instances")

    # Find consistent patterns
    print(f"\nFinding consistent patterns across all runs...")
    consistent_patterns = find_consistent_patterns(data)

    # Print statistics
    analyze_and_print_statistics(consistent_patterns, data)

    # Prepare sample data
    print(f"\nPreparing sample data...")
    sample_data = prepare_sample_data(consistent_patterns, args.dataset, difficulties)

    # Save samples
    print(f"\nSaving samples...")
    saved_paths = save_samples(sample_data, args.agent, args.dataset, args.model)

    if not saved_paths:
        print("\n⚠ No consistent patterns found. No samples saved.")
    else:
        print(f"\n" + "="*80)
        print(f"Sampling completed successfully!")
        print(f"Saved {len(saved_paths)} pattern categories")
        print("="*80)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
