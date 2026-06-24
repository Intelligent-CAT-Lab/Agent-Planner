"""
Compute plan compliance for refiner interventions.

Usage:
    python analysis/plan-compliance/compute_next_step_plan_compliance.py
    python analysis/plan-compliance/compute_next_step_plan_compliance.py --models deepseek-chat-v3-0324 --datasets swebench
    python analysis/plan-compliance/compute_next_step_plan_compliance.py --test 2
"""

import json
import yaml
import argparse
import os
from pathlib import Path
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from tqdm import tqdm
import time
import tempfile
import shutil


def load_model_registry(registry_path: Path) -> dict:
    """Load model pricing registry."""
    with open(registry_path) as f:
        return json.load(f)


def load_config(config_path: Path, target_model: str) -> dict:
    """Load evaluator configuration and select appropriate judge model."""
    with open(config_path) as f:
        config = yaml.safe_load(f)['evaluator']

    # Select judge model based on target model
    # Use a different model family to avoid bias
    if target_model in ['deepseek-chat-v3-0324', 'gemini-2.5-flash']:
        config['model']['model_name'] = 'minimax/minimax-m3'
    elif target_model == 'minimax-m2.5':
        config['model']['model_name'] = 'openai/gpt-5.2-codex'
    else:
        # Default to gpt-5.2-codex for other models
        config['model']['model_name'] = 'openai/gpt-5.2-codex'

    return config


def load_cache(cache_path: Path) -> dict:
    """Load evaluation cache."""
    if cache_path.exists():
        with open(cache_path) as f:
            cache = json.load(f)
        num_evals = len([k for k in cache.keys() if not k.startswith('_')])
        print(f"Loaded {num_evals} cached evaluations")
        return cache
    return {'_metadata': {'total_cost': 0.0, 'total_input_tokens': 0, 'total_output_tokens': 0}}


def save_cache(cache: dict, cache_path: Path, lock: Lock = None):
    """
    Save evaluation cache atomically with thread safety.
    Uses atomic write (write to temp file, then rename) to prevent corruption.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    def atomic_write():
        # Write to temporary file first
        fd, temp_path = tempfile.mkstemp(dir=cache_path.parent, suffix='.json')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(cache, f, indent=2)
            # Atomic rename (POSIX guarantees atomicity)
            shutil.move(temp_path, cache_path)
        except Exception:
            # Clean up temp file on error
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise

    if lock:
        with lock:
            atomic_write()
    else:
        atomic_write()


def calculate_cost(usage: dict, model_name: str, model_registry: dict) -> float:
    """Calculate cost from usage tokens using model registry."""
    # Handle openrouter/ prefix and normalize model name
    model_key = model_name
    if not model_key.startswith('openrouter/'):
        # Try direct lookup
        if model_key not in model_registry:
            # Try with openrouter prefix
            model_key = f"openrouter/{model_name}"

    if model_key not in model_registry:
        # Fallback: estimate with default pricing
        return 0.0

    pricing = model_registry[model_key]
    input_tokens = usage.get('prompt_tokens', 0)
    output_tokens = usage.get('completion_tokens', 0)

    cost = (input_tokens * pricing['input_cost_per_token'] +
            output_tokens * pricing['output_cost_per_token'])

    return cost


def call_api(messages: list, model_name: str, temperature: float = 0.0) -> tuple[str, dict]:
    """Call OpenRouter API following the pattern from plan_refiner/models.py."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1000,  # Reasoning models (minimax-m3) need more tokens for thinking
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
    message = data["choices"][0]["message"]

    # Handle reasoning models (e.g., minimax-m3)
    # Prefer content (final answer) over reasoning (thinking process)
    content = message.get("content")
    if not content:
        # Fallback to reasoning field if content is null
        content = message.get("reasoning") or ""

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
                         config: dict, cache: dict, cache_key: str, model_registry: dict,
                         cache_lock: Lock = None, verbose: bool = False, skip_cache: bool = False) -> tuple[bool, str, dict]:
    """Evaluate a single intervention. Returns (result, cache_key, usage_info) for batch processing."""
    # Check cache with thread safety (unless skip_cache is True for re-evaluation)
    if not skip_cache:
        if cache_lock:
            with cache_lock:
                if cache_key in cache:
                    return cache[cache_key], cache_key, {}
        elif cache_key in cache:
            return cache[cache_key], cache_key, {}

    prompt = format_prompt(guidance, thought, action, config['prompt'])
    messages = [{"role": "user", "content": prompt}]
    model_name = config['model']['model_name']

    try:
        response, usage = call_api(messages, model_name,
                                   config['model'].get('model_kwargs', {}).get('temperature', 0.0))

        if verbose:
            print(f"\n{'='*60}")
            print(f"Cache key: {cache_key}")
            print(f"Response: {response}")
            print(f"Parsed: {parse_response(response)}")
            print(f"Usage: {usage}")
            print(f"{'='*60}\n")

        result = parse_response(response)

        # Calculate cost
        cost = calculate_cost(usage, model_name, model_registry)
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)

        usage_info = {
            'cost': cost,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }

        # Update cache with thread safety
        if cache_lock:
            with cache_lock:
                cache[cache_key] = result
                # Update metadata
                if '_metadata' not in cache:
                    cache['_metadata'] = {'total_cost': 0.0, 'total_input_tokens': 0, 'total_output_tokens': 0}
                cache['_metadata']['total_cost'] += cost
                cache['_metadata']['total_input_tokens'] += input_tokens
                cache['_metadata']['total_output_tokens'] += output_tokens
        else:
            cache[cache_key] = result
            if '_metadata' not in cache:
                cache['_metadata'] = {'total_cost': 0.0, 'total_input_tokens': 0, 'total_output_tokens': 0}
            cache['_metadata']['total_cost'] += cost
            cache['_metadata']['total_input_tokens'] += input_tokens
            cache['_metadata']['total_output_tokens'] += output_tokens

        return result, cache_key, usage_info

    except Exception as e:
        # Return False on error
        if cache_lock:
            with cache_lock:
                cache[cache_key] = False
        else:
            cache[cache_key] = False
        return False, cache_key, {}


