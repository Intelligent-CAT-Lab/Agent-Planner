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
from dataclasses import replace
from typing import List, Optional, Sequence, Set, Tuple

from .kleene import Kleene
from .model import Channel, Hook, InMemoryWorld, Occurrence, World

# Sentinel commands that mark a submission in the SWE-agent harness.
_SUBMIT_MARKERS = ("COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT", "submit")
_EDIT_SUBCOMMANDS = {"create", "insert", "str_replace"}


def classify_kind(
    tool: Optional[str],
    subcommand: Optional[str],
    command: Optional[str],
    phase: Optional[str] = None,
    full_command: Optional[str] = None,
) -> str:
    """
    Coarse action kind used by ``kind(q) = K`` in the DSL.

    This is a deliberately small vocabulary (``view`` / ``edit`` / ``submit`` /
    ``run_test`` / ``search`` / ``general``) over the same signals the Langutory
    classifier already consumes. It is heuristic by nature; the DSL treats it as
    an opaque label and never second-guesses it.

    ``full_command`` is the complete (possibly compound) command text. Submission
    is detected over it — not the parsed ``command`` token — so that the marker is
    found wherever it sits (``submit``; ``echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT``),
    exactly as the legacy monitor matches its ``ending_flags`` against the raw
    command string.
    """
    submit_text = full_command or command or ""
    if any(marker in submit_text for marker in _SUBMIT_MARKERS):
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


# =========================================================================== #
# Live binding: read the occurrence model directly from a GraphBuilder graph.
#
# This is the production wiring. The GL-Guard `World` is built from the *actual*
# Graphectory the monitor maintains, so there is no second graph and no risk of a
# divergent re-classification: the node identities, phases, outcomes, and
# exec-path order are exactly what the legacy detectors see.
#
# The two time-scales (binding design §3) are honoured here:
#   * `repeat`/`revisit`/`exists`/`count` read the occurrence-level exec-path
#     (one entry per node visit, recovered from each node's `step_indices`);
#   * `run` reads a separately supplied step-level phase stream (the monitor's
#     `role_history`), passed into :class:`GraphBoundWorld`.
# =========================================================================== #


class GraphBoundWorld(InMemoryWorld):
    """
    A :class:`World` whose occurrence streams come from a live Graphectory and
    whose phase projection (used by ``run``) is an injected *step-level* stream.

    Everything except ``phase_projection`` is inherited: ``history``,
    ``repetition_stream`` (occurrence-level), ``se`` and ``obs_eq`` all operate on
    the occurrence list exactly as in the reference model.
    """

    def __init__(self, committed_actions, committed_thoughts, q, hook,
                 phase_stream: Sequence[Optional[str]], se_edges=None, obs_eq_fn=None):
        super().__init__(committed_actions, committed_thoughts, q, hook, se_edges, obs_eq_fn)
        # Already the tentative H·q step projection (includes q's step), occurrence
        # order preserved, general phases dropped by the caller.
        self._phase_stream = [None if p in (None, "general") else p for p in phase_stream]

    def phase_projection(self) -> Sequence[Optional[str]]:
        return list(self._phase_stream)


def occurrences_from_graph(graph) -> List[Occurrence]:
    """
    Reconstruct the occurrence-level action stream from a Graphectory.

    Mirrors ``OscillationDetector._extract_exec_path``: every ``(step_idx,
    node_key)`` pair (a node may carry several, one per visit) is collected and
    ordered by ``step_idx`` with a stable sort, so compound-command occurrences
    and repeated node visits appear exactly as the legacy detector sees them.
    Per-visit phase/outcome/observation are read from the node's parallel lists.

    "think" nodes (empty-action steps) carry ``step_index`` (singular) rather than
    ``step_indices`` and are excluded from the action stream — matching the legacy
    exec-path, which only sees action nodes.
    """
    rows = []
    for node_key, data in graph.nodes(data=True):
        step_indices = data.get("step_indices")
        if not step_indices:
            continue
        phases = data.get("phases", [])
        outcomes = data.get("outcome", [])
        observations = data.get("observations", [])
        tool = data.get("tool")
        subcommand = data.get("subcommand")
        command = data.get("command")
        full_action = data.get("full_action") or ""
        for k, step_idx in enumerate(step_indices):
            rows.append((
                step_idx, node_key,
                phases[k] if k < len(phases) else None,
                outcomes[k] if k < len(outcomes) else None,
                observations[k] if k < len(observations) else None,
                tool, subcommand, command, full_action,
            ))
    rows.sort(key=lambda r: r[0])  # stable: ties keep node-iteration order

    occurrences: List[Occurrence] = []
    for oid, (step_idx, node_key, phase, outcome, obs, tool, sub, cmd, full) in enumerate(rows):
        occurrences.append(Occurrence(
            oid=oid,
            channel=Channel.ACTION,
            step=step_idx,
            key=node_key,
            phase=(None if phase in (None, "general") else phase),
            kind=classify_kind(tool, sub, cmd, phase, full_command=full),
            outcome=outcome,
            obs=normalize_obs(obs),
            full_action=full,
        ))
    return occurrences


def structural_edges_from_graph(graph) -> Set[Tuple[str, str]]:
    """Harvest the Graphectory's structural (``type="hier"``) edges for ``SE``."""
    return {(u, v) for u, v, d in graph.edges(data=True) if d.get("type") == "hier"}


def propose_world_from_graph(graph, step_phase_stream: Sequence[Optional[str]]) -> Optional[World]:
    """
    Build a ``propose`` :class:`World` from a tentative Graphectory ``H·q``.

    ``q`` is the final action occurrence; its outcome and observation are stripped
    to ``None`` because at ``propose`` the action has not executed yet (the
    well-formedness checker already forbids reading them). ``step_phase_stream`` is
    the monitor's step-level ``role_history`` extended with the current step.
    """
    occurrences = occurrences_from_graph(graph)
    if not occurrences:
        return None
    q = replace(occurrences[-1], outcome=None, obs=None)
    return GraphBoundWorld(
        committed_actions=occurrences[:-1],
        committed_thoughts=[],
        q=q,
        hook=Hook.PROPOSE,
        phase_stream=step_phase_stream,
        se_edges=structural_edges_from_graph(graph),
    )


def thought_world_from_hashes(thought_hashes: Sequence[str]) -> Optional[World]:
    """
    Build an ``observe(thought)`` :class:`World` from the committed thought-hash
    stream (the monitor's ``thought_history``). ``q`` is the latest thought.
    """
    if not thought_hashes:
        return None
    occ = [Occurrence(oid=i, channel=Channel.THOUGHT, step=i, key=h)
           for i, h in enumerate(thought_hashes)]
    return InMemoryWorld([], occ[:-1], occ[-1], Hook.OBSERVE_THOUGHT)
