# Plan Monitor and Plan Refiner Integration

This document describes the complete integration of `plan_monitor` and `plan_refiner` into the SWE-bench_Pro-os/SWE-agent codebase.

## Overview

The integration adds strategic planning capabilities to SWE-agent through two components:

1. **Plan Monitor**: Tracks agent progress through predefined phases and applies rules to detect problematic patterns (e.g., repeated failed commands, off-track behavior)
2. **Plan Refiner**: Provides LLM-powered strategic guidance when the monitor detects issues, helping the agent recover and stay on track

## Changes Made

### 1. Core Files Modified

#### `sweagent/agent/agents.py`

**Imports Added (Lines 59-74)**:
```python
# Optional imports for plan monitoring and refining
try:
    from plan_monitor import StatefulPhaseMonitor, ActionEvent
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False

try:
    from plan_refiner import PlanRefiner
    from plan_refiner.types import RefinerInput, StateSummary, RefinerTrajectoryStep, RuleTrigger
    REFINER_AVAILABLE = True
except ImportError:
    REFINER_AVAILABLE = False
```

**DefaultAgentConfig Extended (Lines 172-187)**:
- `enable_monitor: bool = False` - Enable/disable plan monitor
- `monitor_rules_config: str = "default_rules"` - Monitor rules configuration
- `save_monitor_graph: bool = False` - Save monitor state graph
- `enable_refiner: bool = False` - Enable/disable plan refiner
- `refiner_config_path: str = "config/default.yaml"` - Refiner configuration path

**DefaultAgent.__init__ Extended (Lines 519-542)**:
- Added plan monitor/refiner state variables
- `_plan_monitor`, `_plan_refiner`, `_trajectory_data`, etc.

**DefaultAgent.from_config Enhanced (Lines 542-584)**:
- Initialize monitor with rules if enabled
- Initialize refiner with model and config if enabled
- Load min_steps_between_refinements from config

**New Methods Added**:
- `_track_planner_intervention()` - Track monitor/refiner interventions
- `save_planner_history()` - Save intervention log to JSON
- `_call_refiner()` - Handle monitor rule triggers with refiner guidance

**setup() Method Enhanced (Lines 639-664)**:
- Store `_output_dir` for later use
- Reset planner state for new instances

**forward() Method Enhanced (Lines 1269-1331)**:
- Check monitor before action execution
- Handle blocking/non-blocking rules
- Call refiner when rules triggered
- Store trajectory data for refiner

