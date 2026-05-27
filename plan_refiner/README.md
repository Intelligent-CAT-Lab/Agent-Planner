# Plan Refiner

External LLM-based planning module for Agent-Planner. Integrates with `mini-swe-agent` and `plan_monitor` to critique and refine execution plans.

## Overview

The plan_refiner provides external planning guidance by:
1. Receiving issue descriptions and trajectory data from mini-swe-agent
2. Getting state summaries from plan_monitor (phases, rules triggered, graph signals)
3. Calling an LLM to critique the current approach
4. Generating refined high-level plans for next steps

## Architecture

```
┌─────────────────┐
│ mini-swe-agent  │
│  (trajectory)   │
└────────┬────────┘
         │
         │ trajectory steps
         │ issue description
         ▼
┌─────────────────┐         ┌──────────────┐
│ plan_monitor    │────────>│ plan_refiner │
│  (rules engine) │  state  │  (LLM-based) │
└─────────────────┘ summary └──────────────┘
         │                          │
         │ rules triggered          │ analysis + new plan
         ▼                          ▼
    (when conditions met, trigger refinement)
```

## Components

### Core Module (`refiner.py`)
- `PlanRefiner`: Main class for plan refinement
- `RefinerConfig`: Configuration for refiner behavior
- Integrates with monitor to build state summaries

### Data Structures (`types.py`)
- `RefinerInput`: Input to refiner (issue + trajectory + state)
- `RefinerOutput`: Output from refiner (analysis + new plan)
- `StateSummary`: Monitor state (phases, rules, graph info)
- `TrajectoryStep`: Single step in trajectory
- `RuleTrigger`: Rule trigger information

### Formatters (`formatters.py`)
- `TrajectoryFormatter`: Formats trajectory for LLM
- `StateSummaryFormatter`: Formats monitor state for LLM
- `PromptBuilder`: Builds prompts from templates

### Models (`models.py`)
- `MockModel`: Mock LLM for testing
- `OpenAIModel`: OpenAI API interface
- `AnthropicModel`: Anthropic API interface

### Simulator (`simulator/refiner_simulator.py`)
- Replays trajectory files through monitor + refiner
- Triggers refinement when monitor rules are satisfied
- Demonstrates full pipeline functionality

## Usage

### Basic Simulation

```bash
# Run on a trajectory file
python plan_refiner/simulator/refiner_simulator.py path/to/trajectory.json

# With verbose output
python plan_refiner/simulator/refiner_simulator.py path/to/trajectory.json --verbose

# Adjust minimum steps between refinements
python plan_refiner/simulator/refiner_simulator.py path/to/trajectory.json --min-steps 10
```

### Programmatic Usage

```python
from plan_refiner import PlanRefiner, RefinerConfig, RefinerInput
from plan_refiner.models import MockModel
from plan_refiner.types import StateSummary, TrajectoryStep

# Initialize refiner
model = MockModel()
config = RefinerConfig(
    template_path="plan_refiner/config/default_template.yaml",
    max_trajectory_steps=None,
    enable_parsing=True
)
refiner = PlanRefiner(model=model, config=config)

# Prepare input
refiner_input = RefinerInput(
    issue_description="Bug description here...",
    trajectory=[
        TrajectoryStep(
            step_index=0,
            thought="My reasoning...",
            action="ls -la",
            observation="file1.py file2.py"
        ),
        # ... more steps
    ],
    state_summary=StateSummary(
        current_phase="P",
        phase_history=["L_navigate", "L_navigate", "P"],
        unique_phases=["L_navigate", "P"],
        rule_triggers=[],
        step_count=3
    )
)

# Run refinement
output = refiner.refine_plan(refiner_input)

# Use results
print(output.analysis)
print(output.new_plan)
```

### Integration with Monitor

