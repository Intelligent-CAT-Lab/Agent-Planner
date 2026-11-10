# analysis/expressiveness — GL-Guard (DriftQL) expressiveness

Does the GL-Guard DSL express the drift conditions it was built for using its
existing operators and runtime data, and how much rule-specific code does that take
versus the Python detectors?

**Scope — the LIVE default profile only.** The study compares the default
signals in `plan_monitor/gl_guard/specs/liveplan.glg` against the five legacy
detector classes in `plan_monitor/rules.py` that implement the same conditions. The
shadow `extra_signals.glg` candidates and the 50-entry process taxonomy are
deliberately **out of scope**: the extra signals have no legacy Python counterpart
(nothing to compare against), and the taxonomy is a catalogue, not an implementation.

| drift condition | default DSL signals | Python detector(s) |
| --- | --- | --- |
| Prolonged single-phase dwell | `dwell_L_navigate`, `dwell_L_reproduce`, `dwell_P`, `dwell_V` | `DwellTimeRule` |
| Action oscillation | `oscillation` | `OscillationRule` + `OscillationDetector` |
| Action revisit | `repeated_view` | `RepeatedViewRule` |
| Thought oscillation | `thought_oscillation` | `ThoughtOscillationRule` |
| Plan-order compliance | `plan_compliance_{premature_patch,premature_validate,skip_patch,skip_validation}` | `PlanComplianceRule` |

`action_recurrence` is a twelfth default signal with **no** legacy counterpart (the
legacy `OscillationDetector` catches only strict periodic cycles; non-periodic
prolonged recurrence was added natively in the DSL). It is reported in text and
excluded from the matched LOC comparison — there is nothing to compare it against.

## What it produces

1. **LOC comparison** (`loc.py`) — the headline, always computed. Pure and
   deterministic; reads source only.
2. **AST-node program size** (`astsize.py`) — a formatting-robust companion to LOC,
   always computed. Same size dimension as LOC but immune to line-wrapping/whitespace.
3. **Behavioral agreement** (`behavioral.py`) — opt-in (`--behavioral`). Reuses the
   production shadow differential (`plan_monitor.gl_guard.shadow`) to replay both
   implementations over the same recorded trajectory prefixes and report where they
   agree, disagree, and why.

All are written to `out/{analysis.json, summary.md}`.

### A note on AST size vs "expressiveness"

Comparing AST node counts *across two languages*, or an AST *edit distance* between a
DSL and a Python program, is **not** an accepted way to measure expressive power: node
taxonomies differ (counts aren't commensurable) and tree size is a *syntactic
conciseness* proxy, not expressiveness (which is argued à la Felleisen, or shown via
coverage). Edit distance is additionally syntax-dominated. So `astsize.py` reports
*program size* only — the within-language convention used by DSL papers (ImageEye
reports DSL program sizes; Spytial counts operations) — explicitly as a conciseness
cross-check on LOC, **not** as an expressiveness claim and **not** as an edit distance.
The DSL node count is a conservative upper bound (the parser desugars
`cycle`/`seen`/`revisit` before counting, e.g. `cycle(..., up_to=10, ...)` → a 10-way
disjunction), so the reported advantage is a lower bound.

## Counting convention (one rule, both languages)

A *code line* is a nonblank, noncomment physical source line; a module/class/function
docstring counts as a comment. The same nonblank/noncomment rule applies to `.glg`.

A GL-Guard signal is three decoupled pieces (`DSL_REFERENCE.md`): detection (`.glg`),
thresholds (`liveplan.config.json`), and message + fire-timing
(`liveplan.advice.json`). Only the detection formula is rule-specific *code*; the rest
is shared **data** driven by a shared **engine**. So:

- **DSL per-rule cost** = the `signal NAME on HOOK when <formula>` block.
- **Legacy per-rule cost** = the detector class(es) + rule-specific helpers, split
  objectively from the Python AST into the parts the DSL offloads to its shared
  layers:
  - `state` = `__init__` + `reset` → DSL `config.json` + `GuardRuntime`
  - `verdict` = `RuleMatch(...)` constructions → DSL `advice.json`
  - `detection` = everything else (predicate + the rule-local suppression / rate
    state machine) → DSL `when` formula + the shared emission policy

The apples-to-apples figure is **DSL formula LOC vs legacy `detection` LOC**. The
class total and the offload breakdown are reported alongside. Message-prep lines
(`.replace`/`.format` outside a `RuleMatch` call) are left in `detection`, biasing the
legacy count upward — so the reported DSL advantage is a lower bound. Shared
infrastructure is counted once per side and never folded into a per-rule number.

The behavioral check leaves textual/AST edit distance out on purpose: it reflects
syntax, not behavior. The meaningful "distance" is the number of paired hook
evaluations that disagree, which is exactly what `behavioral.py` reports.

## Reproduce

```sh
PY=/home/shuyang/miniconda3/envs/planner/bin/python
# LOC only (instant)
$PY -m analysis.expressiveness.analyze
# LOC + behavioral agreement over the in-scope default trajectories
$PY -m analysis.expressiveness.analyze --behavioral \
    --swe-root SWE-agent --pro-root SWE-bench_Pro-os/SWE-agent --jobs 8
# smoke test behavioral on the first N trajectories
$PY -m analysis.expressiveness.analyze --behavioral --limit 40
# tests
$PY -m pytest analysis/expressiveness/tests -q
```

## Reading the results

- **LOC.** The default signals are 1–4 formula lines each; each legacy detector is a
  class an order of magnitude larger. Much of that legacy bulk is exactly the
  `state` + `verdict` machinery (and the per-rule `max_repeats` / `warned_commands`
  suppression counters inside `detection`) that the DSL replaces with shared,
  data-driven emission policies — so even the conservative detection-only ratio stays
  large.
- **Behavioral.** The four `dwell_*` categories are **exact**: the DSL
  `run(Group) >= theta` must reproduce the legacy counter step-for-step, and any
  discrepancy is flagged as a bug. The other categories are **known-difference**: the
  DSL's memoryless / strict-period / node-identity semantics diverge from the legacy
  stateful detectors for documented, benign reasons (bounded escalation, strict
  period vs windowed scan, memoryless vs stateful plan automaton, node-identity vs
  full-command revisit) — see the `plan_monitor.gl_guard.shadow` module docstring.
  These are reported, not asserted. Agreement establishes the two implementations
  compute the same verdicts on the tested inputs; whether *intervening* helps the
  agent is a separate steering experiment, not something replay can establish.
