#!/usr/bin/env python3
"""
Test the specific bug fix: ending flag detection after plan update with revisits.

This tests the exact scenario from astropy__astropy-13033 where:
1. Agent executes phases before refiner
2. Refiner updates plan
3. Agent revisits some phases
4. Agent submits without completing all phases
5. Monitor should detect the premature ending (V_regression_test skipped)
"""

import sys
sys.path.insert(0, '/home/shuyang/Agent-Planner')

from plan_monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent

print("=" * 80)
print("BUG FIX TEST: Ending flag detection after plan update with revisits")
print("=" * 80)

# Initialize monitor
monitor = StatefulPhaseMonitor(enable_rules=True)
plan_rule = monitor.rule_engine.rules.get("plan_compliance")

print(f"\n1. Initial plan: {plan_rule.intended_plan}")

# Simulate phases before refiner (steps 0-4)
print(f"\n2. Execute phases before refiner:")
for i, (cmd, thought, phase_name) in enumerate([
    ("ls astropy/", "Finding files", "L_navigate"),
    ("cat file.py", "Reading code", "L_navigate"),
    ("cat file.py", "More reading", "L_navigate"),
    ("cat file.py", "Even more reading", "L_navigate"),
    ("cat file.py", "Still reading", "L_navigate"),
]):
    event = ActionEvent(step_index=i, command=cmd)
    result = monitor.check_step_pre_emptively(event, thought=thought)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    blocked = result and result.should_block_and_refine()
    print(f"   Step {i} ({phase_name}): blocked={blocked}, plan_index={plan_rule.plan_index}")

print(f"\n3. State before refiner:")
print(f"   plan_index: {plan_rule.plan_index}")
print(f"   role_history: {monitor.get_phase_history()}")

# Refiner updates plan
refined_phases = ['L_reproduce', 'L_navigate', 'P', 'V_newly_generated_test', 'V_regression_test']
print(f"\n4. Refiner suggests (with adjacent duplicates merged): {refined_phases}")
success = monitor.update_intended_plan(refined_phases)

plan_rule = monitor.rule_engine.rules.get("plan_compliance")
print(f"\n5. State after update:")
print(f"   intended_plan: {plan_rule.intended_plan}")
print(f"   plan_index: {plan_rule.plan_index}")
print(f"   Expected next: {plan_rule.intended_plan[plan_rule.plan_index]}")

# Simulate phases after refiner (like real trajectory)
print(f"\n6. Execute phases after refiner:")
after_refiner_actions = [
    ("nl astropy/file.py", "Inspecting code", "L_navigate"),
    ("grep test astropy/tests/", "Finding tests", "L_reproduce"),
    ("sed -i 's/old/new/' file.py", "Patching", "P"),
    ("sed -i 's/old/new/' file.py", "More patching", "P"),
    ("cat file.py", "Verifying patch", "L_navigate"),
    ("cat > test.py", "Creating test", "V_newly_generated_test"),
    ("python test.py", "Running test", "V_newly_generated_test"),
]

for i, (cmd, thought, phase_name) in enumerate(after_refiner_actions, start=5):
    event = ActionEvent(step_index=i, command=cmd)
    result = monitor.check_step_pre_emptively(event, thought=thought)
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    blocked = result and result.should_block_and_refine()
    print(f"   Step {i} ({phase_name}): blocked={blocked}, plan_index={plan_rule.plan_index}")

# Check state before submission
plan_rule = monitor.rule_engine.rules.get("plan_compliance")
print(f"\n7. State before submission:")
print(f"   plan_index: {plan_rule.plan_index}")
print(f"   len(intended_plan): {len(plan_rule.intended_plan)}")
print(f"   Remaining phases: {plan_rule.intended_plan[plan_rule.plan_index:]}")
print(f"   role_history: {monitor.get_phase_history()}")

# Critical test: Agent submits without V_regression_test
print(f"\n8. Agent submits WITHOUT V_regression_test:")
event_submit = ActionEvent(step_index=20, command="echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git diff")
result_submit = monitor.check_step_pre_emptively(event_submit, thought="Submitting")

print(f"\n9. RESULT:")
if result_submit and result_submit.rule_matches:
    print(f"   ✅ VIOLATION DETECTED (Bug is fixed!)")
    for match in result_submit.rule_matches:
        print(f"   - Rule: {match.rule_id}")
        print(f"   - Type: {match.metadata.get('type')}")
        print(f"   - Message: {match.message[:150]}...")
        if 'skipped_phases' in match.metadata:
            print(f"   - Skipped phases: {match.metadata['skipped_phases']}")

    # Verify V_regression_test is in skipped phases
    skipped = match.metadata.get('skipped_phases', [])
    if 'V_regression_test' in skipped:
        print(f"\n   ✅ V_regression_test correctly detected as skipped!")
    else:
        print(f"\n   ❌ V_regression_test NOT in skipped phases: {skipped}")
        sys.exit(1)
else:
    print(f"   ❌ BUG NOT FIXED: No violation detected!")
    plan_rule = monitor.rule_engine.rules.get("plan_compliance")
    print(f"   - plan_index: {plan_rule.plan_index}")
    print(f"   - len(intended_plan): {len(plan_rule.intended_plan)}")
    print(f"   - has_ended: {plan_rule.has_ended}")
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ BUG FIX VERIFIED: Ending flag detection works correctly!")
print("=" * 80)
