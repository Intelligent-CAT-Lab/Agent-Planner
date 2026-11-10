"""
Tidy pattern-resolution schema + I/O.

The detection record for one ``(instance, config)`` run is a flat dict with NAMED
columns only. Columns stay close to the legacy field set — ``resolved`` (Resolution
Status), ``any_signal`` (Has Issue), ``has_planner`` (Trigger Status), ``lang``,
``unique_phases``, ``cost``, ``steps`` — plus one boolean column per GL-Guard signal
(the former "patterns") and one new signal-bearing field, ``refiner_online_triggers``
(which signals fired *online*; not derivable from the committed trajectory). Nothing
redundant is stored: overlap/transition views are derived in the analysis layer, and
cost already folds in the planner cost (legacy parity).

Readers address every field by name (``csv.DictReader``), so the number of signals is
free to change: the signal columns come straight from the live runtime declaration order
via :func:`signal_columns`, the single source of truth shared with the replay engine.

Two artifacts, both generated (never hand-maintained):
  * ``*.long.json`` -- one record per ``(instance, config)`` (a JSON array); the
    machine-readable source of truth, consumed by the analyzer.
  * ``*.wide.csv`` -- a human-viewable pivot (one row per instance, configs side by
    side); its column widths are computed from the data, so extending the signal set
    never breaks the layout.

All text is written UTF-8 with ``ensure_ascii=False`` so the subscript ``lang`` glyphs
(e.g. ``L₂P₁``) are preserved literally rather than ``\\u``-escaped or crashing on a
non-UTF-8 locale.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from analysis.replay.replay_monitor import build_study_runtime

# Config vocabulary. "default" is the vanilla baseline; "sage" an alternate baseline;
# the rest are intervention configs that additionally carry a planner.json.
CONFIG_ORDER = ("default", "sage", "monitor", "refiner-only", "refiner")
BASELINE_CONFIGS = ("default", "sage")
INTERVENTION_CONFIGS = ("monitor", "refiner-only", "refiner")

# Non-signal columns, in display order. Signal columns are appended dynamically.
KEY_COLUMNS = ("instance_id", "config")
OUTCOME_COLUMNS = ("resolved",)                 # 1 / 0 / "" (missing label)
DERIVED_COLUMNS = ("any_signal",)               # Has Issue (any signal fired)
# Intervention-only (blank for baseline configs). ``refiner_online_triggers`` is the
# ONLY online intervention trail available post-hoc: a '|'-joined, de-duplicated list of
# the gl_guard signal names recorded in planner.json ``state_summary.rule_triggers``
# (precise for gl_guard runs; legacy names for legacy runs; empty for monitor-only
# entries, which omit state_summary). It is structured rule-id text, parsed by exact
# membership (never fuzzy message matching) -- see :func:`split_online_triggers`.
INTERVENTION_COLUMNS = ("has_planner", "refiner_online_triggers")
TRAJ_COLUMNS = ("lang", "unique_phases")
METRIC_COLUMNS = ("cost", "steps")

_TRIGGER_SEP = "|"


@lru_cache(maxsize=1)
def _runtime_rules():
    return tuple((r.name, r.hook.value) for r in build_study_runtime().program.rules)


def signal_columns() -> List[str]:
    """Signal names in the live runtime's declaration order (the single source of truth).

    Built from the SAME merged runtime the replay uses, so the tidy table's signal
    columns are exactly the signals the replay evaluates — no drift, no hardcoded list.
    """
    return [name for name, _ in _runtime_rules()]


def signal_hooks() -> Dict[str, str]:
    """signal -> hook ('propose' / 'observe(thought)'), for the analysis layer."""
    return {name: hook for name, hook in _runtime_rules()}


def long_columns(signals: Optional[List[str]] = None) -> List[str]:
    """Full ordered column list for the long table."""
    sigs = signals if signals is not None else signal_columns()
    return list(KEY_COLUMNS + OUTCOME_COLUMNS + DERIVED_COLUMNS + INTERVENTION_COLUMNS
                + TRAJ_COLUMNS + METRIC_COLUMNS) + list(sigs)


@dataclass
class PatternRecord:
    """One ``(instance, config)`` detection record. Signals held in a sub-dict."""
    instance_id: str
    config: str
    resolved: Optional[bool] = None
    lang: str = ""
    unique_phases: str = ""
    cost: float = 0.0
    steps: int = 0
    has_planner: bool = False
    refiner_online_triggers: List[str] = field(default_factory=list)
    signals: Dict[str, bool] = field(default_factory=dict)   # name -> fired
    error: str = ""                        # non-empty if the replay failed

    @property
    def any_signal(self) -> bool:
        return any(self.signals.values())

    def to_row(self, signal_order: List[str]) -> Dict[str, str]:
        """Flatten to a string-valued CSV row keyed by column name."""
        row = {
            "instance_id": self.instance_id, "config": self.config,
            "resolved": "" if self.resolved is None else int(self.resolved),
            "any_signal": int(self.any_signal),
            "lang": self.lang, "unique_phases": self.unique_phases,
            "cost": f"{self.cost:.6f}", "steps": self.steps,
        }
        # Intervention columns are blank for baseline configs (not 0) so "no planner
        # here" is visually distinct from "planner ran, no online triggers".
        if self.config in INTERVENTION_CONFIGS:
            row["has_planner"] = int(self.has_planner)
            row["refiner_online_triggers"] = _TRIGGER_SEP.join(self.refiner_online_triggers)
        else:
            row["has_planner"] = ""
            row["refiner_online_triggers"] = ""
        for sig in signal_order:
            row[sig] = int(bool(self.signals.get(sig, False)))
        return row

    def to_json(self) -> Dict:
        """Lossless JSONL record (native types; signals as a bool map)."""
        d = {
            "instance_id": self.instance_id, "config": self.config,
            "resolved": self.resolved, "any_signal": self.any_signal,
            "lang": self.lang, "unique_phases": self.unique_phases,
            "cost": self.cost, "steps": self.steps, "signals": dict(self.signals),
        }
        if self.config in INTERVENTION_CONFIGS:
            d["has_planner"] = self.has_planner
            d["refiner_online_triggers"] = list(self.refiner_online_triggers)
        if self.error:
            d["error"] = self.error
        return d


def split_online_triggers(cell: str) -> List[str]:
    """Parse a ``refiner_online_triggers`` CSV cell back to a list of rule-ids."""
    return [t for t in (cell or "").split(_TRIGGER_SEP) if t]


# --------------------------------------------------------------------------- #
# Long table I/O (JSON array)
# --------------------------------------------------------------------------- #

def write_long_json(records: List[PatternRecord], path: Path) -> None:
    """Write the long table as a UTF-8 JSON array (one object per record)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([rec.to_json() for rec in records], f, ensure_ascii=False, indent=2)


