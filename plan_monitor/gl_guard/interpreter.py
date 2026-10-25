"""
Three-valued finite-prefix evaluator for GL-Guard (design section 5).

Given a well-formed rule and a :class:`~plan_monitor.gl_guard.model.World`
(the pair ``(H, q)`` at one hook firing), :func:`evaluate` returns a
:class:`~plan_monitor.gl_guard.kleene.Kleene` verdict. The rule *fires* iff the
verdict is ``TRUE``; ``UNKNOWN`` means the representations lack a field the rule
needs and the monitor should abstain rather than guess.

Key semantic commitments, each mapped to the design:

  * ``history(c)`` excludes ``q`` (model guarantee), so a rule can never count the
    current occurrence as its own predecessor.
  * ``exists``: ``T`` if any instance is ``T``; ``F`` if all are ``F`` (including an
    empty history); ``?`` otherwise.
  * ``count {..} >= k``: with ``a`` definitely-true and ``b`` unknown instances,
    ``T`` if ``a >= k``; ``F`` if ``a + b < k``; ``?`` otherwise.
  * Boolean connectives use strong Kleene logic.
  * ``run(F) >= k``: over the phase projection ``P`` of the tentative ``H·q``,
    ``T`` iff ``|P| >= k`` and the last ``k`` retained symbols all lie in ``F``
    (counting occurrences, not compressed runs). Unknown phase symbols yield ``?``.
  * ``repeat(c, length=m, times=r)``: over the identity stream ``s = s_1..s_n`` of
    ``H·q`` (action keys, or the current thought episode), ``T`` iff ``n >= m*r``
    and ``s[n-j] == s[n-m-j]`` for every ``0 <= j < m*(r-1)``. Unknown identities
    that could change the verdict yield ``?``.
"""
from __future__ import annotations

from typing import Dict, Optional

from . import ast
from .config import Config
from .kleene import Kleene, F, T, U, from_bool, k_and, k_not, k_or
from .model import Channel, Occurrence, World


class EvalError(RuntimeError):
    pass


