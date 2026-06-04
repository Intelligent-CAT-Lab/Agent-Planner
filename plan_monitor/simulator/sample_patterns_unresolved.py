#!/usr/bin/env python3
"""
Sample unresolved instances with patterns from run 1.

Analyzes the CSV output from compute_reproducible_patterns.py and identifies instances
that are unresolved in run 1 and have at least one pattern. Saves sampled instances
with their metadata.

Usage:
    python sample_patterns_unresolved.py --agent <agent_name> --model <model_name> --dataset <dataset_name>

e.g:
    python plan_monitor/simulator/sample_patterns_unresolved.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench-pro
"""

import csv
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
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
        Dict mapping instance_id to run data
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


def find_unresolved_with_patterns(data: Dict[str, Dict], run_id: str = '1') -> List[Dict]:
    """
    Find instances that are unresolved in the specified run and have at least one pattern.

    Args:
        data: Parsed CSV data
        run_id: Run ID to check (default: '1', also tries 'run-1', 'run_1')

    Returns:
        List of instances matching criteria
    """
    unresolved_instances = []

    # Try multiple run_id formats
    possible_run_ids = [run_id, f"run-{run_id}", f"run_{run_id}"]
    if run_id.startswith("run-") or run_id.startswith("run_"):
        # If already prefixed, also try without prefix
        run_num = run_id.split("-")[-1].split("_")[-1]
        possible_run_ids.append(run_num)

    for instance_id, instance_data in data.items():
        runs = instance_data['runs']

        # Find which run_id format exists
        matched_run_id = None
        for rid in possible_run_ids:
            if rid in runs:
                matched_run_id = rid
                break

        if matched_run_id is None:
            continue

        run_data = runs[matched_run_id]

        # Check if unresolved and has patterns
        if run_data['outcome'] == 'unresolved' and len(run_data['patterns']) > 0:
            unresolved_instances.append({
                'instance_id': instance_id,
                'run_data': run_data
            })

    return unresolved_instances


def prepare_sample_data(
    unresolved_instances: List[Dict],
    dataset: str,
    difficulties: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """
    Prepare sample data for unresolved instances with patterns.

    Returns:
        List of sample records
    """
    samples = []

    for instance in unresolved_instances:
        instance_id = instance['instance_id']
        run_data = instance['run_data']

        # Build sample record
        sample_record = {
            'instance_id': instance_id,
            'original_resolved': run_data['outcome'] == 'resolved',
            'original_steps': run_data['step'],
            'original_cost': run_data['cost'],
            'original_patterns': run_data['patterns']
        }

        # Add difficulty for swebench
        if dataset == 'swebench' and difficulties:
            sample_record['difficulty'] = difficulties.get(instance_id, 'unknown')

        samples.append(sample_record)

    return samples


def save_samples(
    samples: List[Dict],
    agent: str,
    dataset: str,
    model: str
):
    """Save sample data for unresolved instances with patterns."""
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

    output_dir = agent_base / "script" / "sample-data" / "samples" / "patterns_unresolved" / dataset / model
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    output_path = output_dir / "sampled_instances.json"
    with open(output_path, 'w') as f:
        json.dump(samples, f, indent=2)

    print(f"✓ Saved {len(samples)} instances to {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Sample unresolved instances with patterns from run 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sample unresolved instances with patterns
  python plan_monitor/simulator/sample_patterns_unresolved.py --agent mini-swe-agent --model gpt-5-mini

  # Sample from SWE-agent
  python plan_monitor/simulator/sample_patterns_unresolved.py --agent SWE-agent --model deepseek-chat-v3-0324
        """
    )
    parser.add_argument(
        '--agent',
        type=str,
        default='SWE-agent',
        help='Agent name (default: SWE-agent)'
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
    parser.add_argument(
        '--run-id',
        type=str,
        default='1',
        help='Run ID to sample from (default: 1)'
    )

    args = parser.parse_args()

    # Input CSV path
    csv_path = Path("stats") / "vanilla_reproducible_patterns" / f"{args.dataset}_{args.agent}_{args.model}.csv"

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        print(f"Please run compute_reproducible_patterns.py first to generate the CSV.")
        return 1

    print("="*80)
    print(f"Sampling Unresolved Instances with Patterns")
    print("="*80)
    print(f"Agent: {args.agent}")
    print(f"Dataset: {args.dataset}")
    print(f"Model: {args.model}")
    print(f"Run ID: {args.run_id}")
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

    # Find unresolved instances with patterns
    print(f"\nFinding unresolved instances with patterns in run {args.run_id}...")
    unresolved_instances = find_unresolved_with_patterns(data, run_id=args.run_id)
    print(f"✓ Found {len(unresolved_instances)} unresolved instances with patterns")

    if not unresolved_instances:
        print("\n⚠ No unresolved instances with patterns found.")
        return 1

    # Prepare sample data
    print(f"\nPreparing sample data...")
    samples = prepare_sample_data(unresolved_instances, args.dataset, difficulties)

    # Save samples
    print(f"\nSaving samples...")
    output_path = save_samples(samples, args.agent, args.dataset, args.model)

    print(f"\n" + "="*80)
    print(f"Sampling completed successfully!")
    print(f"Total samples: {len(samples)}")
    print("="*80)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
