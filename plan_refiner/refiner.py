"""
Plan Refiner Implementation.

Main module for plan refinement using LLM-based critique.
Integrates with mini-swe-agent and plan_monitor to provide
external planning guidance.
"""

from __future__ import annotations
import re
import yaml
from pathlib import Path
from typing import Optional, Protocol
from dataclasses import dataclass

from plan_refiner.types import (
    RefinerInput,
    RefinerOutput,
    StateSummary,
    RefinerTrajectoryStep,
    RuleTrigger
)
from plan_refiner.formatters import (
    TrajectoryFormatter,
    StateSummaryFormatter,
    PromptBuilder
)


class ModelProtocol(Protocol):
    """Protocol for LLM model interface."""

    def query(self, system_prompt: str, user_prompt: str) -> str:
        """Query the model with system and user prompts."""
        ...


@dataclass
class RefinerConfig:
    """
    Configuration for plan refiner.

    Attributes:
        template_path: Path to the configuration YAML file
        max_trajectory_steps: Maximum trajectory steps to include (None = all)
        enable_parsing: Whether to parse analysis sections
        min_steps_between_refinements: Minimum steps required between refinements (loaded from config)
        update_plan: Whether to extract refined plan phases for dynamic plan updates (loaded from config)
        trajectory_scope: Scope of trajectory to include ("full", "recent", "selected") (loaded from config)
        state_summary_mode: Mode for including state summary ("full", "rule", "none") (loaded from config)
        include_last_guidance: Whether to include last refinement guidance in prompt (loaded from config)
    """
    template_path: str = "config/default.yaml"
    max_trajectory_steps: Optional[int] = None
    enable_parsing: bool = True
    min_steps_between_refinements: Optional[int] = None
    update_plan: Optional[bool] = None
    trajectory_scope: Optional[str] = None
    state_summary_mode: Optional[str] = None
    include_last_guidance: Optional[bool] = None


