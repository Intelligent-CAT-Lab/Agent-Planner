# Plan Monitor Bug Fix: Missing V_regression_test Detection

## Root Cause

After a dynamic plan update, when phases are revisited (already in `role_history`), the revisit logic returns early without checking if the revisited phase satisfies the currently expected phase. This, combined with the auto-advance logic for already-satisfied phases, can cause `plan_index` to advance incorrectly, potentially reaching or exceeding the plan length prematurely.

When the agent then submits with an ending flag, the check at line 680-682 returns early because `plan_index >= len(intended_plan)`, preventing the premature ending violation from being detected.

## The Problem

1. **Plan after update**: `["L_navigate", "L_reproduce", "L_navigate", "L_navigate", "P", "V_newly_generated_test", "V_regression_test"]`
2. **plan_index after update**: 1
3. **Agent revisits L_navigate** (already in `role_history`):
   - Revisit logic adds to `seen_phases` and returns early
   - `plan_index` stays at 1
4. **Agent executes L_reproduce**:
   - Matches expected at index 1
   - `plan_index` advances to 2
5. **Agent executes P**:
   - Auto-advance finds L_navigate in `seen_phases` matches expected at index 2
   - `plan_index` advances to 3
   - Expected now L_navigate at index 3
   - Auto-advance finds L_navigate AGAIN matches expected at index 3
   - `plan_index` advances to 4
   - (This happens in a loop within the check)
6. **Eventually plan_index reaches 7** (end of plan)
7. **Agent submits**:
   - Check at line 680: `plan_index (7) >= len(plan) (7)`
   - Returns None without checking ending flag!

## The Fix

The auto-advance logic needs to be modified to handle multiple consecutive duplicate phases in a single check. Currently, it only advances once per check, but when there are multiple duplicate expected phases, they should all be skipped in one go.

Alternative fix: The revisit logic should still check if the revisited phase advances the plan, even though it doesn't trigger a violation.

### Recommended Fix: Update the revisit logic

```python
# FIRST: Check if this is a revisit to a successfully executed phase
if role_history and current_category in role_history:
    # Phase was successfully executed before - allow revisit without violation
    # Mark as seen if not already (e.g., after seen_phases was cleared due to plan update)
    if current_category not in self.seen_phases:
        self.seen_phases[current_category] = step_index or 0

    # IMPORTANT: Still check if this revisit satisfies the expected phase
    # This ensures plan_index advances correctly even for revisits
    if self.plan_index < len(self.intended_plan):
        expected_phase = self.intended_plan[self.plan_index]
        # Check if the revisited phase matches or satisfies the expected phase
        if current_category == expected_phase or current_category.startswith(expected_phase + '_'):
            # Advance plan_index since this revisit satisfies the expected phase
            self.plan_index += 1

    return None  # No violation for revisits
```

This ensures that when a phase is revisited, if it happens to match the currently expected phase, the plan_index still advances correctly.

### Alternative Fix: Improve auto-advance to handle multiple duplicates

```python
# Check if we've already seen phases that match multiple consecutive expected phases
while self.plan_index < len(self.intended_plan):
    expected_phase = self.intended_plan[self.plan_index]

    # Check if this expected phase is already in seen_phases
    phase_already_seen = False
    for seen_phase in self.seen_phases:
        if seen_phase == expected_phase or seen_phase.startswith(expected_phase + '_'):
            phase_already_seen = True
            break

    if phase_already_seen:
        # This expected phase is already satisfied, advance
        self.plan_index += 1
    else:
        # Found an unsatisfied expected phase, stop advancing
        break

expected_phase = self.intended_plan[self.plan_index] if self.plan_index < len(self.intended_plan) else None
```

This modifies the auto-advance logic to loop until it finds an expected phase that hasn't been satisfied yet.

## Testing

Both fixes should be tested with the integration test to ensure:
1. Revisited phases advance plan correctly
2. Ending flag detection works after plan updates
3. Duplicate phases in refined plans are handled correctly
