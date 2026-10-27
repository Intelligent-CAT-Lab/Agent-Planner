# GL-Guard — Formal Design of the Process-Monitoring DSL

GL-Guard is a small declarative language for specifying LIVEPLAN's diagnostic
*process* signals — the heuristics that currently live as hand-written Python in
[`plan_monitor/rules.py`](../../rules.py). It is a **specification layer**: it
does not re-implement the Graphectory `G` or the Langutory `L`, nor the online
intervention hook; it expresses the conditions those representations already
support, with a precise, machine-checkable semantics.

This document is the authoritative design for the implementation under
`plan_monitor/gl_guard/`. It refines the overview in
[`GL_Guard_Design.docx`](GL_Guard_Design.docx), and where it tightens or corrects
that overview the change is flagged in **§7 Critical review**.

---

## 1. Process model (inherited, not contributed)

At a committed execution prefix `H`:

* **Graphectory** `G = (V, TE ⊎ SE)` merges occurrences of the same action into
  nodes, records chronological order via temporal edges `TE`, and relates
  code-navigation resources via structural edges `SE`.
* **Langutory** `L` maps committed action occurrences to a configured phase
  sequence (`L_navigate`, `L_reproduce`, `P`, `V_newly_generated_test`,
  `V_regression_test`, or `general`).
* LIVEPLAN also exposes **thought** occurrences for reasoning-loop analysis.

A rule inspects a distinguished **current occurrence** `q`:

* at `propose`, `q` is a *not-yet-executed* action (no outcome, no observation);
* at `observe(action)` / `observe(thought)`, `q` is a *newly committed* occurrence.

`history(c)` is the committed occurrences of channel `c` **strictly before** `q`.
A pending or rejected proposal has no execution outcome.

These representations are prerequisites. GL-Guard's contribution is the language
and its semantics.

---

## 2. Concrete syntax (EBNF)

```
program ::= { rule }
rule    ::= "signal" ID "on" hook "when" formula
hook    ::= "propose" | "observe" "(" channel ")"
channel ::= "action" | "thought"

formula ::= or_expr
or_expr ::= and_expr { "or"  and_expr }
and_expr::= unary   { "and" unary   }
unary   ::= "not" unary
          | exists
          | primary
exists  ::= "exists" ID "in" "history" "(" channel ")" ":" or_expr   (* body is greedy *)
primary ::= "true" | "false"
          | "(" or_expr ")"
          | count | run | repeat
          | atom | derived

count   ::= "count" "{" ID "in" "history" "(" channel ")" "|" or_expr "}" ">=" intexpr
run     ::= "run" "(" group ")" ">=" intexpr
repeat  ::= "repeat" "(" channel "," "length" "=" intexpr "," "times" "=" intexpr ")"

atom    ::= "key"  "(" term ")" "=" "key" "(" term ")"
          | "kind" "(" term ")" "=" ID
          | "phase""(" term ")" "in" group
          | "before" "(" term "," term ")"
          | "outcome" "(" term ")" "=" ID
          | "SE" "(" "node" "(" term ")" "," "node" "(" term ")" ")"
          | "obs_eq" "(" term "," term ")"

derived ::= "seen" "(" group ")"
          | "revisit" "(" channel ")"
          | "cycle" "(" channel "," "up_to" "=" INT "," "times" "=" intexpr ")"

term    ::= ID                       (* q or a bound variable *)
group   ::= ID | "{" ID { "," ID } "}"
intexpr ::= INT | ID                 (* literal or named config parameter *)
```

**Precedence & associativity.** `not` > `and` > `or`; `and`/`or` are
left-associative and flattened into n-ary nodes. Parentheses override. A
quantifier body is **greedy** — it extends to the right as far as possible —
which is the standard binder convention and matches every example in the design
doc. Comments run from `#` to end of line.

**Derived operators** are pure surface sugar, desugared by the parser into the
core language so the checker and interpreter never see them:

```
seen(F)                      ≡  exists s in history(action) : phase(s) in F
revisit(c)                   ≡  exists r in history(c)      : key(r) = key(q)
cycle(c, up_to=K, times=r)   ≡  repeat(c,1,r) or repeat(c,2,r) or … or repeat(c,K,r)
```

