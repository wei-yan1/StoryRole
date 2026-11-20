"""Pure state transitions after a subject has acted.

Only the final accepted/reviewed answer becomes an experience.  No sentence is
promoted to a promise and no ordinary chat is written into the novel graph.
"""

from __future__ import annotations

from typing import Any

from app.harness.types import SubjectState


def update_subject_state(
    state: SubjectState,
    *,
    user_message: str,
    answer: str,
    understanding: dict[str, Any],
    decision: dict[str, Any],
    accepted: bool,
    score: float | None,
    attempts: int,
    evidence_ids: list[str] | None = None,
) -> SubjectState:
    return (state or SubjectState.empty()).record_experience(
        event=user_message,
        understanding=understanding,
        decision=decision,
        answer=answer,
        accepted=accepted,
        score=score,
        attempts=attempts,
        evidence_ids=evidence_ids,
    )


def update_interaction_state(
    state: SubjectState,
    *,
    user_message: str,
    answer: str,
    appraisal: dict[str, Any] | None = None,
    accepted: bool,
    score: float | None,
    attempts: int,
    evidence_ids: list[str] | None = None,
    understanding: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> SubjectState:
    """Compatibility entry point for callers still passing one appraisal."""
    appraisal = appraisal or {}
    understanding = understanding or appraisal.get("understanding") or {
        "user_move": appraisal.get("user_move", "smalltalk"),
        "interpretation": appraisal.get("stakes", ""),
        "stakes": appraisal.get("stakes", ""),
        "touches": appraisal.get("touches", []),
        "emotional_register": "",
    }
    decision = decision or appraisal.get("decision") or {
        "action": appraisal.get("action", "natural_reply"),
        "goal": appraisal.get("stakes", ""),
        "stance": "",
        "decision_reason": appraisal.get("stakes", ""),
    }
    return update_subject_state(
        state,
        user_message=user_message,
        answer=answer,
        understanding=understanding,
        decision=decision,
        accepted=accepted,
        score=score,
        attempts=attempts,
        evidence_ids=evidence_ids,
    )
