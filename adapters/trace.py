"""Structured, scaffold-agnostic record of LivePlan's decisions during a run.

Collects every monitor/refiner intervention (the data the inline agent used to
keep on ``self._planner_history``) and serializes it next to the trajectory as
``{instance_id}.planner.json``. Pure data + JSON — no agent-scaffold types here,
so the same trace format is shared by any scaffold the adapter is wired into.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class InterventionTrace:
    """An append-only log of monitor/refiner interventions for one instance."""

    def __init__(self) -> None:
        self._history: list[dict] = []

    def __bool__(self) -> bool:
        return bool(self._history)

    @property
    def history(self) -> list[dict]:
        return self._history

    def reset(self) -> None:
        """Drop all recorded interventions (called per instance)."""
        self._history = []

    def track(
        self,
        *,
        step_index: int,
        planner_type: str,
        content: str,
        latency_ms: float,
        usage: dict | None = None,
        state_summary: dict | None = None,
    ) -> None:
        """Record one intervention.

        Args:
            step_index: Trajectory length at the moment of the intervention.
            planner_type: ``"monitor"`` or ``"refiner"``.
            content: The message content added to the conversation.
            latency_ms: Time taken, in milliseconds.
            usage: Token usage dict (refiner only: input/output/total tokens, cost).
            state_summary: State summary dict (refiner only).
        """
        intervention: dict[str, Any] = {
            "step": step_index,
            "planner_type": planner_type,
            "content": content,
            "latency_ms": round(latency_ms, 2),
        }
        if usage:
            intervention["usage"] = usage
        if state_summary:
            intervention["state_summary"] = state_summary
        self._history.append(intervention)

    def save(self, output_dir: Path, instance_id: str) -> str | None:
        """Write ``{instance_id}.planner.json`` with a summary + the full log.

        Returns the path written, or ``None`` if there were no interventions.
        """
        if not self._history:
            return None

        output_path = Path(output_dir) / f"{instance_id}.planner.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        monitor_interventions = [x for x in self._history if x["planner_type"] == "monitor"]
        refiner_interventions = [x for x in self._history if x["planner_type"] == "refiner"]

        summary: dict[str, Any] = {
            "total_interventions": len(self._history),
            "monitor_count": len(monitor_interventions),
            "refiner_count": len(refiner_interventions),
            "monitor_total_latency_ms": round(sum(x["latency_ms"] for x in monitor_interventions), 2),
            "refiner_total_latency_ms": round(sum(x["latency_ms"] for x in refiner_interventions), 2),
        }

        if refiner_interventions:
            summary["refiner_total_input_tokens"] = sum(x.get("usage", {}).get("input_tokens", 0) for x in refiner_interventions)
            summary["refiner_total_output_tokens"] = sum(x.get("usage", {}).get("output_tokens", 0) for x in refiner_interventions)
            summary["refiner_total_tokens"] = sum(x.get("usage", {}).get("total_tokens", 0) for x in refiner_interventions)
            summary["refiner_total_cost"] = round(sum(x.get("usage", {}).get("cost", 0.0) for x in refiner_interventions), 6)

        output_data = {"summary": summary, "interventions": self._history}

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        return str(output_path)
