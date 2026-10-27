# GL-Guard ↔ LIVEPLAN: Binding, Emission, and Advice Design

This document refines the [Integration Plan](GL_Guard_Integration_Plan.md) into a
concrete, implemented design for running GL-Guard specifications over the live
Graphectory/Langutory **without a hand-written detector per rule** and **without
changing the semantics of the existing monitor**. It is the design counterpart to
the code now under `plan_monitor/gl_guard/` (`emission.py`, `advice.py`,
`runtime.py`).

It assumes the language itself (grammar, well-formedness, three-valued semantics)
from [`DESIGN.md`](DESIGN.md).

---

## 0. The question in one line

> Can a rule be *detected automatically* from its declarative form — like a SQL
> query — with no per-rule Python, and with its advice message configured
> separately?

**with one honest boundary.** A rule whose condition uses the fixed
primitive vocabulary (`key`, `kind`, `phase`, `before`, `outcome`, `SE`,
`obs_eq`, `exists`, `count`, `run`, `repeat`) is executed by the *one* generic
interpreter — adding a rule is adding a `.glg` line plus a config entry, never a
class. The boundary: a condition needing a relation the vocabulary does not have
(e.g. a dynamic plan automaton, or a non-periodic graph cycle) needs **one**
documented reusable primitive, or must retain its legacy detector as the oracle.
It is automatic *compilation/interpretation*, not automatic *invention* of useful
rules.

The SQL analogy, made precise:

| SQL | GL-Guard |
|---|---|
| Query text | `.glg` signal |
| Tables / indexes | Graphectory `G`, Langutory `L` |
| Storage/access layer | the `World` adapter (occurrence view of `G`/`L`) |
| Query planner + executor | the generic three-valued interpreter |
| `NULL` / three-valued logic | Kleene `?` for unavailable fields |
| Triggers / cursors (stateful firing) | **emission policies** |
| Presentation / formatting | **advice registry** (message templates) |

---

## 1. Three decoupled layers

```
.glg spec ──parse/typecheck once──► checked program (indexed by hook)
                                         │
live G, L ──read-only adapter──► World(H, q, hook)
                                         ▼
                 generic interpreter ──► Kleene verdict  (DETECTION)
                                         ▼
                 emission policy ──────► emit? + variant  (FIRE TIMING)
                                         ▼
                 advice registry ──────► SignalReport{message, block, …} (PRESENTATION)
                                         ▼
                 SignalReport → RuleMatch → existing MonitorResult / refiner
```

* **Detection** is pure and memoryless: the `.glg` condition evaluated on the
  finite prefix. No counters, no cooldown — those are deliberately *not*
  expressible in the language (`DESIGN.md` §3 keeps it finite and stateless).
* **Emission** ([`emission.py`](../emission.py)) is the only stateful "fire
  timing" layer: `always`, `once_per_key`, `on_rising_edge`, `every_n`,
  `cooldown`, `max_per_pattern`. This is where the legacy detectors' counter
  behaviour is reproduced *generically*.
* **Advice** ([`advice.py`](../advice.py)) maps a fired signal to a configured
  message, priority, and intervention — reusing the baseline `default_rules.json`
  messages verbatim.

[`runtime.py`](../runtime.py)'s `GuardRuntime.evaluate(world, commit=…)` is the
single path through all three. There is **no `Rule` subclass per `.glg` rule**.

---

## 2. Read-only binding at the existing hooks (no semantic change)

LIVEPLAN already exposes two decision points; GL-Guard attaches one side-effect-
free evaluation at each (the live engine is selected per run — see §2.1):

| LIVEPLAN call site | GL-Guard hook | `commit` |
|---|---|---|
| `check_step_pre_emptively()` (non-empty action) | `propose` | `False` (tentative) |
| `check_step_pre_emptively()` (empty action → thought) | `observe(thought)` | `False` (tentative) |
| `on_step()` (committed action) | `observe(action)` | `True` (commit) |

**Transactional evaluation = the legacy rollback, mirrored.** The legacy monitor
deep-copies its rule state before a tentative pre-emptive check and restores it if
the action is dropped. `GuardRuntime.evaluate(world, commit=False)` does exactly
this for emission state: `EmissionState.snapshot()` → evaluate → `restore()`.
Thus:

