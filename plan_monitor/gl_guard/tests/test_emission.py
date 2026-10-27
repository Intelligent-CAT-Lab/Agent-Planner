"""Unit tests for the emission policies."""
from __future__ import annotations

import pytest

from plan_monitor.gl_guard.emission import (
    Always, Cooldown, EmissionPolicy, EmissionState, EveryN, MaxPerPattern,
    OncePerKey, OnRisingEdge,
)


def _run(policy, verdicts, steps=None):
    """Feed a sequence of booleans; return the steps (1-indexed) that emitted."""
    cell = {}
    steps = steps or list(range(1, len(verdicts) + 1))
    emitted = []
    for i, (v, s) in enumerate(zip(verdicts, steps), start=1):
        d = policy.decide(cell, s, v)
        if d.emit:
            emitted.append(i)
    return emitted


def test_always():
    assert _run(Always(), [True, False, True]) == [1, 3]


def test_once_per_key():
    assert _run(OncePerKey(), [True, True, False, True]) == [1]


def test_on_rising_edge():
    assert _run(OnRisingEdge(), [True, True, False, True, True]) == [1, 4]


def test_every_n_reproduces_dwell_timing():
    # 14 consecutive true verdicts, period 7 -> emits at the 7th and 14th.
    verdicts = [False] * 6 + [True] * 8   # true from in-phase step 7..14
    emitted = _run(EveryN(period=7), verdicts)
    assert emitted == [7, 14]


def test_every_n_resets_on_break():
    # A break resets the counter, so the next true starts a fresh run and emits
    # immediately (consecutive == 1). This is exactly the dwell behaviour: after
    # leaving a phase, re-entry starts counting from scratch.
    verdicts = [True] + [False] + [True] * 7
    emitted = _run(EveryN(period=7), verdicts)
    # index 1 emits; break at 2 resets; index 3 is a fresh first-true -> emits;
    # indices 4..9 are consecutive 2..7 -> none hit the period again.
    assert emitted == [1, 3]


def test_cooldown():
    # true every step, gap 3, steps 1..6 -> emit at 1, 4
    emitted = _run(Cooldown(gap=3), [True] * 6, steps=[1, 2, 3, 4, 5, 6])
    assert emitted == [1, 4]


def test_max_per_pattern_with_terminal():
    policy = MaxPerPattern(max_emits=3, terminal_variant="stop")
    cell = {}
    decisions = [policy.decide(cell, i, True) for i in range(1, 6)]
    emits = [(d.emit, d.message_variant) for d in decisions]
    assert emits == [(True, None), (True, None), (True, "stop"), (False, None), (False, None)]


def test_state_snapshot_restore():
    state = EmissionState()
    policy = OncePerKey()
    policy.decide(state.cell("sig", "k"), 1, True)   # fires, marks state
    snap = state.snapshot()
    # a tentative evaluation that marks another key
    policy.decide(state.cell("sig", "k2"), 2, True)
    state.restore(snap)
    # k2 should be gone; k should remain fired (so it won't re-fire)
    assert state.cell("sig", "k2") == {}
    assert state.cell("sig", "k").get("fired") == 1


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        EmissionPolicy.from_config({"mode": "nope"})
