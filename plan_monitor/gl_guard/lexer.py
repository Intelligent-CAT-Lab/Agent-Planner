"""
Tokenizer for the GL-Guard DSL.

A small, regex-driven scanner. It is deliberately hand-written (rather than
pulling in a parser-generator dependency) because the language is tiny and we
want precise source positions for well-formedness diagnostics. Comments begin
with ``#`` and run to end of line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# Multi-character punctuation must be matched before single-character tokens.
_TOKEN_SPEC = [
    ("WS", r"[ \t\r\n]+"),
    ("COMMENT", r"\#[^\n]*"),
    ("GE", r">="),
    ("GT", r">"),
    ("INT", r"\d+"),
    ("ID", r"[A-Za-z_][A-Za-z0-9_]*"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("PIPE", r"\|"),
    ("EQ", r"="),
]

_MASTER_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in _TOKEN_SPEC))

# Reserved words become their own token kinds (upper-cased) so the parser can
# branch on them without string comparisons sprinkled everywhere.
_KEYWORDS = {
    "signal", "on", "when",
    "propose", "observe", "action", "thought",
    "true", "false",
    "not", "and", "or",
    "exists", "in", "history",
    "count", "run", "repeat", "cycle",
    # NOTE: ``length``, ``times`` and ``up_to`` are *contextual* keywords (only
    # meaningful inside repeat(...)/cycle(...)); they stay generic IDs so they
    # never collide elsewhere.
    "key", "kind", "phase", "before", "outcome", "obs_eq", "node",
    # SE is case-sensitive and matched explicitly below.
    "seen", "revisit",  # derived-operator sugar
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.kind}({self.value!r})@{self.line}:{self.col}"


class LexError(SyntaxError):
    pass


def tokenize(text: str) -> List[Token]:
    """Scan ``text`` into a list of tokens terminated by an ``EOF`` token."""
    tokens: List[Token] = []
    pos = 0
    line = 1
    line_start = 0
    n = len(text)

    while pos < n:
        m = _MASTER_RE.match(text, pos)
        if not m:
            col = pos - line_start + 1
            raise LexError(f"unexpected character {text[pos]!r} at line {line}, col {col}")
        kind = m.lastgroup
        value = m.group()
        col = pos - line_start + 1

        # Track newlines inside whitespace/comments for accurate positions.
        newlines = value.count("\n")
        if newlines:
            line += newlines
            line_start = m.start() + value.rfind("\n") + 1

        pos = m.end()

        if kind in ("WS", "COMMENT"):
            continue

        if kind == "ID":
            if value == "SE":
                kind = "SE"
            elif value in _KEYWORDS:
                kind = value.upper()
            # otherwise it stays a generic ID (variable / param / group / literal)

        tokens.append(Token(kind, value, m.start(), line, col))

    tokens.append(Token("EOF", "", n, line, pos - line_start + 1))
    return tokens
