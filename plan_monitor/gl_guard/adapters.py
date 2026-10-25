"""
Adapters: build the GL-Guard occurrence model from the live LIVEPLAN state.

GL-Guard reasons over :class:`~plan_monitor.gl_guard.model.Occurrence` streams, so
this module is the *only* place that knows about the concrete Graphectory
(``networkx`` graph) and Langutory (phase labels) shapes. Keeping the binding
here means the DSL core stays representation-agnostic and fully unit-testable
without a graph.

The design explicitly does *not* require touching the existing LIVEPLAN monitor:
:class:`TrajectoryModel` is an incremental, online builder that the monitor
*could* feed as it commits steps, producing a :class:`World` at each hook. The
mapping decisions (what counts as a ``view`` / ``edit`` / ``submit``; which graph
edges are structural) are centralized and documented below.

Mappings to the existing pipeline:

  * phase label  <- Langutory role (``L_navigate`` / ``L_reproduce`` / ``P`` /
    ``V_newly_generated_test`` / ``V_regression_test`` / ``general``). ``general``
    becomes ``phase=None`` (dropped from the projection).
  * key          <- Graphectory node signature (``hash_node_signature`` identity),
    i.e. the node key that merges repeated occurrences of the same action.
  * outcome      <- ``buildGraph.check_command_outcome`` (``success`` / ``failure``).
  * kind         <- :func:`classify_kind` over (tool, subcommand, command).
  * SE edges     <- the Graphectory structural (``type="hier"``) edges.
  * obs          <- the normalized observation string for ``obs_eq``.
"""
from __future__ import annotations

import hashlib
from typing import List, Optional, Sequence, Set, Tuple

from .model import Channel, Hook, InMemoryWorld, Occurrence, World

# Sentinel commands that mark a submission in the SWE-agent harness.
_SUBMIT_MARKERS = ("COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT", "submit")
_EDIT_SUBCOMMANDS = {"create", "insert", "str_replace"}


def classify_kind(
    tool: Optional[str],
    subcommand: Optional[str],
    command: Optional[str],
    phase: Optional[str] = None,
) -> str:
    """
    Coarse action kind used by ``kind(q) = K`` in the DSL.

    This is a deliberately small vocabulary (``view`` / ``edit`` / ``submit`` /
    ``run_test`` / ``search`` / ``general``) over the same signals the Langutory
    classifier already consumes. It is heuristic by nature; the DSL treats it as
    an opaque label and never second-guesses it.
    """
    cmd = command or ""
    if any(marker in cmd for marker in _SUBMIT_MARKERS):
        return "submit"
    if tool == "str_replace_editor":
        if subcommand in _EDIT_SUBCOMMANDS:
            return "edit"
        if subcommand == "view":
            return "view"
    if phase == "P":
        return "edit"
    if phase in ("L_reproduce", "V_newly_generated_test", "V_regression_test"):
        return "run_test"
    if phase == "L_navigate":
        return "view"
    return "general"


def normalize_obs(observation: Optional[str]) -> Optional[str]:
    """Normalize an observation for ``obs_eq``: collapse whitespace, bound length."""
    if observation is None:
        return None
    collapsed = " ".join(observation.split())
    # Hash long observations so equality stays cheap and identity-stable.
    if len(collapsed) > 256:
        return hashlib.md5(collapsed.encode("utf-8")).hexdigest()
    return collapsed


