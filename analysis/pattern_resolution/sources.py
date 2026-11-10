"""
Data sources for pattern-resolution collection: where trajectories live, their official
labels, their cost/step + planner.json metadata, and the GL-Guard replay-detail driver.

All signal detection is the production replay engine (``analysis.replay``); nothing here
re-implements a monitor or matches rule text. The one place we read planner.json is for
the *online intervention trail* (``refiner_online_triggers``) and cost/latency counts —
metadata the replay cannot reconstruct — using the structured ``rule_triggers`` ids, not
message text.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

# config -> trajectory/report subdirectory name (config name IS the dir name here).
_CONFIG_DIR = {"default": "default", "sage": "sage", "monitor": "monitor",
               "refiner-only": "refiner-only", "refiner": "refiner"}
_VERSIONED = {"refiner", "refiner-only"}


def _dataset_path(dataset: str) -> str:
    return "swebench-pro/python" if dataset == "swebench-pro" else dataset


def traj_base(agent_dir: Path, config: str, dataset: str, model: str, run: int,
              version: Optional[str]) -> Path:
    """Trajectory run directory for a config, matching the on-disk convention."""
    parts = [agent_dir, "trajectories", _CONFIG_DIR[config]]
    if config in _VERSIONED and version:
        parts.append(f"version-{version}")
    parts += [_dataset_path(dataset), model, f"run-{run}"]
    return Path(*parts)


# --------------------------------------------------------------------------- #
# Official labels (3-way: resolved / unresolved / missing)
# --------------------------------------------------------------------------- #

def load_labels(agent_dir: Path, config: str, dataset: str, model: str, run: int,
                version: Optional[str]) -> Dict[str, bool]:
    """instance_id -> resolved bool. Absent key => caller treats as 'missing'."""
    ds = _dataset_path(dataset)
    if dataset == "swebench-pro":
        base = [agent_dir, "reports", _CONFIG_DIR[config]]
        if config in _VERSIONED and version:
            base.append(f"version-{version}")
        path = Path(*base, ds, model, f"run-{run}", "eval_results.json")
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return {k: bool(v) for k, v in data.items()} if isinstance(data, dict) else {}

    # swebench: ID-list report under the model directory, a few historical name spellings.
    base = [agent_dir, "reports", _CONFIG_DIR[config]]
    if config in _VERSIONED and version:
        base.append(f"version-{version}")
    rep_dir = Path(*base, ds, model)
    for name in (f"{model}.run-{run}.json", f"{model}.run_{run}.json", f"{model}.{run}.json"):
        path = rep_dir / name
        if path.is_file():
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                return {}
            out: Dict[str, bool] = {}
            for iid in data.get("resolved_ids", []) or []:
                out[iid] = True
            for iid in data.get("unresolved_ids", []) or []:
                out.setdefault(iid, False)
            return out
    return {}


# --------------------------------------------------------------------------- #
# Cost / steps (executor trajectory) + planner.json intervention metadata
# --------------------------------------------------------------------------- #

def read_traj_metrics(traj_path: Path) -> Dict[str, float]:
    """Executor instance_cost + api_calls from a ``.traj`` info block."""
    try:
        stats = json.loads(traj_path.read_text()).get("info", {}).get("model_stats", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {"cost": 0.0, "steps": 0}
    return {"cost": float(stats.get("instance_cost", 0.0) or 0.0),
            "steps": int(stats.get("api_calls", 0) or 0)}


# Canonical plan-compliance message anchor. Both the legacy ``default_rules.json`` and the
# gl_guard ``liveplan.advice.json`` plan-compliance templates lead with this exact,
# placeholder-free phrase, so matching it on a monitor-only ``content`` is a structural
# marker (the system's own template), not an ad-hoc keyword guess.
_PC_MESSAGE_ANCHOR = "Plan compliance violation:"
# The legacy generic plan-compliance id, used as the recovered token so a legacy run's
# online trail is engine-honest (gl_guard runs instead carry the decomposed names).
_PC_GENERIC = "plan_compliance"


def _recovers_plan_compliance(iv: Dict) -> bool:
    """True iff this intervention is an online plan-compliance firing NOT already in
    ``rule_triggers`` — recovered structurally (no fuzzy matching).

    Two deterministic paths, matching how planner.json actually stores legacy firings:
      * Refiner entry: ``state_summary`` is present but ``rule_triggers`` is empty. The
        refiner's exclusion set is exactly ``["plan_compliance"]`` (exact match), so the
        only way all triggers vanish is that plan-compliance was the sole trigger. (A
        gl_guard run keeps its decomposed ``plan_compliance_*`` ids, so it never lands
        here.)
      * Monitor-only entry: ``state_summary`` is absent (monitor/cooling entries never
        write it, both engines), so the sole trace is ``content`` — which, for a
        plan-compliance firing, begins with the canonical template anchor.
    """
    ss = iv.get("state_summary")
    if iv.get("planner_type") == "refiner":
        return ss is not None and not ((ss or {}).get("rule_triggers") or [])
    return ss is None and (iv.get("content") or "").lstrip().startswith(_PC_MESSAGE_ANCHOR)


def read_planner_meta(planner_path: Path) -> Dict:
    """Online intervention metadata from planner.json (empty if absent).

    ``refiner_online_triggers`` is the de-duplicated set of signals that fired online.
    Directly-recorded ids come from the refiner's ``state_summary.rule_triggers`` (precise
    for gl_guard runs). On top of that we RECOVER plan-compliance firings that the record
    does not store as a structured id — legacy excludes the bare ``plan_compliance`` from
    rule_triggers, and monitor-only entries omit state_summary entirely — via
    :func:`_recovers_plan_compliance`, emitting the generic ``plan_compliance`` token so a
    legacy/monitor run's trail is never spuriously empty. See the package README.
    """
    out = {"has_planner": False, "n_interventions": 0, "monitor_count": 0,
           "refiner_count": 0, "refiner_cost": 0.0, "refiner_online_triggers": []}
    if not planner_path.is_file():
        return out
    try:
        data = json.loads(planner_path.read_text())
    except (OSError, json.JSONDecodeError):
        return out
    out["has_planner"] = True
    summary = data.get("summary", {}) or {}
    out["n_interventions"] = int(summary.get("total_interventions", 0) or 0)
    out["monitor_count"] = int(summary.get("monitor_count", 0) or 0)
    out["refiner_count"] = int(summary.get("refiner_count", 0) or 0)
    out["refiner_cost"] = float(summary.get("refiner_total_cost", 0.0) or 0.0)
    triggers = []
    for iv in data.get("interventions", []) or []:
        for rt in (iv.get("state_summary") or {}).get("rule_triggers", []) or []:
            rid = rt.get("rule_id") if isinstance(rt, dict) else str(rt)
            if rid:
                triggers.append(rid)
        if _recovers_plan_compliance(iv):
            triggers.append(_PC_GENERIC)
    out["refiner_online_triggers"] = sorted(set(triggers))
    return out


# --------------------------------------------------------------------------- #
# GL-Guard replay detail (signals True/False + trajectory descriptors)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# planner.json -> per-instance planner_stats (legacy-schema online record)
#
# Ported from the legacy analyzer so the emitted ``planner_stats`` is byte-compatible
# with the detailed-analysis JSON the visualize/ scripts consume. The ONLY behavioural
# change vs legacy is upstream: ``patterns`` now comes from the GL-Guard replay. Refiner
# rule-ids are the structured ``rule_triggers`` (precise decomposed names on gl_guard
# runs; legacy names on v5), defaulting to ``['plan_violation']`` when empty (the legacy
# plan-compliance exclusion recovery). Monitor interventions are classified from the
# canonical message text, returning the same fine labels the downstream coarse-mapper
# expects (plan_violation / dwell_* / oscillation_* / thought_oscillation_* / repeated_view).
# --------------------------------------------------------------------------- #

def classify_monitor_trigger(content: str) -> str:
    """Classify a monitor intervention's message into a legacy fine rule label."""
    c = content.lower()
    if "plan compliance" in c or "skipped phases" in c:
        return "plan_violation"
    if "seem to navigate" in c or "navigate between files" in c:
        return "dwell_L_navigate"
    if "trying to reproduce" in c:
        return "dwell_L_reproduce"
    if "spent the last" in c and "editing" in c:
        return "dwell_P"
    if "spent the last" in c and "validating" in c:
        return "dwell_V"
    if "repeating action" in c and "last trajectory" in c:
        return "oscillation_self_loop"
    if "repeated actions" in c and "revisiting" in c:
        return "oscillation_two_plus_node"
    if "repeating the same reasoning" in c or "circular reasoning" in c:
        return "thought_oscillation_self_loop"
    if "oscillating between" in c and "reasoning patterns" in c:
        return "thought_oscillation_cycle"
    if "cannot make further progress" in c:
        return "oscillation_max_repeats"
    if "already reviewed this location" in c or "have already reviewed" in c:
        return "repeated_view"
    return "unknown"


