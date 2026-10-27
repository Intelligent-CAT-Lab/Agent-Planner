"""
Integration tests for GuardRuntime: detection + emission + advice, and the key
equivalence property — dwell timing matching the legacy reset-after-fire counter.
"""
from __future__ import annotations

from pathlib import Path

from plan_monitor.gl_guard.advice import AdviceRegistry
from plan_monitor.gl_guard.engine import GuardProgram
from plan_monitor.gl_guard.runtime import GuardRuntime
from .fixtures import Traj

SPEC_DIR = Path(__file__).resolve().parents[1] / "specs"


def _runtime():
    program = GuardProgram.load(SPEC_DIR / "liveplan.glg", SPEC_DIR / "liveplan.config.json")
    registry = AdviceRegistry.load(SPEC_DIR / "liveplan.advice.json")
    return GuardRuntime(program, registry)


def _fired_names(reports):
    return [r.rule_id for r in reports]


def test_dwell_emits_at_7_and_14_like_legacy():
    """dwell_L_navigate must fire at in-phase steps 7 and 14 only."""
    rt = _runtime()
    fired_steps = []
    for k in range(1, 15):
        # a propose world whose phase projection has k Navigate symbols,
        # each with a distinct key (so no oscillation / revisit noise).
        t = Traj()
        for i in range(k - 1):
            t.action(f"nav{i}", phase="L_navigate", kind="view")
        world = t.propose(f"nav{k-1}", key=f"nav_q{k}", phase="L_navigate", kind="view")
        names = _fired_names(rt.evaluate(world))
        if "dwell_L_navigate" in names:
            fired_steps.append(k)
    assert fired_steps == [7, 14]


def test_dwell_resets_when_phase_breaks():
    rt = _runtime()
    fired = []
    # navigate 7 (fires at 7), then one patch step (breaks run), then navigate again
    phases = ["L_navigate"] * 7 + ["P"] + ["L_navigate"] * 7
    committed = []
    for k, ph in enumerate(phases, start=1):
        t = Traj()
        for key, p in committed:
            t.action(key, phase=p, kind="view")
        world = t.propose(f"q{k}", key=f"q{k}", phase=ph, kind="view")
        names = _fired_names(rt.evaluate(world))
        if "dwell_L_navigate" in names:
            fired.append(k)
        committed.append((f"c{k}", ph))
    # fires at step 7; the P at step 8 resets; the next 7 navigates fire at step 15
    assert fired == [7, 15]


def test_repeated_view_once_per_key():
    rt = _runtime()
    # view "loc" twice (committed) then propose viewing it again -> revisit fires once
    t = Traj().action("loc", kind="view")
    w1 = t.propose("loc", key="loc", kind="view")
    assert "repeated_view" in _fired_names(rt.evaluate(w1))
    # proposing the same view again: once_per_key suppresses the second warning
    w2 = t.propose("loc", key="loc", kind="view")
    assert "repeated_view" not in _fired_names(rt.evaluate(w2))


def test_oscillation_blocks_and_hits_terminal_variant():
    rt = _runtime()
    reports_seen = []
    for _ in range(6):
        w = Traj().action("A").propose("A", key="A")  # self-loop: repeat true, motif "A"
        reports_seen.append(rt.evaluate(w))
    osc = [[r for r in reps if r.rule_id == "oscillation"] for reps in reports_seen]
    emitted = [bool(x) for x in osc]
    # first 5 emit, 6th suppressed by max_per_pattern(max=5)
    assert emitted == [True, True, True, True, True, False]
    # the 5th emission uses the terminal "max_repeats" variant
    assert "stop or submit" in osc[4][0].message.lower()
    # oscillation is a blocking intervention
    assert osc[0][0].block_execution is True


def _runtime_with_disabled(signal_id):
    """A runtime over the liveplan specs with one signal forced shadow-disabled."""
    program = GuardProgram.load(SPEC_DIR / "liveplan.glg", SPEC_DIR / "liveplan.config.json")
    registry = AdviceRegistry.load(SPEC_DIR / "liveplan.advice.json")
    registry.entries[signal_id].enabled = False
    return GuardRuntime(program, registry)


def test_shadow_signal_inert_in_production_visible_in_shadow():
    # The enable/disable mechanism: a disabled signal is fully inert in production
    # (not evaluated, never surfaced) yet visible under include_disabled (shadow).
    w = Traj().action("loc", kind="view").propose("loc", key="loc", kind="view")
    assert "repeated_view" not in _fired_names(_runtime_with_disabled("repeated_view").evaluate(w))
    assert "repeated_view" in _fired_names(
        _runtime_with_disabled("repeated_view").evaluate(w, include_disabled=True))


def test_plan_compliance_signals_enabled_and_blocking():
    # The plan-compliance decomposition is enabled and blocking by default, with
    # its threshold state persisting across a block (it is excluded from the
    # roll-back-on-block set, mirroring the legacy monitor).
    rt = _runtime()
    for sid in ("plan_compliance_premature_patch", "plan_compliance_premature_validate",
                "plan_compliance_skip_patch", "plan_compliance_skip_validation"):
        entry = rt.registry.get(sid)
        assert entry is not None and entry.enabled and entry.block_execution
        assert entry.persist_on_block
    assert rt.rollback_on_block_ids() == {"oscillation", "thought_oscillation"}
    # submitting without a patch/validation fires the skip signals (blocking)
    w = Traj().action("loc", phase="L_navigate", kind="view").propose("s", kind="submit")
    fired = _fired_names(rt.evaluate(w))
    assert "plan_compliance_skip_patch" in fired
    assert "plan_compliance_skip_validation" in fired


def test_propose_is_transactional():
    """commit=False must not advance emission state (tentative pre-check)."""
    rt = _runtime()
    w = Traj().action("loc", kind="view").propose("loc", key="loc", kind="view")
    # tentative evaluation fires but rolls back its emission bookkeeping
    assert "repeated_view" in _fired_names(rt.evaluate(w, commit=False))
    # because it rolled back, a committed evaluation still sees it as first-time
    assert "repeated_view" in _fired_names(rt.evaluate(w, commit=True))
    # now committed state is set, so a second committed eval is suppressed
    assert "repeated_view" not in _fired_names(rt.evaluate(w, commit=True))


def test_default_order_is_declaration_order():
    # two co-firing signals with default priority keep spec declaration order.
    rt = _runtime()
    # Build a self-loop navigate at in-phase step 7 so dwell_L_navigate AND
    # oscillation both fire; declaration order has oscillation first.
    t = Traj()
    for _ in range(6):
        t.action("A", phase="L_navigate", kind="view")
    world = t.propose("A", key="A", phase="L_navigate", kind="view")
    names = _fired_names(rt.evaluate(world))
    assert "oscillation" in names and "dwell_L_navigate" in names
    assert names.index("oscillation") < names.index("dwell_L_navigate")
