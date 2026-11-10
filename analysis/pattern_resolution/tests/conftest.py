"""Fixtures for the pattern-resolution tests: repo root on path + the shared traj writer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the replay suite's minimal .traj writer (clearly-fabricated fixtures, not study
# data) so the two offline-analysis test suites share one trajectory format.
from analysis.replay.tests.conftest import make_traj  # noqa: E402,F401
