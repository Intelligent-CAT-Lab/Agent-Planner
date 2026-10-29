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

The two benchmarks need **two separate conda environments**. Both forks install
under the identical package name `sweagent` and pin **incompatible** `swe-rex`
versions (SWE-bench needs `>=1.4.0` for local Docker; SWE-bench-Pro needs
`[modal]==1.2.0` for Modal), so they cannot coexist in one environment — the
last `pip install -e` would silently shadow the other.

Create both with one command:

```bash
bash setup.sh          # creates `planner` (SWE-bench) and `planner-pro` (SWE-bench-Pro)
# or individually:  bash setup.sh swebench   |   bash setup.sh pro
```

Each environment gets its benchmark's fork **plus** this repo installed editable,
which provides the shared LivePlan code (`adapters`, `plan_monitor`,
`plan_refiner`). Re-running is safe — existing envs are updated in place.

| Environment   | Benchmark      | Fork                        | swe-rex          | Execution    |
| ------------- | -------------- | --------------------------- | ---------------- | ------------ |
| `planner`     | SWE-bench      | `SWE-agent/`                | `>=1.4.0`        | local Docker |
| `planner-pro` | SWE-bench-Pro  | `SWE-bench_Pro-os/SWE-agent/` | `[modal]==1.2.0` | Modal        |

Activate the one matching the benchmark you want to run (see Quick Start).

<details>
<summary>Manual install (equivalent to one <code>setup.sh</code> env)</summary>

```bash
conda create -n planner python=3.11 -y          # or planner-pro
conda run -n planner pip install -e SWE-agent    # the fork (Pro: SWE-bench_Pro-os/SWE-agent)
conda run -n planner pip install -e .            # shared adapters/plan_monitor/plan_refiner
```
</details>

> **Note:** `SWE-bench_Pro-os/SWE-agent` is a vendored copy of Scale AI's fork ([`scaleapi/SWE-agent`](https://github.com/scaleapi/SWE-agent), branch `scale-customizations`), kept separate from the root `SWE-agent` (Princeton upstream) because it carries Pro-specific engine customizations (Modal execution).

## Quick Start

Run SWE-Agent with LivePlan (activate the env for your benchmark first):

```bash
conda activate planner          # SWE-bench

# Full LivePlan (monitor + LLM refiner)
bash SWE-agent/script/refiner_run.sh

# Monitor only (predefined rule-based guidance)
bash SWE-agent/script/monitor_run.sh

# Vanilla baseline (no intervention)
bash SWE-agent/script/vanilla_run.sh
```

For SWE-bench-Pro, use the `planner-pro` env and its scripts:

```bash
conda activate planner-pro      # SWE-bench-Pro (Modal)
bash SWE-bench_Pro-os/SWE-agent/script/run_refiner.sh
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

**Raw Trajectories**: Hosted on Zenodo due to file size: [https://zenodo.org/records/21465785](https://zenodo.org/records/21465785).