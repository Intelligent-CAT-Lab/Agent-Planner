"""
Abstract syntax for the GL-Guard DSL.

The AST mirrors the grammar of section 3 of the design document:

    rule  ::= signal ID on hook when phi
    hook  ::= propose | observe(action) | observe(thought)
    phi   ::= true | false | atom | not phi | (phi and phi) | (phi or phi)
            | exists x in history(c) : phi
            | count { x in history(c) | phi } >= k
            | run(F) >= k
            | repeat(c, length=m, times=r)
    atom  ::= key(u)=key(v) | kind(u)=K | phase(u) in F
            | before(u,v) | outcome(u)=R | SE(node(u),node(v)) | obs_eq(u,v)

The core language is kept minimal; the derived operators ``seen(F)`` and
``revisit(c)`` are *surface sugar* that the parser desugars into core nodes
(see :mod:`plan_monitor.gl_guard.parser`), so the interpreter and well-formedness
checker only ever see the core forms.

Every node carries enough structure to be pretty-printed back to concrete
syntax via :func:`unparse`, which the tests use as a round-trip oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, List, Tuple, Union

from .model import Channel, Hook

# --------------------------------------------------------------------------- #
# Value expressions: integer parameters and phase groups.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IntLit:
    """A literal positive integer, e.g. the ``2`` in ``times=2``."""

    value: int


@dataclass(frozen=True)
class ParamRef:
    """A named integer parameter resolved from configuration, e.g. ``theta_N``."""

    name: str


IntExpr = Union[IntLit, ParamRef]


@dataclass(frozen=True)
class GroupRef:
    """A named phase group resolved from configuration, e.g. ``Patch``."""

    name: str


@dataclass(frozen=True)
class GroupSet:
    """An inline phase group literal, e.g. ``{L_navigate, L_reproduce}``."""

    labels: FrozenSet[str]


Group = Union[GroupRef, GroupSet]


@dataclass(frozen=True)
class Var:
    """An occurrence term: the current occurrence ``q`` or a bound variable."""

    name: str

    @property
    def is_current(self) -> bool:
        return self.name == "q"


# --------------------------------------------------------------------------- #
# Atoms.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class KeyEq:
    """``key(u) = key(v)`` — same node/action identity."""

    u: Var
    v: Var


@dataclass(frozen=True)
class KindEq:
    """``kind(u) = K`` — the action kind of ``u`` is literal ``K``."""

    u: Var
    kind: str


@dataclass(frozen=True)
class PhaseIn:
    """``phase(u) in F`` — the Langutory phase of ``u`` lies in group ``F``."""

    u: Var
    group: Group


@dataclass(frozen=True)
class Before:
    """``before(u, v)`` — strict chronological order."""

    u: Var
    v: Var


@dataclass(frozen=True)
class OutcomeEq:
    """``outcome(u) = R`` — the execution outcome of ``u`` is ``R``."""

    u: Var
    outcome: str


@dataclass(frozen=True)
class SE:
    """``SE(node(u), node(v))`` — directed structural edge in the Graphectory."""

    u: Var
    v: Var


@dataclass(frozen=True)
class ObsEq:
    """``obs_eq(u, v)`` — observational equivalence of recorded outputs."""

    u: Var
    v: Var


Atom = Union[KeyEq, KindEq, PhaseIn, Before, OutcomeEq, SE, ObsEq]


# --------------------------------------------------------------------------- #
# Formulas.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Const:
    value: bool  # true / false


@dataclass(frozen=True)
class Not:
    operand: "Formula"


@dataclass(frozen=True)
class And:
    operands: Tuple["Formula", ...]


@dataclass(frozen=True)
class Or:
    operands: Tuple["Formula", ...]


@dataclass(frozen=True)
class Exists:
    """``exists x in history(c) : phi``."""

    var: str
    channel: Channel
    body: "Formula"


@dataclass(frozen=True)
class Count:
    """``count { x in history(c) | phi } >= k``."""

    var: str
    channel: Channel
    body: "Formula"
    k: IntExpr


@dataclass(frozen=True)
class Run:
    """``run(F) >= k`` — the last ``k`` retained phase symbols all lie in ``F``."""

    group: Group
    k: IntExpr


@dataclass(frozen=True)
class Repeat:
    """``repeat(c, length=m, times=r)`` — a strict periodic motif at the tail."""

    channel: Channel
    length: IntExpr
    times: IntExpr


Formula = Union[
    Const, Not, And, Or, Exists, Count, Run, Repeat, Atom
]


@dataclass(frozen=True)
class Rule:
    """A complete ``signal ID on hook when phi`` specification."""

    name: str
    hook: Hook
    body: Formula


# --------------------------------------------------------------------------- #
# Pretty-printer (concrete syntax round-trip).
# --------------------------------------------------------------------------- #


def _int(e: IntExpr) -> str:
    return str(e.value) if isinstance(e, IntLit) else e.name


def _group(g: Group) -> str:
    if isinstance(g, GroupRef):
        return g.name
    return "{" + ", ".join(sorted(g.labels)) + "}"


def unparse(node) -> str:
    """Render an AST node back to concrete GL-Guard syntax."""
    if isinstance(node, Rule):
        return f"signal {node.name} on {node.hook.value} when\n  {unparse(node.body)}"

    if isinstance(node, Const):
        return "true" if node.value else "false"
    if isinstance(node, Not):
        return f"not {_paren(node.operand)}"
    if isinstance(node, And):
        return " and ".join(_paren(o) for o in node.operands)
    if isinstance(node, Or):
        return " or ".join(_paren(o) for o in node.operands)
    if isinstance(node, Exists):
        return f"exists {node.var} in history({node.channel.value}) : {unparse(node.body)}"
    if isinstance(node, Count):
        return (
            f"count {{ {node.var} in history({node.channel.value}) | "
            f"{unparse(node.body)} }} >= {_int(node.k)}"
        )
    if isinstance(node, Run):
        return f"run({_group(node.group)}) >= {_int(node.k)}"
    if isinstance(node, Repeat):
        return (
            f"repeat({node.channel.value}, length={_int(node.length)}, "
            f"times={_int(node.times)})"
        )

    if isinstance(node, KeyEq):
        return f"key({node.u.name}) = key({node.v.name})"
    if isinstance(node, KindEq):
        return f"kind({node.u.name}) = {node.kind}"
    if isinstance(node, PhaseIn):
        return f"phase({node.u.name}) in {_group(node.group)}"
    if isinstance(node, Before):
        return f"before({node.u.name}, {node.v.name})"
    if isinstance(node, OutcomeEq):
        return f"outcome({node.u.name}) = {node.outcome}"
    if isinstance(node, SE):
        return f"SE(node({node.u.name}), node({node.v.name}))"
    if isinstance(node, ObsEq):
        return f"obs_eq({node.u.name}, {node.v.name})"

    raise TypeError(f"cannot unparse node of type {type(node).__name__}")


_ATOMS = (KeyEq, KindEq, PhaseIn, Before, OutcomeEq, SE, ObsEq)
_LEAVES = _ATOMS + (Const, Run, Repeat, Count)


def _paren(node) -> str:
    """Parenthesize a sub-formula when needed for unambiguous re-parsing."""
    if isinstance(node, _LEAVES) or isinstance(node, (Not, Exists)):
        return unparse(node)
    return f"({unparse(node)})"
