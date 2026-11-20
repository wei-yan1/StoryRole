"""Pre-execution guardrails for a bounded Harness turn.

Guardrails answer one question: may this action run now? They do not execute it,
do not rewrite its arguments, and do not hide failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .actions import ActionSpec
from .budget import BudgetLedger


@dataclass
class GuardrailDecision:
    allowed: bool
    reason: str = ""
    status: str = "ok"  # ok | denied | error

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, "status": self.status}


class Guardrail(Protocol):
    name: str

    def check(self, action: Any, spec: ActionSpec, ctx: Any) -> GuardrailDecision: ...


def _terminal_failure(ctx: Any) -> bool:
    if getattr(ctx, "state", {}).get("_terminal_error"):
        return True
    for item in getattr(ctx, "observations", []):
        if (
            getattr(item, "status", "") in {"error", "timeout", "degraded"}
            and getattr(item, "action", "") in {
                "plan_turn", "understand_event", "express", "review", "learn",
            }
        ):
            return True
    return False


class DependencyGuard:
    name = "dependency"

    def check(self, action: Any, spec: ActionSpec, ctx: Any) -> GuardrailDecision:
        missing = [name for name in spec.requires if name not in ctx.completed_actions]
        # A terminal failure is allowed to stop even if `learn` never ran; the
        # alternative is a deny loop that never reports the real failure.
        if action.name == "stop" and _terminal_failure(ctx):
            missing = [name for name in missing if name != "learn"]
        if missing:
            return GuardrailDecision(False, f"missing_dependency:{','.join(missing)}", "denied")
        return GuardrailDecision(True)


class ActionLimitGuard:
    name = "action_limit"

    def check(self, action: Any, spec: ActionSpec, ctx: Any) -> GuardrailDecision:
        if spec.max_per_turn is not None and spec.max_per_turn > 0:
            used = int(ctx.action_counts.get(action.name, 0))
            if used >= int(spec.max_per_turn):
                return GuardrailDecision(False, f"max_per_turn_exceeded:{action.name}", "denied")
        return GuardrailDecision(True)


class BudgetGuard:
    name = "budget"

    def __init__(self, ledger: BudgetLedger, *, max_steps: int) -> None:
        self.ledger = ledger
        self.max_steps = max_steps

    def check(self, action: Any, spec: ActionSpec, ctx: Any) -> GuardrailDecision:
        allowed, reason = self.ledger.check_action(
            spec, step=ctx.step, max_steps=self.max_steps,
        )
        if not allowed:
            return GuardrailDecision(False, reason, "error" if reason == "max_steps_exceeded" else "denied")
        return GuardrailDecision(True)


class TerminalGuard:
    name = "terminal"

    def check(self, action: Any, spec: ActionSpec, ctx: Any) -> GuardrailDecision:
        if action.name == "stop" and "learn" not in ctx.completed_actions:
            if not _terminal_failure(ctx):
                return GuardrailDecision(False, "stop_before_learn", "denied")
        return GuardrailDecision(True)


class GuardrailPipeline:
    def __init__(self, guardrails: list[Guardrail] | None = None) -> None:
        self.guardrails = list(guardrails or [])

    def add(self, guardrail: Guardrail) -> None:
        self.guardrails.append(guardrail)

    def check(self, action: Any, spec: ActionSpec, ctx: Any) -> GuardrailDecision:
        for guardrail in self.guardrails:
            decision = guardrail.check(action, spec, ctx)
            if not decision.allowed:
                return decision
        return GuardrailDecision(True)
