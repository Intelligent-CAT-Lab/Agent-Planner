"""
GL-Guard program: load, check, and evaluate a specification.

A :class:`GuardProgram` is a loaded ``.glg`` specification bound to a
:class:`~plan_monitor.gl_guard.config.Config`. At construction it parses every
rule and runs the well-formedness checker, so an ill-formed specification fails
*fast and loudly* at load time rather than silently misbehaving online.

At each hook firing the monitor builds a :class:`~plan_monitor.gl_guard.model.World`
for the proposed/observed occurrence and calls :meth:`GuardProgram.evaluate`,
which returns the verdicts of exactly the rules declared on that hook. This is
the single integration seam with LIVEPLAN: the DSL is a *specification layer*
that computes verdicts; the existing refiner decides what to do with a fired
signal (blocking vs. non-blocking, advisor cool-down, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import ast
from .config import Config
from .interpreter import evaluate
from .kleene import Kleene
from .model import Hook, World
from .parser import parse_program
from .typecheck import check_program


@dataclass(frozen=True)
class Verdict:
    """The outcome of evaluating one rule at one hook firing."""

    rule: str
    value: Kleene

    @property
    def fired(self) -> bool:
        return self.value is Kleene.TRUE

    @property
    def unknown(self) -> bool:
        return self.value is Kleene.UNKNOWN


class GuardProgram:
    def __init__(self, rules: List[ast.Rule], config: Config, *, check: bool = True):
        if check:
            check_program(rules, config)
        self.rules: List[ast.Rule] = list(rules)
        self.config = config
        self._by_hook: Dict[Hook, List[ast.Rule]] = {}
        for rule in self.rules:
            self._by_hook.setdefault(rule.hook, []).append(rule)

    # -- loading -----------------------------------------------------------------

    @classmethod
    def from_source(cls, source: str, config: Config, *, check: bool = True) -> "GuardProgram":
        return cls(parse_program(source), config, check=check)

    @classmethod
    def load(cls, spec_path, config_path, *, check: bool = True) -> "GuardProgram":
        source = Path(spec_path).read_text()
        config = Config.load(config_path)
        return cls.from_source(source, config, check=check)

    # -- rule access -------------------------------------------------------------

    def rules_for(self, hook: Hook) -> List[ast.Rule]:
        return self._by_hook.get(hook, [])

    def rule(self, name: str) -> ast.Rule:
        for r in self.rules:
            if r.name == name:
                return r
        raise KeyError(name)

    # -- evaluation --------------------------------------------------------------

    def evaluate(self, world: World) -> List[Verdict]:
        """Evaluate every rule declared on ``world.hook`` and return their verdicts."""
        return [
            Verdict(rule=r.name, value=evaluate(r, world, self.config))
            for r in self.rules_for(world.hook)
        ]

    def fired(self, world: World) -> List[str]:
        """Names of the rules that fire (verdict TRUE) at ``world``."""
        return [v.rule for v in self.evaluate(world) if v.fired]
