"""Offline, non-executing replay of SWE-agent trajectories through Drift-QL.

A reusable detection engine: it replays a recorded trajectory through the *real*
production :class:`~plan_monitor.drift_ql.drift_monitor.DriftMonitor` (no rule
re-implemented), with no future leakage and an unconditional commit after any
hypothetical block, and reports — per finalization proposal and per run — what each
Drift-QL signal would have done. It is signal-agnostic and dataset-agnostic: point
it at any ``.traj`` file to inspect signals on arbitrary data.

  * :func:`~analysis.replay.replay_monitor.replay_trajectory` — replay one
    trajectory, return its per-submission ledger + per-run signal rollup.
  * :class:`~analysis.replay.replay_monitor.ReplayMonitor` — the DriftMonitor
    subclass that backs it.

The offline signal-selection *study* (discovery, labels, prevalence, association)
lives in :mod:`analysis.signal_selection`, which drives this engine.
"""
from .replay_monitor import ReplayMonitor, replay_trajectory

__all__ = ["ReplayMonitor", "replay_trajectory"]
