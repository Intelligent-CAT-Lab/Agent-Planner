"""
Differential-harness tests: GL-Guard vs the legacy monitor over synthetic
trajectories. Focuses on the *exact* categories (dwell, repeated_view) where the
two systems must agree step-for-step, and exercises the blocked-step
reconstruction path (oscillation, thought_oscillation).
"""
from __future__ import annotations

import pytest

from plan_monitor.phases import ActionEvent
from plan_monitor.gl_guard.shadow import ShadowDiffer, normalize, replay_steps


def _steps(commands, thoughts=None, observations=None):
    thoughts = thoughts or [""] * len(commands)
    observations = observations or [""] * len(commands)
    return [
        (ActionEvent(step_index=i + 1, command=c), t, o)
        for i, (c, t, o) in enumerate(zip(commands, thoughts, observations))
    ]


def test_normalize_collapses_legacy_variants():
    assert normalize("oscillation_self_loop") == "oscillation"
    assert normalize("oscillation_two_plus_node") == "oscillation"
    assert normalize("thought_oscillation_cycle") == "thought_oscillation"
    assert normalize("dwell_L_navigate") == "dwell_L_navigate"
    assert normalize("plan_compliance") == "plan_compliance"
    assert normalize("plan_compliance_skip_patch") == "plan_compliance"


def test_dwell_exact_agreement_on_pure_navigation():
    """A long navigation run: GL-Guard dwell must fire at exactly the legacy steps."""
    differ = ShadowDiffer.build()
    # 14 distinct navigation commands (distinct -> no oscillation / repeated_view).
    commands = [f'grep -rn "token{i}" src/module_{i}.py' for i in range(14)]
    report = replay_steps(differ, _steps(commands))

    assert report.steps == 14
    # exact categories must agree on every step
    assert report.exact_agreement, report.summary()
    nav = report.per_category.get("dwell_L_navigate")
    assert nav is not None, report.summary()
    # fired (and agreed) at the 7th and 14th in-phase step
    assert nav.agree == 2
    assert nav.legacy_only == 0 and nav.glguard_only == 0


def test_blocked_oscillation_path_runs_and_agrees():
    """Repeating one command triggers the (blocking) oscillation on both sides."""
    differ = ShadowDiffer.build()
    commands = ['grep -rn "needle" src/mod.py'] * 4
    report = replay_steps(differ, _steps(commands))

    assert report.steps == 4
    osc = report.per_category.get("oscillation")
    assert osc is not None and osc.agree >= 1, report.summary()
    # the exact categories must not disagree even while oscillation blocks/rolls back
    assert report.exact_agreement, report.summary()


def test_blocked_thought_oscillation_path():
    """Repeated empty-action (thought-only) steps trigger thought_oscillation on both."""
    differ = ShadowDiffer.build()
    commands = ["", "", "", ""]                      # empty actions -> think steps
    thoughts = ["I am stuck and will retry."] * 4    # identical reasoning
    report = replay_steps(differ, _steps(commands, thoughts=thoughts))

    assert report.steps == 4
    th = report.per_category.get("thought_oscillation")
    assert th is not None and th.agree >= 1, report.summary()
    assert report.exact_agreement, report.summary()


def test_oscillation_catches_multi_node_loop():
    """A 3-node command cycle must trigger GL-Guard's oscillation (cycle operator)."""
    differ = ShadowDiffer.build()
    cycle_cmds = ['grep -n "a" src/a.py', 'grep -n "b" src/b.py', 'grep -n "c" src/c.py'] * 3
    report = replay_steps(differ, _steps(cycle_cmds))
    osc = report.per_category.get("oscillation")
    assert osc is not None and (osc.agree + osc.glguard_only) >= 1, report.summary()
    # dwell etc. must remain exactly in agreement
    assert report.exact_agreement, report.summary()


def test_summary_renders():
    differ = ShadowDiffer.build()
    report = replay_steps(differ, _steps(['grep -rn "x" a.py', 'grep -rn "y" b.py']))
    text = report.summary()
    assert "steps: 2" in text
    assert "EXACT categories" in text
