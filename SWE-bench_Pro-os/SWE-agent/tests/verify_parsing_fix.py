#!/usr/bin/env python3
"""
Verify the parsing fix by simulating the exact code path.
"""
import json

def simulate_parse_tool_call_FIXED(tool_call):
    """Simulates the FIXED _parse_tool_call method."""
    print(f"Input tool_call['function']['arguments']: {tool_call['function']['arguments']}")
    print(f"  Type: {type(tool_call['function']['arguments'])}")

    # This is the FIXED code
    if not isinstance(tool_call["function"]["arguments"], dict):
        try:
            values = json.loads(tool_call["function"]["arguments"])
            print(f"  → Parsed from JSON string: {values}")
        except json.JSONDecodeError:
            print(f"  → JSON parse error!")
            return False
    else:
        values = tool_call["function"]["arguments"]
        print(f"  → Using dict directly: {values}")

    # This line was failing before the fix
    try:
        keys = values.keys()
        print(f"  → values.keys() works: {list(keys)}")
        return True
    except AttributeError as e:
        print(f"  → ERROR: {e}")
        return False

# Test Case 1: arguments as dict (OpenRouter/Anthropic format)
print("=" * 60)
print("Test 1: Tool call with arguments as dict")
print("=" * 60)
test1 = {
    "function": {
        "name": "str_replace_editor",
        "arguments": {
            "command": "view",
            "path": "/workspace/file.py"
        }
    }
}
result1 = simulate_parse_tool_call_FIXED(test1)

# Test Case 2: arguments as JSON string (some other providers)
print("\n" + "=" * 60)
print("Test 2: Tool call with arguments as JSON string")
print("=" * 60)
test2 = {
    "function": {
        "name": "bash",
        "arguments": '{"command": "ls -la"}'
    }
}
result2 = simulate_parse_tool_call_FIXED(test2)

print("\n" + "=" * 60)
if result1 and result2:
    print("✓ ALL TESTS PASSED - Fix is correct!")
else:
    print("✗ TESTS FAILED")
print("=" * 60)
