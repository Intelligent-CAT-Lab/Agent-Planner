"""LivePlan adapters: wire monitor/refiner interventions into an agent scaffold
through a single, minimal seam instead of editing the scaffold's source.

- :class:`~adapters.adapter.StepInterceptor` — the scaffold-agnostic contract.
- :class:`~adapters.swe_agent_adapter.LivePlanInterceptor` + :func:`build_interceptor`
  — the SWE-agent binding (monitor, refiner, all intervention state).
- :class:`~adapters.trace.InterventionTrace` — the saved ``{instance}.planner.json``.
"""
from __future__ import annotations

from .adapter import StepInterceptor
from .trace import InterventionTrace

__all__ = ["StepInterceptor", "InterventionTrace", "build_interceptor"]


def build_interceptor(config, agent, *, observe_results: bool = True):
    """Lazy re-export of the SWE-agent interceptor factory.

    Imported lazily so that merely importing :mod:`adapters` does not require
    ``plan_monitor`` / ``plan_refiner`` to be installed.
    """
    from .swe_agent_adapter import build_interceptor as _build

    return _build(config, agent, observe_results=observe_results)
