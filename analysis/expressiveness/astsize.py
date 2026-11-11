"""
Program size in AST nodes -- a formatting-robust companion to the LOC comparison.

Why this exists, and what it is NOT
-----------------------------------
Comparing AST node *counts across two languages*, or an AST *edit distance* between a
DSL program and a Python program, is **not** an accepted way to evaluate expressive
power in the PL literature: node taxonomies differ between languages (so absolute
counts are only weakly commensurable), and tree size measures syntactic *conciseness*,
not *expressiveness* (expressive power is argued in the style of Felleisen, or shown via
coverage). Textual/AST edit distance in particular is syntax-dominated -- a one-token
change can flip a condition while leaving the trees almost identical -- so it is
deliberately **not** computed here.

What top PL papers do report for the size dimension is *program size*: LOC (e.g. Exo)
or the number of DSL constructs / AST nodes of the DSL program (e.g. ImageEye reports
DSL program sizes; Spytial reports the number of operations used) -- always as a
conciseness result. This module reports exactly that, as a cross-check on the LOC
numbers that is immune to line-wrapping and whitespace. Treat the per-row ratio as
indicative, not exact.

Counting convention
-------------------
  * DSL: the number of Drift-QL AST nodes in a signal's ``when`` formula (every
    dataclass node, operators and operand leaves alike), parsed by the production
    parser. The parser DESUGARS ``cycle`` / ``seen`` / ``revisit`` before this count
    sees them -- ``cycle(action, up_to=10, ...)`` becomes a 10-way disjunction -- so
    the DSL count is a conservative UPPER bound on the as-written size (most visible on
    ``oscillation``). This bias runs against the DSL, so the reported advantage is a
    lower bound, consistent with ``loc.py``.
  * Python: positioned AST nodes (every ``ast`` node carrying a source position; the
    context/operator leaves such as ``Load``/``Eq`` have none and are skipped) in the
    detector class, bucketed by the SAME line partition ``loc.py`` uses -- so the
    ``detection`` bucket is the predicate code, excluding ``__init__``/``reset`` state
    and the ``RuleMatch`` verdict.

Scope and DSL-only handling mirror ``loc.py`` exactly (default profile; the five
matched legacy classes; ``action_recurrence`` reported separately, never in a total).
Pure and deterministic.
"""
from __future__ import annotations

import ast as pyast
import dataclasses
from typing import Dict, List

from plan_monitor.drift_ql.parser import parse_program

from analysis.expressiveness import loc


# --------------------------------------------------------------------------- #
# DSL side: Drift-QL AST node count.
# --------------------------------------------------------------------------- #


def _dsl_node_count(node) -> int:
    """Count Drift-QL AST dataclass nodes reachable from ``node`` (inclusive)."""
    if not dataclasses.is_dataclass(node):
        return 0
    total = 1
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if dataclasses.is_dataclass(value):
            total += _dsl_node_count(value)
        elif isinstance(value, (tuple, list, frozenset, set)):
            for item in value:
                total += _dsl_node_count(item)
    return total


def glg_signal_ast_nodes(path=loc.GLG) -> Dict[str, int]:
    """Map each default signal to the node count of its (desugared) ``when`` formula."""
    return {r.name: _dsl_node_count(r.body) for r in parse_program(path.read_text())}


# --------------------------------------------------------------------------- #
# Python side: positioned AST node count, bucketed by the loc.py line partition.
# --------------------------------------------------------------------------- #


def legacy_class_ast_breakdown(pf: loc.PyFile, class_name: str) -> Dict:
    sets = loc.legacy_class_line_sets(pf, class_name)
    cls = sets["cls"]
    buckets = {"total": 0, "state": 0, "verdict": 0, "detection": 0}
    for node in pyast.walk(cls):
        if node is cls:                       # skip the ClassDef wrapper itself
            continue
        line = getattr(node, "lineno", None)
        if line is None:                      # operator / context leaves: no position
            continue
        buckets["total"] += 1
        if line in sets["state"]:
            buckets["state"] += 1
        elif line in sets["verdict"]:
            buckets["verdict"] += 1
        else:
            buckets["detection"] += 1
    return {"class": class_name, **buckets}


