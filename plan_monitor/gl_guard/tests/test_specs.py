"""End-to-end tests: the ten LIVEPLAN signals + the additional diagnostics."""
from __future__ import annotations

from pathlib import Path

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

def test_premature_patching():
    w = Traj().action("x", phase="L_navigate", kind="view").propose("p", phase="P", kind="edit")
    # localization already seen -> not premature
    assert "premature_patching" not in fired(LIVEPLAN, w)
    w2 = Traj().propose("p", phase="P", kind="edit")  # no localization yet
    assert "premature_patching" in fired(LIVEPLAN, w2)


def test_skip_patching_and_validation():
    w = Traj().action("x", phase="L_navigate", kind="view").propose("s", kind="submit")
    f = fired(LIVEPLAN, w)
    assert "skip_patching" in f
    assert "skip_validation" in f
    # once patched + validated, neither fires
    w2 = (Traj()
          .action("x", phase="P", kind="edit")
          .action("v", phase="V_regression_test", kind="run_test")
          .propose("s", kind="submit"))
    f2 = fired(LIVEPLAN, w2)
    assert "skip_patching" not in f2 and "skip_validation" not in f2


def test_action_oscillation_self_loop():
    w = Traj().action("A").propose("A_again", key="A")
    assert "action_oscillation" in fired(LIVEPLAN, w)


def test_thought_oscillation():
    w = Traj().action("a1").thought("h").thought("h").observe_thought("h")
    assert "thought_oscillation" in fired(LIVEPLAN, w)


def test_prolonged_navigation():
    t = Traj()
    for _ in range(6):
        t.action("nav", phase="L_navigate", kind="view")
    w = t.propose("q", phase="L_navigate", kind="view")
    assert "prolonged_navigation" in fired(LIVEPLAN, w)


def test_action_revisit():
    w = Traj().action("loc", kind="view").propose("loc_again", key="loc", kind="view")
    assert "action_revisit" in fired(LIVEPLAN, w)
    # editing (not viewing) the same key does not trip the view-only revisit rule
    w2 = Traj().action("loc", kind="view").propose("loc_edit", key="loc", kind="edit")
    assert "action_revisit" not in fired(LIVEPLAN, w2)


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

def test_only_matching_hook_rules_evaluated():
    # a propose world should not evaluate the thought rule
    w = Traj().action("A").propose("A", key="A")
    names = {v.rule for v in LIVEPLAN.evaluate(w)}
    assert "thought_oscillation" not in names
    assert "action_oscillation" in names
