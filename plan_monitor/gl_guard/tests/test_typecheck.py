"""Well-formedness tests (design section 2)."""
from __future__ import annotations

import pytest

from plan_monitor.gl_guard.parser import parse_rule
from plan_monitor.gl_guard.typecheck import WellFormednessError, check_rule
from .fixtures import liveplan_config


def _err(text, config=None):
    with pytest.raises(WellFormednessError) as ei:
        check_rule(parse_rule(text), config)
    return "\n".join(ei.value.errors)


def test_unbound_variable_rejected():
    msg = _err("signal a on propose when phase(x) in Patch")
    assert "unbound variable 'x'" in msg


def test_outcome_q_invalid_at_propose():
    msg = _err("signal a on propose when outcome(q) = success")
    assert "outcome(q) is invalid at propose" in msg


def test_outcome_q_ok_at_observe_action():
    check_rule(parse_rule("signal a on observe(action) when outcome(q) = success"))


def test_obs_eq_with_q_invalid_at_propose():
    msg = _err("signal a on propose when exists x in history(action): obs_eq(q, x)")
    assert "obs_eq(..) involving q is invalid at propose" in msg


def test_phase_on_thought_rejected():
    msg = _err("signal a on observe(thought) when exists x in history(thought): phase(x) in Patch")
    assert "requires an action occurrence" in msg


def test_run_requires_action_hook():
    msg = _err("signal a on observe(thought) when run(Patch) >= 2")
    assert "run(F) requires an action hook" in msg


def test_repeat_channel_must_match_hook():
    msg = _err("signal a on propose when repeat(thought, length=1, times=2)")
    assert "requires channel to match the hook channel" in msg


def test_key_eq_cross_channel_rejected():
    msg = _err(
        "signal a on observe(thought) when exists x in history(action): key(x) = key(q)"
    )
    assert "same channel" in msg


def test_times_must_be_at_least_two():
    msg = _err("signal a on propose when repeat(action, length=1, times=1)")
    assert "times must be >= 2" in msg


def test_unknown_group_and_param_rejected_with_config():
    cfg = liveplan_config()
    assert "unknown phase group 'Nope'" in _err("signal a on propose when phase(q) in Nope", cfg)
    assert "unknown parameter 'nope'" in _err("signal a on propose when run(Patch) >= nope", cfg)


def test_bad_outcome_literal():
    msg = _err("signal a on observe(action) when outcome(q) = maybe")
    assert "unknown outcome 'maybe'" in msg


def test_shadowing_rejected():
    msg = _err(
        "signal a on propose when exists x in history(action): "
        "exists x in history(action): true"
    )
    assert "shadows" in msg


def test_all_shipped_rules_wellformed():
    from pathlib import Path
    from plan_monitor.gl_guard.parser import parse_program
    cfg = liveplan_config()
    spec_dir = Path(__file__).resolve().parents[1] / "specs"
    for name in ("liveplan.glg", "extra_signals.glg"):
        for rule in parse_program((spec_dir / name).read_text()):
            check_rule(rule, cfg)
