#!/usr/bin/env python3
"""
Diagnose why plan monitor failed to detect V_regression_test skip.

Simulates the exact sequence of events from the astropy__astropy-13033 run.
"""

import sys
sys.path.insert(0, '/home/shuyang/Agent-Planner')

from plan_monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent

# Initialize monitor
monitor = StatefulPhaseMonitor(enable_rules=True)
plan_rule = monitor.rule_engine.rules.get("plan_compliance")

print("=" * 80)
print("DIAGNOSIS: Why V_regression_test skip wasn't detected")
print("=" * 80)

print(f"\n1. Initial state:")
print(f"   Original plan: {plan_rule.intended_plan}")
print(f"   plan_index: {plan_rule.plan_index}")

# Simulate steps 0-4 (before refiner)
# Based on the trajectory, let's assume some phases were executed
print(f"\n2. Simulating steps 0-4 (before refiner at step 5):")

# Step 0: L_navigate
event0 = ActionEvent(step_index=0, command="ls astropy/timeseries")
result0 = monitor.check_step_pre_emptively(event0, thought="Finding timeseries files")
print(f"   Step 0 (L_navigate): violation={result0 is not None and result0.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

# Step 1: L_reproduce
event1 = ActionEvent(step_index=1, command="python reproduce_bug.py")
result1 = monitor.check_step_pre_emptively(event1, thought="Reproducing")
print(f"   Step 1 (L_reproduce): violation={result1 is not None and result1.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

# Step 2: L_navigate
event2 = ActionEvent(step_index=2, command="cat astropy/timeseries/core.py")
result2 = monitor.check_step_pre_emptively(event2, thought="Reading code")
print(f"   Step 2 (L_navigate): violation={result2 is not None and result2.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

# Step 3: P
event3 = ActionEvent(step_index=3, command="str_replace_editor --command str_replace --path astropy/timeseries/core.py")
result3 = monitor.check_step_pre_emptively(event3, thought="Fixing bug")
print(f"   Step 3 (P): violation={result3 is not None and result3.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

# Step 4: V_newly_generated_test
event4 = ActionEvent(step_index=4, command="cat > test_fix.py")
result4 = monitor.check_step_pre_emptively(event4, thought="Creating test")
print(f"   Step 4 (V_newly_generated_test): violation={result4 is not None and result4.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

print(f"\n3. State before refiner:")
print(f"   plan_index: {plan_rule.plan_index}")
print(f"   seen_phases: {plan_rule.seen_phases}")
print(f"   role_history: {monitor.get_phase_history()}")
print(f"   intended_plan: {plan_rule.intended_plan}")
print(f"   Expected next: {plan_rule.intended_plan[plan_rule.plan_index] if plan_rule.plan_index < len(plan_rule.intended_plan) else 'END'}")

# Now simulate refiner updating the plan
refined_phases = ['L_reproduce', 'L_navigate', 'L_navigate', 'P', 'V_newly_generated_test', 'V_regression_test']
print(f"\n4. Refiner suggests: {refined_phases}")

success = monitor.update_intended_plan(refined_phases)
print(f"   Update successful: {success}")

# Re-fetch rule after update
plan_rule = monitor.rule_engine.rules.get("plan_compliance")

print(f"\n5. State after update:")
print(f"   plan_index: {plan_rule.plan_index}")
print(f"   seen_phases: {plan_rule.seen_phases}")
print(f"   role_history: {monitor.get_phase_history()}")
print(f"   intended_plan: {plan_rule.intended_plan}")
print(f"   Expected next: {plan_rule.intended_plan[plan_rule.plan_index] if plan_rule.plan_index < len(plan_rule.intended_plan) else 'END'}")

# Simulate more steps after refiner
print(f"\n6. Steps after refiner (continuing execution):")

# Based on actual trajectory, after refiner the agent did:
# - More navigation
# - More patching
# - Created test
# - Ran test
# - Submitted

# Let's simulate checking those phases
event_nav = ActionEvent(step_index=6, command="nl astropy/timeseries/core.py")
result_nav = monitor.check_step_pre_emptively(event_nav, thought="Inspecting code")
print(f"   Step 6 (L_navigate): violation={result_nav is not None and result_nav.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

event_p = ActionEvent(step_index=7, command="sed -i 's/old/new/' astropy/timeseries/core.py")
result_p = monitor.check_step_pre_emptively(event_p, thought="Editing")
print(f"   Step 7 (P): violation={result_p is not None and result_p.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

event_test_create = ActionEvent(step_index=8, command="cat > test_timeseries_fix.py")
result_test_create = monitor.check_step_pre_emptively(event_test_create, thought="Creating test")
print(f"   Step 8 (V_newly_generated_test): violation={result_test_create is not None and result_test_create.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

event_test_run = ActionEvent(step_index=9, command="python test_timeseries_fix.py")
result_test_run = monitor.check_step_pre_emptively(event_test_run, thought="Running test")
print(f"   Step 9 (V_newly_generated_test): violation={result_test_run is not None and result_test_run.rule_matches}")
print(f"   plan_index: {plan_rule.plan_index}, role_history: {monitor.get_phase_history()}")

# NOW THE CRITICAL PART: Agent submits without V_regression_test
print(f"\n7. CRITICAL: Agent attempts to submit (skipping V_regression_test):")
print(f"   Current plan_index: {plan_rule.plan_index}")
print(f"   Current intended_plan: {plan_rule.intended_plan}")
print(f"   Remaining phases: {plan_rule.intended_plan[plan_rule.plan_index:]}")

event_submit = ActionEvent(step_index=10, command="echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git diff")
result_submit = monitor.check_step_pre_emptively(event_submit, thought="Submitting")

print(f"\n8. Submission check result:")
print(f"   Violation detected: {result_submit is not None and result_submit.rule_matches}")
if result_submit and result_submit.rule_matches:
    for match in result_submit.rule_matches:
        print(f"   - Rule: {match.rule_id}")
        print(f"   - Message: {match.message}")
        print(f"   - Metadata: {match.metadata}")
else:
    print(f"   ❌ NO VIOLATION DETECTED - This is the BUG!")
    print(f"   plan_index at submission: {plan_rule.plan_index}")
    print(f"   len(intended_plan): {len(plan_rule.intended_plan)}")
    print(f"   Check condition: plan_index ({plan_rule.plan_index}) < len(intended_plan) ({len(plan_rule.intended_plan)})?")
    print(f"   has_ended: {plan_rule.has_ended}")

print("\n" + "=" * 80)
