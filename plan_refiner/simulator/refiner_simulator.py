#!/usr/bin/env python3
"""
Simulator for testing the Plan Refiner.

Reads trajectory files, extracts actions step-by-step, feeds them to both
the monitor and the refiner. When plan_monitor rules are triggered, the
refiner is invoked to critique and provide a refined plan.

Sample usage:
python plan_refiner/simulator/refiner_simulator.py mini-swe-agent/outputs/swebench/gpt-5-mini/astropy__astropy-8707/astropy__astropy-8707.traj.json

REFINER OUTPUT EXAMPLE:
ANALYSIS:
--------------------------------------------------------------------------------
### 1. Inferred High-Level Plan So Far
- Search the repository for the FITS header/card implementation to locate Header.fromstring and Card.fromstring.
- Inspect Header.fromstring implementation in astropy/io/fits/header.py to see how it splits and parses the header.
- Inspect Card.fromstring and related helpers (_pad) in astropy/io/fits/card.py to understand how card images are processed.
- Inspect util.py to find encode_ascii/decode_ascii helpers that should be used when handling bytes.

### 2. Evaluation of the Plan's Logic
- The overall strategy — find the methods that must accept bytes and update them — is correct and appropriate for the bug.
- However the agent has spent many steps in navigation without (yet) moving to reproduction or making a concrete change. The plan lacks a reproduction step (a failing test) and hasn't checked the behavior/contract of the helper decode_ascii function which is critical to the fix.
- Conceptually the hypothesis is right: Header.fromstring and Card.fromstring currently assume text strings and therefore will mis-handle Python 3 bytes. The right fix is to decode bytes to str early (with appropriate ASCII decoding) rather than changing downstream logic that expects str.
- Potential subtlety: the codebase has both text and binary-oriented code paths (e.g., encode_ascii used to build regexes), so blindly converting everything to bytes or str in the wrong place could create mismatches elsewhere. That argues for decoding only at the public API boundary (Header.fromstring, Card.fromstring) rather than changing lower-level utilities.

### 3. Review of Implementation and Final Code
- Successful actions:
  - Correctly located Header.fromstring and Card.fromstring, and found _pad and encode/decode helpers. This clarifies where to apply a change.
- Missing or incomplete actions:
  - The agent did not open the implementation of util.decode_ascii (it found its name but didn't inspect its behavior). That is important to know how non-ASCII bytes are handled (raise vs replace).
  - No reproduction/test was created to demonstrate the failure on Python 3 bytes. Without a failing test, it's easy to make a fix that isn't covered or to miss regressions.
  - No code edits were made yet; there is no patch to evaluate.
- Likely correct minimal fix (not yet implemented):
  - Decode bytes/bytearray inputs to str at the entry of Header.fromstring and Card.fromstring using the repository's decode_ascii helper (or equivalent) so the existing string-based parsing continues to work.
  - Also ensure sep is a str (if caller passes bytes).
  - This minimal change should resolve the immediate problem (accepting Python 3 bytes) while keeping existing code paths intact.
- Risks that must be confirmed:
  - decode_ascii semantics (does it raise on non-ASCII bytes or replace?) must be reviewed to match project policy (probably strict ASCII).
  - There are places where the code uses regexes or comparisons expecting bytes; but because Header.fromstring historically accepted str, decoding bytes to str is the safer choice. Still, run tests to catch any interactions.

NEW PLAN:
--------------------------------------------------------------------------------
### Customized High-Level Plan

1. Inspect util.decode_ascii to confirm its behavior
   - Open and read the decode_ascii implementation to confirm it accepts bytes and decodes using ASCII (and how it handles decoding errors — raise vs replace).
   - Decide whether decode_ascii is appropriate to use here (likely yes). If it replaces characters silently, note that test expectations should reflect that; if it raises, tests should expect a UnicodeDecodeError for non-ASCII header bytes.

2. Add targeted unit tests to reproduce the bug
   - Create a new test that calls Header.fromstring with an ASCII-only bytes object representing a minimal header (e.g., one simple key card and END) and asserts the header is parsed correctly (keyword/value present).
   - Create another test that calls Card.fromstring with a single card image provided as bytes and asserts keyword/value parsed correctly.
   - Add at least one test for non-ASCII bytes input to assert the expected behavior (based on decode_ascii semantics discovered in step 1): either expect an exception or a specific decoding behavior.

3. Implement the minimal, local change(s)
   - Modify Header.fromstring: at the very beginning, if data is bytes or bytearray, convert to str using decode_ascii. Also ensure sep is a str by decoding it if bytes were provided. Keep conversion local and early so subsequent logic (string slicing, comparisons, index, join) operates on str.
   - Modify Card.fromstring: at the start, if image is bytes/bytearray, convert to str using decode_ascii before calling _pad or other string operations.
   - Ensure these conversions are confined to these entry points to avoid changing semantics elsewhere.

4. Run the new tests (unit-level)
   - Execute the newly added tests to verify the failing reproduction becomes passing after the change.
   - If tests fail, inspect tracebacks to see whether non-ASCII bytes or some other place expects bytes; adjust strategy accordingly (e.g., enforce stricter decoding or adapt tests).

5. Run the full FITS/IO test subset or full test suite (regression)
   - Run the relevant existing tests (or full test suite if feasible) to detect regressions introduced by the change.
   - If failures are found, prioritize fixes by reading failing tests: likely fixes are limited to other public APIs that can receive bytes; either decode there similarly or adjust code paths that expect bytes.

6. Iterate based on test feedback
   - If any failing tests indicate other code paths expect bytes instead of str, examine those call sites and handle bytes at the appropriate public API boundary instead of changing internals.
   - If decode_ascii behavior causes unexpected changes (e.g., silent replacement), consider using a stricter decoding call or explicit error handling and update tests accordingly.

7. Prepare a concise commit message and tests
   - When tests pass, prepare a patch that includes:
     - The small code changes (Header.fromstring and Card.fromstring decoding).
     - The added unit tests demonstrating the bytes input is accepted.
     - A brief changelog note or docstring update clarifying that fromstring accepts bytes on Python 3.

Notes/Guidance:
- Keep changes minimal and localized to the boundary functions to avoid unintended binary/text mismatches elsewhere.
- Prefer decode_ascii (existing helper) rather than ad-hoc decoding to stay consistent with project policies.
- If you find decode_ascii raises for non-ASCII bytes and the project expects tolerant behavior, discuss whether to accept only ASCII and raise or to replace/ignore non-ASCII bytes — tests should codify the chosen behavior.
"""

