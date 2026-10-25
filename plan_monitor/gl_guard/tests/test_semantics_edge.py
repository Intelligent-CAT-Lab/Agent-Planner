"""
Edge-case semantics tests that pin down the subtle corners of the design:
periodic-motif boundaries, three-valued quantifier/negation interaction, and
the propose-vs-observe treatment of q in the phase projection.
"""
from __future__ import annotations

from plan_monitor.gl_guard.interpreter import _Evaluator
from plan_monitor.gl_guard.kleene import F, T, U
from plan_monitor.gl_guard.parser import parse_formula
from .fixtures import Traj, liveplan_config

CFG = liveplan_config()


def ev(world, text):
    return _Evaluator(world, CFG).eval(parse_formula(text), {})


# -- repeat: exact periodicity boundary --------------------------------------

def test_repeat_length2_times3_requires_three_blocks():
    # AB AB AB  -> length=2, times=3 holds; the final q closes the third block.
    t = Traj()
    for _ in range(2):
        t.action("A").action("B")
    t.action("A")  # ... A B A B A, and q = B
    w = t.propose("B", key="B")  # stream: A B A B A B  (n=6, m=2, r=3)
    assert ev(w, "repeat(action, length=2, times=3)") is T
    # only two blocks present -> fails for times=3
    t2 = Traj().action("A").action("B").action("A")
    w2 = t2.propose("B", key="B")  # A B A B (n=4) -> times=3 needs n>=6
    assert ev(w2, "repeat(action, length=2, times=3)") is F


def test_repeat_boundary_n_equals_mr():
    # Exactly n == m*r with a clean motif: A A A (m=1, r=3)
    w = Traj().action("A").action("A").propose("A", key="A")  # stream A A A
    assert ev(w, "repeat(action, length=1, times=3)") is T
    # one short
    w2 = Traj().action("A").propose("A", key="A")  # stream A A, n=2 < 3
    assert ev(w2, "repeat(action, length=1, times=3)") is F


def test_repeat_unknown_identity_yields_unknown():
    # A ? A with the middle identity unknown -> could be A (T) or not (F) -> ?
    t = Traj().action("A").action(None)  # key=None -> unknown identity
    w = t.propose("A", key="A")  # stream: A None A, m=1 r=3: compare s[n]=s[n-1], s[n-1]=s[n-2]
    assert ev(w, "repeat(action, length=1, times=3)") is U


# -- count: the three bands (T / F / ?) --------------------------------------

def test_count_lower_bound_false():
    # 0 true, 1 unknown, k=2 -> a+b = 1 < 2 -> definitely F
    t = Traj().action("e", kind="edit", outcome=None)
    w = t.propose("e", key="e", kind="edit")
    phi = "count { x in history(action) | kind(x)=edit and key(x)=key(q) and outcome(x)=failure } >= kappa_fail"
    assert ev(w, phi) is F


# -- negation over exists is three-valued ------------------------------------

def test_not_exists_unknown_propagates():
    # exists is ? (only-unknown instance) -> not(exists) is ? too
    w = Traj().action("n1", phase=None, phase_available=False).propose("q")
    assert ev(w, "not exists x in history(action): phase(x) in Patch") is U


def test_not_exists_true_to_false():
    w = Traj().action("p", phase="P").propose("q")
    assert ev(w, "not exists x in history(action): phase(x) in Patch") is F


# -- run at observe(action): q is part of the projection ----------------------

def test_run_includes_committed_q_at_observe_action():
    t = Traj()
    for _ in range(6):
        t.action("nav", phase="L_navigate", kind="view", outcome="success")
    # q observed as the 7th navigate
    w = t.observe_action("nav", phase="L_navigate", kind="view", outcome="success")
    assert ev(w, "run(Navigate) >= theta_N") is T


# -- before() strictness and the "latest action" idiom -----------------------

def test_latest_action_idiom():
    # "x is the latest committed action" == not exists y: before(x, y)
    t = Traj().action("p", phase="P", outcome="failure").action("q2", phase="L_navigate")
    w = t.propose("z")
    # the P action is NOT the latest (q2 came after) -> backtrack-style guard is F
    phi = ("exists x in history(action): phase(x) in Patch and outcome(x)=failure and "
           "not exists y in history(action): before(x, y)")
    assert ev(w, phi) is F
    # make the failed patch the latest
    t2 = Traj().action("p", phase="P", outcome="failure")
    w2 = t2.propose("z")
    assert ev(w2, phi) is T
