"""
The GL-Guard occurrence model and finite-prefix world.

GL-Guard is defined over the LIVEPLAN representations (Graphectory `G` and
Langutory `L`), but it does *not* reimplement them. Instead it consumes a thin,
representation-agnostic view:

  * An :class:`Occurrence` is one committed (or currently-proposed) agent event
    on a *channel* (``action`` or ``thought``). It exposes exactly the fields the
    DSL can observe: identity ``key``, phase label, kind, outcome and a
    normalized observation. Missing fields are modelled as ``None`` and surface
    as the Kleene unknown (?) during evaluation.

  * A :class:`World` is the *finite-prefix model* at a single hook firing. It is
    the pair ``(H, q)`` plus the structural relations of ``G``:

        - ``H``  the committed global occurrence sequence (strictly before ``q``),
        - ``q``  the distinguished current occurrence provided by the hook,
        - ``SE`` / ``obs_eq``  structural and observational relations.

    The World is responsible for the semantic subtleties of section 5 of the
    design: ``history(c)`` excludes ``q``; at ``propose`` the phase-run and
    repetition streams are formed over the *tentative* extension ``H·q`` without
    committing ``q``; and the thought-repetition stream is scoped to the current
    reasoning episode (since the last executable action).

The concrete :class:`InMemoryWorld` below is the reference implementation used by
the interpreter and the tests. Adapters that build a World from a live
Graphectory/Langutory live in :mod:`plan_monitor.gl_guard.adapters`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence

from .kleene import Kleene, U, from_bool


class Channel(str, Enum):
    """The two occurrence channels GL-Guard reasons over."""

    ACTION = "action"
    THOUGHT = "thought"


class Hook(str, Enum):
    """The three online intervention points of LIVEPLAN."""

    PROPOSE = "propose"
    OBSERVE_ACTION = "observe(action)"
    OBSERVE_THOUGHT = "observe(thought)"

    @property
    def channel(self) -> Channel:
        """The channel of the distinguished occurrence ``q`` at this hook."""
        return Channel.THOUGHT if self is Hook.OBSERVE_THOUGHT else Channel.ACTION

    @property
    def is_propose(self) -> bool:
        return self is Hook.PROPOSE


# A phase symbol in the Langutory projection. A concrete label (e.g. "L_navigate")
# is retained; ``None`` denotes a phase that is present but whose label is
# unavailable (yields ? for membership). "general" occurrences are dropped from
# the projection entirely by the World and never appear here.
PhaseSymbol = Optional[str]


@dataclass(frozen=True)
class Occurrence:
    """
    One committed or proposed agent event.

    Attributes:
        oid:     Global total-order index (chronological; ties broken by the
                 builder). ``before(u, v)`` is simply ``u.oid < v.oid``.
        channel: ACTION or THOUGHT.
        step:    Trajectory step index (for diagnostics / metadata only).
        key:     Node/action identity used by ``key(.)`` and ``revisit``. For an
                 action this is the Graphectory node signature; for a thought it
                 is the thought hash. ``None`` iff the identity is unavailable.
        phase:   Canonical Langutory label, or ``None`` for a "general" /
                 unclassified action (dropped from the phase projection).
        phase_available: ``False`` iff the phase *could not be computed* (rare);
                 distinguishes "general" (retained=False, definite) from
                 "unknown" (retained with a ? symbol).
        kind:    Coarse action kind (``view`` / ``edit`` / ``submit`` / ...), or
                 ``None`` if unavailable. Only meaningful on the ACTION channel.
        outcome: ``"success"`` / ``"failure"``, or ``None`` when no execution
                 outcome exists (a pending/proposed action, or not yet computed).
        obs:     Normalized observation string used by ``obs_eq``; ``None`` if the
                 observation is unavailable.
    """

    oid: int
    channel: Channel
    step: int = -1
    key: Optional[str] = None
    phase: PhaseSymbol = None
    phase_available: bool = True
    kind: Optional[str] = None
    outcome: Optional[str] = None
    obs: Optional[str] = None
    full_action: str = ""

    @property
    def retained(self) -> bool:
        """Whether this action contributes a symbol to the Langutory phase projection."""
        if not self.phase_available:
            return True  # retained, but with an unknown symbol
        return self.phase is not None  # "general" (None) is dropped

    @property
    def phase_symbol(self) -> PhaseSymbol:
        return self.phase if self.phase_available else None


class World:
    """
    Abstract finite-prefix model ``(H, q, hook)`` with structural relations.

    Subclasses provide the committed streams and the ``SE`` / ``obs_eq``
    relations. The interpreter never reaches past this interface, so a live
    Graphectory/Langutory and the in-memory test fixture are interchangeable.
    """

    #: The distinguished current occurrence provided by the hook.
    q: Occurrence
    #: The hook at which this world was constructed.
    hook: Hook

    def history(self, channel: Channel) -> Sequence[Occurrence]:
        """Committed occurrences of ``channel`` strictly before ``q`` (excludes ``q``)."""
        raise NotImplementedError

    def phase_projection(self) -> Sequence[PhaseSymbol]:
        """
        Langutory phase projection of the tentative prefix ``H·q``.

        General/unclassified actions are dropped; unavailable phases appear as
        ``None`` (unknown). Occurrence order is preserved; ``q`` is included when
        it is a retained action.
        """
        raise NotImplementedError

    def repetition_stream(self, channel: Channel) -> Sequence[Optional[str]]:
        """
        The identity stream used by ``repeat`` over ``H·q``:

          * action: the key of every action occurrence through ``q``;
          * thought: the keys of the uninterrupted thought episode ending at
            ``q`` (since the last executable action).

        ``None`` entries denote unknown identities.
        """
        raise NotImplementedError

    def se(self, u: Occurrence, v: Occurrence) -> Kleene:
        """Directed structural edge ``SE(node(u), node(v))`` of the Graphectory."""
        raise NotImplementedError

    def obs_eq(self, u: Occurrence, v: Occurrence) -> Kleene:
        """Observational equivalence of two occurrences' recorded outputs."""
        raise NotImplementedError


