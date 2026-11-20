"""Policy protocol for the bounded Harness loop.

A policy is deliberately narrow: it sees the current subject state, observations
and the list of already completed actions, then proposes one next action. It
cannot execute anything, mutate the transcript, or access the context builder
directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .actions import AgentAction, Observation


@dataclass
class PolicyView:
    action: str
    mode: str
    subject_state: Any
    handoff: dict[str, Any]
    state: dict[str, Any]
    observations: list[Observation]
    completed_actions: list[str]
    context: Any = None
    step: int = 0
    available_actions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        subject = self.subject_state
        return {
            "action": self.action,
            "mode": self.mode,
            "subject_state": subject.as_dict() if hasattr(subject, "as_dict") else subject,
            "handoff": dict(self.handoff),
            "completed_actions": list(self.completed_actions),
            "observation_count": len(self.observations),
            "step": self.step,
            "available_actions": list(self.available_actions),
            "context": self.context.as_dict() if hasattr(self.context, "as_dict") else self.context,
        }


class HarnessPolicy(Protocol):
    def next_action(self, view: PolicyView, state: dict[str, Any]) -> AgentAction | None: ...

    def finalize(self, state: dict[str, Any], execution: Any) -> dict[str, Any] | None: ...
