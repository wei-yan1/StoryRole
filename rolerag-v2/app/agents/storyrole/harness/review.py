"""Clean review packet and bounded review-repair loop.

The generator and the reviewer must see different things. The reviewer gets
the user's words, the draft, the persona contract, character relationships and
at most six visible evidence rows. Its main judgment is role likeness; period
and knowledge visibility are only a lightweight cognition check. It never gets
the generator's hidden reasoning or the entire raw context blob.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.harness.graph import GraphRuntime
from app.harness.tools import distill_evidence, distill_relationship
from app.harness.types import ReviewLoopResult


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _contract_text(contract: Any) -> str:
    if contract is None:
        return ""
    if isinstance(contract, str):
        return contract
    if isinstance(contract, dict):
        return json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
    render = getattr(contract, "render", None)
    if callable(render):
        try:
            return str(render(limit=6000))
        except TypeError:
            return str(render())
    return str(contract)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "as_dict"):
        return dict(value.as_dict())
    return {}


@dataclass
class ReviewPacket:
    message: str
    draft: str
    contract_text: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    relationship_text: str = ""
    criteria: str = ""
    attempt: int = 1
    period_name: str = ""
    period_stage: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "draft": self.draft,
            "contract_text": self.contract_text,
            "evidence": list(self.evidence),
            "relationship_text": self.relationship_text,
            "criteria": self.criteria,
            "attempt": self.attempt,
            "period_name": self.period_name,
            "period_stage": self.period_stage,
        }

    def render(self) -> str:
        evidence_lines = [
            f"- [{row.get('kind')}] {row.get('text')}"
            + (f"（{row.get('source')}）" if row.get("source") else "")
            for row in self.evidence
        ] or ["- 本轮没有可见证据。"]
        return "\n".join([
            "【用户本轮原话】",
            self.message,
            "【角色草稿】",
            self.draft,
            "【角色契约（我是谁）】",
            self.contract_text,
            *(["【当前时期】", " / ".join(item for item in (self.period_name, self.period_stage) if item)]
               if (self.period_name or self.period_stage) else []),
            "【可见证据（最多六条）】",
            *evidence_lines,
            "【角色关系】",
            self.relationship_text or "无额外关系状态",
            "【评审标准】",
            self.criteria,
        ])


def build_review_packet(
    *,
    message: str,
    draft: str,
    persona_contract: Any,
    role_context: dict[str, Any] | None = None,
    interaction_state: Any = None,
    relationship: dict[str, Any] | None = None,
    attempt: int = 1,
    period: dict[str, Any] | None = None,
) -> ReviewPacket:
    role_context = role_context or {}
    contract_data = _as_dict(persona_contract)
    period_name = str((period or {}).get("name") or contract_data.get("period_name") or "")
    period_stage = str(contract_data.get("period_stage") or (period or {}).get("timeline_stage") or "")
    evidence_source = list(role_context.get("evidence") or []) + list(role_context.get("novel_evidence") or [])
    evidence = distill_evidence(evidence_source, limit=6)
    relationship_rows = distill_relationship(relationship)
    relationship_text = _clip(role_context.get("ego_summary") or "", 900)
    if relationship_rows:
        relationship_text += (
            "\n" + "信任/亲近/张力/依赖："
            f"{relationship_rows.get('trust')}/{relationship_rows.get('intimacy')}/"
            f"{relationship_rows.get('tension')}/{relationship_rows.get('dependency')}"
        )
    # Keep the parameter for callers from the older Harness contract, but do
    # not turn thread commitments into a separate review target.
    _ = interaction_state
    return ReviewPacket(
        message=message,
        draft=draft,
        contract_text=_contract_text(persona_contract),
        evidence=evidence,
        relationship_text=relationship_text[:1200],
        criteria=(
            "主评：像不像这个角色。综合身份、信念、目标与恐惧、关系态度、决策方式和说话习惯；"
            "事实正确但不像本人，仍应判 fail。"
            "轻查：是否超出角色在当前时期、亲身经历和可见证据内的认知；"
            "早期/晚期混写并入这一项，不单独扩展评审。"
            "当前身份中已交接、离开、审判或结束的职责是现实约束；把过去职责写成现在仍执行，判 fail。"
            + (f"当前时期是{period_name}，仅用于上述轻量认知检查。" if period_name else "")
        ),
        attempt=attempt,
        period_name=period_name,
        period_stage=period_stage,
    )


_MUST_FIX = {
    "knowledge_leak", "core_value_violation", "invented_relation",
    "persona_mismatch", "out_of_character",
}


@dataclass
class LoopGuard:
    """Detect a review loop that is repeating without moving.

    A repeated tool call is not automatically a loop; a repeated review with
    the same draft and the same violations is. The guard looks at progress
    (answer or violation set changed), not only at attempt count.
    """

    max_repeats: int = 2
    _seen: dict[str, int] = field(default_factory=dict)

    def fingerprint(self, draft: str, review: dict[str, Any]) -> str:
        violations = review.get("violations") or review.get("issues") or []
        if isinstance(violations, str):
            violations = [violations]
        normalized = json.dumps(
            {
                "draft": " ".join(str(draft or "").split()),
                "violations": [
                    str(item.get("type") if isinstance(item, dict) else item)
                    for item in violations
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def observe(self, draft: str, review: dict[str, Any]) -> bool:
        key = self.fingerprint(draft, review)
        count = self._seen.get(key, 0) + 1
        self._seen[key] = count
        return count >= self.max_repeats


@dataclass
class ReviewPolicy:
    accept_score: float = 0.65
    must_fix: set[str] = field(default_factory=lambda: set(_MUST_FIX))

    def score(self, review: dict[str, Any] | None) -> float:
        review = review or {}
        try:
            return float(review.get("persona_score") or review.get("score") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def accept(self, review: dict[str, Any] | None) -> bool:
        review = review or {}
        violations = review.get("violations") or review.get("issues") or []
        if isinstance(violations, str):
            violations = [violations]
        violation_names = {
            str(item.get("type") if isinstance(item, dict) else item)
            for item in violations
        }
        if violation_names & self.must_fix:
            return False
        if review.get("pass") is True:
            return True
        return self.score(review) >= self.accept_score


ReviewFn = Callable[[ReviewPacket, str, int], Awaitable[dict[str, Any]] | dict[str, Any]]


async def run_review_loop(
    *,
    draft: str,
    packet: ReviewPacket,
    review_fn: ReviewFn,
    policy: ReviewPolicy | None = None,
    max_attempts: int = 1,
) -> ReviewLoopResult:
    """One review node with a bounded self-loop; a loop is a minimal graph."""
    policy = policy or ReviewPolicy()
    max_attempts = max(1, int(max_attempts))
    guard = LoopGuard()
    state: dict[str, Any] = {
        "nodes": {},
        "draft": draft,
        "attempts": 0,
        "accepted": False,
        "no_progress": False,
        "best_answer": draft,
        "best_score": -1.0,
        "reviews": [],
        "final_answer": draft,
        "review": {},
    }

    async def review_node(current: dict[str, Any]) -> dict[str, Any]:
        attempt = int(current.get("attempts") or 0) + 1
        current["attempts"] = attempt
        packet.attempt = attempt
        try:
            result = review_fn(packet, str(current.get("draft") or draft), attempt)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as error:
            result = {
                "pass": False, "persona_score": 0.0,
                "violations": ["review_failed"], "error": str(error),
                "final_answer": str(current.get("draft") or draft),
            }
        result = dict(result or {})
        current["review"] = result
        current["reviews"].append(result)
        score = policy.score(result)
        current["accepted"] = policy.accept(result)
        final_answer = str(result.get("final_answer") or current.get("draft") or draft)
        current["no_progress"] = (
            False if current["accepted"] else guard.observe(final_answer, result)
        )
        if score >= float(current.get("best_score") or -1.0):
            current["best_score"] = score
            current["best_answer"] = final_answer
        # The reviewer's minimal rewrite is the repair; it never becomes a new
        # model generation, so streaming tokens are not duplicated.
        if not current["accepted"] and attempt < max_attempts:
            current["draft"] = final_answer
        current["final_answer"] = final_answer
        return {
            "attempt": attempt,
            "accepted": bool(current["accepted"]),
            "persona_score": score,
            "final_answer": final_answer,
        }

    runtime = GraphRuntime()
    runtime.add_node("review", review_node, description="independent persona review")
    runtime.add_conditional_edge(
        "review", "review",
        lambda current: (
            not current.get("accepted")
            and not current.get("no_progress")
            and int(current.get("attempts") or 0) < max_attempts
        ),
        label="repair",
    )
    runtime.add_conditional_edge(
        "review", "end",
        lambda current: (
            bool(current.get("accepted"))
            or bool(current.get("no_progress"))
            or int(current.get("attempts") or 0) >= max_attempts
        ),
        label="commit",
    )
    run = await runtime.run_linear(
        start="review", end="end", state=state, max_steps=max_attempts + 1,
    )
    accepted = bool(state.get("accepted"))
    best_answer = str(state.get("best_answer") or draft)
    final_answer = str(state.get("final_answer") or best_answer)
    if not accepted:
        final_answer = best_answer
    stop_reason = "review_accepted" if accepted else (
        "review_no_progress" if state.get("no_progress") else (
            "review_budget_exhausted" if state.get("attempts") else "review_failed"
        )
    )
    return ReviewLoopResult(
        accepted=accepted,
        final_answer=final_answer,
        best_answer=best_answer,
        best_score=float(state.get("best_score") or 0.0),
        attempts=int(state.get("attempts") or 0),
        stop_reason=stop_reason,
        reviews=list(state.get("reviews") or []),
        phase_history=list(run.steps),
    )
