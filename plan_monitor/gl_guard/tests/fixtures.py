"""Shared test fixtures: build worlds from compact occurrence specs."""
from __future__ import annotations

from typing import List, Optional

from plan_monitor.gl_guard.config import Config
from plan_monitor.gl_guard.model import Channel, Hook, InMemoryWorld, Occurrence


def liveplan_config() -> Config:
    import json
    from pathlib import Path

    spec_dir = Path(__file__).resolve().parents[1] / "specs"
    return Config.load(spec_dir / "liveplan.config.json")


class Traj:
    """A fluent builder for a committed trajectory + a candidate q."""

    def __init__(self):
        self._occs: List[Occurrence] = []
        self._oid = 0

    def _next(self) -> int:
        v = self._oid
        self._oid += 1
        return v

    def action(self, key: str, phase: Optional[str] = None, kind: Optional[str] = None,
               outcome: Optional[str] = None, obs: Optional[str] = None,
               phase_available: bool = True) -> "Traj":
        self._occs.append(Occurrence(
            oid=self._next(), channel=Channel.ACTION, step=self._oid,
            key=key, phase=phase, phase_available=phase_available,
            kind=kind, outcome=outcome, obs=obs,
        ))
        return self

    def thought(self, key: str) -> "Traj":
        self._occs.append(Occurrence(
            oid=self._next(), channel=Channel.THOUGHT, step=self._oid, key=key,
        ))
        return self

    def _committed(self):
        acts = [o for o in self._occs if o.channel is Channel.ACTION]
        ths = [o for o in self._occs if o.channel is Channel.THOUGHT]
        return acts, ths

    def propose(self, label: str = "q", key: Optional[str] = None,
                phase: Optional[str] = None, kind: Optional[str] = None,
                phase_available: bool = True, se_edges=None) -> InMemoryWorld:
        # The positional is a label; `key` (identity) defaults to it when omitted.
        acts, ths = self._committed()
        q = Occurrence(oid=self._oid, channel=Channel.ACTION, step=self._oid,
                       key=key if key is not None else label, phase=phase,
                       phase_available=phase_available, kind=kind, outcome=None, obs=None)
        return InMemoryWorld(acts, ths, q, Hook.PROPOSE, se_edges=se_edges or set())

    def observe_thought(self, label: str = "q", key: Optional[str] = None) -> InMemoryWorld:
        acts, ths = self._committed()
        q = Occurrence(oid=self._oid, channel=Channel.THOUGHT, step=self._oid,
                       key=key if key is not None else label)
        return InMemoryWorld(acts, ths, q, Hook.OBSERVE_THOUGHT)

    def observe_action(self, label: str = "q", key: Optional[str] = None,
                       phase: Optional[str] = None, kind: Optional[str] = None,
                       outcome: Optional[str] = None, obs: Optional[str] = None) -> InMemoryWorld:
        acts, ths = self._committed()
        q = Occurrence(oid=self._oid, channel=Channel.ACTION, step=self._oid,
                       key=key if key is not None else label, phase=phase,
                       kind=kind, outcome=outcome, obs=obs)
        return InMemoryWorld(acts, ths, q, Hook.OBSERVE_ACTION)