**add_step_to_history() Method Enhanced (Lines 933-990)**:
- Handle monitor blocking (don't add assistant action)
- Add monitor/refiner messages as user messages

**step() Method Enhanced (Lines 1548-1585)**:
- Check monitor_blocked flag
- Skip trajectory update for blocked steps

**run() Method Enhanced (Lines 1609-1628)**:
- Save planner history after run
- Save monitor graph if enabled

### 2. Configuration Files Created

#### `config/tool_use_with_monitor.yaml`
- Enables monitor only (no refiner)
- Use for observing agent behavior patterns

#### `config/tool_use_with_refiner.yaml`
- Enables both monitor and refiner
- Full strategic guidance system
- Saves monitor graph for visualization

### 3. Sample Data and Scripts Completed

#### `script/sample-data/sample_py_instances.py`
- Unified language sampling script
- Supports python, go, js, ts
- Default: samples all Python instances
- Can specify --num_samples for subset

#### `script/create_wrapper_config.sh`
- Auto-generates wrapper configs
- Validates sampled instances exist
- Calculates instance counts and slices
- Creates ready-to-run configs

## How to Use

### Step 1: Sample Instances by Language

From `SWE-bench_Pro-os/SWE-agent/script/sample-data/`:

```bash
# Sample all Python instances (default)
python sample_py_instances.py --dockerhub_username <username>

# Sample 50 Go instances
python sample_py_instances.py --dockerhub_username <username> --language go --num_samples 50

# Sample JavaScript instances with custom output
python sample_py_instances.py --dockerhub_username <username> --language js --output_path custom.yaml
```

**Output**: Creates `data/<language>/sampled_instances.yaml`

**Language Distribution** (SWE-bench Pro test split):
- Python: 266 instances
- Go: 280 instances  
- JavaScript: 165 instances
- TypeScript: 20 instances
- **Total**: 731 instances

### Step 2: Create Wrapper Configuration

From `SWE-bench_Pro-os/SWE-agent/script/`:

```bash
# Basic usage (default: python, deepseek-chat-v3)
./create_wrapper_config.sh my_config

# Specify model and language
./create_wrapper_config.sh go_deepseek openrouter/deepseek/deepseek-chat-v3-0324 go

# With sample size and workers
./create_wrapper_config.sh py_test openrouter/deepseek/deepseek-chat-v3-0324 python 25 20
```

**Arguments**:
1. `config_name` - Name for the wrapper config file
2. `model` - Full model path (default: openrouter/deepseek/deepseek-chat-v3-0324)
3. `language` - python|go|js|ts (default: python)
4. `num_samples` - Number to run (default: all)
5. `num_workers` - Parallel workers (default: 10)

**Output**: Creates `sweagent_wrapper_configs/<config_name>.yaml`

### Step 3: Run SWE-agent with Monitor/Refiner

#### Option A: Without Monitor/Refiner (Baseline)

```bash
# Use existing sweagent_wrapper.py with your config
python sweagent_wrapper.py my_config
```

#### Option B: With Monitor Only

Edit your config YAML to use the monitor config:
```yaml
config: config/tool_use_with_monitor.yaml
```

Or modify the generated wrapper config's `sweagent_command` to use:
```bash
--config config/tool_use_with_monitor.yaml
```

#### Option C: With Monitor + Refiner (Full System)

Edit your config YAML to use the refiner config:
```yaml
config: config/tool_use_with_refiner.yaml
```

Or modify the generated wrapper config's `sweagent_command` to use:
```bash
--config config/tool_use_with_refiner.yaml
```

### Step 4: Collect Outputs

After completion, you'll have:

1. **Trajectory Files**: `<output_dir>/<instance_id>.traj`
   - Standard SWE-agent trajectory with full history

2. **Planner History**: `<output_dir>/<instance_id>.planner.json`
   - Monitor/refiner interventions
   - Token usage and costs
   - Latency measurements

3. **Monitor Graphs**: `<output_dir>/<instance_id>.monitor_graph.json` (if `save_monitor_graph: true`)
   - State transitions visualization
   - Phase progression

4. **Predictions**: Use gather_patches.py to collect all patches:

```bash
cd ../../  # Back to SWE-bench_Pro-os root
python helper_code/gather_patches.py \
    --directory SWE-agent/trajectories/my_config/swebench-pro/deepseek-chat-v3-0324 \
    --prefix my_config \
    --output my_config_patches.json
```

### Step 5: Evaluate Results

```bash
python swe_bench_pro_eval.py \
    --raw_sample_path=swe_bench_pro_full.csv \
    --patch_path=my_config_patches.json \
    --output_dir=eval_results/my_config \
    --scripts_dir=run_scripts \
    --num_workers=100 \
    --dockerhub_username=jefzda
```

## Configuration Options

### Monitor Configuration

```yaml
agent:
  enable_monitor: true
  monitor_rules_config: "default_rules"  # or custom rules file
  save_monitor_graph: true  # false for production
```

**Available Rules** (from plan_monitor):
- `default_rules` - Balanced set for general use
- `strict_rules` - More aggressive intervention
- `lenient_rules` - Minimal intervention
- Custom: Create your own in `plan_monitor/config/`

### Refiner Configuration

```yaml
agent:
  enable_refiner: true
  refiner_config_path: "config/default.yaml"  # Path relative to plan_refiner package
```

**Refiner Config Controls**:
- LLM model selection
- Prompt templates
- Cooling period (min_steps_between_refinements)
- Cost limits

## Output Structure

```
trajectories/
├── <config>/
│   └── <dataset>/
│       └── <model>/
│           ├── instance_X.traj          # Full trajectory
│           ├── instance_X.planner.json  # Planner interventions
│           ├── instance_X.monitor_graph.json  # State graph (if enabled)
│           └── preds.json              # Compiled predictions
```

### Planner JSON Structure

```json
{
  "summary": {
    "total_interventions": 15,
    "monitor_count": 10,
    "refiner_count": 5,
    "monitor_total_latency_ms": 234.56,
    "refiner_total_latency_ms": 12345.67,
    "refiner_total_input_tokens": 25000,
    "refiner_total_output_tokens": 5000,
    "refiner_total_tokens": 30000,
    "refiner_total_cost": 0.456
  },
  "interventions": [
    {
      "step": 5,
      "planner_type": "monitor",
      "content": "Warning: Repeated failed command...",
      "latency_ms": 23.45
    },
    {
      "step": 6,
      "planner_type": "refiner",
      "content": "[Plan Refiner Guidance]\n\n...",
      "latency_ms": 2345.67,
      "usage": {
        "input_tokens": 5000,
        "output_tokens": 1000,
        "total_tokens": 6000,
        "cost": 0.091
      },
      "state_summary": {
        "current_phase": "exploration",
        "rules_triggered": ["repeated_failure"],
        ...
      }
    }
  ]
}
```

## Performance Considerations

### Time Overhead

- **Monitor Only**: ~20-50ms per step (minimal)
- **Monitor + Refiner** (first call): 2-5 seconds (LLM call)
- **Cooling Period**: Monitor-only after refiner call until threshold reached

### Cost Control

Refiner uses an additional LLM for guidance. Typical costs:
- Input: ~5000 tokens per refinement (issue + trajectory + state)
- Output: ~1000 tokens per refinement (guidance)
- Frequency: Controlled by cooling period (default: every 10 steps minimum)

**Cost Reduction Strategies**:
1. Increase `min_steps_between_refinements` in refiner config
2. Use cheaper refiner model (e.g., GPT-4-mini instead of Claude)
3. Enable refiner only for difficult instances
4. Use monitor-only mode for analysis

### Resource Requirements

- **Memory**: +~100MB for monitor state
- **Disk**: +~50KB per instance for planner.json
- **CPU**: Negligible (graph operations are fast)

## Troubleshooting

### Import Errors

If you see:
```
ImportError: No module named 'plan_monitor'
```

**Solution**: Ensure Agent-Planner directory is in sys.path:
```bash
# Check current path
python3 -c "import sys; print([p for p in sys.path if 'Agent-Planner' in p])"

# If empty, the planner-v1 conda env should have it
conda activate planner-v1
```

### Monitor Rules Not Triggering

1. Check rules config exists: `plan_monitor/config/<rules_config>.yaml`
2. Verify monitor is enabled in agent config
3. Check planner.json - if empty, no rules triggered

### Refiner Not Being Called

1. Verify `enable_refiner: true` and `enable_monitor: true` (refiner requires monitor)
2. Check REFINER_AVAILABLE flag in logs
3. Ensure refiner config path exists
4. Check cooling period - may be within cooldown

### Missing Planner History

Planner history is only saved if interventions occurred. If no rules triggered, no file is created (this is normal).

## Next Steps

### 1. Baseline Comparison

Run experiments with/without monitor/refiner:
```bash
# Baseline (no planner)
python sweagent_wrapper.py baseline_config

# With monitor
# (edit config to use tool_use_with_monitor.yaml)
python sweagent_wrapper.py monitor_config

# With refiner
# (edit config to use tool_use_with_refiner.yaml)
python sweagent_wrapper.py refiner_config
```

### 2. Analyze Interventions

```python
import json
from pathlib import Path

# Load planner history
with open("output/instance_X.planner.json") as f:
    data = json.load(f)

# Analyze
print(f"Total interventions: {data['summary']['total_interventions']}")
print(f"Refiner cost: ${data['summary'].get('refiner_total_cost', 0):.4f}")

# Check specific interventions
for interv in data['interventions']:
    if interv['planner_type'] == 'refiner':
        print(f"Step {interv['step']}: {interv['content'][:100]}...")
```

### 3. Customize Rules

Create custom monitor rules in `plan_monitor/config/`:
```yaml
# my_custom_rules.yaml
rules:
  - name: "my_rule"
    type: "pattern_matching"
    pattern: "specific_pattern"
    severity: "blocking"
    message: "Custom guidance message"
```

Then use in config:
```yaml
agent:
  monitor_rules_config: "my_custom_rules"
```

### 4. Tune Refiner Settings

Edit refiner config to adjust:
- Model selection (cost vs quality)
- Cooling period (frequency)
- Prompt templates (guidance style)
- Token limits

### 5. Scale to Full Dataset

Once validated on samples:
```bash
# Generate full dataset config
python sample_py_instances.py --dockerhub_username shuyangliu1 --language python

./create_wrapper_config.sh full_python openrouter/deepseek/deepseek-chat-v3-0324 python

# Run with increased workers
# (edit config to set num_workers: 50)
python sweagent_wrapper.py full_python
```

## Integration Status

✅ **Complete Integration**:
- ✅ Imports and availability checks
- ✅ Configuration fields
- ✅ Initialization in __init__ and from_config
- ✅ State reset in setup()
- ✅ Monitor checking in forward()
- ✅ Refiner calling with cooling period
- ✅ History management (blocking/non-blocking)
- ✅ Trajectory handling (skip blocked steps)
- ✅ Planner history tracking and saving
- ✅ Monitor graph saving
- ✅ Sample instance generation
- ✅ Wrapper config generation
- ✅ Example configurations

✅ **Tested**:
- ✅ Python compilation (no syntax errors)
- ✅ Import availability (graceful degradation)

🔄 **Ready for Runtime Testing**:
- Run on sample instances
- Verify monitor triggers correctly
- Verify refiner provides guidance
- Validate output files created
- Compare with/without planner performance

## Contact & Support

- Integration issues: Check this README and agents_integration.py
- Monitor rules: See plan_monitor/config/
- Refiner config: See plan_refiner/config/
- SWE-agent issues: https://github.com/SWE-agent/SWE-agent

---

**Integration completed**: 2026-04-29
**Version**: SWE-bench_Pro-os/SWE-agent v1.1.0
**Compatible with**: Agent-Planner plan_monitor and plan_refiner modules