* a **blocking** signal fires at `propose`; because the blocked action never
  commits, its emission is rolled back (it did not "happen"), and the block
  message is surfaced from the propose pass — matching the legacy flow;
* a **non-blocking** signal's agent-facing message is produced at
  `observe(action)` (the committed `on_step`), where emission commits once.

**Adapter contract (the critical part).** The `World` must be built from the
*actual* committed prefix with these rules, using LIVEPLAN's own normalization:

* `history(c)` is strictly before `q`; rejected proposals never enter `G`/`L`.
* At `propose`, `q` is tentative (no outcome, no observation → those fields are
  `?`, and well-formedness already forbids reading them).
* **Do not reconstruct chronology by iterating distinct graph nodes** — one node
  represents many occurrences. Use the node `step_indices` to recover occurrence
  order (the same flattening the legacy oscillation detector uses).
* Preserve `general` filtering and the thought-episode boundary.
* Map `submit` from the configured `ending_flags`, not a guessed command name.

---

## 2.1 Live wiring: `GuardMonitor` and the `monitor_engine` flag

The binding above is realized as a drop-in monitor,
[`GuardMonitor`](../guard_monitor.py), so the agent and the refiner consume it
through the *identical* contract they use for the legacy monitor — no changes to
either beyond one config branch.

* **`GuardMonitor(StatefulPhaseMonitor)`** subclasses the legacy monitor and reuses
  its `__init__` (so the `CommandParser` is seeded with the same tool configs),
  its `GraphBuilder`, role/phase bookkeeping, `thought_history`, `step_counter`,
  and every getter the refiner reads (`get_current_phase`, `get_phase_history`,
  `get_unique_phases`, `graph_builder.G`, `save_graph`). **Only**
  `check_step_pre_emptively` is overridden: it extends the same Graphectory
  (`observation=""`), builds the GL-Guard `World` from it via the adapters, runs
  `GuardRuntime.evaluate`, and maps each fired `SignalReport` onto a genuine
  `RuleMatch` inside a genuine `MonitorResult`. The agent's
  `get_all_messages()` / `should_block_and_refine()` / `rule_matches` path and the
  refiner's `build_state_summary_from_monitor` therefore work unchanged.

* **GL-Guard owns the block decision.** The override runs the legacy transaction —
  tentatively extend `H·q`, evaluate, commit on a non-blocking step or roll the
  extension back on a blocking one — but the verdict and emission timing come from
  the program + advice registry. The persistent dwell stream and non-blocking
  (and `persist_on_block`) emission survive a block; `oscillation` /
  `thought_oscillation` emission is rolled back (`rollback_on_block_ids`). Overhead
  is one graph `deepcopy` per step — *below* the legacy monitor, which also
  deep-copies its rules dict.

* **The `monitor_engine` flag** (`DefaultAgentConfig`, default **`gl_guard`**)
  selects the class in `from_config`:

  ```python
  monitor_cls = GuardMonitor if config.monitor_engine == "gl_guard" else StatefulPhaseMonitor
  agent._plan_monitor = monitor_cls(enable_rules=True, rules_config=config.monitor_rules_config)
  ```

  `monitor_rules_config` still selects the tool-config/parser setup under both
  engines. Setting `monitor_engine: legacy` restores the hand-written `RuleEngine`
  byte-for-byte, which is how the shadow harness keeps the legacy available as a
  differential oracle. **Adding a signal is adding a spec** (`.glg` + an advice
  entry) — no per-rule Python, no agent change.

---

## 3. The two time-scales — the single most important correctness point

LIVEPLAN's detectors do **not** all operate on the same stream. Binding each DSL
operator to the stream its legacy counterpart uses is what makes equivalence
exact.

| Operator | Bound stream | Why |
|---|---|---|
| `run(F)` (dwell) | **step-level** Langutory projection: one symbol per committed trajectory step = that step's *final* phase | `DwellTimeRule` increments **once per `evaluate()` call**, i.e. once per step, using the step's final phase. |
| `repeat(action)` (oscillation) | **occurrence-level** identity stream = the graph exec-path (one entry per node-visit / split command), flattened by `step_indices` | `OscillationDetector` reconstructs the exec path at node granularity, so compound commands contribute several entries. |
| `repeat(thought)` | the **reasoning episode** since the last executable action | matches `ThoughtOscillationRule`'s per-episode hashing. |
| `exists`/`count`/`key`/`outcome`/`obs_eq`/`SE` | occurrence-level history of the channel | these are occurrence predicates. |