def _intervention_in_step(step: Dict, signature: str) -> bool:
    for msg in step.get("query", []):
        parts = msg.get("content", [])
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and signature in p.get("text", ""):
                    return True
        elif isinstance(parts, str) and signature in parts:
            return True
    return False


def find_next_action(intervention_step, content: str, trajectory: List) -> tuple:
    """Agent action/thought at the step where this intervention first appeared.

    Finds where the intervention's unique content signature was newly injected into the
    query messages (the step closest to ``intervention_step``) and returns that step's
    (action, thought). Ported verbatim from the legacy analyzer.
    """
    if not trajectory or intervention_step is None:
        return "", ""
    lines = content.split("\n")
    sig = "\n".join(lines[2:4])[:80] if len(lines) > 2 else content[:80]
    lo, hi = max(0, intervention_step - 2), min(len(trajectory), intervention_step + 5)
    fresh = [i for i in range(lo, hi)
             if _intervention_in_step(trajectory[i], sig)
             and (i == 0 or not _intervention_in_step(trajectory[i - 1], sig))]
    if not fresh:
        return "", ""
    idx = min(fresh, key=lambda x: abs(x - intervention_step))
    step = trajectory[idx]
    return step.get("action", ""), step.get("thought", "")


def extract_planner_stats(planner_path: Path, traj_path: Path):
    """Per-instance ``planner_stats`` (legacy schema) from planner.json + its trajectory.

    Returns ``None`` when no planner.json exists. Interventions preserve the legacy
    fields (monitor -> ``pattern``; refiner -> ``rule_ids``) plus ``next_action`` /
    ``next_thought``; the summary carries the latency/count/cost totals.
    """
    if not planner_path.is_file():
        return None
    try:
        data = json.loads(planner_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    trajectory = []
    if traj_path.is_file():
        try:
            trajectory = json.loads(traj_path.read_text()).get("trajectory", [])
        except (OSError, json.JSONDecodeError):
            trajectory = []

    summary = data.get("summary", {}) or {}
    details = []
    for iv in data.get("interventions", []) or []:
        ptype, step, content = iv.get("planner_type"), iv.get("step"), iv.get("content", "")
        nxt_a, nxt_t = find_next_action(step, content, trajectory)
        if ptype == "monitor":
            details.append({"step": step, "planner_type": "monitor", "content": content[:200],
                            "pattern": classify_monitor_trigger(content),
                            "next_action": nxt_a, "next_thought": nxt_t})
        elif ptype == "refiner":
            rts = (iv.get("state_summary") or {}).get("rule_triggers", []) or []
            rule_ids = [rt.get("rule_id", "unknown") if isinstance(rt, dict) else str(rt)
                        for rt in rts] or ["plan_violation"]
            details.append({"step": step, "planner_type": "refiner", "content": content,
                            "rule_ids": rule_ids, "next_action": nxt_a, "next_thought": nxt_t})
    return {
        "total_interventions": summary.get("total_interventions", 0),
        "monitor_count": summary.get("monitor_count", 0),
        "refiner_count": summary.get("refiner_count", 0),
        "monitor_total_latency_ms": summary.get("monitor_total_latency_ms", 0.0),
        "refiner_total_latency_ms": summary.get("refiner_total_latency_ms", 0.0),
        "refiner_total_cost": summary.get("refiner_total_cost", 0.0),
        "interventions": details,
    }


def _subscript_runlength(phases: List[str]) -> str:
    """Run-length encode a phase sequence with subscripts, e.g. ['P','P','V'] -> 'P₂V₁'."""
    out, prev, count = [], None, 0
    for ph in phases:
        if ph == prev:
            count += 1
        else:
            if prev is not None:
                out.append(f"{prev}{str(count).translate(_SUBSCRIPTS)}")
            prev, count = ph, 1
    if prev is not None:
        out.append(f"{prev}{str(count).translate(_SUBSCRIPTS)}")
    return "".join(out)


def replay_detail(traj_path) -> Dict:
    """Replay one ``.traj`` through GL-Guard and return its detection detail.

    Returns ``signals`` (name -> fired bool over EVERY evaluated signal, from
    ``n_true > 0``) and the phase-sequence descriptors (``lang`` run-length encoding +
    first-appearance ``unique_phases``), all from the one engine. Unknown (three-valued)
    verdicts count as not-fired, so each column is a clean True/False. On a malformed
    trajectory, ``error`` is set and every signal is False.
    """
    # Imported lazily so worker processes pay the import once, and so this module stays
    # importable without the heavy gl_guard stack for pure-schema callers.
    from analysis.replay.replay_monitor import ReplayMonitor
    from plan_monitor.simulator.swe_extractor import ActionExtractor

    # Production-faithful: detect only the LIVE profile (``liveplan.glg``), not the shadow
    # ``extra_signals.glg`` candidates. ``shadow_specs=()`` makes ``_merge_shadow_specs`` a
    # no-op, so the runtime is exactly what the online monitor runs. (The signal-selection
    # study keeps the shadow signals via ``replay_trajectory``; this collect path does not.)
    mon = ReplayMonitor(shadow_specs=())
    mon.reset()
    all_sigs = [r.name for r in mon.runtime.program.rules]
    try:
        steps = list(ActionExtractor(str(traj_path)).extract_actions(include_thought_steps=True))
    except Exception as exc:                       # malformed / unreadable trajectory
        return {"signals": {s: False for s in all_sigs}, "lang": "",
                "unique_phases": "", "error": f"{type(exc).__name__}: {exc}"}
    for event, thought, observation in steps:
        mon.check_step_pre_emptively(event, thought=thought)
        mon.observe_result(observation)

    # Submit-gated signals (plan-compliance skip_* family) describe the TERMINAL
    # state, so they are read at the final submit -- not OR-ed across every submit
    # attempt. Otherwise a premature submit the monitor blocked (before the agent
    # then patched and submitted properly) would be miscounted as an unresolved
    # plan violation in a completed trajectory -- inflating the intervention
    # configs, which by construction bounce the agent off exactly such attempts.
    # Every other signal keeps "fired at any step" (n_true > 0). See
    # ``replay_monitor.submit_gated_signals``.
    def _fired(s: str) -> bool:
        if s in mon._submit_signals:
            return bool(mon.submit_final_true.get(s, False))
        return mon.signal_runstats.get(s, {}).get("n_true", 0) > 0

    return {
        "signals": {s: _fired(s) for s in all_sigs},
        "lang": _subscript_runlength(mon.role_history),
        "unique_phases": ",".join(dict.fromkeys(mon.role_history)),
        "error": "",
    }
