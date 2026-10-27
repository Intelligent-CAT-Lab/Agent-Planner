"""
GuardRuntime: the single generic evaluation path from a `World` to ordered,
rendered :class:`~plan_monitor.gl_guard.advice.SignalReport` objects.

This is the "query engine run-loop": it ties together the three decoupled pieces
— the declarative program (`.glg`), the advice/emission registry (JSON), and the
transactional emission state — so that **adding a rule is adding data, not code**:

    program  = GuardProgram.load("liveplan.glg", "liveplan.config.json")
    registry = AdviceRegistry.load("liveplan.advice.json")
    runtime  = GuardRuntime(program, registry)

    reports = runtime.evaluate(world)         # committed hook (observe)
    pre     = runtime.evaluate(world, commit=False)   # tentative (propose) pre-check

Two properties make this faithful to the legacy monitor:

  * **Separation of detection and emission.** The interpreter decides *truth*;
    the registry's emission policy decides *fire timing* (per-key once, every θ,
    cooldown, max-per-pattern). Nothing stateful lives in the DSL.
  * **Transactional evaluation.** ``commit=False`` snapshots the emission state,
    evaluates, and restores it — exactly as ``check_step_pre_emptively`` deep-
    copies and rolls back the legacy rule state for a tentative proposal.
"""
from __future__ import annotations

from typing import List, Optional

from . import ast
from .advice import AdviceRegistry, SignalReport
from .config import Config
from .engine import GuardProgram
from .emission import EmissionState
from .interpreter import evaluate as eval_rule
from .kleene import Kleene
from .model import World


