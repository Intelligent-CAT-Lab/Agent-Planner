# Plan Monitor Flow Review: Violation Count Persistence Through Rollback

## Overview
This document reviews the complete flow of plan monitor integration with mini-swe-agent, focusing on how violation counts persist through the rollback mechanism in `check_step_pre_emptively`.

---

## 1. Integration Point: mini-swe-agent/agents/default.py

### Initialization (Lines 94-95)
```python
if self.config.enable_monitor and MONITOR_AVAILABLE:
    self.monitor = StatefulPhaseMonitor(enable_rules=True)
```

### Step Execution (Lines 133-201)
```python
def step(self) -> dict:
    """Query the LM, check rules pre-emptively, execute the action if safe."""
    response = self.query()  # Get LLM response

    # Pre-emptively check plan monitor BEFORE executing action
    if self.monitor:
        action = self.parse_action(response)
        event = ActionEvent(step_index=self.step_index, command=action["action"])

        # CRITICAL: Call check_step_pre_emptively (line 145)
        monitor_result = self.monitor.check_step_pre_emptively(event, thought=response.get("content", ""))

        if monitor_result:
            messages = monitor_result.get_all_messages()
            if messages:
                monitor_blocked = monitor_result.should_block_and_refine()

                if monitor_blocked:
                    # IMPORTANT: Action is blocked, never executed
                    self.messages.pop()  # Remove assistant message
                    self.add_message("user", monitor_message)
                    return {"output": "", "return_code": -1}
```

**Key Points:**
- Monitor is called BEFORE action execution
- If blocking rule fires, action is never executed
- Monitor must handle state rollback internally

---

## 2. Monitor: check_step_pre_emptively Flow

### Phase 1: Backup State (Lines 113-133)
```python
# Backup ALL state before tentative evaluation
graph_backup = copy.deepcopy(self.graph_builder.G)
role_history_len = len(self.role_history)
current_phase_backup = self.current_phase
rules_backup = copy.deepcopy(self.rule_engine.rules)  # Includes all rule state
```

**Backed up state:**
- Graph structure
- Role history length
- Current/previous phase
- **All rules with their internal state** (including violation counts)

### Phase 2: Tentative Evaluation (Lines 135-200)
```python
# Temporarily update graph, role_history, and phase
build_online_graph_from_trajectory(...)
self.role_history.append(role)
self.current_phase = new_phase

# Check rules - this MODIFIES rule internal state
rule_matches = self.rule_engine.evaluate(...)  # Calls PlanComplianceRule.check()
```

**State changes during tentative evaluation:**
- Graph is built
- Role history is appended
- Phases are updated
- **Rules increment their counts** (violation_count_per_phase, violation_count_per_combination)

### Phase 3a: If Blocking - Rollback with Violation Count Preservation (Lines 205-272)

#### Step 1: Rollback monitor state (Lines 206-230)
```python
# Rollback basic state
del self.role_history[role_history_len:]
self.step_counter = step_counter_backup
self.current_phase = current_phase_backup
self.created_tests = created_tests_backup
```

#### Step 2: Preserve violation counts BEFORE rollback (Lines 244-252)
```python
# CRITICAL: Save incremented counts from CURRENT rule
plan_rule_current = self.rule_engine.rules.get("plan_compliance")
if plan_rule_current and hasattr(plan_rule_current, 'violation_count_per_phase'):
    saved_violation_count_per_phase = plan_rule_current.violation_count_per_phase.copy()
    saved_violation_count_per_combination = plan_rule_current.violation_count_per_combination.copy()
```

**Why this works:**
- At this point, `plan_rule_current` points to the rule that just incremented its counts
- We save the NEW counts (after increment)

#### Step 3: Rollback all rules (Lines 254-256)
```python
# Replace entire rules dict with backed-up version
if rules_backup is not None:
    self.rule_engine.rules = rules_backup
```

**What happens:**
- `self.rule_engine.rules` now points to the backed-up dict
- All rule state is reset to pre-check state (old counts)
- `plan_rule_current` still references the old object (now orphaned)

