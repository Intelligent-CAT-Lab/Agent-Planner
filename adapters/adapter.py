"""Scaffold-agnostic contract between an agent scaffold and LivePlan.

A scaffold wires exactly one :class:`StepInterceptor` into its step loop and keeps
its own source almost untouched. The interceptor owns the monitor, the refiner, and
all intervention state; the scaffold only has to:

1. **delegate** execution of a proposed step to :meth:`run_step` (replacing its
   vanilla ``return self.handle_action(step)``);
2. **reset** the interceptor per instance (:meth:`reset`, from ``setup``);
3. **flush** on run completion (:meth:`on_run_done`, from ``run``); and
4. **honor** the ``extra_info`` flags the interceptor leaves on a step when it
   builds history / trajectory — the three-key contract below.

``extra_info`` contract (set by the interceptor, read by the scaffold):
  * ``monitor_blocked`` (bool): the proposed action was *not* executed and must be
    dropped — exclude it from both history and trajectory; surface only the guidance.
  * ``monitor_message`` (str): guidance text to append as a ``monitor`` message.
  * ``refiner_message`` (str): guidance text to append as a ``refiner`` message.

This keeps the scaffold's side of the seam generic (plumb three keys) and leaves
every LivePlan-specific decision inside the interceptor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class StepInterceptor(ABC):
    """The single extension point a scaffold delegates a proposed step to.

    One interceptor is bound to one agent (the binding is a concrete-subclass
    concern). Implementations live next to the scaffold they bind — e.g.
    :class:`adapters.swe_agent_adapter.LivePlanInterceptor` for SWE-agent.
    """

    @abstractmethod
    def run_step(self, step: Any) -> Any:
        """Own one proposed step end-to-end and return the final step object.

        Called from the scaffold's ``forward`` right after the action is parsed and
        ``on_actions_generated`` fires, in place of the vanilla
        ``return self.handle_action(step)``. The interceptor decides whether to
        execute the action (via the bound agent's ``handle_action``), block it, and/or
        invoke the refiner, and sets the ``extra_info`` flags documented above.
        """
        raise NotImplementedError

    def reset(self) -> None:
        """Reset per-instance state. Called from the scaffold's ``setup``."""

    def on_run_done(self, output_dir: Path) -> None:
        """Persist intervention data / artifacts. Called at the end of ``run``."""