> This slightly refines `DESIGN.md` §4: `run`'s projection is the **step-final**
> phase stream, not the raw occurrence stream. In the common one-command-per-step
> case they coincide; for compound commands they differ, and `run` must follow
> the step scale to match dwell.

**Compound commands.** A single step is split (by `commandParser`) into several
commands, each classified to a role; consecutive equal roles are collapsed; the
step's *final* role is its step-level phase. The adapter must:

* feed `run` the step-final phase (step scale);
* feed `repeat(action)` every node-visit (occurrence scale, via `step_indices`);
* let plan-compliance see each within-step phase transition (as the legacy loop
  does) — see §5.

---

## 4. Emission policies ↔ legacy counters (exact mappings)

| Legacy behaviour | DSL condition | Emission policy | Shown equivalent by |
|---|---|---|---|
| Dwell fires at θ, 2θ, 3θ consecutive in-phase steps (resets after firing) | `run(F) >= θ` | `every_n(period=θ)` | `test_emission.test_every_n_reproduces_dwell_timing`, `test_runtime.test_dwell_emits_at_7_and_14_like_legacy`, `…resets_when_phase_breaks` |
| `repeated_view` warns once per command key | `kind(q)=view and revisit(action)` | `once_per_key` (key `q.key`) | `test_runtime.test_action_revisit_once_per_key` |
| Oscillation: warn per motif, `max_repeats` then terminal "stop/submit", then quiet | `repeat(action, …)` | `max_per_pattern(max, terminal_variant)` (key `motif`) | `test_runtime.test_oscillation_blocks_and_hits_terminal_variant` |
| Rate-limited warnings (`min_gap`) | any | `cooldown(gap)` | `test_emission.test_cooldown` |
| First-time only (rising edge) | any | `on_rising_edge` | `test_emission.test_on_rising_edge` |

`every_n` matches dwell because, on the step-level stream, `run(F) >= θ` first
turns true exactly at the θ-th in-phase step and stays true; `every_n(θ)` emits on
the 1st, (θ+1)-th, … consecutive true verdict ⇒ in-phase steps θ, 2θ, 3θ. A phase
break drives the verdict false, which **resets** the counter — matching the
legacy reset.

---

## 5. Per-rule equivalence matrix and honest boundaries

Signal names mirror the legacy rule IDs so the differential is an identity map.

| Signal | Detection | Emission | Equivalence status (measured) |
|---|---|---|---|
| `dwell_L_navigate` / `dwell_L_reproduce` / `dwell_P` / `dwell_V` | `run(F) >= θ` over the persistent dwell stream | `every_n(θ)` | **Exact** — 0 discrepancies over 24,259 real SWE-agent steps. Requires the three binding details in §5.1. |
| `repeated_view` | `kind(q)=view and revisit(action)` | `once_per_key` (`q.key`) | **Exact for simple commands.** Diverges on compound commands: legacy keys by the full trajectory command string, GL-Guard by the merged graph node ("location"). The two identities cannot be unified (`oscillation` needs node merging; legacy `repeated_view` needs full-command distinction). |
| `oscillation` — self-loop + multi-node *periodic* cycles | `cycle(action, up_to=10, times=r)` | `max_per_pattern` keyed by loop node-set, **blocking** | **Precise periodic-loop detector.** Catches self-loops and real period-3/4 cycles (including those the legacy misses). It does *not* fire on the legacy's *non-periodic* back-edge recurrences — those are handled, more conservatively, by `oscillation_recurrence`. See §5.2. |
| `oscillation_recurrence` — excessive non-periodic recurrence | `not kind(q)=general and count{x in history | key(x)=key(q)} >= κ_recur` (κ=7) | `once_per_key` (`q.key`), **non-blocking advisory** | The legacy `two+_node_cycle` case the strict `cycle` misses: a substantive action re-run ≥8× interspersed with varying work (measured 5–23×). High threshold + advisory by design — without observations we cannot tell *stuck* from *productive-but-long*, so it advises rather than blocks. Normalizes to the `oscillation` category. See §5.2. |
| `thought_oscillation` | `repeat(thought, m, r)` on the episode | `max_per_pattern` | Strict consecutive repetition vs the legacy windowed count — see §5.2. |
| `plan_compliance_premature_patch` | `phase(q) in Patch and not seen(Localize)` | `once_per_key`, `persist_on_block`, blocking | legacy `phase_skip [L]`. |
| `plan_compliance_premature_validate` | `phase(q) in Validate and not seen(Patch)` | `once_per_key`, `persist_on_block`, blocking | legacy `phase_skip [P]` **and** `[L,P]` in one predicate — both are "entered Validate with no Patch yet". |
| `plan_compliance_skip_patch` / `_skip_validation` | `kind(q)=submit and not seen(Patch/Validate)` | `once_per_key`, `persist_on_block`, blocking | legacy `premature_ending`. `kind=submit` is matched over the **full** command, like the legacy `ending_flags`. |
| (Family) `plan_compliance` | a memoryless decomposition of the legacy ordered-plan automaton (plan `L→P→V`, `per_violation_type_threshold=1`) | per-type once (`once_per_key` on the signal), blocking, counts survive a block (`persist_on_block`) | **360/362 agreement (99.4% recall, 0 false positives)** on 998 default SWE-agent trajectories. Of the legacy firings, ~96% are `premature_ending` and ~1% `phase_skip`; the decomposition reproduces all of them. Residual = 2 rare out-of-order `phase_skip` orderings the stateful plan-index automaton models but the memoryless predicates don't. **Dynamic plan updates** (`update_intended_plan`) are *not* modeled — the decomposition is the fixed `L→P→V` plan; see §5.2. |

