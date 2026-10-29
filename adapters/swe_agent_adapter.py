"""SWE-agent binding of the LivePlan :class:`~adapters.adapter.StepInterceptor`.

All of the monitor/refiner logic that used to live inline in
``sweagent/agent/agents.py`` (see the stale reference ``agents_original.py``) is
collected here, behaviorally unchanged. The agent scaffold keeps only a small seam
that constructs an interceptor via :func:`build_interceptor` and delegates each
proposed step to :meth:`LivePlanInterceptor.run_step`.

The interceptor holds a back-reference to its agent and reaches into a small,
documented set of scaffold attributes/methods (the "seam API"):
``agent.handle_action``, ``agent.tools.get_state``, ``agent._env``,
``agent.trajectory``, ``agent._problem_statement``, and ``agent.logger``. The
dependency is strictly one-directional (adapter -> scaffold); the scaffold never
imports concrete LivePlan types.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapter import StepInterceptor
from .trace import InterventionTrace

try:
    from plan_monitor import ActionEvent, StatefulPhaseMonitor

    MONITOR_AVAILABLE = True
except ImportError:  # pragma: no cover
    MONITOR_AVAILABLE = False
    StatefulPhaseMonitor = None  # type: ignore
    ActionEvent = None  # type: ignore

try:
    # GL-Guard engine: a drop-in StatefulPhaseMonitor whose rules come from the
    # declarative DSL specs instead of the hand-written RuleEngine.
    from plan_monitor.gl_guard.guard_monitor import GuardMonitor

    GL_GUARD_AVAILABLE = True
except ImportError:  # pragma: no cover
    GL_GUARD_AVAILABLE = False
    GuardMonitor = None  # type: ignore

try:
    from plan_refiner import PlanRefiner
    from plan_refiner.types import RefinerInput, StateSummary

    REFINER_AVAILABLE = True
except ImportError:  # pragma: no cover
    REFINER_AVAILABLE = False
    PlanRefiner = None  # type: ignore


def build_interceptor(config: Any, agent: Any, *, observe_results: bool = True) -> StepInterceptor | None:
    """Construct the LivePlan interceptor for an agent, or ``None`` if disabled.

    Returns ``None`` when neither the monitor nor the refiner is enabled, so a
    vanilla agent gets ``_interceptor = None`` and behaves exactly like upstream.
    Mirrors the old ``DefaultAgent.from_config`` wiring.

    Args:
        observe_results: Feed each executed action's observation back to the monitor
            (``monitor.observe_result``) so the committed graph node records its real
            outcome. Default True reproduces the root fork. Only gl_guard implements
            the hook (legacy no-ops via the ``hasattr`` guard); it is kept because
            outcome-aware signals (see specs/extra_signals.glg) consume it.
    """
    if not (getattr(config, "enable_monitor", False) or getattr(config, "enable_refiner", False)):
        return None
    return LivePlanInterceptor(config, agent, observe_results=observe_results)


class LivePlanInterceptor(StepInterceptor):
    """Owns the monitor, the refiner, and all intervention state for one agent.

    Three operating modes, selected by config (identical to the inline agent):
      1. monitor enabled, refiner enabled  -> monitor-triggered refiner
      2. monitor enabled, refiner disabled -> monitor only
      3. monitor disabled, refiner enabled -> interval-based refiner (refiner-only)
    """

    def __init__(self, config: Any, agent: Any, *, observe_results: bool = True) -> None:
        self.agent = agent
        self.config = config
        # Feed observations back to the monitor after execution so committed nodes
        # record their real outcome (consumed by outcome-aware gl_guard signals).
        # No-op on the legacy monitor, which has no observe_result hook.
        self.observe_results = observe_results

        # Intervention state (formerly scattered DefaultAgent attributes).
        self.monitor: Any = None
        self.refiner: Any = None
        self.trajectory_data: list[tuple] = []  # (event, thought, observation) tuples for refiner
        self.min_steps_between_refinements: int = 10
        self.last_refinement_step: int = -100
        self.last_refinement_guidance: str | None = None
        self.monitor_triggers_since_refinement: int = 0  # triggers during cooling period
        self.save_monitor_graph: bool = getattr(config, "save_monitor_graph", False)
        self.trace = InterventionTrace()

        # Initialize monitor if enabled and available
        if config.enable_monitor and MONITOR_AVAILABLE:
            if config.monitor_engine == "gl_guard":
                if not GL_GUARD_AVAILABLE:
                    raise ImportError(
                        "monitor_engine='gl_guard' but plan_monitor.gl_guard could not be "
                        "imported; set monitor_engine='legacy' or fix the gl_guard install."
                    )
                monitor_cls = GuardMonitor
            else:
                monitor_cls = StatefulPhaseMonitor
            self.monitor = monitor_cls(
                enable_rules=True,
                rules_config=config.monitor_rules_config,
            )
            agent.logger.info(
                "Plan monitor enabled (engine=%s, rules config=%s)",
                config.monitor_engine,
                config.monitor_rules_config,
            )

        # Initialize refiner if enabled and available
        if config.enable_refiner and REFINER_AVAILABLE:
            if self.monitor:
                agent.logger.info(
                    "Initializing plan refiner (monitor-triggered mode) with config: %s",
                    config.refiner_config_path,
                )
            else:
                agent.logger.info(
                    "Initializing plan refiner (interval-based mode) with config: %s",
                    config.refiner_config_path,
                )

            refiner_model = PlanRefiner.create_model_from_config(config.refiner_config_path)
            agent.logger.info("Refiner model type: %s", type(refiner_model).__name__)

            from plan_refiner.refiner import RefinerConfig

            refiner_config = RefinerConfig(template_path=config.refiner_config_path)
            self.refiner = PlanRefiner(refiner_model, config=refiner_config)

            self.min_steps_between_refinements = PlanRefiner.get_min_steps_from_config(config.refiner_config_path)
            agent.logger.info("Plan refiner enabled with min_steps=%d", self.min_steps_between_refinements)

    # -- lifecycle ------------------------------------------------------------- #

    def reset(self) -> None:
        """Reset per-instance intervention state (called from ``setup``)."""
        self.trajectory_data = []
        self.last_refinement_step = -100
        self.last_refinement_guidance = None
        self.trace.reset()
        self.monitor_triggers_since_refinement = 0

    def on_run_done(self, output_dir: Path) -> None:
        """Save planner history and (optionally) the monitor graph."""
        agent = self.agent
        if self.trace:
            assert agent._problem_statement is not None
            planner_path = self.trace.save(output_dir, agent._problem_statement.id)
            if planner_path:
                agent.logger.info("Planner history saved to %s", planner_path)

        if self.save_monitor_graph and self.monitor:
            try:
                assert agent._problem_statement is not None
                self.monitor.save_graph(str(output_dir), agent._problem_statement.id)
                agent.logger.info("Monitor graph saved to %s", output_dir)
            except Exception as e:
                agent.logger.warning("Failed to save monitor graph: %s", e)

    # -- the step seam --------------------------------------------------------- #

    def run_step(self, step: Any) -> Any:
        """Replace the vanilla ``return self.handle_action(step)``.

        Handles the three configurations:
          1. Monitor enabled, refiner enabled -> monitor-triggered refiner
          2. Monitor enabled, refiner disabled -> monitor only
          3. Monitor disabled, refiner enabled -> interval-based refiner
        """
        agent = self.agent
        step_index = len(agent.trajectory)

        # Configuration 1 & 2: Monitor enabled
        event = None
        if self.monitor is not None:
            event = ActionEvent(step_index=step_index, command=step.action)

            # Track monitor latency
            monitor_start_time = time.time()
            monitor_result = self.monitor.check_step_pre_emptively(event, thought=step.thought)
            monitor_latency_ms = (time.time() - monitor_start_time) * 1000

            if monitor_result is not None:
                messages = monitor_result.get_all_messages()
                if messages:
                    monitor_message = "\n".join(messages)
                    agent.logger.info(f"📋 PLAN MONITOR\n{monitor_message}")
                    monitor_blocked = monitor_result.should_block_and_refine()

                    # Check if refiner is enabled to handle rule triggers
                    if self.refiner:
                        # Refiner handles both blocking and non-blocking cases
                        step = self._call_refiner(
                            monitor_result.rule_matches,
                            monitor_message,
                            is_blocking=monitor_blocked,
                            step=step,
                            event=event,
                            monitor_latency_ms=monitor_latency_ms,
                        )
                        return step
                    else:
                        # No refiner - handle manually with tracking
                        if monitor_blocked:
                            # Just block with monitor message
                            step.extra_info["monitor_message"] = monitor_message
                            step.extra_info["monitor_blocked"] = True

                            # Track monitor intervention
                            self.trace.track(
                                step_index=len(agent.trajectory),
                                planner_type="monitor",
                                content=monitor_message,
                                latency_ms=monitor_latency_ms,
                                usage=None,
                            )

                            agent.logger.warning("Plan monitor blocked action execution")
                            assert agent._env is not None
                            step.observation = ""  # No observation since action wasn't executed
                            step.state = agent.tools.get_state(env=agent._env)
                            return step
                        else:
                            # Execute action and add monitor message (non-blocking)
                            step = agent.handle_action(step)
                            self._observe_monitor_result(step)
                            step.extra_info["monitor_message"] = monitor_message
                            step.extra_info["monitor_blocked"] = False

                            # Track monitor intervention
                            self.trace.track(
                                step_index=len(agent.trajectory),
                                planner_type="monitor",
                                content=monitor_message,
                                latency_ms=monitor_latency_ms,
                                usage=None,
                            )

                            # Store trajectory data for potential future refiner use
                            self.trajectory_data.append((event, step.thought, step.observation))
                            return step

        # No monitor OR no rules triggered - proceed normally
        step = agent.handle_action(step)
        self._observe_monitor_result(step)

        # Store trajectory data for refiner (when monitor enabled but no rules triggered)
        if self.monitor:
            # Reuse the event created earlier (when monitor was checked)
            assert event is not None, "Event should have been created when monitor check was performed"
            self.trajectory_data.append((event, step.thought, step.observation))

        # Configuration 3: Refiner-only mode (monitor disabled, refiner enabled)
        # Store trajectory and call refiner at intervals
        elif self.refiner is not None:
            # Store trajectory data with event object for refiner
            event = ActionEvent(step_index=step_index, command=step.action)
            self.trajectory_data.append((event, step.thought, step.observation))

            # Call refiner at fixed intervals (skip early steps until we have trajectory data)
            if step_index >= self.min_steps_between_refinements:
                steps_since_last = step_index - self.last_refinement_step
                if steps_since_last >= self.min_steps_between_refinements:
                    step = self._call_refiner_interval_based(step, step_index)

        return step

    # -- monitor feedback ------------------------------------------------------ #

    def _observe_monitor_result(self, step: Any) -> None:
        """Feed an executed action's result back to the monitor.

        The monitor checks a step *before* execution, so its graph node for the
        action carries no outcome. Once the action has run we hand the observation
        back (observe(result) hook) so the committed node records its real
        outcome/edit_status — used only to make the next corrective message
        concrete and truthful, never to change which signals fire. A no-op for
        monitors (e.g. the legacy engine) that don't implement the hook; failures
        here must never break the agent loop.
        """
        if not self.observe_results:
            return
        monitor = self.monitor
        if monitor is not None and hasattr(monitor, "observe_result"):
            try:
                monitor.observe_result(step.observation)
            except Exception:
                self.agent.logger.debug("monitor.observe_result failed", exc_info=True)

    # -- refiner --------------------------------------------------------------- #

    def _call_refiner(
        self,
        rule_matches: list,
        monitor_message: str,
        is_blocking: bool,
        step: Any,
        event: Any,
        monitor_latency_ms: float = 0.0,
    ) -> Any:
        """Call plan_refiner for both blocking and non-blocking rule triggers.

        For blocking rules:
        - Don't execute action
        - Don't add assistant message to history
        - Call refiner for guidance

        For non-blocking rules:
        - Execute action first
        - Keep assistant message and observation in history
        - Call refiner for post-hoc guidance
        """
        agent = self.agent
        rule_type = "Blocking" if is_blocking else "Non-blocking"
        step_index = event.step_index
        agent.logger.info(f"[REFINER] {rule_type} rules triggered at step {step_index}")
        agent.logger.info(f"[REFINER] Rules: {[m.rule_id for m in rule_matches]}")

        # For non-blocking rules: execute action first and store trajectory
        if not is_blocking:
            step = agent.handle_action(step)
            self._observe_monitor_result(step)
            # Store trajectory data BEFORE calling refiner
            self.trajectory_data.append((event, step.thought, step.observation))
        else:
            # For blocking rules: set empty observation and current state
            assert agent._env is not None
            step.observation = ""
            step.state = agent.tools.get_state(env=agent._env)

        # Check cooling period BEFORE building state and calling refiner (optimization)
        # Dual condition: trajectory steps AND monitor trigger count
        # - Normal case: trajectory progresses, exits cooling when steps >= threshold
        # - Blocking case: trajectory stuck (rolled back), exits when triggers >= threshold
        steps_since_last = step_index - self.last_refinement_step
        within_cooling_period = (
            steps_since_last < self.min_steps_between_refinements
            and self.monitor_triggers_since_refinement < self.min_steps_between_refinements
        )

        # If within cooling period, just add monitor message without calling refiner LLM
        if within_cooling_period:
            self.monitor_triggers_since_refinement += 1
            step.extra_info["monitor_message"] = monitor_message
            step.extra_info["monitor_blocked"] = is_blocking

            # Track monitor intervention (within cooling period, no refiner call)
            self.trace.track(
                step_index=len(agent.trajectory),
                planner_type="monitor",
                content=monitor_message,
                latency_ms=monitor_latency_ms,
                usage=None,
            )

            agent.logger.info(
                f"[REFINER] Within cooling period ({steps_since_last}/{self.min_steps_between_refinements} steps, "
                f"{self.monitor_triggers_since_refinement}/{self.min_steps_between_refinements} triggers) - monitor message added"
            )
            return step

        # Not in cooling period - perform full refinement
        # Build state summary from monitor (only when actually calling refiner)
        state_summary = PlanRefiner.build_state_summary_from_monitor(
            self.monitor,
            rule_matches=rule_matches,
            exclude_rule_patterns=["plan_compliance"],
        )

        # Build trajectory steps (includes the just-executed step for non-blocking)
        trajectory_steps = PlanRefiner.build_trajectory_steps(self.trajectory_data)
        agent.logger.debug(f"[REFINER] Trajectory steps:\n{trajectory_steps}")
        agent.logger.debug(f"[REFINER] State summary:\n{state_summary}")

        # Get issue description
        assert agent._problem_statement is not None
        issue_description = agent._problem_statement.get_problem_statement()

        # Create refiner input and call refiner with latency tracking
        refiner_input = RefinerInput(
            issue_description=issue_description,
            trajectory=trajectory_steps,
            state_summary=state_summary,
            last_refinement_guidance=self.last_refinement_guidance,
            last_refinement_step=self.last_refinement_step,
        )

        refiner_start_time = time.time()
        refiner_output = self.refiner.refine_plan(
            refiner_input,
            current_step=step_index,
        )
        refiner_latency_ms = (time.time() - refiner_start_time) * 1000
        agent.logger.info(f"[REFINER] Refiner output:\n{refiner_output.raw_response}\n")

        # Prepare message to add to conversation
        message_to_track = monitor_message  # default fallback

        # Add refined plan as user message
        if refiner_output.raw_response:
            if refiner_output.new_plan:
                message_to_track = f"[Plan Refiner Guidance]\n\n{refiner_output.new_plan}"
            else:
                message_to_track = f"[Plan Refiner Guidance]\n\n{refiner_output.raw_response}"

            step.extra_info["refiner_message"] = message_to_track
            agent.logger.info(message_to_track)
            agent.logger.info(f"[REFINER] New plan added to messages")

            # Update the intended plan in the monitor's plan compliance rule
            if refiner_output.refined_plan_phases:
                plan_updated = self.monitor.update_intended_plan(refiner_output.refined_plan_phases)
                if not plan_updated:
                    agent.logger.warning(f"[REFINER] Warning: Failed to update plan in monitor")

        else:
            agent.logger.warning(f"[REFINER] Warning: Refiner returned empty response. Use monitor message only.")
            message_to_track = monitor_message

        # Set the message in step for later adding to history
        step.extra_info["monitor_message"] = message_to_track
        step.extra_info["monitor_blocked"] = is_blocking

        # Track refiner intervention (includes refiner call + output)
        self.trace.track(
            step_index=len(agent.trajectory),
            planner_type="refiner",
            content=message_to_track,
            latency_ms=refiner_latency_ms,
            usage=refiner_output.usage,
            state_summary=asdict(state_summary),
        )

        # Update last refinement step and guidance, reset monitor trigger counter
        self.last_refinement_step = step_index
        self.monitor_triggers_since_refinement = 0
        if refiner_output.new_plan:
            self.last_refinement_guidance = refiner_output.new_plan

        return step

    def _call_refiner_interval_based(self, step: Any, step_index: int) -> Any:
        """Call plan_refiner at fixed intervals (refiner-only mode, monitor disabled)."""
        agent = self.agent
        agent.logger.info(f"[REFINER] Interval-based refinement at step {step_index}")

        # Build trajectory steps from collected data
        trajectory_steps = PlanRefiner.build_trajectory_steps(self.trajectory_data)
        assert agent._problem_statement is not None
        issue_description = agent._problem_statement.get_problem_statement()

        # Create empty state summary (no monitor available)
        state_summary = StateSummary(
            current_phase=None,
            phase_history=[],
            unique_phases=[],
            rule_triggers=[],
            graph_info={},
            step_count=step_index,
        )

        # Build refiner input
        refiner_input = RefinerInput(
            issue_description=issue_description,
            trajectory=trajectory_steps,
            state_summary=state_summary,
            last_refinement_guidance=self.last_refinement_guidance,
            last_refinement_step=self.last_refinement_step,
        )

        # Call refiner
        refiner_start_time = time.time()
        refiner_output = self.refiner.refine_plan(refiner_input, current_step=step_index)
        refiner_latency_ms = (time.time() - refiner_start_time) * 1000
        agent.logger.info(f"[REFINER] Refiner output:\n{refiner_output.raw_response}\n")

        # Format guidance message
        if refiner_output.raw_response:
            if refiner_output.new_plan:
                guidance_message = f"[Plan Refiner Guidance]\n\n{refiner_output.new_plan}"
            else:
                guidance_message = f"[Plan Refiner Guidance]\n\n{refiner_output.raw_response}"
            step.extra_info["refiner_message"] = guidance_message
            agent.logger.info(guidance_message)
        else:
            agent.logger.warning(f"[REFINER] Warning: Refiner returned empty response")
            guidance_message = ""

        # Track intervention (no state summary needed for interval-based)
        self.trace.track(
            step_index=len(agent.trajectory),
            planner_type="refiner",
            content=guidance_message,
            latency_ms=refiner_latency_ms,
            usage=refiner_output.usage,
            state_summary=None,
        )

        # Update last refinement tracking
        self.last_refinement_step = step_index
        if refiner_output.new_plan:
            self.last_refinement_guidance = refiner_output.new_plan

        return step
