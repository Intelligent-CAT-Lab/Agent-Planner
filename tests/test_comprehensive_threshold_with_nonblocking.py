"""
Comprehensive test: Non-blocking rules + blocking rules + threshold enforcement.

Scenario (against the current default config: plan ["L", "P", "V"],
per_violation_type_threshold = 1):
1. Steps 0-4: Dwell rule triggers (non-blocking), state committed and the
   reset-after-fire counter advances.
2. First submit: Plan compliance triggers (blocking) for skipping patching (P)
   and testing (V), and the step is rolled back.
3. Second submit: Plan compliance does NOT trigger again -- the per-violation-type
   threshold (1) for the skipped {P, V} combination is already reached.

This ensures:
- Non-blocking dwell state is *preserved* across a blocking rollback (not wiped).
- Blocking plan-compliance violation counts increment correctly under rollback.
- Threshold enforcement works for individual phases and combinations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_comprehensive_scenario():
    """Non-blocking dwell, then blocking plan-compliance with threshold-1 enforcement."""
    monitor = StatefulPhaseMonitor(enable_rules=True)

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    threshold = plan_rule.per_violation_type_threshold  # current default: 1

    # Lower the dwell threshold so it fires quickly within the navigation phase.
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    dwell_rule.threshold = 4

    step_index = 0

    # -- Phase 1: navigate and trigger the (non-blocking) dwell rule --------------
    dwell_fired = False
    for i in range(5):
        event = ActionEvent(step_index=step_index, command=f"ls {i}")
        result = monitor.check_step_pre_emptively(event, thought=f"Navigating {i}")
        if result and any(m.rule_id == "dwell_L_navigate" for m in result.rule_matches):
            dwell_fired = True
        step_index += 1

    assert dwell_fired, "dwell_L_navigate should fire during a 5-step navigation run"
    dwell_count_after_phase1 = dwell_rule.dwell_count  # reset-after-fire -> small, but committed

    # -- Phase 2: first submit -> blocking plan compliance, step rolled back ------
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 1")
    step_index += 1

    plan_matches = [m for m in (result.rule_matches if result else []) if m.rule_id == "plan_compliance"]
    assert plan_matches, "first premature submit should trigger plan_compliance"
    assert result.should_block_and_refine(), "plan_compliance is a blocking intervention"

    # The non-blocking dwell state must survive the blocking rollback unchanged.
    assert dwell_rule.dwell_count == dwell_count_after_phase1, \
        "dwell count (non-blocking) must be preserved across the blocking submit"

    # Skipping straight to submit skips patching (P) and testing (V).
    assert plan_rule.violation_count_per_phase.get("P", 0) == 1
    assert plan_rule.violation_count_per_phase.get("V", 0) == 1
    assert plan_rule.violation_count_per_combination.get(("P", "V"), 0) == 1

    # -- Phase 3: second submit -> threshold reached, no re-trigger ---------------
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 2")

    plan_matches = [m for m in (result.rule_matches if result else []) if m.rule_id == "plan_compliance"]
    assert not plan_matches, "second submit must NOT re-trigger once the threshold is reached"
    # counts stay put -- the {P, V} combination is already at its threshold
    assert plan_rule.violation_count_per_phase.get("P", 0) == threshold
    assert plan_rule.violation_count_per_phase.get("V", 0) == threshold
    assert plan_rule.violation_count_per_combination.get(("P", "V"), 0) == threshold

    # dwell state still preserved after the second blocking check
    assert dwell_rule.dwell_count == dwell_count_after_phase1


if __name__ == "__main__":
    test_comprehensive_scenario()
    print("✅ comprehensive threshold + non-blocking test passed")
