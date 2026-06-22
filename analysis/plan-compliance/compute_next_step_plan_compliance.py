"""
Compute plan compliance for refiner interventions.

Usage:
    python analysis/plan-compliance/compute_plan_compliance.py --model deepseek-chat-v3-0324 --dataset swebench
    python analysis/plan-compliance/compute_plan_compliance.py --model deepseek-chat-v3-0324 --dataset swebench --test 2
"""

import json
import yaml
import argparse
import os
from pathlib import Path
import requests


def load_config(config_path: Path) -> dict:
    """Load evaluator configuration."""
    with open(config_path) as f:
        return yaml.safe_load(f)['evaluator']


def load_cache(cache_path: Path) -> dict:
    """Load evaluation cache."""
    if cache_path.exists():
        with open(cache_path) as f:
            cache = json.load(f)
        print(f"Loaded {len(cache)} cached evaluations")
        return cache
    return {}


def save_cache(cache: dict, cache_path: Path):
    """Save evaluation cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2)


def call_api(messages: list, model_name: str, temperature: float = 0.0) -> tuple[str, dict]:
    """Call OpenRouter API following the pattern from plan_refiner/models.py."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 100,  # Enough for "True" or "False" with reasoning tokens
        "usage": {"include": True},  # Request usage information
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),  # Use data= with json.dumps, not json=
        timeout=60
    )

    if not response.ok:
        try:
            error_data = response.json()
            raise RuntimeError(f"API error {response.status_code}: {error_data}")
        except json.JSONDecodeError:
            raise RuntimeError(f"API error {response.status_code}: {response.text}")

    data = response.json()
    content = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage", {})

    return content, usage


def parse_response(response: str) -> bool:
    """Parse True/False from response."""
    if not response:
        return False
    return 'true' in response.strip().lower()


def format_prompt(guidance: str, thought: str, action: str, prompt_template: str) -> str:
    """Format evaluation prompt."""
    prompt = prompt_template.replace('{THOUGHT}', thought).replace('{ACTION}', action)
    return f"<guidance>\n{guidance}\n</guidance>\n\n{prompt}"


def evaluate_intervention(guidance: str, thought: str, action: str,
                         config: dict, cache: dict, cache_key: str, verbose: bool = False) -> bool:
    """Evaluate a single intervention."""
    if cache_key in cache:
        return cache[cache_key]

    prompt = format_prompt(guidance, thought, action, config['prompt'])
    messages = [{"role": "user", "content": prompt}]

    response, usage = call_api(messages, config['model']['model_name'],
                               config['model'].get('model_kwargs', {}).get('temperature', 0.0))

    if verbose:
        print(f"\n{'='*60}")
        print(f"Cache key: {cache_key}")
        print(f"Response: {response}")
        print(f"Parsed: {parse_response(response)}")
        print(f"{'='*60}\n")

    result = parse_response(response)
    cache[cache_key] = result

    return result


def process_analysis_file(analysis_path: Path, config: dict, cache: dict, test_mode: int = 0):
    """Process analysis JSON file and add follows_guidance field."""
    with open(analysis_path) as f:
        data = json.load(f)

    config_name = data['config']
    evaluations = []
    processed = 0
    skipped_no_data = 0

    # Collect interventions to evaluate
    for category in ['R-R', 'R-U', 'U-R', 'U-U']:
        if category not in data.get('category_details', {}):
            continue

        for inst in data['category_details'][category].get('instances', []):
            if not inst.get(config_name, {}).get('has_planner'):
                continue

            interventions = inst[config_name].get('planner_stats', {}).get('interventions', [])

            for interv in interventions:
                if interv.get('planner_type') != 'refiner':
                    continue

                # Skip if already evaluated
                if 'follows_guidance' in interv:
                    continue

                guidance = interv.get('content', '')
                action = interv.get('next_action', '')
                thought = interv.get('next_thought', '')

                if not guidance or not action:
                    skipped_no_data += 1
                    continue

                cache_key = f"{inst['instance_id']}:{interv['step']}"
                evaluations.append((interv, cache_key, guidance, thought, action))

                if test_mode > 0 and len(evaluations) >= test_mode:
                    break

            if test_mode > 0 and len(evaluations) >= test_mode:
                break

        if test_mode > 0 and len(evaluations) >= test_mode:
            break

    print(f"\nFound {len(evaluations)} interventions to evaluate")
    if skipped_no_data > 0:
        print(f"Skipped {skipped_no_data} interventions (missing data)")

    if not evaluations:
        print("No new evaluations needed")
        return

    # Evaluate interventions
    print("\nEvaluating interventions...")
    verbose = test_mode > 0  # Show details in test mode
    for i, (interv, cache_key, guidance, thought, action) in enumerate(evaluations):
        try:
            result = evaluate_intervention(guidance, thought, action, config, cache, cache_key, verbose)
            interv['follows_guidance'] = result
            processed += 1

            if not verbose and ((i + 1) % 10 == 0 or (i + 1) == len(evaluations)):
                print(f"  {i + 1}/{len(evaluations)} completed")

        except Exception as e:
            print(f"  Error on evaluation {i + 1}: {e}")
            interv['follows_guidance'] = False
            cache[cache_key] = False

    # Save results
    if not test_mode:
        with open(analysis_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved updated analysis to {analysis_path}")
    else:
        print(f"\nTest mode - not saving to file")

    # Print statistics
    follows = sum(1 for e, _, _, _, _ in evaluations if e.get('follows_guidance'))
    print(f"\nResults: {follows}/{len(evaluations)} follow guidance ({follows/len(evaluations)*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description='Compute plan compliance for refiner interventions')
    parser.add_argument('--agent', default='SWE-agent', help='Agent name')
    parser.add_argument('--model', required=True, help='Model name')
    parser.add_argument('--dataset', default='swebench', help='Dataset name')
    parser.add_argument('--config', default='refiner', choices=['refiner', 'monitor'])
    parser.add_argument('--test', type=int, default=0, help='Test mode: evaluate only N interventions')
    args = parser.parse_args()

    # Setup paths
    script_dir = Path(__file__).parent.parent.parent
    analysis_path = (script_dir / "analysis/analysis-results/comparison/detailed-analysis" /
                    args.config / f"{args.agent}-{args.model}-{args.dataset}-{args.config}-analysis.json")
    evaluator_config_path = script_dir / "analysis/plan-compliance/evaluator.yaml"
    cache_path = script_dir / f"analysis/plan-compliance/.cache/{args.agent}-{args.model}-{args.dataset}-{args.config}.json"

    if not analysis_path.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_path}")
    if not evaluator_config_path.exists():
        raise FileNotFoundError(f"Evaluator config not found: {evaluator_config_path}")

    print(f"Analysis file: {analysis_path}")
    print(f"Cache file: {cache_path}")
    if args.test:
        print(f"Test mode: evaluating only {args.test} interventions")

    # Load config and cache
    config = load_config(evaluator_config_path)
    cache = load_cache(cache_path)

    # Process analysis file
    process_analysis_file(analysis_path, config, cache, args.test)

    # Save cache
    save_cache(cache, cache_path)
    print(f"\nCache saved: {len(cache)} evaluations")


if __name__ == "__main__":
    main()
