"""
Model interfaces for plan refiner.

Provides implementations of ModelProtocol for different LLM backends.
"""

from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from plan_refiner.utils.cache_control import set_cache_control

logger = logging.getLogger("plan_refiner.models")


class MockModel:
    """
    Mock model for testing.

    Returns a structured response that follows the expected format.
    """

    def query(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        """
        Generate a mock response.

        Args:
            system_prompt: System prompt (unused)
            user_prompt: User prompt (used to extract context)

        Returns:
            Tuple of (mock structured response, usage dict with token counts)
        """
        response = """<analysis>

### 1. Inferred High-Level Plan So Far
Based on the trajectory, the agent appears to be following this plan:
1. Explored the codebase to understand the relevant files
2. Attempted to reproduce the issue
3. Made modifications to fix the bug
4. Ran tests to validate the fix

### 2. Evaluation of the Plan's Logic
The plan follows a reasonable L → P → V workflow. However, there may be
gaps in understanding the root cause before applying the patch. The agent
should ensure proper reproduction before moving to patching.

### 3. Review of Implementation and Final Code
The implementation shows good exploration patterns. However, some commands
were repeated unnecessarily, indicating potential oscillation. The final
patch addresses the surface issue but may not handle edge cases.

</analysis>

<new_plan>

### Customized High-Level Plan

1. Re-run or create a focused test that clearly demonstrates
   the bug described in the issue. Confirm the failure mode matches expectations.

2. Inspect the relevant implementation files to understand
   the logic flow and identify the exact location where the buggy behavior originates.

3. Apply a minimal, targeted fix to address the root cause identified
   in step. Ensure the fix is consistent with the existing code patterns.

4. Verify the fix resolves the issue by running
   the reproduction test and confirming it now passes.

5. Run the broader test suite to ensure no regressions
   were introduced by the change.

</new_plan>"""

        # Mock usage information
        usage_info = {
            "input_tokens": 1000,  # Mock values
            "output_tokens": 500,
            "total_tokens": 1500,
            "cost": 0.015  # Mock cost (e.g., $0.015)
        }

        return response, usage_info


@dataclass
class OpenRouterModelConfig:
    """Configuration for OpenRouter model."""
    model_name: str
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    set_cache_control: Literal["default_end"] | None = None
    """Set explicit cache control markers"""


class OpenRouterAPIError(Exception):
    """Custom exception for OpenRouter API errors."""
    pass


class OpenRouterAuthenticationError(Exception):
    """Custom exception for OpenRouter authentication errors."""
    pass


class OpenRouterRateLimitError(Exception):
    """Custom exception for OpenRouter rate limit errors."""
    pass


class OpenRouterModel:
    """
    OpenRouter API model interface.

    Follows the same pattern as mini-swe-agent's OpenRouterModel.
    """

    def __init__(
        self,
        model_name: str,
        model_kwargs: dict[str, Any] = None,
        set_cache_control: Literal["default_end"] | None = None,
        **kwargs
    ):
        """
        Initialize OpenRouter model.

        Args:
            model_name: Model name (e.g., "openai/gpt-5-mini")
            model_kwargs: Additional model parameters
            set_cache_control: Cache control mode for efficiency (e.g., "default_end")
            **kwargs: Additional configuration
        """
        self.config = OpenRouterModelConfig(
            model_name=model_name,
            model_kwargs=model_kwargs or {},
            set_cache_control=set_cache_control
        )
        self._api_url = "https://openrouter.ai/api/v1/chat/completions"
        self._api_key = os.getenv("OPENROUTER_API_KEY", "")

        # Track cost and calls like mini-swe-agent models
        self.cost = 0.0
        self.n_calls = 0

        # Load model pricing registry for cost computation
        self._model_registry = self._load_model_registry()

        if not self._api_key:
            logger.warning(
                "OPENROUTER_API_KEY not set. Set it with: "
                "export OPENROUTER_API_KEY=your_key"
            )

    def _load_model_registry(self) -> dict:
        """Load model pricing registry for cost computation."""
        import plan_refiner
        registry_path = Path(plan_refiner.__file__).parent / "config" / "model_registry.json"

        if not registry_path.exists():
            logger.warning(f"Model registry not found at {registry_path}")
            return {}

        try:
            with open(registry_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load model registry: {e}")
            return {}

    def _compute_cost_from_tokens(self, usage: dict) -> float:
        """
        Compute cost from token counts when API doesn't provide it.

        Args:
            usage: Usage dict with token counts

        Returns:
            Computed cost in dollars
        """
        model_name = self.config.model_name

        # Check if model is in registry
        if model_name not in self._model_registry:
            logger.warning(f"Model {model_name} not in registry. Cannot compute cost.")
            return 0.0

        pricing = self._model_registry[model_name]

        # Extract token counts
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # Handle cache tokens if present (Anthropic models)
        cache_creation_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        cache_read_tokens = usage.get("prompt_tokens_details", {}).get("cache_read_tokens", 0)

        # Compute cost
        cost = 0.0

        # Input tokens (excluding cache)
        regular_input_tokens = input_tokens - cache_creation_tokens - cache_read_tokens
        cost += regular_input_tokens * pricing.get("input_cost_per_token", 0)

        # Output tokens
        cost += output_tokens * pricing.get("output_cost_per_token", 0)

        # Cache write tokens (if applicable)
        if cache_creation_tokens > 0:
            cost += cache_creation_tokens * pricing.get("cache_write_cost_per_token",
                                                        pricing.get("input_cost_per_token", 0))

        # Cache read tokens (if applicable)
        if cache_read_tokens > 0:
            cost += cache_read_tokens * pricing.get("cache_read_cost_per_token", 0)

        return cost

    @retry(
        stop=stop_after_attempt(int(os.getenv("PLAN_REFINER_RETRY_ATTEMPTS", "3"))),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        retry=retry_if_not_exception_type(
            (
                OpenRouterAuthenticationError,
                KeyboardInterrupt,
            )
        ),
    )
    def _query_api(self, messages: list[dict[str, str]], **kwargs):
        """
        Query OpenRouter API with retry logic.

        Args:
            messages: List of message dicts
            **kwargs: Additional parameters

        Returns:
            API response JSON
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "usage": {"include": True},  # Request cost information from OpenRouter
            **(self.config.model_kwargs | kwargs),
        }

        try:
            response = requests.post(
                self._api_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                error_msg = (
                    "Authentication failed. Set OPENROUTER_API_KEY environment variable."
                )
                raise OpenRouterAuthenticationError(error_msg) from e
            elif response.status_code == 429:
                raise OpenRouterRateLimitError("Rate limit exceeded") from e
            else:
                raise OpenRouterAPIError(
                    f"HTTP {response.status_code}: {response.text}"
                ) from e
        except requests.exceptions.RequestException as e:
            raise OpenRouterAPIError(f"Request failed: {e}") from e

    def query(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        """
        Query the model with system and user prompts.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt

        Returns:
            Tuple of (model response text, usage dict with token counts and cost)
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Apply cache control if configured for efficiency
        if self.config.set_cache_control:
            messages = set_cache_control(messages, mode=self.config.set_cache_control)

        response = self._query_api(messages)

        # Extract content from response
        content = response["choices"][0]["message"]["content"] or ""

        # Extract usage information (tokens and cost)
        usage = response.get("usage", {})

        # Debug: Log the raw usage data to diagnose issues
        if not usage:
            logger.error(
                f"No usage data in API response for model {self.config.model_name}. "
                f"Response keys: {list(response.keys())}"
            )

        # Extract token counts
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # Debug: Log token counts to diagnose "output_tokens is 0" issue
        if output_tokens == 0 and content:
            logger.warning(
                f"Output tokens is 0 but content is non-empty (length: {len(content)}). "
                f"Raw usage data: {usage}"
            )

        # Extract cost from OpenRouter response (preferred)
        cost = usage.get("cost", 0.0)
        assert cost >= 0.0, f"Cost is negative: {cost}"

        # If cost not available from API, compute from token counts using model registry
        if cost == 0.0 and (input_tokens > 0 or output_tokens > 0):
            computed_cost = self._compute_cost_from_tokens(usage)
            if computed_cost > 0.0:
                cost = computed_cost
                logger.info(
                    f"Cost not provided by API for {self.config.model_name}. "
                    f"Computed from token counts: ${cost:.6f} "
                    f"(input: {input_tokens}, output: {output_tokens})"
                )
            else:
                logger.warning(
                    f"Cost not provided by API and cannot compute for {self.config.model_name}. "
                    f"Model may not be in registry."
                )
        elif cost == 0.0:
            logger.warning(
                f"No cost or token information available from API for {self.config.model_name}."
            )

        # Track cost and calls
        self.n_calls += 1
        self.cost += cost

        usage_info = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost": cost
        }

        return content, usage_info


# Legacy model classes for backward compatibility
class OpenAIModel:
    """OpenAI API model interface (deprecated - use OpenRouterModel instead)."""

    def __init__(
        self,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        logger.warning(
            "OpenAIModel is deprecated. Use OpenRouterModel with model_name='openai/gpt-4'"
        )
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required for OpenAIModel. "
                "Install with: pip install openai"
            )

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        if api_key:
            openai.api_key = api_key

    def query(self, system_prompt: str, user_prompt: str) -> str:
        import openai

        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        return response.choices[0].message.content


class AnthropicModel:
    """Anthropic Claude API model interface (deprecated - use OpenRouterModel instead)."""

    def __init__(
        self,
        model: str = "claude-3-sonnet-20240229",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ):
        logger.warning(
            "AnthropicModel is deprecated. Use OpenRouterModel with model_name='anthropic/claude-3-sonnet'"
        )
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required for AnthropicModel. "
                "Install with: pip install anthropic"
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def query(self, system_prompt: str, user_prompt: str) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        return message.content[0].text
