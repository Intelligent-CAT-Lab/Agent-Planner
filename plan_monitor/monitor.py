"""
Stateful Phase Monitor Implementation.

This module provides a plug-and-play monitor that tracks phase transitions
across agent actions. It maintains state across steps and detects both
coarse-grained (L -> P -> V) and fine-grained phase changes.

The monitor integrates a rule engine that provides:
- Phase transition detection (L -> P -> V)
- Strategy shift detection (e.g., V -> L, P -> L)
- Dwell time monitoring (detecting stuck agents)
"""

from __future__ import annotations
from typing import Optional, Set
from pathlib import Path
from plan_monitor.phases import ActionEvent, MonitorResult, Phase
from plan_monitor.commandParser import CommandParser
from plan_monitor.mapLang import get_action_role
from plan_monitor.rules import RuleEngine
from plan_monitor.buildGraph import GraphBuilder, build_online_graph_from_trajectory, check_command_outcome


class StatefulPhaseMonitor:
    """
    Plug-and-play phase monitor with state tracking and rule engine.

    Detects phase transitions (both category-level and exact phase changes)
    and returns messages when transitions occur. Maintains state for:
    - Current phase
    - Previous roles (for context in mapLang)
    - Created test files (for validation phase detection)
    - Dynamic test suites (for ephemeral validation code)

    Integrates a rule engine that provides:
    - Phase transition guidance (L -> P -> V)
    - Strategy shift detection (e.g., V -> L, P -> L)
    - Dwell time monitoring and intervention

    Usage:
        monitor = StatefulPhaseMonitor()
        for action_event in action_stream:
            result = monitor.on_step(action_event)
            if result:
                # Print all messages (phase change + rule matches)
                for msg in result.get_all_messages():
                    print(msg)
    """

    def __init__(
        self,
        parser: Optional[CommandParser] = None,
        enable_rules: bool = True,
        rules_config: Optional[str] = None
    ):
        """
        Initialize the monitor.

        Args:
            parser: Optional CommandParser instance. If not provided, creates default.
            enable_rules: Whether to enable rule engine (default: True)
            rules_config: Name of rules config file (without .json extension) or full path.
                         If name only, looks in plan_monitor/config/{name}.json.
                         If None, uses default_rules.json.
        """
        # Rule engine integration (create before parser to access config)
        self.enable_rules = enable_rules

        # Resolve rules config path
        config_path = None
        if enable_rules:
            if rules_config:
                from pathlib import Path
                config_path_obj = Path(rules_config)
                if config_path_obj.is_absolute():
                    config_path = config_path_obj
                else:
                    # Treat as config name, resolve relative to config directory
                    config_path = Path(__file__).parent / "config" / f"{rules_config}.json"
            # else: None will trigger RuleEngine's default (default_rules.json)

        self.rule_engine = RuleEngine(config_path=config_path) if enable_rules else None

        # Initialize parser with tool configs from rule engine
        if parser is None:
            parser = CommandParser()
            if self.rule_engine:
                # Load tool configs from rule engine's config
                tool_configs = self.rule_engine.config.get("meta_data", {}).get("agent", {}).get("SWE-agent", {}).get("tool_configs", [])
                if tool_configs:
                    # Resolve paths relative to the plan_monitor directory
                    from pathlib import Path
                    base_path = Path(__file__).parent.parent
                    resolved_paths = [str(base_path / config) for config in tool_configs]
                    parser.load_tool_yaml_files(resolved_paths)

        self.parser = parser
        self.current_phase: Optional[Phase] = None
        self.previous_phase: Optional[Phase] = None
        self.role_history: list[str] = []
        self.created_tests: Set[str] = set()
        self.created_dynamic_suites: Set[str] = set()

        # Track thought history for oscillation detection (separate from graph)
        # Stores MD5 hash of full thought text when action is empty
        # Using hash prevents false positives from prefix matching
        self.thought_history: list[str] = []

        # Graph building (built when rules enabled for oscillation detection)
        self.graph_builder = GraphBuilder() if enable_rules else None
        self.step_counter = 1  # Start from 1

    def check_step_pre_emptively(
        self,
        event: ActionEvent,
        thought: str = ""
    ) -> Optional[MonitorResult]:
        """
        Check if rules would trigger, updating state only if no blocking rules fire.

        Temporarily updates graph and role_history to detect patterns. Reverts if blocking, commits if not.

        Args:
            event: ActionEvent containing step information
            thought: Optional thought/reasoning text from this step

        Returns:
            MonitorResult with rule_matches if rules trigger, None otherwise
        """
        import copy

        parsed_commands = self.parser.parse(event.command)

        # Handle empty actions (valid think steps OR problematic oscillations)
        if not parsed_commands:
            # Create "think" node in graph to track reasoning flow
            if self.graph_builder:
                # Backup state before tentative graph update
                graph_backup = copy.deepcopy(self.graph_builder.G)
                prev_node_backup = self.graph_builder.previous_node
                step_counter_backup = self.step_counter

                # Build "think" node with thought-based signature
                self._build_think_node(self.step_counter, thought, event.command)
                self.step_counter += 1

                # Add thought hash to history for oscillation tracking
                import hashlib
                thought_hash = hashlib.md5(thought.encode('utf-8')).hexdigest()
                self.thought_history.append(thought_hash)

                # Check for thought-level oscillation (problematic repetition)
                if self.enable_rules and self.rule_engine:
                    thought_osc_rule = self.rule_engine.rules.get("thought_oscillation")
                    oscillation_match = None
                    if thought_osc_rule:
                        oscillation_match = thought_osc_rule.check(thought_history=self.thought_history)

                    if oscillation_match:
                        # Problematic repetition detected - rollback graph and history
                        self.graph_builder.G = graph_backup
                        self.graph_builder.previous_node = prev_node_backup
                        self.step_counter = step_counter_backup
                        self.thought_history.pop()  # Remove the just-added thought hash

                        return MonitorResult(
                            current_phase=self.current_phase,
                            phase_changed=False,
                            category_changed=False,
                            previous_phase=self.previous_phase,
                            rule_matches=[oscillation_match]
                        )

            # No oscillation detected - this is a valid think step
            return None

        # Backup state
        graph_backup = copy.deepcopy(self.graph_builder.G) if self.graph_builder else None
        prev_node_backup = self.graph_builder.previous_node if self.graph_builder else None
        node_sig_backup = copy.deepcopy(self.graph_builder.node_signature_to_key) if self.graph_builder else None
        localization_nodes_backup = self.graph_builder.localization_nodes.copy() if self.graph_builder else None
        # Backup graph_builder's prev_phases and created_tests for correct phase classification
        # These are used by get_action_role() during graph building and must be rolled back
        prev_phases_backup = self.graph_builder.prev_phases.copy() if self.graph_builder else None
        created_tests_gb_backup = self.graph_builder.created_tests.copy() if self.graph_builder else None
        role_history_len = len(self.role_history)
        step_counter_backup = self.step_counter
        current_phase_backup = self.current_phase
        previous_phase_backup = self.previous_phase

        # Backup test tracking sets
        created_tests_backup = self.created_tests.copy()
        created_dynamic_suites_backup = self.created_dynamic_suites.copy()

        # Backup rule engine state
        rules_backup = copy.deepcopy(self.rule_engine.rules) if self.rule_engine else None
        trigger_history_backup = self.rule_engine.trigger_history.copy() if self.rule_engine else None

        # Temporarily build graph for this step
        if self.graph_builder:
            build_online_graph_from_trajectory(
                builder=self.graph_builder,
                step_idx=self.step_counter,
                thought=thought,
                action=event.command,
                observation="",
                parser=self.parser
            )
            self.step_counter += 1

        # STEP 1: Collect roles from all split commands in this trajectory step
        # Track unique consecutive roles to add to role_history
        step_roles = []  # Roles collected in this step (non-general only)
        last_role_in_step = None
        all_rule_matches = []

        for cmd_idx, cmd_info in enumerate(parsed_commands):
            tool = cmd_info.get("tool")
            subcommand = cmd_info.get("subcommand")
            command = cmd_info.get("command")
            args = cmd_info.get("args", [])
            flags = cmd_info.get("flags", {})

            role = get_action_role(
                tool=tool, subcommand=subcommand, command=command, args=args, flags=flags,
                prev_roles=self.role_history, created_tests=self.created_tests,
                created_dynamic_suites=self.created_dynamic_suites
            )

            # Check plan compliance rule even for "general" roles to detect ending flags
            # (e.g., "submit" command that ends execution)
            if role == "general":
                if self.enable_rules and self.rule_engine:
                    plan_rule = self.rule_engine.rules.get("plan_compliance")
                    if plan_rule and plan_rule.enabled:
                        # Check plan compliance for ending flags only (current_phase=None)
                        plan_match = plan_rule.check(
                            current_phase=None,
                            previous_phase=self.current_phase,
                            step_index=event.step_index,
                            command=event.command
                        )
                        if plan_match:
                            all_rule_matches.append(plan_match)
                # Skip further processing for general roles
                continue

            # Only collect role if it's different from the last role in this step
            # This handles: "grep x && grep y" (both L_navigate) -> collect L_navigate once
            #               "grep x && sed -i file.py" (L then P) -> collect both
            if role != last_role_in_step:
                step_roles.append(role)
                last_role_in_step = role

        # STEP 2: If no non-general roles, still check trajectory-level rules (oscillation)
        # These rules work on full commands regardless of role classification
        if not step_roles:
            # Evaluate trajectory-level rules that don't depend on roles
            if self.enable_rules and self.rule_engine:
                # Check oscillation (works on full command history)
                osc_rule = self.rule_engine.rules.get("oscillation")
                if osc_rule and osc_rule.enabled:
                    osc_match = osc_rule.check(
                        graph=self.graph_builder.G if self.graph_builder else None,
                        step_index=event.step_index,
                        command=event.command
                    )
                    if osc_match:
                        all_rule_matches.append(osc_match)

            if all_rule_matches:
                return MonitorResult(
                    current_phase=self.current_phase,
                    phase_changed=False,
                    category_changed=False,
                    previous_phase=self.previous_phase,
                    rule_matches=all_rule_matches
                )
            return None

        # STEP 3: Add collected roles to role_history, update phase tracking,
        # and check plan compliance for EACH phase transition within the step
        phase_before_step = self.current_phase
        phase_changed_in_step = False

        for idx, role in enumerate(step_roles):
            self.role_history.append(role)
            new_phase = Phase(role)

            prev_phase_for_transition = None
            if self.current_phase is None:
                # First phase - just initialize
                self.current_phase = new_phase
                phase_changed_in_step = True
                prev_phase_for_transition = None  # First phase, no previous
            elif new_phase != self.current_phase:
                # Phase changed - update state
                prev_phase_for_transition = self.current_phase
                self.previous_phase = self.current_phase
                self.current_phase = new_phase
                phase_changed_in_step = True

            # Check plan compliance for EACH new phase within the step
            # This ensures compound commands like "edit && view" properly track P then L
            if self.enable_rules and self.rule_engine and phase_changed_in_step:
                plan_rule = self.rule_engine.rules.get("plan_compliance")
                if plan_rule and plan_rule.enabled:
                    plan_match = plan_rule.check(
                        current_phase=new_phase,
                        previous_phase=prev_phase_for_transition,
                        step_index=event.step_index,
                        command=event.command,
                        role_history=self.role_history[:role_history_len]  # History before this step
                    )
                    if plan_match:
                        all_rule_matches.append(plan_match)

        # STEP 4: Evaluate non-plan-compliance rules once per trajectory step
        # Use the final phase of the step and the full command
        final_phase = Phase(step_roles[-1])
        # Only pass previous_phase if there was a transition in this step
        # This helps dwell rules detect fresh phase changes
        phase_transition = self.previous_phase if phase_changed_in_step else None

        if self.enable_rules and self.rule_engine:
            rule_matches = self.rule_engine.evaluate(
                current_phase=final_phase,
                previous_phase=phase_transition,
                graph=self.graph_builder.G if self.graph_builder else None,
                step_index=event.step_index,  # Use actual trajectory step index
                command=event.command,  # Use full command, not split
                outcome=None,
                role_history=self.role_history[:role_history_len],  # Pass history before current step
                check_repeated_view=True,  # Check on the full command
                skip_plan_compliance=True  # Already checked in the loop above
            )
            if rule_matches:
                all_rule_matches.extend(rule_matches)

        # Check if blocking
        should_block = any(hasattr(m, 'block_execution') and m.block_execution for m in all_rule_matches)

        # Save violation counts from current rules (after tentative check may have incremented them)
        # This must be done BEFORE rollback regardless of blocking/non-blocking for consistency
        saved_violation_count_per_phase = None
        saved_violation_count_per_combination = None
        if self.rule_engine:
            plan_rule_current = self.rule_engine.rules.get("plan_compliance")
            if plan_rule_current and hasattr(plan_rule_current, 'violation_count_per_phase'):
                saved_violation_count_per_phase = plan_rule_current.violation_count_per_phase.copy()
                saved_violation_count_per_combination = plan_rule_current.violation_count_per_combination.copy()

        if should_block:
            # Rollback monitor state
            del self.role_history[role_history_len:]
            self.step_counter = step_counter_backup
            self.current_phase = current_phase_backup
            self.previous_phase = previous_phase_backup

            # Rollback graph builder state
            if self.graph_builder and graph_backup is not None:
                self.graph_builder.G = graph_backup
                self.graph_builder.previous_node = prev_node_backup
                self.graph_builder.node_signature_to_key = node_sig_backup
                if localization_nodes_backup is not None:
                    self.graph_builder.localization_nodes = localization_nodes_backup
                # Rollback prev_phases and created_tests to prevent misclassification
                # If P was tentatively added to prev_phases, it must be removed
                # Otherwise get_action_role() will think P was already executed
                if prev_phases_backup is not None:
                    self.graph_builder.prev_phases = prev_phases_backup
                if created_tests_gb_backup is not None:
                    self.graph_builder.created_tests = created_tests_gb_backup

            # Rollback test tracking sets
            # These are modified by get_action_role() during tentative evaluation
            self.created_tests = created_tests_backup
            self.created_dynamic_suites = created_dynamic_suites_backup

            # Rollback rule engine state with special handling for non-blocking rules and violation counts
            # During tentative evaluation, all rules update their internal state:
            # - PhaseTransitionRule/StrategyShiftRule increment trigger_count
            # - DwellTimeRule updates current_phase and dwell_count (non-blocking)
            # - RepeatedViewRule updates action_history and warned_commands (non-blocking)
            # - OscillationDetector updates triggered_patterns and pattern_counts (blocking)
            # - PlanComplianceRule updates seen_phases, violation_count, etc. (blocking)
            # - RuleEngine updates trigger_history for rate limiting
            # Since the action is blocked and never actually executed, blocking rule state
            # changes must be rolled back to maintain consistency.
            # HOWEVER:
            # 1. DwellTimeRule state (non-blocking) must persist even when blocking occurs
            # 2. RepeatedViewRule state (non-blocking) must persist even when blocking occurs
            # 3. PlanComplianceRule violation counts must persist for threshold tracking
            if self.rule_engine:
                # Preserve non-blocking rule states
                saved_dwell_states = {}
                saved_repeated_view_states = {}
                for rule_id, rule in self.rule_engine.rules.items():
                    if hasattr(rule, 'dwell_count'):  # DwellTimeRule
                        saved_dwell_states[rule_id] = {
                            'current_phase': rule.current_phase,
                            'dwell_count': rule.dwell_count,
                            'triggered_dwells': rule.triggered_dwells.copy() if hasattr(rule, 'triggered_dwells') else set()
                        }
                    elif hasattr(rule, 'action_history'):  # RepeatedViewRule
                        saved_repeated_view_states[rule_id] = {
                            'action_history': rule.action_history.copy(),
                            'warned_commands': rule.warned_commands.copy()
                        }

                # Rollback all rules (this replaces the entire rules dict with the backed-up version)
                if rules_backup is not None:
                    self.rule_engine.rules = rules_backup

                # Restore non-blocking rule states (should persist even when blocking occurs)
                for rule_id, saved_state in saved_dwell_states.items():
                    rule_restored = self.rule_engine.rules.get(rule_id)
                    if rule_restored:
                        rule_restored.current_phase = saved_state['current_phase']
                        rule_restored.dwell_count = saved_state['dwell_count']
                        if hasattr(rule_restored, 'triggered_dwells'):
                            rule_restored.triggered_dwells = saved_state['triggered_dwells']

                for rule_id, saved_state in saved_repeated_view_states.items():
                    rule_restored = self.rule_engine.rules.get(rule_id)
                    if rule_restored and hasattr(rule_restored, 'action_history'):
                        rule_restored.action_history = saved_state['action_history']
                        rule_restored.warned_commands = saved_state['warned_commands']

                # Restore plan compliance violation counts (already saved before if/else)
                if saved_violation_count_per_phase is not None:
                    plan_rule_restored = self.rule_engine.rules.get("plan_compliance")
                    if plan_rule_restored:
                        plan_rule_restored.violation_count_per_phase = saved_violation_count_per_phase
                        plan_rule_restored.violation_count_per_combination = saved_violation_count_per_combination

                if trigger_history_backup is not None:
                    self.rule_engine.trigger_history = trigger_history_backup

            return MonitorResult(
                current_phase=current_phase_backup, phase_changed=False, category_changed=False,
                previous_phase=previous_phase_backup, rule_matches=all_rule_matches
            )
        else:
            # Non-blocking: no rollback needed, violation counts already correctly updated
            if all_rule_matches:
                return MonitorResult(
                    current_phase=self.current_phase, phase_changed=False, category_changed=False,
                    previous_phase=self.previous_phase, rule_matches=all_rule_matches
                )
            return None

    def on_step(
        self,
        event: ActionEvent,
        thought: str = "",
        observation: str = ""
    ) -> Optional[MonitorResult]:
        """
        Process a single action event and detect phase transitions.

        Args:
            event: ActionEvent containing step information
            thought: Optional thought/reasoning text from this step
            observation: Optional observation/output from this step

        Returns:
            MonitorResult if a phase change occurred, None otherwise
        """
        # Build graph online if graph builder exists
        if self.graph_builder:
            build_online_graph_from_trajectory(
                builder=self.graph_builder,
                step_idx=self.step_counter,
                thought=thought,
                action=event.command,
                observation=observation,
                parser=self.parser
            )
            self.step_counter += 1

        # Parse the command to extract structured information
        parsed_commands = self.parser.parse(event.command)

        if not parsed_commands:
            # Unable to parse, skip this step
            return None

        # STEP 1: Collect roles from all split commands in this trajectory step
        step_roles = []  # Roles collected in this step (non-general only)
        last_role_in_step = None
        all_rule_matches = []

        # Compute outcome for the full command (using observation from last split command)
        outcome = None

        for cmd_idx, cmd_info in enumerate(parsed_commands):
            tool = cmd_info.get("tool")
            subcommand = cmd_info.get("subcommand")
            command = cmd_info.get("command")
            args = cmd_info.get("args", [])
            flags = cmd_info.get("flags", {})

            # Compute outcome for last command in sequence
            is_last_command = (cmd_idx == len(parsed_commands) - 1)
            if is_last_command:
                outcome = check_command_outcome(command, observation, tool, subcommand, args)

            role = get_action_role(
                tool=tool, subcommand=subcommand, command=command, args=args, flags=flags,
                prev_roles=self.role_history, created_tests=self.created_tests,
                created_dynamic_suites=self.created_dynamic_suites
            )

            # Check plan compliance rule even for "general" roles to detect ending flags
            if role == "general":
                if self.enable_rules and self.rule_engine:
                    plan_rule = self.rule_engine.rules.get("plan_compliance")
                    if plan_rule and plan_rule.enabled:
                        plan_match = plan_rule.check(
                            current_phase=None,
                            previous_phase=self.current_phase,
                            step_index=event.step_index,
                            command=event.command
                        )
                        if plan_match:
                            all_rule_matches.append(plan_match)
                continue

            # Only collect role if it's different from the last role in this step
            if role != last_role_in_step:
                step_roles.append(role)
                last_role_in_step = role

        # STEP 2: If no non-general roles, return early
        if not step_roles:
            if all_rule_matches:
                return MonitorResult(
                    current_phase=self.current_phase,
                    phase_changed=False,
                    category_changed=False,
                    previous_phase=self.previous_phase,
                    rule_matches=all_rule_matches
                )
            return None

        # STEP 3: Add collected roles to role_history, detect phase changes,
        # and check plan compliance for EACH phase transition within the step
        phase_changed = False
        category_changed = False
        role_history_len_before_step = len(self.role_history)

        for role in step_roles:
            self.role_history.append(role)
            new_phase = Phase(role)

            prev_phase_for_transition = None
            if self.current_phase is None:
                # First phase - just initialize
                self.current_phase = new_phase
                phase_changed = True
                prev_phase_for_transition = None
            elif new_phase != self.current_phase:
                # Phase changed - detect category change
                category_changed = not new_phase.in_same_group(self.current_phase)
                prev_phase_for_transition = self.current_phase
                self.previous_phase = self.current_phase
                self.current_phase = new_phase
                phase_changed = True

            # Check plan compliance for EACH new phase within the step
            # This ensures compound commands like "edit && view" properly track P then L
            if phase_changed and self.enable_rules and self.rule_engine:
                plan_rule = self.rule_engine.rules.get("plan_compliance")
                if plan_rule and plan_rule.enabled:
                    plan_match = plan_rule.check(
                        current_phase=new_phase,
                        previous_phase=prev_phase_for_transition,
                        step_index=event.step_index,
                        command=event.command,
                        role_history=self.role_history[:role_history_len_before_step]
                    )
                    if plan_match:
                        all_rule_matches.append(plan_match)

        # STEP 4: Evaluate non-plan-compliance rules once per trajectory step
        final_phase = Phase(step_roles[-1])
        phase_transition = self.previous_phase if phase_changed else None

        if self.enable_rules and self.rule_engine:
            rule_matches = self.rule_engine.evaluate(
                current_phase=final_phase,
                previous_phase=phase_transition,
                graph=self.graph_builder.G if self.graph_builder else None,
                step_index=event.step_index,  # Use actual trajectory step index
                command=event.command,  # Use full command, not split
                outcome=outcome,
                check_repeated_view=True,  # Check on the full command
                skip_plan_compliance=True  # Already checked in the loop above
            )
            if rule_matches:
                all_rule_matches.extend(rule_matches)

        # STEP 5: Return result if phase changed or rules triggered
        if phase_changed or all_rule_matches:
            return MonitorResult(
                current_phase=final_phase,
                phase_changed=phase_changed,
                category_changed=category_changed,
                previous_phase=self.previous_phase,
                rule_matches=all_rule_matches
            )

        return None

    def _build_think_node(self, step_idx: int, thought: str, command: str):
        """
        Build a "think" node in the graph for steps with empty actions.

        These nodes track reasoning flow when action parsing fails, allowing
        detection of thought-level oscillations while preserving valid thinking steps.

        Args:
            step_idx: Step index for this node
            thought: Agent's reasoning/thought text
            command: Original command string (empty or unparseable)
        """
        import hashlib

        # Create node signature from thought (first 200 chars for consistency)
        thought_snippet = thought[:200] if thought else ""
        thought_hash = hashlib.md5(thought_snippet.encode('utf-8')).hexdigest()[:8]
        node_key = f"think_{thought_hash}"

        # Add node to graph
        self.graph_builder.G.add_node(
            node_key,
            step_index=step_idx,
            label="think",
            full_action=command,  # Store original (empty) command
            thought=thought,
            observation=""
        )

        # Add edge from previous node
        if self.graph_builder.previous_node:
            self.graph_builder.G.add_edge(self.graph_builder.previous_node, node_key)

        self.graph_builder.previous_node = node_key

        # Update signature tracking
        self.graph_builder.node_signature_to_key[node_key] = node_key

    def reset(self):
        """Reset the monitor state to initial conditions."""
        self.current_phase = None
        self.previous_phase = None
        self.role_history.clear()
        self.created_tests.clear()
        self.created_dynamic_suites.clear()
        self.thought_history.clear()

        # Reset rule engine (includes trigger history)
        if self.rule_engine:
            self.rule_engine.reset()
            self.rule_engine.trigger_history.clear()

        # Reset graph builder
        if self.graph_builder:
            self.graph_builder = GraphBuilder()
            self.step_counter = 1  # Start from 1

    def get_current_phase(self) -> Optional[Phase]:
        """Get the current phase."""
        return self.current_phase

    def get_phase_history(self) -> list[str]:
        """Get the full history of roles (including duplicates)."""
        return self.role_history.copy()

    def get_unique_phases(self) -> list[str]:
        """Get unique phases in order of first appearance."""
        seen = set()
        unique = []
        for role in self.role_history:
            if role not in seen:
                seen.add(role)
                unique.append(role)
        return unique

    def save_graph(self, output_dir: str, instance_id: str) -> Optional[str]:
        """
        Save the built graph to disk.

        Args:
            output_dir: Base output directory for saving graphs
            instance_id: Instance identifier (e.g., 'astropy__astropy-12907')

        Returns:
            Path to saved JSON file, or None if graph builder is not available
        """
        if not self.graph_builder:
            return None

        return self.graph_builder.finalize_and_save(output_dir, instance_id)

    def get_graph(self):
        """
        Get the current graph (without saving).

        Returns:
            NetworkX MultiDiGraph or None if graph builder is not available
        """
        if not self.graph_builder:
            return None

        return self.graph_builder.G

    def update_intended_plan(self, refined_plan_phases: list[str]) -> bool:
        """
        Update the intended plan in the plan compliance rule from the current index.

        This method is designed to be called after receiving refined plan phases
        from an external planner (e.g., plan_refiner). It updates the plan compliance
        rule's intended plan dynamically while maintaining state consistency.

        Args:
            refined_plan_phases: List of phase labels for the new plan
                                 (e.g., ["L_navigate", "L_reproduce", "P", "V_newly_generated_test"])

        Returns:
            True if update was successful, False if plan compliance rule is not available

        Example:
            # After getting refined phases from plan_refiner
            success = monitor.update_intended_plan(refiner_output.refined_plan_phases)
            if success:
                print("Plan updated successfully")
        """
        if not self.rule_engine:
            return False

        plan_rule = self.rule_engine.rules.get("plan_compliance")
        if not plan_rule or not hasattr(plan_rule, 'update_plan'):
            return False

        # Get current plan state before update
        old_plan = plan_rule.intended_plan.copy()
        old_index = plan_rule.plan_index

        # Update the plan
        plan_rule.update_plan(refined_plan_phases)

        # Log the update
        print(f"[MONITOR] Plan updated at index {old_index}")
        print(f"[MONITOR] Old plan: {old_plan}")
        print(f"[MONITOR] New plan: {plan_rule.intended_plan}")
        print(f"[MONITOR] Next expected phase: {plan_rule.intended_plan[plan_rule.plan_index] if plan_rule.plan_index < len(plan_rule.intended_plan) else 'Plan complete'}")

        return True
