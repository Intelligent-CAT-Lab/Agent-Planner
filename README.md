# Agent-Planner

Artifact for Monitor, Detect, Advise: Rule-Based Monitoring and Next-Step Intervention for Programming Agents. This repository contains **LivePlan**, a system that monitors programming agent execution and provides both rule-based predefined guidance and LLM-generated custom advice to improve agent performance on code repair tasks.

## Overview

LivePlan operates through two complementary components:

**Monitor** (`plan_monitor`) continuously observes agent execution and builds trajectory representations:
- Extracts high-level phases from low-level actions (e.g., code navigation, patching, validation)
- Constructs program dependency graphs (Graphectory) and execution sequences (Langutory)
- Evaluates trajectories against configurable rules to detect issues: plan violations, stuck behavior, oscillations, or lost strategy

**Advisor** (`plan_refiner`) provides LLM-based intervention when triggered by rules:
- Receives issue description, execution trajectory, and monitor state
- Queries an LLM for analysis and refined next-step guidance
- Fully pluggable—integrates cleanly via step-level hooks in any agent
- Invoked only when monitor rules fire and outside cooldown to minimize cost

The two components work together: the monitor detects *when* intervention is needed; the advisor generates *what* to advise next.

## Installation

Install in a single conda environment:

```bash
cd Agent-Planner && pip install -e .
cd SWE-agent && pip install -e .
# for SWE-Bench Pro
cd ../SWE-bench_Pro-os/SWE-agent && pip install -e .
```

## Quick Start

Run SWE-Agent with LivePlan:

```bash
# Full LivePlan (monitor + LLM refiner)
bash SWE-agent/script/refiner_run.sh

# Monitor only (predefined rule-based guidance)
bash SWE-agent/script/monitor_run.sh

# Vanilla baseline (no intervention)
bash SWE-agent/script/vanilla_run.sh
```

Trajectories are saved to `{agent_dir}/trajectories/{method}/swebench/...` organized by approach and run.

## Configuration

### Rules
Customize detection logic in `plan_monitor/config/default_rules.json`:
- **plan violation**: Detect skipped phases or wrong order
- **oscillation**: Detect repeated loops in actions or thoughts
- **long stagnation**: Detect prolonged stagnation in single phase
- **repeated action**: Detect a backedge in Graphectory.

Each rule includes configurable thresholds and custom messages.

### LLM Models
Edit `plan_refiner/config/default.yaml` to specify the model (via OpenRouter) and adjust temperature, max tokens, and prompt templates.

## Results & Baselines

We provide recorded trajectories for all baselines:

| Method | Approach |
|--------|----------|
| `vanilla` | No monitoring (baseline) |
| `sage` | Oracle heuristic predictor of interventions |
| `monitor` | Rule-based predefined guidance only |
| `refiner-only` | Periodic LLM advisor on fixed schedule |
| `refiner` | LivePlan: rule-triggered LLM advisor (proposed) |

**Raw Trajectories**: Hosted on Zenodo due to file size: []().