#!/usr/bin/env python3
"""
Test classification of complex_command cases.
The issue: complex_command falls through to general, but should analyze content.
"""

from plan_monitor.commandParser import CommandParser
from plan_monitor.mapLang import get_action_role

parser = CommandParser()

# Case 1: User's example - compound command with heredoc creating test file
cmd1 = """cd /testbed && cat > /tmp/repro_timeseries_bug.py <<'PY'
import numpy as np
from astropy.time import Time
PY
python /tmp/repro_timeseries_bug.py"""

print("Case 1: Compound command with heredoc + python execution")
print(f"Command: {cmd1[:80]}...")
parsed1 = parser.parse(cmd1)
print(f"Parsed: {parsed1}")

if parsed1:
    p = parsed1[0]
    # Current behavior
    role = get_action_role(
        tool=None,
        subcommand=None,
        command=p.get("command"),
        args=p.get("args", []),
        flags=p.get("flags", {}),
        prev_roles=[],
        created_tests=set()
    )
    print(f"Current role: {role}")
    print(f"Expected: L_reproduce (test file creation + execution)")
    print()

# Case 2: Complex command creating test file
cmd2 = """cd /testbed && python - <<'PY'\nimport numpy as np\nfrom astropy.time import Time\nfrom astropy.timeseries import TimeSeries\n\ntime = Time(np.arange(3), format='jd')\nts = TimeSeries(time=time, data={'flux':[1,2,3]})\nts._required_columns = ['time', 'flux']\n# Make ordering wrong by renaming? easiest is alter columns through keep_columns\ntry:\n    ts.keep_columns(['flux','time'])\nexcept Exception as e:\n    print(type(e).__name__ + ':', e)\nPY"""

print("\nCase 2: for loop with test execution")
print(f"Command: {cmd2}")
parsed2 = parser.parse(cmd2)
print(f"Parsed: {parsed2}")

if parsed2:
    p = parsed2[0]
    role = get_action_role(
        tool=None,
        subcommand=None,
        command=p.get("command"),
        args=p.get("args", []),
        flags=p.get("flags", {}),
        prev_roles=["P"],
        created_tests=set()
    )
    print(f"Current role: {role}")
    print(f"Expected: V_newly_generated_test (test execution)")
    print()

# Case 3: Complex command patching non-test file
cmd3 = """rm -f /tmp/repro_timeseries_bug.py && cd /testbed && git diff -- astropy/timeseries/core.py && python - <<'PY'\nimport numpy as np\nfrom astropy.time import Time\nfrom astropy.timeseries import TimeSeries\n\ntime = Time(np.arange(100000, 100003), format='jd')\nts = TimeSeries(time=time, data={'flux':[99.9,99.8,99.7]})\nts._required_columns = ['time','flux']\ntry:\n    ts.remove_column('flux')\nexcept Exception as e:\n    print(type(e).__name__ + ':', e)\nPY"""

print("\nCase 3: if statement patching non-test file")
print(f"Command: {cmd3}")
parsed3 = parser.parse(cmd3)
print(f"Parsed: {parsed3}")

