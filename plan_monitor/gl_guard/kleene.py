"""
Three-valued (strong Kleene) logic for GL-Guard.

GL-Guard evaluates process conditions over a *finite committed prefix* of an
agent trajectory. A predicate may be definitely true (T), definitely false (F),
or *unknown* (?) when a well-typed field is unavailable (e.g. an observation was
not recorded, or an outcome has not been computed). Boolean connectives follow
the strong Kleene truth tables, which are the unique monotone extension of
classical logic that treats ? as "could be either T or F".

    not:   not T = F,  not F = T,  not ? = ?

    and:   F dominates   (F and _ = F);   else ? if any ?;   else T
    or:    T dominates   (T or  _ = T);   else ? if any ?;   else F

This module is deliberately tiny and dependency-free; it is the semantic core
that the interpreter builds on.
"""
from __future__ import annotations

from enum import Enum


class Kleene(Enum):
    """A three-valued truth value."""

    TRUE = "T"
    FALSE = "F"
    UNKNOWN = "?"

    def __bool__(self) -> bool:  # pragma: no cover - defensive
        # Forbid accidental coercion: `if value:` would silently treat ? as T.
        raise TypeError(
            "Kleene values must not be coerced to bool; compare explicitly "
            "against Kleene.TRUE / Kleene.FALSE / Kleene.UNKNOWN."
        )

    def __str__(self) -> str:
        return self.value


# Short aliases used throughout the interpreter.
T = Kleene.TRUE
F = Kleene.FALSE
U = Kleene.UNKNOWN


def from_bool(b: bool) -> Kleene:
    """Lift a definite Python bool into Kleene."""
    return T if b else F


def k_not(a: Kleene) -> Kleene:
    if a is U:
        return U
    return F if a is T else T


def k_and(*values: Kleene) -> Kleene:
    """Strong-Kleene conjunction over any number of operands (n-ary, short-circuit)."""
    saw_unknown = False
    for v in values:
        if v is F:
            return F
        if v is U:
            saw_unknown = True
    return U if saw_unknown else T


def k_or(*values: Kleene) -> Kleene:
    """Strong-Kleene disjunction over any number of operands (n-ary, short-circuit)."""
    saw_unknown = False
    for v in values:
        if v is T:
            return T
        if v is U:
            saw_unknown = True
    return U if saw_unknown else F
