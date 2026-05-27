# Agent-Planner

Artifact repository for agent plan refinement.

Install both packages in the same conda environment in editable mode:

```bash
# 1. Activate the planner conda environment
conda activate planner

# 2. Install agent-planner (provides plan_monitor)
cd /home/shuyang/Agent-Planner
pip install -e .

# 3. Install mini-swe-agent in the same environment
cd /home/shuyang/Agent-Planner/mini-swe-agent
pip install -e .
```