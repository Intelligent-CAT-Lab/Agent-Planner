"""
Build Langutory sequences from raw trajectory action nodes.

Reads action nodes parsed from trajectories and builds role sequences using mapLang.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any, Set
from plan_monitor.mapLang import get_action_role


def build_lang_sequence_rle(step_nodes: List[Tuple[int, Dict[str, Any]]]) -> Tuple[List[str], List[int]]:
    """
    Build run-length encoded role sequence from action nodes.

    Args:
        step_nodes: List of (step_index, node) tuples where node contains:
            - tool: SWE-agent tool name or None
            - command: Shell command or None
            - subcommand: Tool subcommand or None
            - args: Command arguments (dict for tools, list for shell)
            - flags: Command flags (dict)

    Returns:
        roles: run-collapsed roles e.g. ['L_navigate','L_reproduce', 'P', 'V_newly_generated_test'...]
        lens:  streak length per run      [  3,  2,  3, 1 ...]
    """
    roles: List[str] = []
    lens: List[int] = []
    prev: Optional[str] = None
    created_tests: Set[str] = set()

    for step_idx, node in step_nodes:
        tool = node.get('tool')
        command = node.get('command')
        subcommand = node.get('subcommand')
        args = node.get('args')
        flags = node.get('flags')

        # Get action role from mapLang
        role = get_action_role(
            tool=tool,
            subcommand=subcommand,
            command=command,
            args=args,
            flags=flags,
            prev_roles=roles,
            created_tests=created_tests
        )

        # Skip general or empty roles
        if not role or role == 'general':
            continue

        # Run-length encoding: collapse consecutive identical roles
        if role == prev:
            lens[-1] += 1
        else:
            roles.append(role)
            lens.append(1)
            prev = role

    return roles, lens


def build_lang_sequence(step_nodes: List[Tuple[int, Dict[str, Any]]]) -> List[str]:
    """
    Build full role sequence from action nodes (no run-length encoding).

    Args:
        step_nodes: List of (step_index, node) tuples where node contains:
            - tool: SWE-agent tool name or None
            - command: Shell command or None
            - subcommand: Tool subcommand or None
            - args: Command arguments (dict for tools, list for shell)
            - flags: Command flags (dict)

    Returns:
        List of role strings for each step (excluding 'general')
    """
    roles: List[str] = []
    created_tests: Set[str] = set()

    for step_idx, node in step_nodes:
        tool = node.get('tool')
        command = node.get('command')
        subcommand = node.get('subcommand')
        args = node.get('args')
        flags = node.get('flags')

        # Get action role from mapLang
        role = get_action_role(
            tool=tool,
            subcommand=subcommand,
            command=command,
            args=args,
            flags=flags,
            prev_roles=roles,
            created_tests=created_tests
        )

        # Skip general role or empty
        if not role or role == 'general':
            continue

        roles.append(role)

    return roles