#### Step 4: Restore incremented counts (Lines 258-264)
```python
# Get fresh reference to the restored rule
plan_rule_restored = self.rule_engine.rules.get("plan_compliance")
if plan_rule_restored:
    # Update with the INCREMENTED counts we saved
    plan_rule_restored.violation_count_per_phase = saved_violation_count_per_phase
    plan_rule_restored.violation_count_per_combination = saved_violation_count_per_combination
```

**Result:**
- Restored rule now has the incremented violation counts
- Next time the same violation happens, counts continue from current value

### Phase 3b: If Not Blocking (Lines 273-279)
```python
# State already updated, just return result
if all_rule_matches:
    return MonitorResult(
        current_phase=self.current_phase,
        rule_matches=all_rule_matches
    )
```

**No rollback needed:**
- Graph changes are kept
- Role history is kept
- Violation counts are kept
- Agent will execute the action

---

## 3. PlanComplianceRule: Violation Count Logic

### Ending Flag Check (Lines 642-688)

#### Step 1: Detect ending flag
```python
if self.ending_flags and command:
    for ending_flag in self.ending_flags:
        if ending_flag in command:
            self.has_ended = True
```

#### Step 2: Determine skipped phases
```python
if self.plan_index < len(self.intended_plan):
    skipped_phases = self.intended_plan[self.plan_index:]
```

#### Step 3: Filter phases that reached threshold (Lines 650-653)
```python
reportable_phases = [
    phase for phase in skipped_phases
    if not self._has_reached_threshold(phase)
]
```

**_has_reached_threshold logic (Lines 598-621):**
```python
def _has_reached_threshold(self, phase: str) -> bool:
    # Check exact match
    if self.violation_count_per_phase.get(phase, 0) >= self.per_violation_type_threshold:
        return True

    # Check if phase is prefix of tracked phase (V vs V_regression_test)
    for tracked_phase, count in self.violation_count_per_phase.items():
        if tracked_phase.startswith(phase + '_') and count >= self.per_violation_type_threshold:
            return True

    # Check if tracked phase is prefix of current (V_regression_test vs V)
    for tracked_phase, count in self.violation_count_per_phase.items():
        if phase.startswith(tracked_phase + '_') and count >= self.per_violation_type_threshold:
            return True

    return False
```

#### Step 4: Check combination threshold (Lines 659-662)
```python
combination_key = tuple(sorted(reportable_phases))
if self.violation_count_per_combination.get(combination_key, 0) >= self.per_violation_type_threshold:
    return None  # Threshold reached, no violation
```

#### Step 5: Increment counts (Lines 664-670)
```python
# Update combination count
self.violation_count_per_combination[combination_key] = \
    self.violation_count_per_combination.get(combination_key, 0) + 1

# Update individual phase counts
for phase in reportable_phases:
    self.violation_count_per_phase[phase] = self.violation_count_per_phase.get(phase, 0) + 1
```

#### Step 6: Return violation
```python
return RuleMatch(
    rule_id=self.rule_id,
    message=self.message.format(...),
    block_execution=self.block_execution,
    metadata={...}
)
```

### Phase Skip Check (Lines 781-826)
**Similar logic:**
1. Detect skipped phases
2. Filter by threshold
3. Check combination threshold
4. Increment counts
5. Return violation

---

## 4. Complete Flow Example: Repeated Submit Violation

### Attempt 1: First Submit Without Completing Plan

1. **mini-swe-agent calls monitor:**
   ```python
   event = ActionEvent(step_index=9, command="submit")
   monitor_result = self.monitor.check_step_pre_emptively(event, thought="...")
   ```

2. **Monitor backs up state:**
   ```python
   rules_backup = copy.deepcopy(self.rule_engine.rules)  # violation_count_per_phase = {}
   ```

3. **Rule checks and increments:**
   ```python
   # PlanComplianceRule.check() detects ending flag
   # Skipped: ["L_reproduce", "P", "V"]
   # Reportable: ["L_reproduce", "P", "V"] (none reached threshold yet)
   # Increment: violation_count_per_phase = {"L_reproduce": 1, "P": 1, "V": 1}
   #           violation_count_per_combination = {("L_reproduce", "P", "V"): 1}
   # Return: RuleMatch with block_execution=True
   ```

