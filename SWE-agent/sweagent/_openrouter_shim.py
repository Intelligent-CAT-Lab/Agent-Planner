# sweagent/_openrouter_shim.py
from __future__ import annotations
from typing import Any, Dict, List

def _is_openrouter_target(model_name: str | None, api_base: str | None) -> bool:
    name = (model_name or "").lower()
    base = (api_base or "").lower()
    return ("openrouter.ai" in base) or name.startswith("openrouter/")

def _is_anthropic_model(model_name: str | None) -> bool:
    """Check if the model is an Anthropic Claude model."""
    name = (model_name or "").lower()
    return "anthropic" in name or "claude" in name

def _flatten_content_parts_to_text(content: Any, preserve_cache_control: bool = False) -> str:
    """
    Flatten content parts to text.

    Args:
        content: Content to flatten (can be list of dicts, dict, or string)
        preserve_cache_control: If True, preserve cache_control in the structure
                               (returns original list format for Anthropic caching)
    """
    if isinstance(content, list):
        # For Anthropic prompt caching via OpenRouter, preserve the list structure
        # with cache_control markers
        if preserve_cache_control:
            # Keep the list format but ensure proper structure
            return content

        # Standard flattening for non-Anthropic or non-caching cases
        out: List[str] = []
        for part in content:
            if isinstance(part, dict):
                # Remove cache_control for non-Anthropic models
                if "cache_control" in part:
                    part = {k: v for k, v in part.items() if k != "cache_control"}
                txt = part.get("text") or part.get("content")
                if isinstance(txt, str):
                    out.append(txt)
            elif isinstance(part, str):
                out.append(part)
        return "\n".join(out)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return "" if content is None else str(content)

def sanitize_messages_for_openrouter(messages: List[Dict[str, Any]], model_name: str | None = None) -> List[Dict[str, Any]]:
    """
    Convert to OpenAI chat-completions shape with STRING content,
    but PRESERVE function-calling fields (tool_calls, tool_call_id, name).

    For Anthropic models, preserve cache_control to enable prompt caching via OpenRouter.

    Args:
        messages: List of message dictionaries
        model_name: Model name to determine if cache_control should be preserved
    """
    # Check if this is an Anthropic model that supports caching
    is_anthropic = _is_anthropic_model(model_name)

    sanitized: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")

        # Normalize accidental {"user":{"content":...}} shape
        if role is None:
            for cand in ("user", "assistant", "system", "tool"):
                if cand in m and isinstance(m[cand], dict):
                    role = cand
                    content = m[cand].get("content", content)
                    break
        if role is None:
            role = "user"

        # Tool result messages must include tool_call_id and name; keep fields
        if role == "tool":
            out = {"role": "tool"}
            # preserve required keys if present
            if "tool_call_id" in m:
                out["tool_call_id"] = m["tool_call_id"]
            if "name" in m:
                out["name"] = m["name"]
            # content must be a string for tool messages
            out["content"] = _flatten_content_parts_to_text(content, preserve_cache_control=False)
            sanitized.append(out)
            continue

        # Assistant messages that trigger tools: preserve tool_calls
        tool_calls = m.get("tool_calls")
        if isinstance(tool_calls, list) and len(tool_calls) > 0:
            # Make a shallow copy to avoid mutating upstream
            tc_copy: List[Dict[str, Any]] = []
            for i, tc in enumerate(tool_calls):
                if not isinstance(tc, dict):
                    continue
                tc_new = dict(tc)
                # Ensure an id exists (Mistral requires it)
                if "id" not in tc_new or not tc_new["id"]:
                    tc_new["id"] = f"call_{i+1}"
                # Ensure type and function fields are present
                if "type" not in tc_new:
                    tc_new["type"] = "function"
                func = tc_new.get("function") or {}
                # keep function name/arguments as-is; do not stringify
                tc_new["function"] = func
                tc_copy.append(tc_new)
            out = {
                "role": "assistant",
                # For Anthropic, preserve list structure with cache_control
                "content": _flatten_content_parts_to_text(content, preserve_cache_control=is_anthropic),
                "tool_calls": tc_copy,
            }
            sanitized.append(out)
            continue

        # Plain system/user/assistant text messages
        # For Anthropic models, preserve cache_control in content structure
        out_msg = {
            "role": role,
            "content": _flatten_content_parts_to_text(content, preserve_cache_control=is_anthropic),
        }

        # Preserve message-level cache_control for Anthropic (rare but valid)
        if is_anthropic and "cache_control" in m:
            out_msg["cache_control"] = m["cache_control"]

        sanitized.append(out_msg)

    return sanitized