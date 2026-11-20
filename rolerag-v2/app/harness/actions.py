"""Action protocol and registry for one bounded Harness turn.

The registry is intentionally small: an action declares what it needs, which
context sections it may see, whether it is terminal, and how many times it may
run. The runtime owns the loop; policy owns only the choice of the next action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol


@dataclass(frozen=True)
class ActionSpec:
    name: str
    purpose: str
    requires: tuple[str, ...] = ()
    category: str = "state"  # state | model | tool | control
    max_per_turn: int | None = 1
    context_sections: tuple[str, ...] = ()
    terminal: bool = False
    critical: bool = False
    idempotent: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "requires": list(self.requires),
            "category": self.category,
            "max_per_turn": self.max_per_turn,
            "context_sections": list(self.context_sections),
            "terminal": self.terminal,
            "critical": self.critical,
            "idempotent": self.idempotent,
        }


@dataclass
class AgentAction:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": dict(self.args), "reason": self.reason}

    def fingerprint(self) -> str:
        return json.dumps(
            {"name": self.name, "args": self.args},
            ensure_ascii=False, sort_keys=True, default=str,
        )


@dataclass
class Observation:
    action: str
    status: str = "ok"  # ok | denied | timeout | degraded | error
    data: Any = None
    error: str = ""
    provenance: list[str] = field(default_factory=list)
    budget_delta: dict[str, Any] = field(default_factory=dict)
    state_patch: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    recovery: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "degraded"}

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "provenance": list(self.provenance),
            "budget_delta": dict(self.budget_delta),
            "state_patch": dict(self.state_patch),
            "artifacts": dict(self.artifacts),
            "recovery": dict(self.recovery or {}),
        }


ActionHandler = Callable[[AgentAction, Any, Any], Observation | Awaitable[Observation]]


class ActionRegistry:
    """Maps action names to one isolated handler and its declared contract."""

    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, spec: ActionSpec, handler: ActionHandler) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate action: {spec.name}")
        if not callable(handler):
            raise TypeError(f"handler for {spec.name} is not callable")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def spec(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def handler(self, name: str) -> ActionHandler | None:
        return self._handlers.get(name)

    def names(self) -> list[str]:
        return list(self._specs)

    def specs(self) -> dict[str, ActionSpec]:
        return dict(self._specs)

    def as_dict(self) -> list[dict[str, Any]]:
        return [self._specs[name].as_dict() for name in self._specs]


class ActionExecutorProtocol(Protocol):
    async def execute(self, action: AgentAction, context: Any, execution: Any) -> Observation: ...
