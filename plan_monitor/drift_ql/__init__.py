"""
Drift-QL: a lightweight domain-specific language for specifying LIVEPLAN's
process-monitoring signals formally.

Drift-QL is a *specification layer*. It does not replace the Graphectory /
Langutory representations or the online intervention hook; it expresses the
diagnostic conditions those representations support as declarative rules with a
precise three-valued, finite-prefix semantics. See ``docs/DESIGN.md`` for the
full formal treatment and ``docs/Drift_QL_Design.docx`` for the original design.

Typical use::

    from plan_monitor.drift_ql import DriftProgram, Config
    from plan_monitor.drift_ql.adapters import TrajectoryModel

    program = DriftProgram.load("specs/liveplan.glg", "specs/liveplan.config.json")

    model = TrajectoryModel()
    # ... monitor commits actions/thoughts into `model` as the agent runs ...
    world = model.world_for_propose(step=42, key=node_key, phase="P", kind="edit")
    fired = program.fired(world)   # -> e.g. ["premature_patching"]
"""
from __future__ import annotations

from . import ast, model
from .advice import AdviceRegistry, SignalReport
from .config import Config, ConfigError
from .emission import EmissionPolicy, EmissionState
from .engine import DriftProgram, Verdict
from .interpreter import evaluate
from .kleene import Kleene
from .model import Channel, Hook, InMemoryWorld, Occurrence, World
from .parser import parse_formula, parse_program, parse_rule
from .runtime import DriftRuntime
from .typecheck import WellFormednessError, check_program, check_rule

__all__ = [
    # language
    "DriftProgram",
    "Verdict",
    "Config",
    "ConfigError",
    "Kleene",
    "Channel",
    "Hook",
    "Occurrence",
    "World",
    "InMemoryWorld",
    "evaluate",
    "parse_program",
    "parse_rule",
    "parse_formula",
    "check_program",
    "check_rule",
    "WellFormednessError",
    # binding / emission / advice layer
    "DriftRuntime",
    "AdviceRegistry",
    "SignalReport",
    "EmissionPolicy",
    "EmissionState",
    "ast",
    "model",
]
