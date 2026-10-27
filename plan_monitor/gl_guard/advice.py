"""
Advice registry: configure *what happens* when a signal fires, independently of
the ``.glg`` file that says *when* it fires.

A `.glg` specification is pure detection logic. Everything operational — the
human-readable advice message, the firing/emission policy, the priority used to
order simultaneous matches, and whether the signal blocks execution — lives in a
separate, versioned JSON registry. This mirrors the split the legacy system
already has (conditions in `rules.py`, messages/thresholds in
`default_rules.json`) and lets the baseline messages be reused verbatim.

Registry entry (one per signal id):

    {
      "enabled": true,                 # shadow-first: disabled signals still
                                       #   evaluate for differential logging but
                                       #   never reach the agent
      "priority": 0,                   # OPTIONAL (default 0). Only reorders
                                       #   signals that fire at the SAME hook;
                                       #   with the default, co-firing signals
                                       #   keep spec declaration order (which
                                       #   matches the legacy evaluation order).
                                       #   It never affects whether a signal fires.
      "key": "signal",                 # emission key: signal | q.key | q.phase | motif
      "emit": {"mode": "every_n", "period": 7},
      "intervention": {"block_execution": false},
      "advice": {
        "template": "You have dwelled in {phase} for {threshold} steps. ...",
        "variants": {"max_repeats": "If you cannot progress, stop or submit."}
      }
    }

Message templates may reference only **whitelisted** variables drawn from typed
signal metadata (``{phase}``, ``{threshold}``, ``{action}``, ``{command}``,
``{step}``). Any tool-derived value (``{action}``, ``{command}``) is escaped and
truncated before substitution. Placeholders are validated at load time; a missing
template or policy for an *enabled* signal is a configuration error, never silent
empty guidance.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .emission import EmissionPolicy

# Variables a template is allowed to reference. Each maps to a typed source the
# runtime fills from the hook context; nothing else may appear in a template.
#   action / command  -- the current (revisited) action
#   actions           -- the distinct members of a detected loop, in loop order
#   steps             -- the step range the loop spans
ALLOWED_TEMPLATE_VARS = frozenset(
    {"phase", "threshold", "action", "command", "step", "actions", "steps"}
)
# Variables whose value originates from tool output and must be sanitized.
_TOOL_DERIVED_VARS = frozenset({"action", "command", "actions"})
_MAX_TOOL_VALUE_LEN = 200
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class AdviceConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SignalReport:
    """A fired, rendered signal — shaped to map cleanly onto a legacy ``RuleMatch``."""

    rule_id: str
    message: str
    block_execution: bool
    step_index: int
    priority: int
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_rule_match_kwargs(self) -> dict:
        """Kwargs for constructing a legacy ``RuleMatch`` at the integration seam."""
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "block_execution": self.block_execution,
            "metadata": self.metadata,
            "step_index": self.step_index,
        }


@dataclass
class AdviceEntry:
    signal_id: str
    enabled: bool
    priority: int
    key: str
    policy: EmissionPolicy
    block_execution: bool
    template: str
    variants: Dict[str, str] = field(default_factory=dict)
    # Emission state records what the agent has already been told. A block prevents
    # the action but does not un-tell the agent, so a blocking signal's emission
    # (its threshold/escalation counter) must survive the rollback: plan_compliance
    # so a violation is reported at most once, oscillation so its bounded run of
    # warnings reaches the terminal "stop or submit" instead of resetting on every
    # block and blocking a stuck agent forever. Every current blocking signal sets
    # this; a future signal that wants its emission undone on block omits it.
    persist_on_block: bool = False

    def render(self, variant: Optional[str], variables: Dict[str, object]) -> str:
        template = self.template if variant is None else self.variants.get(variant, self.template)
        return _render(template, variables)


def _sanitize(name: str, value: object) -> str:
    text = str(value)
    if name in _TOOL_DERIVED_VARS:
        text = " ".join(text.split())  # collapse whitespace / newlines
        if len(text) > _MAX_TOOL_VALUE_LEN:
            text = text[:_MAX_TOOL_VALUE_LEN] + "…"
    return text


def _validate_template(signal_id: str, template: str) -> None:
    for var in _PLACEHOLDER_RE.findall(template):
        if var not in ALLOWED_TEMPLATE_VARS:
            raise AdviceConfigError(
                f"signal {signal_id!r}: template uses unknown variable {{{var}}}; "
                f"allowed: {sorted(ALLOWED_TEMPLATE_VARS)}"
            )


def _render(template: str, variables: Dict[str, object]) -> str:
    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name in variables:
            return _sanitize(name, variables[name])
        return m.group(0)  # leave unknown placeholder intact (validated at load)

    return _PLACEHOLDER_RE.sub(repl, template)


class AdviceRegistry:
    def __init__(self, entries: Dict[str, AdviceEntry]):
        self.entries = entries

    @classmethod
    def from_dict(cls, data: dict) -> "AdviceRegistry":
        signals = data.get("signals", {})
        entries: Dict[str, AdviceEntry] = {}
        for sid, raw in signals.items():
            advice = raw.get("advice", {})
            template = advice.get("template")
            enabled = bool(raw.get("enabled", False))
            if enabled and not template:
                raise AdviceConfigError(f"enabled signal {sid!r} has no advice template")
            if template:
                _validate_template(sid, template)
            variants = advice.get("variants", {})
            for vname, vtemplate in variants.items():
                _validate_template(sid, vtemplate)
            entries[sid] = AdviceEntry(
                signal_id=sid,
                enabled=enabled,
                priority=int(raw.get("priority", 0)),
                key=raw.get("key", "signal"),
                policy=EmissionPolicy.from_config(raw.get("emit", {"mode": "always"})),
                block_execution=bool(raw.get("intervention", {}).get("block_execution", False)),
                persist_on_block=bool(raw.get("intervention", {}).get("persist_on_block", False)),
                template=template or "",
                variants=variants,
            )
        return cls(entries)

    @classmethod
    def load(cls, path) -> "AdviceRegistry":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def get(self, signal_id: str) -> Optional[AdviceEntry]:
        return self.entries.get(signal_id)
