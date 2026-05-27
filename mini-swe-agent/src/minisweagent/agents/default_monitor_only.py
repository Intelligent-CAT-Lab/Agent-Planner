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
        self.step_index = 0

        # Tracking history for plan_monitor interventions
        # Each entry: {step, planner_type, content, latency_ms}
        self.planner_history = []

        # Initialize monitor if enabled and available
        if self.config.enable_monitor and MONITOR_AVAILABLE:
            self.monitor = StatefulPhaseMonitor(enable_rules=True)

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
        self.step_index = 0
        self.add_message("system", self.render_template(self.config.system_template))
        self.add_message("user", self.render_template(self.config.instance_template))
        print("Is monitor available:", MONITOR_AVAILABLE)
        print("Is monitor enabled:", self.config.enable_monitor)
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
        """Query the LM, execute the action, return the observation."""
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

                    if monitor_blocked:
                        # Remove the assistant message from history that was just added in query()
                        # Don't execute action, don't append this step to history
                        # Only add the monitor message as user feedback
                        self.messages.pop()  # Remove assistant message
                        self.add_message("user", monitor_message)

                        # Track monitor intervention
                        self._track_planner_intervention(
                            planner_type="monitor",
                            content=monitor_message,
                            latency_ms=monitor_latency_ms,
                            usage=None
                        )

                        # Return empty output to indicate action was not executed
                        return {"output": "", "return_code": -1}
                    else:
                        # Execute action normally, then append monitor message after observation
                        output = self.execute_action(action)
                        observation = self.render_template(self.config.action_observation_template, output=output)
                        self.add_message("user", observation)
                        self.add_message("user", monitor_message)

                        # Track monitor intervention
                        self._track_planner_intervention(
                            planner_type="monitor",
                            content=monitor_message,
                            latency_ms=monitor_latency_ms,
                            usage=None
                        )

                        return output

        return self.get_observation(response)

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

    def _track_planner_intervention(self, planner_type: str, content: str, latency_ms: float, usage: dict = None):
        """
        Track a plan_monitor intervention.

        Args:
            planner_type: Type of planner ("monitor")
            content: The message content added to conversation
            latency_ms: Time taken in milliseconds
            usage: Token usage dict (not used in monitor_only agent)
        """
        intervention = {
            "step": self.step_index,
            "planner_type": planner_type,
            "content": content,
            "latency_ms": round(latency_ms, 2)
        }

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

        summary = {
            "total_interventions": len(self.planner_history),
            "monitor_count": len(monitor_interventions),
            "monitor_total_latency_ms": round(sum(x["latency_ms"] for x in monitor_interventions), 2),
        }

        output_data = {
            "summary": summary,
            "interventions": self.planner_history
        }

        # Save to JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        return str(output_path)
