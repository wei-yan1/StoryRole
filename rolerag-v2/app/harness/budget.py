"""Hard budget accounting for one Harness turn."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .actions import ActionSpec
from .types import TurnBudget


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class BudgetLedger:
    """Tracks the fields `TurnBudget` used to only declare.

    The ledger is intentionally conservative: an action is rejected *before*
    execution when its category has no remaining allowance. Token usage is
    charged only when a caller actually reports it; an unreported model call
    still consumes a model-call slot.
    """

    budget: TurnBudget
    started_at: float = field(default_factory=time.perf_counter)
    model_calls: int = 0
    retrieve_calls: int = 0
    tokens: int = 0
    steps: int = 0
    degraded: list[str] = field(default_factory=list)

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000

    def remaining_ms(self) -> float:
        effective = min(
            float(self.budget.deadline_ms),
            float(self.budget.max_wall_time_ms),
        )
        return max(0.0, effective - self.elapsed_ms())

    def deadline_exceeded(self) -> bool:
        return self.remaining_ms() <= 0

    def check_action(self, spec: ActionSpec, *, step: int, max_steps: int) -> tuple[bool, str]:
        if step >= max_steps:
            return False, "max_steps_exceeded"
        if self.deadline_exceeded():
            return False, "deadline_exceeded"
        if spec.category == "model" and self.model_calls >= int(self.budget.max_model_calls):
            return False, "max_model_calls_exceeded"
        if spec.category == "tool" and self.retrieve_calls >= int(self.budget.max_retrieve_calls):
            return False, "max_retrieve_calls_exceeded"
        if self.tokens >= int(self.budget.max_tokens):
            return False, "max_tokens_exceeded"
        return True, ""

    def charge_model(self, *, stage: str, tokens: int = 0) -> None:
        self.model_calls += 1
        self.tokens += max(0, int(tokens))
        if self.model_calls > int(self.budget.max_model_calls):
            self.degraded.append(f"budget_model_calls:{stage}")
        if self.tokens > int(self.budget.max_tokens):
            self.degraded.append(f"budget_tokens:{stage}")

    def charge_tool(self) -> None:
        self.retrieve_calls += 1
        if self.retrieve_calls > int(self.budget.max_retrieve_calls):
            self.degraded.append("budget_retrieve_calls")

    def charge_tokens(self, tokens: int) -> None:
        self.tokens += max(0, int(tokens))
        if self.tokens > int(self.budget.max_tokens):
            self.degraded.append("budget_tokens")

    def charge_observation(self, observation: Any) -> None:
        delta = getattr(observation, "budget_delta", None) or {}
        if delta.get("model_calls"):
            self.charge_model(
                stage=str(delta.get("stage") or observation.action),
                tokens=int(delta.get("tokens") or 0),
            )
        elif delta.get("tokens"):
            self.charge_tokens(int(delta.get("tokens") or 0))
        if delta.get("retrieve_calls"):
            for _ in range(max(0, int(delta.get("retrieve_calls") or 0))):
                self.charge_tool()

    def snapshot(self) -> dict[str, Any]:
        return {
            "budget": {
                "max_tokens": self.budget.max_tokens,
                "max_wall_time_ms": self.budget.max_wall_time_ms,
                "max_model_calls": self.budget.max_model_calls,
                "max_retrieve_calls": self.budget.max_retrieve_calls,
                "max_context_tokens": self.budget.max_context_tokens,
                "max_review_attempts": self.budget.max_review_attempts,
                "deadline_ms": self.budget.deadline_ms,
            },
            "used": {
                "model_calls": self.model_calls,
                "retrieve_calls": self.retrieve_calls,
                "tokens": self.tokens,
                "steps": self.steps,
                "elapsed_ms": round(self.elapsed_ms(), 2),
            },
            "degraded": list(self.degraded),
        }

    def as_dict(self) -> dict[str, Any]:
        return self.snapshot()
