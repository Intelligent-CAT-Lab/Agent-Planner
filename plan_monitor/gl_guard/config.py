"""
Configuration binding for GL-Guard.

The DSL is intentionally *parameterised*: thresholds (``theta_N``, ``kappa_fail``,
motif lengths...) and phase groups (``Patch``, ``Validate``...) are configuration,
not language constants (design section 6). A :class:`Config` resolves the named
references that appear in a specification to concrete values at evaluation time.

A phase group is a set of symbols that may contain either canonical Langutory
labels (``L_navigate``) or coarse prefixes (``L``, ``P``, ``V``). Membership of a
phase ``p`` in a group ``F`` holds iff ``p``'s label is listed, or ``p``'s prefix
(the part before the first underscore, per :class:`plan_monitor.phases.Phase`) is
listed. This keeps groups robust to fine-grained phase labels such as
``V_regression_test`` without enumerating every variant.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Optional

from . import ast

# Canonical outcome literals; GL-Guard does not invent new ones.
OUTCOMES: FrozenSet[str] = frozenset({"success", "failure"})


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    phase_groups: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    params: Dict[str, int] = field(default_factory=dict)
    kinds: FrozenSet[str] = frozenset()
    outcomes: FrozenSet[str] = OUTCOMES

    # -- loading -----------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        groups = {
            name: frozenset(labels)
            for name, labels in data.get("phase_groups", {}).items()
        }
        params = {name: int(v) for name, v in data.get("params", {}).items()}
        kinds = frozenset(data.get("kinds", []))
        outcomes = frozenset(data.get("outcomes", OUTCOMES))
        return cls(phase_groups=groups, params=params, kinds=kinds, outcomes=outcomes)

    @classmethod
    def load(cls, path) -> "Config":
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))

    # -- resolution --------------------------------------------------------------

    def resolve_int(self, e: ast.IntExpr) -> int:
        if isinstance(e, ast.IntLit):
            return e.value
        if e.name not in self.params:
            raise ConfigError(f"unknown parameter {e.name!r}")
        return self.params[e.name]

    def resolve_group(self, g: ast.Group) -> FrozenSet[str]:
        if isinstance(g, ast.GroupSet):
            return g.labels
        if g.name not in self.phase_groups:
            raise ConfigError(f"unknown phase group {g.name!r}")
        return self.phase_groups[g.name]

    def phase_in_group(self, phase_label: Optional[str], g: ast.Group) -> bool:
        """
        Definite membership test for a *known* phase label.

        Returns ``False`` for ``None`` (a "general"/unclassified phase belongs to
        no named group). Matches on exact label or on the single-letter prefix.
        """
        if phase_label is None:
            return False
        members = self.resolve_group(g)
        if phase_label in members:
            return True
        prefix = phase_label.split("_", 1)[0]
        return prefix in members
