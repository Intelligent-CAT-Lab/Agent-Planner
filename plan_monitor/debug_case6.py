#!/usr/bin/env python3
"""Debug case 6 - compound operation with both P and test execution"""

from mapLang import _extract_paths_generic, _is_test_related, _extract_edited_files_from_python_code
import re

bash_text = """cd /testbed && python - <<'PY'
from pathlib import Path
p=Path('astropy/timeseries/core.py')
s=p.read_text()
old=\"\"\"old text\"\"\"
new=\"\"\"new text\"\"\"
p.write_text(s.replace(old,new))
PY
python /tmp/repro_timeseries.py"""

print("Case 6 analysis:")
print("=" * 80)

bash_lower = bash_text.lower()
tokens = bash_text.split()

print(f"Bash text (first 100 chars): {bash_text[:100]}...")
print()

# Extract paths
paths = _extract_paths_generic(tokens)
print(f"Paths from tokens: {paths}")

# Check for python heredocs
python_heredoc_edits = []
if 'python' in bash_lower and '<<' in bash_text:
    for match in re.finditer(r"<<['\"]?(\w+)['\"]?\s*\n(.*?)\n\1", bash_text, re.DOTALL):
        delimiter = match.group(1)
        heredoc_content = match.group(2)
        print(f"\nFound heredoc with delimiter '{delimiter}'")
        print(f"  Content (first 80 chars): {heredoc_content[:80]}...")

        edited_files = _extract_edited_files_from_python_code(heredoc_content)
        print(f"  Edited files: {edited_files}")
        python_heredoc_edits.extend(edited_files)

paths.extend(python_heredoc_edits)

print(f"\nAll paths: {paths}")
print(f"Python heredoc edits: {python_heredoc_edits}")

# Check test-related
test_related = _is_test_related(paths)
print(f"Test related: {test_related}")

print("\n" + "=" * 80)
print("Analysis:")
print("  - First heredoc edits: astropy/timeseries/core.py (NON-TEST file)")
print("  - Second command: python /tmp/repro_timeseries.py (TEST file)")
print("  - This command has TWO phases:")
print("    1. P (patching non-test file)")
print("    2. L_reproduce (before patch) or V_regression_test (after patch)")
print()
print("Current behavior:")
print("  - paths includes both 'astropy/timeseries/core.py' and '/tmp/repro_timeseries.py'")
print("  - test_related=True because '/tmp/repro_timeseries.py' contains 'repro'")
print("  - Logic hits: 'elif test_related or any(hint in bash_lower...)'")
print("  - Returns: L_reproduce (before patch)")
print()
print("Expected behavior:")
print("  - Should recognize BOTH phases exist")
print("  - Primary role should be determined by the dominant operation")
print("  - Since it patches AND runs test, should return: P, V_regression_test")
print("  - Or prioritize P since it's the patch operation")
