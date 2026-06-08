#!/usr/bin/env python3
"""Test model initialization with custom litellm registry."""

import os
os.environ['OPENROUTER_API_KEY'] = 'test-key'

from sweagent.agent.models import ModelConfig, LanguageModelAdapter

# Create config with custom registry
config = ModelConfig(
    name="openrouter/deepseek/deepseek-chat-v3-0324",
    api_base="https://openrouter.ai/api/v1",
    api_key="test-key",
    litellm_model_registry="litellm_model_registry.json",
    per_instance_cost_limit=2.0,
    total_cost_limit=100.0
)

print(f"✓ ModelConfig created successfully")
print(f"  Model: {config.name}")
print(f"  Registry: {config.litellm_model_registry}")
print(f"  Cost limit: ${config.per_instance_cost_limit}")

# Try to initialize the model adapter (will fail at API call but should pass config init)
try:
    model = LanguageModelAdapter(config)
    print(f"\n✓ LanguageModelAdapter initialized successfully")
    print(f"  Max input tokens: {model.model_max_input_tokens}")
    print(f"  Max output tokens: {model.model_max_output_tokens}")
    print(f"  Provider: {model.lm_provider}")
except Exception as e:
    print(f"\n✗ LanguageModelAdapter initialization failed: {e}")
