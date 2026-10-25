"""
Static well-formedness checking for GL-Guard (design section 2).

Well-formedness is what makes the three-valued semantics *sound*: it guarantees
every term is bound to an occurrence of a definite channel, that channel-typed
predicates are only applied where they make sense, and that no rule inspects a
field the hook cannot yet provide. The checker runs once at load time and reports
*all* violations for a rule at once.

Rules enforced:

  (W1) Only ``q`` may be free; every other variable must be bound by ``exists``
       or ``count``. No shadowing of an in-scope name (keeps binding unambiguous).
  (W2) ``kind``, ``phase``, ``outcome`` and ``SE`` require *action* occurrences;
       applying them to a thought term is ill-typed.
  (W3) ``key(u) = key(v)`` requires ``u`` and ``v`` to share a channel.
  (W4) At ``propose``, ``q`` has no execution outcome and no observation yet:
       ``outcome(q)`` and any ``obs_eq`` mentioning ``q`` are invalid.
  (W5) ``run(F)`` requires an action hook (``propose`` or ``observe(action)``).
  (W6) ``repeat(c, ...)`` requires ``c`` to equal the hook's channel.
  (W7) Literal integer arguments are positive; ``times`` (``r``) is >= 2; named
       parameters are checked against the config when one is supplied.
  (W8) ``kind`` / ``outcome`` literals and group / parameter references resolve
       against the config when one is supplied.

A variable's *channel* is that of its binder (``history(c)``); ``q``'s channel is
the hook's channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import ast
from .config import Config
from .model import Channel, Hook


class WellFormednessError(Exception):
    def __init__(self, rule_name: str, errors: List[str]):
        self.rule_name = rule_name
        self.errors = errors
        detail = "\n  - ".join(errors)
        super().__init__(f"signal {rule_name!r} is ill-formed:\n  - {detail}")


@dataclass
class _Scope:
    """Maps an in-scope variable name to the channel of its binder."""

    bindings: Dict[str, Channel]

    def extend(self, name: str, channel: Channel) -> "_Scope":
        return _Scope({**self.bindings, name: channel})

    def channel_of(self, name: str) -> Optional[Channel]:
        return self.bindings.get(name)


class _Checker:
    def __init__(self, rule: ast.Rule, config: Optional[Config]):
        self.rule = rule
        self.config = config
        self.hook = rule.hook
        self.errors: List[str] = []

    # -- helpers -----------------------------------------------------------------

    def _err(self, msg: str):
        self.errors.append(msg)

    def _channel_of(self, var: ast.Var, scope: _Scope) -> Optional[Channel]:
        if var.is_current:
            return self.hook.channel
        ch = scope.channel_of(var.name)
        if ch is None:
            self._err(f"unbound variable {var.name!r} (only 'q' may be free)")
        return ch

    def _require_action(self, var: ast.Var, scope: _Scope, pred: str):
        ch = self._channel_of(var, scope)
        if ch is not None and ch is not Channel.ACTION:
            self._err(f"{pred}({var.name}) requires an action occurrence, "
                      f"but {var.name!r} is a thought")

    def _mentions_q(self, var: ast.Var) -> bool:
        return var.is_current

    # -- traversal ---------------------------------------------------------------

    def check(self) -> List[str]:
        self._check_formula(self.rule.body, _Scope({}))
        return self.errors

    def _check_formula(self, node: ast.Formula, scope: _Scope):
        if isinstance(node, ast.Const):
            return
        if isinstance(node, ast.Not):
            self._check_formula(node.operand, scope)
            return
        if isinstance(node, ast.And) or isinstance(node, ast.Or):
            for op in node.operands:
                self._check_formula(op, scope)
            return
        if isinstance(node, ast.Exists):
            self._check_binder(node.var, node.channel, node.body, scope)
            return
        if isinstance(node, ast.Count):
            self._check_int(node.k, name="k", minimum=1)
            self._check_binder(node.var, node.channel, node.body, scope)
            return
        if isinstance(node, ast.Run):
            self._check_run(node)
            return
        if isinstance(node, ast.Repeat):
            self._check_repeat(node)
            return
        # atoms
        self._check_atom(node, scope)

    def _check_binder(self, var: str, channel: Channel, body: ast.Formula, scope: _Scope):
        if var == "q":
            self._err("cannot bind a variable named 'q' (reserved for the current occurrence)")
        elif scope.channel_of(var) is not None:
            self._err(f"variable {var!r} shadows an enclosing binding")
        self._check_formula(body, scope.extend(var, channel))

    def _check_run(self, node: ast.Run):
        if self.hook is Hook.OBSERVE_THOUGHT:
            self._err("run(F) requires an action hook (propose or observe(action))")
        self._check_group(node.group)
        self._check_int(node.k, name="k", minimum=1)

    def _check_repeat(self, node: ast.Repeat):
        if node.channel is not self.hook.channel:
            self._err(f"repeat({node.channel.value}, ...) requires channel to match "
                      f"the hook channel ({self.hook.channel.value})")
        self._check_int(node.length, name="length", minimum=1)
        self._check_int(node.times, name="times", minimum=2)

    def _check_atom(self, node: ast.Atom, scope: _Scope):
        if isinstance(node, ast.KeyEq):
            cu = self._channel_of(node.u, scope)
            cv = self._channel_of(node.v, scope)
            if cu is not None and cv is not None and cu is not cv:
                self._err("key(u) = key(v) requires u and v on the same channel "
                          f"(got {cu.value} and {cv.value})")
            return
        if isinstance(node, ast.KindEq):
            self._require_action(node.u, scope, "kind")
            self._check_kind_literal(node.kind)
            return
        if isinstance(node, ast.PhaseIn):
            self._require_action(node.u, scope, "phase")
            self._check_group(node.group)
            return
        if isinstance(node, ast.OutcomeEq):
            self._require_action(node.u, scope, "outcome")
            self._check_outcome_literal(node.outcome)
            if self.hook.is_propose and self._mentions_q(node.u):
                self._err("outcome(q) is invalid at propose (q has no outcome yet)")
            return
        if isinstance(node, ast.SE):
            self._require_action(node.u, scope, "SE")
            self._require_action(node.v, scope, "SE")
            return
        if isinstance(node, ast.ObsEq):
            self._channel_of(node.u, scope)  # binding check
            self._channel_of(node.v, scope)
            if self.hook.is_propose and (self._mentions_q(node.u) or self._mentions_q(node.v)):
                self._err("obs_eq(..) involving q is invalid at propose "
                          "(q has no observation yet)")
            return
        if isinstance(node, ast.Before):
            self._channel_of(node.u, scope)
            self._channel_of(node.v, scope)
            return
        raise TypeError(f"unknown atom {type(node).__name__}")

    # -- literal / reference resolution -----------------------------------------

    def _check_int(self, e: ast.IntExpr, name: str, minimum: int):
        if isinstance(e, ast.IntLit):
            if e.value < minimum:
                self._err(f"{name} must be >= {minimum}, got {e.value}")
            return
        # ParamRef: validated against config if one is present; value bound >= minimum.
        if self.config is not None:
            if e.name not in self.config.params:
                self._err(f"unknown parameter {e.name!r}")
            elif self.config.params[e.name] < minimum:
                self._err(f"parameter {e.name!r} = {self.config.params[e.name]} "
                          f"violates {name} >= {minimum}")

    def _check_group(self, g: ast.Group):
        if self.config is None:
            return
        if isinstance(g, ast.GroupRef) and g.name not in self.config.phase_groups:
            self._err(f"unknown phase group {g.name!r}")

    def _check_kind_literal(self, kind: str):
        if self.config is not None and self.config.kinds and kind not in self.config.kinds:
            self._err(f"unknown action kind {kind!r} "
                      f"(declared kinds: {sorted(self.config.kinds)})")

    def _check_outcome_literal(self, outcome: str):
        if outcome not in (self.config.outcomes if self.config else {"success", "failure"}):
            self._err(f"unknown outcome {outcome!r} (expected 'success' or 'failure')")


def check_rule(rule: ast.Rule, config: Optional[Config] = None) -> None:
    """Raise :class:`WellFormednessError` if ``rule`` violates any constraint."""
    errors = _Checker(rule, config).check()
    if errors:
        raise WellFormednessError(rule.name, errors)


def check_program(rules, config: Optional[Config] = None) -> None:
    """Check every rule; raises on the first ill-formed one."""
    for rule in rules:
        check_rule(rule, config)
