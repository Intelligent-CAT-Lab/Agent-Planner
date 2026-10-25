"""Lexer / parser tests, including desugaring and round-trip pretty-printing."""
from __future__ import annotations

import pytest

from plan_monitor.gl_guard import ast
from plan_monitor.gl_guard.ast import unparse
from plan_monitor.gl_guard.model import Channel, Hook
from plan_monitor.gl_guard.parser import ParseError, parse_formula, parse_program, parse_rule


def test_parse_simple_rule():
    r = parse_rule("signal premature_patching on propose when phase(q) in Patch and not seen(Localize)")
    assert r.name == "premature_patching"
    assert r.hook is Hook.PROPOSE
    assert isinstance(r.body, ast.And)


def test_hook_variants():
    assert parse_rule("signal a on observe(action) when true").hook is Hook.OBSERVE_ACTION
    assert parse_rule("signal a on observe(thought) when true").hook is Hook.OBSERVE_THOUGHT


def test_seen_desugars_to_exists():
    phi = parse_formula("seen(Patch)")
    assert isinstance(phi, ast.Exists)
    assert phi.channel is Channel.ACTION
    assert isinstance(phi.body, ast.PhaseIn)


def test_revisit_desugars_to_exists_keyeq_q():
    phi = parse_formula("revisit(action)")
    assert isinstance(phi, ast.Exists)
    assert isinstance(phi.body, ast.KeyEq)
    # one side is q
    assert phi.body.v.is_current or phi.body.u.is_current


def test_precedence_not_binds_tighter_than_and():
    phi = parse_formula("not true and false")
    assert isinstance(phi, ast.And)
    assert isinstance(phi.operands[0], ast.Not)


def test_and_binds_tighter_than_or():
    phi = parse_formula("true and false or true")
    assert isinstance(phi, ast.Or)
    assert isinstance(phi.operands[0], ast.And)


def test_exists_body_is_greedy():
    # exists should swallow the whole conjunction to its right.
    phi = parse_formula(
        "kind(q) = submit and exists x in history(action): kind(x) = edit and outcome(x) = success"
    )
    assert isinstance(phi, ast.And)
    # second conjunct is the exists, whose body is itself an And of two atoms
    exists = phi.operands[1]
    assert isinstance(exists, ast.Exists)
    assert isinstance(exists.body, ast.And)
    assert len(exists.body.operands) == 2


def test_count_grammar():
    phi = parse_formula(
        "count { x in history(action) | kind(x) = edit and outcome(x) = failure } >= kappa_fail"
    )
    assert isinstance(phi, ast.Count)
    assert isinstance(phi.k, ast.ParamRef)
    assert phi.k.name == "kappa_fail"


def test_repeat_and_run():
    r = parse_formula("repeat(action, length=2, times=3)")
    assert isinstance(r, ast.Repeat)
    assert r.length.value == 2 and r.times.value == 3
    run = parse_formula("run(Navigate) >= theta_N")
    assert isinstance(run, ast.Run)


def test_se_and_obs_eq():
    se = parse_formula("SE(node(x), node(y))")
    assert isinstance(se, ast.SE)
    oe = parse_formula("obs_eq(x, y)")
    assert isinstance(oe, ast.ObsEq)


def test_inline_group_literal():
    phi = parse_formula("phase(q) in {L_navigate, L_reproduce}")
    assert isinstance(phi.group, ast.GroupSet)
    assert phi.group.labels == frozenset({"L_navigate", "L_reproduce"})


def test_comments_ignored():
    r = parse_rule("# a comment\nsignal a on propose when true # trailing")
    assert r.name == "a"


def test_parse_errors():
    with pytest.raises(ParseError):
        parse_rule("signal a on propose phase(q) in Patch")  # missing 'when'
    with pytest.raises(ParseError):
        parse_formula("run(Patch) > 3")  # only >= allowed


def test_roundtrip_unparse_reparse():
    for text in [
        "phase(q) in Patch and not seen(Localize)",
        "kind(q) = submit and seen(Patch)",
        "run(Validate) >= theta_V",
        "repeat(action, length=1, times=2)",
    ]:
        phi1 = parse_formula(text)
        phi2 = parse_formula(unparse(phi1))
        assert phi1 == phi2


def test_both_spec_files_parse():
    from pathlib import Path
    spec_dir = Path(__file__).resolve().parents[1] / "specs"
    for name in ("liveplan.glg", "extra_signals.glg"):
        rules = parse_program((spec_dir / name).read_text())
        assert rules
