"""Tests for the deterministic LOC comparison (analysis.expressiveness.loc)."""
import ast

from analysis.expressiveness import loc


def test_glg_block_count_matches_hand_count():
    sigs = loc.glg_signal_loc(loc.GLG)
    # repeated_view is exactly: `signal ... when` + `kind(q) = view and revisit(action)`.
    assert sigs["repeated_view"] == 2
    # Commented-out lines inside a block (e.g. a disabled guard) do not count.
    assert sigs["oscillation"] == 2
    # All default signals are short formula blocks.
    assert all(1 <= n <= 6 for n in sigs.values())


def test_py_counter_ignores_blanks_comments_docstrings():
    src = '''"""module doc
spans two lines."""
import os  # inline comment survives

def f():
    """method doc."""
    # a comment
    x = 1

    return x
'''
    import tempfile
    import pathlib
    p = pathlib.Path(tempfile.mkstemp(suffix=".py")[1])
    p.write_text(src)
    # code lines: `import os`, `def f():`, `x = 1`, `return x` == 4.
    assert loc.py_file_code_lines(p) == 4


def test_legacy_breakdown_is_a_partition():
    rules = loc.PyFile(loc.RULES_PY)
    for name in ["DwellTimeRule", "RepeatedViewRule", "ThoughtOscillationRule",
                 "PlanComplianceRule", "OscillationDetector", "OscillationRule"]:
        b = loc.legacy_class_breakdown(rules, name)
        # state + verdict + detection exactly partitions the class total.
        assert b["state"] + b["verdict"] + b["detection"] == b["total"]
        assert b["detection"] >= 0


def test_every_default_signal_is_accounted_for():
    """Each liveplan.glg signal is either matched to a legacy class or DSL-only."""
    declared = set(loc.glg_signal_loc(loc.GLG))
    matched = {s for g in loc.GROUPS for s in g["dsl_signals"]}
    assert matched.isdisjoint(loc.DSL_ONLY_SIGNALS)
    assert matched | set(loc.DSL_ONLY_SIGNALS) == declared, \
        declared ^ (matched | set(loc.DSL_ONLY_SIGNALS))


def test_dsl_only_signals_excluded_from_matched_totals():
    r = loc.compute_loc()
    only = r["dsl_only_signals"]["signals"]
    assert "action_recurrence" in only
    # DSL-only signals are reported but not in any matched group.
    matched_sigs = {s for g in r["groups"] for s in g["dsl"]["signals"]}
    assert matched_sigs.isdisjoint(only)


def test_compute_loc_shape_and_ratio():
    r = loc.compute_loc()
    t = r["totals"]
    # 11 matched default signals (12 declared minus 1 DSL-only).
    assert t["n_dsl_signals"] == 11
    assert t["dsl_formula_loc"] > 0
    # The DSL formulas are dramatically shorter than the legacy classes.
    assert t["legacy_class_total"] > t["dsl_formula_loc"] * 5
    # detection-only ratio is the conservative (apples-to-apples) figure and is < total ratio.
    assert t["ratio_detection"] <= t["ratio_total"]
    assert r["shared_infrastructure"]["dsl"]["engine_total"] > 0
    assert r["shared_infrastructure"]["legacy"]["monitor_py"] > 0


def test_markdown_renders():
    md = loc.to_markdown(loc.compute_loc())
    assert "LOC: default GL-Guard signals" in md
    assert "detection×" in md
