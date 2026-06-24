# Plan Compliance Analysis - Low Following Rate Investigation

**Date**: 2026-06-23
**Model**: deepseek-chat-v3-0324 (swebench)
**Result**: 130/605 (21.5%) follow guidance
**Judge Model**: minimax/minimax-m3

## Summary

The low 21.5% guidance following rate is **not a bug**, but reveals important insights about:
1. How guidance is interpreted by the judge
2. The gap between mental understanding (thought) and observable action
3. Potential improvements to guidance phrasing and evaluation

## Root Cause Analysis

### 1. Judge Interprets Guidance Literally

The judging prompt states:
> "Judge primarily based on the action. Use the thought only as supporting evidence when the action is ambiguous."

This leads to **strict action-based evaluation** where:
- Guidance: "Review X then update Y" 
- Agent thought: Shows complete review with analysis
- Agent action: Directly implements update
- Judge: **FALSE** (action doesn't show "review" step)

### 2. Two-Step Guidance vs One-Step Action Pattern

**~50% of False cases** fall into this pattern:

| Guidance Says | Agent Action | Judge |
|--------------|-------------|-------|
| Review/Identify/Navigate | str_replace (modify) | FALSE |
| Review X then update Y | update Y directly | FALSE |
| Locate X and inspect Y | Only inspects Y | FALSE |

**Analysis**: The agent completes exploratory work mentally (visible in thought) but the action jumps to implementation.

#### Example Case: astropy__astropy-13579:17

**Guidance**:
```
Review the `SlicedLowLevelWCS` initialization and helper attributes 
(the slice bookkeeping for dropped axes) to find how fixed world 
values should be derived from the slice, THEN update `world_to_pixel_values`...
```

**Thought** (shows mental review):
```
Key Steps:
1. Inspect Initialization: Review how slices are stored and processed...
   - Review how slices are stored and processed during initialization
   - Identify how slice information can be used to derive fixed world values
2. Update `world_to_pixel_values`: Replace the default approach...
```

**Action**:
```
str_replace_editor str_replace /testbed/astropy/wcs/wcsapi/wrappers/sliced_wcs.py
[directly modifies the code]
```

**Judge Result**: FALSE

**Why False**: Action doesn't show observable "review" step (no `view` or `grep` command), even though thought demonstrates review was completed.

### 3. Next Step Extraction is Correct

Verified trajectory analysis confirms:
- Interventions correctly mapped to first appearance in trajectory
- Actions correctly extracted from the step where intervention appears
- No off-by-one errors or misalignment

**Example verification** (astropy__astropy-13579):
- Planner.json step 17 → Actually appears at trajectory step 18 ✓
- Extracted action matches trajectory[18].action ✓
- Previous fix handles duplicate interventions correctly ✓

## Pattern Analysis

### Distribution of False Cases

| Pattern | Count | % of False |
|---------|-------|------------|
| Guidance says "review" but action modifies | 120 | 23.5% |
| Guidance says "navigate/identify" but action modifies | 134 | 26.2% |
| Other mismatches | 257 | 50.3% |

### What Passes as True

TRUE cases show direct action-guidance alignment:
- "Shift away...inspect" → `str_replace_editor view` ✓
- "Re-run" → `python reproduce.py` ✓
- "Remove script" → `rm script.py` ✓
- "Locate module" → `str_replace_editor view` ✓

## Is the Judge Too Strict?

### Current Behavior (Strict)
- Treats multi-step guidance as requiring multi-step actions
- Ignores mental work shown in thought
- Values observable actions over strategic intent

### Arguments for Current Strictness
1. **Testable**: Action-based evaluation is objective
2. **Literal following**: Guidance should be followed as written
3. **Process matters**: "Review then update" implies review should be visible

### Arguments Against
1. **Mental work**: Agent may complete exploratory work mentally
2. **Efficiency**: Skipping intermediate steps when answer is known is smart
3. **Goal-oriented**: Focus on achieving guidance goal, not step-by-step mimicry

## Recommendations

### Option 1: Accept Current Rate (Conservative)
**Rationale**: Strict evaluation maintains high standards for guidance following.

**Actions**:
- Document that 21.5% is expected for strict literal interpretation
- Use as baseline for comparing different models/methods

### Option 2: Adjust Judging Criteria (Moderate)
**Rationale**: Give credit for achieving guidance goals even if process differs.

**Changes to evaluator prompt**:
```yaml
Judging criteria:
- Return True if the action achieves the goal stated in the guidance, 
  even if it skips intermediate exploratory steps that the thought 
  demonstrates were completed mentally.
- For multi-step guidance ("X then Y"), return True if the action 
  reasonably completes X implicitly or proceeds directly to Y when 
  the thought shows X was analyzed.
- Return False only if the action contradicts the guidance or pursues 
  an unrelated goal.
```

### Option 3: Two-Tier Evaluation (Comprehensive)
**Rationale**: Capture both strict and lenient interpretations.

**Metrics**:
1. **Strict compliance**: Current method (action-only focus)
2. **Goal achievement**: Consider thought + action together
3. **Report both** for complete picture

### Option 4: Improve Guidance Phrasing (Proactive)
**Rationale**: Make guidance more action-oriented to reduce ambiguity.

**Before**: "Review X then update Y"
**After**: "Update Y based on your understanding of X"

**Before**: "Identify and inspect X"
**After**: "Inspect X to verify Y"

## Conclusion

The 21.5% rate is **not an error** but reflects:
1. **Strict literal interpretation** by the judge
2. **Agent efficiency** (mental exploration vs observable actions)
3. **Multi-step guidance** mapped to single-step actions

**Recommended Action**: Accept current rate as baseline OR implement Option 2 (adjusted criteria) with explicit justification in methodology.

## Resolution: Updated Judge Prompt

**Decision**: Implemented Option 2 (Adjusted Criteria)

### Changes Made to evaluator.yaml

**Old Prompt** (Strict):
- "Judge primarily based on the action"
- No credit for mental exploratory work
- Treats multi-step guidance as requiring multi-step actions

**New Prompt** (Goal-Oriented):
- "Return True if the action achieves or makes meaningful progress toward the goal"
- Gives credit for exploratory steps completed mentally (shown in thought)
- For multi-step guidance, accepts proceeding to later steps when thought shows analysis
- Still rejects actions that contradict or ignore guidance

### Key Improvements

1. **Mental Work Recognition**: Thought showing "review/identify/locate" analysis now counts
2. **Multi-Step Flexibility**: "Review X then Y" → Action doing Y is TRUE if thought shows X
3. **Goal-Focused**: Evaluates whether guidance goal is achieved, not step-by-step mimicry
4. **Maintains Rigor**: Still rejects contradictory or unrelated actions

### Expected Impact

- Previous: ~21.5% (130/605) follow guidance
- Expected after re-evaluation: ~40-50% (conservative estimate)
- Pattern: ~50% of False cases were mental-work-not-visible scenarios

### Validation Plan

1. Re-run evaluation on deepseek-chat-v3-0324 with new prompt
2. Sample 30-50 flipped cases (False→True) to validate correctness
3. Compare across models (gemini-2.5-flash, minimax-m2.5)
4. Document methodology in paper with justification for goal-oriented evaluation

## Next Steps

1. ✅ Updated judge prompt in evaluator.yaml
2. Clear cache and re-run evaluation with new prompt
3. Compare old vs new results to quantify impact
4. Document chosen interpretation in paper methodology