**Rule of engagement:** never replace a stateful legacy detector with `run`/
`repeat` and *claim* equivalence from the table alone. Equivalence is whatever
shadow differential testing (G2 below) demonstrates.

### 5.1 The three binding details that make dwell exactly equivalent

The legacy `DwellTimeRule` is a stateful counter wired into the monitor's control
flow; reproducing it step-for-step required matching three behaviours exactly
(each surfaced as a real discrepancy by the harness and then fixed):

1. **Evaluation occasions.** The monitor evaluates dwell only on steps that yield a
   phase role (its `STEP 4`); a `general`-only step evaluates oscillation and the
   submit-triggered plan-compliance checks (`STEP 1`/`STEP 2`), but *not* dwell.
   GL-Guard therefore evaluates every propose signal **except the `run`-based
   (dwell) ones** on a general-only step (detected structurally via
   `run_signal_names`), so the `every_n` counter is not advanced spuriously while
   oscillation and submit plan-compliance still fire there.
2. **Persistent dwell stream (across block rollbacks).** The dwell counter is
   *non-blocking*, so the monitor **preserves** it even when another (blocking)
   rule rolls the step back. GL-Guard's `run` must therefore read a persistent
   stream that includes blocked roles-steps and every within-step transition —
   not the rolled-back `role_history`. The harness maintains exactly this
   (`ShadowDiffer._dwell_stream`).
3. **Single-phase runs.** The counter resets on any *exact* phase change, so a run
   is a dwell in one identical phase, not merely "k occurrences in the group".
   `run(F) >= k` encodes this (§4 of `DESIGN.md`); it is what makes `dwell_V`
   (with `V_regression_test` / `V_newly_generated_test`) agree.

### 5.2 Do the remaining differences make sense? (reflection)

The non-dwell categories diverge from legacy; the question is whether GL-Guard's
behaviour is *defensible*, not merely different.