from __future__ import annotations
import re
import json
import argparse
from pathlib import Path
from typing import Optional

from plan_monitor.monitor import StatefulPhaseMonitor
from plan_monitor.simulator.mini_extractor import ActionExtractor
from plan_refiner.refiner import PlanRefiner, RefinerConfig
from plan_refiner.types import RefinerInput, RefinerTrajectoryStep, RuleTrigger, StateSummary
from plan_refiner.models import MockModel


class RefinerSimulator:
    """
    Simulates plan refinement by replaying trajectory files.

    The simulator:
    1. Reads actions from a trajectory file
    2. Feeds each action to the plan_monitor
    3. When monitor rules are triggered, invokes the plan_refiner
    4. Prints the analysis and refined plan
    """

    def __init__(
        self,
        trajectory_path: str | Path,
        refiner_config: Optional[RefinerConfig] = None,
        min_steps_between_refinements: int = 5,
        use_mock_model: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the simulator.

        Args:
            trajectory_path: Path to trajectory JSON file
            refiner_config: Optional refiner configuration
            min_steps_between_refinements: Minimum steps between refinements (default: 5)
            use_mock_model: Use mock model instead of real LLM (default: True)
            verbose: Print all steps, not just refinements (default: False)
        """
        self.trajectory_path = Path(trajectory_path)
        self.min_steps_between_refinements = min_steps_between_refinements
        self.verbose = verbose

        # Initialize components
        self.monitor = StatefulPhaseMonitor(enable_rules=True)
        self.extractor = ActionExtractor(trajectory_path)

        # Initialize refiner with model from config
        if use_mock_model:
            from plan_refiner.models import MockModel
            model = MockModel()
        else:
            # Load model from configuration file
            config_path = refiner_config.template_path if refiner_config else "plan_refiner/config/default.yaml"
            model = PlanRefiner.create_model_from_config(config_path)

        # Override min_steps_between_refinements in config if provided
        if refiner_config is None:
            refiner_config = RefinerConfig()
        refiner_config.min_steps_between_refinements = min_steps_between_refinements

        self.refiner = PlanRefiner(model=model, config=refiner_config)

        # Track trajectory for refiner
        self.trajectory_steps: list[RefinerTrajectoryStep] = []
        self.all_rule_triggers: list[RuleTrigger] = []

        # Get issue description from trajectory
        self.issue_description = self._extract_issue_description()

    def _extract_issue_description(self) -> str:
        """
        Extract issue description from trajectory file.

        Looks for <pr_description> tags in the first user message.

        Returns:
            Issue description string
        """
        with open(self.trajectory_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Get messages
        messages = data.get('messages', [])

        # Look for pr_description in first user message
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')

                # Extract content between <pr_description> tags
                # Pattern: <pr_description>\nConsider the following PR description:\n{TASK}\n</pr_description>
                pr_match = re.search(
                    r'<pr_description>\s*(?:Consider the following PR description:\s*)?(.*?)\s*</pr_description>',
                    content,
                    re.DOTALL | re.IGNORECASE
                )
                if pr_match:
                    return pr_match.group(1).strip()

                # Fallback: look for "Please solve this issue:" pattern
                issue_match = re.search(
                    r'Please solve this issue:\s*(.*?)(?=\n\n|You can execute|$)',
                    content,
                    re.DOTALL
                )
                if issue_match:
                    issue_text = issue_match.group(1).strip()
                    if len(issue_text) > 1000:
                        issue_text = issue_text[:1000] + "..."
                    return issue_text

        # Fallback: use instance_id
        instance_id = data.get('instance_id', 'unknown')
        return f"Issue: {instance_id} (description not found in trajectory)"

    def run(self):
        """
        Run the simulation.

        Processes all actions from the trajectory, monitors phase transitions,
        and triggers plan refinement when monitor rules are satisfied.
        """
        instance_id = self.extractor.get_instance_id()
        message_count = self.extractor.get_message_count()

        print(f"{'='*80}")
        print(f"Plan Refiner Simulation")
        print(f"{'='*80}")
        print(f"Instance ID: {instance_id}")
        print(f"Total messages: {message_count}")
        print(f"Issue Description:")
        print(f"{self.issue_description[:200]}...")
        print(f"{'='*80}\n")

        refinement_count = 0
        last_refinement_step = -1

        for event, thought, observation in self.extractor.extract_actions():
            # Add to trajectory
            step = RefinerTrajectoryStep(
                step_index=event.step_index,
                thought=thought,
                action=event.command,
                observation=observation
            )
            self.trajectory_steps.append(step)

            # Process through monitor
            result = self.monitor.on_step(event, thought=thought, observation=observation)

            # Collect rule triggers
            if result and result.rule_matches:
                for match in result.rule_matches:
                    trigger = RuleTrigger(
                        rule_id=getattr(match, 'rule_id', 'unknown'),
                        message=getattr(match, 'message', ''),
                        step_index=event.step_index,
                        metadata=getattr(match, 'metadata', {})
                    )
                    self.all_rule_triggers.append(trigger)

            if self.verbose:
                print(f"\n[Step {event.step_index}]")
                print(f"Command: {event.command[:100]}{'...' if len(event.command) > 100 else ''}")
                if result:
                    phase = self.monitor.get_current_phase()
                    print(f"Phase: {phase}")
                    if result.rule_matches:
                        print(f"Rules triggered: {len(result.rule_matches)}")

            # Trigger refinement when monitor rules are satisfied
            # Pass step info to refiner, which will handle cooling period internally
            if result and result.rule_matches:
                rule_ids = [m.rule_id for m in result.rule_matches]
                trigger_reason = f"Monitor rules triggered: {', '.join(rule_ids)}"

                # Call refiner (it will handle cooling period internally)
                is_full_refinement = self._run_refinement(
                    event.step_index,
                    trigger_reason,
                    last_refinement_step
                )

                # Only update last_refinement_step and count if full refinement occurred
                if is_full_refinement:
                    refinement_count += 1
                    last_refinement_step = event.step_index

        # Final summary
        print(f"\n{'='*80}")
        print(f"Simulation Complete")
        print(f"{'='*80}")
        print(f"Total steps: {len(self.trajectory_steps)}")
        print(f"Refinements triggered: {refinement_count}")
        print(f"Total rules triggered by monitor: {len(self.all_rule_triggers)}")
        print(f"{'='*80}\n")

    def _run_refinement(self, step_index: int, reason: str, last_refinement_step: int) -> bool:
        """
        Run plan refinement at the current state.

        Args:
            step_index: Current step index
            reason: Reason for triggering refinement
            last_refinement_step: Step index of last refinement

        Returns:
            True if full refinement occurred, False if within cooling period
        """
        print(f"\n{'='*80}")
        print(f"PLAN REFINEMENT TRIGGERED at Step {step_index}")
        print(f"Reason: {reason}")
        print(f"{'='*80}\n")

        # Build state summary from monitor
        state_summary = StateSummary(
            current_phase=str(self.monitor.get_current_phase()) if self.monitor.get_current_phase() else None,
            phase_history=self.monitor.get_phase_history(),
            # unique_phases=self.monitor.get_unique_phases(),
            rule_triggers=self.all_rule_triggers.copy(),
            # graph_info={
            #     "node_count": self.monitor.graph_builder.G.number_of_nodes() if self.monitor.graph_builder else 0,
            #     "edge_count": self.monitor.graph_builder.G.number_of_edges() if self.monitor.graph_builder else 0,
            # },
            step_count=step_index + 1
        )

        # Build refiner input
        refiner_input = RefinerInput(
            issue_description=self.issue_description,
            trajectory=self.trajectory_steps.copy(),
            state_summary=state_summary
        )

        # Run refinement with step information for cooling period check
        try:
            # Print prompts in verbose mode for debugging
            if self.verbose:
                from plan_refiner.formatters import TrajectoryFormatter, StateSummaryFormatter

                trajectory_text = TrajectoryFormatter.format_trajectory(
                    refiner_input.trajectory,
                    max_steps=self.refiner.config.max_trajectory_steps
                )
                state_summary_text = StateSummaryFormatter.format_state_summary(
                    refiner_input.state_summary
                )

                system_prompt, user_prompt = self.refiner.prompt_builder.build_prompt(
                    issue_description=refiner_input.issue_description,
                    trajectory_text=trajectory_text,
                    state_summary_text=state_summary_text
                )

                print("DEBUG: SYSTEM PROMPT:")
                print("-" * 80)
                print(system_prompt)
                print()

                print("DEBUG: USER PROMPT:")
                print("-" * 80)
                # print(user_prompt[:1000] + "..." if len(user_prompt) > 1000 else user_prompt)
                print(user_prompt)
                print()

            # Call refiner with step information
            output = self.refiner.refine_plan(
                refiner_input,
                current_step=step_index,
                last_refinement_step=last_refinement_step
            )

            # Check if we're in cooling period
            if output.is_cooling_period:
                print("🧊 COOLING PERIOD - Refinement skipped")
                print(f"Steps since last refinement: {step_index - last_refinement_step}")
                print(f"Minimum required: {self.refiner.config.min_steps_between_refinements}")
                print()

                if output.cooling_period_message:
                    print("MONITOR MESSAGE:")
                    print("-" * 80)
                    print(output.cooling_period_message)
                    print()
                else:
                    print("(No monitor message available)")
                    print()

                return False  # Did not perform full refinement

            # Full refinement occurred
            print("✅ FULL REFINEMENT PERFORMED")
            print()

            # Print results
            print("ANALYSIS:")
            print("-" * 80)
            print(output.analysis)
            print()

            print("NEW PLAN:")
            print("-" * 80)
            print(output.new_plan)
            print()

            return True  # Full refinement performed

        except Exception as e:
            print(f"Error during refinement: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """CLI entry point for the refiner simulator."""
    parser = argparse.ArgumentParser(
        description="Simulate plan refinement with trajectory files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run simulation (triggers when monitor rules are satisfied)
  python plan_refiner/simulator/refiner_simulator.py mini-swe-agent/outputs/swebench/gpt-5-mini/astropy__astropy-7606/astropy__astropy-7606.traj.json

  # Run with verbose output
  python plan_refiner/simulator/refiner_simulator.py trajectory.json --verbose

  # Adjust minimum steps between refinements
  python plan_refiner/simulator/refiner_simulator.py trajectory.json --min-steps 10
        """
    )

    parser.add_argument(
        'trajectory',
        type=str,
        help='Path to trajectory JSON file'
    )

    parser.add_argument(
        '--min-steps',
        type=int,
        default=None,
        help='Minimum steps between refinements (default: from config)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print all steps, not just refinements'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='plan_refiner/config/default.yaml',
        help='Path to configuration file (default: plan_refiner/config/default.yaml)'
    )

    args = parser.parse_args()

    # Validate trajectory file exists
    trajectory_path = Path(args.trajectory)
    if not trajectory_path.exists():
        print(f"Error: Trajectory file not found: {trajectory_path}")
        return 1

    # Create config
    config = RefinerConfig(
        template_path=args.config,
        max_trajectory_steps=None,  # Include all steps
        enable_parsing=True
    )

    # Load min_steps from config, CLI arg overrides
    min_steps = args.min_steps
    if min_steps is None:
        min_steps = PlanRefiner.get_min_steps_from_config(args.config)

    # Run simulation
    try:
        simulator = RefinerSimulator(
            trajectory_path=trajectory_path,
            refiner_config=config,
            min_steps_between_refinements=min_steps,
            use_mock_model=False,
            verbose=args.verbose
        )
        simulator.run()
        return 0
    except Exception as e:
        print(f"Error running simulation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
