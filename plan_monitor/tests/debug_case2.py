#!/usr/bin/env python3
"""Debug case 2 classification"""

from mapLang import _extract_paths_generic, _is_test_related, _contains_redirection, _extract_edited_files_from_python_code
import re

bash_text = """cd /testbed && python - <<'PY'
import numpy as np
from astropy.time import Time
from astropy.timeseries import TimeSeries

time = Time(np.arange(3), format='jd')
ts = TimeSeries(time=time, data={'flux':[1,2,3]})
ts._required_columns = ['time', 'flux']
try:
    ts.keep_columns(['flux','time'])
except Exception as e:
    print(type(e).__name__ + ':', e)
PY"""

print("Bash text analysis:")
print("=" * 80)

# Tokenize
tokens = bash_text.split()
print(f"Tokens (first 10): {tokens[:10]}")

# Extract paths
paths = _extract_paths_generic(tokens)
print(f"Paths extracted: {paths}")

# Check for heredoc content
if 'python' in bash_text.lower() and '<<' in bash_text:
    heredoc_match = re.search(r"<<['\"]?(\w+)['\"]?\s*\n(.*?)\n\1", bash_text, re.DOTALL)
    if heredoc_match:
        print(f"Heredoc delimiter: {heredoc_match.group(1)}")
        heredoc_content = heredoc_match.group(2)
        print(f"Heredoc content (first 100 chars): {heredoc_content[:100]}...")

        # Check for file edits
        edited_files = _extract_edited_files_from_python_code(heredoc_content)
        print(f"Edited files from heredoc: {edited_files}")
        paths.extend(edited_files)

# Check test-related
test_related = _is_test_related(paths)
print(f"Test related: {test_related}")

# Check redirection
is_writing = _contains_redirection(tokens)
print(f"Contains redirection: {is_writing}")

# Check python execution
is_python_exec = any(t in ('python', 'python3', 'python2', 'pytest') for t in tokens)
print(f"Is python execution: {is_python_exec}")

print("\n" + "=" * 80)
print("Analysis:")
print(f"  - This is python heredoc (python - <<PY)")
print(f"  - No file writes in the code")
print(f"  - Should be: inline test execution")
print(f"  - Expected after patch: V_newly_generated_test")
print(f"  - Current logic returns: P (because is_writing=True due to redirect in parent command)")
