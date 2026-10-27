"""
Tests for GuardMonitor -- the GL-Guard-backed, drop-in StatefulPhaseMonitor.

These exercise the integration contract the SWE-agent + plan_refiner depend on:
``check_step_pre_emptively`` returning a genuine ``MonitorResult`` of genuine
``RuleMatch`` objects, the blocking/rollback transaction, and the inherited
getters the refiner reads. Equivalence to the legacy *detectors* over real
trajectories is covered separately by the shadow differential harness.
"""
from __future__ import annotations

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent, MonitorResult
from plan_monitor.rules import RuleMatch
from plan_monitor.gl_guard.guard_monitor import GuardMonitor


def _event(step, command):
    return ActionEvent(step_index=step, command=command)


def _run(monitor, steps):
    """Feed (command, thought) steps; return the per-step MonitorResult list."""
    results = []
    for i, (command, thought) in enumerate(steps, start=1):
        results.append(monitor.check_step_pre_emptively(_event(i, command), thought=thought))
    return results


# -- drop-in contract ---------------------------------------------------------

def test_is_a_stateful_phase_monitor_with_the_same_surface():
    m = GuardMonitor()
    assert isinstance(m, StatefulPhaseMonitor)
    # the attributes/methods the agent + refiner read
    for attr in ("graph_builder", "step_counter", "parser", "role_history",
                 "get_current_phase", "get_phase_history", "get_unique_phases",
                 "save_graph", "update_intended_plan", "reset"):
        assert hasattr(m, attr), attr


def test_returns_monitorresult_of_rulematch():
    m = GuardMonitor()
    # a long navigation run fires the (non-blocking) dwell signal at step 7
    results = _run(m, [(f'grep -rn "tok{i}" src/mod_{i}.py', "") for i in range(7)])
    fired = results[6]
    assert isinstance(fired, MonitorResult)
    assert fired.rule_matches and all(isinstance(rm, RuleMatch) for rm in fired.rule_matches)
    rm = fired.rule_matches[0]
    assert rm.rule_id == "dwell_L_navigate"
    assert rm.message and rm.step_index == 7
    assert rm.block_execution is False
    # messages surface through the standard MonitorResult API
    assert fired.get_all_messages()
    assert fired.should_block_and_refine() is False


def test_quiet_steps_return_none():
    m = GuardMonitor()
    results = _run(m, [('grep -rn "a" src/a.py', ""), ('grep -rn "b" src/b.py', "")])
    assert results == [None, None]


# -- blocking + transactional rollback ----------------------------------------

def test_oscillation_blocks_and_rolls_back_the_tentative_step():
    m = GuardMonitor()
    cmd = 'python reproduce.py'
    # repeat the same command: the self-loop oscillation (blocking) eventually fires
    blocked_result = None
    for i in range(1, 6):
        sc_before = m.step_counter
        res = m.check_step_pre_emptively(_event(i, cmd), thought="")
        if res is not None and res.should_block_and_refine():
            blocked_result = res
            # a blocked step is rolled back: the tentative graph extension and the
            # step counter are restored (the action never executed).
            assert m.step_counter == sc_before
            break
    assert blocked_result is not None
    osc = [rm for rm in blocked_result.rule_matches if rm.rule_id == "oscillation"]
    assert osc and osc[0].block_execution is True


def test_plan_compliance_blocks_on_submit_without_patch():
    m = GuardMonitor()
    res = _run(m, [('grep -rn "bug" src/a.py', ""), ("submit", "done")])[-1]
    assert res is not None and res.should_block_and_refine() is True
    ids = {rm.rule_id for rm in res.rule_matches}
    assert "plan_compliance_skip_patch" in ids
    assert "plan_compliance_skip_validation" in ids
    assert all(rm.block_execution for rm in res.rule_matches
               if rm.rule_id.startswith("plan_compliance"))


def test_plan_compliance_fires_once_per_type():
    # once_per_key(signal) == legacy per-violation-type threshold 1: a second
    # premature submit does not re-fire the same skip signal.
    m = GuardMonitor()
    _run(m, [('grep -rn "bug" src/a.py', "")])
    first = m.check_step_pre_emptively(_event(2, "submit"), thought="")
    second = m.check_step_pre_emptively(_event(3, "submit"), thought="")
    assert first is not None and "plan_compliance_skip_patch" in {r.rule_id for r in first.rule_matches}
    second_ids = {r.rule_id for r in second.rule_matches} if second else set()
    assert "plan_compliance_skip_patch" not in second_ids


def test_thought_oscillation_blocks_on_repeated_reasoning():
    m = GuardMonitor()
    # empty actions -> think steps; identical reasoning repeated hits r_thought
    blocked = None
    for i in range(1, 6):
        res = m.check_step_pre_emptively(_event(i, ""), thought="I am stuck, retrying.")
        if res is not None and res.should_block_and_refine():
            blocked = res
            break
    assert blocked is not None
    assert any(rm.rule_id == "thought_oscillation" for rm in blocked.rule_matches)


# -- phase/getter parity + plan shim ------------------------------------------

def test_phase_tracking_advances_for_the_refiner():
    m = GuardMonitor()
    _run(m, [('grep -rn "x" src/a.py', ""), ('sed -i "s/a/b/" src/a.py', "")])
    assert m.get_current_phase() is not None
    assert m.get_phase_history()            # role_history populated
    assert "L_navigate" in m.get_unique_phases()


def test_update_intended_plan_shim():
    m = GuardMonitor()
    assert m.update_intended_plan(["L_navigate", "P", "V_regression_test"]) is True
    assert m._intended_plan == ["L_navigate", "P", "V_regression_test"]
    assert m.update_intended_plan([]) is False


def test_reset_clears_guard_state():
    m = GuardMonitor()
    _run(m, [(f'grep -rn "t{i}" src/m_{i}.py', "") for i in range(3)])
    m.reset()
    assert m.step_counter == 1
    assert m.role_history == [] and m._dwell_stream == []
    assert m.get_current_phase() is None
