"""
Test scenario: Non-blocking rule triggers first, then blocking rule triggers later.

Scenario:
1. Step 1-5: Navigate repeatedly, dwell rule triggers (non-blocking)
2. Step 6: Try to submit, plan compliance rule triggers (blocking)
3. Step 7: Try to submit again, plan compliance rule triggers again (blocking)
4. Step 8: Try to submit third time, should NOT trigger (threshold reached)

This tests that:
- Non-blocking rule state is preserved when no rollback happens
- Blocking rule violation counts persist across rollbacks
- Threshold enforcement works correctly
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_nonblocking_then_blocking():
    """
    Test that non-blocking rule state and blocking rule violation counts both work correctly.
    """
    print("\n" + "="*80)
    print("TEST: Non-blocking rule first, then blocking rule")
    print("="*80)

    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Step 0: Navigate (establish plan)
    print("\nPhase 1: Initial navigate")
    step_index = 0
    event = ActionEvent(step_index=step_index, command="ls")
    result = monitor.check_step_pre_emptively(event, thought="Let me start")
    print(f"  Step {step_index}: Phase = {monitor.get_current_phase()}")
    step_index += 1

    # Steps 1-8: Stay in L_navigate (should trigger dwell rule eventually)
    print("\nPhase 2: Dwell in L_navigate (trigger non-blocking dwell rule)")
    print("-"*60)
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    if dwell_rule:
        print(f"  Dwell rule threshold: {dwell_rule.threshold}")

    for i in range(1, 9):
        event = ActionEvent(step_index=step_index, command=f"ls -l {i}")
        result = monitor.check_step_pre_emptively(event, thought=f"Still navigating {i}")

        # Check if dwell rule triggered
        triggered = False
        if result and result.rule_matches:
            for match in result.rule_matches:
                if match.rule_id == "dwell_L_navigate":
                    triggered = True
                    break

        # Get dwell rule state
        dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
        dwell_count = dwell_rule.dwell_count if dwell_rule else 0

        print(f"  Step {step_index}: dwell_count={dwell_count}, dwell_triggered={triggered}")
        step_index += 1

    # Now try to submit without completing plan (blocking plan compliance rule)
    print("\nPhase 3: Try to submit without completing plan")
    print("-"*60)

    # Get initial states
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")

    print(f"\nBefore first submit:")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else 'N/A'}")

    # Attempt 1: Submit (should trigger plan compliance, blocking)
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 1")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                break

    # Get states after attempt 1
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")

    print(f"\nAfter submit attempt 1 (step {step_index}):")
    print(f"  Plan rule triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else 'N/A'}")

    step_index += 1

    # Attempt 2: Submit again (should trigger plan compliance again, blocking)
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 2")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                break

    # Get states after attempt 2
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")

    print(f"\nAfter submit attempt 2 (step {step_index}):")
    print(f"  Plan rule triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else 'N/A'}")

    step_index += 1

    # Attempt 3: Submit third time (should NOT trigger - threshold reached)
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 3")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                break

    # Get states after attempt 3
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")

    print(f"\nAfter submit attempt 3 (step {step_index}):")
    print(f"  Plan rule triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else 'N/A'}")

    # Verification
    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)

    success = True

    # Check dwell rule state is preserved
    if dwell_rule and dwell_rule.dwell_count > 0:
        print(f"✓ Dwell rule state preserved (count={dwell_rule.dwell_count})")
    else:
        print(f"✗ Dwell rule state NOT preserved")
        success = False

    # Check plan compliance violation counts
    if plan_rule:
        counts = plan_rule.violation_count_per_phase
        if counts.get('L_reproduce', 0) == 2 and counts.get('P', 0) == 2 and counts.get('V', 0) == 2:
            print(f"✓ Plan compliance violation counts correct: {counts}")
        else:
            print(f"✗ Plan compliance violation counts incorrect: {counts}")
            success = False
    else:
        print(f"✗ Plan compliance rule not found")
        success = False

    if success:
        print("\n✅ TEST PASSED!")
        return True
    else:
        print("\n❌ TEST FAILED!")
        return False


if __name__ == "__main__":
    try:
        success = test_nonblocking_then_blocking()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
