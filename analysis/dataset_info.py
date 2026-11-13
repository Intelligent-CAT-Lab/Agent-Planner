"""Canonical dataset sizes used as denominators for success / resolution rates.

A SWE-bench Pro *report* grades only the subset of instances that could be
evaluated, so dividing a resolved count by the report size overstates the rate
and makes configurations with different report coverage incomparable. The correct
denominator is the number of instances the dataset actually contains for the
language under analysis. That count is computed here from the dataset itself
(``swe_bench_pro_full.csv``, via its ``repo_language`` column) rather than
hardcoded, so it stays correct when a language other than the current default
(python) is analysed.
"""
from __future__ import annotations

import csv
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
PRO_DATASET_CSV = REPO / "SWE-bench_Pro-os" / "swe_bench_pro_full.csv"


@lru_cache(maxsize=None)
def swebench_pro_size(language: str = "python") -> int:
    """Count SWE-bench Pro instances whose ``repo_language`` is ``language``."""
    # patch / problem_statement cells exceed csv's default field size limit.
    csv.field_size_limit(sys.maxsize)
    with PRO_DATASET_CSV.open(newline="", encoding="utf-8") as stream:
        return sum(
            1 for row in csv.DictReader(stream)
            if row["repo_language"].strip().lower() == language.lower()
        )


@lru_cache(maxsize=None)
def swebench_verified_size() -> int:
    """Size of the SWE-bench Verified test split (loaded once; falls back to 500)."""
    try:
        from datasets import load_dataset
        return len(load_dataset("princeton-nlp/SWE-bench_Verified", split="test"))
    except Exception:
        return 500  # SWE-bench Verified is a fixed 500-instance benchmark


def dataset_size(dataset: str, language: str = "python") -> Optional[int]:
    """Full instance count to divide by for a success / resolution rate.

    Derived from the dataset itself so it stays correct as languages/splits change.
    Returns None for an unknown dataset, so the caller falls back to its own
    observed count.
    """
    if dataset == "swebench-pro":
        return swebench_pro_size(language)
    if dataset == "swebench":
        return swebench_verified_size()
    return None
