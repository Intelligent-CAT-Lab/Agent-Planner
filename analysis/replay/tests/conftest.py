"""Shared fixtures for the replay tests: repo root on path + a tiny-traj writer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def make_traj(tmp_path):
    """Write a minimal SWE-agent .traj file from (action, observation) steps.

    These are clearly-fabricated fixtures, never study data.
    """
    counter = {"n": 0}

    def _make(steps, instance="fixture__inst-1", exit_status="submitted"):
        counter["n"] += 1
        data = {
            "trajectory": [
                {"action": a, "observation": o, "thought": (t if len(st) > 2 else "reasoning")}
                for st in steps
                for (a, o, t) in [(st[0], st[1], st[2] if len(st) > 2 else "")]
            ],
            "info": {"exit_status": exit_status, "submission": "diff"},
            "environment": instance,
        }
        path = tmp_path / f"{instance}.{counter['n']}.traj"
        path.write_text(json.dumps(data))
        return str(path)

    return _make
