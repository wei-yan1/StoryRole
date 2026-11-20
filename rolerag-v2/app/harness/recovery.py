"""Explicit recovery decisions for failed Harness actions.

Recovery is not an invisible `except: await model()` retry. Every decision is
recorded on the Observation and in the trace, with one of four outcomes:
retry, degrade, replan, or stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .actions import ActionSpec, Observation


@dataclass
class RecoveryDecision:
    action: str  # retry | degrade | replan | stop
    reason: str
    max_attempts: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reason": self.reason, "max_attempts": self.max_attempts}


class RecoveryPolicy(Protocol):
    def decide(
        self, action: Any, spec: ActionSpec, observation: Observation, attempt: int,
    ) -> RecoveryDecision | None: ...


class DefaultRecoveryPolicy:
    """Conservative default: retry only idempotent tool timeouts once."""

    def decide(
        self, action: Any, spec: ActionSpec, observation: Observation, attempt: int,
    ) -> RecoveryDecision | None:
        if observation.status == "denied":
            return RecoveryDecision("replan", observation.error or "action_denied")
        if observation.status == "timeout":
            if spec.category == "tool" and spec.idempotent and attempt < 1:
                return RecoveryDecision("retry", "tool_timeout_retry", max_attempts=1)
            return RecoveryDecision("degrade", "timeout_degraded")
        if observation.status == "error":
            if spec.critical:
                return RecoveryDecision("stop", f"critical_action_failed:{action.name}")
            if spec.category == "tool" and spec.idempotent and attempt < 1:
                return RecoveryDecision("retry", "tool_error_retry", max_attempts=1)
            return RecoveryDecision("degrade", f"action_degraded:{action.name}")
        return None
