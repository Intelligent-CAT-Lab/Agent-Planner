#!/usr/bin/env python3
"""Test that the parsing fix works for both dict and string arguments."""

# Simulate the fixed code logic
def test_parsing(tool_call_args):
    """Test the parsing logic with fixed code."""
    if not isinstance(tool_call_args, dict):
        try:
            import json
            values = json.loads(tool_call_args)
            print(f"✓ Parsed JSON string arguments: {values}")
        except json.JSONDecodeError:
            print(f"✗ Failed to parse JSON: {tool_call_args}")
            return False
    else:
        values = tool_call_args
        print(f"✓ Using dict arguments directly: {values}")

    # This would fail with the old code when tool_call_args was a dict
    try:
        keys = values.keys()
        print(f"  Keys: {list(keys)}")
        return True
    except AttributeError as e:
        print(f"✗ AttributeError: {e}")
        return False

# Test case 1: arguments as dict (this was failing before)
print("Test 1: Arguments as dict")
test1 = test_parsing({"command": "ls", "path": "/root"})

print("\nTest 2: Arguments as JSON string")
test2 = test_parsing('{"command": "ls", "path": "/root"}')

if test1 and test2:
    print("\n✓ All tests passed - parsing fix is correct")
else:
    print("\n✗ Tests failed")
