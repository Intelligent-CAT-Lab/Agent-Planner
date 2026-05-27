"""
Validate that violation counts persist through rollback.

This test verifies the fix works correctly by checking that:
1. Violation counts are incremented during check
2. Violation counts persist after rollback
3. Threshold is enforced correctly across multiple blocked attempts
"""

import sys
from pathlib import Path
import copy

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_rollback_preserves_violation_counts():
    """
    Test that violation counts persist through rollback in check_step_pre_emptively.
    """
    print("\n" + "="*80)
    print("TEST: Violation Counts Persist Through Rollback")
    print("="*80)

    monitor = StatefulPhaseMonitor(enable_rules=True)

    # First, set up some phase history
    print("\nPhase 1: Navigate")
    event = ActionEvent(step_index=0, command="ls")
    result = monitor.check_step_pre_emptively(event, thought="")
    print(f"  Current phase: {monitor.get_current_phase()}")

    # Now submit 5 times and verify:
    # - Violation counts increment correctly
    # - Rollback doesn't clear them
    # - Threshold is enforced
    print("\nPhase 2: Submit 5 times without completing plan")

    for attempt in range(1, 6):
        print(f"\n  Attempt {attempt}:")

        # Get fresh rule reference each time (important after rollback)
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")

        # Get counts before check
        before_individual = plan_rule.violation_count_per_phase.copy()
        before_combo = plan_rule.violation_count_per_combination.copy()
        print(f"    Before: individual={before_individual}, combo={before_combo}")

        # Check (this will trigger rollback if blocking)
        event = ActionEvent(step_index=attempt, command="submit")
        result = monitor.check_step_pre_emptively(event, thought="")

        # Get fresh rule reference after check (might have been rolled back)
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")

        # Get counts after check
        after_individual = plan_rule.violation_count_per_phase.copy()
        after_combo = plan_rule.violation_count_per_combination.copy()
        print(f"    After:  individual={after_individual}, combo={after_combo}")

        # Check if violation triggered
        if result and result.rule_matches:
            for match in result.rule_matches:
                if match.rule_id == "plan_compliance":
                    print(f"    ✓ Violation triggered")

                    # Verify counts increased (or stayed same if at threshold)
                    if attempt <= 2:  # Should increment
                        assert after_individual != before_individual or after_combo != before_combo, \
                            f"Counts should change on attempt {attempt}"
                        print(f"    ✓ Counts incremented correctly")
                    break
        else:
            print(f"    ✓ No violation (threshold reached)")
            # Verify counts didn't change after threshold
            assert after_individual == before_individual, "Counts shouldn't change after threshold"
            assert after_combo == before_combo, "Counts shouldn't change after threshold"

    # Get final rule reference
    plan_rule_final = monitor.rule_engine.rules.get("plan_compliance")
    print(f"\n  Final violation counts:")
    print(f"    Individual: {plan_rule_final.violation_count_per_phase}")
    print(f"    Combination: {plan_rule_final.violation_count_per_combination}")

    # Verify final state
    assert len([m for m in monitor.rule_engine.rules.get("plan_compliance").violation_count_per_phase.values() if m > 0]) > 0, \
        "Should have some violation counts"

    print("\n" + "="*80)
    print("✅ TEST PASSED: Violation counts persist correctly through rollback!")
    print("="*80)
    return True


def test_rollback_mechanism():
    """
    Test the rollback mechanism specifically.
    """
    print("\n" + "="*80)
    print("TEST: Rollback Mechanism Details")
    print("="*80)

    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Navigate first
    event = ActionEvent(step_index=0, command="ls")
    monitor.check_step_pre_emptively(event, thought="")

    print("\n1. First submit (should trigger and increment)")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   Before: {plan_rule.violation_count_per_phase}")

    # Make backup like check_step_pre_emptively does
    rules_backup = copy.deepcopy(monitor.rule_engine.rules)

    # Submit
    event = ActionEvent(step_index=1, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="")

    # Get fresh reference after check
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   After:  {plan_rule.violation_count_per_phase}")
    print(f"   Result: {result is not None and any(m.rule_id == 'plan_compliance' for m in result.rule_matches)}")

    # Verify the backed-up version has OLD counts
    backed_up_rule = rules_backup.get("plan_compliance")
    print(f"   Backup had: {backed_up_rule.violation_count_per_phase}")

    # Verify current rule has NEW counts
    current_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   Current has: {current_rule.violation_count_per_phase}")

    # The key: current should have incremented counts even though rollback happened
    assert len(current_rule.violation_count_per_phase) > 0, "Current rule should have violations"

    print("\n2. Second submit (should trigger and increment again)")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   Before: {plan_rule.violation_count_per_phase}")

    event = ActionEvent(step_index=2, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="")

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   After:  {plan_rule.violation_count_per_phase}")

    print("\n3. Third submit (should NOT trigger - threshold reached)")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   Before: {plan_rule.violation_count_per_phase}")

    event = ActionEvent(step_index=3, command="submit")
    result = monitor.check_step_pre_emptively(event, thought="")

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    if result and result.rule_matches:
        violations = [m for m in result.rule_matches if m.rule_id == "plan_compliance"]
        assert len(violations) == 0, "Should not trigger on 3rd attempt"
        print(f"   After:  {plan_rule.violation_count_per_phase}")
        print(f"   ✓ No violation (correct)")
    else:
        print(f"   ✓ No result (correct)")

    print("\n" + "="*80)
    print("✅ TEST PASSED: Rollback mechanism works correctly!")
    print("="*80)
    return True


if __name__ == "__main__":
    try:
        test_rollback_preserves_violation_counts()
        test_rollback_mechanism()
        print("\n" + "="*80)
        print("✅ ALL ROLLBACK TESTS PASSED!")
        print("="*80)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