4. **Monitor detects blocking and saves counts:**
   ```python
   # Current rule has: {"L_reproduce": 1, "P": 1, "V": 1}
   saved_violation_count_per_phase = {"L_reproduce": 1, "P": 1, "V": 1}
   saved_violation_count_per_combination = {("L_reproduce", "P", "V"): 1}
   ```

5. **Monitor rolls back rules:**
   ```python
   self.rule_engine.rules = rules_backup  # Restores rules with counts = {}
   ```

6. **Monitor restores incremented counts:**
   ```python
   plan_rule_restored = self.rule_engine.rules.get("plan_compliance")
   plan_rule_restored.violation_count_per_phase = {"L_reproduce": 1, "P": 1, "V": 1}
   plan_rule_restored.violation_count_per_combination = {("L_reproduce", "P", "V"): 1}
   ```

7. **mini-swe-agent handles blocking:**
   ```python
   if monitor_blocked:
       self.messages.pop()  # Remove assistant message
       self.add_message("user", monitor_message)  # Add violation message
       return {"output": "", "return_code": -1}  # Action not executed
   ```

**Result:** Violation triggered, counts = 1, action blocked

---

### Attempt 2: Second Submit Without Completing Plan

1. **mini-swe-agent calls monitor again:**
   ```python
   event = ActionEvent(step_index=10, command="submit")
   monitor_result = self.monitor.check_step_pre_emptively(event, thought="...")
   ```

2. **Monitor backs up state:**
   ```python
   # IMPORTANT: Backup includes CURRENT counts
   rules_backup = copy.deepcopy(self.rule_engine.rules)
   # violation_count_per_phase = {"L_reproduce": 1, "P": 1, "V": 1}
   ```

3. **Rule checks and increments:**
   ```python
   # Skipped: ["L_reproduce", "P", "V"]
   # Filter: All reportable (none reached threshold of 2 yet)
   # Combination: {("L_reproduce", "P", "V"): 1} < 2, so trigger
   # Increment: violation_count_per_phase = {"L_reproduce": 2, "P": 2, "V": 2}
   #           violation_count_per_combination = {("L_reproduce", "P", "V"): 2}
   # Return: RuleMatch with block_execution=True
   ```

4. **Monitor saves NEW counts:**
   ```python
   saved_violation_count_per_phase = {"L_reproduce": 2, "P": 2, "V": 2}
   saved_violation_count_per_combination = {("L_reproduce", "P", "V"): 2}
   ```

5. **Monitor rolls back and restores:**
   ```python
   self.rule_engine.rules = rules_backup  # Restores with counts = 1
   plan_rule_restored.violation_count_per_phase = {"L_reproduce": 2, "P": 2, "V": 2}
   plan_rule_restored.violation_count_per_combination = {("L_reproduce", "P", "V"): 2}
   ```

**Result:** Violation triggered, counts = 2, action blocked

---

### Attempt 3: Third Submit Without Completing Plan

1. **mini-swe-agent calls monitor:**
   ```python
   event = ActionEvent(step_index=11, command="submit")
   monitor_result = self.monitor.check_step_pre_emptively(event, thought="...")
   ```

2. **Monitor backs up state:**
   ```python
   # Backup includes counts = 2
   rules_backup = copy.deepcopy(self.rule_engine.rules)
   ```

3. **Rule checks threshold:**
   ```python
   # Skipped: ["L_reproduce", "P", "V"]
   # Filter: _has_reached_threshold returns True for all (counts = 2, threshold = 2)
   # Reportable: [] (empty after filtering)
   # Return: None (no violation)
   ```

4. **Monitor returns None:**
   ```python
   # No blocking, no rule matches
   return None
   ```

5. **mini-swe-agent proceeds:**
   ```python
   # No monitor result, execute action normally
   return self.get_observation(response)
   ```

