# GL-Guard

A lightweight domain-specific language that expresses LIVEPLAN's
process-monitoring signals as a formal **specification layer** over the existing
Graphectory and Langutory representations.

Today those signals are hand-written heuristics in
[`plan_monitor/rules.py`](../rules.py). GL-Guard lets them be stated declaratively
with a precise three-valued, finite-prefix semantics — so they can be read,
checked, and (eventually) validated against the legacy monitor.

> **The existing LIVEPLAN implementation is untouched.** GL-Guard is additive and
> self-contained (pure standard library). It computes signal *verdicts*; the
> existing refiner still decides what to do with them.

## Example

```glg
# "editing before any localization has happened"
signal premature_patching on propose when
  phase(q) in Patch and not seen(Localize)

# "the same edit identity has already failed kappa_fail times"
signal repeated_failed_edit on propose when
  kind(q) = edit and
  count { x in history(action) |
    kind(x) = edit and key(x) = key(q) and outcome(x) = failure } >= kappa_fail
```

## Usage

```python
from plan_monitor.gl_guard import GuardProgram
from plan_monitor.gl_guard.adapters import TrajectoryModel

program = GuardProgram.load("specs/liveplan.glg", "specs/liveplan.config.json")

model = TrajectoryModel()                       # fed by the monitor as it runs
world = model.world_for_propose(step=42, key=node_key, phase="P", kind="edit")
print(program.fired(world))                     # -> ["premature_patching"]
```

CLI (authoring / CI linting):

```bash
python -m plan_monitor.gl_guard.cli check specs/liveplan.glg --config specs/liveplan.config.json
python -m plan_monitor.gl_guard.cli fmt   specs/extra_signals.glg
```

## Layout

- `docs/DESIGN.md` — the authoritative formal design (grammar, semantics,
  well-formedness, critical review of the original overview).
- `docs/GL_Guard_Binding_Design.md` — how GL-Guard binds to the live monitor
  (hooks, the two time-scales, emission policies, advice registry, and the
  measured equivalence results).
- `docs/GL_Guard_Design.docx` — the original design overview.
- `specs/` — the ten LIVEPLAN signals, the representative extra signals, and the
  configuration (thresholds + phase groups + advice registry).
- `kleene.py`, `model.py`, `ast.py`, `lexer.py`, `parser.py`, `typecheck.py`,
  `interpreter.py`, `config.py`, `engine.py`, `cli.py` — the language pipeline.
- `emission.py`, `advice.py`, `runtime.py` — detection → fire-timing → message.
- `adapters.py` — build the `World` from a live `GraphBuilder` graph.
- `guard_monitor.py` — `GuardMonitor`, the drop-in `StatefulPhaseMonitor` the agent
  uses when `monitor_engine: gl_guard` (the default). See the binding design §2.1.
- `shadow.py` — the shadow differential harness (see below).
- `tests/` — parser, well-formedness, Kleene, interpreter, edge-case, adapter,
  model, engine, CLI, emission, runtime, and shadow tests.

## Adding a signal

A signal is **three decoupled pieces** — detection, fire-timing + message, and
thresholds — so adding one is adding *data*, not code. No per-rule Python, no
agent change.

**1. Detection** — add the condition to a `.glg` spec (`specs/liveplan.glg`, or a
new spec file). Express *what is true*, memorylessly, over the vocabulary
(`phase`/`kind`/`key`/`seen`/`count`/`before`/`run`/`cycle`/`revisit`/…). The
signal name becomes its id:

```glg
# "re-editing a location that already failed too many times"
signal thrashing_edit on propose when
  kind(q) = edit and
  count { x in history(action) | key(x) = key(q) and outcome(x) = failure } >= kappa_fail
```

**2. Thresholds** — put every number in `specs/liveplan.config.json`, never in the
spec (e.g. `kappa_fail`). Annotate it with a `_`-prefixed comment key explaining
*why that value* (the loader ignores `_`-keys). Phase groups and kinds live here too.

**3. Message + fire-timing** — add one entry to `specs/liveplan.advice.json` keyed
by the signal name:

```json
"thrashing_edit": {
  "enabled": true,                         // false = shadow-only (evaluated for the
                                           //   differential harness, never shown to the agent)
  "key": "q.key",                          // emission scope: signal | q.key | q.phase | motif
  "emit": {"mode": "once_per_key"},        // once_per_key | every_n | on_rising_edge | cooldown | max_per_pattern | always
  "intervention": {"block_execution": false},   // true vetoes the action; add "persist_on_block": true to keep counts across a block
  "advice": {"template": "You have edited {command} several times and it keeps failing. The fix location is likely wrong: re-read the issue and the surrounding code to relocate the bug before editing again."}
}
```

**Writing the message** — mirror the existing templates; they are what the LLM
actually acts on, so clarity decides whether the intervention helps:

- **Name the pattern concretely**, grounded in the step (e.g. "You have dwelled in
  {phase} for {threshold} steps").
- **Give specific, actionable next steps that move toward a *successful* outcome**
  — often 2–3 numbered options, not a bare "stop". Good messages offer a way
  *forward* (localize first, write a reproduction, validate, submit), not just a
  prohibition.
- **Be concise and imperative.** One short paragraph.
- **Use only the whitelisted variables** `{phase} {threshold} {action} {command}
  {step}` — any tool-derived value (`{action}`/`{command}`) is auto-escaped and
  truncated; an unknown placeholder fails validation at load.
- Blocking signals should additionally tell the agent what to do *instead*, since
  their action was just vetoed.

**4. Validate.** `enabled: false` keeps a new rule shadow-only — it is evaluated by
the differential harness (so you can measure its firing and overlap on real
trajectories) but never reaches the agent. Promote to `enabled: true` only after
checking it on the default trajectories. Then run:

```bash
python -m pytest plan_monitor/gl_guard/tests/ -q
python -m plan_monitor.gl_guard.shadow SWE-agent/trajectories/default/swebench/<model> --agent swe-agent
```

At runtime each fired signal becomes a `SignalReport` → legacy `RuleMatch` inside
the unchanged `MonitorResult`, so it flows through the existing refiner /
blocking / cool-down path automatically.

> Note: `outcome(x)` and `obs_eq(x, y)` are empty at the live `propose` hook (the
> action has not executed), so signals that depend on them (see
> `specs/extra_signals.glg`) fire only in offline analysis, not online. Online
> signals use structure only: `phase` / `kind` / `key` / `seen` / `count` / `run`.

## Shadow differential testing

Replay real trajectories and diff GL-Guard against the legacy monitor at every
step (the dwell categories are exactly equivalent; other categories report
documented differences):

```bash
python -m plan_monitor.gl_guard.shadow <traj-file-or-dir> --agent swe-agent
```

## Tests

```bash
python -m pytest plan_monitor/gl_guard/tests/ -q
```
