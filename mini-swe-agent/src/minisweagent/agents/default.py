"""Basic agent class. See https://mini-swe-agent.com/latest/advanced/control_flow/ for visual explanation."""

import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from jinja2 import StrictUndefined, Template

from minisweagent import Environment, Model

try:
    from plan_monitor import StatefulPhaseMonitor, ActionEvent
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False

try:
    from plan_refiner import PlanRefiner
    from plan_refiner.types import RefinerInput, StateSummary, RefinerTrajectoryStep, RuleTrigger
    REFINER_AVAILABLE = True
except ImportError:
    REFINER_AVAILABLE = False


@dataclass
class AgentConfig:
    # The default settings are the bare minimum to run the agent. Take a look at the config files for improved settings.
    system_template: str = "You are a helpful assistant that can do anything."
    instance_template: str = (
        "Your task: {{task}}. Please reply with a single shell command in triple backticks. "
        "To finish, the first line of the output of the shell command must be 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT'."
    )
    timeout_template: str = (
        "The last command <command>{{action['action']}}</command> timed out and has been killed.\n"
        "The output of the command was:\n <output>\n{{output}}\n</output>\n"
        "Please try another command and make sure to avoid those requiring interactive input."
    )
    format_error_template: str = "Please always provide EXACTLY ONE action in triple backticks."
    action_observation_template: str = "Observation: {{output}}"
    step_limit: int = 0
    cost_limit: float = 3.0
    enable_monitor: bool = False
    monitor_rules_config: str = "default_rules"
    save_monitor_graph: bool = False
    enable_refiner: bool = False
    refiner_config_path: str = "plan_refiner/config/default.yaml"


class NonTerminatingException(Exception):
    """Raised for conditions that can be handled by the agent."""


class FormatError(NonTerminatingException):
    """Raised when the LM's output is not in the expected format."""


class ExecutionTimeoutError(NonTerminatingException):
    """Raised when the action execution timed out."""


class TerminatingException(Exception):
    """Raised for conditions that terminate the agent."""


class Submitted(TerminatingException):
    """Raised when the LM declares that the agent has finished its task."""


class LimitsExceeded(TerminatingException):
    """Raised when the agent has reached its cost or step limit."""


