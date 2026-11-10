"""
Collect pattern-resolution data by replaying trajectories through the production
GL-Guard engine (all 17 signals, True/False), across configs, into a tidy table.

For every ``(instance, config)`` run this records: the official resolution label; the
GL-Guard signal map (``n_true > 0`` per signal, from a non-executing replay — the SAME
engine that runs online, so no monitor is re-implemented and no rule text is matched);
replay-derived trajectory descriptors (submitted, action/thought step counts, phase
``lang``/``unique_phases``); executor cost/steps; and, for intervention configs, the
planner.json metadata — including ``refiner_online_triggers``, the structured record of
which signals fired *online* (incl. blocked/rolled-back proposals absent from the
committed trajectory). Replay and the online trail are complementary and kept separate.

Why this replaces the legacy collector (``analysis/legacy/``): the legacy path detected
patterns with the deprecated ``StatefulPhaseMonitor`` and recovered online signals by
matching planner.json rule text / inferring ``plan_violation`` from empty rule_triggers
— fragile, lossy, and unable to distinguish the plan-compliance sub-types. It also wrote
a fixed-width multi-section CSV (3 header rows, widths 13/15, 7 hardcoded patterns) that
had to be edited in several places to change the signal set. Here the signal columns are
derived from the live spec, so the schema is signal-count-agnostic.

Outputs (under ``analysis/analysis-results/pattern-resolution/``):
  * ``{agent}-{model}-{dataset}.long.csv`` / ``.long.jsonl`` -- source of truth.
  * ``{agent}-{model}-{dataset}.wide.csv``                   -- generated human pivot.

Example:
  python analysis/collect_pattern_resolution.py --agent SWE-agent \
      --model deepseek-chat-v3-0324 --dataset swebench --jobs 6
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from analysis.pattern_resolution.schema import (CONFIG_ORDER, INTERVENTION_CONFIGS,
                                                PatternRecord, signal_columns,
                                                write_long_json, write_wide_csv)
from analysis.pattern_resolution.sources import (load_labels, read_planner_meta,
                                                 read_traj_metrics, replay_detail,
                                                 traj_base)

REPO = Path(__file__).resolve().parent.parent


def _collect_one(task: Dict) -> PatternRecord:
    """Worker: replay one trajectory + read its metadata -> one PatternRecord."""
    det = replay_detail(task["traj_path"])
    metrics = read_traj_metrics(Path(task["traj_path"]))
    rec = PatternRecord(
        instance_id=task["instance_id"], config=task["config"], resolved=task["resolved"],
        lang=det["lang"], unique_phases=det["unique_phases"],
        cost=metrics["cost"], steps=metrics["steps"],
        signals=det["signals"], error=det["error"],
    )
    if task["planner_path"]:
        pm = read_planner_meta(Path(task["planner_path"]))
        rec.has_planner = pm["has_planner"]
        rec.refiner_online_triggers = pm["refiner_online_triggers"]
        rec.cost += pm["refiner_cost"]          # total = executor + planner (legacy parity)
    return rec


def build_tasks(agent_dir: Path, dataset: str, model: str, configs: List[str],
                runs: Dict[str, int], version: Optional[str]) -> List[Dict]:
    tasks: List[Dict] = []
    for config in configs:
        run = runs[config]
        ver = version if config in ("refiner", "refiner-only") else None
        base = traj_base(agent_dir, config, dataset, model, run, ver)
        if not base.is_dir():
            print(f"  [skip] {config}: no trajectories at {base}")
            continue
        labels = load_labels(agent_dir, config, dataset, model, run, ver)
        is_intervention = config in INTERVENTION_CONFIGS
        n = 0
        for inst_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            instance = inst_dir.name
            traj = inst_dir / f"{instance}.traj"
            if not traj.is_file():
                continue
            planner = inst_dir / f"{instance}.planner.json"
            tasks.append({
                "config": config, "instance_id": instance,
                "resolved": labels.get(instance),
                "traj_path": str(traj),
                "planner_path": str(planner) if (is_intervention and planner.is_file()) else None,
            })
            n += 1
        print(f"  {config}: {n} trajectories (run-{run}{', v' + ver if ver else ''})")
    return tasks


def run(records_tasks: List[Dict], jobs: int) -> List[PatternRecord]:
    records: List[PatternRecord] = []
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(_collect_one, t) for t in records_tasks]
            for i, fut in enumerate(as_completed(futs), 1):
                records.append(fut.result())
                if i % 200 == 0:
                    print(f"  replayed {i}/{len(records_tasks)}")
    else:
        for i, t in enumerate(records_tasks, 1):
            records.append(_collect_one(t))
            if i % 200 == 0:
                print(f"  replayed {i}/{len(records_tasks)}")
    return records


def print_summary(records: List[PatternRecord]) -> None:
    print("\n" + "=" * 70 + "\nCOLLECTION SUMMARY\n" + "=" * 70)
    for cfg in CONFIG_ORDER:
        recs = [r for r in records if r.config == cfg]
        if not recs:
            continue
        resolved = sum(1 for r in recs if r.resolved)
        with_sig = sum(1 for r in recs if r.any_signal)
        errs = sum(1 for r in recs if r.error)
        line = (f"  {cfg:13s} n={len(recs):4d}  resolved={resolved:4d}  "
                f"any_signal={with_sig:4d}")
        if cfg in INTERVENTION_CONFIGS:
            line += f"  has_planner={sum(1 for r in recs if r.has_planner):4d}"
        if errs:
            line += f"  errors={errs}"
        print(line)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="SWE-agent")
    ap.add_argument("--model", required=True)
    ap.add_argument("--dataset", default="swebench", choices=["swebench", "swebench-pro"])
    ap.add_argument("--configs", nargs="+", default=list(CONFIG_ORDER), choices=CONFIG_ORDER)
    ap.add_argument("--vanilla-run", type=int, default=1)
    ap.add_argument("--sage-run", type=int, default=1)
    ap.add_argument("--monitor-run", type=int, default=1)
    ap.add_argument("--refiner-only-run", type=int, default=1)
    ap.add_argument("--refiner-run", type=int, default=1)
    ap.add_argument("--version", default="5", help="version for refiner / refiner-only")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None, help="cap tasks (smoke test)")
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args(argv)

    agent_dir = (REPO / args.agent if args.dataset == "swebench"
                 else REPO / "SWE-bench_Pro-os" / args.agent)
    if not agent_dir.is_dir():
        raise FileNotFoundError(f"Agent directory not found: {agent_dir}")
    runs = {"default": args.vanilla_run, "sage": args.sage_run, "monitor": args.monitor_run,
            "refiner-only": args.refiner_only_run, "refiner": args.refiner_run}

    print(f"Agent={args.agent}  model={args.model}  dataset={args.dataset}")
    tasks = build_tasks(agent_dir, args.dataset, args.model,
                        args.configs, runs, args.version)
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        print("No trajectories found for any requested config.")
        return 1
    print(f"\nReplaying {len(tasks)} trajectories (jobs={args.jobs})...")
    records = run(tasks, args.jobs)

    out_dir = args.out_dir or (REPO / "analysis" / "analysis-results" / "pattern-resolution")
    stem = f"{args.agent}-{args.model}-{args.dataset}"
    write_long_json(records, out_dir / f"{stem}.long.json")
    write_wide_csv(records, out_dir / f"{stem}.wide.csv", signal_columns())
    print(f"\nWrote {stem}.long.json + {stem}.wide.csv to {out_dir}")
    print_summary(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
