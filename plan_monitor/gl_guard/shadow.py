"""
Shadow-mode differential harness: replay trajectories and diff GL-Guard vs the
legacy LIVEPLAN monitor at every step.

This is gate **G2** of the binding plan. It drives the real
:class:`~plan_monitor.monitor.StatefulPhaseMonitor` exactly as the existing
`scan_rule_triggers` scanner does (via ``check_step_pre_emptively``), and at each
step builds a GL-Guard :class:`World` **from the monitor's own Graphectory and
``role_history``** — so both systems observe the identical representation. It then
compares which signal *categories* fire at each step.

Design properties that keep the comparison honest and cheap:

  * **Legacy is the oracle for state.** Both systems advance on the legacy monitor's
    block decision, so their committed prefixes stay identical and the diff
    isolates *detection/emission* differences rather than path divergence.
  * **No second graph.** For the common (non-blocked) step the binder reads the
    monitor's live graph directly; only on a *blocked* step (which the monitor
    rolls back) does it deep-copy the builder once to reconstruct the tentative
    ``H·q`` view. Overhead is therefore ~one extra occurrence pass per step —
    comparable to the legacy oscillation detector's own exec-path scan.
  * **Emission mirrors legacy rollback.** Blocking signals' emission is rolled back
    on a blocked step (the action never committed); non-blocking signals persist.

Signal names mirror the legacy rule IDs, so the comparison is almost an identity
map (the only normalization strips the legacy emission suffixes, e.g.
``oscillation_self_loop`` → ``oscillation``). Categories split into:

  * **exact** — ``dwell_*``: GL-Guard reproduces the legacy dwell counter
    step-for-step (see ``_dwell_stream`` below); a discrepancy here is a real bug.
  * **known-difference** — divergences here are expected and reported, not asserted:
      - ``oscillation`` — strict periodic motif vs the legacy non-periodic cycle
        counter; and bounded escalation vs legacy's unbounded re-firing — GL-Guard
        warns per motif up to the ``max_repeats`` terminal (a non-blocking "stop or
        submit"), then goes quiet, whereas the legacy detector rolls its counter
        back on every block and re-fires indefinitely. Sustained loops therefore
        show up as ``legacy_only`` steps after GL-Guard has bounded the motif;
      - ``thought_oscillation`` — strict tail vs the legacy windowed count;
      - ``plan_compliance`` — memoryless decomposition vs the legacy stateful plan
        automaton;
      - ``repeated_view`` — GL-Guard keys a revisit by the merged *graph node*
        (the "location"), while the legacy rule keys by the full trajectory
        *command string*. These agree for simple commands and diverge only on
        compound commands where a view sub-action (e.g. a trailing ``nl``/``grep``)
        recurs under a different full command. The two identities cannot be
        unified: ``oscillation`` needs node-level merging, legacy ``repeated_view``
        needs full-command distinction.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from plan_monitor.phases import ActionEvent

from .adapters import propose_world_from_graph, thought_world_from_hashes
from .advice import AdviceRegistry
from .engine import GuardProgram
from .model import Hook
from .runtime import GuardRuntime

_SPEC_DIR = Path(__file__).resolve().parent / "specs"

# --------------------------------------------------------------------------- #
# Category normalization. Names already match the legacy rule IDs; we only need
# to collapse the legacy emission suffixes and the plan-compliance decomposition.
# --------------------------------------------------------------------------- #

EXACT_CATEGORIES = frozenset({
    "dwell_L_navigate", "dwell_L_reproduce", "dwell_P", "dwell_V",
})
KNOWN_DIFFERENCE_CATEGORIES = frozenset({
    "oscillation", "thought_oscillation", "plan_compliance", "repeated_view",
})
ALL_CATEGORIES = EXACT_CATEGORIES | KNOWN_DIFFERENCE_CATEGORIES


def normalize(rule_or_signal_id: str) -> str:
    """Collapse legacy emission variants / plan decompositions to a canonical name."""
    rid = rule_or_signal_id
    # thought_oscillation must be checked before the oscillation prefix.
    if rid.startswith("thought_oscillation"):
        return "thought_oscillation"
    if rid.startswith("oscillation"):
        return "oscillation"
    if rid.startswith("plan_compliance"):
        return "plan_compliance"
    if rid.startswith("dwell_L_navigate"):
        return "dwell_L_navigate"
    if rid.startswith("dwell_L_reproduce"):
        return "dwell_L_reproduce"
    if rid.startswith("dwell_P"):
        return "dwell_P"
    if rid.startswith("dwell_V"):
        return "dwell_V"
    if rid.startswith("repeated_view"):
        return "repeated_view"
    return rid


# --------------------------------------------------------------------------- #
# Per-step and aggregate results.
# --------------------------------------------------------------------------- #


@dataclass
class StepDiff:
    step_index: int
    blocked: bool
    legacy: Set[str]            # legacy categories fired this step
    glguard: Set[str]          # GL-Guard categories fired this step

    @property
    def agreements(self) -> Set[str]:
        return self.legacy & self.glguard

    @property
    def legacy_only(self) -> Set[str]:
        return self.legacy - self.glguard

    @property
    def glguard_only(self) -> Set[str]:
        return self.glguard - self.legacy


@dataclass
class CategoryStats:
    category: str
    agree: int = 0
    legacy_only: int = 0
    glguard_only: int = 0

    @property
    def total(self) -> int:
        return self.agree + self.legacy_only + self.glguard_only

    @property
    def disagreements(self) -> int:
        return self.legacy_only + self.glguard_only


@dataclass
class ShadowReport:
    steps: int = 0
    per_category: Dict[str, CategoryStats] = field(default_factory=dict)
    # steps where an *exact* category disagreed (these are potential bugs)
    exact_discrepancies: List[Tuple[int, str, str]] = field(default_factory=list)

    def cat(self, name: str) -> CategoryStats:
        return self.per_category.setdefault(name, CategoryStats(name))

    def record(self, diff: StepDiff) -> None:
        self.steps += 1
        for c in diff.agreements:
            self.cat(c).agree += 1
        for c in diff.legacy_only:
            self.cat(c).legacy_only += 1
            if c in EXACT_CATEGORIES:
                self.exact_discrepancies.append((diff.step_index, c, "legacy_only"))
        for c in diff.glguard_only:
            self.cat(c).glguard_only += 1
            if c in EXACT_CATEGORIES:
                self.exact_discrepancies.append((diff.step_index, c, "glguard_only"))

    @property
    def exact_agreement(self) -> bool:
        return not self.exact_discrepancies

    def summary(self) -> str:
        lines = [f"steps: {self.steps}", ""]
        header = f"{'category':24} {'agree':>6} {'legacy_only':>12} {'gl_only':>8}  kind"
        lines += [header, "-" * len(header)]
        for cat in sorted(self.per_category, key=lambda c: (c not in EXACT_CATEGORIES, c)):
            s = self.per_category[cat]
            kind = "exact" if cat in EXACT_CATEGORIES else "known-diff"
            lines.append(f"{cat:24} {s.agree:>6} {s.legacy_only:>12} {s.glguard_only:>8}  {kind}")
        lines.append("")
        if self.exact_agreement:
            lines.append("EXACT categories: full agreement ✓")
        else:
            lines.append(f"EXACT categories: {len(self.exact_discrepancies)} discrepancy(ies) ✗")
            for step, cat, who in self.exact_discrepancies[:20]:
                lines.append(f"  step {step}: {cat} ({who})")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The differ.
# --------------------------------------------------------------------------- #


def _md5(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


class ShadowDiffer:
    """Drives one legacy monitor + GL-Guard runtime over a single trajectory."""

    def __init__(self, monitor, runtime: GuardRuntime):
        self.monitor = monitor
        self.runtime = runtime
        # Persistent dwell phase stream: the exact sequence the legacy dwell
        # counter sees. Every roles-step contributes its roles (committed *and*
        # blocked — the monitor preserves dwell state across a block rollback —
        # including within-step transitions); general-only steps contribute
        # nothing (the monitor skips dwell on them). `run` is evaluated over this
        # stream, not over the rolled-back role_history.
        self._dwell_stream: List[str] = []
        # Signals eligible on a general-only step: everything except the run-based
        # (dwell) rules — oscillation plus the submit-triggered plan-compliance
        # checks, which the legacy monitor also evaluates on general steps.
        self._general_step_signals = (
            {r.name for r in runtime.program.rules_for(Hook.PROPOSE)}
            - runtime.program.run_signal_names(Hook.PROPOSE)
        )

    @classmethod
    def build(cls, rules_config: Optional[str] = None) -> "ShadowDiffer":
        from plan_monitor.monitor import StatefulPhaseMonitor

        monitor = StatefulPhaseMonitor(enable_rules=True, rules_config=rules_config)
        program = GuardProgram.load(_SPEC_DIR / "liveplan.glg", _SPEC_DIR / "liveplan.config.json")
        registry = AdviceRegistry.load(_SPEC_DIR / "liveplan.advice.json")
        return cls(monitor, GuardRuntime(program, registry))

    # -- one step ----------------------------------------------------------------

    def step(self, event: ActionEvent, thought: str = "", observation: str = "") -> StepDiff:
        monitor = self.monitor
        is_thought_step = not (event.command and event.command.strip())

        roles_before = list(monitor.role_history)
        thoughts_before = list(monitor.thought_history)
        step_counter_before = monitor.step_counter

        # 1) Legacy detection (the oracle). This also evolves the monitor's state,
        #    committing on a non-blocking step and rolling back on a blocking one.
        emission_snapshot = self.runtime.state.snapshot()
        result = monitor.check_step_pre_emptively(event, thought=thought)
        legacy_ids = [m.rule_id for m in result.rule_matches] if result else []
        blocked = bool(result and result.should_block_and_refine())

        # 2) Build the GL-Guard world from the monitor's own representation.
        if is_thought_step:
            world = self._thought_world(thought, blocked, thoughts_before)
            restrict = None  # observe(thought) hook: only thought_oscillation
        else:
            graph, step_roles, had_roles = self._action_graph_and_roles(
                event, thought, observation, blocked, roles_before, step_counter_before,
            )
            if had_roles:
                self._dwell_stream.extend(step_roles)   # persistent, matches legacy dwell
            world = propose_world_from_graph(graph, self._dwell_stream)
            # Mirror the monitor's control flow: a general-only step evaluates the
            # non-dwell signals (oscillation + the submit-triggered plan-compliance
            # checks) and skips the run-based dwell rules, keeping those emission
            # counters in lock-step.
            restrict = None if had_roles else self._general_step_signals

        gl_reports = self.runtime.evaluate(
            world, commit=True, include_disabled=True, restrict_to=restrict,
        ) if world else []
        gl_ids = [r.rule_id for r in gl_reports]

        # 3) Mirror the legacy block rollback on GL-Guard emission state.
        if blocked:
            self.runtime.rollback_blocking(emission_snapshot)

        return StepDiff(
            step_index=event.step_index,
            blocked=blocked,
            legacy={normalize(r) for r in legacy_ids},
            glguard={normalize(s) for s in gl_ids},
        )

    def _thought_world(self, thought, blocked, thoughts_before):
        if not blocked:
            thoughts_withq = list(self.monitor.thought_history)   # includes the new hash
        else:
            thoughts_withq = thoughts_before + [_md5(thought)]    # monitor popped it on rollback
        return thought_world_from_hashes(thoughts_withq)

    def _action_graph_and_roles(self, event, thought, observation, blocked,
                                roles_before, step_counter_before):
        """Returns ``(graph, step_roles, had_roles)`` for an action step's tentative H·q."""
        monitor = self.monitor
        if not blocked:
            graph = monitor.graph_builder.G                       # already contains q
            step_roles = list(monitor.role_history)[len(roles_before):]
        else:
            # The monitor rolled back; reconstruct the tentative H·q on a clone.
            # Build with observation="" to match check_step_pre_emptively exactly:
            # at propose time there is no observation yet, and the node signature
            # includes an observation-derived edit_status, so a non-empty
            # observation here would change node identity and desync oscillation.
            clone = copy.deepcopy(monitor.graph_builder)
            from plan_monitor.buildGraph import build_online_graph_from_trajectory
            build_online_graph_from_trajectory(
                builder=clone, step_idx=step_counter_before,
                thought=thought, action=event.command,
                observation="", parser=monitor.parser,
            )
            graph = clone.G
            step_roles = self._reconstruct_step_roles(event.command, roles_before)
        return graph, step_roles, (len(step_roles) > 0)

    def _reconstruct_step_roles(self, command: str, roles_before: List[str]) -> List[str]:
        """Recompute a blocked step's collected roles, mirroring the monitor's STEP 1."""
        from plan_monitor.mapLang import get_action_role

        parsed = self.monitor.parser.parse(command)
        created_tests = set(self.monitor.created_tests)
        created_dynamic = set(self.monitor.created_dynamic_suites)
        step_roles: List[str] = []
        last: Optional[str] = None
        for cmd in parsed:
            role = get_action_role(
                tool=cmd.get("tool"), subcommand=cmd.get("subcommand"),
                command=cmd.get("command"), args=cmd.get("args", []),
                flags=cmd.get("flags", {}),
                prev_roles=roles_before, created_tests=created_tests,
                created_dynamic_suites=created_dynamic,
            )
            if role == "general":
                continue
            if role != last:
                step_roles.append(role)
                last = role
        return step_roles