* **`oscillation` — does strict periodicity miss harmful loops, and what is the
  *right* signal?** This was reflected on and **measured**, not asserted. Two facts
  drove the design:

  1. **Observations/outcomes are unavailable at `propose`.** The monitor's
     pre-emptive check runs *before* the action executes, so it builds the graph
     with `observation=""`; the agent never feeds the result back. Every node's
     observation/outcome is therefore empty online (verified: all legacy-only
     oscillation nodes had 0 recorded observations). So "is this loop making
     progress?" **cannot** be answered from observations live — only structure
     (node identity, phase, kind) is available. This also means the obs/outcome
     signals in `extra_signals.glg` are *analysis-only*; they cannot fire online.
  2. **The legacy-only cases are high-recurrence, not 2–3-round iteration.** Every
     one had the same node recurring **≥5× (tail to 23×)**, interspersed with
     *varying* edits — so there is no clean period for `cycle`, yet the node
     recurs excessively.

  The response is two complementary signals rather than one blunt one:
  - `oscillation` (strict periodic, **blocking**) stays the precise detector of
    mechanical loops — self-loops and period-k cycles. A clean period is a strong,
    low-false-positive signal, so blocking is justified.
  - `oscillation_recurrence` (**non-blocking advisory**, κ_recur = 7) covers the
    high-recurrence case *conservatively*. The threshold was tuned on the default
    set: at ≥5× it over-fires (+218 `gl_only` — it sweeps in productive edit→test
    iteration the periodic detector rightly ignores), so it is set to ≥8× (clearly
    excessive) and gated to non-`general` actions (benign `cd`/`ls`/env recurrence
    is excluded). Because we cannot distinguish *stuck* from *productive-but-long*
    without observations, it **advises, never blocks** — surfacing the concern
    (and triggering the refiner) without disrupting a long but productive debug.
    This is the "not misleading" choice: a false positive costs one hedged
    message, never a blocked step.

  Net: GL-Guard points at the genuinely harmful loops (mechanical cycles, blocked;
  extreme recurrence, advised) while declining to replicate the legacy's blanket
  blocking of ordinary iterative debugging.

* **`plan_compliance` — can a memoryless decomposition match the stateful
  automaton?** For the firings that actually occur, yes. The legacy automaton's
  real output on the default set is ~96% `premature_ending` (submit before the
  plan is complete) and ~1% `phase_skip`; the four memoryless predicates
  (`premature_patch`, `premature_validate`, `skip_patch`, `skip_validation`)
  reproduce **360/362** of them with **zero** false positives, each firing once
  per violation type (`once_per_key`), blocking, with counts surviving a block
  (`persist_on_block`) — a faithful match to `per_violation_type_threshold = 1`.
  Two subtleties were essential: submission must be detected over the *full*
  command (not the parsed token), matching the legacy `ending_flags`; and the
  submit-triggered checks must be evaluated on `general`-role steps (where submit
  lives), not only on phase-role steps. The residual 2 `legacy_only` are
  out-of-order `phase_skip` orderings whose suppression depends on the legacy
  plan-index advancing — true cross-hook state the finite-prefix DSL omits.
  **Dynamic plan updates** (`update_intended_plan`) are likewise not modeled: the
  decomposition encodes the fixed `L→P→V` plan, so `GuardMonitor.update_intended_plan`
  is a parity shim that records the refined plan but does not re-key the signals.

* **`repeated_view` — does node-level keying misfire?** Yes, it can, and so can
  the legacy's. Legacy keys by the full trajectory command string; GL-Guard keys
  by the merged graph node (the "location"). Consider `sed … && nl file` run
  twice with a *different* `sed`: the legacy sees two different commands and stays
  silent; GL-Guard sees the same `nl file` node and fires "already reviewed this
  location". GL-Guard is arguably more faithful to the *intent* ("you re-viewed
  this location") — **but** if the file was edited between the two views, the
  content differs and the warning is misleading. Neither keying is content-aware.
  The principled, non-misleading signal is **`repeated_unchanged_view`**
  (`extra_signals.glg`), which adds `obs_eq(x, y)` and so fires only when the
  observation is actually unchanged. Recommendation: treat the bare
  `repeated_view` as a coarse advisory (its message already defers to the
  edit-verification case) and prefer the `obs_eq`-guarded variant where precision
  matters. This is a property of the *signal definition*, not a DSL defect — the
  DSL expresses both cleanly.

* **`thought_oscillation` — strict tail vs windowed count.** The legacy fires when
  a thought recurs ≥ k times within a sliding window of 10, catching
  *non-consecutive* repetition (`A X A Y A`). GL-Guard's `repeat(thought, 1, r)`
  requires `r` *consecutive* identical thoughts. For empty-action "think" bursts
  (which are typically consecutive) the two mostly agree; GL-Guard misses the
  interleaved case. Matching it exactly needs a bounded-window operator, which the
  DSL deliberately omits ("no implicit recent window"; recency must be explicit).
  This is the one place the current vocabulary is genuinely less expressive; a
  future `within_last(k)` window primitive — with defined `?`-semantics — would
  close it, and is the honest way to add it rather than hard-coding a window.

