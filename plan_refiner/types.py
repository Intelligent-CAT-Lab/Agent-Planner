"""
Data structures for plan refiner.

Defines input/output types and state representations for the plan refiner.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RefinerTrajectoryStep:
    """
    Single step in the trajectory for plan refiner input.

    Attributes:
        step_index: Step number in the trajectory
        thought: Agent's reasoning for this step
        action: Bash command executed
        observation: Output from the command execution
    """
    step_index: int
    thought: str
    action: str
    observation: str


@dataclass
class RuleTrigger:
    """
    Information about a triggered rule from the monitor.

    Attributes:
        rule_id: Identifier for the triggered rule
        message: Guidance message from the rule
        step_index: Step where the rule triggered
        metadata: Additional rule-specific information
    """
    rule_id: str
    message: str
    step_index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class StateSummary:
    """
    Summary of the current execution state from plan_monitor.

    Attributes:
        current_phase: Current phase (e.g., L_navigate, P, V_regression_test)
        phase_history: Full sequence of phases (with duplicates)
        unique_phases: Unique phases in order of first appearance
        rule_triggers: List of all triggered rules
        graph_info: Graph-based signals (oscillations, etc.)
        step_count: Total number of steps executed
    """
    current_phase: Optional[str] = None
    phase_history: list[str] = field(default_factory=list)
    unique_phases: list[str] = field(default_factory=list)
    rule_triggers: list[RuleTrigger] = field(default_factory=list)
    graph_info: dict = field(default_factory=dict)
    step_count: int = 0


@dataclass
class RefinerInput:
    """
    Input to the plan refiner.

    Attributes:
        issue_description: The bug/issue description
        trajectory: List of trajectory steps so far
        state_summary: State summary from plan_monitor
        last_refinement_guidance: Last refinement guidance from previous refiner call
        last_refinement_step: Step index of last refinement (for filtering trajectory)
    """
    issue_description: str
    trajectory: list[RefinerTrajectoryStep]
    state_summary: StateSummary
    last_refinement_guidance: Optional[str] = None
    last_refinement_step: Optional[int] = None


@dataclass
class RefinerOutput:
    """
    Output from the plan refiner.

    Attributes:
        analysis: Analysis section with critique
        new_plan: Refined high-level plan for next steps
        raw_response: Full LLM response
        inferred_plan: Extracted inferred plan from analysis
        evaluation: Extracted evaluation from analysis
        implementation_review: Extracted implementation review
        is_cooling_period: True if refinement was skipped due to cooling period
        cooling_period_message: Message to return during cooling period
        usage: Token usage statistics (input_tokens, output_tokens, total_tokens)
        refined_plan_phases: List of phases extracted from new_plan (e.g., ["L_navigate", "P", "V_regression_test"])
    """
    analysis: str
    new_plan: str
    raw_response: str
    inferred_plan: Optional[str] = None
    evaluation: Optional[str] = None
    implementation_review: Optional[str] = None
    is_cooling_period: bool = False
    cooling_period_message: Optional[str] = None
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    refined_plan_phases: list[str] = field(default_factory=list)