# --------------------------------------------------------------------------- #
# Replay driving.
# --------------------------------------------------------------------------- #


def replay_steps(differ: ShadowDiffer,
                 steps: Iterable[Tuple[ActionEvent, str, str]]) -> ShadowReport:
    """Replay an explicit sequence of ``(event, thought, observation)`` steps."""
    report = ShadowReport()
    for event, thought, observation in steps:
        report.record(differ.step(event, thought, observation))
    return report


def replay_trajectory(traj_path, agent: str = "mini-swe-agent",
                      rules_config: Optional[str] = None) -> ShadowReport:
    """Replay one trajectory file (same extractors as `scan_rule_triggers`)."""
    from plan_monitor.simulator import mini_extractor, swe_extractor

    if agent == "swe-agent":
        extractor = swe_extractor.ActionExtractor(traj_path)
    else:
        extractor = mini_extractor.ActionExtractor(traj_path)

    differ = ShadowDiffer.build(rules_config=rules_config)
    return replay_steps(differ, extractor.extract_actions())


def replay_directory(traj_dir, agent: str = "mini-swe-agent") -> ShadowReport:
    """Replay every trajectory under a directory, aggregating into one report."""
    traj_dir = Path(traj_dir)
    pattern = "**/*.traj" if agent == "swe-agent" else "**/*.traj.json"
    aggregate = ShadowReport()
    for traj_file in sorted(traj_dir.glob(pattern)):
        try:
            report = replay_trajectory(traj_file, agent=agent)
        except Exception as exc:  # keep going across a dataset
            print(f"  skip {traj_file.name}: {exc}")
            continue
        aggregate.steps += report.steps
        for cat, stats in report.per_category.items():
            agg = aggregate.cat(cat)
            agg.agree += stats.agree
            agg.legacy_only += stats.legacy_only
            agg.glguard_only += stats.glguard_only
        aggregate.exact_discrepancies.extend(report.exact_discrepancies)
    return aggregate


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="gl_guard.shadow",
        description="Shadow differential test: GL-Guard vs legacy monitor over trajectories.",
    )
    parser.add_argument("path", help="a trajectory file or a directory of them")
    parser.add_argument("--agent", default="mini-swe-agent",
                        choices=["mini-swe-agent", "swe-agent"])
    args = parser.parse_args(argv)

    path = Path(args.path)
    report = replay_directory(path, agent=args.agent) if path.is_dir() \
        else replay_trajectory(path, agent=args.agent)
    print(report.summary())
    return 0 if report.exact_agreement else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
