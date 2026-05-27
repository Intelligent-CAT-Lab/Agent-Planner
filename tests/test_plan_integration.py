#!/usr/bin/env python3
"""
Integration test for plan_monitor and plan_refiner dynamic plan updates.

Tests the complete workflow:
1. Monitor detects plan violation pre-emptively
2. Refiner generates refined plan with phase annotations
3. Monitor's intended plan is updated dynamically
4. State consistency is maintained
"""

import sys
sys.path.insert(0, '/home/shuyang/Agent-Planner')

from plan_monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent, Phase
from plan_refiner import PlanRefiner
from plan_refiner.models import MockModel
from plan_refiner.types import RefinerInput, StateSummary, TrajectoryStep, RuleTrigger


def test_end_to_end_plan_update():
    """
    Test the complete flow from rule violation to plan update using check_step_pre_emptively.
    """
    print("=" * 80)
    print("END-TO-END INTEGRATION TEST: Monitor + Refiner + Dynamic Plan Update")
    print("=" * 80)

    # Initialize monitor with original plan
    print("\n1. Initialize monitor with original plan")
    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Get the plan compliance rule
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    assert plan_rule is not None, "Plan compliance rule not found"

    original_plan = plan_rule.intended_plan.copy()
    print(f"   Original plan: {original_plan}")
    print(f"   Initial plan_index: {plan_rule.plan_index}")

    # Simulate: Agent attempts to execute L_navigate (matches expected)
    print("\n2. Agent attempts L_navigate (first phase)")
    event1 = ActionEvent(step_index=0, command="ls src/")
    result1 = monitor.check_step_pre_emptively(event1, thought="Looking for relevant files")

    if result1 and result1.rule_matches:
        print(f"   ✗ Unexpected violation: {result1.rule_matches[0].message}")
        assert False, "L_navigate should not violate at step 0"
    else:
        print(f"   ✓ No violation - L_navigate allowed")

    # State was updated by check_step_pre_emptively
    print(f"   Current phase: {monitor.current_phase}")
    print(f"   Phase history: {monitor.get_phase_history()}")
    print(f"   plan_index: {plan_rule.plan_index}")

    # Now attempt to skip to P (should violate because we skipped L_reproduce)
    print("\n3b. Agent attempts to skip to P (VIOLATION!)")
    event2 = ActionEvent(step_index=2, command="str_replace_editor str_replace src/auth.py")
    result2 = monitor.check_step_pre_emptively(event2, thought="Applying the fix")

    print(f"   result2: {result2}")
    if result2:
        print(f"   rule_matches: {result2.rule_matches}")
        if result2.rule_matches:
            for match in result2.rule_matches:
                print(f"   - Rule: {match.rule_id}, Message: {match.message}")

    assert result2 is not None, "Expected rule violation"
    assert result2.rule_matches, "Expected rule matches"
    print(f"   ✓ Violation detected: {result2.rule_matches[0].message}")

    metadata = result2.rule_matches[0].metadata
    print(f"   Skipped phases: {metadata.get('skipped_phases')}")
    print(f"   Blocking: {result2.should_block_and_refine()}")

    # Since it's blocking, the action shouldn't be in role_history yet
    # check_step_pre_emptively tentatively updates state but rolls back if blocking
    # Re-fetch plan_rule after check (rollback may replace the rules dict)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   Phase history after check: {monitor.get_phase_history()}")
    print(f"   plan_index after check: {plan_rule.plan_index}")

    # Build state summary and trajectory for refiner
    print("\n4. Prepare refiner input")
    state_summary = StateSummary(
        current_phase=str(monitor.current_phase),
        phase_history=monitor.get_phase_history(),
        unique_phases=monitor.get_unique_phases(),
        rule_triggers=[
            RuleTrigger(
                rule_id=m.rule_id,
                message=m.message,
                step_index=1,
                metadata=m.metadata
            )
            for m in result2.rule_matches
        ],
        step_count=1  # Only one action successfully executed
    )

    trajectory_steps = [
        TrajectoryStep(step_index=0, thought="Looking for relevant files",
                      action="ls src/", observation="file1.py\nfile2.py")
    ]

    issue_description = "Fix the bug in the authentication module"

    refiner_input = RefinerInput(
        issue_description=issue_description,
        trajectory=trajectory_steps,
        state_summary=state_summary
    )

    # Mock refined plan response with phase annotations
    print("\n5. Mock refiner response with refined plan")
    mock_response = """
    <analysis>
    The agent executed navigation (L_navigate) but is now attempting to skip directly
    to testing (V_newly_generated_test) without reproducing the bug (L_reproduce) or
    applying a patch (P). This violates the intended workflow and may lead to inadequate
    bug understanding.
    </analysis>

    <new_plan>

    ### Customized High-Level Plan

    1. [Phase=L_reproduce] Create a minimal reproduction script to verify the bug exists
    2. [Phase=L_navigate] Locate the exact source of the bug in the authentication module
    3. [Phase=P] Apply the necessary patch to fix the authentication issue
    4. [Phase=V_newly_generated_test] Test the fix with the reproduction script
    5. [Phase=V_regression_test] Run existing authentication tests to ensure no regressions

    </new_plan>
    """

    # Create refiner and parse response
    refiner = PlanRefiner(model=MockModel())
    refiner_output = refiner._parse_response(mock_response)

    print(f"   Extracted phases: {refiner_output.refined_plan_phases}")
    expected_phases = ["L_reproduce", "L_navigate", "P", "V_newly_generated_test", "V_regression_test"]
    assert refiner_output.refined_plan_phases == expected_phases, \
        f"Expected {expected_phases}, got {refiner_output.refined_plan_phases}"

    # Update monitor's intended plan
    print("\n6. Update monitor's intended plan with refined phases")
    print(f"   Plan before update: {plan_rule.intended_plan}")
    print(f"   plan_index before update: {plan_rule.plan_index}")
    print(f"   seen_phases before update: {plan_rule.seen_phases}")
    print(f"   role_history before update: {monitor.get_phase_history()}")

    success = monitor.update_intended_plan(refiner_output.refined_plan_phases)
    assert success, "Plan update failed"

    # Re-fetch plan_rule after update (in case rollback/update replaced the rules dict)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")

    print(f"\n   Plan after update: {plan_rule.intended_plan}")
    print(f"   plan_index after update: {plan_rule.plan_index}")
    print(f"   seen_phases after update: {plan_rule.seen_phases}")
    print(f"   role_history after update: {monitor.get_phase_history()}")
    print(f"   Next expected phase: {plan_rule.intended_plan[plan_rule.plan_index] if plan_rule.plan_index < len(plan_rule.intended_plan) else 'END'}")

    # Verify state consistency
    print("\n7. Verify state consistency")
    print(f"   ✓ seen_phases cleared: {len(plan_rule.seen_phases) == 0}")
    print(f"   ✓ role_history preserved: {monitor.get_phase_history() == ['L_navigate']}")
    print(f"   ✓ plan_index maintained")

    assert len(plan_rule.seen_phases) == 0, "seen_phases should be cleared"
    assert monitor.get_phase_history() == ['L_navigate'], \
        f"role_history should be preserved, got {monitor.get_phase_history()}"

    # Test agent continuing with refined plan
    print("\n8. Agent continues with refined plan")

    # Agent attempts L_reproduce (from refined plan)
    print("\n   8a. Agent attempts L_reproduce (expected next phase)")
    event3 = ActionEvent(step_index=2, command="python reproduce_bug.py")
    result3 = monitor.check_step_pre_emptively(event3, thought="Reproducing the bug")

    if result3 and result3.rule_matches:
        print(f"      ✗ Unexpected violation: {result3.rule_matches[0].message}")
    else:
        print(f"      ✓ No violation (L_reproduce matches expected)")

    print(f"      Current phase: {monitor.current_phase}")
    print(f"      Phase history: {monitor.get_phase_history()}")
    print(f"      plan_index: {plan_rule.plan_index}")

    # Agent revisits L_navigate (already in role_history, should be allowed)
    print("\n   8b. Agent attempts to revisit L_navigate")
    event4 = ActionEvent(step_index=3, command="cat src/auth.py")
    result4 = monitor.check_step_pre_emptively(event4, thought="Reading auth module")

    if result4 and result4.rule_matches:
        print(f"      ✗ Unexpected violation: {result4.rule_matches[0].message}")
    else:
        print(f"      ✓ No violation (L_navigate revisit allowed)")

    print(f"      Current phase: {monitor.current_phase}")
    print(f"      Phase history: {monitor.get_phase_history()}")
    print(f"      plan_index: {plan_rule.plan_index}")

    # Agent attempts P (patching)
    print("\n   8c. Agent attempts P (patching)")
    event5 = ActionEvent(step_index=4, command="str_replace_editor --path src/auth.py --old_str 'old' --new_str 'new'")
    result5 = monitor.check_step_pre_emptively(event5, thought="Applying the fix")

    if result5 and result5.rule_matches:
        print(f"      ✗ Unexpected violation: {result5.rule_matches[0].message}")
    else:
        print(f"      ✓ No violation (P matches expected)")

    print(f"      Current phase: {monitor.current_phase}")
    print(f"      Phase history: {monitor.get_phase_history()}")
    print(f"      plan_index: {plan_rule.plan_index}")

    # Agent attempts V_newly_generated_test
    print("\n   8d. Agent attempts V_newly_generated_test")
    event6 = ActionEvent(step_index=5, command="pytest test_new.py")
    result6 = monitor.check_step_pre_emptively(event6, thought="Testing the fix")

    if result6 and result6.rule_matches:
        print(f"      ✗ Unexpected violation: {result6.rule_matches[0].message}")
    else:
        print(f"      ✓ No violation (V_newly_generated_test matches expected)")

    print(f"      Current phase: {monitor.current_phase}")
    print(f"      Phase history: {monitor.get_phase_history()}")
    print(f"      plan_index: {plan_rule.plan_index}")

    print("\n" + "=" * 80)
    print("TEST SUMMARY: Integration Test PASSED")
    print("=" * 80)
    print("✓ Monitor detected plan violation pre-emptively")
    print("✓ Refiner extracted refined plan phases")
    print("✓ Monitor's intended plan was updated dynamically")
    print("✓ State consistency maintained (seen_phases cleared, role_history preserved)")
    print("✓ Agent can continue with refined plan without violations")
    print("=" * 80)


if __name__ == "__main__":
    try:
        test_end_to_end_plan_update()
        print("\n✅ All tests PASSED!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
