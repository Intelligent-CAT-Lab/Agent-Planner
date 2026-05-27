"""
Test for prefix matching in threshold checking.

Verifies that when checking thresholds:
- If "V" has reached threshold, "V_regression_test" is also considered reached
- If "V_regression_test" has reached threshold, "V" is also considered reached
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.rules import PlanComplianceRule
from plan_monitor.phases import Phase


def test_prefix_threshold_forward():
    """
    Test that if a prefix phase reaches threshold, specific phases are also filtered.

    Scenario:
    - Plan: ["L_navigate", "V", "P"]
    - Skip "V" twice (exhaust threshold)
    - Then skip "V_regression_test" and "P" together
    - "V_regression_test" should be filtered because "V" reached threshold
    - Only "P" should be reported
    """
    print("\n" + "="*80)
    print("TEST: Prefix Threshold - Specific Phase Filtered When Prefix Exhausted")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "V", "P"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Navigate first
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    print("\nPhase 1: Exhaust 'V' threshold")

    # Skip V → P twice
    for i in range(2):
        print(f"  Attempt {i+1}: Skip V → P")
        rule.plan_index = 1
        rule.seen_phases = {"L_navigate": 0}
        phase = Phase("P")
        match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=i+1, command="patch", role_history=["L_navigate"])
        assert match is not None, f"Should trigger on attempt {i+1}"
        print(f"    ✓ Violation count for V: {rule.violation_count_per_phase.get('V', 0)}")

    print(f"\n  V violations: {rule.violation_count_per_phase.get('V', 0)}")
    assert rule.violation_count_per_phase.get("V", 0) == 2

    print("\nPhase 2: Now try skipping to V_regression_test")
    print("  Expected: V_regression_test should be filtered (V exhausted)")

    # Reset and skip to V_regression_test
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V_regression_test")

    # V_regression_test matches V via prefix, so should advance without violation
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=3, command="test", role_history=["L_navigate"])
    assert match is None, "V_regression_test should satisfy V (prefix match, no skip violation)"
    print("  ✓ V_regression_test satisfies V expectation (no skip violation)")

    print("\nPhase 3: Now end prematurely (skip V and P)")
    print("  Expected: Only P should be reported (V is exhausted)")

    # Reset to after L_navigate
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    # End execution
    match = rule.check(current_phase=None, previous_phase=None, step_index=4, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger for P"
    reported = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Reported phases: {reported}")
    assert "V" not in reported, "V should be filtered (exhausted)"
    assert "P" in reported, "P should be included"

    print(f"\n  Final violation counts: {rule.violation_count_per_phase}")

    print("\n" + "="*80)
    print("TEST PASSED: Specific phase filtered when prefix exhausted!")
    print("="*80)


def test_prefix_threshold_reverse():
    """
    Test that if a specific phase reaches threshold, its prefix is also filtered.

    Scenario:
    - Plan: ["L_navigate", "V_regression_test", "P"]
    - Skip "V_regression_test" twice (exhaust threshold)
    - Then end execution skipping "V_regression_test" and "P"
    - Since V_regression_test is exhausted, "V" is also considered exhausted
    - Only "P" should be reported
    """
    print("\n" + "="*80)
    print("TEST: Prefix Threshold - Prefix Filtered When Specific Phase Exhausted")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "V_regression_test", "P"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Navigate first
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    print("\nPhase 1: Exhaust 'V_regression_test' threshold")

    # Skip V_regression_test → P twice
    for i in range(2):
        print(f"  Attempt {i+1}: Skip V_regression_test → P")
        rule.plan_index = 1
        rule.seen_phases = {"L_navigate": 0}
        phase = Phase("P")
        match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=i+1, command="patch", role_history=["L_navigate"])
        assert match is not None, f"Should trigger on attempt {i+1}"
        print(f"    ✓ Violation count for V_regression_test: {rule.violation_count_per_phase.get('V_regression_test', 0)}")

    print(f"\n  V_regression_test violations: {rule.violation_count_per_phase.get('V_regression_test', 0)}")
    assert rule.violation_count_per_phase.get("V_regression_test", 0) == 2

    print("\nPhase 2: End prematurely (skip V_regression_test and P)")
    print("  Expected: Only P should be reported (V_regression_test is exhausted)")

    # Reset to after L_navigate
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    # End execution
    match = rule.check(current_phase=None, previous_phase=None, step_index=3, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger for P"
    reported = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Reported phases: {reported}")
    assert "V_regression_test" not in reported, "V_regression_test should be filtered (exhausted)"
    assert "P" in reported, "P should be included"

    print(f"\n  Final violation counts: {rule.violation_count_per_phase}")

    print("\n" + "="*80)
    print("TEST PASSED: Prefix filtered when specific phase exhausted!")
    print("="*80)


def test_multiple_variants_share_threshold():
    """
    Test that V and V_* variants share threshold via prefix matching.

    Scenario:
    - Plan: ["L_navigate", "V", "P"]
    - Skip "V" twice (exhaust V threshold)
    - Then try to skip "V" again via ending
    - "V" should be filtered because threshold reached
    """
    print("\n" + "="*80)
    print("TEST: V Exhaustion Also Filters V_* Variants")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "V", "P"],
        ending_flags=["submit"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Navigate first
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    print("\nPhase 1: Skip 'V' twice")
    for i in range(2):
        rule.plan_index = 1
        rule.seen_phases = {"L_navigate": 0}
        phase = Phase("P")
        match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=i+1, command="patch", role_history=["L_navigate"])
        assert match is not None, f"Should trigger on attempt {i+1}"
        print(f"  Attempt {i+1}: ✓ V count = {rule.violation_count_per_phase.get('V', 0)}")

    print(f"\n  V threshold exhausted: {rule.violation_count_per_phase.get('V', 0)}")

    print("\nPhase 2: End prematurely, check if V is filtered")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}

    match = rule.check(current_phase=None, previous_phase=None, step_index=3, command="submit", role_history=["L_navigate"])
    assert match is not None, "Should trigger for P only"
    reported = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Reported: {reported}")
    assert "V" not in reported, "V should be filtered (exhausted)"
    assert "P" in reported, "P should be included"

    print(f"\n  Final counts: {rule.violation_count_per_phase}")

    print("\n" + "="*80)
    print("TEST PASSED: V exhaustion filters correctly!")
    print("="*80)


def test_config_plan_uses_generic_v():
    """
    Test realistic scenario where config plan uses generic "V".

    Scenario:
    - Plan: ["L_navigate", "L_reproduce", "P", "V"] (generic V in plan)
    - Agent performs V_newly_generated_test, V_regression_test (specific variants)
    - All should count towards "V" threshold
    """
    print("\n" + "="*80)
    print("TEST: Config Plan with Generic V")
    print("="*80)

    rule = PlanComplianceRule(
        rule_id="test_compliance",
        message="Violation: {violation}. Expected: {expected}. Skipped: {skipped}",
        intended_plan=["L_navigate", "L_reproduce", "P", "V"],
        per_violation_type_threshold=2,
        block_execution=False
    )

    # Navigate
    phase = Phase("L_navigate")
    rule.check(current_phase=phase, previous_phase=None, step_index=0, command="ls", role_history=[])

    print("\nPhase 1: Skip L_reproduce and P, go to V_newly_generated_test")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V_newly_generated_test")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=1, command="test", role_history=["L_navigate"])
    assert match is not None, "Should trigger for skipping L_reproduce and P"
    reported = match.metadata.get("skipped_phases", [])
    print(f"  ✓ Skipped: {reported}")
    assert "L_reproduce" in reported and "P" in reported

    print("\nPhase 2: Skip L_reproduce and P again, go to V_regression_test")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V_regression_test")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=2, command="test", role_history=["L_navigate"])
    assert match is not None, "Should trigger (2nd time)"
    print(f"  ✓ Triggered. Counts: {rule.violation_count_per_phase}")

    print("\nPhase 3: Try skipping again (3rd time - should NOT trigger)")
    rule.plan_index = 1
    rule.seen_phases = {"L_navigate": 0}
    phase = Phase("V_newly_generated_test")
    match = rule.check(current_phase=phase, previous_phase=Phase("L_navigate"), step_index=3, command="test", role_history=["L_navigate"])
    assert match is None, "Should NOT trigger (both L_reproduce and P exhausted)"
    print(f"  ✓ Not triggered. Counts: {rule.violation_count_per_phase}")

    print("\n" + "="*80)
    print("TEST PASSED: Config plan with generic V works!")
    print("="*80)


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*80)
    print("RUNNING ALL PREFIX THRESHOLD MATCHING TESTS")
    print("="*80)

    try:
        test_prefix_threshold_forward()
        test_prefix_threshold_reverse()
        test_multiple_variants_share_threshold()
        test_config_plan_uses_generic_v()

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
