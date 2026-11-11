"""
analysis/expressiveness -- expressiveness study of the Drift-QL (DriftQL) DSL.

One compact question (per the evaluation design): can the drift conditions the DSL
was built for be expressed in the existing language and runtime, and how much
rule-specific code does that take versus the legacy Python detectors? Scope is the
LIVE default ``liveplan.glg`` profile only -- the twelve signals that have a legacy
counterpart. The shadow ``extra_signals.glg`` candidates and the 50-entry process
taxonomy are out of scope.

Two products, matching the ``signal_selection`` study conventions:

  1. LOC comparison (``loc.py``) + an AST-node program-size cross-check
     (``astsize.py``) -- always computed; pure, deterministic, no I/O beyond reading
     source. The headline conciseness deliverable. (AST size is a formatting-robust
     companion to LOC, NOT a cross-language edit distance and NOT a measure of
     expressive power -- see ``astsize.py``.)
  2. Behavioral agreement (``behavioral.py``) -- opt-in with ``--behavioral``; reuses
     the shadow differential harness to confirm the DSL and legacy detectors agree on
     recorded trajectory prefixes, and to report (not hide) the documented divergences.

Writes ``out/analysis.json`` + ``out/summary.md``.

Usage::

    PY=python   # the 'planner' conda env interpreter (e.g. `conda run -n planner python`)
    # LOC only (instant)
    $PY -m analysis.expressiveness.analyze
    # LOC + behavioral agreement over the in-scope default trajectories
    $PY -m analysis.expressiveness.analyze --behavioral \
        --swe-root SWE-agent --pro-root SWE-bench_Pro-os/SWE-agent --jobs 6
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.expressiveness import astsize, behavioral, loc

REPO = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="analysis.expressiveness.analyze",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--out-dir", type=Path,
                    default=Path(__file__).resolve().parent / "out")
    ap.add_argument("--behavioral", action="store_true",
                    help="also run the legacy-vs-DSL behavioral differential (slower)")
    ap.add_argument("--swe-root", type=Path, default=REPO / "SWE-agent")
    ap.add_argument("--pro-root", type=Path,
                    default=REPO / "SWE-bench_Pro-os" / "SWE-agent")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None,
                    help="cap behavioral replay to the first N in-scope trajectories")
    args = ap.parse_args(argv)

    result = {"loc": loc.compute_loc(), "ast_size": astsize.compute_ast_size()}
    md = [loc.to_markdown(result["loc"]), astsize.to_markdown(result["ast_size"])]

    if args.behavioral:
        result["behavioral"] = behavioral.compute_agreement(
            args.swe_root, args.pro_root, jobs=args.jobs, limit=args.limit)
        md.append(behavioral.to_markdown(result["behavioral"]))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "analysis.json").write_text(json.dumps(result, indent=2))
    (args.out_dir / "summary.md").write_text(
        "# Drift-QL (DriftQL) expressiveness\n\n" + "\n".join(md) + "\n")

    print(f"wrote {args.out_dir/'analysis.json'}")
    print(f"wrote {args.out_dir/'summary.md'}")
    print()
    print("\n".join(md))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