class InMemoryWorld(World):
    """
    Reference :class:`World` built from explicit occurrence lists.

    This is the model used by the interpreter's tests and by the adapters once
    they have projected the live representations into :class:`Occurrence` lists.
    It implements the finite-prefix semantics (section 5) directly:

      * ``history(c)`` returns the committed occurrences of channel ``c`` (which
        the constructor guarantees are strictly before ``q``);
      * the phase/repetition streams append ``q`` tentatively at ``propose`` and
        already contain ``q`` at ``observe`` — in both cases ``history`` excludes
        it, so a rule can never count ``q`` as its own predecessor.
    """

    def __init__(
        self,
        committed_actions: Sequence[Occurrence],
        committed_thoughts: Sequence[Occurrence],
        q: Occurrence,
        hook: Hook,
        se_edges: Optional[set] = None,
        obs_eq_fn: Optional[Callable[[Occurrence, Occurrence], Kleene]] = None,
    ):
        self._actions: List[Occurrence] = list(committed_actions)
        self._thoughts: List[Occurrence] = list(committed_thoughts)
        self.q = q
        self.hook = hook
        # Structural edges as a set of (source_key, target_key) pairs.
        self._se_edges = se_edges or set()
        self._obs_eq_fn = obs_eq_fn or self._default_obs_eq

        self._validate_prefix()

    # -- construction invariants -------------------------------------------------

    def _validate_prefix(self) -> None:
        """history must be strictly before q, and q's channel must match the hook."""
        if self.q.channel != self.hook.channel:
            raise ValueError(
                f"q is on channel {self.q.channel} but hook {self.hook} expects "
                f"{self.hook.channel}"
            )
        committed = self._actions if self.q.channel is Channel.ACTION else self._thoughts
        for occ in committed:
            if occ.oid >= self.q.oid:
                raise ValueError(
                    "committed history must be strictly before q (found oid "
                    f"{occ.oid} >= q.oid {self.q.oid})"
                )

    # -- streams -----------------------------------------------------------------

    def history(self, channel: Channel) -> Sequence[Occurrence]:
        src = self._actions if channel is Channel.ACTION else self._thoughts
        # Defensive: enforce "strictly before q" for the *other* channel too.
        return [o for o in src if o.oid < self.q.oid]

    def _tentative_actions(self) -> List[Occurrence]:
        """Committed actions plus q (when q is an action): the H·q action stream."""
        actions = self.history(Channel.ACTION)
        if self.q.channel is Channel.ACTION:
            return list(actions) + [self.q]
        return list(actions)

    def phase_projection(self) -> Sequence[PhaseSymbol]:
        return [o.phase_symbol for o in self._tentative_actions() if o.retained]

    def repetition_stream(self, channel: Channel) -> Sequence[Optional[str]]:
        if channel is Channel.ACTION:
            return [o.key for o in self._tentative_actions()]

        # Thought channel: the uninterrupted reasoning episode ending at q.
        # The episode is the maximal suffix of thoughts occurring after the last
        # committed action (feedback-separated thoughts are *not* conflated).
        last_action_oid = max((o.oid for o in self.history(Channel.ACTION)), default=-1)
        episode = [o for o in self.history(Channel.THOUGHT) if o.oid > last_action_oid]
        if self.q.channel is Channel.THOUGHT:
            episode = episode + [self.q]
        return [o.key for o in episode]

    # -- structural relations ----------------------------------------------------

    def se(self, u: Occurrence, v: Occurrence) -> Kleene:
        if u.key is None or v.key is None:
            return U
        return from_bool((u.key, v.key) in self._se_edges)

    def obs_eq(self, u: Occurrence, v: Occurrence) -> Kleene:
        return self._obs_eq_fn(u, v)

    @staticmethod
    def _default_obs_eq(u: Occurrence, v: Occurrence) -> Kleene:
        if u.obs is None or v.obs is None:
            return U
        return from_bool(u.obs == v.obs)