if parsed3:
    p = parsed3[0]
    role = get_action_role(
        tool=None,
        subcommand=None,
        command=p.get("command"),
        args=p.get("args", []),
        flags=p.get("flags", {}),
        prev_roles=["P"],
        created_tests=set()
    )
    print(f"Current role: {role}")
    print(f"Expected: V_newly_generated_test")

    cmd4 = """
    cd /testbed && sed -n '1,240p' astropy/modeling/separable.py && printf '\\n--- CORE ---\\n' && sed -n '2890,3725p' astropy/modeling/core.py && printf '\\n--- REPRO ---\\n' > /tmp/repro.py && cat > /tmp/repro.py <<'PY'\nfrom astropy.modeling import models as m\nfrom astropy.modeling.separable import separability_matrix\n\ncm = m.Linear1D(10) & m.Linear1D(5)\nmodel = m.Pix2Sky_TAN() & cm\nprint(separability_matrix(cm))\nprint(separability_matrix(model))\nPY\npython /tmp/repro.py
    """
    print(f"Command: {cmd4}")
    parsed4 = parser.parse(cmd4)
    print(f"Parsed: {parsed4}")

    if parsed4:
        p = parsed4[0]
        role = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
    print(f"Current role: {role}")
    print(f"Expected: L_reproduce")

    cmd5 = """
    cd /testbed && python - <<'PY'\nfrom pathlib import Path\np=Path('astropy/timeseries/core.py')\ns=p.read_text()\nold=\"\"\"            if not self._required_columns_relax and len(self.colnames) < len(required_columns):\\n\\n                missing = required_columns[len(self.colnames):]\\n                raise ValueError(\\\"{} object is invalid - expected columns {} to be present\\\"\\n                                 .format(self.__class__.__name__, repr(missing)))\\n\\n            elif self.colnames[:len(required_columns)] != required_columns:\\n\\n                raise ValueError(\\\"{} object is invalid - expected columns {} but found {}\\\"\\n                                 .format(self.__class__.__name__, repr(required_columns), repr(self.colnames[:len(required_columns)])))\\n\"\"\"\nnew=\"\"\"            if not self._required_columns_relax and len(self.colnames) == 0:\\n\\n                raise ValueError(\\\"{} object is invalid - expected '{}' \\\"\\n                                 \\\"as the first column{} but time series has no columns\\\"\\n                                 .format(self.__class__.__name__, required_columns[0], plural))\\n\\n            elif self.colnames[:len(required_columns)] != required_columns:\\n\\n                raise ValueError(\\\"{} object is invalid - expected '{}' \\\"\\n                                 \\\"as the first column{} but found '{}'\\\"\\n                                 .format(self.__class__.__name__, required_columns[0], plural, self.colnames[0]))\\n\"\"\"\np.write_text(s.replace(old,new))\nPY\npython - <<'PY'\nfrom pathlib import Path\np=Path('astropy/timeseries/core.py')\ns=p.read_text()\nprint('patched')\nPY
    """
    print(f"Command: {cmd5}")
    parsed5 = parser.parse(cmd5)
    print(f"Parsed: {parsed5}")

    if parsed5:
        p = parsed5[0]
        role = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
    print(f"Current role: {role}")
    print(f"Expected: P")

    cmd6 = """
    cd /testbed && python - <<'PY'\nfrom pathlib import Path\np=Path('astropy/timeseries/core.py')\ns=p.read_text()\nold=\"\"\"            if not self._required_columns_relax and len(self.colnames) == 0:\\n\\n                raise ValueError(\\\"{} object is invalid - expected '{}' \\\"\\n                                 \\\"as the first column{} but time series has no columns\\\"\\n                                 .format(self.__class__.__name__, required_columns[0], plural))\\n\\n            elif self.colnames[:len(required_columns)] != required_columns:\\n\\n                raise ValueError(\\\"{} object is invalid - expected '{}' \\\"\\n                                 \\\"as the first column{} but found '{}'\\\"\\n                                 .format(self.__class__.__name__, required_columns[0], plural, self.colnames[0]))\\n\"\"\"\nnew=\"\"\"            if not self._required_columns_relax and len(self.colnames) < len(required_columns):\\n\\n                missing = required_columns[len(self.colnames):]\\n                raise ValueError(\\\"{} object is invalid - expected columns {} to be present\\\"\\n                                 .format(self.__class__.__name__, repr(missing)))\\n\\n            elif self.colnames[:len(required_columns)] != required_columns:\\n\\n                raise ValueError(\\\"{} object is invalid - expected columns {} but found {}\\\"\\n                                 .format(self.__class__.__name__, repr(required_columns), repr(self.colnames[:len(required_columns)])))\\n\"\"\"\np.write_text(s.replace(old,new))\nPY\npython /tmp/repro_timeseries.py
    """
    parsed6 = parser.parse(cmd6)
    print(f"Parsed: {parsed6}")

    if parsed6:
        p = parsed6[0]
        role = get_action_role(
            tool=None,
            subcommand=None,
            command=p.get("command"),
            args=p.get("args", []),
            flags=p.get("flags", {}),
            prev_roles=[],
            created_tests=set()
        )
    print(f"Current role: {role}")
    print(f"Expected: P, V_regression_test")
    