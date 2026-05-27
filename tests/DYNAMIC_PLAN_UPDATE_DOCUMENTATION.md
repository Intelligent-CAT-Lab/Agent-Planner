# Dynamic Plan Update Integration Documentation

## Overview

This document describes the integration between `plan_monitor` and `plan_refiner` for dynamic plan updates during agent execution. The system allows the agent's intended execution plan to be dynamically adjusted based on plan refiner guidance while maintaining state consistency.

## Architecture

### Components

1. **plan_monitor**: Tracks phase execution and detects plan violations
2. **plan_refiner**: Generates refined plans with phase annotations when violations occur
3. **mini-swe-agent**: Orchestrates the monitor-refiner workflow

### Data Flow

```
Agent Action
    ↓
Monitor Pre-Check (check_step_pre_emptively)
    ↓
Rule Violation? → Yes → Refiner Called
    ↓                       ↓
   No                   Extract Phases
    ↓                       ↓
Execute Action         Update Monitor Plan
    ↓                       ↓
Update State           Agent Continues
```

## Implementation Details

### 1. Phase Extraction in plan_refiner

**File**: `plan_refiner/refiner.py`

**New Method**: `_extract_plan_phases()`

```python
def _extract_plan_phases(self, new_plan: str) -> list[str]:
    """
    Extract phase labels from [Phase=X] annotations in the new_plan.

    Returns:
        List of valid phases (e.g., ["L_navigate", "L_reproduce", "P"])
    """
```

**Features**:
- Extracts phases using regex pattern: `r'\[Phase\s*=\s*([^\]]+)\]'`
- Handles whitespace variations: `[Phase=X]`, `[Phase = X]`, etc.
- Filters to only valid phases: L_navigate, L_reproduce, P, V_newly_generated_test, V_regression_test
- Preserves phase order and allows duplicates
- Integrated into `_parse_response()` method

**Output**: `RefinerOutput.refined_plan_phases` field contains extracted phases

### 2. Plan Update in plan_monitor

**File**: `plan_monitor/monitor.py`

**New Method**: `update_intended_plan()`

```python
def update_intended_plan(self, refined_plan_phases: list[str]) -> bool:
    """
    Update the intended plan in the plan compliance rule from the current index.

    Args:
        refined_plan_phases: List of phase labels for the new plan

    Returns:
        True if update was successful, False if rule not available
    """
```

**Features**:
- Accesses the `plan_compliance` rule from the rule engine
- Calls `update_plan()` on the rule with refined phases
- Logs old and new plans for debugging
- Returns success status

**File**: `plan_monitor/rules.py`

**New Method**: `PlanComplianceRule.update_plan()`

```python
def update_plan(self, new_plan: list[str]):
    """
    Dynamically update the intended plan from the current index.

    - Keeps completed portion: intended_plan[:plan_index]
    - Replaces remaining portion with new_plan
    - Clears seen_phases to restart first-appearance tracking
    - Does NOT affect role_history (maintained by monitor)
    """
```

### 3. Integration in mini-swe-agent

**File**: `mini-swe-agent/src/minisweagent/agents/default.py`

**Modified Method**: `_call_refiner()`

```python
# After refiner generates new plan
if refiner_output.refined_plan_phases:
    plan_updated = self.monitor.update_intended_plan(refiner_output.refined_plan_phases)
    if not plan_updated:
        print(f"[REFINER] Warning: Failed to update plan in monitor")
```

**Workflow**:
1. Monitor detects rule violation pre-emptively
2. If blocking rule triggers, state is rolled back
3. Refiner is called to generate refined plan
4. Phases are extracted from refined plan
5. Monitor's intended plan is updated
6. Agent continues with new plan

## State Consistency Guarantees

### What Gets Updated

| Component | Updated? | How? |
|-----------|----------|------|
| `intended_plan` | ✅ Yes | Completed portion + new plan |
| `plan_index` | ✅ Maintained | Not changed during update |
| `seen_phases` | ✅ Cleared | Restart first-appearance tracking |
| `role_history` | ✅ Preserved | Maintained by monitor (not affected) |
| `violation_count` | ✅ Preserved | Violations still count toward threshold |

### Revisit Handling

After plan update, phases that were successfully executed before the update (in `role_history`) are allowed as revisits:

1. **Check order**: role_history check → seen_phases check
2. **Revisit logic**: If phase in `role_history`, allow without violation
3. **State update**: Mark revisited phase in `seen_phases` to advance plan

### Example Scenario