def read_long(path: Path) -> List[Dict]:
    """Read a long JSON array into dict rows, addressing every field BY NAME.

    ``signals`` is already a name->bool map in the record, so the signal set is read
    cleanly regardless of how many signals it holds. A few typed convenience scalars are
    added (``resolved_bool`` / ``has_planner_bool`` / ``online_triggers`` /
    ``signal_columns``) so the analyzer can stay signal-count-agnostic.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows: List[Dict] = []
    for rec in data:
        row = dict(rec)
        row["signals"] = dict(rec.get("signals") or {})
        row["signal_columns"] = list(row["signals"].keys())
        row["resolved_bool"] = rec.get("resolved")          # bool | None (missing)
        row["has_planner_bool"] = bool(rec.get("has_planner"))
        row["online_triggers"] = list(rec.get("refiner_online_triggers") or [])
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Wide pivot (generated for human viewing; widths computed from the data)
# --------------------------------------------------------------------------- #

def _wide_fields(config: str, signals: List[str]) -> List[str]:
    """Per-config field list in the wide pivot (compact, human-oriented)."""
    head = ["resolved"] + (["has_planner"] if config in INTERVENTION_CONFIGS else [])
    tail = ["any_signal", "lang", "unique_phases", "cost", "steps"]
    if config in INTERVENTION_CONFIGS:
        tail += ["refiner_online_triggers"]
    return head + list(signals) + tail


def write_wide_csv(records: List[PatternRecord], path: Path,
                   signal_order: Optional[List[str]] = None) -> None:
    """Pivot long records to a per-instance wide CSV with a 2-row header.

    Header row 1 names each config section (spanning its fields); row 2 names the
    fields. Nothing is hardcoded: section spans equal ``len(_wide_fields(config))``,
    computed from the actual signal set, so adding signals just widens each section.
    """
    sigs = signal_order if signal_order is not None else signal_columns()
    configs = [c for c in CONFIG_ORDER if any(r.config == c for r in records)]
    by_key: Dict[tuple, PatternRecord] = {(r.instance_id, r.config): r for r in records}
    instances = sorted({r.instance_id for r in records})

    header1, header2 = ["Instance ID"], [""]
    for cfg in configs:
        fields = _wide_fields(cfg, sigs)
        header1 += [cfg] + [""] * (len(fields) - 1)
        header2 += fields

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header1)
        w.writerow(header2)
        for inst in instances:
            row = [inst]
            for cfg in configs:
                fields = _wide_fields(cfg, sigs)
                rec = by_key.get((inst, cfg))
                if rec is None:
                    row += [""] * len(fields)
                else:
                    flat = rec.to_row(sigs)
                    row += [flat.get(fld, "") for fld in fields]
            w.writerow(row)
