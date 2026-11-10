"""
Tests for the replay-based pattern-resolution pipeline.

Covers the two properties that matter most:
  * **signal-count-agnostic tidy schema** — columns are additive in the signal set, read
    back BY NAME, and the wide pivot's section spans are computed from the data.
  * **legacy-compatible analysis** — ``patterns`` folds the GL-Guard replay signals into
    the legacy 7 buckets (names/semantics preserved) and appends the precise extras, and
    the ported ``planner_stats`` extraction keeps the online record (precise ``rule_ids``
    with the ``plan_violation`` exclusion-recovery).
"""
import csv
import json

from analysis.analyze_pattern_resolution import (categorize, patterns_from_signals,
                                                 planner_aggregates, trigger_status)
from analysis.pattern_resolution.schema import (PatternRecord, _wide_fields, long_columns,
                                                read_long, write_long_json, write_wide_csv)
from analysis.pattern_resolution.sources import (_subscript_runlength, classify_monitor_trigger,
                                                 extract_planner_stats, read_planner_meta,
                                                 replay_detail)


# -- schema: signal-count-agnostic ------------------------------------------- #

def test_signal_count_agnostic_roundtrip(tmp_path):
    sigs = ["sig_a", "sig_b", "sig_c"]
    recs = [
        PatternRecord("inst1", "default", resolved=True, lang="L₂P₁", unique_phases="L,P",
                      cost=1.5, steps=10, signals={"sig_a": True, "sig_b": False, "sig_c": True}),
        PatternRecord("inst1", "refiner", resolved=False, has_planner=True,
                      refiner_online_triggers=["sig_b", "legacy_x"],
                      signals={"sig_a": False, "sig_b": True, "sig_c": False}),
    ]
    p = tmp_path / "t.long.json"
    write_long_json(recs, p)
    rows = read_long(p)

    assert rows[0]["signal_columns"] == sigs                     # discovered by name
    assert rows[0]["signals"] == {"sig_a": True, "sig_b": False, "sig_c": True}
    assert rows[0]["lang"] == "L₂P₁"                             # utf-8 subscripts preserved
    assert rows[0]["resolved_bool"] is True
    assert rows[0]["has_planner_bool"] is False                  # baseline: no planner
    assert rows[1]["has_planner_bool"] is True
    assert rows[1]["online_triggers"] == ["sig_b", "legacy_x"]   # exact rule-ids


def test_adding_a_signal_is_purely_additive():
    assert long_columns(["a", "b", "c"]) == long_columns(["a", "b"]) + ["c"]
    assert (len(_wide_fields("refiner", ["a", "b", "c"]))
            == len(_wide_fields("refiner", ["a", "b"])) + 1)


def test_wide_pivot_header_spans_match_field_counts(tmp_path):
    sigs = ["s1", "s2"]
    recs = [PatternRecord("i1", "default", resolved=True, signals={"s1": True}),
            PatternRecord("i1", "refiner", resolved=False, has_planner=True,
                          signals={"s2": True})]
    p = tmp_path / "t.wide.csv"
    write_wide_csv(recs, p, sigs)
    header1, header2 = list(csv.reader(open(p)))[:2]
    assert [c for c in header1 if c and c != "Instance ID"] == ["default", "refiner"]
    assert len(header2) == 1 + len(_wide_fields("default", sigs)) + len(_wide_fields("refiner", sigs))


# -- replay detection (True/False) ------------------------------------------- #

def test_replay_detail_clean_booleans(make_traj):
    steps = [("str_replace_editor view /t/m.py", "class X: pass"), ("submit", "")]
    det = replay_detail(make_traj(steps))
    assert det["error"] == ""
    assert det["signals"]["plan_compliance_skip_patch"] is True
    assert det["signals"]["plan_compliance_skip_validation"] is True
    assert det["signals"]["dwell_P"] is False
    assert all(v in (True, False) for v in det["signals"].values())
    assert "L_navigate" in det["unique_phases"]


def test_replay_detail_malformed_is_all_false(tmp_path):
    bad = tmp_path / "b.traj"
    bad.write_text("{ not json")
    det = replay_detail(str(bad))
    assert det["error"] and det["signals"] and all(v is False for v in det["signals"].values())


def test_subscript_runlength():
    assert _subscript_runlength(["P", "P", "V"]) == "P₂V₁"
    assert _subscript_runlength([]) == ""


# -- patterns: legacy buckets + precise extras ------------------------------- #

def test_patterns_fold_into_legacy_buckets_and_keep_extras():
    sig = {"plan_compliance_skip_validation": True, "plan_compliance_skip_patch": False,
           "oscillation": False, "action_recurrence": True, "thought_oscillation": False,
           "dwell_L_navigate": False, "dwell_V": True, "repeated_view": False}
    p = patterns_from_signals(sig)
    # legacy buckets present with correct names + semantics
    assert p["plan_violation"] is True                 # any plan_compliance_*
    assert p["oscillation"] is True                    # via action_recurrence
    assert p["dwell_V"] is True and p["repeated_view"] is False
    assert p["dwell_L_reproduce"] is False             # absent signal -> False bucket
    for b in ("plan_violation", "oscillation", "dwell_L_navigate", "dwell_L_reproduce",
              "dwell_P", "dwell_V", "repeated_view"):
        assert b in p
    # precise extras preserved verbatim (non-colliding names)
    assert p["plan_compliance_skip_validation"] is True
    assert p["action_recurrence"] is True
    assert p["plan_compliance_skip_patch"] is False