class DefaultAgent:
    def __init__(self, model: Model, env: Environment, *, config_class: Callable = AgentConfig, **kwargs):
        self.config = config_class(**kwargs)
        self.messages: list[dict] = []
        self.model = model
        self.env = env
        self.extra_template_vars = {}
        self.monitor = None
        self.refiner = None
        self.step_index = 1
        self.trajectory_data = []  # Store (event, thought, observation) tuples for refiner
        self.min_steps_between_refinements = 5
        self.last_refinement_step = -100

        # Tracking history for plan_monitor and plan_refiner interventions
        # Each entry: {step, planner_type, content, latency_ms, usage}
        self.planner_history = []

        # Initialize monitor if enabled and available
        if self.config.enable_monitor and MONITOR_AVAILABLE:
            self.monitor = StatefulPhaseMonitor(enable_rules=True)

        # Initialize refiner if enabled and available
        if self.config.enable_refiner and REFINER_AVAILABLE and self.monitor:
            refiner_model = PlanRefiner.create_model_from_config(self.config.refiner_config_path)
            self.refiner = PlanRefiner(refiner_model, config=None)
            self.min_steps_between_refinements = PlanRefiner.get_min_steps_from_config(self.config.refiner_config_path)

    def render_template(self, template: str, **kwargs) -> str:
        template_vars = asdict(self.config) | self.env.get_template_vars() | self.model.get_template_vars()
        return Template(template, undefined=StrictUndefined).render(
            **kwargs, **template_vars, **self.extra_template_vars
        )

    def add_message(self, role: str, content: str, **kwargs):
        self.messages.append({"role": role, "content": content, **kwargs})

    def run(self, task: str, **kwargs) -> tuple[str, str]:
        """Run step() until agent is finished. Return exit status & message"""
        self.extra_template_vars |= {"task": task, **kwargs}
        self.messages = []
        self.step_index = 1
        self.add_message("system", self.render_template(self.config.system_template))
        self.add_message("user", self.render_template(self.config.instance_template))
        print("Is monitor available:", MONITOR_AVAILABLE)
        print("Is monitor enabled:", self.config.enable_monitor)
        print("Is refiner available:", REFINER_AVAILABLE)
        print("Is refiner enabled:", self.config.enable_refiner)
        while True:
            try:
                self.step()
                self.step_index += 1
            except NonTerminatingException as e:
                self.add_message("user", str(e))
            except TerminatingException as e:
                self.add_message("user", str(e))
                return type(e).__name__, str(e)

    def step(self) -> dict:
        """Query the LM, check rules pre-emptively, execute the action if safe, return the observation."""
        # Query model (limit check and assistant message handled in query())
        response = self.query()

        # Pre-emptively check plan monitor before executing action
        if self.monitor:
            action = self.parse_action(response)
            event = ActionEvent(step_index=self.step_index, command=action["action"])

            # Track monitor latency
            monitor_start_time = time.time()
            monitor_result = self.monitor.check_step_pre_emptively(event, thought=response.get("content", ""))
            monitor_latency_ms = (time.time() - monitor_start_time) * 1000

            if monitor_result:
                messages = monitor_result.get_all_messages()
                if messages:
                    monitor_message = messages[0]
                    monitor_blocked = monitor_result.should_block_and_refine()

                    # Check if refiner is enabled to handle rule triggers
                    if self.refiner:
                        # Refiner handles both blocking and non-blocking cases
                        return self._call_refiner(
                            monitor_result.rule_matches,
                            monitor_message,
                            is_blocking=monitor_blocked,
                            action=action,
                            response=response,
                            event=event,
                            monitor_latency_ms=monitor_latency_ms
                        )
                    else:
                        # No refiner - handle manually with tracking
                        if monitor_blocked:
                            # Just block with monitor message
                            self.messages.pop()  # Remove assistant message
                            self.add_message("user", monitor_message)
                            print(f"[MONITOR] Blocking action at step {self.step_index} with message:\n{monitor_message}\n")

                            # Track monitor intervention
                            self._track_planner_intervention(
                                planner_type="monitor",
                                content=monitor_message,
                                latency_ms=monitor_latency_ms,
                                usage=None
                            )

                            return {"output": "", "return_code": -1}
                        else:
                            # Execute action and add monitor message
                            output = self.execute_action(action)
                            observation = self.render_template(self.config.action_observation_template, output=output)
                            self.add_message("user", observation)
                            self.add_message("user", monitor_message)
                            print(f"[MONITOR] Non-blocking rule triggered at step {self.step_index} with message:\n{monitor_message}\n")

                            # Track monitor intervention
                            self._track_planner_intervention(
                                planner_type="monitor",
                                content=monitor_message,
                                latency_ms=monitor_latency_ms,
                                usage=None
                            )

                            self.trajectory_data.append((event, response.get("content", ""), output.get("output", "")))
                            return output

        # No monitor or no rules triggered - proceed normally
        return self.get_observation(response)

    def _call_refiner(self, rule_matches: list, monitor_message: str, is_blocking: bool,
                      action: dict, response: dict, event: ActionEvent, monitor_latency_ms: float = 0.0) -> dict:
        """
        Call plan_refiner for both blocking and non-blocking rule triggers.

        For blocking rules:
        - Don't execute action
        - Don't add assistant message to history
        - Call refiner for guidance

        For non-blocking rules:
        - Execute action first
        - Keep assistant message and observation in history
        - Call refiner for post-hoc guidance

        Args:
            rule_matches: List of triggered rules from monitor
            monitor_message: Pre-computed message from monitor (to avoid redundant extraction)
            is_blocking: Whether the rule blocks execution
            action: Parsed action dict
            response: Model response dict
            event: ActionEvent for this step
            monitor_latency_ms: Latency of monitor check in milliseconds

        Returns:
            Output dict (empty for blocking, actual output for non-blocking)
        """
        rule_type = "Blocking" if is_blocking else "Non-blocking"
        print(f"\n[REFINER] {rule_type} rules triggered at step {self.step_index}")
        print(f"[REFINER] Rules: {[m.rule_id for m in rule_matches]}")

        # Handle message history based on blocking status
        if is_blocking:
            # Remove assistant message for blocking rules
            self.messages.pop()
        
        # For non-blocking rules: execute action first and store trajectory
        if not is_blocking:
            output = self.execute_action(action)
            observation = self.render_template(self.config.action_observation_template, output=output)
            self.add_message("user", observation)
            # Store trajectory data BEFORE calling refiner
            self.trajectory_data.append((event, response.get("content", ""), output.get("output", "")))

        # Check cooling period BEFORE building state and calling refiner (optimization)
        steps_since_last = self.step_index - self.last_refinement_step
        within_cooling_period = steps_since_last < self.min_steps_between_refinements

        # If within cooling period, just return monitor message without calling refiner LLM
        # Exclude plan_compliance messages
        if within_cooling_period:
            from plan_monitor.phases import MonitorResult
            filtered_monitor_result = MonitorResult(
                current_phase=None,
                phase_changed=False,
                rule_matches=rule_matches
            )
            filtered_messages = filtered_monitor_result.get_filtered_messages(exclude_rule_patterns=['plan_compliance'])
            filtered_message = filtered_messages[0] if filtered_messages else ""

            if filtered_message:
                self.add_message("user", filtered_message)

                # Track monitor intervention (within cooling period, no refiner call)
                self._track_planner_intervention(
                    planner_type="monitor",
                    content=filtered_message,
                    latency_ms=monitor_latency_ms,
                    usage=None
                )

                print(f"[REFINER] Within cooling period ({steps_since_last}/{self.min_steps_between_refinements} steps) - monitor message added")
            
            # Return appropriate output based on blocking status
            if is_blocking:
                return {"output": "", "exit_code": -1}
            else:
                return output

        # Not in cooling period - perform full refinement
        # Build state summary from monitor (only when actually calling refiner)
        state_summary = PlanRefiner.build_state_summary_from_monitor(
            self.monitor,
            rule_matches=rule_matches
        )

        # Build trajectory steps (includes the just-executed step for non-blocking)
        trajectory_steps = PlanRefiner.build_trajectory_steps(self.trajectory_data)
        print(trajectory_steps)
        print()
        print(state_summary)

        # Get issue description
        issue_description = self.extra_template_vars.get("task", "No task description available")

        # Create refiner input and call refiner with latency tracking
        refiner_input = RefinerInput(
            issue_description=issue_description,
            trajectory=trajectory_steps,
            state_summary=state_summary
        )

        refiner_start_time = time.time()
        refiner_output = self.refiner.refine_plan(
            refiner_input,
            current_step=self.step_index,
            last_refinement_step=self.last_refinement_step
        )
        refiner_latency_ms = (time.time() - refiner_start_time) * 1000
        print(f"[REFINER] Refiner output:\n{refiner_output.raw_response}\n")

        # Add refined plan as user message
        if refiner_output.raw_response:
            if refiner_output.new_plan:
                message_to_track = f"[Plan Refiner Guidance]\n\n{refiner_output.new_plan}"
            else:
                message_to_track = f"[Plan Refiner Guidance]\n\n{refiner_output.raw_response}"
            self.add_message("user", message_to_track)
            print(f"[REFINER] New plan added to messages")

            # Update the intended plan in the monitor's plan compliance rule
            if refiner_output.refined_plan_phases:
                plan_updated = self.monitor.update_intended_plan(refiner_output.refined_plan_phases)
                if not plan_updated:
                    print(f"[REFINER] Warning: Failed to update plan in monitor")

        else:
            print(f"[REFINER] Warning: Refiner returned empty response.")
            # Exclude plan_compliance messages as they were already processed by refiner
            from plan_monitor.phases import MonitorResult
            filtered_monitor_result = MonitorResult(
                current_phase=None,
                phase_changed=False,
                rule_matches=rule_matches
            )
            filtered_messages = filtered_monitor_result.get_filtered_messages(exclude_rule_patterns=['plan_compliance'])

            if filtered_messages:
                message_to_track = filtered_messages[0]
                self.add_message("user", message_to_track)
                print(f"[REFINER] Use monitor message as fallback.")
            else:
                message_to_track = "" 

        # Track refiner intervention (includes refiner call + output)
        from dataclasses import asdict
        self._track_planner_intervention(
            planner_type="refiner",
            content=message_to_track,
            latency_ms=refiner_latency_ms,
            usage=refiner_output.usage,
            state_summary=asdict(state_summary)
        )

        # Update last refinement step
        self.last_refinement_step = self.step_index

        # Return appropriate output based on blocking status
        if is_blocking:
            return {"output": "", "exit_code": -1}
        else:
            return output

    def query(self) -> dict:
        """Query the model and return the response."""
        if 0 < self.config.step_limit <= self.model.n_calls or 0 < self.config.cost_limit <= self.model.cost:
            raise LimitsExceeded()
        response = self.model.query(self.messages)
        self.add_message("assistant", **response)
        return response

    def get_observation(self, response: dict) -> dict:
        """Execute the action and return the observation."""
        action = self.parse_action(response)
        output = self.execute_action(action)
        observation = self.render_template(self.config.action_observation_template, output=output)
        self.add_message("user", observation)

        # Store trajectory data for refiner (when monitor isn't active or no rules triggered)
        if self.monitor:
            event = ActionEvent(step_index=self.step_index, command=action["action"])
            self.trajectory_data.append((event, response.get("content", ""), output.get("output", "")))

        return output

    def parse_action(self, response: dict) -> dict:
        """Parse the action from the message. Returns the action."""
        actions = re.findall(r"```bash\s*\n(.*?)\n```", response["content"], re.DOTALL)
        if len(actions) == 1:
            return {"action": actions[0].strip(), **response}
        raise FormatError(self.render_template(self.config.format_error_template, actions=actions))

    def execute_action(self, action: dict) -> dict:
        try:
            output = self.env.execute(action["action"])
        except subprocess.TimeoutExpired as e:
            output = e.output.decode("utf-8", errors="replace") if e.output else ""
            raise ExecutionTimeoutError(
                self.render_template(self.config.timeout_template, action=action, output=output)
            )
        except TimeoutError:
            raise ExecutionTimeoutError(self.render_template(self.config.timeout_template, action=action, output=""))
        self.has_finished(output)
        return output

    def has_finished(self, output: dict[str, str]):
        """Raises Submitted exception with final output if the agent has finished its task."""
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() in ["MINI_SWE_AGENT_FINAL_OUTPUT", "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"]:
            raise Submitted("".join(lines[1:]))

    def _track_planner_intervention(self, planner_type: str, content: str, latency_ms: float, usage: dict = None, state_summary: dict = None):
        """
        Track a plan_monitor or plan_refiner intervention.

        Args:
            planner_type: Type of planner ("monitor" or "refiner")
            content: The message content added to conversation
            latency_ms: Time taken in milliseconds
            usage: Token usage dict (for refiner only: input_tokens, output_tokens, total_tokens)
            state_summary: State summary dict (for refiner only: phases, rules triggered, etc.)
        """
        intervention = {
            "step": self.step_index,
            "planner_type": planner_type,
            "content": content,
            "latency_ms": round(latency_ms, 2)
        }

        # Add usage information for refiner
        if usage:
            intervention["usage"] = usage

        # Add state summary for refiner
        if state_summary:
            intervention["state_summary"] = state_summary

        self.planner_history.append(intervention)

    def save_planner_history(self, output_dir: str, instance_id: str) -> str:
        """
        Save planner_history to a JSON file.

        Args:
            output_dir: Directory to save the file (same as trajectory)
            instance_id: Instance identifier

        Returns:
            Path to the saved file, or None if no interventions
        """
        import json
        from pathlib import Path

        if not self.planner_history:
            # No interventions to save
            return None

        # Create output path: {output_dir}/{instance_id}.planner.json
        output_path = Path(output_dir) / f"{instance_id}.planner.json"

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Compute summary statistics
        monitor_interventions = [x for x in self.planner_history if x["planner_type"] == "monitor"]
        refiner_interventions = [x for x in self.planner_history if x["planner_type"] == "refiner"]

        summary = {
            "total_interventions": len(self.planner_history),
            "monitor_count": len(monitor_interventions),
            "refiner_count": len(refiner_interventions),
            "monitor_total_latency_ms": round(sum(x["latency_ms"] for x in monitor_interventions), 2),
            "refiner_total_latency_ms": round(sum(x["latency_ms"] for x in refiner_interventions), 2),
        }

        # Add refiner token and cost statistics
        if refiner_interventions:
            summary["refiner_total_input_tokens"] = sum(x.get("usage", {}).get("input_tokens", 0) for x in refiner_interventions)
            summary["refiner_total_output_tokens"] = sum(x.get("usage", {}).get("output_tokens", 0) for x in refiner_interventions)
            summary["refiner_total_tokens"] = sum(x.get("usage", {}).get("total_tokens", 0) for x in refiner_interventions)
            summary["refiner_total_cost"] = round(sum(x.get("usage", {}).get("cost", 0.0) for x in refiner_interventions), 6)

        output_data = {
            "summary": summary,
            "interventions": self.planner_history
        }

        # Save to JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        return str(output_path)