# --------------------------------------------------------------------------- #
# Top-level computation (mirrors loc.compute_loc()).
# --------------------------------------------------------------------------- #


def compute_ast_size() -> Dict:
    rules = loc.PyFile(loc.RULES_PY)
    dsl_nodes = glg_signal_ast_nodes()

    groups_out: List[Dict] = []
    tot_dsl = tot_legacy_total = tot_legacy_detection = 0
    for g in loc.GROUPS:
        dsl_per = {sig: dsl_nodes[sig] for sig in g["dsl_signals"]}
        dsl_sz = sum(dsl_per.values())
        parts = [legacy_class_ast_breakdown(rules, c) for c in g["legacy_classes"]]
        legacy_total = sum(p["total"] for p in parts)
        legacy_detection = sum(p["detection"] for p in parts)
        tot_dsl += dsl_sz
        tot_legacy_total += legacy_total
        tot_legacy_detection += legacy_detection
        groups_out.append({
            "group": g["group"],
            "dsl": {"signals": dsl_per, "n_signals": len(dsl_per), "nodes": dsl_sz},
            "legacy": {"classes": parts, "total": legacy_total,
                       "detection": legacy_detection},
            "ratio_total": round(legacy_total / dsl_sz, 1) if dsl_sz else None,
            "ratio_detection": round(legacy_detection / dsl_sz, 1) if dsl_sz else None,
        })

    dsl_only = {sig: dsl_nodes[sig] for sig in loc.DSL_ONLY_SIGNALS}
    return {
        "metric": "program size in AST nodes (conciseness companion to LOC; not an "
                  "edit distance, not expressive power)",
        "caveat": ("cross-language node counts are only weakly commensurable; the DSL "
                   "count is a conservative upper bound (cycle/seen/revisit are desugared "
                   "before counting)"),
        "groups": groups_out,
        "totals": {
            "dsl_nodes": tot_dsl,
            "legacy_total": tot_legacy_total,
            "legacy_detection": tot_legacy_detection,
            "ratio_total": round(tot_legacy_total / tot_dsl, 1) if tot_dsl else None,
            "ratio_detection": round(tot_legacy_detection / tot_dsl, 1) if tot_dsl else None,
        },
        "dsl_only_signals": {"signals": dsl_only},
    }


def to_markdown(result: Dict) -> str:
    L: List[str] = []
    L.append("## Program size (AST nodes) — conciseness cross-check")
    L.append("")
    L.append(f"_Metric:_ {result['metric']}.  ")
    L.append(f"_Caveat:_ {result['caveat']}.")
    L.append("")
    L.append("| signal(s) | DSL AST nodes | legacy class nodes | legacy detection nodes | total× | detection× |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for g in result["groups"]:
        names = ", ".join(g["dsl"]["signals"])
        L.append(f"| {names} | {g['dsl']['nodes']} | {g['legacy']['total']} "
                 f"| {g['legacy']['detection']} | {g['ratio_total']}× | {g['ratio_detection']}× |")
    t = result["totals"]
    L.append(f"| **total** | **{t['dsl_nodes']}** | **{t['legacy_total']}** "
             f"| **{t['legacy_detection']}** | **{t['ratio_total']}×** | **{t['ratio_detection']}×** |")
    L.append("")
    osc = next((g for g in result["groups"] if g["group"] == "oscillation"), None)
    if osc:
        L.append(f"`oscillation`'s {osc['dsl']['nodes']} nodes are inflated by desugaring "
                 "— the author writes one `cycle(action, up_to=10, times=r_action)` "
                 "construct, which expands to a 10-way disjunction before counting — so "
                 "that row's DSL size is a loose upper bound.")
        L.append("")
    only = result["dsl_only_signals"]["signals"]
    if only:
        names = ", ".join(f"`{s}` ({n} nodes)" for s, n in only.items())
        L.append(f"_DSL-only signal excluded from the matched comparison: {names}._")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(compute_ast_size(), indent=2))