**Result:** No violation triggered, action proceeds

---

## 5. Critical Design Points

### ✅ Violation Counts Persist Across Rollback
- **Why:** Counts are explicitly saved before rollback and restored after
- **Implementation:** Lines 244-264 in monitor.py
- **Result:** Repeated blocked attempts eventually stop triggering

### ✅ Other Rule State Is Properly Rolled Back
- PhaseTransitionRule trigger_count: rolled back ✓
- DwellTimeRule dwell_count: rolled back ✓
- OscillationDetector pattern_counts: rolled back ✓
- **Why:** These track successful executions, not blocked attempts

### ✅ Threshold Checking Works Correctly
- Individual phase threshold: checked via `_has_reached_threshold()`
- Combination threshold: checked via `violation_count_per_combination`
- Prefix matching: handled in `_has_reached_threshold()`
- **Result:** Both individual and combination thresholds are enforced

### ✅ Fresh References Required in Tests
- **Issue:** After rollback, `self.rule_engine.rules` is replaced
- **Impact:** External references become stale
- **Solution:** Get fresh reference after each check
- **Example:**
  ```python
  # BAD: Holds stale reference
  plan_rule = monitor.rule_engine.rules.get("plan_compliance")
  for attempt in range(5):
      monitor.check_step_pre_emptively(...)
      print(plan_rule.violation_count_per_phase)  # Always shows old counts!

  # GOOD: Gets fresh reference each time
  for attempt in range(5):
      monitor.check_step_pre_emptively(...)
      plan_rule = monitor.rule_engine.rules.get("plan_compliance")
      print(plan_rule.violation_count_per_phase)  # Shows current counts
  ```

---

## 6. Test Coverage

### ✅ test_rollback_validation.py
- Tests violation counts persist through rollback
- Tests threshold enforcement across multiple blocked attempts
- Verifies counts increment: 0 → 1 → 2
- Verifies violations stop after threshold

### ✅ test_integration_bug.py
- Tests full StatefulPhaseMonitor integration
- Simulates exact mini-swe-agent usage pattern
- Verifies violations stop after threshold (2 violations, then silent)

### ✅ test_repeated_submit_bug.py
- Tests exact scenario from user bug report
- Agent submits 5 times without completing V
- Verifies only 2 violations trigger

### ✅ test_per_violation_type_threshold.py
- Comprehensive test of all threshold scenarios
- Tests phase skip, premature ending, mixed types
- Tests compound skip with partial exhaustion
- Tests combination tracking

### ✅ test_prefix_threshold_matching.py
- Tests asymmetric prefix matching
- Tests V vs V_regression_test scenarios
- Tests config plan with generic V

---

## 7. Verification Summary

### Monitor Integration ✓
- mini-swe-agent correctly calls `check_step_pre_emptively` before action execution
- Blocking rules prevent action execution
- Non-blocking rules allow action but add guidance message

### State Management ✓
- All relevant state is backed up before tentative evaluation
- Rollback correctly restores graph, role_history, phases
- Violation counts are explicitly preserved across rollback

### Threshold Enforcement ✓
- Individual phase thresholds enforced via `_has_reached_threshold()`
- Combination thresholds enforced via `violation_count_per_combination`
- Prefix matching works correctly for V vs V_* variants
- Filtered combinations get their own thresholds

### Count Persistence ✓
- Counts increment correctly: 0 → 1 → 2
- Counts persist through rollback mechanism
- Counts stop incrementing after threshold
- Violations stop triggering after threshold

---

## 8. Conclusion

**The implementation is correct and working as intended.**

Key aspects verified:
1. ✅ Violation counts increment during tentative evaluation
2. ✅ Counts are preserved through rollback (lines 244-264)
3. ✅ Threshold checking prevents violations after limit reached
4. ✅ Both individual and combination thresholds work correctly
5. ✅ Prefix matching works for V vs V_* variants
6. ✅ All integration tests pass
7. ✅ mini-swe-agent integration is correct

The only gotcha is that external test code must get fresh rule references after each check, since rollback replaces the entire rules dict.
