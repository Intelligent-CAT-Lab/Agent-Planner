# GL-Guard → LIVEPLAN: Implementation and Validation Plan

**Objective.** Execute newly authored GL-Guard specifications over LIVEPLAN's incrementally maintained Graphectory/Langutory state **without writing a Python detector for each rule**, while preserving the original monitor, intervention policy, and existing evaluation results.

**Basis.** The supplied `DESIGN.md` documents an existing lexer/parser, type checker, AST, Kleene evaluator, `GuardProgram`, `World` model, and adapters. The implementation contains `StatefulPhaseMonitor`, `RuleEngine`, `RuleMatch`, and [`default_rules.json`](https://github.com/Intelligent-CAT-Lab/Agent-Planner/blob/main/plan_monitor/config/default_rules.json). The proposed integration below is **not a claim that the unprovided local GL-Guard implementation has been tested**.

## 1. Core design: a query engine, not a rule-code generator

```text
.glg specification ──parse/typecheck once──► AST / checked program
                                              │
Existing G, L ──read-only adapter──► World(H,q)│
                                              ▼
                              generic AST interpreter (T/F/?)
                                              │
                               SignalEvent(rule_id, witness)
                                              ▼
                     message/policy registry ──► RuleMatch
                                              │
                   existing LIVEPLAN advisor + intervention processor
```

**SQL-like automatic execution is possible.** The author supplies a declarative query; the generic interpreter evaluates its AST using a fixed vocabulary of primitives (`key`, `kind`, `phase`, `before`, `outcome`, `SE`, `obs_eq`, `exists`, `count`, `run`, `repeat`). An **additional rule using only these supported primitives requires no new detector class**. This is *automatic interpretation/compilation*, **not** automatic invention of useful rules or arbitrary semantic detectors. A proposed signal requiring a new relation (e.g. `same_test_failure` or `changed_file_since`) needs a **single documented primitive/extractor** and well-defined semantics before specifications may use it. Unknown observations return `?`, not an invented Boolean value.

A valid example using the grammar from `DESIGN.md`:

```text
signal repeated_failed_edit on propose when
    kind(q) = edit and
    count {x in history(action) |
        kind(x) = edit and key(x) = key(q)
        and outcome(x) = failure
    } >= edit_retry_threshold
```

Here `edit_retry_threshold` is configured, not chosen implicitly by the language. `q` is pending at `propose`, so the rule counts **earlier committed failures**, never a hypothetical failure of `q`.

## 2. Preserve the execution model; add a read-only binding

| Preserve exactly | Add or modify minimally |
|---|---|
| `plan_monitor/buildGraph.py`, `mapLang.py`, `phases.py`, command parsing and phase classifications | `TrajectoryModel/World` adapter exposing an **ordered occurrence view** of the actual G/L and hook context |
| `StatefulPhaseMonitor.check_step_pre_emptively()` and `on_step()` timing, tentative update and rollback | One **optional, side-effect-free GL-Guard evaluation call** at the corresponding decision point |
| Original `RuleEngine`, its counters, ordering, messages, rate limits, and plan-update behavior | A selectable `legacy | shadow | gl_guard` backend; default stays `legacy` |
| `RuleMatch`, `MonitorResult`, predefined advice path, `plan_refiner` and cooldown/blocking logic | A generic `SignalEvent → RuleMatch` adapter and declarative message/policy bindings |
| Raw trajectories, evaluation scripts, result tables, original JSON | New differential-test logs and offline query-replay reports; do not rewrite original results |

**Adapter contract (critical).** Define `world_for_propose(...)` from the actual committed prefix plus a *tentative*, non-executed `q`; `world_for_observe(...)` from the newly committed `q` with `history(c)` **strictly before** it. Expose the graph's action identity, occurrence indices/outcomes/observations/structural edges and Langutory phase projection using the **same** normalization as LIVEPLAN. The adapter must not reconstruct chronology by iterating distinct graph nodes: one node can represent many occurrences. Handle multiple subcommands/phases inside one step in the same places the existing monitor does; do **not** collapse step-level actions and phase occurrences into one assumed time scale. Preserve `general` filtering and thought-episode boundaries. Map `submit` using the actual configured `ending_flags`, not a guessed action name.

**No dual mutation.** In `shadow` mode, the legacy monitor alone updates G/L, the compliance automaton, warned-command sets, oscillation counters, and advisor state. GL-Guard takes a snapshot/read-only view and returns diagnostic events only. Rejected proposals are absent from committed history. Observation hooks run only after execution and cannot retroactively block that action.

## 3. One generic rule-evaluation path

1. **Load once:** `GuardProgram.load(glg_path, config_path)`; parse, resolve groups/parameters, type-check, and index rules by hook. Abort on unbound variables, invalid channel use, or missing configuration.
2. **Bind:** At an existing pre-execution or post-observation decision point, build `World(H,q,hook)` from the actual G/L (and observed metadata). Do not change phase classification.
3. **Evaluate:** For every rule at the hook, run the *same* AST interpreter; return `T`, `F`, or `?` and, optionally, a finite witness (matched occurrence IDs, phase positions, graph edges). Fire only on `T`.
4. **Route:** Convert each true verdict to a stable `SignalEvent(rule_id, hook, parameters, witness, metadata)`. Keep detection separate from deduplication, message generation, and intervention.
5. **Emit:** A generic policy/message registry creates the existing `RuleMatch(rule_id, message, block_execution, metadata, step_index)`, respecting order/priority and the chosen rule-emission policy. Forward through the existing `MonitorResult` and advisor pathways **only in an explicitly enabled GL-Guard mode**.

**Important compatibility limit.** The ten signal *concepts* are expressible, but the current language does not automatically reproduce all historical **emissions**. In `rules.py`, dwell detectors reset their counters after firing; repeated views have per-command one-time warning state; plan compliance uses a stateful plan index, seen/attempted phases, and per-violation limits; oscillation checks use recent-path pattern recognition and pattern-specific counters. Strict `repeat(...)` is not identical to every legacy graph-cycle test. **Do not replace these with `run` or `repeat` and claim equivalence.** Initially keep legacy emission/policy state as the oracle; implement explicit *generic* emission policies (`once_per_key`, `every_n`, `on_rising_edge`, `cooldown`, `max_per_pattern`) only where their semantics can be defined and verified. If the underlying detection condition itself differs (e.g. dynamic plan-compliance automaton or non-periodic cycles), either add a small, specified reusable primitive or retain the legacy detector for that baseline signal. No hidden callback to handwritten rule code should be described as fully compiled DSL evaluation.

## 4. Configure predefined advice independently of the DSL

The `.glg` file specifies **when** a signal is true. A declarative registry specifies **what happens**. Retain `default_rules.json` as the canonical baseline configuration, including its existing messages. For new signals, use a separate versioned config, conceptually:

```yaml
signals:
  repeated_failed_edit:
    enabled: false             # shadow first; explicit promotion to active
    params:
      edit_retry_threshold: <chosen-on-development-data>
    priority: 50
    emit: {mode: on_rising_edge}
    advice:
      template: "The same edit has failed repeatedly. Inspect the failure and adjust the target or edit."
    intervention:
      block_execution: false   # advisory by default
```

`<chosen-on-development-data>` is a **documentation placeholder**, not a valid numeric config value: replace it with a validated integer before loading. The registry is *outside* the grammar, unless the language is intentionally extended with a typed policy section. Allow only **whitelisted template variables** from typed signal metadata and witness fields (e.g. `{threshold}`, `{action}`, `{phase}`, `{skipped}`); validate placeholders at startup and escape/truncate user-controlled tool output. A missing message/policy should fail configuration validation for active rules, not silently produce empty guidance.

**Routing:** use the existing `RuleMatch.message` as predefined monitor advice in monitor-only mode and as signal context for the LLM advisor in full LIVEPLAN. The existing refiner, cooldown and blocking decision remain unchanged. Multiple simultaneous matches must use the original ordering/prioritization when comparing with the legacy system. A new GL-Guard signal must not automatically default to blocking merely because it correlates with failure.

## 5. Scientific validation before activating anything

| Gate | Experiment and acceptance criterion |
|---|---|
| **G0 — Model conformance** | Synthetic prefixes with repeated graph nodes, compound commands, phase transitions, `general`, missing observations, thought-only episodes, pending actions, and blocked proposals. Check `history` excludes `q` and the committed G/L is unchanged by reads. |
| **G1 — Language correctness** | For every well-typed rule, direct reference interpretation versus optimized evaluator on the same `World`: exact three-valued verdict agreement. No unsupported primitive silently returns `F`. |
| **G2 — Legacy differential testing** | **Shadow-mode** comparison at every matched hook: normalized raw conditions, rule IDs, trigger timing, ordered `RuleMatch`s, formatted messages, block flags, and emission/cooldown counters. Record all discrepancies by cause. Check specially the plan-state automaton, periodic dwell resets, graph-cycle recognition, once-per-command revisit, and thought-history hashing. |
| **G3 — Preservation** | With GL-Guard disabled or shadow-only, original intervention decisions and executor-visible inputs must be identical to the baseline on deterministic fixtures; repeat representative end-to-end smoke runs. Do not assume stochastic trajectories themselves will be byte-identical. |
| **G4 — New-rule utility** | Replay new specifications on **Vanilla committed traces** (and true proposal logs, if available): coverage, marginal detection, overlap, monitoring overhead, and manually assessed actionability. Offline replay cannot establish improved resolution or infer suppressed proposals that were never recorded. |

**Only after G0–G3 pass:** enable a new rule behind a feature flag, initially advisory. Run a limited prospective study if claiming it improves agent outcomes. **Do not rerun the old benchmark matrix merely to validate a compatible interpreter.** Keep the original outcomes attributed to the original evaluated implementation unless compatibility evidence supports a narrower equivalence claim.

## 6. Minimal implementation order

1. **Freeze baseline:** pin repository commit, `default_rules.json`, model settings, scripts, and existing trajectories. Export fixtures exercising every detector and emission policy.
2. **Finish the adapter:** `World` must be sourced from the actual `GraphBuilder`, Langutory state, proposal and observation hooks; audit occurrence/phase granularity and action-vs-thought identity. Add a non-mutating snapshot API.
3. **Generic evaluation and configuration:** connect `GuardProgram.fired`/verdicts to the `SignalEvent` interface; add one message/policy registry; do not subclass `Rule` per `.glg` rule.
4. **Shadow instrumentation:** insert read-only evaluation after the original tentative construction and before the original decision; record both outputs without changing execution. Compare raw truth separately from emitted warnings.
5. **Incremental optimization (only if needed):** index occurrence counts, phase runs, and repeated motifs **without changing semantics**; compare with the reference interpreter.
6. **Offline taxonomy study:** register a few supported new rules, validate their witnesses and incremental coverage, and only then consider controlled activation. Future synthesis can enumerate/check DSL programs, but *usefulness and interventions still need empirical validation*.

**Definition of done:** A developer adds a well-typed `.glg` signal plus a validated config entry, and the generic evaluator detects and reports it without any per-rule Python implementation; when `legacy` or `shadow` is selected, LIVEPLAN's original execution decisions and evaluated pipeline remain unchanged. Claims of exact ten-rule compatibility are limited to what differential testing establishes.