class GuardRuntime:
    def __init__(
        self,
        program: GuardProgram,
        registry: AdviceRegistry,
        state: Optional[EmissionState] = None,
    ):
        self.program = program
        self.registry = registry
        self.state = state or EmissionState()

    # -- public API --------------------------------------------------------------

    def evaluate(self, world: World, *, commit: bool = True,
                 include_disabled: bool = False,
                 restrict_to: Optional[set] = None) -> List[SignalReport]:
        """
        Evaluate every rule declared on ``world.hook`` and return the reports that
        fire *and* pass their emission policy, ordered by descending priority.

        ``commit=False`` runs the whole pass transactionally (emission counters are
        snapshotted and restored), for a side-effect-free tentative pre-check.
        ``include_disabled=True`` also returns shadow (not-yet-enabled) signals —
        used for differential logging, never for agent-facing output.
        ``restrict_to`` (a set of signal names) limits evaluation to those signals,
        so the caller can mirror the legacy monitor's control flow, which only
        evaluates the dwell/view/plan rules on steps that yield a phase role and
        evaluates oscillation on every step.
        """
        snap = self.state.snapshot() if not commit else None
        try:
            return self._evaluate(world, include_disabled, restrict_to)
        finally:
            if snap is not None:
                self.state.restore(snap)

    # -- internals ---------------------------------------------------------------

    def _evaluate(self, world: World, include_disabled: bool,
                  restrict_to: Optional[set]) -> List[SignalReport]:
        reports: List[SignalReport] = []
        for rule in self.program.rules_for(world.hook):
            if restrict_to is not None and rule.name not in restrict_to:
                continue

            entry = self.registry.get(rule.name)
            if entry is None:
                continue  # a rule with no advice entry is detection-only; skip surfacing

            # A disabled signal is fully inert in production: not evaluated, no
            # emission state touched. In shadow mode (include_disabled) it is
            # evaluated so differential logging sees the would-be timeline.
            if not entry.enabled and not include_disabled:
                continue

            verdict = eval_rule(rule, world, self.program.config)
            if verdict is Kleene.UNKNOWN:
                continue  # abstain on unknown: no emit, and leave emission state untouched

            # Consult the emission policy for both TRUE and FALSE verdicts so
            # run-length policies (every_n, on_rising_edge) can reset on a break.
            is_true = verdict is Kleene.TRUE
            key = self._emission_key(entry.key, world, rule)
            decision = entry.policy.decide(self.state.cell(rule.name, key), world.q.step, is_true)
            if not decision.emit:
                continue

            reports.append(self._render(rule, entry, decision.message_variant, world))

        reports.sort(key=lambda r: -r.priority)
        return reports

    def _render(self, rule: ast.Rule, entry, variant, world: World) -> SignalReport:
        q = world.q
        variables = {
            "phase": q.phase if q.phase is not None else "general",
            "action": q.full_action or (q.key or ""),
            "command": q.full_action or (q.key or ""),
            "step": q.step,
            "threshold": self._threshold(rule),
        }
        message = entry.render(variant, variables)
        return SignalReport(
            rule_id=rule.name,
            message=message,
            block_execution=entry.block_execution,
            step_index=q.step,
            priority=entry.priority,
            metadata={
                "hook": world.hook.value,
                "phase": variables["phase"],
                "variant": variant,
                "enabled": entry.enabled,
            },
        )

    # -- emission keys & threshold introspection --------------------------------

    def _emission_key(self, kind: str, world: World, rule: ast.Rule) -> str:
        q = world.q
        if kind == "signal":
            return ""
        if kind == "q.key":
            return q.key or ""
        if kind == "q.phase":
            return q.phase if q.phase is not None else "general"
        if kind == "motif":
            return self._loop_key(rule, world)
        raise ValueError(f"unknown emission key kind {kind!r}")

    def _loop_key(self, rule: ast.Rule, world: World) -> str:
        """
        A rotation-invariant identity for the loop a `repeat`/`cycle` rule matched.

        The oscillation rule desugars to a disjunction of `repeat`s over periods
        1..K. We find the *smallest* period whose last two blocks are equal and
        key by the set of nodes in that block, so A-B-A-B and B-A-B-A map to the
        same loop and warnings stay bounded per loop (as the legacy per-pattern
        counter does), rather than alternating by last action.
        """
        repeats = _collect(rule.body, ast.Repeat)
        if not repeats:
            return ""
        stream = list(world.repetition_stream(repeats[0].channel))
        lengths = sorted({self.program.config.resolve_int(r.length) for r in repeats})
        for m in lengths:
            if len(stream) >= 2 * m and stream[-m:] == stream[-2 * m:-m]:
                block = stream[-m:]
                if any(x is None for x in block):
                    continue
                return "cycle:" + "|".join(sorted(str(x) for x in block))
        # No period held (e.g. the match was unknown-valued); fall back to the tail.
        return "tail:" + "|".join(str(x) for x in stream[-max(lengths):])

    def _threshold(self, rule: ast.Rule) -> Optional[int]:
        """Best-effort 'the' threshold of a rule, for the ``{threshold}`` placeholder."""
        run = _find(rule.body, ast.Run)
        if run is not None:
            return self.program.config.resolve_int(run.k)
        rep = _find(rule.body, ast.Repeat)
        if rep is not None:
            return self.program.config.resolve_int(rep.times)
        cnt = _find(rule.body, ast.Count)
        if cnt is not None:
            return self.program.config.resolve_int(cnt.k)
        return None

    def blocking_signal_ids(self):
        """Names of the signals whose advice entry declares a blocking intervention."""
        return {sid for sid, e in self.registry.entries.items() if e.block_execution}

    def rollback_on_block_ids(self):
        """
        Blocking signals whose emission is rolled back when a proposal is blocked.

        A blocked action never executes, so a blocking signal's emission is
        normally undone (the detected pattern isn't real yet — e.g. oscillation).
        Signals flagged ``persist_on_block`` are excluded: their emission survives
        the rollback, mirroring the legacy monitor, which keeps plan_compliance's
        per-violation-type threshold counts across a block.
        """
        return {sid for sid, e in self.registry.entries.items()
                if e.block_execution and not e.persist_on_block}

    def rollback_blocking(self, snapshot) -> None:
        """
        Restore the emission state of the roll-back-on-block signals to ``snapshot``.

        Call this when the current proposal was *blocked* (so its action never
        committed): those signals' emission must be rolled back — exactly as the
        legacy monitor rolls back its blocking-rule state — while non-blocking
        signals, and ``persist_on_block`` signals, keep the state they advanced.
        """
        self.state.restore_signals(snapshot, self.rollback_on_block_ids())

    def reset(self) -> None:
        self.state.reset()

    @classmethod
    def load(cls, spec_path, config_path, advice_path) -> "GuardRuntime":
        program = GuardProgram.load(spec_path, config_path)
        registry = AdviceRegistry.load(advice_path)
        return cls(program, registry)


def _collect(node, node_type):
    """All descendants of ``node`` of ``node_type`` (pre-order)."""
    found = []
    if isinstance(node, node_type):
        found.append(node)
    if isinstance(node, ast.Not):
        found += _collect(node.operand, node_type)
    elif isinstance(node, (ast.And, ast.Or)):
        for op in node.operands:
            found += _collect(op, node_type)
    elif isinstance(node, (ast.Exists, ast.Count)):
        found += _collect(node.body, node_type)
    return found


def _find(node, node_type):
    """Return the first descendant of ``node`` of ``node_type`` (pre-order), or None."""
    found = _collect(node, node_type)
    return found[0] if found else None
