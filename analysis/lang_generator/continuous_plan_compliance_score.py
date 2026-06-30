"""
Continuous Plan Hypothesis Test: Compute numeric compliance scores for agent trajectories.

CORE LOGIC:
Computes a continuous compliance score (0 to 1) based on three components:

1. S1 (PPF) - Vocabulary Deviation (extra terminal types):
   S1 = m / (m + |X|)
   where m = number of distinct expected phases, X = set of distinct out-of-alphabet phases
   Perfect score (S1=1) when no extra phase types exist

2. S2 (PPC)- Required Production Coverage (recall):
   S2 = (required symbols seen) / (required symbols)
   Perfect score (S2=1) when all expected phases appear

3. S3 (POC) - Order Conformance (based on first appearances):
   S3 = (longest increasing subsequence of first appearances) / (expected phase sequence length)
   Perfect score (S3=1) when first appearances of all expected phases are in strictly increasing order
   Note: Phase revisits are allowed; only first appearance order matters

Final Score = Geometric Mean(S1, S2, S3) = (S1 * S2 * S3)^(1/3)

PREFIX MATCHING (asymmetric):
- "L_reproduce_regression_test" matches expected "L_reproduce" ✓ (actual can be more specific)
- "L_reproduce" does NOT match expected "L_reproduce_regression_test" ✗ (actual insufficient)

Expected Order:
- plan: L_navigate → L_reproduce → P → V_newly_generated_test
"""

from __future__ import annotations
import json
import math
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
import numpy as np


@dataclass
class PlanTestConfig:
    """Configuration for continuous plan hypothesis test."""
    dataset: str = "SWE-Bench-Verified"
    agent: str = "SWE-agent"
    models: Optional[List[str]] = None
    setting: str = "plan"
    data_dir: str = "artifacts"
    expected_order: Tuple[str, ...] = ("L_navigate", "L_reproduce", "P", "V_newly_generated_test")


@dataclass
class ComplianceScore:
    """Compliance score breakdown."""
    s1_vocabulary: float  # Vocabulary deviation score
    s2_coverage: float    # Required production coverage score
    s3_order: float       # Order conformance score
    final_score: float    # Geometric mean of S1, S2, S3

    # Detailed breakdown
    num_expected_phases: int
    num_extra_phases: int
    num_required_seen: int
    num_required_total: int
    lcs_length: int
    expected_length: int


# Setting to expected order mapping
SETTING_TO_EXPECTED_ORDER = {
    "plan": ("L_navigate", "L_reproduce", "P", "V_newly_generated_test"),
}


def extract_phase_prefix(lang_item: str) -> str:
    """
    Extract phase prefix from language item (e.g., 'L_navigate_2' -> 'L_navigate').

    Args:
        lang_item: Language item from trajectory (e.g., 'L_navigate_2', 'P_1')

    Returns:
        Phase prefix without run-length suffix
    """
    parts = lang_item.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return lang_item


def phase_matches_expected(actual_phase: str, expected_phase: str) -> bool:
    """
    Check if an actual phase matches an expected phase using prefix matching.

    Prefix matching rule (asymmetric):
    - Exact match: actual_phase == expected_phase ✓
    - Prefix match: actual_phase starts with expected_phase + "_" ✓
    - Reverse does NOT work: "L_reproduce" does NOT match "L_reproduce_regression_test"

    Args:
        actual_phase: Phase from languatory
        expected_phase: Phase from expected_order

    Returns:
        True if actual_phase satisfies the expected_phase requirement
    """
    if actual_phase == expected_phase:
        return True
    return actual_phase.startswith(expected_phase + "_")


def extract_phase_sequence(languatory: List[str]) -> List[str]:
    """
    Extract ordered sequence of distinct phases from languatory.

    Args:
        languatory: List of language items with run-length suffixes

    Returns:
        Ordered list of phase prefixes (preserves order, keeps duplicates)
    """
    return [extract_phase_prefix(item) for item in languatory]


