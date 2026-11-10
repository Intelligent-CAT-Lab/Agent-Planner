"""
Action Extractor for SWE-Agent Trajectory Files.

Extracts action events from trajectory JSON files for testing the monitor.
"""

from __future__ import annotations
import json
import re
from typing import Iterator, Optional
from pathlib import Path
from plan_monitor.phases import ActionEvent


class ActionExtractor:
    """
    Extracts ActionEvent objects from trajectory JSON files.

    Parses assistant messages to extract bash commands for monitor testing.
    """

    def __init__(self, trajectory_path: str | Path):
        """
        Initialize the extractor with a trajectory file.

        Args:
            trajectory_path: Path to the trajectory JSON file
        """
        self.trajectory_path = Path(trajectory_path)
        self._data: Optional[dict] = None
        self._load_trajectory()

    def _load_trajectory(self):
        """Load and parse the trajectory JSON file."""
        with open(self.trajectory_path, 'r', encoding='utf-8') as f:
            self._data = json.load(f)

        if not isinstance(self._data, dict):
            raise ValueError(f"Invalid trajectory format: expected dict, got {type(self._data)}")

        if 'trajectory' not in self._data:
            raise ValueError("Trajectory missing 'trajectory' field")

    def extract_actions(
        self, include_thought_steps: bool = False
    ) -> Iterator[tuple[ActionEvent, str, str]]:
        """
        Extract all action events from the trajectory with thought and observation.

        Args:
            include_thought_steps: when True, also yield steps that carry a thought
                but no action (``command=""``). These mirror the online monitor's
                thought-only turns: ``GuardMonitor.check_step_pre_emptively`` routes
                an empty command to its ``observe(thought)`` path, which is what
                ``thought_oscillation`` is evaluated on. The default (False) preserves
                the historical behaviour every other consumer relies on — only
                steps with a parseable action are surfaced.

        Yields:
            Tuples of (ActionEvent, thought, observation) for each step
        """
        if not self._data:
            return

        trajectory = self._data.get('trajectory', [])
        step_index = 1  # Start from 1 for alignment with mini-swe-agent

        for step_idx, step in enumerate(trajectory):
            if not isinstance(step, dict):
                continue

            thought = step.get('thought', '')
            action = step.get('action', '')
            observation = step.get('observation', '')

            # An action step, or — when asked — a thought-only step (a turn the
            # model spent reasoning without issuing a command). A step with neither
            # is skipped in both modes.
            if action or (include_thought_steps and thought):
                event = ActionEvent(
                    step_index=step_index,
                    command=action,
                    cwd=None,
                    last_output=None,
                    extra={
                        'message_index': step_idx,
                        'instance_id': self._data.get('environment'),
                    }
                )
                yield event, thought, observation
                step_index += 1

    def get_instance_id(self) -> Optional[str]:
        """Get the instance ID from the trajectory."""
        return self._data.get('environment') if self._data else None

    def get_message_count(self) -> int:
        """Get the total number of steps in the trajectory."""
        return len(self._data.get('trajectory', [])) if self._data else 0