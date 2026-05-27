"""
Test scenario: Non-blocking and blocking rules trigger in the SAME step.

Scenario:
1. Dwell in L_navigate until dwell threshold
2. At the SAME step where dwell triggers, also try to submit (blocking plan compliance)

This tests that:
- When both non-blocking and blocking rules trigger simultaneously
- Blocking rule causes rollback
- Non-blocking rule state is also rolled back (correct behavior since action didn't execute)
- But plan compliance violation counts persist
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_simultaneous_nonblocking_blocking():
    """
    Test both non-blocking and blocking rules triggering in same step.
    """
    print("\n" + "="*80)
    print("TEST: Non-blocking and blocking rules trigger simultaneously")
    print("="*80)

    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Lower dwell threshold for testing
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    if dwell_rule:
        dwell_rule.threshold = 3  # Trigger after 3 steps in same phase
        print(f"Set dwell threshold to: {dwell_rule.threshold}")

    # Step 0: Navigate (establish plan)
    print("\nStep 0: Initial navigate")
    step_index = 0
    event = ActionEvent(step_index=step_index, command="ls")
    result = monitor.check_step_pre_emptively(event, thought="Let me start")
    print(f"  Phase = {monitor.get_current_phase()}")
    step_index += 1

    # Steps 1-2: Stay in L_navigate (building up to dwell threshold)
    print("\nSteps 1-2: Dwell in L_navigate")
    for i in range(2):
        event = ActionEvent(step_index=step_index, command=f"ls -l {i}")
        result = monitor.check_step_pre_emptively(event, thought=f"Still navigating")

        dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
        print(f"  Step {step_index}: dwell_count={dwell_rule.dwell_count if dwell_rule else 0}")
        step_index += 1

    # Get state before the critical step
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\nBefore critical step:")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else {}}")

    # Step 3: Try to submit - this will:
    # 1. Stay in L_navigate (dwell_count will hit threshold=3, trigger non-blocking dwell rule)
    # 2. Try to end execution (trigger blocking plan compliance rule)
    print(f"\nStep {step_index}: CRITICAL - submit while at dwell threshold")
    print("  Expected: both dwell rule AND plan compliance trigger")
    print("  Expected: plan compliance blocks, dwell increment is rolled back")

    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting")

    # Check which rules triggered
    dwell_triggered = False
    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "dwell_L_navigate":
                dwell_triggered = True
            if match.rule_id == "plan_compliance":
                plan_triggered = True

    # Get states after
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\nAfter critical step:")
    print(f"  Dwell rule triggered: {dwell_triggered}")
    print(f"  Plan rule triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else {}}")

    step_index += 1

    # Verification
    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)

    success = True

    # Check that dwell count was rolled back (stayed at 3, not incremented to 4)
    # Because the action was blocked and never executed
    if dwell_rule:
        if dwell_rule.dwell_count == 3:
            print(f"✓ Dwell count correctly rolled back (stayed at {dwell_rule.dwell_count})")
        else:
            print(f"✗ Dwell count NOT rolled back correctly: {dwell_rule.dwell_count} (expected 3)")
            success = False

    # Check plan compliance violation counts persisted
    if plan_rule:
        counts = plan_rule.violation_count_per_phase
        if counts.get('L_reproduce', 0) == 1 and counts.get('P', 0) == 1 and counts.get('V', 0) == 1:
            print(f"✓ Plan compliance violation counts persisted: {counts}")
        else:
            print(f"✗ Plan compliance violation counts incorrect: {counts}")
            success = False

    # Check both rules triggered
    if plan_triggered and dwell_triggered:
        print(f"✓ Both rules triggered as expected")
    else:
        print(f"✗ Not both rules triggered: dwell={dwell_triggered}, plan={plan_triggered}")
        success = False

    # Now try submit again to verify threshold still works
    print(f"\n\nStep {step_index}: Submit again (second attempt)")
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 2")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                break

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"  Plan rule triggered: {plan_triggered}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else {}}")

    if plan_triggered and plan_rule:
        counts = plan_rule.violation_count_per_phase
        if counts.get('L_reproduce', 0) == 2 and counts.get('P', 0) == 2 and counts.get('V', 0) == 2:
            print(f"✓ Second violation incremented correctly")
        else:
            print(f"✗ Second violation counts incorrect: {counts}")
            success = False

    step_index += 1

    # Third attempt should not trigger (threshold=2 reached)
    print(f"\nStep {step_index}: Submit third time (should not trigger)")
    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 3")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                break

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"  Plan rule triggered: {plan_triggered}")
    print(f"  Plan violation counts: {plan_rule.violation_count_per_phase if plan_rule else {}}")

    if not plan_triggered:
        print(f"✓ Third attempt correctly did not trigger (threshold reached)")
    else:
        print(f"✗ Third attempt incorrectly triggered")
        success = False

    if success:
        print("\n✅ ALL CHECKS PASSED!")
        return True
    else:
        print("\n❌ SOME CHECKS FAILED!")
        return False


if __name__ == "__main__":
    try:
        success = test_simultaneous_nonblocking_blocking()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
