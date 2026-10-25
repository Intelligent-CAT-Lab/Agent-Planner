"""Tests for model invariants and the structural-edge harvester."""
from __future__ import annotations

import pytest

from plan_monitor.gl_guard.adapters import TrajectoryModel
from plan_monitor.gl_guard.kleene import F, T
from plan_monitor.gl_guard.model import Channel, Hook, InMemoryWorld, Occurrence


def _action(oid, key="k"):
    return Occurrence(oid=oid, channel=Channel.ACTION, key=key)


def test_world_rejects_channel_mismatch():
    q_thought = Occurrence(oid=5, channel=Channel.THOUGHT, key="t")
    with pytest.raises(ValueError):
        InMemoryWorld([], [], q_thought, Hook.PROPOSE)  # propose expects action q


def test_world_rejects_history_not_before_q():
    q = _action(2)
    later = _action(3)  # oid >= q.oid on the same channel
    with pytest.raises(ValueError):
        InMemoryWorld([later], [], q, Hook.PROPOSE)


def test_history_excludes_other_channel_after_q():
    # A thought committed after q must not leak into history(thought).
    q = _action(2)
    t_before = Occurrence(oid=1, channel=Channel.THOUGHT, key="a")
    t_after = Occurrence(oid=3, channel=Channel.THOUGHT, key="b")
    w = InMemoryWorld([], [t_before, t_after], q, Hook.PROPOSE)
    hist = list(w.history(Channel.THOUGHT))
    assert hist == [t_before]


class _FakeGraph:
    def __init__(self, edges):
        self._edges = edges

    def edges(self, data=False):
        return self._edges


def test_add_structural_edges_from_graph_filters_hier():
    model = TrajectoryModel()
    g = _FakeGraph([
        ("0:f", "1:f", {"type": "hier"}),
        ("1:f", "2:f", {"type": "exec"}),   # execution edge: NOT structural
    ])
    model.add_structural_edges_from_graph(g)
    a = model.commit_action(step=1, key="0:f", phase="L_navigate", kind="view", outcome="success")
    b = model.commit_action(step=2, key="1:f", phase="L_navigate", kind="view", outcome="success")
    c = model.commit_action(step=3, key="2:f", phase="L_navigate", kind="view", outcome="success")
    w = model.world_for_observe_action(c)
    assert w.se(a, b) is T       # hier edge present
    assert w.se(b, c) is F       # exec edge was filtered out
