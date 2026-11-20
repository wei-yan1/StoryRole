"""Turn trace for the bounded agent harness.

The trace is intentionally smaller than a full observability backend: it records
the facts needed to replay why a turn chose an action, what context it saw, what
the tool returned, and where the budget went. It never stores the full prompt or
hidden model reasoning by default.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .types import now_iso


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


@dataclass
class TraceEvent:
    kind: str
    at_ms: float
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "at_ms": round(float(self.at_ms), 2),
            "payload": dict(self.payload),
        }


@dataclass
class HarnessTrace:
    turn_id: str
    scope_key: str = ""
    started_at: float = field(default_factory=time.perf_counter)
    events: list[TraceEvent] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)

    def record(self, kind: str, **payload: Any) -> TraceEvent:
        event = TraceEvent(
            kind=kind,
            at_ms=(time.perf_counter() - self.started_at) * 1000,
            payload={key: value for key, value in payload.items() if value is not None},
        )
        self.events.append(event)
        return event

    def action(self, name: str, **payload: Any) -> None:
        self.record("action", action=name, **payload)

    def observation(self, action: str, status: str, **payload: Any) -> None:
        self.record("observation", action=action, status=status, **payload)

    def stop(self, stop_reason: str, **payload: Any) -> None:
        payload.setdefault("stop_reason", stop_reason)
        self.record("stop", **payload)

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "scope_key": self.scope_key,
            "created_at": self.created_at,
            "events": [event.as_dict() for event in self.events],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        actions = [
            str(event.payload.get("action") or "")
            for event in self.events
            if event.kind == "action" and event.payload.get("action")
        ]
        statuses: dict[str, int] = {}
        for event in self.events:
            if event.kind != "observation":
                continue
            status = str(event.payload.get("status") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "event_count": len(self.events),
            "actions": actions,
            "observation_statuses": statuses,
        }

    def render(self, *, limit: int = 20) -> str:
        lines: list[str] = []
        for event in self.events[-limit:]:
            payload = event.payload
            action = _clip(payload.get("action") or payload.get("reason") or "", 80)
            status = _clip(payload.get("status") or payload.get("kind") or "", 40)
            lines.append(f"{event.at_ms:8.1f}ms {event.kind:12s} {action} {status}".rstrip())
        return "\n".join(lines)
