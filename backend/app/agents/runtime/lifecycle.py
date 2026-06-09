"""Lifecycle tracing for controlled Agent runs.

The runtime is intentionally small: it gives Chat/Interview agents a shared
phase vocabulary without turning the project into a heavy plugin framework.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


CANONICAL_AGENT_PHASES = (
    "BeforeTurn",
    "BeforeReasoning",
    "PromptRender",
    "Reasoner",
    "AfterReasoning",
    "AfterTurn",
)


class AgentPipelineError(ValueError):
    """Raised when an agent phase is unknown or recorded out of order."""


@dataclass
class AgentLifecycleRecorder:

    assistant_type: str
    request_id: str
    agent_run_id: str
    name: str = "chat_agent_pipeline"
    _steps: list[dict[str, Any]] = field(default_factory=list)
    _phase_index: int = 0

    def complete(self, phase: str, **summary: Any) -> None:
        if phase not in CANONICAL_AGENT_PHASES:
            raise AgentPipelineError(f"unknown agent phase: {phase}")
        expected = CANONICAL_AGENT_PHASES[self._phase_index] if self._phase_index < len(CANONICAL_AGENT_PHASES) else None
        if phase != expected:
            raise AgentPipelineError(f"agent phase out of order: expected {expected}, got {phase}")

        self._steps.append(
            {
                "phase": phase,
                "status": "completed",
                "summary": _safe_summary(summary),
                "timestamp_ms": int(time.time() * 1000),
            }
        )
        self._phase_index += 1

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "assistant_type": self.assistant_type,
            "request_id": self.request_id,
            "agent_run_id": self.agent_run_id,
            "phases": [step["phase"] for step in self._steps],
            "steps": list(self._steps),
        }


def _safe_summary(value: Any) -> Any:
    """Keep trace metadata compact and safe for API responses."""
    if isinstance(value, dict):
        return {str(key): _safe_summary(item) for key, item in value.items() if key not in {"raw_prompt", "prompt", "messages"}}
    if isinstance(value, list):
        return [_safe_summary(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:240]
