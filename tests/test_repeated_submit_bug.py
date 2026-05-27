"""
Test to demonstrate the bug fix for repeated submit violations.

This reproduces the exact scenario from the user's bug report where
the agent keeps submitting without completing V (testing), and the
violation should stop triggering after the threshold is reached.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.rules import PlanComplianceRule
from plan_monitor.phases import Phase


def test_repeated_submit_with_threshold():
    """
    Simulate the exact scenario from the bug report.

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"]
    - Agent navigates and patches multiple times
    - Then keeps submitting without completing V (testing)
    - Violation should trigger at most 2 times, then stop
    """
    print("\n" + "="*80)
    print("TEST: Repeated Submit Without V - Threshold Enforcement")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="plan_compliance",
        message="Plan compliance violation: {violation}. Expected to {expected}. Skipped phases: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        ending_flags=["submit"],
        phase_names={
            "L_navigate": "navigation",
            "L_reproduce": "reproducing",
            "P": "patching",
            "V": "testing"
        },
        per_violation_type_threshold=2,
        block_execution=True
    )

    # Simulate completing L_navigate, L_reproduce, and P (but not V)
    print("\nSimulate completing phases up to P (skipping V):")

    # Complete L_navigate
    phase = Phase("L_navigate")
    match = rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])
    assert match is None
    print("  ✓ L_navigate completed")

    # Complete L_reproduce
    phase = Phase("L_reproduce")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=1, command="reproduce", role_history=["L_navigate"])
    assert match is None
    print("  ✓ L_reproduce completed")

    # Complete P
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_reproduce"), step_index=2, command="edit", role_history=["L_navigate", "L_reproduce"])
    assert match is None
    print("  ✓ P completed")

    print(f"\nAfter completing L_navigate, L_reproduce, P:")
    print(f"  plan_index: {rule.plan_index}")
    print(f"  Expected next: {rule.intended_plan[rule.plan_index] if rule.plan_index < len(rule.intended_plan) else 'DONE'}")

    # Now simulate repeated submits without completing V
    print("\n" + "="*60)
    print("Agent keeps submitting without completing V (testing):")
    print("="*60)

    violation_count = 0

    # Try submitting 5 times (should only trigger twice)
    for attempt in range(1, 6):
        print(f"\nAttempt {attempt}: Submit without V")

        match = rule.check(
            current_phase=None,
            previous_phase=None,
            step_index=2 + attempt,
            command="submit",
            role_history=["L_navigate", "L_reproduce", "P"]
        )

        if match:
            violation_count += 1
            print(f"  ✓ Violation #{violation_count} triggered")
            print(f"    Message: {match.message}")
            print(f"    Skipped phases: {match.metadata.get('skipped_phases', [])}")
            print(f"    Individual counts: {rule.violation_count_per_phase}")
            print(f"    Combination counts: {rule.violation_count_per_combination}")
        else:
            print(f"  ✗ No violation (threshold reached)")
            print(f"    Individual counts: {rule.violation_count_per_phase}")
            print(f"    Combination counts: {rule.violation_count_per_combination}")

    print("\n" + "="*60)
    print(f"Total violations triggered: {violation_count}")
    print(f"Expected: 2 (threshold)")
    print("="*60)

    # Verify exactly 2 violations were triggered
    assert violation_count == 2, f"Expected 2 violations, got {violation_count}"

    # Verify V has count of 2
    assert rule.violation_count_per_phase.get("V", 0) == 2, "V should have 2 violations"

    # Verify combination ('V',) has count of 2
    assert rule.violation_count_per_combination.get(("V",), 0) == 2, "Combination ('V',) should have 2 violations"

    print("\n" + "="*80)
    print("✅ TEST PASSED: Threshold correctly limits violations!")
    print("="*80)


if __name__ == "__main__":
    try:
        test_repeated_submit_with_threshold()
        print("\n✅ Bug fix verified!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
