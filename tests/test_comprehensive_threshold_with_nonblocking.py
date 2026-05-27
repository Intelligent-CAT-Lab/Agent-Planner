"""
Comprehensive test: Non-blocking rules + blocking rules + threshold enforcement.

Scenario matches user's description:
1. Step 1-5: Dwell rule triggers (non-blocking), state committed
2. Step 7: Plan compliance rule triggers (blocking) for skipping L_reproduce
3. Step 8: Plan compliance rule triggers again (blocking)
4. Step 9: Plan compliance should NOT trigger (threshold=2 reached)
5. Verify combination tracking also works

This ensures:
- Non-blocking rule state persists across steps
- Blocking rule violation counts increment correctly with rollback
- Threshold enforcement works for individual phases and combinations
- The else branch (should_block=False) correctly preserves state
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_comprehensive_scenario():
    """
    Complete scenario with non-blocking first, then blocking with threshold.
    """
    print("\n" + "="*80)
    print("COMPREHENSIVE TEST: Non-blocking + Blocking + Threshold")
    print("="*80)

    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Verify threshold is set to 2
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"Plan compliance threshold: {plan_rule.per_violation_type_threshold}")

    # Lower dwell threshold for faster triggering
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    if dwell_rule:
        dwell_rule.threshold = 4
        print(f"Dwell L_navigate threshold: {dwell_rule.threshold}")

    step_index = 0

    # =========================================================================
    # Phase 1: Steps 0-4 - Navigate and trigger dwell rule (non-blocking)
    # =========================================================================
    print("\n" + "="*60)
    print("Phase 1: Navigate and trigger dwell rule (non-blocking)")
    print("="*60)

    for i in range(5):
        event = ActionEvent(step_index=step_index, command=f"ls {i}")
        result = monitor.check_step_pre_emptively(event, thought=f"Navigating {i}")

        dwell_triggered = False
        if result and result.rule_matches:
            for match in result.rule_matches:
                if match.rule_id == "dwell_L_navigate":
                    dwell_triggered = True
                    print(f"  Step {step_index}: ⚠️  DWELL RULE TRIGGERED (non-blocking)")
                    break

        dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
        if not dwell_triggered:
            print(f"  Step {step_index}: dwell_count={dwell_rule.dwell_count if dwell_rule else 0}")

        step_index += 1

    # Get state after dwell phase
    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\nState after Phase 1:")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'}")
    print(f"  Plan violations: {plan_rule.violation_count_per_phase if plan_rule else {}}")
    print(f"  Current phase: {monitor.get_current_phase()}")

    # =========================================================================
    # Phase 2: Step 7 - First submit attempt (blocking plan compliance)
    # =========================================================================
    print("\n" + "="*60)
    print("Phase 2: First submit attempt (should trigger and block)")
    print("="*60)

    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 1")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                print(f"  Step {step_index}: 🚫 PLAN COMPLIANCE TRIGGERED (blocking)")
                print(f"    Message: {match.message[:100]}...")
                break

    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\nState after first submit:")
    print(f"  Plan triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Dwell count: {dwell_rule.dwell_count if dwell_rule else 'N/A'} (should be preserved)")
    print(f"  Plan violations (individual): {plan_rule.violation_count_per_phase if plan_rule else {}}")
    print(f"  Plan violations (combo): {plan_rule.violation_count_per_combination if plan_rule else {}}")

    assert dwell_rule.dwell_count >= 4, "Dwell count should be preserved from Phase 1"
    assert plan_rule.violation_count_per_phase.get('L_reproduce', 0) == 1, "Should have 1 violation"

    step_index += 1

    # =========================================================================
    # Phase 3: Step 8 - Second submit attempt (should trigger and block again)
    # =========================================================================
    print("\n" + "="*60)
    print("Phase 3: Second submit attempt (should trigger and block again)")
    print("="*60)

    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 2")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                print(f"  Step {step_index}: 🚫 PLAN COMPLIANCE TRIGGERED (blocking)")
                break

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\nState after second submit:")
    print(f"  Plan triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Plan violations (individual): {plan_rule.violation_count_per_phase if plan_rule else {}}")
    print(f"  Plan violations (combo): {plan_rule.violation_count_per_combination if plan_rule else {}}")

    assert plan_rule.violation_count_per_phase.get('L_reproduce', 0) == 2, "Should have 2 violations"
    assert plan_rule.violation_count_per_phase.get('P', 0) == 2, "Should have 2 violations for P"
    assert plan_rule.violation_count_per_phase.get('V', 0) == 2, "Should have 2 violations for V"

    step_index += 1

    # =========================================================================
    # Phase 4: Step 9 - Third submit attempt (should NOT trigger - threshold reached)
    # =========================================================================
    print("\n" + "="*60)
    print("Phase 4: Third submit attempt (should NOT trigger - threshold reached)")
    print("="*60)

    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 3")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                print(f"  Step {step_index}: ❌ UNEXPECTED - PLAN COMPLIANCE TRIGGERED")
                break

    if not plan_triggered:
        print(f"  Step {step_index}: ✅ CORRECT - No plan compliance trigger")

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\nState after third submit:")
    print(f"  Plan triggered: {plan_triggered}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    print(f"  Plan violations (individual): {plan_rule.violation_count_per_phase if plan_rule else {}}")
    print(f"  Plan violations (combo): {plan_rule.violation_count_per_combination if plan_rule else {}}")

    assert not plan_triggered, "Should NOT trigger on third attempt"
    assert plan_rule.violation_count_per_phase.get('L_reproduce', 0) == 2, "Should stay at 2 violations"

    step_index += 1

    # =========================================================================
    # Phase 5: Step 10 - Fourth submit (verify still doesn't trigger)
    # =========================================================================
    print("\n" + "="*60)
    print("Phase 5: Fourth submit (verify threshold persists)")
    print("="*60)

    event = ActionEvent(step_index=step_index, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="Submitting attempt 4")

    plan_triggered = False
    if result and result.rule_matches:
        for match in result.rule_matches:
            if match.rule_id == "plan_compliance":
                plan_triggered = True
                break

    print(f"  Step {step_index}: Plan triggered: {plan_triggered} (should be False)")

    assert not plan_triggered, "Should NOT trigger on fourth attempt"

    # =========================================================================
    # Final Verification
    # =========================================================================
    print("\n" + "="*80)
    print("FINAL VERIFICATION:")
    print("="*80)

    dwell_rule = monitor.rule_engine.rules.get("dwell_L_navigate")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\n✓ Dwell rule state preserved: count={dwell_rule.dwell_count if dwell_rule else 0}")
    print(f"✓ Plan compliance individual violations: {plan_rule.violation_count_per_phase if plan_rule else {}}")
    print(f"✓ Plan compliance combination violations: {plan_rule.violation_count_per_combination if plan_rule else {}}")
    print(f"✓ Threshold enforcement working correctly")
    print(f"✓ Non-blocking and blocking rules coexist correctly")

    print("\n✅ ALL COMPREHENSIVE TESTS PASSED!")
    return True


if __name__ == "__main__":
    try:
        test_comprehensive_scenario()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ ASSERTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
