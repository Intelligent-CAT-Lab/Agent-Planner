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
- `docs/GL_Guard_Design.docx` — the original design overview.
- `specs/` — the ten LIVEPLAN signals, the representative extra signals, and the
  configuration (thresholds + phase groups).
- `kleene.py`, `model.py`, `ast.py`, `lexer.py`, `parser.py`, `typecheck.py`,
  `interpreter.py`, `config.py`, `engine.py`, `adapters.py`, `cli.py` — the
  language pipeline (see the module map in `docs/DESIGN.md`).
- `tests/` — parser, well-formedness, Kleene, interpreter, edge-case, adapter,
  model, engine, and CLI tests.

## Tests

```bash
python -m pytest plan_monitor/gl_guard/tests/ -q
```