class PlanRefiner:
    """
    Main plan refiner class.

    Integrates with mini-swe-agent and plan_monitor to:
    1. Collect issue description and trajectory from agent
    2. Get state summary from plan_monitor
    3. Call LLM to critique and refine the plan
    4. Return structured analysis and new plan
    """

    def __init__(
        self,
        model: ModelProtocol,
        config: Optional[RefinerConfig] = None
    ):
        """
        Initialize the plan refiner.

        Args:
            model: LLM model instance implementing ModelProtocol
            config: Optional configuration (uses defaults if not provided)
        """
        self.model = model
        self.config = config or RefinerConfig()
        self.template = self._load_template()
        self.prompt_builder = PromptBuilder(self.template.get("external_planner", {}))

        # Load min_steps_between_refinements from template if not set in config
        if self.config.min_steps_between_refinements is None:
            planner_config = self.template.get("external_planner", {})
            self.config.min_steps_between_refinements = planner_config.get("min_steps_between_refinements", 5)

        # Load update_plan from template if not set in config
        if self.config.update_plan is None:
            planner_config = self.template.get("external_planner", {})
            self.config.update_plan = planner_config.get("update_plan", True)

        # Load trajectory_scope from template if not set in config
        if self.config.trajectory_scope is None:
            planner_config = self.template.get("external_planner", {})
            self.config.trajectory_scope = planner_config.get("trajectory_scope", "full")

        # Load state_summary_mode from template if not set in config
        if self.config.state_summary_mode is None:
            planner_config = self.template.get("external_planner", {})
            self.config.state_summary_mode = planner_config.get("state_summary_mode", "full")

        # Load include_last_guidance from template if not set in config
        if self.config.include_last_guidance is None:
            planner_config = self.template.get("external_planner", {})
            self.config.include_last_guidance = planner_config.get("include_last_guidance", True)

    def _filter_trajectory(
        self,
        trajectory: list[RefinerTrajectoryStep],
        last_refinement_step: Optional[int]
    ) -> list[RefinerTrajectoryStep]:
        """
        Filter trajectory based on trajectory_scope configuration.

        Args:
            trajectory: Full trajectory list
            last_refinement_step: Step index of last refinement

        Returns:
            Filtered trajectory list based on scope
        """
        if self.config.trajectory_scope == "full":
            return trajectory
        elif self.config.trajectory_scope == "recent":
            # Only include steps since last refinement
            if last_refinement_step is None:
                return trajectory
            return [step for step in trajectory if step.step_index > last_refinement_step]
        elif self.config.trajectory_scope == "selected":
            # Not implemented yet - fallback to full
            return trajectory
        else:
            # Default to full
            return trajectory

    def _load_template(self) -> dict:
        """Load the prompt template from YAML file."""
        import plan_refiner
        import logging
        logger = logging.getLogger(__name__)

        # Resolve template path: relative paths are always resolved relative to plan_refiner package
        # This matches the behavior of create_model_from_config() for consistency
        template_path = Path(self.config.template_path)
        logger.info(f"[Refiner] Loading template from: {self.config.template_path}")
        if not template_path.is_absolute():
            # Always resolve relative paths from package root (not CWD)
            template_path = Path(plan_refiner.__file__).parent / self.config.template_path
            logger.info(f"[Refiner] Resolved to package path: {template_path}")

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {self.config.template_path} (resolved to: {template_path})")

        logger.info(f"[Refiner] Loading template from: {template_path.absolute()}")
        with open(template_path, 'r', encoding='utf-8') as f:
            template = yaml.safe_load(f)
            logger.info(f"[Refiner] Template loaded, top-level keys: {list(template.keys())}")
            return template

    @staticmethod
    def create_model_from_config(config_path: str):
        """
        Create a model instance from configuration file.

        Args:
            config_path: Path to YAML configuration file (relative to plan_refiner package or absolute)

        Returns:
            Model instance implementing the query(system_prompt, user_prompt) interface
        """
        from plan_refiner.models import OpenRouterModel, MockModel
        import plan_refiner

        # Resolve config path: relative paths are resolved relative to plan_refiner package
        config_file = Path(config_path)
        if not config_file.is_absolute():
            # Always resolve relative paths from package root (not CWD)
            config_file = Path(plan_refiner.__file__).parent / config_path

        if not config_file.exists():
            raise FileNotFoundError(f"Config not found: {config_path} (resolved to: {config_file})")

        # Log the resolved config file path for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Loading refiner config from: {config_file.absolute()}")

        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Get model configuration from external_planner.model
        planner_config = config.get("external_planner", {})
        model_config = planner_config.get("model", {})
        model_name = model_config.get("model_name")
        model_class = model_config.get("model_class", "openrouter")
        model_kwargs = model_config.get("model_kwargs", {})
        set_cache_control = model_config.get("set_cache_control", None)

        # Handle mock model
        if not model_name or model_class == "mock":
            import warnings
            warnings.warn(
                f"Using MockModel for plan refiner (model_name={model_name}, model_class={model_class}). "
                f"This will return dummy responses. Config loaded from: {config_file.absolute()}",
                UserWarning
            )
            return MockModel()

        # Create model based on class
        if model_class == "openrouter":
            return OpenRouterModel(
                model_name=model_name,
                model_kwargs=model_kwargs,
                set_cache_control=set_cache_control
            )
        else:
            raise ValueError(f"Unsupported model_class: {model_class}")

    @staticmethod
    def get_min_steps_from_config(config_path: str) -> int:
        """
        Get min_steps_between_refinements from configuration file.

        Args:
            config_path: Path to YAML configuration file (relative to plan_refiner package or absolute)

        Returns:
            Minimum steps between refinements (default: 5)
        """
        import plan_refiner

        # Resolve config path: relative paths are resolved relative to plan_refiner package
        config_file = Path(config_path)
        if not config_file.is_absolute():
            # Always resolve relative paths from package root (not CWD)
            config_file = Path(plan_refiner.__file__).parent / config_path

        if not config_file.exists():
            return 5

        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        planner_config = config.get("external_planner", {})
        return planner_config.get("min_steps_between_refinements", 10)

    def refine_plan(
        self,
        refiner_input: RefinerInput,
        current_step: Optional[int] = None
    ) -> RefinerOutput:
        """
        Refine the plan based on current trajectory and state.

        Args:
            refiner_input: Input containing issue, trajectory, state summary, and last refinement info
            current_step: Current step index (optional, for cooling period check)

        Returns:
            RefinerOutput with analysis and new plan, or monitor message if within cooling period
        """
        # Check if within cooling period
        if current_step is not None and refiner_input.last_refinement_step is not None:
            steps_since_last = current_step - refiner_input.last_refinement_step
            if steps_since_last < self.config.min_steps_between_refinements:
                # Within cooling period - return only the monitor messages from current step
                # Filter rule triggers that occurred at the current step
                current_step_triggers = [
                    trigger for trigger in refiner_input.state_summary.rule_triggers
                    if trigger.step_index == current_step
                ]
                monitor_messages = [trigger.message for trigger in current_step_triggers if trigger.message]

                if monitor_messages:
                    cooling_message = "\n\n".join(monitor_messages)
                    return RefinerOutput(
                        analysis="",
                        new_plan="",
                        raw_response="",
                        is_cooling_period=True,
                        cooling_period_message=cooling_message
                    )
                else:
                    # No monitor messages, return empty output
                    return RefinerOutput(
                        analysis="",
                        new_plan="",
                        raw_response="",
                        is_cooling_period=True,
                        cooling_period_message=None
                    )

        # Proceed with full refinement
        # Filter trajectory based on scope
        trajectory_to_format = self._filter_trajectory(
            refiner_input.trajectory,
            refiner_input.last_refinement_step
        )

        # Format trajectory
        trajectory_text = TrajectoryFormatter.format_trajectory(
            trajectory_to_format,
            max_steps=self.config.max_trajectory_steps
        )

        # Format state summary based on mode
        state_summary_text = None
        if self.config.state_summary_mode == "full":
            state_summary_text = StateSummaryFormatter.format_state_summary(
                refiner_input.state_summary
            )
        elif self.config.state_summary_mode == "rule":
            state_summary_text = StateSummaryFormatter.format_rule_messages(
                refiner_input.state_summary
            )
        # For "none", state_summary_text remains None

        # Build prompts with conditional sections
        system_prompt, user_prompt = self.prompt_builder.build_prompt(
            issue_description=refiner_input.issue_description,
            trajectory_text=trajectory_text,
            state_summary_text=state_summary_text,
            last_guidance=refiner_input.last_refinement_guidance if self.config.include_last_guidance else None
        )

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Refiner Debug] issue_description length: {len(refiner_input.issue_description)}")
        logger.info(f"[Refiner Debug] trajectory length: {len(refiner_input.trajectory)}")
        logger.info(f"[Refiner Debug] trajectory_text length: {len(trajectory_text)}")
        logger.info(f"[Refiner Debug] user_prompt length: {len(user_prompt)}")
        logger.info(f"[Refiner Debug] user_prompt first 500 chars:\n{user_prompt[:500]}")
        print(f"[Refiner] Refiner input:\n{user_prompt}\n")

        # Query LLM
        response, usage_info = self.model.query(system_prompt, user_prompt)

        # Parse response
        output = self._parse_response(response)

        # Add usage information to output
        output.usage = usage_info

        return output

    def _parse_response(self, response: str) -> RefinerOutput:
        """
        Parse LLM response into structured output.

        Args:
            response: Raw LLM response

        Returns:
            RefinerOutput with parsed sections
        """
        # Extract <analysis> section
        analysis_match = re.search(
            r"<analysis>(.*?)</analysis>",
            response,
            re.DOTALL | re.IGNORECASE
        )
        analysis = analysis_match.group(1).strip() if analysis_match else ""

        # Extract <new_plan> section
        new_plan_match = re.search(
            r"<new_plan>(.*?)</new_plan>",
            response,
            re.DOTALL | re.IGNORECASE
        )
        new_plan = new_plan_match.group(1).strip() if new_plan_match else ""

        # Extract refined plan phases from new_plan (if update_plan is enabled)
        refined_plan_phases = []
        if self.config.update_plan:
            refined_plan_phases = self._extract_plan_phases(new_plan)

        output = RefinerOutput(
            analysis=analysis,
            new_plan=new_plan,
            raw_response=response,
            refined_plan_phases=refined_plan_phases
        )

        # Parse analysis subsections if enabled
        if self.config.enable_parsing and analysis:
            output.inferred_plan = self._extract_subsection(
                analysis,
                r"###\s*1\.\s*Inferred High-Level Plan So Far"
            )
            output.evaluation = self._extract_subsection(
                analysis,
                r"###\s*2\.\s*Evaluation of the Plan's Logic"
            )
            output.implementation_review = self._extract_subsection(
                analysis,
                r"###\s*3\.\s*Review of Implementation and Final Code"
            )

        return output

    def _extract_subsection(self, text: str, header_pattern: str) -> Optional[str]:
        """
        Extract a subsection from analysis text.

        Args:
            text: Full analysis text
            header_pattern: Regex pattern for the section header

        Returns:
            Extracted section text or None
        """
        # Find section start
        header_match = re.search(header_pattern, text, re.IGNORECASE)
        if not header_match:
            return None

        start = header_match.end()

        # Find section end (next ### header or end of text)
        next_section = re.search(r"\n###\s+", text[start:])
        end = start + next_section.start() if next_section else len(text)

        return text[start:end].strip()

    def _extract_plan_phases(self, new_plan: str) -> list[str]:
        """
        Extract phase labels from the new_plan text.

        The new_plan typically contains numbered steps with [Phase=X] annotations:
            1. [Phase=L_navigate] ...
            2. [Phase=L_reproduce] ...
            3. [Phase=P] ...
            4. [Phase=V_newly_generated_test] ...
            5. [Phase=V_regression_test] ...

        Adjacent duplicate phases are merged since phases represent categories of work,
        not individual actions. For example:
            [L_reproduce, L_navigate, L_navigate, P] -> [L_reproduce, L_navigate, P]

        Args:
            new_plan: The new_plan text containing phase annotations

        Returns:
            List of phase labels in order with adjacent duplicates merged
            (e.g., ["L_navigate", "L_reproduce", "P"])
            Only valid phases are included: L_navigate, L_reproduce, P,
            V_newly_generated_test, V_regression_test
        """
        # Define valid phases
        VALID_PHASES = {
            "L_navigate",
            "L_reproduce",
            "P",
            "V_newly_generated_test",
            "V_regression_test"
        }

        phases = []

        # Pattern to match [Phase=X] annotations with optional whitespace
        # Handles: [Phase=X], [Phase = X], [Phase= X ], etc.
        # Captures the phase name inside [Phase=...]
        pattern = r'\[Phase\s*=\s*([^\]]+)\]'

        # Find all phase annotations in order
        for match in re.finditer(pattern, new_plan):
            phase = match.group(1).strip()

            # Only include valid phases
            if phase in VALID_PHASES:
                # Merge adjacent duplicates: only add if different from last phase
                if not phases or phases[-1] != phase:
                    phases.append(phase)

        return phases

    @staticmethod
    def build_state_summary_from_monitor(
        monitor,
        rule_matches: list = None,
        exclude_rule_patterns: list = None
    ) -> StateSummary:
        """
        Build StateSummary from a StatefulPhaseMonitor instance.

        Note: By default filters out plan_compliance triggers to avoid biasing the refiner
        with prescriptive phase sequences, allowing independent plan generation.

        Args:
            monitor: StatefulPhaseMonitor instance
            rule_matches: Optional list of recent rule matches
            exclude_rule_patterns: List of rule_id patterns to exclude from state_summary.
                                   Default: []

        Returns:
            StateSummary object
        """
        current_phase = monitor.get_current_phase()
        phase_history = monitor.get_phase_history()
        unique_phases = monitor.get_unique_phases()

        # Convert rule matches to RuleTrigger objects
        # Exclude specified patterns (default: plan_compliance to preserve refiner's independent reasoning)
        rule_triggers = []
        if rule_matches:
            for match in rule_matches:
                # Skip excluded patterns
                if match.rule_id in exclude_rule_patterns:
                    continue

                trigger = RuleTrigger(
                    rule_id=match.rule_id,
                    message=match.message,
                    step_index=match.step_index,
                    metadata=match.metadata
                )
                rule_triggers.append(trigger)

        # Get graph info if available
        graph_info = {}
        if hasattr(monitor, 'graph_builder') and monitor.graph_builder:
            graph = monitor.graph_builder.G
            graph_info = {
                "node_count": graph.number_of_nodes(),
                "edge_count": graph.number_of_edges(),
            }

        return StateSummary(
            current_phase=str(current_phase) if current_phase else None,
            phase_history=phase_history,
            unique_phases=unique_phases,
            rule_triggers=rule_triggers,
            graph_info=graph_info,
            step_count=monitor.step_counter if hasattr(monitor, 'step_counter') else 0
        )

    @staticmethod
    def build_trajectory_steps(
        trajectory_data: list[tuple]
    ) -> list[RefinerTrajectoryStep]:
        """
        Build RefinerTrajectoryStep list from trajectory data.

        Args:
            trajectory_data: List of (event, thought, observation) tuples

        Returns:
            List of RefinerTrajectoryStep objects
        """
        steps = []
        for event, thought, observation in trajectory_data:
            step = RefinerTrajectoryStep(
                step_index=event.step_index,
                thought=thought,
                action=event.command,
                observation=observation
            )
            steps.append(step)
        return steps