class TrajectoryModel:
    """
    Incremental builder of the committed occurrence streams.

    Feed committed actions/thoughts in chronological order via :meth:`commit_action`
    and :meth:`commit_thought`; obtain a :class:`World` for the next hook via
    :meth:`world_for_propose`, :meth:`world_for_observe_action`, or
    :meth:`world_for_observe_thought`.
    """

    def __init__(self) -> None:
        self._actions: List[Occurrence] = []
        self._thoughts: List[Occurrence] = []
        self._se_edges: Set[Tuple[str, str]] = set()
        self._next_oid = 0

    # -- committing --------------------------------------------------------------

    def _alloc_oid(self) -> int:
        oid = self._next_oid
        self._next_oid += 1
        return oid

    def commit_action(
        self,
        *,
        step: int,
        key: Optional[str],
        phase: Optional[str],
        kind: Optional[str],
        outcome: Optional[str],
        observation: Optional[str] = None,
        full_action: str = "",
        phase_available: bool = True,
    ) -> Occurrence:
        occ = Occurrence(
            oid=self._alloc_oid(),
            channel=Channel.ACTION,
            step=step,
            key=key,
            phase=(None if phase in (None, "general") else phase),
            phase_available=phase_available,
            kind=kind,
            outcome=outcome,
            obs=normalize_obs(observation),
            full_action=full_action,
        )
        self._actions.append(occ)
        return occ

    def commit_thought(self, *, step: int, key: Optional[str]) -> Occurrence:
        occ = Occurrence(
            oid=self._alloc_oid(),
            channel=Channel.THOUGHT,
            step=step,
            key=key,
        )
        self._thoughts.append(occ)
        return occ

    def add_structural_edge(self, src_key: str, dst_key: str) -> None:
        """Record a directed Graphectory structural edge ``SE(src, dst)``."""
        self._se_edges.add((src_key, dst_key))

    def add_structural_edges_from_graph(self, graph) -> None:
        """Harvest ``type="hier"`` edges from a live ``networkx`` Graphectory."""
        for u, v, data in graph.edges(data=True):
            if data.get("type") == "hier":
                self._se_edges.add((u, v))

    # -- world construction ------------------------------------------------------

    def _candidate(self, channel: Channel, **attrs) -> Occurrence:
        return Occurrence(oid=self._next_oid, channel=channel, **attrs)

    def world_for_propose(
        self,
        *,
        step: int,
        key: Optional[str],
        phase: Optional[str],
        kind: Optional[str],
        full_action: str = "",
        phase_available: bool = True,
    ) -> World:
        """
        A World for a *not-yet-executed* action ``q``.

        ``q`` has no outcome and no observation (both ``None`` -> unknown), which
        the well-formedness checker already forbids rules from inspecting.
        """
        q = self._candidate(
            Channel.ACTION,
            step=step,
            key=key,
            phase=(None if phase in (None, "general") else phase),
            phase_available=phase_available,
            kind=kind,
            outcome=None,
            obs=None,
            full_action=full_action,
        )
        return self._make_world(q, Hook.PROPOSE)

    def world_for_observe_action(self, q: Occurrence) -> World:
        """A World for a freshly *committed* action ``q`` (already outcome-annotated)."""
        if q not in self._actions:
            raise ValueError("observe(action) world requires q to be committed first")
        committed = [o for o in self._actions if o.oid < q.oid]
        return InMemoryWorld(committed, self._thoughts_before(q.oid), q,
                             Hook.OBSERVE_ACTION, self._se_edges)

    def world_for_observe_thought(self, q: Occurrence) -> World:
        """A World for a freshly *committed* thought ``q``."""
        if q not in self._thoughts:
            raise ValueError("observe(thought) world requires q to be committed first")
        committed = [o for o in self._thoughts if o.oid < q.oid]
        return InMemoryWorld(self._actions_before(q.oid), committed, q,
                             Hook.OBSERVE_THOUGHT, self._se_edges)

    # -- helpers -----------------------------------------------------------------

    def _actions_before(self, oid: int) -> List[Occurrence]:
        return [o for o in self._actions if o.oid < oid]

    def _thoughts_before(self, oid: int) -> List[Occurrence]:
        return [o for o in self._thoughts if o.oid < oid]

    def _make_world(self, q: Occurrence, hook: Hook) -> World:
        return InMemoryWorld(
            committed_actions=list(self._actions),
            committed_thoughts=list(self._thoughts),
            q=q,
            hook=hook,
            se_edges=set(self._se_edges),
        )