```python
from plan_monitor.monitor import StatefulPhaseMonitor
from plan_refiner.refiner import PlanRefiner

# Initialize components
monitor = StatefulPhaseMonitor(enable_rules=True)
refiner = PlanRefiner(model=model, config=config)

# Process trajectory
for event, thought, observation in trajectory:
    result = monitor.on_step(event, thought=thought, observation=observation)

    # Trigger refinement when rules fire
    if result and result.rule_matches:
        # Build state summary from monitor
        state_summary = PlanRefiner.build_state_summary_from_monitor(
            monitor,
            result.rule_matches
        )

        # Build refiner input
        refiner_input = RefinerInput(
            issue_description=issue,
            trajectory=trajectory_steps,
            state_summary=state_summary
        )

        # Get refined plan
        output = refiner.refine_plan(refiner_input)
        print(output.new_plan)
```

## Configuration

### Configuration File (`config/default.yaml`)

The configuration file contains:

1. **Model Configuration**:
   ```yaml
   model_name: "openai/gpt-5-mini"  # Model name for OpenRouter
   model_class: "openrouter"         # Model class to use
   model_kwargs:
     temperature: 0.7
     max_tokens: 2000
     # For reasoning models:
     # extra_body:
     #   reasoning:
     #     effort: "medium"
   ```

2. **Prompt Templates**:
   - System prompt defining the planner's role
   - User prompt template with placeholders:
     - `{{ISSUE_DESCRIPTION}}`: Bug/issue description
     - `{{TRAJECTORY_SO_FAR}}`: Formatted trajectory steps
     - `{{STATE_SUMMARY}}`: Formatted state summary from monitor

### Using Different Models

To use a different model, edit `plan_refiner/config/default.yaml`:

```yaml
# For GPT-4
model_name: "openai/gpt-4"
model_class: "openrouter"

# For Claude Sonnet
model_name: "anthropic/claude-3-5-sonnet-20241022"
model_class: "openrouter"

# For reasoning models
model_name: "deepseek/deepseek-reasoner"
model_class: "openrouter"
model_kwargs:
  temperature: 0.7
  max_tokens: 2000
  extra_body:
    reasoning:
      effort: "high"
```

### Environment Variables

Set your OpenRouter API key:
```bash
export OPENROUTER_API_KEY=your_key_here
```

### Expected Output Format

The LLM should return:

```xml
<analysis>
### 1. Inferred High-Level Plan So Far
[What the agent has been doing]

### 2. Evaluation of the Plan's Logic
[Critique of the strategy]

### 3. Review of Implementation and Final Code
[Assessment of execution quality]
</analysis>

<new_plan>
### Customized High-Level Plan
1. [Phase=L_navigate] Step description...
2. [Phase=P] Step description...
3. [Phase=V_regression_test] Step description...
...
</new_plan>
```

## Testing

The plan_refiner includes a comprehensive simulator that validates:
1. ✓ Issue description extraction from trajectory
2. ✓ Monitor integration and rule triggering
3. ✓ State summary generation
4. ✓ Trajectory formatting for LLM
5. ✓ Plan refiner LLM interface
6. ✓ Analysis and plan output parsing

Run tests with:

```bash
# Test on sample trajectories
python plan_refiner/simulator/refiner_simulator.py mini-swe-agent/outputs/swebench/gpt-5-mini/django__django-10914/django__django-10914.traj.json

# Test with verbose output
python plan_refiner/simulator/refiner_simulator.py mini-swe-agent/outputs/swebench/devstral-small/samples/astropy__astropy-13033/astropy__astropy-13033.traj.json --verbose
```

## Design Principles

1. **Clean separation**: Refiner is independent of agent implementation
2. **Protocol-based**: Works with any model implementing `ModelProtocol`
3. **Configurable**: Template-driven prompts, adjustable parameters
4. **Observable**: Verbose mode for debugging
5. **Testable**: Mock model for testing without API calls

## Future Enhancements

- Support for real LLM models (OpenAI, Anthropic)
- Caching of refinements to avoid redundant calls
- Multi-turn refinement dialogue
- Integration with agent's planning loop
- Metrics tracking (refinement quality, acceptance rate)
