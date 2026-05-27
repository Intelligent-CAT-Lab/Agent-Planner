# Bug Fix Summary: Plan Monitor Ending Flag Detection

## Problem

After a dynamic plan update, the plan monitor failed to detect when the agent submitted without completing remaining phases (specifically V_regression_test was skipped in astropy__astropy-13033 without triggering a violation).

## Root Cause

Two issues caused `plan_index` to incorrectly reach the end of the plan:

### Issue 1: Revisit Logic Didn't Advance Plan
**Location**: `plan_monitor/rules.py` lines 665-670

When a phase was revisited (already in `role_history`), the logic would:
1. Add the phase to `seen_phases`
2. Return early without checking if it satisfies the expected phase
3. **Not advance `plan_index`**

This meant that even if the revisit satisfied the currently expected phase, `plan_index` didn't advance.

### Issue 2: Auto-Advance Only Advanced Once
**Location**: `plan_monitor/rules.py` lines 686-702

The auto-advance logic that skips satisfied phases would only advance `plan_index` ONCE per check, even if multiple consecutive expected phases were already satisfied.

Combined effect:
1. Revisits added phases to `seen_phases` without advancing `plan_index`
2. Subsequent checks would auto-advance once, but not enough to skip all satisfied phases
3. Eventually this could cause `plan_index` to reach the end prematurely
4. When ending flag was detected, the check at line 680 (`plan_index >= len(intended_plan)`) would return early without detecting premature ending

### Issue 3: Adjacent Duplicates in Refined Plans
**Location**: `plan_refiner/refiner.py` lines 332-375

The refiner could suggest plans like `['L_navigate', 'L_navigate', 'P']` where adjacent phases are duplicated. These represent the same category of work and should be merged to avoid confusion.

## Solution

### Fix 1: Revisit Logic Advances Plan
**File**: `plan_monitor/rules.py` lines 665-679

```python
if role_history and current_category in role_history:
    # Phase was successfully executed before - allow revisit without violation
    if current_category not in self.seen_phases:
        self.seen_phases[current_category] = step_index or 0

    # IMPORTANT: Even though this is a revisit (no violation), we still need to
    # advance plan_index if this revisit satisfies the currently expected phase
    if self.plan_index < len(self.intended_plan):
        expected_phase = self.intended_plan[self.plan_index]
        if current_category == expected_phase or current_category.startswith(expected_phase + '_'):
            # This revisit satisfies the expected phase - advance plan_index
            self.plan_index += 1

    return None  # No violation for revisits
```

**Key change**: Revisits now check if they satisfy the expected phase and advance `plan_index` accordingly, while still returning no violation.

### Fix 2: Auto-Advance Loops Until Unsatisfied Phase
**File**: `plan_monitor/rules.py` lines 690-709

```python
# Auto-advance: Skip past all consecutive expected phases that are already satisfied
while self.plan_index < len(self.intended_plan):
    expected_phase = self.intended_plan[self.plan_index]

    # Check if any seen phase satisfies this expected phase
    phase_satisfied = False
    for seen_phase in self.seen_phases:
        if seen_phase == expected_phase or seen_phase.startswith(expected_phase + '_'):
            phase_satisfied = True
            break

    if phase_satisfied:
        # This expected phase is already satisfied - advance to next
        self.plan_index += 1
    else:
        # Found an unsatisfied expected phase - stop auto-advancing
        break

# Check again if we've completed the plan after auto-advance
if self.plan_index >= len(self.intended_plan):
    return None

expected_phase = self.intended_plan[self.plan_index]
```

**Key change**: Auto-advance now loops to skip ALL consecutive satisfied phases until it finds one that hasn't been satisfied yet.

### Fix 3: Merge Adjacent Duplicates in Refined Plans
**File**: `plan_refiner/refiner.py` lines 367-376

```python
# Find all phase annotations in order
for match in re.finditer(pattern, new_plan):
    phase = match.group(1).strip()

    # Only include valid phases
    if phase in VALID_PHASES:
        # Merge adjacent duplicates: only add if different from last phase
        if not phases or phases[-1] != phase:
            phases.append(phase)
```

**Key change**: Adjacent duplicate phases are merged. `['L_navigate', 'L_navigate', 'P']` becomes `['L_navigate', 'P']`.

Note: Non-adjacent duplicates are preserved (e.g., `['L_navigate', 'L_reproduce', 'L_navigate']` remains unchanged).

## Verification

### Test 1: Phase Extraction with Merging
**File**: `plan_refiner/test_phase_extraction.py`

All 9 tests pass, including:
- Adjacent duplicates are merged: `['L_navigate', 'L_navigate']` → `['L_navigate']`
- Non-adjacent duplicates are preserved: `['L_navigate', 'L_reproduce', 'L_navigate']` unchanged

### Test 2: Integration Test
**File**: `test_plan_integration.py`

Passes, verifying:
- Plan updates work correctly
- Revisits are allowed without violations
- State consistency is maintained

### Test 3: Bug Fix Verification
**File**: `test_ending_flag_bug_fix.py`

Specifically tests the reported bug scenario:
- ✅ Ending flag detection works after plan updates
- ✅ V_regression_test skip is correctly detected
- ✅ Premature ending violation is triggered

## Design Principles

1. **Follow the refined plan**: Agent must complete all phases in the updated plan from the current index

2. **Allow revisits**: Phases already in `role_history` can be revisited for iterative problem-solving without triggering violations

3. **Advance plan correctly**: Revisits that satisfy expected phases advance the plan, ensuring correct tracking

4. **Auto-advance intelligently**: Skip past ALL consecutive satisfied phases to find the next unsatisfied one

5. **Merge adjacent duplicates**: Simplify refined plans by merging adjacent duplicate phases

## Impact

- **Before fix**: Agent could skip V_regression_test and submit without violation
- **After fix**: Ending flag detection correctly identifies skipped phases and blocks submission

## Files Modified

1. `plan_refiner/refiner.py`: Added adjacent duplicate merging
2. `plan_monitor/rules.py`: Fixed revisit logic and auto-advance logic
3. `plan_refiner/test_phase_extraction.py`: Updated tests for merging behavior
4. `test_ending_flag_bug_fix.py`: New test verifying the bug fix

## Testing

Run all tests to verify:
```bash
# Phase extraction tests
python plan_refiner/test_phase_extraction.py

# Integration test
python test_plan_integration.py

# Bug fix verification
python test_ending_flag_bug_fix.py
```

All tests pass ✅

## Conclusion

The bug is fixed through three coordinated changes:
1. Revisit logic advances plan when satisfying expected phases
2. Auto-advance loops to skip all consecutive satisfied phases
3. Adjacent duplicate phases are merged in refined plans

These changes ensure that `plan_index` tracks the plan correctly and ending flag detection works as expected, preventing agents from skipping required phases like V_regression_test.
