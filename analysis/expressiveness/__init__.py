"""Expressiveness study for the GL-Guard (DriftQL) DSL.

Measures how concisely the DSL expresses the drift conditions it was built for,
versus the legacy Python detectors, on the LIVE default profile only.

Public surface:
  * :mod:`analysis.expressiveness.loc` -- lines-of-code comparison (deterministic).
  * :mod:`analysis.expressiveness.behavioral` -- legacy-vs-DSL verdict agreement on
    recorded trajectories (reuses the shadow differential harness).
  * :mod:`analysis.expressiveness.analyze` -- CLI that runs both and writes reports.
"""
from .loc import compute_loc

__all__ = ["compute_loc"]
