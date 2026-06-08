#!/usr/bin/env python3
"""Test cost calculation with custom litellm model registry."""

import json
import litellm

# Load custom registry
with open("litellm_model_registry.json") as f:
    model_costs = json.load(f)
    litellm.register_model(model_costs)

# Test model
model_name = "openrouter/deepseek/deepseek-chat-v3-0324"

# Check if model is registered
if model_name in litellm.model_cost:
    print(f"✓ Model '{model_name}' found in litellm.model_cost")
    model_info = litellm.model_cost[model_name]
    print(f"  Input cost per token: ${model_info['input_cost_per_token']}")
    print(f"  Output cost per token: ${model_info['output_cost_per_token']}")
    print(f"  Max input tokens: {model_info['max_input_tokens']}")
    print(f"  Max output tokens: {model_info['max_output_tokens']}")
    print(f"  Provider: {model_info['litellm_provider']}")

    # Test cost calculation
    input_tokens = 1000
    output_tokens = 500
    estimated_cost = (
        input_tokens * model_info['input_cost_per_token'] +
        output_tokens * model_info['output_cost_per_token']
    )
    print(f"\n  Example cost for 1000 input + 500 output tokens: ${estimated_cost:.6f}")
else:
    print(f"✗ Model '{model_name}' NOT found in litellm.model_cost")
    print(f"  Available models: {list(litellm.model_cost.keys())[:5]}...")
