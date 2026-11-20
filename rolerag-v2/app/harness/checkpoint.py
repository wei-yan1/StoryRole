"""Durable, compact checkpoint for a single Harness turn.

A checkpoint must be enough to answer: which actions already completed, what
the subject state was, what budget was consumed, and where to resume. It must
not become a second transcript or store full retrieval payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import SubjectState, now_iso


@dataclass
class TurnCheckpoint:
    turn_id: str
    scope_key: str
    mode: str
    status: str = "running"
    step: int = 0
    completed_actions: list[str] = field(default_factory=list)
    action_history: list[dict[str, Any]] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    subject_state: dict[str, Any] = field(default_factory=dict)
    artifacts_digest: dict[str, Any] = field(default_factory=dict)
    stop_reason: str = ""
    updated_at: str = ""
    version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "scope_key": self.scope_key,
            "mode": self.mode,
            "status": self.status,
            "step": int(self.step),
            "completed_actions": list(self.completed_actions),
            "action_history": list(self.action_history),
            "budget_snapshot": dict(self.budget_snapshot),
            "subject_state": dict(self.subject_state),
            "artifacts_digest": dict(self.artifacts_digest),
            "stop_reason": self.stop_reason,
            "updated_at": self.updated_at or now_iso(),
            "version": int(self.version),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TurnCheckpoint | None":
        if not isinstance(payload, dict) or not payload.get("turn_id"):
            return None
        return cls(
            turn_id=str(payload.get("turn_id")),
            scope_key=str(payload.get("scope_key") or ""),
            mode=str(payload.get("mode") or "quick"),
            status=str(payload.get("status") or "running"),
            step=int(payload.get("step") or 0),
            completed_actions=[str(item) for item in (payload.get("completed_actions") or [])],
            action_history=list(payload.get("action_history") or []),
            budget_snapshot=dict(payload.get("budget_snapshot") or {}),
            subject_state=dict(payload.get("subject_state") or {}),
            artifacts_digest=dict(payload.get("artifacts_digest") or {}),
            stop_reason=str(payload.get("stop_reason") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            version=int(payload.get("version") or 1),
        )

    def subject(self) -> SubjectState:
        return SubjectState.from_dict(self.subject_state)

    def completed(self, action: str) -> bool:
        return action in self.completed_actions

    def mark(
        self,
        *,
        action: str,
        status: str,
        reason: str = "",
        step: int | None = None,
        budget: dict[str, Any] | None = None,
        subject_state: dict[str, Any] | None = None,
        artifacts_digest: dict[str, Any] | None = None,
    ) -> None:
        if action not in self.completed_actions and status in {"ok", "degraded"}:
            self.completed_actions.append(action)
        self.action_history.append({
            "action": action,
            "status": status,
            "reason": reason,
            "at": now_iso(),
        })
        if step is not None:
            self.step = int(step)
        if budget is not None:
            self.budget_snapshot = dict(budget)
        if subject_state is not None:
            self.subject_state = dict(subject_state)
        if artifacts_digest is not None:
            self.artifacts_digest = dict(artifacts_digest)
        self.status = "completed" if action == "learn" else self.status
        self.updated_at = now_iso()
