# R→U Case Studies: Refiner Intervention Degradation Analysis

## Summary

Analysis of 4 R→U instances where refiner intervention caused vanilla success to degrade to failure.
SWE-agent-gpt-5.4-mini-swebench-pro

---

## Instance 1: ansible__ansible-395e5e20fab9 (PlayIterator enums)

**Problem:** Standardize PlayIterator state representation with enums while preserving backward compatibility via deprecated attributes.

**Refiner Guidance:** "Implement instance-level deprecated attribute resolver (e.g., `__getattr__`)"

### Trajectory:
1. ✅ Agent implements `__getattr__` correctly
2. ✅ Validates it works (both class and instance access)
3. ✅ First submit (CORRECT solution)
4. 📝 System feedback: Standard cleanup (remove temp files, revert test changes)
5. ❌ Agent misinterprets as "code cleanup"
6. ❌ Removes the `__getattr__` method it just added
7. ❌ Second submit (BROKEN solution) - fails evaluation

### Attribution:
**Category #3: Executor fails to follow guidance effectively**

- Guidance was CORRECT
- Agent executed correctly initially
- Agent **misinterpreted routine submission feedback**
- Thought "cleanup pass" meant refactoring code, not file cleanup
- Self-sabotage after correct implementation

---

## Instance 2: ansible__ansible-a02e22e902a69aeb (Galaxy offline mode)

**Problem:** `ansible-galaxy collection install` contacts servers even with `--offline` flag.

**Solution Required:** Thread `offline` parameter through call chain:
`CLI → collection/__init__.py → dependency_resolution → galaxy_api_proxy`

### Vanilla (SUCCESS - 17 steps):
- Traced call chain systematically
- Modified **5 files** to thread offline end-to-end
- No testing - comprehensive changes then submit
- ✅ Complete solution

### Refiner (FAILURE - 26 steps):

**First Guidance (Step 24):**
> "Review the dependency resolution PROVIDER logic that invokes Galaxy API calls..."

- ❌ Directed to `providers.py` (WRONG layer - secondary concern)
- Should focus on call chain threading (primary issue)

**Agent Response:**
- Tried to add offline parameter to MultiGalaxyAPIProxy
- Hit TypeError 6+ times (offline param not recognized)
- Stuck debugging import/PYTHONPATH issues
- Created test scripts → more distractions

**Second Guidance (Step 39):**
> "Inspect which `galaxy_api_proxy` module is actually being imported..."

- Diagnosed import issue (system vs repo Ansible)
- Fixed with PYTHONPATH
- Made provider.py changes
- Submitted with false confidence

**Final Submission:**
- ✅ Added offline to galaxy_api_proxy
- ✅ Modified providers.py checks
- ❌ Missing CLI wiring (never threads offline from user input)
- ❌ Missing collection/__init__.py changes
- **offline parameter has no source - disconnected**

### Attribution:
**Category #1: Low-quality guidance focused on secondary issues**

1. **Misdirected focus** to providers.py (secondary layer) instead of call chain threading (primary)
2. **Testing-induced distraction** - premature testing led to import issues, consumed effort
3. **Incomplete solution** - after fixing imports, agent thought problem was solved, missed core wiring

Vanilla succeeded by ignoring providers.py entirely and focusing on threading the parameter through.

---

## Instance 3: ansible__ansible-cb94c0cc (timeout CLI options)

**Problem:** Add `timeout` option to ad-hoc/console CLIs and make task_include accept timeout keyword.

### Vanilla (SUCCESS - 36 steps):
Modified **5 files**:
- adhoc.py, option_helpers.py, console.py, task_include.py
- **✅ task_executor.py** - Changed `self._task.timeout` to `getattr(self._task, 'timeout', 0)` for safe attribute access

### Refiner (FAILURE - 45 steps, +9 extra):
Modified **4 files**:
- adhoc.py, option_helpers.py, console.py, task_include.py
- **❌ Missing: task_executor.py**

**Refiner Guidance (Step 28):**
> "Review the remaining required behaviors by inspecting the console command handlers... and the include validation in `TaskInclude`..."

### Attribution:
**Category #1: Low-quality guidance focused on wrong areas**
**Category #2: Execution non-determinism**

**Problems:**
- ❌ Too passive ("review and inspect" vs directive)
- ❌ Focused on console handlers and TaskInclude (already addressed)
- ❌ Didn't mention task_executor.py (the critical missing piece)
- Agent followed guidance, inspected suggested areas, submitted incomplete

Vanilla discovered task_executor.py naturally. Guidance should have been directive: "Inspect task_executor.py to ensure timeout attribute access is safe"

---

## Instance 4: openlibrary-c12943be1db80 (LCCN normalization)

