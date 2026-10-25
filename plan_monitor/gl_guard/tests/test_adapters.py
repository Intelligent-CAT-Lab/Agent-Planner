"""Tests for the live-representation adapter (TrajectoryModel, classify_kind)."""
from __future__ import annotations

from pathlib import Path

from plan_monitor.gl_guard.adapters import TrajectoryModel, classify_kind, normalize_obs
from plan_monitor.gl_guard.engine import GuardProgram
from plan_monitor.gl_guard.model import Channel, Hook

SPEC_DIR = Path(__file__).resolve().parents[1] / "specs"


def _programs():
    lp = GuardProgram.load(SPEC_DIR / "liveplan.glg", SPEC_DIR / "liveplan.config.json")
    ex = GuardProgram.load(SPEC_DIR / "extra_signals.glg", SPEC_DIR / "liveplan.config.json")
    return lp, ex


# -- kind classification ------------------------------------------------------

def test_classify_kind_submit():
    assert classify_kind(None, None, "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT") == "submit"
    assert classify_kind("bash", None, "submit") == "submit"


def test_classify_kind_edit_view():
    assert classify_kind("str_replace_editor", "str_replace", "...") == "edit"
    assert classify_kind("str_replace_editor", "create", "...") == "edit"
    assert classify_kind("str_replace_editor", "view", "...") == "view"


def test_classify_kind_phase_fallbacks():
    assert classify_kind("bash", None, "pytest", phase="P") == "edit"
    assert classify_kind("bash", None, "pytest x", phase="V_regression_test") == "run_test"
    assert classify_kind("bash", None, "grep x", phase="L_navigate") == "view"
    assert classify_kind("bash", None, "ls", phase="general") == "general"


def test_normalize_obs_whitespace_and_hashing():
    assert normalize_obs("a   b\n c") == "a b c"
    assert normalize_obs(None) is None
    long = "x " * 400
    assert len(normalize_obs(long)) == 32  # md5 hex digest


# -- incremental world construction -------------------------------------------

def test_general_action_dropped_from_projection():
    model = TrajectoryModel()
    model.commit_action(step=1, key="g", phase="general", kind="general", outcome="success")
    w = model.world_for_propose(step=2, key="n", phase="L_navigate", kind="view")
    # projection should contain only q (the general action is dropped)
    assert list(w.phase_projection()) == ["L_navigate"]


def test_history_strictly_before_q_at_propose():
    model = TrajectoryModel()
    a1 = model.commit_action(step=1, key="a", phase="L_navigate", kind="view", outcome="success")
    w = model.world_for_propose(step=2, key="b", phase="P", kind="edit")
    hist = list(w.history(Channel.ACTION))
    assert hist == [a1]
    assert all(o.oid < w.q.oid for o in hist)


def test_end_to_end_premature_patching_via_adapter():
    lp, _ = _programs()
    model = TrajectoryModel()
    # no localization committed yet; propose a patch
    w = model.world_for_propose(step=1, key="p", phase="P", kind="edit")
    assert "premature_patching" in lp.fired(w)

    # after a localization action, proposing the patch no longer fires it
    model.commit_action(step=1, key="nav", phase="L_navigate", kind="view", outcome="success")
    w2 = model.world_for_propose(step=2, key="p", phase="P", kind="edit")
    assert "premature_patching" not in lp.fired(w2)


def test_end_to_end_repeated_failed_edit_via_adapter():
    _, ex = _programs()
    model = TrajectoryModel()
    model.commit_action(step=1, key="e", phase="P", kind="edit", outcome="failure")
    model.commit_action(step=2, key="e", phase="P", kind="edit", outcome="failure")
    w = model.world_for_propose(step=3, key="e", phase="P", kind="edit")
    assert "repeated_failed_edit" in ex.fired(w)


def test_observe_thought_episode_via_adapter():
    lp, _ = _programs()
    model = TrajectoryModel()
    model.commit_action(step=1, key="a1", phase="L_navigate", kind="view", outcome="success")
    model.commit_thought(step=2, key="h")
    model.commit_thought(step=3, key="h")
    q = model.commit_thought(step=4, key="h")
    w = model.world_for_observe_thought(q)
    assert w.hook is Hook.OBSERVE_THOUGHT
    assert "thought_oscillation" in lp.fired(w)


def test_structural_edge_feeds_se():
    model = TrajectoryModel()
    a = model.commit_action(step=1, key="0:f", phase="L_navigate", kind="view", outcome="success")
    model.add_structural_edge("0:f", "1:f")
    b = model.commit_action(step=2, key="1:f", phase="L_navigate", kind="view", outcome="success")
    w = model.world_for_observe_action(b)
    from plan_monitor.gl_guard.kleene import T
    assert w.se(a, b) is T
