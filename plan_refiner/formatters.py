"""
Formatters for plan refiner input.

Converts trajectory steps and state summaries into formatted strings
for LLM consumption.
"""

from __future__ import annotations
from typing import Optional
from plan_refiner.types import RefinerTrajectoryStep, StateSummary, RuleTrigger


class TrajectoryFormatter:
    """Formats trajectory steps into a readable string for LLM input."""

    @staticmethod
    def format_trajectory(trajectory: list[RefinerTrajectoryStep], max_steps: int = None) -> str:
        """
        Format trajectory steps into a structured string.

        Args:
            trajectory: List of trajectory steps
            max_steps: Maximum number of steps to include (None = all)

        Returns:
            Formatted trajectory string
        """
        if not trajectory:
            return "No actions taken yet."

        # Limit trajectory if requested
        steps_to_format = trajectory if max_steps is None else trajectory[-max_steps:]

        formatted_steps = []
        for step in steps_to_format:
            step_text = f"## Step {step.step_index}\n\n"

            if step.thought:
                step_text += f"**Thought:**\n{step.thought}\n\n"

            step_text += f"**Action:**\n```bash\n{step.action}\n```\n\n"

            if step.observation:
                # Truncate very long observations
                obs = step.observation
                if len(obs) > 5000:
                    obs = obs[:2500] + "\n\n... [truncated] ...\n\n" + obs[-2500:]
                step_text += f"**Observation:**\n```\n{obs}\n```\n"

            formatted_steps.append(step_text)

        return "\n".join(formatted_steps)


class StateSummaryFormatter:
    """Formats state summary from plan_monitor into a readable string."""

    @staticmethod
    def format_state_summary(state: StateSummary) -> str:
        """
        Format state summary into a structured string.

        Args:
            state: State summary from plan_monitor

        Returns:
            Formatted state summary string
        """
        sections = []

        # Current phase
        sections.append("## Current Execution State\n")
        if state.current_phase:
            sections.append(f"**Current Phase:** {state.current_phase}")
        sections.append(f"**Total Steps Executed:** {state.step_count}")

        # Phase history (Langutory)
        sections.append("\n## Phase History\n")
        if state.phase_history:
            sections.append(f"**Full Phase Sequence:** {' -> '.join(state.phase_history)}")
            # sections.append(f"\n**Unique Phases:** {', '.join(state.unique_phases)}")
        else:
            sections.append("No phases recorded yet.")

        # Rule triggers
        if state.rule_triggers:
            sections.append("\n## Triggered Rules\n")
            sections.append(f"**Total Rules Triggered:** {len(state.rule_triggers)}\n")

            # Group by rule type
            rule_groups = {}
            for trigger in state.rule_triggers:
                rule_type = StateSummaryFormatter._classify_rule(trigger.rule_id)
                if rule_type not in rule_groups:
                    rule_groups[rule_type] = []
                rule_groups[rule_type].append(trigger)

            for rule_type, triggers in sorted(rule_groups.items()):
                sections.append(f"### {rule_type}\n")
                for trigger in triggers:
                    sections.append(f"- **Step {trigger.step_index}** ({trigger.rule_id}): {trigger.message}")

        return "\n".join(sections)

    @staticmethod
    def format_rule_messages(state: StateSummary) -> str:
        """
        Format only the currently triggered rule messages (for state_summary_mode="rule").

        This includes only the rules triggered at the current step that caused the refiner
        to be invoked, formatted with step index prefix followed by aggregated messages.

        Args:
            state: State summary from plan_monitor

        Returns:
            Formatted string with step index and rule messages, or empty string if no rules
        """
        if not state.rule_triggers:
            return ""

        # Get step index from first trigger (all triggers are from the same step)
        step_index = state.rule_triggers[0].step_index

        # Aggregate trigger messages from current step
        messages = []
        for trigger in state.rule_triggers:
            messages.append(trigger.message)

        # Format: message1\n\nmessage2 (if multiple)
        formatted_messages = "\n\n".join(messages)
        return f"{formatted_messages}"

    @staticmethod
    def _classify_rule(rule_id: str) -> str:
        """Classify rule ID into a human-readable category."""
        if "transition" in rule_id:
            return "Phase Transitions"
        elif "shift" in rule_id:
            return "Strategy Shifts"
        elif "dwell" in rule_id:
            return "Stagnation Alerts"
        elif "oscillation" in rule_id:
            return "Repeated Loop Detection"
        elif "compliance" in rule_id:
            return "Plan Violation"
        elif "repeated" in rule_id:
            return "Repeated Actions"
        else:
            return "Other Rules"


class PromptBuilder:
    """Builds prompts for the LLM using templates and formatted inputs."""

    def __init__(self, template: dict):
        """
        Initialize with a template.

        Args:
            template: Template dict with 'system' and 'user_template' keys
        """
        self.system_prompt = template.get("system", "")
        self.user_template = template.get("user_template", "")

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[PromptBuilder] Template keys: {list(template.keys())}")
        logger.info(f"[PromptBuilder] system_prompt length: {len(self.system_prompt)}")
        logger.info(f"[PromptBuilder] user_template length: {len(self.user_template)}")

    def build_prompt(
        self,
        issue_description: str,
        trajectory_text: str,
        state_summary_text: Optional[str] = None,
        last_guidance: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Build system and user prompts with conditional sections.

        Args:
            issue_description: The bug/issue description
            trajectory_text: Formatted trajectory string
            state_summary_text: Formatted state summary string (None to omit)
            last_guidance: Last refinement guidance (None to omit)

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        user_prompt = self.user_template.replace("{{ISSUE_DESCRIPTION}}", issue_description)
        user_prompt = user_prompt.replace("{{TRAJECTORY_SO_FAR}}", trajectory_text)
        user_prompt = user_prompt.replace("{{RECENT_TRAJECTORY}}", trajectory_text)

        # Conditionally include state summary
        if state_summary_text is not None:
            user_prompt = user_prompt.replace("{{STATE_SUMMARY}}", state_summary_text)
        else:
            # Remove state_summary section if not included
            user_prompt = self._remove_section(user_prompt, "state_summary")

        # Conditionally include last guidance
        if last_guidance is not None:
            user_prompt = user_prompt.replace("{{LATEST_GUIDANCE}}", last_guidance)
        else:
            # Remove latest_guidance section if not included
            user_prompt = self._remove_section(user_prompt, "latest_guidance")
            user_prompt = user_prompt.replace("{{LATEST_GUIDANCE}}", "")

        return self.system_prompt, user_prompt

    @staticmethod
    def _remove_section(text: str, section_name: str) -> str:
        """
        Remove a section block (e.g., <state_summary>...</state_summary>) from text.

        Args:
            text: Text containing the section
            section_name: Name of the section to remove

        Returns:
            Text with section removed
        """
        import re
        # Match the section tags and everything between them
        pattern = rf'<{section_name}>.*?</{section_name}>\s*'
        return re.sub(pattern, '', text, flags=re.DOTALL)
