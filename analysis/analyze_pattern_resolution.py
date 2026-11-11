"""
Analyze pattern-resolution data into the detailed-analysis JSON, from the tidy table
written by ``analysis/collect_pattern_resolution.py``.

Output is a DROP-IN for the legacy detailed-analysis JSON (same ``config`` / ``summary`` /
``category_details`` schema, same per-instance ``vanilla``+``<config>`` entries, same
``planner_stats``, written to the same ``comparison/detailed-analysis/<config>/`` path), so
the visualize/ and other downstream consumers are unaffected. The ONLY thing that changes is
the SIGNALS: ``patterns`` is now sourced from the production Drift-QL replay instead of the
deprecated monitor + CSV text-matching. The legacy 7 pattern names are preserved (as
buckets, same semantics) and the finer Drift-QL signals are added alongside — so downstream
reads its familiar keys and gains the precise ones ("our updated version's signals may be
more"). ``planner_stats`` (the online intervention record) is still recorded, with precise
``rule_ids`` from ``rule_triggers`` (decomposed on drift_ql runs; legacy names + the
``plan_violation`` exclusion-recovery on v5).

Example:
  python analysis/analyze_pattern_resolution.py --agent SWE-agent \
      --model deepseek-chat-v3-0324 --dataset swebench --config monitor refiner-only refiner
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from analysis.pattern_resolution.schema import BASELINE_CONFIGS, read_long
from analysis.pattern_resolution.sources import extract_planner_stats, traj_base

REPO = Path(__file__).resolve().parent.parent

# Legacy pattern buckets, in legacy order. Preserved (names + semantics) so downstream
# keeps working; the finer Drift-QL signals are appended under their own (non-colliding)
# names by :func:`patterns_from_signals`.
LEGACY_BUCKETS = ("plan_violation", "oscillation", "dwell_L_navigate",
                  "dwell_L_reproduce", "dwell_P", "dwell_V", "repeated_view")


def patterns_from_signals(sig: Dict[str, bool]) -> Dict[str, bool]:
    """Replay signal map -> ``patterns`` dict: legacy 7 buckets + precise extras.

    Buckets fold the Drift-QL signals into the legacy taxonomy (``plan_violation`` = any
    ``plan_compliance_*``; ``oscillation`` = oscillation | action_recurrence |
    thought_oscillation; the dwell/repeated_view buckets equal their like-named signals).
    Every Drift-QL signal whose name is not a bucket name is then added verbatim, so the
    decomposed plan-compliance family and the oscillation/thought variants are available
    without disturbing the legacy keys.
    """
    out = {
        "plan_violation": any(v for k, v in sig.items() if k.startswith("plan_compliance")),
        "oscillation": bool(sig.get("oscillation") or sig.get("action_recurrence")
                            or sig.get("thought_oscillation")),
        "dwell_L_navigate": bool(sig.get("dwell_L_navigate")),
        "dwell_L_reproduce": bool(sig.get("dwell_L_reproduce")),
        "dwell_P": bool(sig.get("dwell_P")),
        "dwell_V": bool(sig.get("dwell_V")),
        "repeated_view": bool(sig.get("repeated_view")),
    }
    for k, v in sig.items():                         # precise extras (declaration order)
        if k not in LEGACY_BUCKETS:
            out[k] = bool(v)
    return out


def by_config(rows: List[Dict]) -> Dict[str, Dict[str, Dict]]:
    out: Dict[str, Dict[str, Dict]] = {}
    for r in rows:
        out.setdefault(r["config"], {})[r["instance_id"]] = r
    return out


def _cost(r: Dict) -> float:
    try:
        return float(r.get("cost") or 0.0)
    except (ValueError, TypeError):
        return 0.0


def _steps(r: Dict) -> int:
    try:
        return int(r.get("steps") or 0)
    except (ValueError, TypeError):
        return 0


def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _view(row: Dict) -> Dict:
    """Legacy per-run view: resolved/has_issue/patterns/lang/unique_phases/cost/steps."""
    patterns = patterns_from_signals(row["signals"])
    return {
        "resolved": row["resolved_bool"] is True,     # missing label -> False (legacy parity)
        "has_issue": any(patterns.values()),
        "patterns": patterns,
        "lang": row.get("lang", ""),
        "unique_phases": row.get("unique_phases", ""),
        "cost": _cost(row),
        "steps": _steps(row),
    }


# --------------------------------------------------------------------------- #
# Report pieces (legacy schema)
# --------------------------------------------------------------------------- #

def trigger_status(cfg: Dict[str, Dict]) -> Dict:
    triggered = [i for i, r in cfg.items() if r["has_planner_bool"]]
    t_res = sum(1 for i in triggered if cfg[i]["resolved_bool"] is True)
    return {
        "total_planner_instances": len(cfg),
        "triggered_count": len(triggered),
        "triggered_percentage": (len(triggered) / len(cfg) * 100) if cfg else 0,
        "triggered_resolved": t_res,
        "triggered_unresolved": len(triggered) - t_res,
        "non_triggered_count": len(cfg) - len(triggered),
    }


def categorize(base: Dict[str, Dict], cfg: Dict[str, Dict], triggered_only: bool = True) -> Dict[str, List[str]]:
    cats = {"R-R": [], "R-U": [], "U-R": [], "U-U": []}
    iids = [i for i, r in cfg.items() if r["has_planner_bool"]] if triggered_only else list(cfg)
    for i in iids:
        if i not in base:
            continue
        v = "R" if base[i]["resolved_bool"] is True else "U"
        p = "R" if cfg[i]["resolved_bool"] is True else "U"
        cats[f"{v}-{p}"].append(i)
    return cats


def planner_aggregates(triggered: List[str], stats_by_iid: Dict[str, Dict]) -> Dict:
    n = len(triggered)
    tot = {"interventions": 0, "monitor": 0, "refiner": 0,
           "mon_lat": 0.0, "ref_lat": 0.0, "ref_cost": 0.0}
    dist: Counter = Counter()
    for i in triggered:
        ps = stats_by_iid.get(i)
        if not ps:
            continue
        tot["interventions"] += ps["total_interventions"]
        tot["monitor"] += ps["monitor_count"]
        tot["refiner"] += ps["refiner_count"]
        tot["mon_lat"] += ps["monitor_total_latency_ms"]
        tot["ref_lat"] += ps["refiner_total_latency_ms"]
        tot["ref_cost"] += ps["refiner_total_cost"]
        for iv in ps["interventions"]:
            if iv["planner_type"] == "monitor":
                dist[f"monitor_{iv.get('pattern', 'unknown')}"] += 1
            else:
                for rid in iv.get("rule_ids", ["unknown"]):
                    dist[rid] += 1
    out = {"total_triggered": n, "trigger_type_distribution": dict(dist)}
    if n:
        out.update({
            "avg_interventions": tot["interventions"] / n,
            "avg_monitor_count": tot["monitor"] / n,
            "avg_refiner_count": tot["refiner"] / n,
            "avg_monitor_latency_ms": tot["mon_lat"] / n,
            "avg_refiner_latency_ms": tot["ref_lat"] / n,
            "avg_refiner_cost": tot["ref_cost"] / n,
        })
    return out


def category_details(iids: List[str], base: Dict[str, Dict], cfg: Dict[str, Dict],
                     config: str, stats_by_iid: Dict[str, Dict]) -> Dict:
    instances, vcost, pcost, vstep, pstep = [], [], [], [], []
    pattern_counter: Counter = Counter()
    for i in iids:
        if i not in base or i not in cfg:
            continue
        bv, cv = _view(base[i]), _view(cfg[i])
        vcost.append(bv["cost"]); pcost.append(cv["cost"])
        vstep.append(bv["steps"]); pstep.append(cv["steps"])
        for p, on in bv["patterns"].items():
            if on:
                pattern_counter[p] += 1
        cdict = dict(cv)
        cdict["overlapping_issues"] = [p for p, on in cv["patterns"].items()
                                       if on and bv["patterns"].get(p)]
        cdict["has_planner"] = cfg[i]["has_planner_bool"]
        ps = stats_by_iid.get(i)
        if cfg[i]["has_planner_bool"] and ps:
            cdict["planner_stats"] = ps
        instances.append({"instance_id": i, "vanilla": bv, config: cdict})
    total = max(len(base), len(cfg))
    return {
        "count": len(iids),
        "percentage": (len(iids) / total * 100) if total else 0,
        "avg_vanilla_cost": _avg(vcost), f"avg_{config}_cost": _avg(pcost),
        "avg_vanilla_steps": _avg(vstep), f"avg_{config}_steps": _avg(pstep),
        "pattern_distribution": dict(pattern_counter),
        "instances": instances,
    }


def generate_report(config: str, base: Dict[str, Dict], cfg: Dict[str, Dict],
                    stats_by_iid: Dict[str, Dict]) -> Dict:
    categories = categorize(base, cfg, triggered_only=True)
    triggered = [i for i, r in cfg.items() if r["has_planner_bool"]]
    return {
        "config": config,
        "summary": {
            "total_instances": len(cfg),
            "trigger_status": trigger_status(cfg),
            "planner_aggregates": planner_aggregates(triggered, stats_by_iid),
            "categories": {cat: {"count": len(iids),
                                 "percentage": (len(iids) / len(cfg) * 100) if cfg else 0}
                           for cat, iids in categories.items()},
        },
        "category_details": {cat: category_details(iids, base, cfg, config, stats_by_iid)
                             for cat, iids in categories.items()},
    }


# --------------------------------------------------------------------------- #

def _collect_planner_stats(agent_dir: Path, cfg: Dict[str, Dict], config: str,
                           dataset: str, model: str, run: int, version: Optional[str]) -> Dict[str, Dict]:
    """``planner_stats`` for every triggered instance (locating planner.json + traj)."""
    ver = version if config in ("refiner", "refiner-only") else None
    base_dir = traj_base(agent_dir, config, dataset, model, run, ver)
    out = {}
    for iid, r in cfg.items():
        if not r["has_planner_bool"]:
            continue
        inst = base_dir / iid
        ps = extract_planner_stats(inst / f"{iid}.planner.json", inst / f"{iid}.traj")
        if ps is not None:
            out[iid] = ps
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="SWE-agent")
    ap.add_argument("--model", required=True)
    ap.add_argument("--dataset", default="swebench", choices=["swebench", "swebench-pro"])
    ap.add_argument("--config", nargs="+", default=["monitor", "refiner-only", "refiner"])
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--refiner-version", default="5")
    ap.add_argument("--long", type=Path, default=None, help="path to the long CSV")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: analysis/analysis-results/comparison/detailed-analysis")
    args = ap.parse_args(argv)

    stem = f"{args.agent}-{args.model}-{args.dataset}"
    long_path = args.long or (REPO / "analysis" / "analysis-results" / "pattern-resolution"
                              / f"{stem}.long.json")
    if not long_path.is_file():
        print(f"[skip] long table not found: {long_path} (run collect first)",
              file=sys.stderr)
        return 1
    agent_dir = (REPO / args.agent if args.dataset == "swebench"
                 else REPO / "SWE-bench_Pro-os" / args.agent)
    out_dir = args.out_dir or (REPO / "analysis" / "analysis-results" / "comparison"
                               / "detailed-analysis")

    cfgs = by_config(read_long(long_path))
    baseline = next((b for b in BASELINE_CONFIGS if b in cfgs), None)
    base_map = cfgs.get(baseline, {})
    if not baseline:
        print("[warn] no baseline (default/sage) in table — categories will be empty.")

    requested = [c for c in args.config if c in cfgs]
    missing = [c for c in args.config if c not in cfgs]
    if missing:
        print(f"[warn] not in table, skipped: {missing}. Present: {sorted(cfgs)}")

    for config in requested:
        stats = _collect_planner_stats(agent_dir, cfgs[config], config, args.dataset,
                                       args.model, args.run, args.refiner_version)
        report = generate_report(config, base_map, cfgs[config], stats)
        dest = out_dir / config / f"{stem}-{config}-analysis.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        ts = report["summary"]["trigger_status"]
        cats = report["summary"]["categories"]
        cat_summary = ", ".join(f"{k}={v['count']}" for k, v in cats.items())
        print(f"  {config}: {len(cfgs[config])} instances, triggered "
              f"{ts['triggered_count']}, [{cat_summary}] -> {dest}")
    if not requested:
        # A baseline-only table (e.g. a model/dataset with no intervention runs) has
        # nothing to compare — a clean no-op, not a failure.
        print(f"[skip] {stem}: no requested intervention config present "
              f"(table has {sorted(cfgs)}) — nothing to analyze.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