**Problem:** Normalize Library of Congress Control Numbers (LCCNs) - current cleanup strips prefixes or leaves hyphenated values unnormalized.

**Solution:** Create `normalize_lccn()` function and integrate it where LCCNs are used.

### Vanilla (SUCCESS - 42 steps):
Modified **2 files**:
- ✅ `openlibrary/utils/lccn.py` - Created normalize_lccn function
- ✅ `openlibrary/plugins/upstream/models.py` - Integrated in citation generation (where LCCNs are displayed)

### Refiner (FAILURE - 41 steps):
Modified **2 files**:
- ✅ `openlibrary/utils/lccn.py` - Created normalize_lccn function
- ❌ `openlibrary/catalog/marc/parse.py` - Integrated in MARC import (WRONG location)
- ✗ Missing: `models.py` (primary LCCN usage for display/citation)

**Refiner Guidance (Step 20):**
> "Identify where LCCNs are currently parsed or cleaned in the codebase (e.g., edition save/import flows or identifier utilities)"

**Agent State Before Guidance:**
- Step 14: Created normalize_lccn function
- Step 18: Searched for usage - found NONE (function not integrated anywhere)
- Function created but NOT integrated yet

**Agent Response After Guidance:**
- Searched for "lccn" in codebase
- Found parse.py (MARC import flow)
- Integrated normalize_lccn there
- **Completely missed models.py** (the primary LCCN display/citation flow)

### Attribution:
**Category #1: Low-quality guidance - vague and misleading**

**Problems:**
1. Too vague about WHERE to look
2. Mentioned "import flows" which misdirected agent to parse.py (MARC import)
3. Didn't emphasize the MAIN flow: edition display/citation in models.py
4. parse.py is **secondary** (data ingestion); models.py is **primary** (data display/usage)

**What happened:**
- Agent followed guidance literally
- Found parse.py (matches "import flows" from guidance)
- Integrated there and stopped
- Missed the primary usage point (models.py citation generation)

**Should have been:**
- Specific: "Look at edition citation/display in `models.py` where LCCNs are formatted for output"
- Or: "Focus on the main LCCN usage in citation generation, not just import flows"

---

## Patterns Across All 4 Cases

### Distribution by Category:

| Category | Count | Instances |
|----------|-------|-----------|
| **#1: Low-quality/misleading guidance** | **3** | Galaxy offline, timeout CLI, LCCN |
| **#2: Execution non-determinism** | 1 | timeout CLI (also #1) |
| **#3: Executor fails to follow guidance** | 1 | PlayIterator |

### Common Anti-Patterns in Failed Guidance:

1. **Wrong layer focus** (Galaxy, timeout)
   - Guidance points to secondary/wrong code layers
   - Agent follows literally, misses primary layer

2. **Too vague/passive** (timeout, LCCN)
   - "Review and inspect" instead of "Modify X"
   - Agent inspects what's suggested, misses what's not mentioned

3. **Misleading examples** (LCCN, Galaxy)
   - Mentions "import flows" → agent finds wrong import layer
   - Mentions "provider logic" → agent focuses on providers.py

4. **Testing distractions** (Galaxy)
   - Encourages testing too early
   - Agent gets stuck debugging test infrastructure
   - Loses focus on holistic solution

### When Guidance Works:

**PlayIterator** - Guidance was:
- ✅ Specific: "Implement `__getattr__`"
- ✅ Directive: Clear action to take
- ✅ Correct layer: Instance-level resolution

Agent executed correctly but failed on post-submission cleanup (not guidance's fault).

### Key Insight:

**Vanilla succeeds by exploration and holistic thinking:**
- Traces full call chains (Galaxy)
- Discovers all relevant files naturally (timeout, LCCN)
- Makes comprehensive changes without testing distractions

**Refiner fails when guidance:**
- Narrows focus to wrong areas
- Uses vague language ("review", "inspect")
- Mentions examples that misdirect (wrong flows/layers)
- Creates testing distractions

---

## Recommendations for Better Guidance:

1. **Be specific about files/functions** - Don't say "import flows", say "models.py citation generation"

2. **Be directive, not passive** - "Modify X" not "Review X"

3. **Point to primary concerns first** - Call chain threading before provider logic; display layer before import layer

4. **Avoid testing suggestions** - Let agent make comprehensive changes first

5. **Verify guidance correctness** - Does the suggested location actually solve the problem?

---

## Conclusion

**75% of R→U degradations** (3 of 4) were caused by **low-quality or misleading guidance** that:
- Focused on wrong code layers
- Used vague/passive language
- Misdirected with poor examples
- Created testing distractions

Only **25%** (1 of 4) was pure executor failure despite correct guidance.

The refiner's value depends critically on guidance quality. Vague or misdirected guidance is worse than no guidance - it prevents agents from natural exploration that leads to correct solutions.
