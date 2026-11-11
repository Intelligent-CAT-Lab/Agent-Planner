"""
Behavioral agreement: legacy Python detectors vs default Drift-QL signals, on the
same recorded trajectory prefixes.

Expressiveness is a statement about what the language *can say*; this module is the
companion behavioral check -- it confirms that where the DSL re-expresses a legacy
condition, the two implementations actually agree on recorded inputs, and it reports
the disagreements and their causes rather than hiding them.

It reuses the production shadow differential harness
(:mod:`plan_monitor.drift_ql.shadow`) unchanged. For each trajectory that harness
drives BOTH systems step-for-step over the identical representation (the legacy
monitor is the oracle for committed state, so prefixes never diverge) and records,
per default-profile signal category, how many step-level hook evaluations agree,
fire in legacy only, or fire in Drift-QL only. Categories split into:

  * EXACT (the four ``dwell_*``): the DSL must reproduce the legacy counter
    step-for-step; any discrepancy is a real bug and is surfaced individually.
  * KNOWN-DIFFERENCE (``oscillation``, ``thought_oscillation``, ``plan_compliance``,
    ``repeated_view``): the DSL's memoryless / strict-period / node-identity
    semantics diverge from the legacy stateful detectors for documented, benign
    reasons (see the ``plan_monitor.drift_ql.shadow`` module docstring). These are
    reported, not asserted.

Scope matches the signal-selection study: vanilla (``default``) trajectories only,
three executor models, SWE-bench Verified (all) + SWE-bench Pro (python). No agent
runs, no execution -- pure replay of recorded steps.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from analysis.signal_selection.analyze import in_scope
from analysis.signal_selection.inventory import discover
from plan_monitor.drift_ql import shadow

REPO = Path(__file__).resolve().parents[2]


def _replay_one(traj_path: str) -> Optional[Dict]:
    """Replay one trajectory through the shadow differ; return its per-category tallies."""
    try:
        rep = shadow.replay_trajectory(traj_path, agent="swe-agent")
    except Exception as exc:  # malformed / unreadable trajectory -- skip, keep going
        return {"error": f"{type(exc).__name__}: {exc}", "steps": 0}
    return {
        "steps": rep.steps,
        "per_category": {
            cat: {"agree": st.agree, "legacy_only": st.legacy_only,
                  "driftql_only": st.driftql_only}
            for cat, st in rep.per_category.items()
        },
        "exact_discrepancies": [
            {"step": s, "category": c, "who": who}
            for s, c, who in rep.exact_discrepancies
        ],
    }


def compute_agreement(swe_root: Path, pro_root: Path, *, jobs: int = 6,
                      limit: Optional[int] = None) -> Dict:
    """Aggregate legacy-vs-DSL step agreement over the in-scope default trajectories."""
    records = [r for r in discover(swe_root, pro_root) if in_scope(r)]
    records.sort(key=lambda r: (r.dataset, r.model, r.instance))
    if limit is not None:
        records = records[:limit]

    cats: Dict[str, Dict[str, int]] = {}
    exact_discrepancies: List[Dict] = []
    n_steps = n_trajectories = n_errors = 0

    paths = [str(r.traj_path) for r in records]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_replay_one, p): p for p in paths}
        for fut in as_completed(futures):
            res = fut.result()
            if res is None or res.get("error"):
                n_errors += 1
                continue
            n_trajectories += 1
            n_steps += res["steps"]
            for cat, t in res["per_category"].items():
                acc = cats.setdefault(cat, {"agree": 0, "legacy_only": 0, "driftql_only": 0})
                acc["agree"] += t["agree"]
                acc["legacy_only"] += t["legacy_only"]
                acc["driftql_only"] += t["driftql_only"]
            for d in res["exact_discrepancies"]:
                exact_discrepancies.append({**d, "traj": futures[fut]})

    categories = {}
    for cat, t in sorted(cats.items()):
        total = t["agree"] + t["legacy_only"] + t["driftql_only"]
        categories[cat] = {
            **t,
            "total_firings": total,
            "disagreements": t["legacy_only"] + t["driftql_only"],
            "agreement_rate": round(t["agree"] / total, 4) if total else None,
            "kind": ("exact" if cat in shadow.EXACT_CATEGORIES else "known-difference"),
        }

    return {
        "scope": "default trajectories; models deepseek/gemini/minimax; swebench + pro-python",
        "n_trajectories": n_trajectories,
        "n_unreadable": n_errors,
        "n_steps": n_steps,
        "exact_agreement": not exact_discrepancies,
        "categories": categories,
        "exact_discrepancies": exact_discrepancies[:50],
        "n_exact_discrepancies": len(exact_discrepancies),
    }


def to_markdown(result: Dict) -> str:
    L: List[str] = []
    L.append("## Behavioral agreement: legacy detectors vs default Drift-QL signals")
    L.append("")
    L.append(f"_Scope:_ {result['scope']}.  ")
    L.append(f"Replayed {result['n_trajectories']} trajectories "
             f"({result['n_steps']} step-level hook evaluations); "
             f"{result['n_unreadable']} unreadable, skipped.")
    L.append("")
    L.append("| category | kind | agree | legacy-only | GL-only | agreement rate |")
    L.append("|---|---|--:|--:|--:|--:|")
    for cat, t in result["categories"].items():
        rate = "—" if t["agreement_rate"] is None else f"{t['agreement_rate']:.1%}"
        L.append(f"| {cat} | {t['kind']} | {t['agree']} | {t['legacy_only']} "
                 f"| {t['driftql_only']} | {rate} |")
    L.append("")
    if result["exact_agreement"]:
        L.append("**EXACT categories (`dwell_*`): full step-for-step agreement ✓** — the DSL "
                 "`run(Group) >= theta` reproduces the legacy dwell counter exactly.")
    else:
        L.append(f"**EXACT categories: {result['n_exact_discrepancies']} discrepancy(ies) ✗** "
                 "(a real bug — these must match):")
        for d in result["exact_discrepancies"][:20]:
            L.append(f"  - step {d['step']}: {d['category']} ({d['who']}) in {d['traj']}")
    L.append("")
    L.append("Known-difference categories diverge for documented, benign reasons "
             "(bounded escalation, strict period vs windowed scan, memoryless vs "
             "stateful plan automaton, node-identity vs full-command revisit); see the "
             "`plan_monitor.drift_ql.shadow` module docstring. Divergences there are "
             "reported, not treated as errors.")
    L.append("")
    return "\n".join(L)