`cycle` captures "stuck in a loop of **any period up to K**": a self-loop `A A`
at period 1, `A-B-A-B` at period 2, `A-B-C-A-B-C` at period 3, and so on. `up_to`
must be an integer literal so the disjunction is expanded at parse time. It exists
because a bare `repeat(action, length=1, times=r)` catches *only* self-loops and
silently misses multi-node loops — see §7.3.

---

## 3. Well-formedness (static checking)

Well-formedness is what makes the three-valued semantics sound: every term is
bound to an occurrence of a definite channel, channel-typed predicates apply only
where they type-check, and no rule reads a field the hook cannot provide. A
variable's channel is that of its binder; `q`'s channel is the hook's channel.

| # | Rule |
|---|------|
| W1 | Only `q` may be free; all other variables must be bound by `exists`/`count`. No shadowing. |
| W2 | `kind`, `phase`, `outcome`, `SE` require **action** occurrences. |
| W3 | `key(u)=key(v)` requires `u`,`v` on the **same** channel. |
| W4 | At `propose`, `outcome(q)` and any `obs_eq` mentioning `q` are **invalid** (no outcome/observation yet). |
| W5 | `run(F)` requires an **action** hook (`propose` or `observe(action)`). |
| W6 | `repeat(c,…)` requires `c` to equal the hook's channel. |
| W7 | Integer literals are positive; `times` (`r`) ≥ 2; named params are checked against config. |
| W8 | `kind`/`outcome` literals and group/param references resolve against config. |

Implemented in [`typecheck.py`](../typecheck.py); violations are reported *all at
once* per rule.

---

## 4. Three-valued finite-prefix semantics

Verdicts range over **strong Kleene** `{T, F, ?}` ([`kleene.py`](../kleene.py)).
`?` means a well-typed field is unavailable (e.g. an observation was not
recorded); the monitor should abstain rather than guess. A rule **fires** iff its
verdict is `T`.

Let `H` be the committed occurrence sequence, `q` the current occurrence, and `ρ`
the binding of historical variables. We write `⟦φ⟧(H, q, ρ) ∈ {T, F, ?}`.

* `before(u,v)` is strict chronological order (`u.oid < v.oid`).
* `key` maps an occurrence to its graph-node / action identity; `SE` follows the
  directed structural relation of `G`; `obs_eq` uses a declared
  equality/normalization relation on observed outputs — never inferred semantics.
* At `propose`, phase-run and repetition checks form the *tentative* extension
  `H·q` **without committing** `q`. At `observe(c)`, `q` is already recorded and
  the monitor evaluates the same logical extension. In both cases `history(c)`
  excludes `q`, so a rule can never count `q` as its own predecessor.

**Atoms.** A field that is unavailable yields `?`; otherwise the atom is the
definite lift of the underlying comparison. `phase(u) in F` is `F` for a
`general`/unclassified occurrence (it belongs to no named group).

**Connectives.** Strong Kleene (`not`, n-ary `and`/`or`).

**Quantifiers** over `history(c)`:

* `exists x : φ` — `T` if some instance is `T`; `F` if **all** are `F` (including
  an empty history); `?` otherwise.
* `count {x | φ} >= k` — with `a` definitely-true and `b` unknown instances:
  `T` if `a ≥ k`; `F` if `a + b < k`; `?` otherwise.

**Phase run.** Let `P` be the Langutory phase projection of `H·q` (occurrence
order; `general` dropped; unavailable phases appear as `?` symbols; **occurrences
are counted, not compressed runs**). A *run* is a maximal dwell in a **single**
phase — the last `k` occurrences must be the *same* phase and it must lie in `F`:

```
run(F) >= k   ≡   |P| ≥ k  ∧  (last_k(P) are all equal)  ∧  ⋀_{s ∈ last_k(P)} (s ∈ F)
```

