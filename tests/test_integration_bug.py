"""
Test to reproduce the integration bug where violations keep triggering.

This simulates the exact scenario from the mini-swe-agent integration where
the agent performs multiple navigates and patches, then keeps submitting
without completing V.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_integration_repeated_submit():
    """
    Simulate the exact integration scenario.

    Phase history: Multiple L_navigate and P phases, then repeated submits.
    """
    print("\n" + "="*80)
    print("TEST: Integration - Repeated Submit Behavior")
    print("="*80)

    # Create monitor (simulates mini-swe-agent integration)
    monitor = StatefulPhaseMonitor(enable_rules=True)

    print("\nInitial state:")
    print(f"  Rules: {list(monitor.rule_engine.rules.keys())}")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    if plan_rule:
        print(f"  Plan: {plan_rule.intended_plan}")
        print(f"  Threshold: {plan_rule.per_violation_type_threshold}")
        print(f"  Ending flags: {plan_rule.ending_flags}")

    # Simulate phase history: Navigate and Patch multiple times
    phase_sequence = [
        ("ls", "L_navigate"),
        ("ls -la", "L_navigate"),
        ("find . -name '*.py'", "L_navigate"),
        ("grep -r 'function'", "L_navigate"),
        ("cat file.py", "L_navigate"),
        ("edit file.py", "P"),
        ("git diff", "L_navigate"),
        ("edit file.py", "P"),
        ("ls", "L_navigate"),
    ]

    print("\nSimulating phase sequence:")
    for step_idx, (command, expected_phase) in enumerate(phase_sequence):
        event = ActionEvent(step_index=step_idx, command=command)
        result = monitor.check_step_pre_emptively(event, thought="")

        current = monitor.get_current_phase()
        print(f"  Step {step_idx}: {command:30s} → Phase: {current}")

        if result and result.rule_matches:
            for match in result.rule_matches:
                print(f"    ⚠️  Rule {match.rule_id}: {match.message}")

    print(f"\nAfter phase sequence:")
    print(f"  Current phase: {monitor.get_current_phase()}")
    print(f"  Role history: {monitor.role_history}")
    print(f"  plan_index: {plan_rule.plan_index if plan_rule else 'N/A'}")

    # Now simulate repeated submits
    print("\n" + "="*60)
    print("Agent repeatedly submits without completing V:")
    print("="*60)

    violation_messages = []

    # Try submitting 5 times
    for attempt in range(1, 6):
        step_idx = len(phase_sequence) + attempt - 1
        event = ActionEvent(step_index=step_idx, command="submit")

        print(f"\nAttempt {attempt}: submit (before check)")
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")
        if plan_rule:
            print(f"  Before: counts={plan_rule.violation_count_per_phase}, combo={plan_rule.violation_count_per_combination}")

        result = monitor.check_step_pre_emptively(event, thought="")

        print(f"  After check:")
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")
        if plan_rule:
            print(f"  After: counts={plan_rule.violation_count_per_phase}, combo={plan_rule.violation_count_per_combination}")

        if result and result.rule_matches:
            for match in result.rule_matches:
                if match.rule_id == "plan_compliance":
                    violation_messages.append(match.message)
                    print(f"  ✗ Violation #{len(violation_messages)}: {match.message}")
                    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
                    if plan_rule:
                        print(f"    Individual counts: {plan_rule.violation_count_per_phase}")
                        print(f"    Combination counts: {plan_rule.violation_count_per_combination}")
        else:
            print(f"  ✓ No violation (threshold reached)")
            plan_rule = monitor.rule_engine.rules.get("plan_compliance")
            if plan_rule:
                print(f"    Individual counts: {plan_rule.violation_count_per_phase}")
                print(f"    Combination counts: {plan_rule.violation_count_per_combination}")

    print("\n" + "="*60)
    print(f"Total plan compliance violations: {len(violation_messages)}")
    print(f"Expected: 2 (threshold)")
    print("="*60)

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    if plan_rule:
        print(f"\nFinal rule state:")
        print(f"  plan_index: {plan_rule.plan_index}")
        print(f"  violation_count_per_phase: {plan_rule.violation_count_per_phase}")
        print(f"  violation_count_per_combination: {plan_rule.violation_count_per_combination}")

    # Verify
    if len(violation_messages) <= 2:
        print("\n" + "="*80)
        print("✅ TEST PASSED: Threshold enforced correctly!")
        print("="*80)
        return True
    else:
        print("\n" + "="*80)
        print(f"❌ TEST FAILED: Expected 2 violations, got {len(violation_messages)}")
        print("="*80)
        return False


if __name__ == "__main__":
    try:
        success = test_integration_repeated_submit()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST CRASHED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
