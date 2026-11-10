"""
Shared schema + data sources for the (replay-based) pattern-resolution analysis.

The pair ``analysis/collect_pattern_resolution.py`` (writer) and
``analysis/analyze_pattern_resolution.py`` (reader) both build on this package so they
never drift. Everything signal-related is derived from the production GL-Guard runtime
(:func:`analysis.replay.replay_monitor.build_study_runtime`), so the whole pipeline is
**signal-count-agnostic**: add or remove a signal in the ``.glg`` spec and the tidy
table simply gains or loses a named column — no offset math, no fixed header widths.

Modules:
  * :mod:`analysis.pattern_resolution.schema`  -- column model + long/jsonl/wide I/O.
  * :mod:`analysis.pattern_resolution.sources` -- trajectory discovery, official labels,
    cost/step + planner.json metadata, and the GL-Guard replay-detail driver.
"""
from analysis.pattern_resolution.schema import (CONFIG_ORDER, INTERVENTION_CONFIGS,
                                                PatternRecord, read_long, signal_columns,
                                                write_long_json, write_wide_csv)

__all__ = [
    "CONFIG_ORDER", "INTERVENTION_CONFIGS", "PatternRecord", "read_long",
    "signal_columns", "write_long_json", "write_wide_csv",
]
