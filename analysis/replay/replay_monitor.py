"""
Deterministic, non-executing replay of a SWE-agent trajectory.

:class:`ReplayMonitor` subclasses the production
:class:`~plan_monitor.drift_ql.drift_monitor.DriftMonitor` so detection reuses the
*real* graph builder, adapters, three-valued interpreter, and emission policies —
no rule is re-implemented. It differs from the live monitor in exactly the two ways
an offline replay requires, and is otherwise byte-identical:

  1. **Unconditional commit.** A recorded vanilla action happened even if a detector
     would have blocked it. The live monitor rolls back a blocking proposal; the
     replay never does — it records ``would_block`` / ``would_emit`` counterfactually
     and commits the recorded transition, so the next prefix is the true vanilla
     prefix. Nothing is executed; ``observe_result`` only ingests the *recorded*
     observation.

  2. **Shadow verdicts.** Signals that are ``enabled:false`` are skipped by the
     production runtime; the replay evaluates them under ``include_disabled=True`` so
     a not-yet-enabled candidate can still be characterised. For every proposal the
     replay accumulates three observables into the per-signal rollup: the pure
     interpreter verdict (true/false/unknown) via ``program.evaluate``, whether the
     emission policy would emit, and whether it would block.

No-leakage is structural, not a post-hoc strip: at step *i* the graph holds the
committed actions ``0..i-1`` (with their real recorded outcomes, filled by prior
``observe_result`` calls) plus ``q`` built with ``observation=""`` and
``outcome=None``. ``q``'s recorded observation/outcome are ingested only *after* its
propose evaluation, by the driver calling ``observe_result``.

The engine is signal-agnostic and its single output is the per-run, per-signal rollup
over EVERY evaluated signal (propose *and* ``observe(thought)``) — for offline traj
analysis: "what signals fired for this trajectory, and how often". Submits are
recognized by the action, exactly as online; a submission signal fires whenever its
condition holds at a submit proposal, and submits are neither ranked nor counted. A
caller studying any subset of signals needs no engine change; the only study-specific
knowledge lives in the analysis layer (``analysis.signal_selection``). Replaying a
single trajectory to inspect its signals is just :func:`replay_trajectory`.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Dict

from plan_monitor.buildGraph import build_online_graph_from_trajectory
from plan_monitor.drift_ql import ast as _ast
from plan_monitor.drift_ql.adapters import (propose_world_from_graph,
                                            thought_world_from_hashes)
from plan_monitor.drift_ql.advice import AdviceRegistry
from plan_monitor.drift_ql.config import Config
from plan_monitor.drift_ql.engine import DriftProgram
from plan_monitor.drift_ql.drift_monitor import DriftMonitor, _SPEC_DIR
from plan_monitor.drift_ql.kleene import Kleene as _K
from plan_monitor.drift_ql.model import Hook
from plan_monitor.drift_ql.parser import parse_program
from plan_monitor.drift_ql.runtime import DriftRuntime
from plan_monitor.simulator.swe_extractor import ActionExtractor

# Candidate signals under study live in their own spec so production ``DriftMonitor``
# never loads them. The replay evaluates them in SHADOW alongside the live profile.
# Dropping a new ``(spec, advice)`` here (or passing ``shadow_specs``) adds it to the
# study with no engine change; passing ``shadow_specs=()`` replays the live profile
# exactly (e.g. to inspect signals on arbitrary trajectories).
DEFAULT_SHADOW_SPECS = (("extra_signals.glg", "extra_signals.advice.json"),)


@lru_cache(maxsize=None)
def _study_program(shadow_specs):
    """Parse the merged ``liveplan`` ∪ candidate spec set ONCE per process.

    Returns the immutable ``(DriftProgram, AdviceRegistry)`` pair. Both are read-only
    during evaluation — all mutable emission state lives in :class:`DriftRuntime` — so
    the parsed result is cached and every :func:`build_study_runtime` call wraps it in a
    *fresh* runtime. ``shadow_specs`` is the cache key (a tuple of ``(glg, advice)``
    pairs), so passing ``()`` (the live profile) caches separately from the default.
    """
    config = Config.load(_SPEC_DIR / "liveplan.config.json")
    rules = list(parse_program((_SPEC_DIR / "liveplan.glg").read_text()))
    seen = {r.name for r in rules}
    base_reg = AdviceRegistry.load(_SPEC_DIR / "liveplan.advice.json")
    entries = dict(base_reg.entries)
    for glg, adv in shadow_specs:
        gpath, apath = _SPEC_DIR / glg, _SPEC_DIR / adv
        if not gpath.is_file():
            continue
        for rule in parse_program(gpath.read_text()):
            if rule.name not in seen:          # live definition wins on overlap
                rules.append(rule); seen.add(rule.name)
        if apath.is_file():
            for name, entry in AdviceRegistry.load(apath).entries.items():
                entries.setdefault(name, entry)  # live advice wins on overlap
    program = DriftProgram(rules, config)
    registry = AdviceRegistry(
        entries, non_blocking_action_kinds=base_reg.non_blocking_action_kinds)
    return program, registry


def build_study_runtime(shadow_specs=DEFAULT_SHADOW_SPECS) -> DriftRuntime:
    """The live ``liveplan`` program + shadow candidate specs, as one runtime.

    All specs share ``liveplan.config.json`` (so the candidates' phase groups
    resolve). The merge is **overlap-safe**: a signal (or advice entry) defined in
    both the live profile and a candidate spec keeps its *live* definition — the
    candidate's duplicate is dropped — so production semantics are authoritative and
    the well-formedness checker never sees a duplicate name. Candidates keep their
    ``enabled:false`` advice, so they surface only under ``include_disabled=True``.
    This is the single source of truth for the replayed signal set; both
    :class:`ReplayMonitor` and the analysis build from it, so they never drift.

    The spec parse is memoized per process (:func:`_study_program`) and only the small
    mutable :class:`DriftRuntime` is rebuilt per call — so replaying thousands of
    trajectories in one worker parses the ``.glg`` specs once, not once per trajectory.
    """
    program, registry = _study_program(tuple(shadow_specs))
    return DriftRuntime(program, registry)


def _top_level_conjuncts(node):
    """Flatten the top-level ``and`` of a rule body into its conjunct list."""
    if isinstance(node, _ast.And):
        out = []
        for op in node.operands:
            out.extend(_top_level_conjuncts(op))
        return out
    return [node]


def submit_gated_signals(program, hook) -> set:
    """Names of rules on ``hook`` that *require* ``kind(q) = submit`` to fire.

    These are the plan-compliance submit family (``skip_patch`` / ``skip_validation``
    / ``no_successful_patch`` / ``stale_validation`` / ...): a terminal-state check
    that is only meaningful at a submission. Detected structurally as a top-level
    conjunct ``kind(q) = submit`` -- so a *negated* occurrence (``oscillation`` /
    ``action_recurrence``, which say ``not kind(q)=submit``) is correctly excluded,
    and any new ``kind(q) = submit and ...`` signal is classified automatically.

    This is an OFFLINE-replay concern only. The online engine fires these normally
    at every submit (it cannot know which submit is the last); but when scoring a
    *completed* trajectory offline, only the final submit characterises the end
    state -- a premature submit the monitor already blocked, then a proper submit
    after patching, must not be counted as an unresolved violation. ``replay_detail``
    reads these signals at the last submit instead of OR-ing across every attempt.
    """
    out = set()
    for rule in program.rules_for(hook):
        for conj in _top_level_conjuncts(rule.body):
            if isinstance(conj, _ast.KindEq) and conj.kind == "submit":
                out.add(rule.name)
                break
    return out


def _blank_runstat() -> Dict:
    return {"n_eval": 0, "n_true": 0, "n_unknown": 0,
            "n_emit": 0, "n_block": 0, "first_true_step": None}


class ReplayMonitor(DriftMonitor):
    """A ``DriftMonitor`` that records counterfactual verdicts and never rolls back."""

    def __init__(self, *args, shadow_specs=DEFAULT_SHADOW_SPECS, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._merge_shadow_specs(shadow_specs)
        # Signals that only fire on a submit proposal (computed after the shadow
        # merge, so candidate submit signals are included). Their trajectory-level
        # verdict is read at the LAST submit, not OR-ed across attempts -- see
        # ``submit_gated_signals`` and ``submit_final_true``.
        self._submit_signals = submit_gated_signals(self.runtime.program, Hook.PROPOSE)
        # Verdict of each submit-gated signal at the most recent submit proposal
        # (overwritten every submit step, so after the replay it holds the final
        # submit's verdicts). Empty if the run never submitted.
        self.submit_final_true: Dict[str, bool] = {}
        self.n_action_steps = 0
        self.n_thought_steps = 0
        # Whether the run issued a submit (recognized by the action, as online). This
        # is the opportunity for the submission signals; submits are not ranked or
        # counted — a submission signal simply fires whenever its condition holds.
        self.submitted = False
        # Per-run, per-signal rollup over ALL evaluated proposals (propose and
        # observe(thought)): how often each signal was evaluated, became
        # true/unknown, would emit, would block, and where it first fired. This is
        # the complete "monitored signals" record the offline analysis needs; the
        # replay emits no .planner.json (no advisor is invoked).
        self.signal_runstats: Dict[str, Dict] = {}

    def _merge_shadow_specs(self, shadow_specs) -> None:
        """Swap in the shadow-augmented runtime (``liveplan`` ∪ candidates).

        A no-op when no candidate spec file is present, so the replay then mirrors the
        live profile (honouring any custom spec passed to ``DriftMonitor``). The
        general-step restriction is re-synced to the merged program (the live monitor
        skips dwell/run signals on general-only steps).
        """
        if not any((_SPEC_DIR / g).is_file() for g, _ in shadow_specs):
            return
        self.runtime = build_study_runtime(shadow_specs)
        program = self.runtime.program
        self._general_step_signals = (
            {r.name for r in program.rules_for(Hook.PROPOSE)}
            - program.run_signal_names(Hook.PROPOSE)
        )

    def _accumulate(self, raw: Dict, emitted: Dict, step: int) -> None:
        for sig, val in raw.items():
            st = self.signal_runstats.setdefault(sig, _blank_runstat())
            st["n_eval"] += 1
            if val is _K.TRUE:
                st["n_true"] += 1
                if st["first_true_step"] is None:
                    st["first_true_step"] = step
            elif val is _K.UNKNOWN:
                st["n_unknown"] += 1
        for sig, rep in emitted.items():
            st = self.signal_runstats.setdefault(sig, _blank_runstat())
            st["n_emit"] += 1
            if rep.block_execution:
                st["n_block"] += 1

    # -- the overridden propose step: evaluate counterfactually, commit always ----

    def _check_action_step(self, event, thought, parsed_commands):
        # Tentatively extend H·q with observation="" (propose-time: the action has
        # not executed; a real observation would change the node signature). This
        # mirrors the live monitor exactly.
        build_online_graph_from_trajectory(
            builder=self.graph_builder,
            step_idx=event.step_index,
            thought=thought,
            action=event.command,
            observation="",
            parser=self.parser,
        )
        self.step_counter += 1
        # whole proposed step -> outcome None (pending compound sub-commands too)
        self._mark_current_step_outcome_unknown(event.step_index)

        step_roles = self._collect_step_roles(parsed_commands)
        self._advance_phases(step_roles)
        had_roles = bool(step_roles)
        if had_roles:
            self._dwell_stream.extend(step_roles)

        world = propose_world_from_graph(self.graph_builder.G, self._dwell_stream)
        self.n_action_steps += 1
        if world is None:
            return None

        # (a) raw interpreter verdicts for EVERY propose rule (no emission policy,
        #     no enabled filter) -- the clean detection ledger.
        raw = {v.rule: v.value for v in self.runtime.program.evaluate(world)}

        # (b) emission-policy decision (what a LIVE monitor would surface), incl. the
        #     disabled shadow signals. Mirror the live restrict: dwell signals only
        #     advance on roles-steps. commit=True so once_per_key / escalation state
        #     advances along the (unconditionally committed) timeline.
        restrict = None if had_roles else self._general_step_signals
        reports = self.runtime.evaluate(
            world, commit=True, include_disabled=True, restrict_to=restrict
        )
        emitted = {r.rule_id: r for r in reports}

        self._accumulate(raw, emitted, world.q.step)

        # A submit proposal is the opportunity for the submission signals; their
        # verdicts are already rolled up by ``_accumulate`` above, exactly as online.
        # We additionally snapshot the submit-gated signals' raw verdicts here so the
        # offline rollup can read them at the FINAL submit (this overwrites on each
        # submit, so the last attempt wins) rather than OR-ing across attempts.
        if world.q.kind == "submit":
            self.submitted = True
            self.submit_final_true = {
                s: (raw.get(s) is _K.TRUE) for s in self._submit_signals
            }

        # Unconditional commit: NO rollback even if a report would block.
        return None

    # -- thought-only steps (observe(thought) hook) ------------------------------

    def _check_thought_step(self, event, thought):
        """Mirror the live observe(thought) path, committing unconditionally.

        A thought-only step (the model reasoned without issuing a command) feeds the
        thought-repetition stream exactly as the live monitor does — a "think" node
        plus an MD5 thought hash — so ``thought_oscillation`` is exercised offline
        with the same semantics as online (and rolled up like every other signal).
        """
        self._build_think_node(event.step_index, thought, event.command)
        self.step_counter += 1
        self.thought_history.append(hashlib.md5(thought.encode("utf-8")).hexdigest())
        self.n_thought_steps += 1

        world = thought_world_from_hashes(list(self.thought_history))
        if world is None:
            return None
        raw = {v.rule: v.value for v in self.runtime.program.evaluate(world)}
        reports = self.runtime.evaluate(world, commit=True, include_disabled=True)
        emitted = {r.rule_id: r for r in reports}
        self._accumulate(raw, emitted, world.q.step)
        return None

    # observe_result is inherited from DriftMonitor: it fills each committed action
    # node's recorded outcome via buildGraph.check_command_outcome (the single, fixed
    # outcome binding) and is a no-op for think nodes. The replay drives it in the
    # live order (propose, then observe), so committed-history outcomes are available
    # at each later propose.

    def reset(self) -> None:
        super().reset()
        self.n_action_steps = 0
        self.n_thought_steps = 0
        self.submitted = False
        self.submit_final_true = {}
        self.signal_runstats = {}


def replay_trajectory(traj_path) -> Dict:
    """
    Replay one ``.traj`` file end-to-end and return its detection record.

    The order is exactly the live agent loop: for each recorded step, evaluate the
    proposal (propose / observe(thought) hook, no q observation) and only THEN ingest
    the recorded observation (``observe_result``). Thought-only steps are replayed
    too (``include_thought_steps=True``) so ``thought_oscillation`` is detected.

    Submits are recognized exactly as online — by parsing the action
    (``world.q.kind == "submit"``), never by inspecting the submit's tool feedback.
    Every submit proposal is a finalization proposal: a submission signal fires
    whenever its condition holds at that proposal, just as online. The replay does
    not look ahead to see whether another submit follows, rank submits, or count
    them — it simply records what each signal did.

    Returns ``{"meta": {...}}`` where ``meta`` carries the trajectory size
    (``n_steps`` action steps, ``n_thought_steps`` thought-only steps), whether the run
    ever submitted (``submitted`` — the opportunity for the submission signals), and the
    per-run, per-signal rollup (``meta["signals"]``) over every evaluated proposal. The
    rollup is the single detection record: for each signal it holds how often it was
    evaluated, fired (``n_true``), was unknown, would emit, would block, and where it
    first fired — everything the analysis consumes.
    """
    mon = ReplayMonitor()
    mon.reset()
    try:  # ActionExtractor loads+parses the JSON in its constructor, so guard both
        ex = ActionExtractor(str(traj_path))
        steps = list(ex.extract_actions(include_thought_steps=True))
    except Exception as exc:  # malformed / unreadable trajectory
        return {"meta": {"error": f"{type(exc).__name__}: {exc}", "n_steps": 0}}

    for event, thought, observation in steps:
        mon.check_step_pre_emptively(event, thought=thought)
        mon.observe_result(observation)

    return {
        "meta": {
            "n_steps": mon.n_action_steps,
            "n_thought_steps": mon.n_thought_steps,
            "submitted": mon.submitted,
            "signals": mon.signal_runstats,
        },
    }