# -- analysis views (legacy schema pieces) ----------------------------------- #

def test_categorize_triggered_only():
    base = {"a": {"resolved_bool": True}, "b": {"resolved_bool": False}}
    cfg = {"a": {"resolved_bool": True, "has_planner_bool": True},
           "b": {"resolved_bool": True, "has_planner_bool": False}}
    cats = categorize(base, cfg, triggered_only=True)
    assert cats["R-R"] == ["a"]                         # a triggered, R->R
    assert cats["U-R"] == [] and cats["R-U"] == [] and cats["U-U"] == []  # b not triggered


def test_trigger_status_counts():
    cfg = {"a": {"has_planner_bool": True, "resolved_bool": True},
           "b": {"has_planner_bool": True, "resolved_bool": False},
           "c": {"has_planner_bool": False, "resolved_bool": None}}
    t = trigger_status(cfg)
    assert t["total_planner_instances"] == 3 and t["triggered_count"] == 2
    assert t["triggered_resolved"] == 1 and t["triggered_unresolved"] == 1
    assert t["non_triggered_count"] == 1


def test_planner_aggregates_distribution():
    stats = {
        "a": {"total_interventions": 2, "monitor_count": 1, "refiner_count": 1,
              "monitor_total_latency_ms": 10.0, "refiner_total_latency_ms": 20.0,
              "refiner_total_cost": 0.5,
              "interventions": [{"planner_type": "monitor", "pattern": "dwell_V"},
                                {"planner_type": "refiner", "rule_ids": ["plan_violation"]}]},
    }
    agg = planner_aggregates(["a"], stats)
    assert agg["total_triggered"] == 1
    assert agg["trigger_type_distribution"] == {"monitor_dwell_V": 1, "plan_violation": 1}
    assert agg["avg_interventions"] == 2 and agg["avg_refiner_cost"] == 0.5


# -- planner.json -> planner_stats (ported, precise) ------------------------- #

def test_classify_monitor_trigger_labels():
    assert classify_monitor_trigger("Plan compliance violation: ...") == "plan_violation"
    assert classify_monitor_trigger("You seem to navigate between files ...") == "dwell_L_navigate"
    assert classify_monitor_trigger("You have already reviewed this location.") == "repeated_view"
    assert classify_monitor_trigger("totally unrelated text") == "unknown"


def test_extract_planner_stats_precise_and_recovered(tmp_path):
    planner = tmp_path / "x.planner.json"
    planner.write_text(json.dumps({
        "summary": {"total_interventions": 3, "monitor_count": 1, "refiner_count": 2,
                    "refiner_total_cost": 0.9},
        "interventions": [
            {"planner_type": "monitor", "step": 1, "content": "Plan compliance violation: x"},
            {"planner_type": "refiner", "step": 4, "content": "g",
             "state_summary": {"rule_triggers": [{"rule_id": "plan_compliance_skip_validation"}]}},
            {"planner_type": "refiner", "step": 7, "content": "g",
             "state_summary": {"rule_triggers": []}},     # legacy exclusion -> plan_violation
        ]}))
    traj = tmp_path / "x.traj"
    traj.write_text(json.dumps({"trajectory": []}))
    ps = extract_planner_stats(planner, traj)
    assert ps["total_interventions"] == 3 and ps["refiner_count"] == 2
    ivs = ps["interventions"]
    assert ivs[0]["pattern"] == "plan_violation"                 # monitor classified
    assert ivs[1]["rule_ids"] == ["plan_compliance_skip_validation"]   # precise (gl_guard)
    assert ivs[2]["rule_ids"] == ["plan_violation"]             # recovered from empty triggers


def test_extract_planner_stats_absent_is_none(tmp_path):
    assert extract_planner_stats(tmp_path / "nope.planner.json", tmp_path / "nope.traj") is None


# -- table online trail recovery (read_planner_meta) ------------------------- #

def _write_planner(tmp_path, interventions, summary=None):
    p = tmp_path / "m.planner.json"
    p.write_text(json.dumps({"summary": summary or {}, "interventions": interventions}))
    return p


def test_read_planner_meta_recovers_legacy_plan_compliance(tmp_path):
    interventions = [
        {"planner_type": "refiner", "content": "[Plan Refiner Guidance]\n...",
         "state_summary": {"rule_triggers": []}},
        {"planner_type": "refiner", "content": "...",
         "state_summary": {"rule_triggers": [{"rule_id": "oscillation_self_loop"}]}},
        {"planner_type": "monitor", "content": "Plan compliance violation: ended execution ..."},
        {"planner_type": "monitor", "content": "You seem to navigate between files ..."},
    ]
    pm = read_planner_meta(_write_planner(tmp_path, interventions))
    assert pm["has_planner"] is True
    assert "plan_compliance" in pm["refiner_online_triggers"]        # recovered -> not none
    assert "oscillation_self_loop" in pm["refiner_online_triggers"]  # directly recorded


def test_read_planner_meta_glguard_precise_no_generic_token(tmp_path):
    interventions = [
        {"planner_type": "refiner", "content": "...",
         "state_summary": {"rule_triggers": [{"rule_id": "plan_compliance_skip_validation"}]}},
    ]
    pm = read_planner_meta(_write_planner(tmp_path, interventions))
    assert pm["refiner_online_triggers"] == ["plan_compliance_skip_validation"]
