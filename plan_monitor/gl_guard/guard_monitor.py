"""
GuardMonitor: a drop-in :class:`~plan_monitor.monitor.StatefulPhaseMonitor`
whose rule engine is the GL-Guard DSL instead of the hand-written
:class:`~plan_monitor.rules.RuleEngine`.

Design goals (see ``docs/GL_Guard_Binding_Design.md``):

  * **Zero changes to the legacy monitor.** ``GuardMonitor`` *subclasses*
    ``StatefulPhaseMonitor`` and reuses its ``__init__`` (so the ``CommandParser``
    gets the identical tool configs), its ``GraphBuilder``, its role/phase
    bookkeeping, ``thought_history``, ``step_counter`` and every getter the
    refiner reads. Only :meth:`check_step_pre_emptively` is overridden.

  * **Same representation GL-Guard was validated against.** Each step extends the
    *same* Graphectory the legacy monitor would build (same node signatures,
    phases, exec-path), then a GL-Guard :class:`World` is read directly from it
    via :mod:`plan_monitor.gl_guard.adapters`. There is no second graph and no
    re-classification, so the dwell/oscillation/view streams are byte-identical
    to the legacy detectors' — the property the shadow differential harness
    verifies step-for-step on real trajectories.

  * **Drop-in contract.** The method returns a genuine
    :class:`~plan_monitor.phases.MonitorResult` of genuine
    :class:`~plan_monitor.rules.RuleMatch` objects (built from each fired
    :class:`~plan_monitor.gl_guard.advice.SignalReport`), so the agent's
    ``get_all_messages`` / ``should_block_and_refine`` / ``rule_matches`` contract
    and the refiner's ``build_state_summary_from_monitor`` work unchanged.

  * **GL-Guard owns the block decision.** The transaction mirrors the legacy one
    — tentatively extend ``H·q`` with ``observation=""``, evaluate, then commit on
    a non-blocking step or roll the extension back on a blocking one — but the
    *verdict* and *emission timing* come from the DSL program + advice registry.
    The persistent dwell stream and non-blocking emission state survive a block
    (as the legacy monitor preserves dwell/view state across a rollback); blocking
    signals' emission is rolled back because the action never executed.

Overhead is comparable to (slightly below) the legacy monitor's: one
``deepcopy`` of the graph per step, and — unlike the legacy path — no deepcopy of
a rules dict.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import List, Optional

from plan_monitor.buildGraph import build_online_graph_from_trajectory
from plan_monitor.commandParser import CommandParser
from plan_monitor.mapLang import get_action_role
from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.phases import ActionEvent, MonitorResult, Phase
from plan_monitor.rules import RuleMatch

from .adapters import propose_world_from_graph, thought_world_from_hashes
from .advice import AdviceRegistry, SignalReport
from .engine import GuardProgram
from .model import Hook
from .runtime import GuardRuntime

_SPEC_DIR = Path(__file__).resolve().parent / "specs"


class GuardMonitor(StatefulPhaseMonitor):
    """A ``StatefulPhaseMonitor`` driven by a GL-Guard specification."""

    def __init__(
        self,
        parser: Optional[CommandParser] = None,
        enable_rules: bool = True,
        rules_config: Optional[str] = None,
        *,
        spec_path=None,
        config_path=None,
        advice_path=None,
    ) -> None:
        # Reuse the legacy setup verbatim: this builds the GraphBuilder and seeds
        # the CommandParser with the selected config's tool YAMLs, so graph
        # construction is identical to the legacy monitor's. The legacy
        # ``RuleEngine`` is constructed (it carries the tool config) but never
        # consulted — this class overrides every method that would use it.
        super().__init__(parser=parser, enable_rules=enable_rules, rules_config=rules_config)

        program = GuardProgram.load(
            spec_path or _SPEC_DIR / "liveplan.glg",
            config_path or _SPEC_DIR / "liveplan.config.json",
        )
        registry = AdviceRegistry.load(advice_path or _SPEC_DIR / "liveplan.advice.json")
        self.runtime = GuardRuntime(program, registry)

        # Signals to evaluate on a general-only step (no phase role). The legacy
        # monitor checks oscillation and plan-compliance ending-flags on such a
        # step but skips the phase-dwell rules; we mirror that by evaluating every
        # propose signal except the run-based (dwell) ones, whose every-N emission
        # must advance only on steps that actually extend the phase stream.
        self._general_step_signals = (
            {r.name for r in program.rules_for(Hook.PROPOSE)}
            - program.run_signal_names(Hook.PROPOSE)
        )

        # The step-level phase stream `run` (dwell) reads. It accumulates every
        # roles-step's collected roles — committed *and* blocked — mirroring the
        # legacy dwell counter, which persists across a block rollback. It is
        # deliberately *not* part of the per-step snapshot (never rolled back).
        self._dwell_stream: List[str] = []

        # Best-effort record of the latest refined plan (see update_intended_plan).
        self._intended_plan: Optional[List[str]] = None

    # -- the single overridden hook ---------------------------------------------

    def check_step_pre_emptively(
        self, event: ActionEvent, thought: str = ""
    ) -> Optional[MonitorResult]:
        """GL-Guard evaluation of one proposed step; see the class docstring."""
        parsed_commands = self.parser.parse(event.command)
        if not parsed_commands:
            return self._check_thought_step(event, thought)
        return self._check_action_step(event, thought, parsed_commands)

    # -- action steps (propose hook) --------------------------------------------

    def _check_action_step(self, event, thought, parsed_commands) -> Optional[MonitorResult]:
        backup = self._snapshot()

        # Tentatively extend the Graphectory with H·q. observation="" because at
        # propose time the action has not executed: the node signature folds in an
        # observation-derived edit_status, so a non-empty observation here would
        # change node identity and desync oscillation from the legacy detector.
        build_online_graph_from_trajectory(
            builder=self.graph_builder,
            step_idx=self.step_counter,
            thought=thought,
            action=event.command,
            observation="",
            parser=self.parser,
        )
        self.step_counter += 1

        # Mirror the legacy STEP 1/STEP 3: collect this step's non-general roles
        # (consecutive-deduped) and advance the phase bookkeeping the refiner reads.
        step_roles = self._collect_step_roles(parsed_commands)
        self._advance_phases(step_roles)
        had_roles = bool(step_roles)
        if had_roles:
            self._dwell_stream.extend(step_roles)

        world = propose_world_from_graph(self.graph_builder.G, self._dwell_stream)
        # Mirror the legacy control flow: on a roles-step every signal is eligible;
        # on a general-only step only the non-dwell signals are (oscillation and
        # the submit-triggered plan-compliance checks), keeping the dwell emission
        # counters in lock-step with the legacy monitor.
        restrict = None if had_roles else self._general_step_signals

        emission_snapshot = self.runtime.state.snapshot()
        reports = self.runtime.evaluate(world, commit=True, restrict_to=restrict) if world else []

        return self._finish(reports, backup, emission_snapshot)

    # -- thought steps (observe(thought) hook) ----------------------------------

    def _check_thought_step(self, event, thought) -> Optional[MonitorResult]:
        backup = self._snapshot()

        # Mirror the legacy empty-action path: a "think" node plus an MD5 thought
        # hash feed the thought-repetition stream.
        self._build_think_node(self.step_counter, thought, event.command)
        self.step_counter += 1
        self.thought_history.append(hashlib.md5(thought.encode("utf-8")).hexdigest())

        world = thought_world_from_hashes(list(self.thought_history))
        emission_snapshot = self.runtime.state.snapshot()
        reports = self.runtime.evaluate(world, commit=True) if world else []

        return self._finish(reports, backup, emission_snapshot)

    # -- shared commit / rollback / result --------------------------------------

    def _finish(self, reports, backup, emission_snapshot) -> Optional[MonitorResult]:
        should_block = any(r.block_execution for r in reports)
        if should_block:
            # The action never executed: undo the tentative graph extension and
            # phase/role advance. The persistent dwell stream and non-blocking
            # emission state are kept; blocking signals' emission is rolled back.
            self._restore(backup)
            self.runtime.rollback_blocking(emission_snapshot)

        if not reports:
            return None

        rule_matches = [RuleMatch(**r.to_rule_match_kwargs()) for r in reports]
        if should_block:
            current_phase, previous_phase = backup["current_phase"], backup["previous_phase"]
        else:
            current_phase, previous_phase = self.current_phase, self.previous_phase
        return MonitorResult(
            current_phase=current_phase,
            phase_changed=False,
            category_changed=False,
            previous_phase=previous_phase,
            rule_matches=rule_matches,
        )

    # -- legacy STEP 1/STEP 3 mirrored verbatim ---------------------------------

    def _collect_step_roles(self, parsed_commands) -> List[str]:
        """The step's non-general roles, consecutive-deduped (legacy STEP 1)."""
        step_roles: List[str] = []
        last_role: Optional[str] = None
        for cmd in parsed_commands:
            role = get_action_role(
                tool=cmd.get("tool"),
                subcommand=cmd.get("subcommand"),
                command=cmd.get("command"),
                args=cmd.get("args", []),
                flags=cmd.get("flags", {}),
                prev_roles=self.role_history,
                created_tests=self.created_tests,
                created_dynamic_suites=self.created_dynamic_suites,
            )
            if role == "general":
                continue
            if role != last_role:
                step_roles.append(role)
                last_role = role
        return step_roles

    def _advance_phases(self, step_roles) -> None:
        """Append roles and advance current/previous phase (legacy STEP 3)."""
        for role in step_roles:
            self.role_history.append(role)
            new_phase = Phase(role)
            if self.current_phase is None:
                self.current_phase = new_phase
            elif new_phase != self.current_phase:
                self.previous_phase = self.current_phase
                self.current_phase = new_phase

    # -- transactional state snapshot / restore ---------------------------------

    def _snapshot(self) -> dict:
        """Capture the mutable state the legacy monitor backs up before a step."""
        gb = self.graph_builder
        return {
            "G": copy.deepcopy(gb.G),
            "previous_node": gb.previous_node,
            "node_signature_to_key": copy.deepcopy(gb.node_signature_to_key),
            "localization_nodes": list(gb.localization_nodes),
            "gb_prev_phases": set(gb.prev_phases),
            "gb_created_tests": set(gb.created_tests),
            "role_history": list(self.role_history),
            "step_counter": self.step_counter,
            "current_phase": self.current_phase,
            "previous_phase": self.previous_phase,
            "created_tests": set(self.created_tests),
            "created_dynamic_suites": set(self.created_dynamic_suites),
            "thought_history": list(self.thought_history),
        }

    def _restore(self, s: dict) -> None:
        gb = self.graph_builder
        gb.G = s["G"]
        gb.previous_node = s["previous_node"]
        gb.node_signature_to_key = s["node_signature_to_key"]
        gb.localization_nodes = s["localization_nodes"]
        gb.prev_phases = s["gb_prev_phases"]
        gb.created_tests = s["gb_created_tests"]
        self.role_history = s["role_history"]
        self.step_counter = s["step_counter"]
        self.current_phase = s["current_phase"]
        self.previous_phase = s["previous_phase"]
        self.created_tests = s["created_tests"]
        self.created_dynamic_suites = s["created_dynamic_suites"]
        self.thought_history = s["thought_history"]

    # -- lifecycle / parity -----------------------------------------------------

    def reset(self) -> None:
        super().reset()
        self.runtime.reset()
        self._dwell_stream = []
        self._intended_plan = None

    def update_intended_plan(self, refined_plan_phases: List[str]) -> bool:
        """
        Parity shim for the refiner's post-refinement plan rewrite.

        The legacy monitor rewrites its stateful ``PlanComplianceRule`` automaton
        here. GL-Guard's plan-compliance signals are a *memoryless* decomposition
        of a fixed L→P→V ordering (and are shadow-disabled by default pending a
        faithful stateful decomposition — see the binding design), so there is no
        dynamic automaton to mutate. We record the refined plan for introspection
        and report success iff a plan was supplied, keeping the agent's call site
        working unchanged.
        """
        if not refined_plan_phases:
            return False
        self._intended_plan = list(refined_plan_phases)
        return True
