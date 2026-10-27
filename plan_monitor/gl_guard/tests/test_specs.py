"""End-to-end tests: the ten LIVEPLAN signals + the additional diagnostics."""
from __future__ import annotations

from pathlib import Path

from plan_monitor.gl_guard.config import Config
from plan_monitor.gl_guard.engine import GuardProgram
from plan_monitor.gl_guard.kleene import F, T, U
from .fixtures import Traj, liveplan_config

SPEC_DIR = Path(__file__).resolve().parents[1] / "specs"


def _program(name):
    return GuardProgram.load(SPEC_DIR / name, SPEC_DIR / "liveplan.config.json")


LIVEPLAN = _program("liveplan.glg")
EXTRA = _program("extra_signals.glg")


def fired(program, world):
    return set(program.fired(world))


# -- the ten original signals -------------------------------------------------

def test_plan_compliance_premature_patch():
    w = Traj().action("x", phase="L_navigate", kind="view").propose("p", phase="P", kind="edit")
    # localization already seen -> not premature
    assert "plan_compliance_premature_patch" not in fired(LIVEPLAN, w)
    w2 = Traj().propose("p", phase="P", kind="edit")  # no localization yet
    assert "plan_compliance_premature_patch" in fired(LIVEPLAN, w2)


def test_plan_compliance_skip_patch_and_validation():
    w = Traj().action("x", phase="L_navigate", kind="view").propose("s", kind="submit")
    f = fired(LIVEPLAN, w)
    assert "plan_compliance_skip_patch" in f
    assert "plan_compliance_skip_validation" in f
    # once patched + validated, neither fires
    w2 = (Traj()
          .action("x", phase="P", kind="edit")
          .action("v", phase="V_regression_test", kind="run_test")
          .propose("s", kind="submit"))
    f2 = fired(LIVEPLAN, w2)
    assert "plan_compliance_skip_patch" not in f2 and "plan_compliance_skip_validation" not in f2


def test_plan_compliance_premature_validate():
    # validating (Validate) before any patch fires -- the legacy phase_skip [P]/[L,P]
    w = (Traj().action("x", phase="L_navigate", kind="view")
         .propose("v", phase="V_regression_test", kind="run_test"))
    assert "plan_compliance_premature_validate" in fired(LIVEPLAN, w)
    # once a patch exists, validating is on-plan -> no violation
    w2 = (Traj().action("x", phase="L_navigate", kind="view")
          .action("p", phase="P", kind="edit")
          .propose("v", phase="V_regression_test", kind="run_test"))
    assert "plan_compliance_premature_validate" not in fired(LIVEPLAN, w2)


def test_oscillation_self_loop():
    w = Traj().action("A").propose("A_again", key="A")
    assert "oscillation" in fired(LIVEPLAN, w)


def test_oscillation_catches_multi_node_cycles():
    # the `cycle` operator must catch 2- and 3-node loops, not only self-loops
    abab = Traj().action("A").action("B").action("A").action("B").propose("A", key="A")
    assert "oscillation" in fired(LIVEPLAN, abab)
    abcabc = (Traj().action("A").action("B").action("C")
              .action("A").action("B").action("C").propose("A", key="A"))
    assert "oscillation" in fired(LIVEPLAN, abcabc)
    # a non-repeating sequence must NOT fire
    nonloop = Traj().action("A").action("B").action("C").action("D").propose("E", key="E")
    assert "oscillation" not in fired(LIVEPLAN, nonloop)


def test_oscillation_recurrence_high_count():
    # the same substantive action node re-run kappa_recur (7) times before q
    # fires oscillation_recurrence even without a clean period (the legacy
    # two+_node_cycle case the strict `cycle` misses). A milder recurrence
    # (below threshold) stays quiet -- it may be productive iteration.
    t = Traj()
    for _ in range(7):
        t.action("node_T", phase="L_reproduce", kind="run_test")
    w = t.propose("python test.py", key="node_T", phase="L_reproduce", kind="run_test")
    assert "oscillation_recurrence" in fired(LIVEPLAN, w)

    mild = Traj()
    for _ in range(3):
        mild.action("node_T", phase="L_reproduce", kind="run_test")
    wm = mild.propose("python test.py", key="node_T", phase="L_reproduce", kind="run_test")
    assert "oscillation_recurrence" not in fired(LIVEPLAN, wm)


