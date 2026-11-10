# Pattern-resolution analysis (GL-Guard replay)

It answers,
per `(instance, config)`: which process signals the trajectory exhibits, whether the task
resolved, and how the intervention configs compare to the baseline.

## Why this exists (the three fixes)

1. **Signals from the real engine, not a re-implementation.** Detection is a non-executing
   replay of each `.traj` through the production GL-Guard monitor
   (`analysis.replay.replay_monitor`) using the **live profile only** (`liveplan.glg`,
   `shadow_specs=()`), so the signals are exactly what the online monitor runs — no
   `extra_signals.glg` shadow candidates. Each is reported as clean `True/False`
   (`n_true > 0`). No `StatefulPhaseMonitor`, no rule-text matching, no `plan_violation`
   inference. (The shadow candidates are studied separately in `analysis.signal_selection`.)

2. **Precise online signals, two complementary sources.** The replay tells us what is true
   on the *committed* trajectory. `planner.json` tells us what fired *online*:
   - **gl_guard runs (v6+):** `state_summary.rule_triggers[].rule_id` carries the exact
     decomposed names (`plan_compliance_skip_patch`, `…_skip_validation`, …). We read the
     structured ids into the `refiner_online_triggers` column. The
     historical `exclude_rule_patterns=["plan_compliance"]` filter is **exact-match**, so
     it never drops the decomposed names — they pass through.
   - **legacy runs (v5, monitor):** the bare `plan_compliance` id *was* excluded, and
     monitor-only entries write no `state_summary`. Rather than lose the online count, we
     **recover plan-compliance structurally** (no fuzzy matching) from two planner.json
     invariants: a refiner entry with `state_summary` present but `rule_triggers` empty
     ⟺ plan-compliance was the sole excluded trigger (the exclusion set is exactly
     `["plan_compliance"]`); a monitor-only entry whose `content` leads with the canonical
     template anchor `"Plan compliance violation:"`. Both emit the generic `plan_compliance`
     token, so a legacy/monitor run's online plan-compliance is never spuriously zero.
     `analyze` reports it family-matched (generic legacy id ∪ gl_guard `plan_compliance_*`)
     against the committed replay.
   `analyze` reconciles the two (`online` vs `committed_only` vs `online_only`): a signal
   that fired on a *blocked, rolled-back* proposal shows as `online_only` (absent from the
   committed trajectory); an advisory / non-refiner firing shows as `committed_only`.
   Neither source alone is complete, which is exactly why both are recorded.
   `state_summary.phase_history` is **not** used — it is a flat, consecutive-deduped role
   list with no step-index mapping and is inconsistent across rollbacks; the replay's
   `role_history` (→ `lang` / `unique_phases`) is the correct, deterministic substitute.

3. **Signal-count-agnostic.** The long table stores signals as a name→bool map, and the
   analyzer folds them into the legacy taxonomy by name (`plan_violation` = any
   `plan_compliance_*`; `oscillation` = oscillation ∪ recurrence ∪ thought; the rest are
   like-named) and appends the finer signals verbatim. Adding/removing a signal in the
   `.glg` just changes the map — no fixed widths, no offsets, no code change.

## Artifacts

Collector — `analysis/analysis-results/pattern-resolution/`:
- `{agent}-{model}-{dataset}.long.json` — one record per `(instance, config)` (a UTF-8 JSON
  array); the machine-readable source of truth consumed by the analyzer. Fields:
  `instance_id, config, resolved, any_signal, has_planner, refiner_online_triggers, lang,
  unique_phases, cost, steps, signals{…}`.
- `{agent}-{model}-{dataset}.wide.csv` — human pivot (one row per instance, configs side by
  side; section widths computed from the data).

Analyzer — `analysis/analysis-results/comparison/detailed-analysis/<config>/`:
- `{agent}-{model}-{dataset}-<config>-analysis.json` — a **drop-in** for the legacy
  detailed-analysis JSON (identical `config` / `summary` / `category_details` /
  `planner_stats` schema), so the `visualize/` and other consumers are unaffected. The only
  change is `patterns`: the legacy 7 buckets (names + semantics preserved) **plus** the
  finer GL-Guard signals. `planner_stats` keeps the online record with precise `rule_ids`.

## Usage

```bash
# 1) collect (replays trajectories; --jobs for parallelism)
python analysis/collect_pattern_resolution.py \
    --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench --jobs 8

# 2) analyze a table vs its baseline (default, else sage)
python analysis/analyze_pattern_resolution.py \
    --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench \
    --config monitor refiner-only refiner

# or the whole matrix
python analysis/run_analysis.py
```

Replaying `monitor` / `refiner` / `refiner-only` trajectories is fully supported (pass the
config and, for versioned configs, `--version`).

## Note on labels

Resolution comes from the official eval reports (3-way: resolved / unresolved / **missing**;
an instance absent from a present report is `missing`). If a config's eval report is absent
*at the queried run*, its transitions are empty (R-R/U-R = 0) until the report is present —
the signals are still fully populated.

## Note on run ids (legacy behavior, unchanged)

One run per config (`--vanilla-run` / `--monitor-run` / `--refiner-run` / …, default run-1;
`--version` default 5 for refiner / refiner-only), and the analyzer locates planner.json
with a single `--run`. Configs whose data lives at a non-default run — e.g. a model whose
monitor/refiner-only trajectories are run-0, or a pro refiner v5 report at run-2 — must be
collected/analyzed with the matching `--*-run`; they are **not** auto-detected (matching the
legacy pipeline).

## Layout

- `schema.py` — record model + long-JSON / wide-CSV I/O (the single source of truth for the
  signal set, shared with the replay engine).
- `sources.py` — trajectory discovery, official labels, cost/step + planner.json metadata,
  and the GL-Guard replay-detail driver.
- `tests/` — signal-count-agnostic schema round-trips, replay detection, and the
  online-vs-committed reconciliation.
