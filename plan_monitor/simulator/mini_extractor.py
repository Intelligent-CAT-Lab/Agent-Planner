"""
Action Extractor for Trajectory Files.

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

        if 'messages' not in self._data:
            raise ValueError("Trajectory missing 'messages' field")

    def parse_thought_and_action(self, response: dict) -> tuple[Optional[str], Optional[str]]:
        """
        Parse thought and action from a message.

        Args:
            response: Message dict with 'content' field

        Returns:
            Tuple of (thought, action) where thought is the THOUGHT section and action is the bash command
        """
        content = response.get("content", "")

        # Extract THOUGHT section
        thought_match = re.search(r"THOUGHT:\s*(.*?)(?=```bash|\Z)", content, re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else ""

        # Extract bash command
        actions = re.findall(r"```bash\s*\n(.*?)\n```", content, re.DOTALL)
        action = actions[0].strip() if len(actions) == 1 else None

        return thought, action

    def extract_actions(self) -> Iterator[tuple[ActionEvent, str, str]]:
        """
        Extract all action events from the trajectory with thought and observation.

        Yields:
            Tuples of (ActionEvent, thought, observation) for each step
        """
        if not self._data:
            return

        messages = self._data.get('messages', [])
        step_index = 1  # Start from 1 for alignment with mini-swe-agent

        for msg_idx, message in enumerate(messages):
            if not isinstance(message, dict):
                continue

            role = message.get('role')

            # Only process assistant messages (agent actions)
            if role != 'assistant':
                continue

            # Parse thought and action
            thought, action = self.parse_thought_and_action(message)

            if action:
                # Get observation from next user message (extract content from <output> tags)
                observation = ""
                if msg_idx + 1 < len(messages):
                    next_message = messages[msg_idx + 1]
                    if isinstance(next_message, dict) and next_message.get('role') == 'user':
                        content = next_message.get('content', '')
                        # Extract content between <output> tags
                        output_match = re.search(r'<output>\s*(.*?)\s*</output>', content, re.DOTALL)
                        if output_match:
                            observation = output_match.group(1).strip()
                        else:
                            # Fallback to full content if no <output> tags
                            observation = content

                event = ActionEvent(
                    step_index=step_index,
                    command=action,
                    cwd=None,
                    last_output=None,
                    extra={
                        'message_index': msg_idx,
                        'instance_id': self._data.get('instance_id'),
                    }
                )
                yield event, thought, observation
                step_index += 1

    def get_instance_id(self) -> Optional[str]:
        """Get the instance ID from the trajectory."""
        return self._data.get('instance_id') if self._data else None

    def get_message_count(self) -> int:
        """Get the total number of messages in the trajectory."""
        return len(self._data.get('messages', [])) if self._data else 0
