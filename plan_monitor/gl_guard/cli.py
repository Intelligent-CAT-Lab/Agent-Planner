"""
A tiny command-line front-end for GL-Guard: parse, well-formedness-check, and
pretty-print a specification. Useful for authoring and for CI linting of ``.glg``
files.

    python -m plan_monitor.gl_guard.cli check specs/liveplan.glg --config specs/liveplan.config.json
    python -m plan_monitor.gl_guard.cli fmt   specs/liveplan.glg
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ast import unparse
from .config import Config
from .parser import parse_program
from .typecheck import WellFormednessError, check_program


def _load(spec: str):
    return parse_program(Path(spec).read_text())


def cmd_check(args) -> int:
    rules = _load(args.spec)
    config = Config.load(args.config) if args.config else None
    try:
        check_program(rules, config)
    except WellFormednessError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"ok: {len(rules)} rule(s) parsed and well-formed")
    for r in rules:
        print(f"  - {r.name} on {r.hook.value}")
    return 0


def cmd_fmt(args) -> int:
    rules = _load(args.spec)
    for r in rules:
        print(unparse(r))
        print()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gl_guard", description="GL-Guard DSL tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="parse and well-formedness-check a spec")
    p_check.add_argument("spec")
    p_check.add_argument("--config", default=None)
    p_check.set_defaults(func=cmd_check)

    p_fmt = sub.add_parser("fmt", help="parse and pretty-print a spec")
    p_fmt.add_argument("spec")
    p_fmt.set_defaults(func=cmd_fmt)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
