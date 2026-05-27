"""
Test for per-violation-type threshold in PlanComplianceRule.

This test verifies that the PlanComplianceRule correctly tracks violations
per skipped phase type and stops triggering after the threshold is reached
for each specific violation type.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.rules import PlanComplianceRule
from plan_monitor.phases import Phase


def test_per_violation_type_threshold_phase_skip():
    """
    Test that per-violation-type threshold works for phase_skip violations.

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"]
    - Threshold: 2 per violation type
    - First exhaust L_reproduce threshold (skip it twice)
    - Then try to submit without V (testing) 3 times
    - First 2 times should trigger for V
    - 3rd time should NOT trigger (V threshold reached)
    """
    print("\n" + "="*80)
    print("TEST: Per-Violation-Type Threshold for Phase Skip + Submit")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    print("\n=== Phase 1: Exhaust L_reproduce threshold ===")

    # Navigate first
    print("\nStep 1: Navigate (expected)")
    phase = Phase("L_navigate")
    match = rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])
    assert match is None, "First phase should not trigger violation"
    print("  ✓ No violation")

    # Skip L_reproduce twice to exhaust its threshold
    print("\nStep 2: Skip L_reproduce → P (1st violation for L_reproduce)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=1, command="edit", role_history=["L_navigate"])
    assert match is not None, "Should trigger violation for skipping L_reproduce"
    assert "L_reproduce" in match.message or "reproducing" in match.message, "Should mention skipped phase"
    print(f"  ✓ Violation triggered: {match.message}")
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")

    print("\nStep 3: Skip L_reproduce again (2nd violation for L_reproduce)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=2, command="edit", role_history=["L_navigate"])
    assert match is not None, "Should trigger violation for skipping L_reproduce (2nd time)"
    assert "L_reproduce" in match.message or "reproducing" in match.message, "Should mention skipped phase"
    print(f"  ✓ Violation triggered: {match.message}")
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2, "L_reproduce should have 2 violations"

    print("\nStep 4: Skip L_reproduce again (3rd time - should NOT trigger)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=3, command="edit", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger violation (L_reproduce threshold exhausted)"
    print(f"  ✓ No violation triggered (L_reproduce threshold reached)")
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")

    print("\n=== Phase 2: Now test submitting without V (testing) 3 times ===")
    print("Note: L_reproduce is already exhausted, so only V should be reported")

    # Attempt 1: Submit without V (1st time for V)
    print("\nStep 5: Complete Navigate, L_reproduce, P, then submit (skip V) - 1st time")
    rule.plan_index = 3  # At V position
    rule.seen_phases = {"L_navigate": 0, "L_reproduce": 1, "P": 2}
    match = rule.check(current_phase=None, previous_phase=None, step_index=4, command="submit",
                      role_history=["L_navigate", "L_reproduce", "P"])
    assert match is not None, "Should trigger violation for skipping V (1st time)"
    reported = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Violation triggered")
    print(f"  ✓ Reported phases: {reported}")
    assert "V" in reported, "Should report V"
    assert "L_reproduce" not in reported, "L_reproduce should be filtered (exhausted)"
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("V", 0) == 1, "V should have 1 violation"

    # Attempt 2: Submit without V (2nd time for V)
    print("\nStep 6: Submit without V again - 2nd time")
    # Note: No need to reset has_ended anymore - we removed that check
    rule.plan_index = 3
    rule.seen_phases = {"L_navigate": 0, "L_reproduce": 1, "P": 2}
    match = rule.check(current_phase=None, previous_phase=None, step_index=5, command="submit",
                      role_history=["L_navigate", "L_reproduce", "P"])
    assert match is not None, "Should trigger violation for skipping V (2nd time)"
    reported = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Violation triggered")
    print(f"  ✓ Reported phases: {reported}")
    assert "V" in reported, "Should report V"
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("V", 0) == 2, "V should have 2 violations"

    # Attempt 3: Submit without V (3rd time - should NOT trigger)
    print("\nStep 7: Submit without V again - 3rd time (should NOT trigger)")
    rule.plan_index = 3
    rule.seen_phases = {"L_navigate": 0, "L_reproduce": 1, "P": 2}
    match = rule.check(current_phase=None, previous_phase=None, step_index=6, command="submit",
                      role_history=["L_navigate", "L_reproduce", "P"])
    assert match is None, "Should NOT trigger violation (V threshold exhausted)"
    print(f"  ✓ No violation triggered (V threshold reached)")
    print(f"  ✓ Final violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2, "L_reproduce should remain at 2"
    assert rule.violation_count_per_phase.get("V", 0) == 2, "V should remain at 2"

    print("\n" + "="*80)
    print("TEST PASSED: Per-violation-type threshold works correctly!")
    print("="*80)


def test_per_violation_type_threshold_premature_ending():
    """
    Test that per-violation-type threshold works for premature_ending violations.

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"]
    - Threshold: 2 per violation type
    - Agent ends execution multiple times at different points
    - Each skipped phase should be tracked separately
    """
    print("\n" + "="*80)
    print("TEST: Per-Violation-Type Threshold for Premature Ending")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Step 1: Navigate successfully
    print("\nStep 1: Navigate successfully")
    phase = Phase("L_navigate")
    match = rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])
    assert match is None, "First phase should not trigger violation"
    print("  ✓ No violation")

    # Step 2: End prematurely (1st time for L_reproduce, P, V)
    print("\nStep 2: Submit (end prematurely) - 1st violation for L_reproduce, P, V")
    match = rule.check(current_phase=None, previous_phase=None, step_index=1, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger violation for premature ending"
    print(f"  ✓ Violation triggered: {match.message}")
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 1
    assert rule.violation_count_per_phase.get("P", 0) == 1
    assert rule.violation_count_per_phase.get("V", 0) == 1

    # Step 3: Reset and end prematurely again (2nd time)
    print("\nStep 3: Reset and submit again - 2nd violation for L_reproduce, P, V")
    rule.plan_index = 1  # Still at L_reproduce
    match = rule.check(current_phase=None, previous_phase=None, step_index=2, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger violation (2nd time)"
    print(f"  ✓ Violation triggered: {match.message}")
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2
    assert rule.violation_count_per_phase.get("P", 0) == 2
    assert rule.violation_count_per_phase.get("V", 0) == 2

    # Step 4: Try to end prematurely again (3rd time - should NOT trigger)
    print("\nStep 4: Submit again (3rd time) - should NOT trigger")
    rule.plan_index = 1
    match = rule.check(current_phase=None, previous_phase=None, step_index=3, command="submit", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger violation (threshold reached for all phases)"
    print(f"  ✓ No violation triggered (all phases reached threshold)")
    print(f"  ✓ Violation counts: {rule.violation_count_per_phase}")

    print("\n" + "="*80)
    print("TEST PASSED: Per-violation-type threshold works for premature ending!")
    print("="*80)


def test_mixed_violation_types():
    """
    Test complex scenario with mixed violation types.

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"]
    - Threshold: 2
    - Skip L_reproduce twice (phase_skip) - exhausts threshold
    - End prematurely, skipping P and V - should trigger for P and V
    - Skip L_reproduce again - should NOT trigger (already exhausted)
    - End prematurely again - P and V should trigger again (2nd time)
    - End prematurely 3rd time - should NOT trigger (all exhausted)
    """
    print("\n" + "="*80)
    print("TEST: Mixed Violation Types (Phase Skip + Premature Ending)")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    print("\nPhase 1: Skip L_reproduce twice via phase_skip")

    # Navigate first
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    # Skip L_reproduce → P (1st skip of L_reproduce)
    print("  Step 1a: Skip L_reproduce → P (1st time)")
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=1, command="edit", role_history=["L_navigate"])
    assert match is not None
    print(f"    ✓ Triggered: L_reproduce count = {rule.violation_count_per_phase.get('L_reproduce', 0)}")

    # Reset and skip L_reproduce again (2nd skip of L_reproduce)
    print("  Step 1b: Skip L_reproduce → P (2nd time)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=2, command="edit", role_history=["L_navigate"])
    assert match is not None
    print(f"    ✓ Triggered: L_reproduce count = {rule.violation_count_per_phase.get('L_reproduce', 0)}")
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2, "L_reproduce should have 2 violations"

    print("\nPhase 2: End prematurely (should trigger for P and V, not L_reproduce)")

    # Reset to after L_navigate, before L_reproduce
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    # End prematurely at L_reproduce stage (skips L_reproduce, P, V)
    print("  Step 2: Submit (skips L_reproduce, P, V)")
    match = rule.check(current_phase=None, previous_phase=None, step_index=3, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger for P and V"
    # L_reproduce should NOT be in the message because it already reached threshold
    assert "L_reproduce" not in match.metadata.get("skipped_phases", []), "L_reproduce should be filtered out"
    print(f"    ✓ Triggered for: {match.metadata.get('skipped_phases', [])}")
    print(f"    ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("P", 0) == 1, "P should have 1 violation"
    assert rule.violation_count_per_phase.get("V", 0) == 1, "V should have 1 violation"
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2, "L_reproduce should still be 2"

    print("\nPhase 3: Skip L_reproduce again (3rd time - should NOT trigger)")

    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    print("  Step 3: Skip L_reproduce → P (3rd time)")
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=4, command="edit", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger (L_reproduce exhausted)"
    print(f"    ✓ Not triggered (threshold reached)")
    print(f"    ✓ Violation counts: {rule.violation_count_per_phase}")

    print("\nPhase 4: End prematurely again (should trigger for P and V 2nd time)")

    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    print("  Step 4: Submit again (2nd premature ending)")
    match = rule.check(current_phase=None, previous_phase=None, step_index=5, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger for P and V (2nd time)"
    print(f"    ✓ Triggered for: {match.metadata.get('skipped_phases', [])}")
    print(f"    ✓ Violation counts: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("P", 0) == 2, "P should have 2 violations"
    assert rule.violation_count_per_phase.get("V", 0) == 2, "V should have 2 violations"

    print("\nPhase 5: End prematurely 3rd time (should NOT trigger - all exhausted)")

    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    print("  Step 5: Submit again (3rd premature ending)")
    match = rule.check(current_phase=None, previous_phase=None, step_index=6, command="submit", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger (all phases exhausted)"
    print(f"    ✓ Not triggered (all phases reached threshold)")
    print(f"    ✓ Final violation counts: {rule.violation_count_per_phase}")

    print("\n" + "="*80)
    print("TEST PASSED: Mixed violation types work correctly!")
    print("="*80)


def test_compound_skip_partial_exhaustion():
    """
    Test the specific scenario mentioned in the requirements:
    If the violation type is "ended execution. skipped reproducing and testing",
    and "reproducing" has already reached threshold, should only trigger for "testing".

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"]
    - Threshold: 2
    - Skip L_reproduce twice (exhausts it)
    - End execution skipping L_reproduce, P, V
    - Should only report P and V (not L_reproduce)
    """
    print("\n" + "="*80)
    print("TEST: Compound Skip with Partial Exhaustion")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        ending_flags=["submit"],
        phase_names={
            "L_reproduce": "reproducing",
            "P": "patching",
            "V": "testing"
        },
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Navigate first
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    print("\nStep 1: Exhaust 'reproducing' (L_reproduce) threshold")

    # Skip L_reproduce twice
    for i in range(2):
        print(f"  Attempt {i+1}: Skip L_reproduce")
        rule.plan_index = 1
        rule.seen_phases = {"L_navigate": 0}
        phase = Phase("P")
        match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=i+1, command="edit", role_history=["L_navigate"])
        assert match is not None, f"Should trigger on attempt {i+1}"
        print(f"    ✓ Violation count for L_reproduce: {rule.violation_count_per_phase.get('L_reproduce', 0)}")

    print(f"\n  Final state: L_reproduce violations = {rule.violation_count_per_phase.get('L_reproduce', 0)}")
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2, "L_reproduce should be exhausted"

    print("\nStep 2: End execution (skip L_reproduce, P, V)")
    print("  Expected: Should only report 'patching' and 'testing', NOT 'reproducing'")

    rule.plan_index = 1  # Back to expecting L_reproduce
    rule.seen_phases = {"L_navigate": 0}

    match = rule.check(current_phase=None, previous_phase=None, step_index=3, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger violation"

    skipped = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Skipped phases in violation: {skipped}")
    print(f"  ✓ Message: {match.message}")

    # Verify L_reproduce is NOT in the skipped phases
    assert "L_reproduce" not in skipped, "L_reproduce should be filtered out (exhausted)"

    # Verify P and V ARE in the skipped phases
    assert "P" in skipped, "P should be included"
    assert "V" in skipped, "V should be included"

    # Verify the message contains "patching" and "testing" but not "reproducing"
    assert "reproducing" not in match.message, "Message should not mention 'reproducing'"
    assert "patching" in match.message, "Message should mention 'patching'"
    assert "testing" in match.message, "Message should mention 'testing'"

    print(f"  ✓ Violation counts after ending: {rule.violation_count_per_phase}")
    assert rule.violation_count_per_phase.get("P", 0) == 1, "P should have 1 violation"
    assert rule.violation_count_per_phase.get("V", 0) == 1, "V should have 1 violation"
    assert rule.violation_count_per_phase.get("L_reproduce", 0) == 2, "L_reproduce should remain at 2"

    print("\n" + "="*80)
    print("TEST PASSED: Compound skip with partial exhaustion works correctly!")
    print("="*80)


def test_combination_tracking():
    """
    Test that violation combinations are tracked separately.

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"]
    - Threshold: 2
    - Skip just L_reproduce twice (combination ["L_reproduce"])
    - Skip L_reproduce and P together twice (combination ["L_reproduce", "P"])
    - Both combinations should trigger separately, even though L_reproduce appears in both
    """
    print("\n" + "="*80)
    print("TEST: Combination Tracking (Same Phase in Different Combinations)")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Navigate first
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    print("\nPhase 1: Skip just L_reproduce twice (combination: [L_reproduce])")

    # Skip L_reproduce → P (1st time for combination [L_reproduce])
    print("  Attempt 1: Skip L_reproduce → P")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=1, command="edit", role_history=["L_navigate"])
    assert match is not None, "Should trigger (1st time for [L_reproduce])"
    print(f"    ✓ Triggered. Combinations: {rule.violation_count_per_combination}")
    assert rule.violation_count_per_combination.get(("L_reproduce",), 0) == 1

    # Skip L_reproduce → P (2nd time for combination [L_reproduce])
    print("  Attempt 2: Skip L_reproduce → P")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=2, command="edit", role_history=["L_navigate"])
    assert match is not None, "Should trigger (2nd time for [L_reproduce])"
    print(f"    ✓ Triggered. Combinations: {rule.violation_count_per_combination}")
    assert rule.violation_count_per_combination.get(("L_reproduce",), 0) == 2

    # Try 3rd time - should NOT trigger (threshold reached for this combination)
    print("  Attempt 3: Skip L_reproduce → P (should NOT trigger)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("P")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=3, command="edit", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger (threshold reached for [L_reproduce])"
    print(f"    ✓ Not triggered. Combinations: {rule.violation_count_per_combination}")

    print("\nPhase 2: Skip L_reproduce and P together (combination: [L_reproduce, P])")
    print("  Note: L_reproduce individual threshold is reached, so only [P] will be reported")

    # End execution skipping L_reproduce and P (but L_reproduce is filtered out)
    # This creates a NEW combination [P] which should trigger
    print("  Attempt 1: Skip L_reproduce and P → V")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=4, command="test", role_history=["L_navigate"])
    # L_reproduce is filtered out, leaving [P] as the combination
    assert match is not None, "Should trigger for [P]"
    print(f"    ✓ Triggered. Reported: {match.metadata.get('skipped_phases', [])}")
    print(f"    ✓ Combinations: {rule.violation_count_per_combination}")
    assert "L_reproduce" not in match.metadata.get("skipped_phases", []), "L_reproduce should be filtered out"
    assert "P" in match.metadata.get("skipped_phases", []), "P should be included"
    assert rule.violation_count_per_combination.get(("P",), 0) == 1

    # Try again - should trigger (2nd time for combination [P])
    print("  Attempt 2: Skip L_reproduce and P → V")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=5, command="test", role_history=["L_navigate"])
    assert match is not None, "Should trigger (2nd time for [P])"
    print(f"    ✓ Triggered. Combinations: {rule.violation_count_per_combination}")
    assert rule.violation_count_per_combination.get(("P",), 0) == 2

    # Try 3rd time - should NOT trigger (threshold reached for [P])
    print("  Attempt 3: Skip L_reproduce and P → V (should NOT trigger)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=6, command="test", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger (threshold reached for [P])"
    print(f"    ✓ Not triggered. Combinations: {rule.violation_count_per_combination}")

    print("\n  Final state:")
    print(f"    Individual phase counts: {rule.violation_count_per_phase}")
    print(f"    Combination counts: {rule.violation_count_per_combination}")

    print("\n" + "="*80)
    print("TEST PASSED: Combination tracking works correctly!")
    print("="*80)


def test_filtered_combination_tracking():
    """
    Test that filtered combinations have their own threshold tracking.

    Scenario:
    - Plan: ["A", "B", "C", "D"]
    - Threshold: 2
    - Exhaust individual thresholds for A and B
    - Then skip all three (A, B, C) together
    - After filtering A and B, remaining combination [C] should have its own tracking
    """
    print("\n" + "="*80)
    print("TEST: Filtered Combination Has Its Own Threshold")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["A", "B", "C", "D"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    print("\nPhase 1: Exhaust individual thresholds for A and B")

    # Skip A twice
    print("  Skip A twice:")
    for i in range(2):
        rule.plan_index = 0
        rule.seen_phases = {}
        phase = Phase("B")
        match = rule.check(current_phase=phase, previous_phase=None, step_index=i, command="cmd", role_history=[])
        assert match is not None, f"Should trigger on attempt {i+1}"
        print(f"    Attempt {i+1}: ✓ Triggered for A")

    # Skip A and B twice
    print("  Skip A,B twice:")
    for i in range(2):
        rule.plan_index = 0
        rule.seen_phases = {}
        phase = Phase("C")
        match = rule.check(current_phase=phase, previous_phase=None, step_index=2+i, command="cmd", role_history=[])
        # A is filtered out, leaving [B]
        assert match is not None, f"Should trigger on attempt {i+1}"
        print(f"    Attempt {i+1}: ✓ Triggered for B (A filtered)")

    print(f"\n  After exhausting A and B individually:")
    print(f"    Individual counts: {rule.violation_count_per_phase}")
    print(f"    Combination counts: {rule.violation_count_per_combination}")

    print("\nPhase 2: Skip A, B, C together (A and B should be filtered, leaving [C])")

    # Skip A, B, C → D (1st time for combination [C] after filtering)
    print("  Attempt 1: Skip A,B,C → D")
    rule.plan_index = 0
    rule.seen_phases = {}
    phase = Phase("D")
    match = rule.check(current_phase=phase, previous_phase=None, step_index=4, command="cmd", role_history=[])
    assert match is not None, "Should trigger for [C] (A and B filtered)"
    reported = match.metadata.get("skipped_phases", [])
    print(f"    ✓ Triggered. Reported: {reported}")
    assert "A" not in reported, "A should be filtered out"
    assert "B" not in reported, "B should be filtered out"
    assert "C" in reported, "C should be included"
    assert rule.violation_count_per_combination.get(("C",), 0) == 1

    # Try again (2nd time for combination [C])
    print("  Attempt 2: Skip A,B,C → D")
    rule.plan_index = 0
    rule.seen_phases = {}
    phase = Phase("D")
    match = rule.check(current_phase=phase, previous_phase=None, step_index=5, command="cmd", role_history=[])
    assert match is not None, "Should trigger (2nd time for [C])"
    print(f"    ✓ Triggered. Combination count: {rule.violation_count_per_combination.get(('C',), 0)}")
    assert rule.violation_count_per_combination.get(("C",), 0) == 2

    # Try 3rd time - should NOT trigger (threshold reached for [C])
    print("  Attempt 3: Skip A,B,C → D (should NOT trigger)")
    rule.plan_index = 0
    rule.seen_phases = {}
    phase = Phase("D")
    match = rule.check(current_phase=phase, previous_phase=None, step_index=6, command="cmd", role_history=[])
    assert match is None, "Should NOT trigger (threshold reached for [C])"
    print(f"    ✓ Not triggered")

    print(f"\n  Final state:")
    print(f"    Individual counts: {rule.violation_count_per_phase}")
    print(f"    Combination counts: {rule.violation_count_per_combination}")

    print("\n" + "="*80)
    print("TEST PASSED: Filtered combination has its own threshold!")
    print("="*80)


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*80)
    print("RUNNING ALL PER-VIOLATION-TYPE THRESHOLD TESTS")
    print("="*80)

    try:
        test_per_violation_type_threshold_phase_skip()
        test_per_violation_type_threshold_premature_ending()
        test_mixed_violation_types()
        test_compound_skip_partial_exhaustion()
        test_combination_tracking()
        test_filtered_combination_tracking()

        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        return True
    except AssertionError as e:
        print("\n" + "="*80)
        print(f"❌ TEST FAILED: {e}")
        print("="*80)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
