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


def test_oscillation_escalates_to_a_non_blocking_terminal_not_forever():
    # The escalation ladder: a stuck self-loop blocks a bounded number of times,
    # then the terminal "stop or submit" advisory fires NON-blocking and lets the
    # action through. Without the persist-across-block fix the counter would reset
    # on every block and the agent would be blocked indefinitely.
    m = GuardMonitor()
    cmd = "python reproduce.py"
    blocks, terminal = 0, None
    for i in range(1, 9):
        res = m.check_step_pre_emptively(_event(i, cmd), thought="")
        osc = [rm for rm in (res.rule_matches if res else []) if rm.rule_id == "oscillation"]
        if not osc:
            continue
        if "stop or submit" in osc[0].message.lower():
            terminal = osc[0]
            break
        assert osc[0].block_execution is True  # pre-terminal warnings block
        blocks += 1
    assert terminal is not None, "escalation never reached the terminal advisory"
    assert terminal.block_execution is False  # the exit ramp does not block
    assert 1 <= blocks <= 5  # bounded, not infinite


def test_oscillation_message_names_the_whole_cycle():
    # A genuine A-B cycle must be described as the A/B loop, not mislabelled as a
    # single-action repeat (which reads as a false positive to the agent).
    m = GuardMonitor()
    seq = ["cat foo.py", "grep bar foo.py", "cat foo.py", "grep bar foo.py"]
    msg = None
    for i, c in enumerate(seq, start=1):
        res = m.check_step_pre_emptively(_event(i, c), thought="")
        osc = [rm for rm in (res.rule_matches if res else []) if rm.rule_id == "oscillation"]
        if osc:
            msg = osc[0].message
            break
    assert msg is not None
    assert "cat foo.py" in msg and "grep bar foo.py" in msg  # both members named


def test_step_index_is_caller_trajectory_index_and_collapses_compound():
    # Surfaced step numbers must match the caller's event.step_index (as the legacy
    # monitor sets RuleMatch.step_index), and a compound command (several sub-actions
    # in one step) must map to a SINGLE step index so a message never mislabels the
    # sub-actions of one step as separate steps.
    from plan_monitor.gl_guard.adapters import occurrences_from_graph
    m = GuardMonitor()
    m.check_step_pre_emptively(_event(100, "cat a.py"), thought="")
    m.check_step_pre_emptively(_event(101, "grep x a.py && grep y b.py"), thought="")
    occ = occurrences_from_graph(m.graph_builder.G)
    assert [o.step for o in occ] == [100, 101, 101]  # caller indices; compound shares one
    # a fired RuleMatch carries the caller's step index (the refiner correlates on it)
    m.check_step_pre_emptively(_event(102, "cat a.py"), thought="")
    res = m.check_step_pre_emptively(_event(103, "grep x a.py && grep y b.py"), thought="")
    osc = [rm for rm in (res.rule_matches if res else []) if rm.rule_id == "oscillation"]
    assert osc and osc[0].step_index == 103


def test_observe_result_records_outcome_without_changing_identity():
    # The observe(result) hook records the real outcome on the committed node in
    # place (node identity unchanged, so detection is unaffected).
    from plan_monitor.gl_guard.adapters import occurrences_from_graph
    m = GuardMonitor()
    m.check_step_pre_emptively(_event(1, "python -m pytest t.py"), thought="")
    keys_before = [o.key for o in occurrences_from_graph(m.graph_builder.G)]
    m.observe_result("E   assert 1 == 2\n1 failed in 0.1s")
    occ = occurrences_from_graph(m.graph_builder.G)
    assert [o.key for o in occ] == keys_before      # identity preserved
    assert occ[-1].outcome == "failure"             # real outcome recorded


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
