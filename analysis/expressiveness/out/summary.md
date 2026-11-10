# GL-Guard (DriftQL) expressiveness

## LOC: default GL-Guard signals vs legacy Python detectors

_Scope:_ default liveplan.glg profile only; extra_signals.glg and the process taxonomy excluded.  
_Convention:_ nonblank, noncomment physical lines; docstrings count as comments; DSL per-rule = signal formula block, legacy per-rule = detector class split (state/verdict/detection) via AST.

### Per-condition comparison

| signal(s) | #sig | DSL formula LOC | legacy class LOC | legacy detection LOC | total× | detection× |
|---|--:|--:|--:|--:|--:|--:|
| dwell_L_navigate, dwell_L_reproduce, dwell_P, dwell_V | 4 | 8 | 51 | 26 | 6.4× | 3.2× |
| oscillation | 1 | 2 | 213 | 175 | 106.5× | 87.5× |
| repeated_view, action_recurrence | 2 | 6 | 50 | 19 | 8.3× | 3.2× |
| thought_oscillation | 1 | 2 | 106 | 56 | 53.0× | 28.0× |
| plan_compliance_premature_patch, plan_compliance_skip_patch, plan_compliance_skip_validation | 3 | 6 | 154 | 104 | 25.7× | 17.3× |
| **total** | **11** | **24** | **574** | **380** | **23.9×** | **15.8×** |

`detection×` compares the DSL formula against only the legacy *detection* lines (class minus the `__init__`/`reset` state and the `RuleMatch` verdict, which the DSL offloads to shared config/advice data).

### Legacy per-class offload breakdown

| legacy class | total | state (→config/runtime) | verdict (→advice) | detection (→formula) |
|---|--:|--:|--:|--:|
| DwellTimeRule | 51 | 15 | 10 | 26 |
| OscillationRule | 11 | 6 | 0 | 5 |
| OscillationDetector | 202 | 8 | 24 | 170 |
| RepeatedViewRule | 50 | 11 | 20 | 19 |
| ThoughtOscillationRule | 106 | 10 | 40 | 56 |
| PlanComplianceRule | 154 | 22 | 28 | 104 |

### Per-signal DSL formula LOC

| signal | formula LOC |
|---|--:|
| dwell_L_navigate | 2 |
| dwell_L_reproduce | 2 |
| dwell_P | 2 |
| dwell_V | 2 |
| oscillation | 2 |
| repeated_view | 2 |
| action_recurrence | 4 |
| thought_oscillation | 2 |
| plan_compliance_premature_patch | 2 |
| plan_compliance_skip_patch | 2 |
| plan_compliance_skip_validation | 2 |

_DSL-only signals with no legacy counterpart, excluded from the matched comparison: `action_recurrence` (4 LOC). No legacy Python counterpart: the legacy OscillationDetector catches only strict periodic cycles, so non-periodic prolonged recurrence was added natively in the DSL. Excluded from the matched comparison (nothing to compare against)._

### Shared infrastructure (counted once, not charged to any rule)

**DSL engine** (amortized over all signals): 1703 LOC across 13 modules + 195 LOC live binding (guard_monitor.py); shared data: liveplan.config.json 34 + liveplan.advice.json 93 nonblank JSON lines.

**Legacy shared**: bases + RuleEngine 215 LOC (rules.py) + monitor.py 448 + phases.py 109.

_Legacy detectors with no default-profile DSL counterpart (excluded): PhaseTransitionRule (24), StrategyShiftRule (23)._

## Program size (AST nodes) — conciseness cross-check

_Metric:_ program size in AST nodes (conciseness companion to LOC; not an edit distance, not expressive power).  
_Caveat:_ cross-language node counts are only weakly commensurable; the DSL count is a conservative upper bound (cycle/seen/revisit are desugared before counting).

| signal(s) | DSL AST nodes | legacy class nodes | legacy detection nodes | total× | detection× |
|---|--:|--:|--:|--:|--:|
| dwell_L_navigate, dwell_L_reproduce, dwell_P, dwell_V | 12 | 232 | 128 | 19.3× | 10.7× |
| oscillation | 31 | 1324 | 1156 | 42.7× | 37.3× |
| repeated_view, action_recurrence | 19 | 227 | 119 | 11.9× | 6.3× |
| thought_oscillation | 3 | 552 | 416 | 184.0× | 138.7× |
| plan_compliance_premature_patch, plan_compliance_skip_patch, plan_compliance_skip_validation | 25 | 769 | 567 | 30.8× | 22.7× |
| **total** | **90** | **3104** | **2386** | **34.5×** | **26.5×** |

`oscillation`'s 31 nodes are inflated by desugaring — the author writes one `cycle(action, up_to=10, times=r_action)` construct, which expands to a 10-way disjunction before counting — so that row's DSL size is a loose upper bound.

_DSL-only signal excluded from the matched comparison: `action_recurrence` (12 nodes)._

