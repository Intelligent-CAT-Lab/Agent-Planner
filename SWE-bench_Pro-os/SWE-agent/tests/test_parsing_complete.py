#!/usr/bin/env python3
"""Test all edge cases for the parsing fix."""
import json

def test_parse(tool_call_args, test_name):
    """Test parsing with type validation."""
    print(f"\n{test_name}")
    print(f"  Input: {tool_call_args} (type: {type(tool_call_args).__name__})")

    if not isinstance(tool_call_args, dict):
        try:
            values = json.loads(tool_call_args)
            if not isinstance(values, dict):
                print(f"  ✗ FAIL: Parsed to {type(values).__name__}, not dict")
                return False
            print(f"  ✓ Parsed JSON string to dict: {values}")
        except json.JSONDecodeError as e:
            print(f"  ✗ FAIL: JSON decode error: {e}")
            return False
    else:
        values = tool_call_args
        print(f"  ✓ Using dict directly: {values}")

    # This should now always work
    try:
        keys = values.keys()
        print(f"  ✓ keys() works: {list(keys)}")
        return True
    except AttributeError as e:
        print(f"  ✗ FAIL: AttributeError: {e}")
        return False

# Test 1: Dict (normal case)
r1 = test_parse({"command": "view", "path": "/file"}, "Test 1: Dict arguments")

# Test 2: JSON string with dict
r2 = test_parse('{"command": "ls"}', "Test 2: JSON string → dict")

# Test 3: JSON string with plain string (should fail gracefully)
r3 = test_parse('"just a string"', "Test 3: JSON string → string (should fail)")

# Test 4: JSON string with number (should fail gracefully)
r4 = test_parse('42', "Test 4: JSON string → number (should fail)")

# Test 5: JSON string with array (should fail gracefully)
r5 = test_parse('["item1", "item2"]', "Test 5: JSON string → array (should fail)")

print("\n" + "=" * 60)
if r1 and r2 and not r3 and not r4 and not r5:
    print("✓ ALL TESTS PASSED")
    print("  - Dict arguments: Works")
    print("  - JSON string → dict: Works")
    print("  - Invalid types: Rejected correctly")
else:
    print("✗ SOME TESTS FAILED")
print("=" * 60)
