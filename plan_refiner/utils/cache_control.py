"""
Cache control utilities for API calls.

Implements cache control markers for LLM APIs (e.g., Anthropic's prompt caching)
to improve efficiency and reduce costs by caching frequently reused content.
"""

import copy
from typing import Literal


def _get_content_text(entry: dict) -> str:
    """Extract text content from message entry."""
    if isinstance(entry["content"], str):
        return entry["content"]
    assert len(entry["content"]) == 1, "Expected single message in content"
    return entry["content"][0]["text"]


def _clear_cache_control(entry: dict) -> None:
    """Remove cache control markers from message entry."""
    if isinstance(entry["content"], list):
        assert len(entry["content"]) == 1, "Expected single message in content"
        entry["content"][0].pop("cache_control", None)
    entry.pop("cache_control", None)


def _set_cache_control(entry: dict) -> None:
    """Add cache control marker to message entry."""
    if not isinstance(entry["content"], list):
        entry["content"] = [
            {
                "type": "text",
                "text": _get_content_text(entry),
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        entry["content"][0]["cache_control"] = {"type": "ephemeral"}

    # Special handling for tool messages
    if entry["role"] == "tool":
        entry["content"][0].pop("cache_control", None)
        entry["cache_control"] = {"type": "ephemeral"}


def set_cache_control(
    messages: list[dict],
    *,
    mode: Literal["default_end"] | None = "default_end"
) -> list[dict]:
    """
    Add cache control markers to messages for API efficiency.

    This enables prompt caching on supported APIs (e.g., Anthropic's Claude)
    to reduce costs and latency by caching frequently reused content.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        mode: Cache control mode. Currently only supports "default_end"
              which adds cache marker to the last message.

    Returns:
        Deep copy of messages with cache control markers added

    Example:
        >>> messages = [
        ...     {"role": "system", "content": "You are a helpful assistant"},
        ...     {"role": "user", "content": "Hello"}
        ... ]
        >>> cached_messages = set_cache_control(messages)
        # Last message will have cache_control marker
    """
    if mode != "default_end":
        raise ValueError(f"Invalid mode: {mode}. Only 'default_end' is supported.")

    # Deep copy to avoid modifying original messages
    messages = copy.deepcopy(messages)

    # Process messages in reverse order
    new_messages = []
    for i_entry, entry in enumerate(reversed(messages)):
        _clear_cache_control(entry)
        if i_entry == 0:  # Last message
            _set_cache_control(entry)
        new_messages.append(entry)

    return list(reversed(new_messages))
