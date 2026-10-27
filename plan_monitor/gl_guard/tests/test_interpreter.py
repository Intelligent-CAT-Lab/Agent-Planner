"""Three-valued finite-prefix semantics tests (design section 5)."""
from __future__ import annotations

from plan_monitor.gl_guard.interpreter import _Evaluator
from plan_monitor.gl_guard.kleene import F, T, U
from plan_monitor.gl_guard.parser import parse_formula
from .fixtures import Traj, liveplan_config

CFG = liveplan_config()


def ev(world, text):
    return _Evaluator(world, CFG).eval(parse_formula(text), {})


# -- exists -------------------------------------------------------------------

def test_exists_true_false_empty():
    w = Traj().action("n1", phase="L_navigate").propose("q")
    assert ev(w, "exists x in history(action): phase(x) in Navigate") is T
    assert ev(w, "exists x in history(action): phase(x) in Patch") is F
    # empty history -> F
    w0 = Traj().propose("q")
    assert ev(w0, "exists x in history(action): phase(x) in Patch") is F


def test_exists_unknown_when_only_unknowns():
    # an action whose phase is unavailable; membership is ? for that instance
    w = Traj().action("n1", phase=None, phase_available=False).propose("q")
    assert ev(w, "exists x in history(action): phase(x) in Patch") is U


def test_history_excludes_q():
    # q has the same key as nothing in history -> revisit is F even though q exists
    w = Traj().action("a", kind="view").propose("q", key="qk", kind="view")
    assert ev(w, "revisit(action)") is F
    w2 = Traj().action("a", kind="view").propose("q", key="a", kind="view")
    assert ev(w2, "revisit(action)") is T


# -- count --------------------------------------------------------------------

def test_count_threshold():
    t = (Traj()
         .action("e", kind="edit", outcome="failure")
         .action("e", kind="edit", outcome="failure"))
    w = t.propose("q", key="e", kind="edit")
    phi = "count { x in history(action) | kind(x)=edit and key(x)=key(q) and outcome(x)=failure } >= kappa_fail"
    assert ev(w, phi) is T  # kappa_fail = 2
    w1 = Traj().action("e", kind="edit", outcome="failure").propose("q", key="e", kind="edit")
    assert ev(w1, phi) is F  # only 1 failure


def test_count_unknown_band():
    # 1 definite failure + 1 unknown outcome; k=2 -> a=1,b=1 -> a>=k? no; a+b<k? 2<2 no -> ?
    t = (Traj()
         .action("e", kind="edit", outcome="failure")
         .action("e", kind="edit", outcome=None))
    w = t.propose("q", key="e", kind="edit")
    phi = "count { x in history(action) | kind(x)=edit and key(x)=key(q) and outcome(x)=failure } >= kappa_fail"
    assert ev(w, phi) is U


# -- run ----------------------------------------------------------------------

def test_run_counts_occurrences_not_compressed():
    t = Traj()
    for _ in range(6):
        t.action("nav", phase="L_navigate", kind="view")
    # q also navigate -> 7 occurrences in projection
    w = t.propose("q", phase="L_navigate", kind="view")
    assert ev(w, "run(Navigate) >= theta_N") is T  # theta_N = 7


def test_run_false_when_recent_breaks():
    t = Traj()
    for _ in range(6):
        t.action("nav", phase="L_navigate", kind="view")
    t.action("p", phase="P", kind="edit")  # breaks the run
    w = t.propose("q", phase="L_navigate", kind="view")
    assert ev(w, "run(Navigate) >= theta_N") is F


def test_run_requires_a_single_phase_dwell():
    # A mix of two Validate-group phases is NOT a run (legacy dwell resets on the
    # exact phase change), even though both are in Validate.
    t = Traj()
    for _ in range(4):
        t.action("vr", phase="V_regression_test", kind="run_test")
    for _ in range(3):
        t.action("vn", phase="V_newly_generated_test", kind="run_test")
    w = t.propose("q", phase="V_newly_generated_test", kind="run_test")
    # last 7 are mixed V_regression / V_newly -> not a single-phase run
    assert ev(w, "run(Validate) >= 7") is F
    # but 4 consecutive identical V_newly (incl q) is a run of 4
    assert ev(w, "run(Validate) >= 4") is T
    assert ev(w, "run(Validate) >= 5") is F


def test_run_general_actions_dropped_from_projection():
    t = Traj()
    for _ in range(3):
        t.action("nav", phase="L_navigate", kind="view")
        t.action("g", phase=None, kind="general")  # general -> dropped
    # projection has 3 Navigate + q = 4 Navigate symbols, < 7
    w = t.propose("q", phase="L_navigate", kind="view")
    assert ev(w, "run(Navigate) >= 4") is T
    assert ev(w, "run(Navigate) >= 5") is F


# -- repeat -------------------------------------------------------------------

def test_repeat_self_loop():
    # A A (q) -> length=1 times=2 over [A, q=A]
    w = Traj().action("A").propose("q", key="A")
    assert ev(w, "repeat(action, length=1, times=2)") is T
    w2 = Traj().action("B").propose("q", key="A")
    assert ev(w2, "repeat(action, length=1, times=2)") is F


def test_repeat_abab_cycle():
    # stream A B A B (q=A) ... we want ABAB with revisit; length=2 times=2 needs
    # s[n-j]=s[n-2-j] for j in {0,1}: last 4 form ABAB
    t = Traj().action("A").action("B").action("A").action("B")
    w = t.propose("q", key="A")  # stream: A B A B A
    assert ev(w, "repeat(action, length=2, times=2)") is T
    # break it
    t2 = Traj().action("A").action("B").action("C").action("B")
    w2 = t2.propose("q", key="A")
    assert ev(w2, "repeat(action, length=2, times=2)") is F


def test_repeat_too_short_is_false():
    w = Traj().action("A").propose("q", key="B")
    assert ev(w, "repeat(action, length=2, times=2)") is F


def test_thought_repeat_scoped_to_episode():
    # thoughts after the last action form the episode. Same thought 3x -> fires.
    t = (Traj()
         .action("a1")               # last executable action
         .thought("h").thought("h"))
    w = t.observe_thought("h")       # episode = [h, h, h]
    assert ev(w, "repeat(thought, length=1, times=3)") is T
    # a thought before the last action must NOT be conflated into the episode
    t2 = (Traj()
          .thought("h")
          .action("a1")
          .thought("h"))
    w2 = t2.observe_thought("h")     # episode = [h, h] only
    assert ev(w2, "repeat(thought, length=1, times=3)") is F


# -- kleene connectives -------------------------------------------------------

def test_strong_kleene_or_short_circuits_true():
    # True or ? == True
    w = Traj().action("n1", phase="L_navigate").propose("q", phase="L_navigate")
    phi = "phase(q) in Navigate or exists x in history(action): phase(x) in Patch"
    assert ev(w, phi) is T


def test_se_unknown_without_edges():
    w = Traj().action("a").propose("q", key="a")
    # SE between q and itself-key a with no edges -> F (definite, edge absent)
    assert ev(w, "exists x in history(action): SE(node(x), node(q))") is F