def process_analysis_file(analysis_path: Path, config: dict, cache: dict, cache_path: Path,
                         model_registry: dict, test_mode: int = 0, max_workers: int = 4, save_interval: int = 10,
                         reevaluate: bool = False):
    """Process analysis JSON file and add follows_guidance field."""
    with open(analysis_path) as f:
        data = json.load(f)

    config_name = data['config']
    evaluations = []
    skipped_no_data = 0
    skipped_existing = 0

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

                # Skip if already evaluated (unless reevaluate flag set)
                if 'follows_guidance' in interv and not reevaluate:
                    skipped_existing += 1
                    continue

                guidance = interv.get('content', '')
                action = interv.get('next_action', '')
                thought = interv.get('next_thought', '')

                # Skip if missing guidance
                if not guidance:
                    skipped_no_data += 1
                    # Mark as False for interventions with no action
                    if not action and guidance:
                        interv['follows_guidance'] = False
                    continue

                cache_key = f"{inst['instance_id']}:{interv['step']}"
                evaluations.append((interv, cache_key, guidance, thought, action))

                if test_mode > 0 and len(evaluations) >= test_mode:
                    break

            if test_mode > 0 and len(evaluations) >= test_mode:
                break

        if test_mode > 0 and len(evaluations) >= test_mode:
            break

    print(f"Found {len(evaluations)} interventions to evaluate")
    if skipped_existing > 0:
        print(f"Skipped {skipped_existing} already evaluated")
    if skipped_no_data > 0:
        print(f"Skipped {skipped_no_data} interventions (missing data)")

    if not evaluations:
        print("No new evaluations needed")
        return

    # Evaluate interventions in parallel
    print(f"Evaluating with {max_workers} workers...")
    verbose = test_mode > 0 and len(evaluations) <= 5
    cache_lock = Lock()
    completed_count = 0
    session_cost = 0.0
    session_input_tokens = 0
    session_output_tokens = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_eval = {
            executor.submit(
                evaluate_intervention,
                guidance, thought, action,
                config, cache, cache_key, model_registry,
                cache_lock, verbose, reevaluate  # Pass reevaluate to skip cache
            ): (interv, cache_key)
            for interv, cache_key, guidance, thought, action in evaluations
        }

        # Process results with progress bar
        with tqdm(total=len(evaluations), desc="Evaluating", unit="eval") as pbar:
            for future in as_completed(future_to_eval):
                interv, cache_key = future_to_eval[future]
                try:
                    result, _, usage_info = future.result()
                    interv['follows_guidance'] = result
                    completed_count += 1

                    # Track session usage
                    if usage_info:
                        session_cost += usage_info.get('cost', 0.0)
                        session_input_tokens += usage_info.get('input_tokens', 0)
                        session_output_tokens += usage_info.get('output_tokens', 0)

                    # Periodic cache save (atomic write prevents corruption)
                    if completed_count % save_interval == 0:
                        save_cache(cache, cache_path, cache_lock)

                except Exception as e:
                    if not verbose:
                        tqdm.write(f"Error on {cache_key}: {e}")
                    interv['follows_guidance'] = False
                    with cache_lock:
                        cache[cache_key] = False

                pbar.update(1)

    # Final cache save
    save_cache(cache, cache_path, cache_lock)

    # Save results
    if not test_mode:
        with open(analysis_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved updated analysis to {analysis_path}")
    else:
        print(f"Test mode - not saving analysis file")

    # Print statistics
    follows = sum(1 for e, _, _, _, _ in evaluations if e.get('follows_guidance'))
    print(f"Results: {follows}/{len(evaluations)} follow guidance ({follows/len(evaluations)*100:.1f}%)")

    # Print cost statistics
    if session_cost > 0:
        print(f"Session cost: ${session_cost:.6f} ({session_input_tokens} input + {session_output_tokens} output tokens)")

    # Print total cache statistics
    with cache_lock if cache_lock else Lock():
        metadata = cache.get('_metadata', {})
        total_cost = metadata.get('total_cost', 0.0)
        total_input = metadata.get('total_input_tokens', 0)
        total_output = metadata.get('total_output_tokens', 0)
        if total_cost > 0:
            print(f"Total cumulative cost: ${total_cost:.6f} ({total_input} input + {total_output} output tokens)")


def process_single_config(agent: str, model: str, dataset: str, config_name: str,
                         script_dir: Path, model_registry: dict, test_mode: int, max_workers: int, save_interval: int,
                         reevaluate: bool = False):
    """Process a single model-dataset-config combination."""
    analysis_path = (script_dir / "analysis/analysis-results/comparison/detailed-analysis" /
                    config_name / f"{agent}-{model}-{dataset}-{config_name}-analysis.json")
    evaluator_config_path = script_dir / "analysis/plan-compliance/evaluator.yaml"
    cache_path = script_dir / f"analysis/plan-compliance/.cache/{agent}-{model}-{dataset}-{config_name}.json"

    if not analysis_path.exists():
        print(f"⚠ Skipping {model}/{dataset}/{config_name}: Analysis file not found")
        return

    print(f"\n{'='*80}")
    print(f"Processing: {model} / {dataset} / {config_name}")
    print(f"{'='*80}")
    print(f"Analysis: {analysis_path.name}")
    print(f"Cache: {cache_path.name}")

    # Load config and cache
    config = load_config(evaluator_config_path, model)
    print(f"Judge model: {config['model']['model_name']}")
    cache = load_cache(cache_path)

    # Process analysis file
    process_analysis_file(analysis_path, config, cache, cache_path, model_registry,
                         test_mode, max_workers, save_interval, reevaluate)

    num_evals = len([k for k in cache.keys() if not k.startswith('_')])
    print(f"Cache: {num_evals} total evaluations")


def main():
    parser = argparse.ArgumentParser(
        description='Compute plan compliance for refiner interventions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all default models and datasets
  python analysis/plan-compliance/compute_next_step_plan_compliance.py

  # Process specific model and dataset
  python analysis/plan-compliance/compute_next_step_plan_compliance.py --models deepseek-chat-v3-0324 --datasets swebench

  # Test mode with 2 evaluations
  python analysis/plan-compliance/compute_next_step_plan_compliance.py --test 2
        """
    )
    parser.add_argument('--agent', default='SWE-agent', help='Agent name (default: SWE-agent)')
    parser.add_argument('--models', nargs='+',
                       default=['deepseek-chat-v3-0324', 'gemini-2.5-flash', 'minimax-m2.5'],
                       help='Model names (default: all three models)')
    parser.add_argument('--datasets', nargs='+', default=['swebench', 'swebench-pro'],
                       help='Dataset names (default: swebench swebench-pro)')
    parser.add_argument('--config', default='refiner', choices=['refiner-only', 'refiner', 'monitor'],
                       help='Config type (default: refiner)')
    parser.add_argument('--test', type=int, default=0,
                       help='Test mode: evaluate only N interventions per config')
    parser.add_argument('--max-workers', type=int, default=8,
                       help='Maximum parallel workers (default: 8)')
    parser.add_argument('--save-interval', type=int, default=10,
                       help='Save cache every N evaluations (default: 10)')
    parser.add_argument('--reevaluate', action='store_true',
                       help='Re-evaluate interventions that already have follows_guidance field')
    args = parser.parse_args()

    script_dir = Path(__file__).parent.parent.parent
    evaluator_config_path = script_dir / "analysis/plan-compliance/evaluator.yaml"
    model_registry_path = script_dir / "analysis/plan-compliance/model_registry.json"

    if not evaluator_config_path.exists():
        raise FileNotFoundError(f"Evaluator config not found: {evaluator_config_path}")
    if not model_registry_path.exists():
        raise FileNotFoundError(f"Model registry not found: {model_registry_path}")

    # Load model registry
    model_registry = load_model_registry(model_registry_path)

    # Process all combinations
    total_configs = len(args.models) * len(args.datasets)
    print(f"Processing {total_configs} configurations:")
    print(f"  Models: {', '.join(args.models)}")
    print(f"  Datasets: {', '.join(args.datasets)}")
    print(f"  Config: {args.config}")
    print(f"  Max workers: {args.max_workers}")
    if args.test:
        print(f"  Test mode: {args.test} evaluations per config")

    start_time = time.time()
    processed = 0

    for model in args.models:
        for dataset in args.datasets:
            try:
                process_single_config(
                    args.agent, model, dataset, args.config,
                    script_dir, model_registry, args.test, args.max_workers, args.save_interval,
                    args.reevaluate
                )
                processed += 1
            except Exception as e:
                print(f"\n✗ Error processing {model}/{dataset}: {e}")
                continue

    elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"✓ Completed {processed}/{total_configs} configurations in {elapsed:.1f}s")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