evaluated in Kleene (length `< k` ⇒ `F`; a definite phase change inside the last
`k` ⇒ `F`; an unknown symbol that could change the verdict ⇒ `?`). The
single-phase requirement mirrors the legacy `DwellTimeRule`, whose counter resets
on any exact phase change: a mix of `V_regression_test` and `V_newly_generated_test`
is *not* a run even though both are in the `Validate` group. (For single-valued
phase groups — `Navigate`, `Reproduce`, `Patch` — identity and membership
coincide, so this only refines the multi-phase `Validate` case.)

**Repetition.** Let `s = s₁ … sₙ` be the identity stream of `H·q`:

* for `action`: the key of every action occurrence through `q`;
* for `thought`: the keys of the **uninterrupted reasoning episode** ending at
  `q` (the maximal suffix since the last executable action — feedback-separated
  thoughts are not conflated).

Then, for `m ≥ 1`, `r ≥ 2`:

```
repeat(c, length=m, times=r)   ≡   n ≥ m·r  ∧  ∀ j ∈ [0, m(r−1)) :  s[n−j] = s[n−m−j]
```

(`AAA` for `m=1,r=3`; `ABAB` for `m=2,r=2`). Unknown identities that could change
the verdict yield `?`.

Implemented in [`interpreter.py`](../interpreter.py); the model that supplies the
streams and relations is [`model.py`](../model.py).

---

## 5. The ten original LIVEPLAN signals

Expressed in [`specs/liveplan.glg`](../specs/liveplan.glg); thresholds and phase
groups come from [`specs/liveplan.config.json`](../specs/liveplan.config.json).

| LIVEPLAN signal | GL-Guard condition |
|---|---|
| Premature Patching | `on propose: phase(q) in Patch and not seen(Localize)` |
| Skip Patching | `on propose: kind(q)=submit and not seen(Patch)` |
| Skip Validation | `on propose: kind(q)=submit and not seen(Validate)` |
| Thought Oscillation | `on observe(thought): repeat(thought, length=m, times=r)` |
| Action Oscillation | `on propose: repeat(action, length=m, times=r)` |
| Prolonged Navigation | `on propose: run(Navigate) >= θ_N` |
| Prolonged Reproduction | `on propose: run(Reproduce) >= θ_R` |
| Prolonged Patching | `on propose: run(Patch) >= θ_P` |
| Prolonged Validation | `on propose: run(Validate) >= θ_V` |
| Action Revisit | `on propose: kind(q)=view and revisit(action)` |

## 6. Representative additional signals

In [`specs/extra_signals.glg`](../specs/extra_signals.glg): `stale_validation`,
`repeated_failed_edit`, `failed_patch_backtrack`, `repeated_unchanged_view`.
These are candidate diagnostics composed from existing observations — not proven
failures or validated interventions.

---

## 7. Critical review of the original overview

The design doc is sound; the implementation tightens the following points so the
semantics are unambiguous and executable:

1. **Quantifier scoping was implicit.** The doc's examples (§7.1, §7.3) only
   parse correctly if the quantifier body is *greedy*. We make that an explicit
   grammar rule (§2) and test it.
2. **`general` vs unknown phases.** The doc's phase projection "respects
   Langutory's treatment of general actions" without saying what that is. We
   commit: `general` occurrences are **dropped** from the projection (a known
   fact, contributes no symbol), whereas a phase that *could not be computed* is
   retained as an unknown (`?`) symbol. The two are semantically different and
   only the latter can make `run` evaluate to `?`.
3. **`repeat` is strict periodicity; oscillation must cover every period.** A
   single `repeat(action, length=1, times=2)` catches *only* self-loops; the
   legacy `OscillationDetector` also detects two-node (`A-B-A-B`) and multi-node
   (`A-B-C-A-B-C`) periodic cycles. Expressing oscillation as that single
   `repeat` **silently misses real multi-node loops** — a correctness bug, since
   those loops are exactly the harmful ones. The `cycle(c, up_to=K, times=r)`
   derived operator fixes this by covering periods 1..K. Differential testing
   (§7.3) shows the result has **full recall of the legacy detector plus real
   period-3/4 loops the legacy heuristic itself misses**. (The legacy also keeps
   `max_repeats`/rate-limit bookkeeping; that is the *emission* layer, kept
   separate — see `GL_Guard_Binding_Design.md`.)