def compute_longest_increasing_subsequence_length(
    first_appearances: Dict[str, int],
    expected_order: Tuple[str, ...]
) -> int:
    """
    Compute longest subsequence of expected phases with strictly increasing first appearances.

    This checks if the first appearances of expected phases conform to the expected order,
    allowing phase revisits (only first appearance matters).

    Args:
        first_appearances: Mapping from phase to its first appearance index
        expected_order: Expected phase order

    Returns:
        Length of longest subsequence with increasing first appearances
    """
    # Extract first appearance indices for expected phases (None if missing)
    indices = []
    for expected_phase in expected_order:
        found_idx = None
        for actual_phase, idx in first_appearances.items():
            if phase_matches_expected(actual_phase, expected_phase):
                if found_idx is None or idx < found_idx:
                    found_idx = idx
        indices.append(found_idx)

    # Find longest increasing subsequence (LIS) among non-None indices
    # dp[i] = length of longest increasing subsequence ending at position i
    n = len(indices)
    if n == 0:
        return 0

    dp = [0] * n
    for i in range(n):
        if indices[i] is not None:
            dp[i] = 1  # At minimum, the phase itself
            for j in range(i):
                if indices[j] is not None and indices[j] < indices[i]:
                    dp[i] = max(dp[i], dp[j] + 1)

    return max(dp) if dp else 0


def extract_first_appearances(languatory: List[str]) -> Dict[str, int]:
    """
    Extract first appearance indices for each unique phase, accounting for run lengths.

    Args:
        languatory: List of language items with run-length suffixes

    Returns:
        Dictionary mapping phase prefix to its cumulative first appearance index
    """
    first_appearances = {}
    cumulative_idx = 0

    for item in languatory:
        phase = extract_phase_prefix(item)

        # Extract run length from suffix
        parts = item.rsplit('_', 1)
        run_length = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1

        if phase not in first_appearances:
            first_appearances[phase] = cumulative_idx

        cumulative_idx += run_length

    return first_appearances


def compute_compliance_score(
    languatory: List[str],
    expected_order: Tuple[str, ...]
) -> ComplianceScore:
    """
    Compute continuous compliance score for a trajectory.

    Args:
        languatory: Trajectory language items
        expected_order: Expected phase order

    Returns:
        ComplianceScore object with detailed breakdown
    """
    # Extract phase information
    phase_sequence = extract_phase_sequence(languatory)
    distinct_phases = set(phase_sequence)
    first_appearances = extract_first_appearances(languatory)

    # S1: Vocabulary Deviation
    # Count extra phases (not matching any expected phase)
    extra_phases = set()
    for phase in distinct_phases:
        is_expected = any(phase_matches_expected(phase, exp) for exp in expected_order)
        if not is_expected:
            extra_phases.add(phase)

    m = len(expected_order)  # Number of expected distinct phases
    num_extra = len(extra_phases)
    s1_vocabulary = m / (m + num_extra) if (m + num_extra) > 0 else 0.0

    # S2: Required Production Coverage (recall)
    # Count how many expected phases appear in the trajectory
    required_seen = set()
    for expected_phase in expected_order:
        for actual_phase in distinct_phases:
            if phase_matches_expected(actual_phase, expected_phase):
                required_seen.add(expected_phase)
                break

    num_required_seen = len(required_seen)
    num_required_total = len(expected_order)
    s2_coverage = num_required_seen / num_required_total if num_required_total > 0 else 0.0

    # S3: Order Conformance (based on first appearances)
    # Find longest subsequence of expected phases with increasing first appearances
    lis_length = compute_longest_increasing_subsequence_length(first_appearances, expected_order)
    expected_length = len(expected_order)
    s3_order = lis_length / expected_length if expected_length > 0 else 0.0

    # Final Score: Geometric Mean
    if s1_vocabulary > 0 and s2_coverage > 0 and s3_order > 0:
        final_score = (s1_vocabulary * s2_coverage * s3_order) ** (1/3)
    else:
        final_score = 0.0

    return ComplianceScore(
        s1_vocabulary=s1_vocabulary,
        s2_coverage=s2_coverage,
        s3_order=s3_order,
        final_score=final_score,
        num_expected_phases=m,
        num_extra_phases=num_extra,
        num_required_seen=num_required_seen,
        num_required_total=num_required_total,
        lcs_length=lis_length,
        expected_length=expected_length
    )

def main():
    """Main entry point for continuous plan hypothesis testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute continuous compliance scores for agent trajectories"
    )


if __name__ == "__main__":
    main()