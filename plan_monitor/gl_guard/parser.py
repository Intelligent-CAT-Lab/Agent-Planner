"""
Recursive-descent parser for the GL-Guard DSL.

Grammar (section 3), with the standard precedence  not > and > or  and optional
parentheses for grouping. A quantifier body is *greedy*: it extends as far to
the right as possible (the usual binder convention), which is why

    phi1 and exists x in history(action): phi2 and phi3

parses as ``phi1 and (exists x: (phi2 and phi3))`` — matching every example in
the design document.

The derived operators ``seen(F)`` and ``revisit(c)`` are desugared here into the
core language, so downstream stages (well-formedness, interpreter) only deal with
core AST nodes:

    seen(F)      ==>  exists _s in history(action) : phase(_s) in F
    revisit(c)   ==>  exists _r in history(c)      : key(_r) = key(q)

Fresh, non-colliding variable names are generated for the desugared binders.
"""
from __future__ import annotations

from typing import List, Optional

from . import ast
from .lexer import Token, tokenize
from .model import Channel, Hook


class ParseError(SyntaxError):
    pass


class Parser:
    def __init__(self, tokens: List[Token], source: str = ""):
        self._toks = tokens
        self._i = 0
        self._source = source
        self._gensym = 0

    # -- token helpers -----------------------------------------------------------

    @property
    def _cur(self) -> Token:
        return self._toks[self._i]

    def _at(self, kind: str) -> bool:
        return self._cur.kind == kind

    def _advance(self) -> Token:
        tok = self._toks[self._i]
        self._i += 1
        return tok

    def _expect(self, kind: str) -> Token:
        if not self._at(kind):
            self._error(f"expected {kind}, found {self._cur.kind} ({self._cur.value!r})")
        return self._advance()

    def _error(self, msg: str):
        t = self._cur
        raise ParseError(f"line {t.line}, col {t.col}: {msg}")

    def _fresh(self, stem: str) -> str:
        self._gensym += 1
        return f"__{stem}{self._gensym}"

    # -- entry points ------------------------------------------------------------

    def parse_program(self) -> List[ast.Rule]:
        rules: List[ast.Rule] = []
        while not self._at("EOF"):
            rules.append(self.parse_rule())
        return rules

    def parse_rule(self) -> ast.Rule:
        self._expect("SIGNAL")
        name = self._expect("ID").value
        self._expect("ON")
        hook = self._parse_hook()
        self._expect("WHEN")
        body = self._parse_formula()
        return ast.Rule(name=name, hook=hook, body=body)

    def _parse_hook(self) -> Hook:
        if self._at("PROPOSE"):
            self._advance()
            return Hook.PROPOSE
        if self._at("OBSERVE"):
            self._advance()
            self._expect("LPAREN")
            chan = self._parse_channel()
            self._expect("RPAREN")
            return Hook.OBSERVE_ACTION if chan is Channel.ACTION else Hook.OBSERVE_THOUGHT
        self._error("expected a hook: 'propose' or 'observe(...)'")

    def _parse_channel(self) -> Channel:
        if self._at("ACTION"):
            self._advance()
            return Channel.ACTION
        if self._at("THOUGHT"):
            self._advance()
            return Channel.THOUGHT
        self._error("expected channel 'action' or 'thought'")

    # -- formulas (precedence: or < and < unary) ---------------------------------

    def _parse_formula(self) -> ast.Formula:
        return self._parse_or()

    def _parse_or(self) -> ast.Formula:
        first = self._parse_and()
        operands = [first]
        while self._at("OR"):
            self._advance()
            operands.append(self._parse_and())
        if len(operands) == 1:
            return first
        return ast.Or(tuple(operands))

    def _parse_and(self) -> ast.Formula:
        first = self._parse_unary()
        operands = [first]
        while self._at("AND"):
            self._advance()
            operands.append(self._parse_unary())
        if len(operands) == 1:
            return first
        return ast.And(tuple(operands))

    def _parse_unary(self) -> ast.Formula:
        if self._at("NOT"):
            self._advance()
            return ast.Not(self._parse_unary())
        if self._at("EXISTS"):
            return self._parse_exists()
        return self._parse_primary()

    def _parse_exists(self) -> ast.Formula:
        self._expect("EXISTS")
        var = self._expect("ID").value
        self._expect("IN")
        self._expect("HISTORY")
        self._expect("LPAREN")
        chan = self._parse_channel()
        self._expect("RPAREN")
        self._expect("COLON")
        # Greedy body: a full (lowest-precedence) formula.
        body = self._parse_or()
        return ast.Exists(var=var, channel=chan, body=body)

    def _parse_primary(self) -> ast.Formula:
        t = self._cur

        if t.kind == "TRUE":
            self._advance()
            return ast.Const(True)
        if t.kind == "FALSE":
            self._advance()
            return ast.Const(False)
        if t.kind == "LPAREN":
            self._advance()
            inner = self._parse_or()
            self._expect("RPAREN")
            return inner
        if t.kind == "COUNT":
            return self._parse_count()
        if t.kind == "RUN":
            return self._parse_run()
        if t.kind == "REPEAT":
            return self._parse_repeat()
        if t.kind == "CYCLE":
            return self._parse_cycle()

        # atoms and derived sugar
        if t.kind == "KEY":
            return self._parse_key_eq()
        if t.kind == "KIND":
            return self._parse_kind_eq()
        if t.kind == "PHASE":
            return self._parse_phase_in()
        if t.kind == "BEFORE":
            return self._parse_before()
        if t.kind == "OUTCOME":
            return self._parse_outcome_eq()
        if t.kind == "SE":
            return self._parse_se()
        if t.kind == "OBS_EQ":
            return self._parse_obs_eq()
        if t.kind == "SEEN":
            return self._parse_seen()
        if t.kind == "REVISIT":
            return self._parse_revisit()

        self._error(f"unexpected token {t.kind} ({t.value!r}) at start of formula")

    # -- quantitative constructs -------------------------------------------------

    def _parse_count(self) -> ast.Count:
        self._expect("COUNT")
        self._expect("LBRACE")
        var = self._expect("ID").value
        self._expect("IN")
        self._expect("HISTORY")
        self._expect("LPAREN")
        chan = self._parse_channel()
        self._expect("RPAREN")
        self._expect("PIPE")
        body = self._parse_or()
        self._expect("RBRACE")
        self._expect("GE")
        k = self._parse_int()
        return ast.Count(var=var, channel=chan, body=body, k=k)

    def _parse_run(self) -> ast.Run:
        self._expect("RUN")
        self._expect("LPAREN")
        group = self._parse_group()
        self._expect("RPAREN")
        self._expect("GE")
        k = self._parse_int()
        return ast.Run(group=group, k=k)

    def _parse_repeat(self) -> ast.Repeat:
        self._expect("REPEAT")
        self._expect("LPAREN")
        chan = self._parse_channel()
        self._expect("COMMA")
        self._expect_id_value("length")
        self._expect("EQ")
        length = self._parse_int()
        self._expect("COMMA")
        self._expect_id_value("times")
        self._expect("EQ")
        times = self._parse_int()
        self._expect("RPAREN")
        return ast.Repeat(channel=chan, length=length, times=times)

    def _parse_cycle(self) -> ast.Formula:
        # cycle(c, up_to=K, times=r)  ==  OR over m in 1..K of repeat(c, length=m, times=r)
        # It captures "stuck in a loop of any period up to K" (self-loop AA at m=1,
        # ABAB at m=2, ABCABC at m=3, ...). up_to must be a literal so the
        # disjunction can be expanded at parse time.
        self._expect("CYCLE")
        self._expect("LPAREN")
        chan = self._parse_channel()
        self._expect("COMMA")
        self._expect_id_value("up_to")
        self._expect("EQ")
        if not self._at("INT"):
            self._error("cycle's up_to must be an integer literal")
        up_to = int(self._advance().value)
        if up_to < 1:
            self._error("cycle's up_to must be >= 1")
        self._expect("COMMA")
        self._expect_id_value("times")
        self._expect("EQ")
        times = self._parse_int()
        self._expect("RPAREN")

        disjuncts = tuple(
            ast.Repeat(channel=chan, length=ast.IntLit(m), times=times)
            for m in range(1, up_to + 1)
        )
        return disjuncts[0] if len(disjuncts) == 1 else ast.Or(disjuncts)

    def _expect_id_value(self, expected: str):
        # ``length`` and ``times`` are contextual keywords matched by value.
        if self._at("ID") and self._cur.value == expected:
            self._advance()
            return
        self._error(f"expected '{expected}', found {self._cur.kind} ({self._cur.value!r})")

    # -- atoms -------------------------------------------------------------------

    def _parse_fn_term(self, keyword: str) -> ast.Var:
        """Parse ``keyword ( term )`` and return the term."""
        self._expect(keyword)
        self._expect("LPAREN")
        var = self._parse_term()
        self._expect("RPAREN")
        return var

    def _parse_key_eq(self) -> ast.KeyEq:
        u = self._parse_fn_term("KEY")
        self._expect("EQ")
        v = self._parse_fn_term("KEY")
        return ast.KeyEq(u=u, v=v)

    def _parse_kind_eq(self) -> ast.KindEq:
        u = self._parse_fn_term("KIND")
        self._expect("EQ")
        kind = self._parse_literal_name()
        return ast.KindEq(u=u, kind=kind)

    def _parse_phase_in(self) -> ast.PhaseIn:
        u = self._parse_fn_term("PHASE")
        self._expect("IN")
        group = self._parse_group()
        return ast.PhaseIn(u=u, group=group)

    def _parse_before(self) -> ast.Before:
        self._expect("BEFORE")
        self._expect("LPAREN")
        u = self._parse_term()
        self._expect("COMMA")
        v = self._parse_term()
        self._expect("RPAREN")
        return ast.Before(u=u, v=v)

    def _parse_outcome_eq(self) -> ast.OutcomeEq:
        u = self._parse_fn_term("OUTCOME")
        self._expect("EQ")
        outcome = self._parse_literal_name()
        return ast.OutcomeEq(u=u, outcome=outcome)

    def _parse_se(self) -> ast.SE:
        self._expect("SE")
        self._expect("LPAREN")
        self._expect("NODE")
        self._expect("LPAREN")
        u = self._parse_term()
        self._expect("RPAREN")
        self._expect("COMMA")
        self._expect("NODE")
        self._expect("LPAREN")
        v = self._parse_term()
        self._expect("RPAREN")
        self._expect("RPAREN")
        return ast.SE(u=u, v=v)

    def _parse_obs_eq(self) -> ast.ObsEq:
        self._expect("OBS_EQ")
        self._expect("LPAREN")
        u = self._parse_term()
        self._expect("COMMA")
        v = self._parse_term()
        self._expect("RPAREN")
        return ast.ObsEq(u=u, v=v)

    # -- derived-operator sugar --------------------------------------------------

    def _parse_seen(self) -> ast.Exists:
        # seen(F) == exists _s in history(action): phase(_s) in F
        self._expect("SEEN")
        self._expect("LPAREN")
        group = self._parse_group()
        self._expect("RPAREN")
        v = self._fresh("s")
        return ast.Exists(
            var=v,
            channel=Channel.ACTION,
            body=ast.PhaseIn(u=ast.Var(v), group=group),
        )

    def _parse_revisit(self) -> ast.Exists:
        # revisit(c) == exists _r in history(c): key(_r) = key(q)
        self._expect("REVISIT")
        self._expect("LPAREN")
        chan = self._parse_channel()
        self._expect("RPAREN")
        v = self._fresh("r")
        return ast.Exists(
            var=v,
            channel=chan,
            body=ast.KeyEq(u=ast.Var(v), v=ast.Var("q")),
        )

    # -- leaves ------------------------------------------------------------------

    def _parse_term(self) -> ast.Var:
        name = self._expect("ID").value
        return ast.Var(name)

    def _parse_literal_name(self) -> str:
        # A bare identifier used as a literal (kind K, outcome R).
        return self._expect("ID").value

    def _parse_int(self) -> ast.IntExpr:
        if self._at("INT"):
            return ast.IntLit(int(self._advance().value))
        if self._at("ID"):
            return ast.ParamRef(self._advance().value)
        self._error("expected an integer literal or a named parameter")

    def _parse_group(self) -> ast.Group:
        if self._at("LBRACE"):
            self._advance()
            labels = [self._expect("ID").value]
            while self._at("COMMA"):
                self._advance()
                labels.append(self._expect("ID").value)
            self._expect("RBRACE")
            return ast.GroupSet(frozenset(labels))
        name = self._expect("ID").value
        return ast.GroupRef(name)


# --------------------------------------------------------------------------- #
# Convenience functions.
# --------------------------------------------------------------------------- #


def parse_program(text: str) -> List[ast.Rule]:
    """Parse a full ``.glg`` specification (zero or more rules)."""
    return Parser(tokenize(text), source=text).parse_program()


def parse_rule(text: str) -> ast.Rule:
    """Parse exactly one rule."""
    parser = Parser(tokenize(text), source=text)
    rule = parser.parse_rule()
    if not parser._at("EOF"):
        parser._error("trailing tokens after rule")
    return rule


def parse_formula(text: str, hook: Optional[Hook] = None) -> ast.Formula:
    """Parse a bare formula (used by tests)."""
    parser = Parser(tokenize(text), source=text)
    phi = parser._parse_formula()
    if not parser._at("EOF"):
        parser._error("trailing tokens after formula")
    return phi