4. **Thought-episode boundary is part of the definition.** Thought repetition is
   scoped to the current reasoning episode (since the last executable action).
   The model enforces this, so feedback-separated thoughts cannot be conflated.
5. **Three-valued `count`/`run` boundaries** are made precise (the `a`/`b` bands,
   the `|P| < k ⇒ F` case) and unit-tested, rather than left to prose.
6. **`run` is a single-phase dwell, not group-membership.** The legacy
   `DwellTimeRule` counter resets on any *exact* phase change, so `run(F) >= k`
   requires the last `k` occurrences to be the *same* phase in `F` (§4). Without
   this, `dwell_V` over-fires on a mix of `V_regression_test` /
   `V_newly_generated_test`.

### 7.3 Oscillation recall (measured)

Over two SWE-agent trajectory sets, GL-Guard's `cycle`-based `oscillation` fires a
superset of the legacy detector: it matches every legacy oscillation **and**
flags real multi-node loops the legacy misses (e.g. a repeating
`cd → set_env → <command>` period-3 cycle, or a `cd → set_env → python → submit`
period-4 cycle). For a loop-detection *safety* signal, over-approximation toward
catching real loops is the correct bias; `max_per_pattern` emission (keyed by the
loop's node-set) keeps warnings bounded per loop.

---

## 8. Module map

| Module | Responsibility |
|---|---|
| [`kleene.py`](../kleene.py) | Strong-Kleene three-valued logic. |
| [`model.py`](../model.py) | `Occurrence`, `Channel`, `Hook`, and the finite-prefix `World` (`InMemoryWorld` reference). |
| [`ast.py`](../ast.py) | AST node definitions + concrete-syntax pretty printer. |
| [`lexer.py`](../lexer.py) | Regex tokenizer with source positions. |
| [`parser.py`](../parser.py) | Recursive-descent parser; desugars `seen`/`revisit`. |
| [`typecheck.py`](../typecheck.py) | Well-formedness checker (§3). |
| [`interpreter.py`](../interpreter.py) | Three-valued finite-prefix evaluator (§4). |
| [`config.py`](../config.py) | Phase groups + numeric parameters; membership resolution. |
| [`engine.py`](../engine.py) | `GuardProgram`: load → check → evaluate per hook. |
| [`adapters.py`](../adapters.py) | Build the occurrence model from a live Graphectory/Langutory. |
| [`cli.py`](../cli.py) | `check` / `fmt` command-line tool. |
| [`specs/`](../specs/) | The ten signals, the extra signals, and the config. |
| [`tests/`](../tests/) | Lexer/parser, well-formedness, Kleene, interpreter, edge-case, adapter, engine, and CLI tests. |

## 9. Integration seam (no changes to existing LIVEPLAN code required)

```python
from plan_monitor.gl_guard import GuardProgram
from plan_monitor.gl_guard.adapters import TrajectoryModel

program = GuardProgram.load("specs/liveplan.glg", "specs/liveplan.config.json")
model = TrajectoryModel()                      # fed as the monitor commits steps

# at a propose hook:
world = model.world_for_propose(step=i, key=node_key, phase=role, kind=kind)
for name in program.fired(world):              # e.g. ["premature_patching"]
    ...  # hand to the existing refiner (blocking/non-blocking, cool-down, …)
```

GL-Guard computes *verdicts*; the existing refiner decides what to do with a
fired signal. Blocking/non-blocking, advisor cool-down, and rate limiting remain
policy outside the DSL.

## 10. Correctness & compatibility boundary

The target property is agreement between the incremental evaluator and a
reference interpretation over the same normalized prefix, plus the invariant that
rejected proposals never enter the committed `G`/`L`. Neither proves task
correctness or beneficial intervention. The original monitor should be retained
as a compatibility oracle: compare all ten rule decisions, thresholds,
general-phase filtering, thought segmentation, and oscillation counters on
replayable decisions before claiming equivalence.
