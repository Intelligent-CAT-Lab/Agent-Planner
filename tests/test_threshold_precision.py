"""
Precision test for per-violation-type threshold exactly as mini-swe-agent uses it.

Tests that violations trigger EXACTLY threshold times:
- With threshold=2: trigger on attempt 1 and 2, NOT on 3 and after
- With threshold=1: trigger on attempt 1 only, NOT on 2 and after
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_threshold_2():
    """
    Test threshold=2: Should trigger EXACTLY twice (1st and 2nd), then stop.
    """
    print("\n" + "="*80)
    print("TEST 1: Threshold=2 (default)")
    print("="*80)

    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Step 0: Navigate (establish plan)
    step_index = 0
    event = ActionEvent(step_index=step_index, command="ls")
    result = monitor.check_step_pre_emptively(event, thought="Let me start")
    print(f"\nStep {step_index}: Navigate")
    print(f"  Phase: {monitor.get_current_phase()}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    step_index += 1

    # Attempts to submit without completing plan
    print("\n" + "-"*60)
    print("Attempting to submit 5 times without completing plan:")
    print("-"*60)

    trigger_count = 0
    for attempt in range(1, 6):
        event = ActionEvent(step_index=step_index, command="submit")
        result = monitor.check_step_pre_emptively(event, thought=f"Submitting attempt {attempt}")

        triggered = False
        blocked = False
        if result:
            messages = result.get_all_messages()
            blocked = result.should_block_and_refine()
            if messages:
                triggered = True
                trigger_count += 1

        print(f"\nAttempt {attempt} (step {step_index}):")
        print(f"  Triggered: {triggered}")
        print(f"  Blocked: {blocked}")

        if triggered:
            print(f"  Message: {messages[0][:80]}...")

        # Get violation counts
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")
        if plan_rule:
            print(f"  Counts: {plan_rule.violation_count_per_phase}")

        step_index += 1

    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)
    print(f"Total triggers: {trigger_count}")
    print(f"Expected: 2")

    if trigger_count == 2:
        print("✅ TEST 1 PASSED: Triggered exactly 2 times!")
        return True
    else:
        print(f"❌ TEST 1 FAILED: Expected 2 triggers, got {trigger_count}")
        return False


def test_threshold_1():
    """
    Test threshold=1: Should trigger EXACTLY once (1st only), then stop.
    """
    print("\n\n" + "="*80)
    print("TEST 2: Threshold=1")
    print("="*80)

    # Create monitor with threshold=1 by directly modifying the rule
    monitor = StatefulPhaseMonitor(enable_rules=True)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    if plan_rule:
        plan_rule.per_violation_type_threshold = 1
        print(f"Set threshold to: {plan_rule.per_violation_type_threshold}")

    # Step 0: Navigate (establish plan)
    step_index = 0
    event = ActionEvent(step_index=step_index, command="ls")
    result = monitor.check_step_pre_emptively(event, thought="Let me start")
    print(f"\nStep {step_index}: Navigate")
    print(f"  Phase: {monitor.get_current_phase()}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    step_index += 1

    # Attempts to submit without completing plan
    print("\n" + "-"*60)
    print("Attempting to submit 5 times without completing plan:")
    print("-"*60)

    trigger_count = 0
    for attempt in range(1, 6):
        event = ActionEvent(step_index=step_index, command="submit")
        result = monitor.check_step_pre_emptively(event, thought=f"Submitting attempt {attempt}")

        triggered = False
        blocked = False
        if result:
            messages = result.get_all_messages()
            blocked = result.should_block_and_refine()
            if messages:
                triggered = True
                trigger_count += 1

        print(f"\nAttempt {attempt} (step {step_index}):")
        print(f"  Triggered: {triggered}")
        print(f"  Blocked: {blocked}")

        if triggered:
            print(f"  Message: {messages[0][:80]}...")

        # Get violation counts
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")
        if plan_rule:
            print(f"  Counts: {plan_rule.violation_count_per_phase}")

        step_index += 1

    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)
    print(f"Total triggers: {trigger_count}")
    print(f"Expected: 1")

    if trigger_count == 1:
        print("✅ TEST 2 PASSED: Triggered exactly 1 time!")
        return True
    else:
        print(f"❌ TEST 2 FAILED: Expected 1 trigger, got {trigger_count}")
        return False


def test_threshold_3():
    """
    Test threshold=3: Should trigger EXACTLY three times (1st, 2nd, 3rd), then stop.
    """
    print("\n\n" + "="*80)
    print("TEST 3: Threshold=3")
    print("="*80)

    # Create monitor with threshold=3 by directly modifying the rule
    monitor = StatefulPhaseMonitor(enable_rules=True)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    if plan_rule:
        plan_rule.per_violation_type_threshold = 3
        print(f"Set threshold to: {plan_rule.per_violation_type_threshold}")

    # Step 0: Navigate (establish plan)
    step_index = 0
    event = ActionEvent(step_index=step_index, command="ls")
    result = monitor.check_step_pre_emptively(event, thought="Let me start")
    print(f"\nStep {step_index}: Navigate")
    print(f"  Phase: {monitor.get_current_phase()}")
    print(f"  Blocked: {result.should_block_and_refine() if result else False}")
    step_index += 1

    # Attempts to submit without completing plan
    print("\n" + "-"*60)
    print("Attempting to submit 6 times without completing plan:")
    print("-"*60)

    trigger_count = 0
    for attempt in range(1, 7):
        event = ActionEvent(step_index=step_index, command="submit")
        result = monitor.check_step_pre_emptively(event, thought=f"Submitting attempt {attempt}")

        triggered = False
        blocked = False
        if result:
            messages = result.get_all_messages()
            blocked = result.should_block_and_refine()
            if messages:
                triggered = True
                trigger_count += 1

        print(f"\nAttempt {attempt} (step {step_index}):")
        print(f"  Triggered: {triggered}")
        print(f"  Blocked: {blocked}")

        if triggered:
            print(f"  Message: {messages[0][:80]}...")

        # Get violation counts
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")
        if plan_rule:
            print(f"  Counts: {plan_rule.violation_count_per_phase}")

        step_index += 1

    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)
    print(f"Total triggers: {trigger_count}")
    print(f"Expected: 3")

    if trigger_count == 3:
        print("✅ TEST 3 PASSED: Triggered exactly 3 times!")
        return True
    else:
        print(f"❌ TEST 3 FAILED: Expected 3 triggers, got {trigger_count}")
        return False


if __name__ == "__main__":
    try:
        test1_pass = test_threshold_2()
        test2_pass = test_threshold_1()
        test3_pass = test_threshold_3()

        print("\n\n" + "="*80)
        print("FINAL RESULTS:")
        print("="*80)
        print(f"Test 1 (threshold=2): {'✅ PASS' if test1_pass else '❌ FAIL'}")
        print(f"Test 2 (threshold=1): {'✅ PASS' if test2_pass else '❌ FAIL'}")
        print(f"Test 3 (threshold=3): {'✅ PASS' if test3_pass else '❌ FAIL'}")

        if test1_pass and test2_pass and test3_pass:
            print("\n✅ ALL TESTS PASSED!")
            sys.exit(0)
        else:
            print("\n❌ SOME TESTS FAILED!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
