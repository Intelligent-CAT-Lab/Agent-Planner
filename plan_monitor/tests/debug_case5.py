#!/usr/bin/env python3
"""Debug case 5 classification"""

from mapLang import _extract_paths_generic, _is_test_related, _extract_edited_files_from_python_code
import re

bash_text = """python - <<'PY'
from pathlib import Path
p=Path('astropy/timeseries/core.py')
s=p.read_text()
old=\"\"\"some old text\"\"\"
new=\"\"\"some new text\"\"\"
p.write_text(s.replace(old,new))
PY
python - <<'PY'
from pathlib import Path
p=Path('astropy/timeseries/core.py')
s=p.read_text()
print('patched')
PY"""

print("Case 5 analysis:")
print("=" * 80)

bash_lower = bash_text.lower()
tokens = bash_text.split()

print(f"Bash text (first 100 chars): {bash_text[:100]}...")
print(f"Tokens (first 10): {tokens[:10]}")

# Extract paths
paths = _extract_paths_generic(tokens)
print(f"\nPaths from tokens: {paths}")

# Check for python heredocs
python_heredoc_edits = []
if 'python' in bash_lower and '<<' in bash_text:
    # Find ALL heredoc matches (there may be multiple)
    heredoc_pattern = r"<<['\"]?(\w+)['\"]?\s*\n(.*?)\n\1"
    for match in re.finditer(heredoc_pattern, bash_text, re.DOTALL):
        delimiter = match.group(1)
        heredoc_content = match.group(2)
        print(f"\nFound heredoc with delimiter '{delimiter}'")
        print(f"  Content (first 80 chars): {heredoc_content[:80]}...")

        edited_files = _extract_edited_files_from_python_code(heredoc_content)
        print(f"  Edited files: {edited_files}")
        python_heredoc_edits.extend(edited_files)

print(f"\nTotal python_heredoc_edits: {python_heredoc_edits}")
paths.extend(python_heredoc_edits)

# Check test-related
test_related = _is_test_related(paths)
print(f"Test related: {test_related}")

# Check for output redirection
has_output_redirect = any(op in bash_text for op in ['>', '>>'])
print(f"Has output redirect (>, >>): {has_output_redirect}")

# Check if python heredoc stdin
is_python_heredoc_stdin = 'python' in bash_lower and '<<' in bash_text and '-' in tokens
print(f"Is python heredoc stdin: {is_python_heredoc_stdin}")

# Determine if writing
is_writing = has_output_redirect and not (is_python_heredoc_stdin and not python_heredoc_edits)
print(f"Is writing: {is_writing}")

# Check inline test exec
is_inline_test_exec = (
    'python' in bash_lower and
    '<<' in bash_text and
    not python_heredoc_edits
)
print(f"Is inline test exec: {is_inline_test_exec}")

print("\n" + "=" * 80)
print("Expected behavior:")
print("  - First heredoc edits astropy/timeseries/core.py (non-test file)")
print("  - Should be classified as P (patching)")
print("  - Current logic: is_inline_test_exec=False (correct), python_heredoc_edits=['astropy/timeseries/core.py']")
print("  - Should hit: 'elif test_related or any(hint in bash_lower...)'")
print("  - test_related should be False (no test hints in 'astropy/timeseries/core.py')")
print("  - Should hit final: 'elif is_writing and paths' -> return P")
