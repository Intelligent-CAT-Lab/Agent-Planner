"""
Lines-of-code comparison: default Drift-QL (DriftQL) signals vs their legacy
Python detectors.

Scope -- the LIVE ``liveplan.glg`` profile ONLY. The twelve default signals are
matched to the five legacy detector classes in ``plan_monitor/rules.py`` that
implement the same conditions. The shadow ``extra_signals.glg`` candidates and the
50-entry process taxonomy are deliberately out of scope: ``extra_signals`` has no
legacy Python counterpart (nothing to compare), and the taxonomy is a catalogue,
not an implementation.

ONE counting convention, applied to both languages
--------------------------------------------------
A *code line* is a nonblank, noncomment physical source line. A module / class /
function docstring is treated as a comment (not code); a ``#`` comment and blank
lines are skipped; an inline comment does not stop its line from counting. The same
nonblank/noncomment rule is applied to ``.glg`` source.

What is charged to a rule, and what is shared
---------------------------------------------
A Drift-QL signal is three decoupled pieces (DSL_REFERENCE.md): detection
(``.glg``), thresholds (``liveplan.config.json``), and message + fire-timing
(``liveplan.advice.json``). Only the detection formula is rule-specific *code*; the
config and advice are shared DATA driven by one shared ENGINE. So:

  * **DSL per-rule cost** = the ``signal NAME on HOOK when <formula>`` block.
  * **Legacy per-rule cost** = the detector class(es) + any rule-specific helper.
    Each class is split, objectively from the Python AST, into the parts the DSL
    offloads to its shared layers:

        state     = ``__init__`` + ``reset`` bodies     -> DSL config.json + runtime
        verdict   = ``RuleMatch(...)`` constructions     -> DSL advice.json
        detection = everything else in the class         -> DSL ``when`` formula
                    (the predicate *plus* the rule-local suppression / rate-limit
                     state machine, which the DSL expresses as a shared emission
                     policy, not as per-rule code)

The apples-to-apples figure is **DSL formula LOC vs legacy ``detection`` LOC**. The
class total and the ``state`` / ``verdict`` offload are reported alongside for
transparency. Message-preparation lines (``message.replace``/``.format`` outside a
``RuleMatch`` call) are left inside ``detection``, which biases the legacy detection
count *upward* -- i.e. conservatively against the DSL -- so the reported DSL
advantage is a lower bound.

Shared infrastructure (the fixed, amortized cost of each approach) is counted once
per side and never folded into a per-rule number.

Pure and deterministic: reads source files, runs no trajectories. Run via
``analysis.expressiveness.analyze`` or call :func:`compute_loc` directly.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parents[2]
RULES_PY = REPO / "plan_monitor" / "rules.py"
MONITOR_PY = REPO / "plan_monitor" / "monitor.py"
PHASES_PY = REPO / "plan_monitor" / "phases.py"
GLG = REPO / "plan_monitor" / "drift_ql" / "specs" / "liveplan.glg"
CONFIG_JSON = REPO / "plan_monitor" / "drift_ql" / "specs" / "liveplan.config.json"
ADVICE_JSON = REPO / "plan_monitor" / "drift_ql" / "specs" / "liveplan.advice.json"
GLG_DIR = REPO / "plan_monitor" / "drift_ql"

# --------------------------------------------------------------------------- #
# Matched groups: one drift condition family, its default DSL signal(s), and the
# legacy detector class(es) that implement the same condition. Keep this the single
# source of truth; the signal names are validated against liveplan.glg at runtime.
# --------------------------------------------------------------------------- #

GROUPS: List[Dict] = [
    {
        "group": "dwell",
        "condition": "Prolonged single-phase dwell",
        "dsl_signals": ["dwell_L_navigate", "dwell_L_reproduce", "dwell_P", "dwell_V"],
        "legacy_classes": ["DwellTimeRule"],
        "note": "One legacy class, four config instances; four DSL signals over run(Group) >= theta.",
    },
    {
        "group": "oscillation",
        "condition": "Action oscillation",
        "dsl_signals": ["oscillation"],
        "legacy_classes": ["OscillationRule", "OscillationDetector"],
        "note": "Legacy wrapper + detector (cycle-matching algorithms); DSL cycle(...).",
    },
    {
        "group": "repeated_action",
        "condition": "Repeated view",
        "dsl_signals": ["repeated_view", "action_recurrence"],
        "legacy_classes": ["RepeatedViewRule"],
        "note": "Identity recurrence of a view; DSL kind(q)=view and revisit(action).",
    },
    {
        "group": "thought_oscillation",
        "condition": "Thought oscillation",
        "dsl_signals": ["thought_oscillation"],
        "legacy_classes": ["ThoughtOscillationRule"],
        "note": "Repeated reasoning motif in the current episode; DSL repeat(thought,...).",
    },
    {
        "group": "plan_compliance",
        "condition": "Plan-order compliance: premature / skip",
        "dsl_signals": [
            "plan_compliance_premature_patch",
            "plan_compliance_skip_patch",
            "plan_compliance_skip_validation",
        ],
        "legacy_classes": ["PlanComplianceRule"],
        "note": "Legacy stateful L->P->V automaton; DSL four memoryless propose predicates.",
    },
]

# Default DSL signals with NO legacy Python counterpart -- reported in text, excluded
# from the matched LOC comparison (there is nothing to compare against). The legacy
# OscillationDetector only catches strict periodic cycles; non-periodic prolonged
# recurrence (count{ x in history | key(x)=key(q) } >= kappa) was added natively in
# the DSL, so it has no matching detector class.
DSL_ONLY_SIGNALS = ["action_recurrence"]

# Shared infrastructure, counted once per side (NOT charged to any rule).
DSL_ENGINE_MODULES = [
    "lexer", "ast", "parser", "typecheck", "config", "kleene", "interpreter",
    "engine", "runtime", "emission", "advice", "model", "adapters",
]  # the language machinery, amortized over every signal
DSL_BINDING_MODULE = "drift_monitor"  # live monitor integration (analog of monitor.py)

LEGACY_SHARED_CLASSES = ["RuleMatch", "Rule", "GraphectoryRule", "RuleEngine"]

# Legacy detectors that implement conditions NOT in the default DSL profile -- listed
# for completeness, excluded from the per-rule comparison (no default signal to match).
LEGACY_UNMATCHED_CLASSES = ["PhaseTransitionRule", "StrategyShiftRule"]


# --------------------------------------------------------------------------- #
# Counting primitives.
# --------------------------------------------------------------------------- #


def _docstring_lines(tree: ast.AST) -> Set[int]:
    """Physical lines occupied by module/class/function docstrings (treated as comments)."""
    out: Set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(node, (ast.Module, ast.ClassDef,
                                             ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def _real_token_lines(src: str) -> Set[int]:
    """Lines carrying at least one token that is not whitespace/comment structure."""
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.ENCODING,
            tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    out: Set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in skip or tok.string.strip() == "":
            continue
        out.add(tok.start[0])
    return out


class PyFile:
    """A parsed Python file with a reusable nonblank/noncomment line counter."""

    def __init__(self, path: Path):
        self.path = path
        self.src = path.read_text()
        self.tree = ast.parse(self.src)
        self._real = _real_token_lines(self.src)
        self._doc = _docstring_lines(self.tree)
        self._code = self._real - self._doc
        self.classes = {n.name: n for n in ast.walk(self.tree)
                        if isinstance(n, ast.ClassDef)}

    def count(self, a: int, b: int) -> int:
        return sum(1 for ln in range(a, b + 1) if ln in self._code)

    def total(self) -> int:
        return len(self._code)


def py_file_code_lines(path: Path) -> int:
    return PyFile(path).total()


def glg_signal_loc(path: Path) -> Dict[str, int]:
    """Nonblank/noncomment LOC of each ``signal`` block in a .glg file.

    A block runs from its ``signal NAME ...`` line up to (but not including) the next
    ``signal`` line or EOF. Blank lines, full-line ``#`` comments, and trailing
    ``#`` inline comments do not count; the formula lines do.
    """
    blocks: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if stripped.startswith("signal "):
            m = re.match(r"signal\s+(\S+)", stripped)
            current = m.group(1)
            blocks[current] = [raw]
        elif current is not None:
            blocks[current].append(raw)
    out: Dict[str, int] = {}
    for sig, lines in blocks.items():
        n = 0
        for line in lines:
            code = line.split("#", 1)[0].strip()
            if code:
                n += 1
        out[sig] = n
    return out


def json_nonblank_lines(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


# --------------------------------------------------------------------------- #
# Legacy-class AST breakdown: state / verdict / detection.
# --------------------------------------------------------------------------- #


def _method(cls: ast.ClassDef, name: str) -> Optional[ast.FunctionDef]:
    for m in cls.body:
        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == name:
            return m
    return None


def _rulematch_lines(pf: PyFile, cls: ast.ClassDef) -> Set[int]:
    """Lines inside any ``RuleMatch(...)`` construction within the class (the verdict)."""
    out: Set[int] = set()
    for node in ast.walk(cls):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "RuleMatch"):
            out.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return {ln for ln in out if ln in pf._code}


def legacy_class_line_sets(pf: PyFile, class_name: str) -> Dict:
    """Partition a detector class's code lines into state / verdict / detection.

    Shared by the LOC comparison and the AST-size comparison so both read the same
    boundary. ``state`` = ``__init__`` + ``reset`` bodies; ``verdict`` = lines inside
    ``RuleMatch(...)`` constructions (disjoint from state -- those calls live in
    check/detect); ``detection`` = the remainder.
    """
    cls = pf.classes[class_name]
    class_code = {ln for ln in range(cls.lineno, cls.end_lineno + 1) if ln in pf._code}
    state: Set[int] = set()
    for mname in ("__init__", "reset"):
        m = _method(cls, mname)
        if m is not None:
            state.update(ln for ln in range(m.lineno, m.end_lineno + 1)
                         if ln in pf._code)
    verdict = _rulematch_lines(pf, cls) - state
    detection = class_code - state - verdict
    return {"cls": cls, "class_code": class_code,
            "state": state, "verdict": verdict, "detection": detection}


def legacy_class_breakdown(pf: PyFile, class_name: str) -> Dict[str, int]:
    s = legacy_class_line_sets(pf, class_name)
    return {
        "class": class_name,
        "span": [s["cls"].lineno, s["cls"].end_lineno],
        "total": len(s["class_code"]),
        "state": len(s["state"]),       # -> DSL liveplan.config.json + DriftRuntime
        "verdict": len(s["verdict"]),   # -> DSL liveplan.advice.json
        "detection": len(s["detection"]),  # -> DSL `when` formula (+ emission policy)
    }


# --------------------------------------------------------------------------- #
# Top-level computation.
# --------------------------------------------------------------------------- #


def compute_loc() -> Dict:
    """Compute the full LOC comparison as a plain dict (JSON-serialisable)."""
    rules = PyFile(RULES_PY)
    glg = glg_signal_loc(GLG)

    # Validate that every matched signal exists, and that matched + DSL-only exactly
    # account for every signal declared in the live spec (fail loud if the spec drifts).
    declared = set(glg)
    matched = {sig for g in GROUPS for sig in g["dsl_signals"]}
    for sig in matched | set(DSL_ONLY_SIGNALS):
        if sig not in declared:
            raise ValueError(f"signal {sig!r} not found in {GLG}")
    unaccounted = declared - matched - set(DSL_ONLY_SIGNALS)
    if unaccounted:
        raise ValueError(f"liveplan.glg signals not covered by GROUPS or DSL_ONLY: "
                         f"{sorted(unaccounted)}")

    groups_out: List[Dict] = []
    tot_dsl = tot_legacy_total = tot_legacy_detection = 0
    for g in GROUPS:
        dsl_per = {sig: glg[sig] for sig in g["dsl_signals"]}
        dsl_loc = sum(dsl_per.values())
        legacy_parts = [legacy_class_breakdown(rules, c) for c in g["legacy_classes"]]
        legacy_total = sum(p["total"] for p in legacy_parts)
        legacy_detection = sum(p["detection"] for p in legacy_parts)
        legacy_state = sum(p["state"] for p in legacy_parts)
        legacy_verdict = sum(p["verdict"] for p in legacy_parts)
        tot_dsl += dsl_loc
        tot_legacy_total += legacy_total
        tot_legacy_detection += legacy_detection
        groups_out.append({
            "group": g["group"],
            "condition": g["condition"],
            "note": g["note"],
            "dsl": {
                "signals": dsl_per,
                "n_signals": len(dsl_per),
                "formula_loc": dsl_loc,
            },
            "legacy": {
                "classes": legacy_parts,
                "total": legacy_total,
                "state": legacy_state,
                "verdict": legacy_verdict,
                "detection": legacy_detection,
            },
            "ratio_total": round(legacy_total / dsl_loc, 1) if dsl_loc else None,
            "ratio_detection": round(legacy_detection / dsl_loc, 1) if dsl_loc else None,
        })

    # Shared infrastructure, counted once per side.
    dsl_engine = {m: py_file_code_lines(GLG_DIR / f"{m}.py") for m in DSL_ENGINE_MODULES}
    dsl_binding = py_file_code_lines(GLG_DIR / f"{DSL_BINDING_MODULE}.py")
    legacy_shared_classes = {c: rules.count(*[rules.classes[c].lineno,
                                              rules.classes[c].end_lineno])
                             for c in LEGACY_SHARED_CLASSES}
    shared = {
        "dsl": {
            "engine_modules": dsl_engine,
            "engine_total": sum(dsl_engine.values()),
            "binding_module": {DSL_BINDING_MODULE: dsl_binding},
            "data_json": {
                "liveplan.config.json": json_nonblank_lines(CONFIG_JSON),
                "liveplan.advice.json": json_nonblank_lines(ADVICE_JSON),
            },
            "note": ("Engine + binding are shared Python amortized over every signal; "
                     "the JSON files are shared DATA (thresholds, messages, policies), "
                     "not per-rule code."),
        },
        "legacy": {
            "shared_classes": legacy_shared_classes,
            "shared_classes_total": sum(legacy_shared_classes.values()),
            "monitor_py": py_file_code_lines(MONITOR_PY),
            "phases_py": py_file_code_lines(PHASES_PY),
            "note": ("RuleMatch/Rule/GraphectoryRule bases + RuleEngine (rules.py) plus "
                     "the StatefulPhaseMonitor loop (monitor.py) and phase dataclasses "
                     "(phases.py); shared across all legacy detectors."),
        },
    }

    unmatched = {c: rules.count(rules.classes[c].lineno, rules.classes[c].end_lineno)
                 for c in LEGACY_UNMATCHED_CLASSES if c in rules.classes}

    dsl_only = {sig: glg[sig] for sig in DSL_ONLY_SIGNALS}

    return {
        "scope": ("default liveplan.glg profile only; extra_signals.glg and the "
                  "process taxonomy excluded"),
        "convention": ("nonblank, noncomment physical lines; docstrings count as "
                       "comments; DSL per-rule = signal formula block, legacy per-rule "
                       "= detector class split (state/verdict/detection) via AST"),
        "groups": groups_out,
        "totals": {
            "dsl_formula_loc": tot_dsl,
            "legacy_class_total": tot_legacy_total,
            "legacy_detection_loc": tot_legacy_detection,
            "ratio_total": round(tot_legacy_total / tot_dsl, 1) if tot_dsl else None,
            "ratio_detection": round(tot_legacy_detection / tot_dsl, 1) if tot_dsl else None,
            "n_dsl_signals": sum(len(g["dsl_signals"]) for g in GROUPS),
            "n_legacy_classes": sum(len(g["legacy_classes"]) for g in GROUPS),
        },
        "shared_infrastructure": shared,
        "legacy_unmatched_detectors": unmatched,
        "dsl_only_signals": {
            "signals": dsl_only,
            "rationale": ("No legacy Python counterpart: the legacy OscillationDetector "
                          "catches only strict periodic cycles, so non-periodic prolonged "
                          "recurrence was added natively in the DSL. Excluded from the "
                          "matched comparison (nothing to compare against)."),
        },
    }


# --------------------------------------------------------------------------- #
# Rendering.
# --------------------------------------------------------------------------- #


def to_markdown(result: Dict) -> str:
    L: List[str] = []
    L.append("## LOC: default Drift-QL signals vs legacy Python detectors")
    L.append("")
    L.append(f"_Scope:_ {result['scope']}.  ")
    L.append(f"_Convention:_ {result['convention']}.")
    L.append("")
    L.append("### Per-condition comparison")
    L.append("")
    L.append("| signal(s) | #sig | DSL formula LOC | legacy class LOC | legacy detection LOC | total× | detection× |")
    L.append("|---|--:|--:|--:|--:|--:|--:|")
    for g in result["groups"]:
        names = ", ".join(g["dsl"]["signals"])
        L.append(
            f"| {names} | {g['dsl']['n_signals']} "
            f"| {g['dsl']['formula_loc']} | {g['legacy']['total']} "
            f"| {g['legacy']['detection']} | {g['ratio_total']}× | {g['ratio_detection']}× |"
        )
    t = result["totals"]
    L.append(
        f"| **total** | **{t['n_dsl_signals']}** | **{t['dsl_formula_loc']}** "
        f"| **{t['legacy_class_total']}** | **{t['legacy_detection_loc']}** "
        f"| **{t['ratio_total']}×** | **{t['ratio_detection']}×** |"
    )
    L.append("")
    L.append("`detection×` compares the DSL formula against only the legacy *detection* "
             "lines (class minus the `__init__`/`reset` state and the `RuleMatch` verdict, "
             "which the DSL offloads to shared config/advice data).")
    L.append("")

    L.append("### Legacy per-class offload breakdown")
    L.append("")
    L.append("| legacy class | total | state (→config/runtime) | verdict (→advice) | detection (→formula) |")
    L.append("|---|--:|--:|--:|--:|")
    for g in result["groups"]:
        for p in g["legacy"]["classes"]:
            L.append(f"| {p['class']} | {p['total']} | {p['state']} | {p['verdict']} | {p['detection']} |")
    L.append("")

    L.append("### Per-signal DSL formula LOC")
    L.append("")
    L.append("| signal | formula LOC |")
    L.append("|---|--:|")
    for g in result["groups"]:
        for sig, n in g["dsl"]["signals"].items():
            L.append(f"| {sig} | {n} |")
    L.append("")

    dsl_only = result.get("dsl_only_signals", {}).get("signals", {})
    if dsl_only:
        names = ", ".join(f"`{s}` ({n} LOC)" for s, n in dsl_only.items())
        L.append(f"_DSL-only signals with no legacy counterpart, excluded from the "
                 f"matched comparison: {names}. {result['dsl_only_signals']['rationale']}_")
        L.append("")

    s = result["shared_infrastructure"]
    L.append("### Shared infrastructure (counted once, not charged to any rule)")
    L.append("")
    L.append(f"**DSL engine** (amortized over all signals): "
             f"{s['dsl']['engine_total']} LOC across {len(s['dsl']['engine_modules'])} modules "
             f"+ {list(s['dsl']['binding_module'].values())[0]} LOC live binding "
             f"({list(s['dsl']['binding_module'])[0]}.py); "
             f"shared data: liveplan.config.json {s['dsl']['data_json']['liveplan.config.json']} + "
             f"liveplan.advice.json {s['dsl']['data_json']['liveplan.advice.json']} nonblank JSON lines.")
    L.append("")
    L.append(f"**Legacy shared**: bases + RuleEngine {s['legacy']['shared_classes_total']} LOC "
             f"(rules.py) + monitor.py {s['legacy']['monitor_py']} + phases.py {s['legacy']['phases_py']}.")
    L.append("")
    if result["legacy_unmatched_detectors"]:
        um = ", ".join(f"{k} ({v})" for k, v in result["legacy_unmatched_detectors"].items())
        L.append(f"_Legacy detectors with no default-profile DSL counterpart (excluded): {um}._")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(compute_loc(), indent=2))
