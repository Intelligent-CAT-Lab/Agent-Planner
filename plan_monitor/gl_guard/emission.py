"""
Emission policies: turning per-hook *verdicts* into *emissions*.

The interpreter is memoryless: at each hook it returns a Kleene verdict for the
tentative/committed prefix. But the legacy detectors in
[`plan_monitor/rules.py`](../rules.py) do not warn on every true step — they carry
emission state:

  * dwell detectors fire at the θ-th, 2θ-th, … consecutive in-phase step
    (counter **resets** after firing);
  * `repeated_view` warns **once per command key**;
  * oscillation applies rate-limiting and a per-pattern `max_repeats` cap.

GL-Guard keeps *detection* (the declarative `.glg` condition) separate from
*emission* (this module). A signal's condition says *when it is true*; its
emission policy says *when a true verdict actually produces a warning*. This is
the only place stateful "fire timing" lives, and it is small, generic, and
reusable across rules — no per-rule Python.

All state is keyed by ``(signal_id, emission_key)`` so that, e.g., `once_per_key`
is per command and `max_per_pattern` is per oscillation motif. The whole state is
**transactional** (:meth:`EmissionState.snapshot` / :meth:`restore`) so a
tentative *propose* evaluation can be rolled back exactly as the legacy monitor
rolls back its deep-copied rule state.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .kleene import Kleene

# Per-(signal, key) scratch state owned by a policy. Kept as a plain dict so the
# whole EmissionState snapshots with a cheap deepcopy.
_Cell = Dict[str, int]


class EmissionState:
    """Mutable, snapshot-able store of per-(signal, key) emission counters."""

    def __init__(self) -> None:
        self._cells: Dict[Tuple[str, str], _Cell] = {}

    def cell(self, signal_id: str, key: str) -> _Cell:
        return self._cells.setdefault((signal_id, key), {})

    def snapshot(self) -> dict:
        return copy.deepcopy(self._cells)

    def restore(self, snap: dict) -> None:
        self._cells = copy.deepcopy(snap)

    def restore_signals(self, snap: dict, signal_ids) -> None:
        """
        Restore only the cells belonging to ``signal_ids`` to their snapshot values,
        leaving every other signal's state as-is.

        Used to mirror the legacy monitor's block rollback, which restores the
        *blocking* rules' state (oscillation, plan-compliance, thought) when a
        proposal is dropped, while preserving the *non-blocking* rules' state
        (dwell, repeated-view).
        """
        signal_ids = set(signal_ids)
        for key in [k for k in self._cells if k[0] in signal_ids]:
            if key in snap:
                self._cells[key] = copy.deepcopy(snap[key])
            else:
                del self._cells[key]

    def reset(self) -> None:
        self._cells.clear()


@dataclass(frozen=True)
class EmissionDecision:
    """The result of consulting a policy for one verdict."""

    emit: bool
    #: Optional override message id (e.g. the oscillation `max_repeats` terminal
    #: message) that the advice registry should render instead of the default.
    message_variant: Optional[str] = None


class EmissionPolicy:
    """
    A generic, stateful emission gate.

    ``decide`` is called for every *definite* verdict (``is_true`` = whether the
    verdict was ``TRUE``; ``FALSE`` is still delivered so run-length policies can
    reset). It mutates the per-(signal,key) cell and returns whether to emit. An
    ``UNKNOWN`` verdict is never delivered — it neither emits nor mutates state.
    """

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:  # pragma: no cover - abstract
        raise NotImplementedError

    @staticmethod
    def from_config(spec: dict) -> "EmissionPolicy":
        mode = spec.get("mode", "always")
        if mode == "always":
            return Always()
        if mode == "once_per_key":
            return OncePerKey()
        if mode == "every_n":
            return EveryN(period=int(spec["period"]))
        if mode == "on_rising_edge":
            return OnRisingEdge()
        if mode == "cooldown":
            return Cooldown(gap=int(spec["gap"]))
        if mode == "max_per_pattern":
            return MaxPerPattern(
                max_emits=int(spec["max"]),
                terminal_variant=spec.get("terminal_variant"),
            )
        raise ValueError(f"unknown emission mode {mode!r}")


class Always(EmissionPolicy):
    """Emit on every true verdict (no suppression)."""

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:
        return EmissionDecision(emit=is_true)


class OncePerKey(EmissionPolicy):
    """Emit only the first true verdict for a key; suppress the rest (no reset).

    Reproduces `repeated_view`'s per-command one-time warning.
    """

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:
        if not is_true:
            return EmissionDecision(emit=False)
        fired = cell.get("fired", 0)
        cell["fired"] = 1
        return EmissionDecision(emit=(fired == 0))


class OnRisingEdge(EmissionPolicy):
    """Emit only on a false→true transition (the start of a true run)."""

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:
        was_true = cell.get("was_true", 0)
        cell["was_true"] = 1 if is_true else 0
        return EmissionDecision(emit=(is_true and was_true == 0))


class EveryN(EmissionPolicy):
    """
    Emit on the 1st, (period+1)-th, (2·period+1)-th … consecutive true verdict.

    This reproduces the legacy dwell detector exactly: with the monitor's
    step-level phase stream, ``run(F) >= θ`` first becomes true at the θ-th
    in-phase step, and :class:`EveryN` with ``period=θ`` then fires at in-phase
    steps θ, 2θ, 3θ — matching ``DwellTimeRule``'s reset-after-fire counter.
    """

    def __init__(self, period: int):
        if period < 1:
            raise ValueError("EveryN period must be >= 1")
        self.period = period

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:
        if not is_true:
            cell["consecutive"] = 0  # run broken -> reset
            return EmissionDecision(emit=False)
        d = cell.get("consecutive", 0) + 1  # number of consecutive true verdicts
        cell["consecutive"] = d
        return EmissionDecision(emit=((d - 1) % self.period == 0))


class Cooldown(EmissionPolicy):
    """Emit at most once per ``gap`` steps for a key (rate limiting)."""

    def __init__(self, gap: int):
        if gap < 1:
            raise ValueError("Cooldown gap must be >= 1")
        self.gap = gap

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:
        if not is_true:
            return EmissionDecision(emit=False)
        last = cell.get("last_emit")
        if last is None or step - last >= self.gap:
            cell["last_emit"] = step
            return EmissionDecision(emit=True)
        return EmissionDecision(emit=False)


class MaxPerPattern(EmissionPolicy):
    """
    Emit up to ``max_emits`` times per key, optionally emitting one terminal
    message variant on the final allowed emission, then suppress.

    Reproduces the oscillation ``max_repeats`` behaviour: after N warnings about
    the same motif, emit the terminal ("stop or submit") message once, then go
    quiet for that motif.
    """

    def __init__(self, max_emits: int, terminal_variant: Optional[str] = None):
        if max_emits < 1:
            raise ValueError("MaxPerPattern max must be >= 1")
        self.max_emits = max_emits
        self.terminal_variant = terminal_variant

    def decide(self, cell: _Cell, step: int, is_true: bool) -> EmissionDecision:
        if not is_true:
            return EmissionDecision(emit=False)
        count = cell.get("count", 0)
        if count >= self.max_emits:
            return EmissionDecision(emit=False)
        count += 1
        cell["count"] = count
        if count == self.max_emits and self.terminal_variant is not None:
            return EmissionDecision(emit=True, message_variant=self.terminal_variant)
        return EmissionDecision(emit=True)
