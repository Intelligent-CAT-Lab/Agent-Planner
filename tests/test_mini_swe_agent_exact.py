"""
Test exact mini-swe-agent integration pattern.

Mimics exactly how mini-swe-agent calls check_step_pre_emptively.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent


def test_exact_mini_swe_agent_pattern():
    """
    Exact pattern from mini-swe-agent/src/minisweagent/agents/default.py
    """
    print("\n" + "="*80)
    print("TEST: Exact mini-swe-agent integration pattern")
    print("="*80)

    # Initialize monitor exactly as mini-swe-agent does
    monitor = StatefulPhaseMonitor(enable_rules=True)

    # Check rate limiting settings
    if monitor.rule_engine:
        print(f"Rate limiting enabled: {monitor.rule_engine.rate_limit_enabled}")
        print(f"Rate limiting min_gap: {monitor.rule_engine.min_gap}")
        print(f"Initial trigger_history: {monitor.rule_engine.trigger_history}")

    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"Plan compliance threshold: {plan_rule.per_violation_type_threshold}")

    step_index = 0

    # Step 0: Navigate
    print(f"\nStep {step_index}: Navigate")
    event = ActionEvent(step_index=step_index, command="ls")
    monitor_result = monitor.check_step_pre_emptively(event, thought="Let me start")
    print(f"  Phase: {monitor.get_current_phase()}")
    print(f"  Trigger history: {monitor.rule_engine.trigger_history}")
    step_index += 1

    # Now submit 5 times exactly as mini-swe-agent would
    print("\n" + "="*60)
    print("Submit attempts (mimicking mini-swe-agent):")
    print("="*60)

    for attempt in range(1, 6):
        print(f"\n--- Attempt {attempt} (step {step_index}) ---")

        # This is exactly how mini-swe-agent calls it
        event = ActionEvent(step_index=step_index, command="submit")

        print(f"Before check:")
        print(f"  Trigger history: {monitor.rule_engine.trigger_history}")
        print(f"  Violation counts: {plan_rule.violation_count_per_phase}")

        monitor_result = monitor.check_step_pre_emptively(event, thought=f"Submitting attempt {attempt}")

        # IMPORTANT: Get fresh reference after check (rule might have been replaced during rollback)
        plan_rule = monitor.rule_engine.rules.get("plan_compliance")

        print(f"After check:")
        print(f"  Trigger history: {monitor.rule_engine.trigger_history}")
        print(f"  Violation counts: {plan_rule.violation_count_per_phase}")

        if monitor_result:
            messages = monitor_result.get_all_messages()
            if messages:
                print(f"  ✓ Triggered: {messages[0][:80]}...")
                print(f"  Blocked: {monitor_result.should_block_and_refine()}")
            else:
                print(f"  No messages")
        else:
            print(f"  No result")

        step_index += 1

    # Final check (get fresh reference)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print("\n" + "="*60)
    print("FINAL STATE:")
    print("="*60)
    print(f"Trigger history: {monitor.rule_engine.trigger_history}")
    print(f"Violation counts: {plan_rule.violation_count_per_phase}")

    # Count how many times it triggered
    # Based on whether messages were shown
    print("\n" + "="*60)
    print("ANALYSIS:")
    print("="*60)

    expected_triggers = 2  # threshold
    actual_count = plan_rule.violation_count_per_phase.get('L_reproduce', 0)

    print(f"Expected triggers: {expected_triggers}")
    print(f"Actual violation count: {actual_count}")

    if actual_count == expected_triggers:
        print("✅ CORRECT: Triggered exactly threshold times")
        return True
    else:
        print(f"❌ WRONG: Expected {expected_triggers}, got {actual_count}")
        return False


if __name__ == "__main__":
    try:
        success = test_exact_mini_swe_agent_pattern()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
