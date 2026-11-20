"""Assembly for one StoryRole Harness turn.

This module is the only place that wires domain services, action handlers,
policy, tools, context and runtime together. It contains no role logic itself.
"""

from __future__ import annotations

import time
from typing import Any

from app.harness.runtime import AgentHarness
from app.harness.state import get_interaction_state_store
from app.harness.trace import HarnessTrace
from app.harness.types import SubjectState, TurnBudget, TurnScope

from .actions import build_action_registry
from .context import StoryRoleContextBuilder, StoryRoleTurn
from .handoff import TurnHandoff
from .policy import StoryRolePolicy
from .response import build_response
from .services import (
    CognitionService,
    GenerationService,
    PersistenceService,
    PlanningService,
    RecallService,
)
from .tools import build_tool_runtime


async def run_harness_turn(
    agent: Any,
    payload: dict[str, Any],
    *,
    trace: Any,
    identity: dict[str, Any],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    scope = TurnScope.from_payload(payload)
    requested_mode = str(identity.get("requested_mode") or "quick")
    mode = requested_mode if requested_mode in {"quick", "deep"} else "quick"
    budget = TurnBudget.for_mode(mode)
    identity = {
        **identity,
        "requested_mode": mode,
        "max_context_tokens": budget.max_context_tokens,
        "max_review_attempts": budget.max_review_attempts,
    }
    state_store = get_interaction_state_store()
    degradations: list[str] = []
    if getattr(state_store, "degraded", False):
        degradations.append("harness_state_backend_fallback")
    try:
        subject_state = state_store.load(scope)
    except Exception:
        subject_state = SubjectState.empty()
        degradations.append("harness_state_load_failed")
    trace_id = getattr(trace, "trace_id", "") or str(payload.get("trace_id") or "")
    harness_trace = HarnessTrace(turn_id=trace_id, scope_key=scope.state_key)
    turn = StoryRoleTurn(
        agent=agent, payload=payload, identity=identity, trace=trace, scope=scope, mode=mode,
    )
    turn.degradations.extend(degradations)
    turn.identity["_subject_state"] = subject_state

    tools = build_tool_runtime(turn)
    planning = PlanningService(turn)
    recall = RecallService(turn)
    cognition = CognitionService(turn)
    generation = GenerationService(turn)
    persistence = PersistenceService(turn)
    registry = build_action_registry(planning, recall, cognition, generation, persistence)
    context_builder = StoryRoleContextBuilder(turn, max_tokens=budget.max_context_tokens)
    policy = StoryRolePolicy(turn)
    harness = AgentHarness(
        scope=scope,
        mode=mode,
        budget=budget,
        state_store=state_store,
        context_provider=context_builder.build,
        tool_runtime=tools,
        trace=harness_trace,
        registry=registry,
        handoff_builder=lambda state: TurnHandoff.from_subject_state(state).as_dict(),
        max_steps=14 if mode == "quick" else 22,
    )
    runtime_error = ""
    try:
        result = await harness.run(policy, subject_state=subject_state, persist=True)
    except Exception as error:
        runtime_error = f"{type(error).__name__}: {error}"
        turn.degradations.append(f"agent_harness_exception:{type(error).__name__}")
        # Do not silently route back to the legacy workflow. Return an explicit
        # degraded turn so the failure is visible in the response and the trace.
        result = type("HarnessFailure", (), {
            "answer": turn.final_answer or turn.draft or "",
            "stop_reason": "agent_harness_exception",
            "actions": [],
            "observations": [],
            "trace": harness_trace.as_dict(),
            "budget": harness.ledger.as_dict(),
            "state": {"subject": subject_state.as_dict()},
            "checkpoint": harness.checkpoint.as_dict(),
            "degraded": True,
        })()
    if not turn.final_answer and result.answer:
        turn.final_answer = result.answer
    if result.stop_reason != "completed":
        turn.degradations.append(f"agent_harness_stop:{result.stop_reason}")
    trace.finish(status="degraded" if turn.degraded() or result.degraded else "completed")
    return build_response(
        turn, result, started_at=started_at, identity=identity,
        runtime_error=runtime_error,
    )
