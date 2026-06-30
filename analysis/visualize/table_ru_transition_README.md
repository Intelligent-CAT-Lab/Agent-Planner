# R→U Transition Table Generator

## Overview
This script generates LaTeX and Markdown tables showing resolution transition matrices (R→U, U→R) comparing different methods against the Vanilla actor baseline.

## Key Changes

### 1. **Triggered Instances Only (Default)**
By default, the script now computes transitions **only for instances that have triggers** (i.e., instances with a `.planner.json` file):
- For configs with planners (`monitor`, `refiner-only`, `refiner`): Only instances with `.planner.json` are included
- For configs without planners (`sage`, `default`): All instances are considered "triggered"
- This ensures fair comparison by only evaluating instances where the planner had an opportunity to intervene

### 2. **--all Flag for Full Dataset**
Added `--all` flag to compute transitions over all instances in the dataset:
```bash
python analysis/visualize/table_ru_transition.py --all
```

### 3. **Transition Computation Logic**
For triggered (or all) instances only:
- **R→U**: Baseline resolved, config did not resolve
- **U→R**: Baseline did not resolve, config resolved
- **R→R**: Both resolved (not shown in table)
- **U→U**: Neither resolved (not shown in table)

### 4. **Table Format**
Generates tables in the format:
```
| Dataset        | Method          | R→U ↓         | U→R ↑         |
|                |                 | DS | GF | MM | DS | GF | MM |
|----------------|-----------------|-----|-----|-----|-----|-----|-----|
| SWE-bench Pro  | SAGE            | 26  | 12  | 22  | 19  | 28  | 17  |
|                | Monitor-Only    | 19  | 15  | 16  | 28  | 33  | 21  |
|                | Periodic Advisor| 16  | 13  | 18  | 35  | 50  | 24  |
|                | LivePlan        | 3   | 3   | 10  | 36  | 46  | 25  |
```

Where:
- **DS** = DeepSeek-Chat-v3-0324
- **GF** = Gemini-2.5-Flash
- **MM** = Minimax-M2.5

## Usage

### Default (Triggered Instances Only)
```bash
python analysis/visualize/table_ru_transition.py \
  --datasets swebench swebench-pro \
  --models deepseek-chat-v3-0324 gemini-2.5-flash minimax-m2.5 \
  --configs sage monitor refiner-only refiner \
  --run-id 1 \
  --version 5
```

### All Instances
```bash
python analysis/visualize/table_ru_transition.py --all
```

## Output
- `analysis/tables/ru_transition.tex` - LaTeX table
- `analysis/tables/ru_transition.md` - Markdown table

## Implementation Details

### Key Functions

1. **`has_planner_trigger()`**: Checks if a `.planner.json` file exists for an instance
2. **`get_all_instance_ids()`**: Gets all instance IDs from the dataset
3. **`compute_transitions()`**: Computes R-R, R-U, U-R, U-U counts for a given set of instances
4. **`generate_latex_table()`**: Generates LaTeX table with proper formatting

### Set Operations
The transition computation uses proper set operations:
```python
r_r = len(triggered & baseline_resolved & config_resolved)
r_u = len((triggered & baseline_resolved) - config_resolved)
u_r = len((triggered & config_resolved) - baseline_resolved)
u_u = len(triggered - baseline_resolved - config_resolved)
```