---

## 6. Configuring predefined advice (answer to "how are messages configured?")

Messages live **outside** the grammar, in a versioned JSON registry
([`specs/liveplan.advice.json`](../specs/liveplan.advice.json)), one entry per
signal:

```json
"dwell_L_navigate": {
  "enabled": true,                       // shadow-first; explicit promotion
  "key": "signal",                       // emission key
  "emit": {"mode": "every_n", "period": 7},
  "intervention": {"block_execution": false},
  "advice": {"template": "... past {threshold} steps ..."}
}
```

* The baseline messages are the existing `default_rules.json` strings, reused
  verbatim, so monitor-only mode shows identical advice and full-LIVEPLAN mode
  passes identical context to the LLM advisor.
* Templates may reference only **whitelisted** variables (`{phase}`,
  `{threshold}`, `{action}`, `{command}`, `{step}`); tool-derived values are
  escaped and truncated; unknown placeholders fail validation at load.
* `priority` is **optional** (default 0). It only reorders signals that fire at
  the *same* hook; with the default, co-firing signals keep spec declaration
  order, which matches the legacy evaluation sequence. It never affects detection.
* A missing template/policy for an **enabled** signal is a load error — never
  silent empty guidance.
* `block_execution` is per-signal and defaults to advisory. A new signal must not
  block just because it correlates with failure.

Routing: `SignalReport.to_rule_match_kwargs()` constructs the existing
`RuleMatch`; it flows through the unchanged `MonitorResult` → `plan_refiner` →
cooldown/blocking path.

---

## 7. Validation before activation (shadow differential testing)

Detection and emission are validated against the legacy monitor as an **oracle**,
on replayable decisions, before anything is surfaced:

* **G0 Model conformance** — `history` excludes `q`; reads never mutate `G`/`L`;
  compound commands, `general`, missing observations, thought-only episodes, and
  blocked proposals are handled at the right granularity.
* **G1 Language correctness** — reference vs optimized evaluator agree on the
  exact three-valued verdict for every well-typed rule.
* **G2 Legacy differential** — in `shadow` mode, at every matched hook compare
  rule IDs, trigger **step**, ordered `RuleMatch`es, rendered messages, block
  flags, and emission/cooldown counters. Scrutinize dwell resets, graph-cycle
  recognition, once-per-command revisit, thought hashing, and the plan automaton.
* **G3 Preservation** — with GL-Guard disabled or shadow-only, legacy decisions
  and executor-visible inputs are byte-identical on deterministic fixtures.
* **G4 New-rule utility** — replay new specs on committed traces for coverage /
  overlap / overhead; offline replay cannot prove improved resolution.

Only after G0–G3 pass is a rule enabled behind a flag, initially advisory.

### 7.1 G2 status — implemented and run ([`shadow.py`](../shadow.py))

The shadow harness is implemented and runs the real monitor over real
trajectories via the same `check_step_pre_emptively` path as `scan_rule_triggers`,
building each GL-Guard `World` from the monitor's own Graphectory/`role_history`
(no second graph; a deep-copy only on the rare blocked step it must reconstruct).
The reconstruction rebuilds the blocked step with `observation=""`, matching
`check_step_pre_emptively` exactly — important because a node's signature folds in
an observation-derived `edit_status`, so using the real observation there would
change node identity and make GL-Guard miss a self-loop the legacy catches.
Measured over the **default** SWE-agent trajectory set — clean, un-intervened
agent behaviour, which is the honest sample for rule-triggering (the `monitor`/
`refiner` runs already have the monitor's interventions baked in, which suppress
the very patterns being measured). 998 trajectories, 17,254 steps, deepseek-v3:

