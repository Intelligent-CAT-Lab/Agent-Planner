"""Tests for the AST-node program-size cross-check (analysis.expressiveness.astsize)."""
from analysis.expressiveness import astsize, loc


def test_dsl_node_count_leaf_and_nesting():
    # A bare `run(Group) >= theta` dwell signal: Run node + GroupRef + ParamRef = 3.
    nodes = astsize.glg_signal_ast_nodes()
    assert nodes["dwell_P"] == 3
    # oscillation is inflated by cycle desugaring (10-way disjunction) -> large.
    assert nodes["oscillation"] > nodes["dwell_P"] * 3


def test_python_buckets_partition_total():
    rules = loc.PyFile(loc.RULES_PY)
    for name in ["DwellTimeRule", "RepeatedViewRule", "ThoughtOscillationRule",
                 "PlanComplianceRule", "OscillationDetector"]:
        b = astsize.legacy_class_ast_breakdown(rules, name)
        assert b["state"] + b["verdict"] + b["detection"] == b["total"]
        assert all(b[k] >= 0 for k in ("state", "verdict", "detection"))


def test_compute_ast_size_shape():
    r = astsize.compute_ast_size()
    t = r["totals"]
    assert t["dsl_nodes"] > 0
    # Even counting the desugared (inflated) DSL AST, the legacy classes are far larger.
    assert t["legacy_total"] > t["dsl_nodes"] * 3
    assert t["ratio_detection"] <= t["ratio_total"]
    assert "action_recurrence" in r["dsl_only_signals"]["signals"]


def test_markdown_renders():
    md = astsize.to_markdown(astsize.compute_ast_size())
    assert "Program size (AST nodes)" in md
    assert "not an" in md.lower() or "not a" in md.lower()