def test_oscillation_recurrence_excludes_general():
    # benign general commands (cd/ls/env) that recur even past threshold must NOT
    # be flagged -- only substantive (non-general) actions count.
    t = Traj()
    for _ in range(9):
        t.action("node_cd", phase=None, kind="general")
    w = t.propose("cd /testbed", key="node_cd", phase=None, kind="general")
    assert "oscillation_recurrence" not in fired(LIVEPLAN, w)


def test_thought_oscillation():
    w = Traj().action("a1").thought("h").thought("h").observe_thought("h")
    assert "thought_oscillation" in fired(LIVEPLAN, w)


def test_dwell_L_navigate():
    t = Traj()
    for _ in range(6):
        t.action("nav", phase="L_navigate", kind="view")
    w = t.propose("q", phase="L_navigate", kind="view")
    assert "dwell_L_navigate" in fired(LIVEPLAN, w)


def test_repeated_view():
    w = Traj().action("loc", kind="view").propose("loc_again", key="loc", kind="view")
    assert "repeated_view" in fired(LIVEPLAN, w)
    # editing (not viewing) the same key does not trip the view-only revisit rule
    w2 = Traj().action("loc", kind="view").propose("loc_edit", key="loc", kind="edit")
    assert "repeated_view" not in fired(LIVEPLAN, w2)


# -- additional diagnostics ---------------------------------------------------

def test_stale_validation():
    # a successful edit, never validated, then submit
    w = (Traj()
         .action("e", phase="P", kind="edit", outcome="success")
         .propose("s", kind="submit"))
    assert "stale_validation" in fired(EXTRA, w)
    # with a validation after the edit, it is not stale
    w2 = (Traj()
          .action("e", phase="P", kind="edit", outcome="success")
          .action("v", phase="V_regression_test", kind="run_test", outcome="success")
          .propose("s", kind="submit"))
    assert "stale_validation" not in fired(EXTRA, w2)


def test_repeated_failed_edit():
    w = (Traj()
         .action("e", kind="edit", outcome="failure")
         .action("e", kind="edit", outcome="failure")
         .propose("e", key="e", kind="edit"))
    assert "repeated_failed_edit" in fired(EXTRA, w)


def test_failed_patch_backtrack():
    # latest committed action is a failed patch; q returns to localization
    w = (Traj()
         .action("p", phase="P", kind="edit", outcome="failure")
         .propose("nav", phase="L_navigate", kind="view"))
    assert "failed_patch_backtrack" in fired(EXTRA, w)
    # if a later action intervened, the backtrack is not "immediate"
    w2 = (Traj()
          .action("p", phase="P", kind="edit", outcome="failure")
          .action("later", phase="L_navigate", kind="view", outcome="success")
          .propose("nav", phase="L_navigate", kind="view"))
    assert "failed_patch_backtrack" not in fired(EXTRA, w2)


def test_repeated_unchanged_view():
    # two identical earlier views with equivalent observations; q re-views same key
    w = (Traj()
         .action("loc", kind="view", outcome="success", obs="same output")
         .action("loc", kind="view", outcome="success", obs="same output")
         .propose("loc", key="loc", kind="view"))
    assert "repeated_unchanged_view" in fired(EXTRA, w)


# -- hook routing -------------------------------------------------------------

def test_config_ignores_underscore_comment_keys():
    # JSON has no comments: keys beginning with "_" are documentation and must be
    # stripped by the loader (both in params and phase_groups), never parsed as int.
    cfg = Config.from_dict({
        "_comment": "overview",
        "phase_groups": {"_note": "doc", "Patch": ["P"]},
        "params": {"_dwell": "why 7", "theta_P": 7},
        "kinds": ["edit"],
    })
    assert cfg.params == {"theta_P": 7}          # "_dwell" string ignored, not int()'d
    assert set(cfg.phase_groups) == {"Patch"}     # "_note" ignored


def test_liveplan_config_is_annotated_and_clean():
    # the shipped config loads with comments ignored and no dead params
    cfg = Config.load(SPEC_DIR / "liveplan.config.json")
    assert "m_action" not in cfg.params           # removed (was unused)
    assert not any(k.startswith("_") for k in cfg.params)
    for p in ("theta_N", "theta_R", "theta_P", "theta_V", "r_action",
              "m_thought", "r_thought", "kappa_recur", "kappa_fail"):
        assert p in cfg.params


def test_only_matching_hook_rules_evaluated():
    # a propose world should not evaluate the thought rule
    w = Traj().action("A").propose("A", key="A")
    names = {v.rule for v in LIVEPLAN.evaluate(w)}
    assert "thought_oscillation" not in names
    assert "oscillation" in names