| category | agree / legacy-only / gl-only | status |
|---|---|---|
| `dwell_L_navigate` / `dwell_L_reproduce` / `dwell_P` / `dwell_V` | 486 / **0** / **0** | **exact** — the §5.1 binding details |
| `plan_compliance` | 360 / 2 / **0** | **99.4% recall, 0 false positives** — the faithful decomposition (§5 matrix, §5.2). Residual = 2 rare out-of-order `phase_skip` orderings. |
| `repeated_view` | 149 / 1 / 15 | exact for simple commands; residual = compound-command full-command vs node keying (§5.2) |
| `oscillation` (incl. `oscillation_recurrence`) | 1337 / 151 / 597 | `cycle` catches mechanical periodic loops precisely (blocking); `oscillation_recurrence` advises on ≥8× non-periodic recurrence (non-blocking). The per-step shadow diff over-counts `gl_only` here because the recurrence advisory and legacy's `two+_node_cycle` fire at *different* steps on the same loop — by design GL-Guard is not replicating legacy's blanket blocking (§5.2). |
| `thought_oscillation` | agrees on consecutive repetition | residual = windowed-but-non-consecutive (§5.2) |

Two measured notes: (1) an earlier run over the `monitor` trajectory sets showed
`oscillation` at 0 legacy-only — the intervened runs simply contain fewer long
loops; the default set is the honest one. (2) A recurrence threshold of ≥5×
over-fired (+218 `gl_only`, sweeping in productive edit→test iteration), which is
why `oscillation_recurrence` uses ≥8× and advises rather than blocks (§5.2).

Run it with `python -m plan_monitor.gl_guard.shadow <traj-or-dir> --agent swe-agent`;
it exits non-zero iff an **exact** category disagrees (a real bug), and prints a
per-category table plus the offending steps. Tested in
[`tests/test_shadow.py`](../tests/test_shadow.py) (dwell exact agreement; blocked
oscillation/thought reconstruction paths).

---

## 8. Minimal next steps (implementation order)

1. **Freeze the baseline** (commit, `default_rules.json`, fixtures exercising
   every detector and emission policy). *(design/ops)*
2. **Live adapter wired to `GraphBuilder`** — the GL-Guard `World` is read from the
   real Graphectory (occurrence exec-path for `repeat`/`revisit`, structural edges
   for `SE`, observations for `obs_eq`) plus the monitor's step-level dwell stream
   for `run`. *(done — [`adapters.py`](../adapters.py): `occurrences_from_graph`,
   `propose_world_from_graph`, `GraphBoundWorld`)*
3. **Generic evaluation + config** — `GuardRuntime` → `SignalReport` → `RuleMatch`
   adapter. *(done — `runtime.py`, `advice.py`, `emission.py`)*
4. **Shadow differential harness** — read-only replay of real trajectories, diffed
   per step against the legacy monitor. *(done — [`shadow.py`](../shadow.py);
   §7.1 results)*
5. **Live monitor + agent wiring** — `GuardMonitor` as a drop-in `StatefulPhaseMonitor`
   selected by the `monitor_engine` flag (default `gl_guard`); plan-compliance
   decomposition enabled and validated (360/362). *(done — §2.1,
   [`guard_monitor.py`](../guard_monitor.py), `SWE-agent/sweagent/agent/agents.py`)*
6. **Oscillation precision (done)** — `cycle` (blocking) for mechanical periodic
   loops + `oscillation_recurrence` (non-blocking advisory, ≥8×, non-`general`) for
   excessive recurrence. Thresholds tuned on the default set (§5.2); observations
   are unavailable at `propose`, so the advisory is the non-misleading choice.
7. **(Optional) incremental optimization** — the per-step occurrence scan
   (≈ the legacy exec-path scan) can be made incremental for very long
   trajectories without changing semantics, checked against the reference evaluator.

**Definition of done.** A developer adds a well-typed `.glg` signal plus a
validated advice entry, and the generic evaluator detects and reports it with no
per-rule Python; with `monitor_engine: legacy` (or shadow) LIVEPLAN's original
decisions and evaluated pipeline are byte-identical. Compatibility is claimed only
to the extent the G2 differential establishes it: dwell exact, plan-compliance
99.4%, oscillation a documented precision/recall difference.

---

## 9. What automation can and cannot do

* **Can:** interpret/compile any rule over the fixed vocabulary with no new code;
  enumerate and *type-check* candidate `.glg` programs mechanically; replay them
  offline to measure coverage and overlap.
* **Cannot (by itself):** invent *useful* diagnostics, choose thresholds that
  help, or prove an intervention improves outcomes. Those require development-data
  tuning and prospective evaluation. New semantic relations must be added as
  single documented primitives with defined `?`-behaviour — never silently
  returning `F` for the unknown.
