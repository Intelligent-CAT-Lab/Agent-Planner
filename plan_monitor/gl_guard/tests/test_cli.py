"""Tests for the gl_guard CLI (parse / check / fmt)."""
from __future__ import annotations

from pathlib import Path

from plan_monitor.gl_guard.cli import main

SPEC_DIR = Path(__file__).resolve().parents[1] / "specs"
CONFIG = str(SPEC_DIR / "liveplan.config.json")


def test_check_ok(capsys):
    rc = main(["check", str(SPEC_DIR / "liveplan.glg"), "--config", CONFIG])
    assert rc == 0
    out = capsys.readouterr().out
    assert "well-formed" in out
    assert "plan_compliance_premature_patch" in out


def test_check_reports_illformed(tmp_path, capsys):
    bad = tmp_path / "bad.glg"
    bad.write_text("signal a on propose when outcome(q) = success")
    rc = main(["check", str(bad)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ill-formed" in err


def test_fmt_roundtrips(capsys):
    rc = main(["fmt", str(SPEC_DIR / "extra_signals.glg")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "signal stale_validation on propose" in out