```python
# Original plan
intended_plan = ["L_navigate", "P", "V"]
plan_index = 1  # After completing L_navigate

# Agent skips to V (violation detected)
# Refiner suggests: ["L_reproduce", "L_navigate", "P", "V_newly_generated_test"]

# After update
intended_plan = ["L_navigate", "L_reproduce", "L_navigate", "P", "V_newly_generated_test"]
plan_index = 1  # Still 1 (expecting L_reproduce)
seen_phases = {}  # Cleared
role_history = ["L_navigate"]  # Preserved

# Agent can now:
# - Execute L_reproduce (matches expected at index 1)
# - Revisit L_navigate (in role_history, allowed as revisit)
# - Continue with P, V_newly_generated_test
```

## API Usage

### For Agent Frameworks

```python
from plan_monitor import StatefulPhaseMonitor
from plan_refiner import PlanRefiner
from plan_refiner.types import RefinerInput

# 1. Initialize monitor
monitor = StatefulPhaseMonitor(enable_rules=True)

# 2. Initialize refiner
refiner_model = PlanRefiner.create_model_from_config("config/default.yaml")
refiner = PlanRefiner(refiner_model)

# 3. During execution loop
event = ActionEvent(step_index=step, command=action)
result = monitor.check_step_pre_emptively(event, thought=thought)

if result and result.should_block_and_refine():
    # 4. Call refiner
    refiner_input = RefinerInput(
        issue_description=task,
        trajectory=trajectory_steps,
        state_summary=state_summary
    )
    refiner_output = refiner.refine_plan(refiner_input)

    # 5. Update plan
    if refiner_output.refined_plan_phases:
        success = monitor.update_intended_plan(refiner_output.refined_plan_phases)

    # 6. Continue execution (action is blocked, agent will generate new action)
```

## Testing

### Integration Test

**File**: `test_plan_integration.py`

Tests the complete workflow:
1. ✅ Monitor detects plan violation pre-emptively
2. ✅ Refiner extracts refined plan phases
3. ✅ Monitor's intended plan is updated dynamically
4. ✅ State consistency maintained (seen_phases cleared, role_history preserved)
5. ✅ Agent can continue with refined plan without violations

Run test:
```bash
python test_plan_integration.py
```

### Phase Extraction Tests

**File**: `plan_refiner/test_phase_extraction.py`

Tests phase extraction with various formats:
- Standard format with all valid phases
- Invalid phases (filtered out)
- Repeated phases (preserved)
- No phases (empty list)
- Mixed format (some without annotations)
- Empty plan
- Malformed annotations (handled gracefully)
- Full response parsing

Run tests:
```bash
python plan_refiner/test_phase_extraction.py
```

## Configuration

### Plan Refiner Template

**File**: `plan_refiner/config/default.yaml`

Expected output format:
```yaml
<new_plan>

### Customized High-Level Plan

1. [Phase=L_navigate] Navigate to relevant source code
2. [Phase=L_reproduce] Reproduce the issue
3. [Phase=P] Apply the patch
4. [Phase=V_newly_generated_test] Test with new tests
5. [Phase=V_regression_test] Run regression tests

</new_plan>
```

### Monitor Rules

**File**: `plan_monitor/config/default_rules.json`

Original intended plan:
```json
{
  "rules": {
    "plan_compliance": {
      "intended_plan": ["L_navigate", "L_reproduce", "P", "V_newly_generated_test"],
      "block_execution": true
    }
  }
}
```

## Debugging

### Monitor Logs

When plan is updated, monitor outputs:
```
[MONITOR] Plan updated at index 1
[MONITOR] Old plan: ['L_navigate', 'P', 'V']
[MONITOR] New plan: ['L_navigate', 'L_reproduce', 'L_navigate', 'P', 'V_newly_generated_test']
[MONITOR] Next expected phase: L_reproduce
```

### Refiner Logs

```
[REFINER] Blocking rules triggered at step 5
[REFINER] Rules: ['plan_compliance']
[REFINER] Refiner output: <response>
[REFINER] New plan added to messages
```

### Common Issues

1. **Plan not updating**: Check if `plan_compliance` rule is enabled
2. **seen_phases not cleared**: Re-fetch rule after update (rollback may replace rules dict)
3. **Unexpected violations**: Check if phases match valid phase labels exactly
4. **Phase extraction empty**: Verify `[Phase=X]` annotations in refiner output

## Performance Considerations

- **Phase extraction**: O(n) where n is length of new_plan text
- **Plan update**: O(k) where k is size of new plan
- **State rollback**: O(m) where m is number of rules (deep copy)

## Future Enhancements

- [ ] Support for conditional phases (e.g., "skip V if no tests needed")
- [ ] Phase dependencies graph (e.g., "P requires L_reproduce")
- [ ] Partial plan updates (update specific phases without replacing all)
- [ ] Plan versioning/history for debugging
- [ ] Automatic plan optimization based on execution patterns

## Conclusion

The dynamic plan update integration provides a flexible, state-consistent mechanism for adapting agent execution plans in response to detected violations. The modular design allows easy integration with other agent frameworks while maintaining clear separation of concerns between monitoring, refinement, and execution.