class _Evaluator:
    def __init__(self, world: World, config: Config):
        self.world = world
        self.config = config

    # -- term resolution ---------------------------------------------------------

    def _resolve(self, var: ast.Var, env: Dict[str, Occurrence]) -> Occurrence:
        if var.is_current:
            return self.world.q
        try:
            return env[var.name]
        except KeyError as exc:  # pragma: no cover - guarded by typecheck
            raise EvalError(f"unbound variable {var.name!r} at evaluation time") from exc

    # -- dispatch ----------------------------------------------------------------

    def eval(self, node: ast.Formula, env: Dict[str, Occurrence]) -> Kleene:
        method = self._DISPATCH.get(type(node))
        if method is None:  # pragma: no cover - guarded by typecheck
            raise EvalError(f"cannot evaluate node of type {type(node).__name__}")
        return method(self, node, env)

    # -- connectives -------------------------------------------------------------

    def _eval_const(self, node: ast.Const, env) -> Kleene:
        return T if node.value else F

    def _eval_not(self, node: ast.Not, env) -> Kleene:
        return k_not(self.eval(node.operand, env))

    def _eval_and(self, node: ast.And, env) -> Kleene:
        return k_and(*(self.eval(op, env) for op in node.operands))

    def _eval_or(self, node: ast.Or, env) -> Kleene:
        return k_or(*(self.eval(op, env) for op in node.operands))

    # -- quantifiers -------------------------------------------------------------

    def _eval_exists(self, node: ast.Exists, env) -> Kleene:
        saw_unknown = False
        for occ in self.world.history(node.channel):
            sub = self.eval(node.body, {**env, node.var: occ})
            if sub is T:
                return T
            if sub is U:
                saw_unknown = True
        # Empty history or all-false both yield F unless an unknown intervened.
        return U if saw_unknown else F

    def _eval_count(self, node: ast.Count, env) -> Kleene:
        k = self.config.resolve_int(node.k)
        a = 0  # definitely-true instances
        b = 0  # unknown instances
        for occ in self.world.history(node.channel):
            sub = self.eval(node.body, {**env, node.var: occ})
            if sub is T:
                a += 1
            elif sub is U:
                b += 1
        if a >= k:
            return T
        if a + b < k:
            return F
        return U

    # -- phase run ---------------------------------------------------------------

    def _eval_run(self, node: ast.Run, env) -> Kleene:
        k = self.config.resolve_int(node.k)
        projection = list(self.world.phase_projection())
        if len(projection) < k:
            return F
        tail = projection[-k:]
        memberships = [self._phase_member(sym, node.group) for sym in tail]
        return k_and(*memberships)

    def _phase_member(self, sym: Optional[str], group: ast.Group) -> Kleene:
        if sym is None:
            # An unavailable phase symbol: membership could be either way.
            return U
        return from_bool(self.config.phase_in_group(sym, group))

    # -- repetition --------------------------------------------------------------

    def _eval_repeat(self, node: ast.Repeat, env) -> Kleene:
        m = self.config.resolve_int(node.length)
        r = self.config.resolve_int(node.times)
        s = list(self.world.repetition_stream(node.channel))
        n = len(s)
        if n < m * r:
            return F
        # Require s[n-j] == s[n-m-j] for 0 <= j < m*(r-1).  (1-indexed in the
        # design; here s is 0-indexed, so position (n-j) maps to index n-1-j.)
        saw_unknown = False
        for j in range(m * (r - 1)):
            a = s[n - 1 - j]
            b = s[n - 1 - m - j]
            if a is None or b is None:
                saw_unknown = True
                continue
            if a != b:
                return F
        return U if saw_unknown else T

    # -- atoms -------------------------------------------------------------------

    def _eval_key_eq(self, node: ast.KeyEq, env) -> Kleene:
        u = self._resolve(node.u, env)
        v = self._resolve(node.v, env)
        if u.key is None or v.key is None:
            return U
        return from_bool(u.key == v.key)

    def _eval_kind_eq(self, node: ast.KindEq, env) -> Kleene:
        u = self._resolve(node.u, env)
        if u.kind is None:
            return U
        return from_bool(u.kind == node.kind)

    def _eval_phase_in(self, node: ast.PhaseIn, env) -> Kleene:
        u = self._resolve(node.u, env)
        if not u.phase_available:
            return U
        return from_bool(self.config.phase_in_group(u.phase, node.group))

    def _eval_before(self, node: ast.Before, env) -> Kleene:
        u = self._resolve(node.u, env)
        v = self._resolve(node.v, env)
        return from_bool(u.oid < v.oid)

    def _eval_outcome_eq(self, node: ast.OutcomeEq, env) -> Kleene:
        u = self._resolve(node.u, env)
        if u.outcome is None:
            return U
        return from_bool(u.outcome == node.outcome)

    def _eval_se(self, node: ast.SE, env) -> Kleene:
        u = self._resolve(node.u, env)
        v = self._resolve(node.v, env)
        return self.world.se(u, v)

    def _eval_obs_eq(self, node: ast.ObsEq, env) -> Kleene:
        u = self._resolve(node.u, env)
        v = self._resolve(node.v, env)
        return self.world.obs_eq(u, v)

    _DISPATCH = {
        ast.Const: _eval_const,
        ast.Not: _eval_not,
        ast.And: _eval_and,
        ast.Or: _eval_or,
        ast.Exists: _eval_exists,
        ast.Count: _eval_count,
        ast.Run: _eval_run,
        ast.Repeat: _eval_repeat,
        ast.KeyEq: _eval_key_eq,
        ast.KindEq: _eval_kind_eq,
        ast.PhaseIn: _eval_phase_in,
        ast.Before: _eval_before,
        ast.OutcomeEq: _eval_outcome_eq,
        ast.SE: _eval_se,
        ast.ObsEq: _eval_obs_eq,
    }


def evaluate(rule: ast.Rule, world: World, config: Config) -> Kleene:
    """
    Evaluate ``rule`` against ``world``.

    The world's hook must match the rule's hook (a rule is only evaluated at the
    firing it was declared for). Returns the Kleene verdict for the rule body.
    """
    if world.hook is not rule.hook:
        raise EvalError(
            f"rule {rule.name!r} declared on {rule.hook.value} but world is at "
            f"{world.hook.value}"
        )
    return _Evaluator(world, config).eval(rule.body, {})
