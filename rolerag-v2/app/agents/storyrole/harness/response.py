"""Response projection for a completed StoryRole Harness turn."""

from __future__ import annotations

import time
from typing import Any


def build_response(
    turn: Any,
    result: Any,
    *,
    started_at: float,
    identity: dict[str, Any],
    runtime_error: str = "",
) -> dict[str, Any]:
    final_state = result.state.get("subject") or result.state.get("subject_state") or {}
    if hasattr(final_state, "as_dict"):
        final_state = final_state.as_dict()
    review = dict(turn.review or {})
    fidelity = turn.local_fidelity.as_dict() if turn.local_fidelity is not None else {}
    appraisal = turn.appraisal.as_dict() if turn.appraisal is not None else {}
    understanding = turn.understanding.as_dict() if turn.understanding is not None else {}
    degradations = list(turn.degradations)
    if result.degraded:
        degradations.append("agent_harness_degraded")
    if result.stop_reason != "completed":
        degradations.append(f"agent_harness_stop:{result.stop_reason}")
    if runtime_error:
        degradations.append(f"agent_harness_error:{runtime_error}")
    if turn.full_manifest is not None and turn.full_manifest.budget_trimmed:
        if "harness_context_trimmed" not in degradations:
            degradations.append("harness_context_trimmed")
    # Keep the response's subject/decision fields compatible with the existing
    # probe and API, while the full runtime evidence remains in `harness`.
    harness_state = {
        **dict(result.state or {}),
        "subject": final_state,
        "understanding": understanding,
        "decision": appraisal.get("decision") or {},
        "context": turn.full_manifest.as_dict() if turn.full_manifest is not None else {},
        "checkpoint": dict(result.checkpoint or {}),
        "stop_reason": "review_accepted" if review.get("pass") else result.stop_reason,
    }
    return {
        "answer": turn.final_answer or result.answer,
        "character_name": turn.character_name,
        "profile_version": (turn.identity.get("profile_row") or {}).get("version"),
        "mode": turn.mode,
        "plan": {**dict(turn.plan or {}), "mode": turn.mode},
        "deep_plan": dict(turn.deep_plan or {}),
        "reasoning": dict(turn.cognition or {}),
        "execution_plan": turn.execution_plan.as_dict() if turn.execution_plan is not None else {},
        "review": review,
        "memory_decision": dict(turn.memory_decision or {"requires_confirmation": False, "should_save": False}),
        "evidence_count": len(turn.role_evidence),
        "web_evidence_count": len(turn.web_evidence),
        "web_mode": str(turn.payload.get("web_mode") or "off"),
        "engine": "rolerag" if turn.role_retrieval else ("not_needed" if not (turn.plan or {}).get("needs_novel_search") else "legacy"),
        "cutoff": turn.role_retrieval.get("cutoff"),
        "boundary_source": turn.role_retrieval.get("boundary_source"),
        "boundary_confidence": turn.role_retrieval.get("boundary_confidence"),
        "profile_injected": bool(turn.role_retrieval.get("profile_overlay")),
        "persona_fidelity": fidelity,
        "persona_score": review.get("persona_score", fidelity.get("score", 0.0)),
        "persona_rewritten": bool(turn.final_answer and turn.draft and turn.final_answer != turn.draft),
        "route": turn.role_retrieval.get("route"),
        "planner_backend": turn.plan.get("decision_backend"),
        "planner_intent": turn.plan.get("intent"),
        "ego_evidence_count": sum(
            1 for item in turn.role_evidence
            if str(item.get("kind") or "") in {"relation", "relation_gap"}
        ),
        "appraisal": appraisal,
        "subject": {
            "perception": {
                "event_kind": "user_message", "content": turn.message,
                "period_id": turn.period_id,
                "recent_message_count": len(turn.payload.get("recent_messages") or []),
            },
            "understanding": understanding,
            "recall": {
                "needs": list(getattr(turn.understanding, "memory_needs", []) or []),
                "reason": getattr(turn.understanding, "memory_reason", ""),
                "prior_episode_ids": list(getattr(turn.understanding, "prior_episode_ids", []) or []),
                "role_evidence_count": len(turn.role_evidence),
                "web_evidence_count": len(turn.web_evidence),
                "long_term_memory_count": len(turn.memories),
                "role_recall_executed": bool(turn.role_retrieval),
                "retrieved_evidence_count": len(turn.role_evidence),
            },
            "decision": appraisal.get("decision") or {},
            "state": final_state,
        },
        "interaction_state": final_state,
        "harness_enabled": True,
        "harness": harness_state,
        "harness_stop_reason": "review_accepted" if review.get("pass") else result.stop_reason,
        "agent_runtime": "agent_harness",
        "harness_trace": result.trace,
        "harness_budget": result.budget,
        "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        "degraded": bool(degradations),
        "degradations": degradations,
        "evidence_graph_trace_id": getattr(turn.trace, "trace_id", ""),
        "agent_harness_error": runtime_error,
    }
