#!/usr/bin/env python3
"""
Sample instances by programming language from SWE-bench Pro dataset.

This script filters the SWE-bench Pro dataset by language and generates
sampled instances YAML files for use with SWE-agent.

Supported languages: python, go, js, ts

Usage:
    python sample_py_instances.py --dockerhub_username jefzda
    python sample_py_instances.py --dockerhub_username <your-username> --language go --num_samples 50
"""

import argparse
import os
import sys
import yaml
import random
from tqdm import tqdm
from datasets import load_dataset

# Add parent directory to path to import helper functions
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
helper_code_path = os.path.join(os.path.dirname(parent_dir), 'helper_code')
sys.path.insert(0, helper_code_path)

from image_uri import get_dockerhub_image_uri
from create_problem_statement import create_problem_statement

SUPPORTED_LANGUAGES = ['python', 'go', 'js', 'ts']


def sample_instances_by_language(dockerhub_username, language='python', dataset_split='test',
                                  num_samples=None, seed=42):
    """
    Load SWE-bench Pro dataset and filter for specific language instances.

    Args:
        dockerhub_username: Docker Hub username for image URI generation
        language: Programming language to filter (default: python)
        dataset_split: Which split of the dataset to use (default: 'test')
        num_samples: Number of instances to sample (None = all instances of that language)
        seed: Random seed for reproducible sampling

    Returns:
        list: List of instance dictionaries formatted for YAML output
    """
    if language.lower() not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}. Must be one of {SUPPORTED_LANGUAGES}")

    print(f"Loading SWE-bench Pro dataset (split: {dataset_split})...")
    swebench_pro = load_dataset('ScaleAI/SWE-bench_Pro', split=dataset_split)

    # Filter for specified language instances
    print(f"Filtering for {language.upper()} instances...")
    lang_instances = [row for row in swebench_pro
                      if row.get('repo_language', '').lower() == language.lower()]
    print(f"Found {len(lang_instances)} {language.upper()} instances out of {len(swebench_pro)} total")

    # Sample if requested
    if num_samples is not None and num_samples < len(lang_instances):
        print(f"Sampling {num_samples} instances with seed {seed}...")
        random.seed(seed)
        lang_instances = random.sample(lang_instances, num_samples)

    instances = []
    print(f"Processing {len(lang_instances)} instances...")

    for row in tqdm(lang_instances):
        instance_id = row['instance_id']
        repo_name = row.get('repo', '')
        # image_name = get_dockerhub_image_uri(instance_id, dockerhub_username, repo_name)
        image_name = f"{dockerhub_username}/sweap-images:{row['dockerhub_tag']}"
        problem_statement = create_problem_statement(row)

        instance = {
            'image_name': image_name,
            'problem_statement': problem_statement,
            'instance_id': instance_id,
            'base_commit': row['base_commit'],
            'repo_name': 'app'
        }
        instances.append(instance)

    return instances


def write_yaml(instances, output_path):
    """Write instances to YAML file."""
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print(f"Writing {len(instances)} instances to {output_path}...")
    with open(output_path, 'w') as f:
        yaml.dump(instances, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"✓ Successfully generated {output_path}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Sample instances by programming language from SWE-bench Pro',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sample all Python instances (default)
  python sample_py_instances.py --dockerhub_username myusername

  # Sample 100 Go instances
  python sample_py_instances.py --dockerhub_username myusername --language go --num_samples 100

  # Sample JS instances with custom output
  python sample_py_instances.py --dockerhub_username myusername --language js --output_path custom.yaml
        """
    )

    parser.add_argument(
        '--dockerhub_username',
        required=True,
        help='Docker Hub username for generating image URIs'
    )

    parser.add_argument(
        '--language',
        default='python',
        choices=SUPPORTED_LANGUAGES,
        help=f'Programming language to filter (default: python)'
    )

    parser.add_argument(
        '--output_path',
        default=None,
        help='Output path (default: samples/<language>/<dataset>/sampled_instances.yaml)'
    )

    parser.add_argument(
        '--num_samples',
        type=int,
        default=None,
        help='Number of instances to sample (default: all instances of the language)'
    )

    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducible sampling (default: 42)'
    )

    parser.add_argument(
        '--dataset_split',
        default='test',
        help='Dataset split to use (default: test)'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    dataset="swebench-pro"

    # Set default output path if not provided
    if args.output_path is None:
        args.output_path = f'samples/{args.language}/{dataset}/sampled_instances.yaml'

    # Generate language-specific instances
    instances = sample_instances_by_language(
        args.dockerhub_username,
        args.language,
        args.dataset_split,
        args.num_samples,
        args.seed
    )

    # Write to YAML file
    write_yaml(instances, args.output_path)

    print(f"\n✓ Done! Generated {len(instances)} {args.language.upper()} instances.")
    print(f"  Output: {args.output_path}")
    print(f"\nUse with SWE-agent:")
    print(f"  --instances.type file --instances.path {args.output_path}")


if __name__ == "__main__":
    main()
