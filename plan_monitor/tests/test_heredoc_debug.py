#!/usr/bin/env python3
"""
Debug test for heredoc handling in commandParser + mapLang.
Focus: When python dynamically executes heredoc or writes to a file,
determine if it's L_reproduce (test file) or P (patching).
"""

from commandParser import CommandParser
from mapLang import get_action_role

def test_heredoc_python_cases():
    parser = CommandParser()

    # Test case 1: Python heredoc creating a test file (before patch)
    cmd1 = """cat << 'EOF' > /workspace/test_reproduction.py
import sympy as sy
M1 = sy.Matrix.zeros(0, 0)
print(f"Result: {M1.shape}")
EOF"""

    print("=" * 80)
    print("Test 1: cat heredoc creating test_reproduction.py (before patch)")
    print(f"Command: {cmd1[:80]}...")
    parsed1 = parser.parse(cmd1)
    print(f"Parsed: {parsed1}")

    if parsed1:
        p = parsed1[0]
        role1 = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],  # Before patch
            created_tests=set()
        )
        print(f"Role (before patch): {role1}")
        print(f"Expected: L_reproduce (test file creation before patch)")

    # Test case 2: Python heredoc creating a test file (after patch)
    print("\n" + "=" * 80)
    print("Test 2: Same command after patch")
    created_tests = set()
    if parsed1:
        p = parsed1[0]
        role2 = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=["P"],  # After patch
            created_tests=created_tests
        )
        print(f"Role (after patch): {role2}")
        print(f"Created tests tracked: {created_tests}")
        print(f"Expected: V_newly_generated_test (new test file)")

    # Test case 3: Python heredoc executing inline code (not writing to file)
    cmd3 = """python3 - <<'PY'
def f(self):
    return 1
prop = property(f)
print("before:", prop.__doc__)
prop.__doc__ = "assigned"
print("after assign:", prop.__doc__)
PY"""

    print("\n" + "=" * 80)
    print("Test 3: Python heredoc with inline code (no file write)")
    print(f"Command: {cmd3[:80]}...")
    parsed3 = parser.parse(cmd3)
    print(f"Parsed: {parsed3}")

    if parsed3:
        p = parsed3[0]
        role3_before = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],  # Before patch
            created_tests=set()
        )
        print(f"Role (before patch): {role3_before}")
        print(f"Expected: L_reproduce (test execution)")

        role3_after = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=["P"],  # After patch
            created_tests=set(),
            created_dynamic_suites=set()
        )
        print(f"Role (after patch): {role3_after}")
        print(f"Expected: V_newly_generated_test (inline test)")

    # Test case 4: Python heredoc writing to non-test file (patching)
    cmd4 = """cat << 'EOF' > /workspace/fix_matrix.py
import sympy as sy

class Matrix:
    def hstack(*args):
        # Fixed implementation
        return Matrix()
EOF"""

    print("\n" + "=" * 80)
    print("Test 4: Python heredoc creating non-test file (patch)")
    print(f"Command: {cmd4[:80]}...")
    parsed4 = parser.parse(cmd4)
    print(f"Parsed: {parsed4}")

    if parsed4:
        p = parsed4[0]
        role4 = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
        print(f"Role: {role4}")
        print(f"Expected: P (patching non-test file)")

    # Test case 5: Python -c with file writing (test file)
    cmd5 = """python3 -c "
from pathlib import Path
Path('test_repro.py').write_text('import sys\\nprint(sys.version)')
" """

    print("\n" + "=" * 80)
    print("Test 5: Python -c writing to test file")
    print(f"Command: {cmd5}")
    parsed5 = parser.parse(cmd5)
    print(f"Parsed: {parsed5}")

    if parsed5:
        p = parsed5[0]
        role5_before = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
        print(f"Role (before patch): {role5_before}")
        print(f"Expected: L_reproduce (setting up test)")

        role5_after = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=["P"],
            created_tests=set()
        )
        print(f"Role (after patch): {role5_after}")
        print(f"Expected: V_newly_generated_test (creating new test)")

    # Test case 6: Python heredoc writing to test file (inline code)
    cmd6 = """python3 <<'PY'
from pathlib import Path
Path('/workspace/test_debug.py').write_text('''
def test_case():
    assert True
''')
PY"""

    print("\n" + "=" * 80)
    print("Test 6: Python heredoc with inline Path write to test file")
    print(f"Command: {cmd6[:80]}...")
    parsed6 = parser.parse(cmd6)
    print(f"Parsed: {parsed6}")

    if parsed6:
        p = parsed6[0]
        print(f"  Command: {p.get('command')}")
        print(f"  Args: {p.get('args')}")
        print(f"  Flags: {p.get('flags')}")

        role6_before = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
        print(f"Role (before patch): {role6_before}")
        print(f"Expected: L_reproduce (setting up test)")

        role6_after = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=["P"],
            created_tests=set()
        )
        print(f"Role (after patch): {role6_after}")
        print(f"Expected: V_newly_generated_test (creating new test)")

    # Test case 7: Python heredoc writing to non-test file
    cmd7 = """python3 <<'PY'
from pathlib import Path
Path('/workspace/src/matrix.py').write_text('''
class Matrix:
    def hstack(self):
        pass
''')
PY"""

    print("\n" + "=" * 80)
    print("Test 7: Python heredoc with Path write to non-test file")
    print(f"Command: {cmd7[:80]}...")
    parsed7 = parser.parse(cmd7)
    print(f"Parsed: {parsed7}")

    if parsed7:
        p = parsed7[0]
        role7 = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
        print(f"Role: {role7}")
        print(f"Expected: P (patching non-test file)")

if __name__ == "__main__":
    test_heredoc_python_cases()
