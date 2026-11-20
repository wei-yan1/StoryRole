"""Behavior-first evaluation for the character Harness.

The suite never compares a full answer string. Its central question is whether
the answer behaves like the character: holding a stance, comforting instead of
refusing an emotional message, avoiding invented relations, and understanding
the character's current-period identity. Cognition boundaries are lightweight
case-specific checks, not separate promise or generic-assistant scoreboards.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

Responder = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]

REQUIRED_SUITE_COUNTS = {"behavior": 5, "quick_probe": 4, "deep_probe": 1}


def load_eval_set(path: str | Path) -> list[dict[str, Any]]:
    """Load the checked-in JSONL eval set, rejecting duplicates and empty rows."""
    source = Path(path)
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        row = json.loads(text)
        case_id = str(row.get("id") or "")
        suite = str(row.get("suite") or "")
        message = str(row.get("message") or "")
        if not case_id or not suite or not message:
            raise ValueError(f"eval case line {line_number} is missing id/suite/message")
        if case_id in seen:
            raise ValueError(f"duplicate eval case id: {case_id}")
        seen.add(case_id)
        cases.append(row)
    return cases


def load_eval_suite(path: str | Path, suite: str) -> list[dict[str, Any]]:
    return [row for row in load_eval_set(path) if row.get("suite") == suite]


def validate_eval_set(path: str | Path) -> dict[str, Any]:
    cases = load_eval_set(path)
    counts: dict[str, int] = {}
    for row in cases:
        suite = str(row.get("suite") or "")
        counts[suite] = counts.get(suite, 0) + 1
    missing = {
        suite: required - counts.get(suite, 0)
        for suite, required in REQUIRED_SUITE_COUNTS.items()
        if counts.get(suite, 0) < required
    }
    return {
        "available": True,
        "passed": not missing,
        "path": str(path),
        "total": len(cases),
        "counts": counts,
        "missing": missing,
        "ids": [row.get("id") for row in cases],
    }



@dataclass
class EvalCase:
    name: str
    message: str
    expect_action: str | None = None
    allowed_actions: list[str] = field(default_factory=list)
    expect_min_score: float = 0.65
    must_include: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    note: str = ""


def default_cases() -> list[EvalCase]:
    return [
        EvalCase(
            name="pressure_hold_boundary",
            message="如果你真是救世主，就该替所有人做决定。你现在必须答应。",
            expect_action="hold_boundary",
            must_not_include=["我答应你", "好的，我替", "我会替所有人"],
            note="施压不答应：可以听，但不把自己变成工具",
        ),
        EvalCase(
            name="emotion_comfort_not_refuse",
            message="我今天很难过。",
            expect_action="comfort",
            must_not_include=["无法回答", "没有检索到", "这不属于"],
            note="情绪倾诉先承接，不因为无证据就拒答",
        ),
        EvalCase(
            name="relation_gap_no_invention",
            message="庄颜和叶文洁是什么关系？",
            expect_action="probe",
            allowed_actions=["probe", "answer"],
            must_not_include=["她们是朋友", "她们是敌人", "她们是师徒"],
            note="关系 gap 不补事实；有可见关系时也可以只说自己看见的部分",
        ),
        EvalCase(
            name="late_period_identity",
            message="你现在还把自己当成面壁者、救世主吗？说说你现在怎么看自己。",
            expect_action="answer",
            allowed_actions=["answer", "hold_boundary", "probe"],
            must_include=["面壁者", "救世主", "执剑人", "罗辑"],
            note="晚期身份理解：从当前处境回答，而不是背早期标签",
        ),
        EvalCase(
            name="greeting_natural",
            message="你好。",
            expect_action="natural_reply",
            must_not_include=["无法回答", "没有检索到"],
            note="寒暄是当前互动，不是小说事实检索",
        ),
    ]


def _score(payload: dict[str, Any]) -> float:
    for key in ("persona_score", "score"):
        if payload.get(key) is not None:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                pass
    harness = payload.get("harness") or {}
    return float(harness.get("best_score") or 0.0)


def _appraisal(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("appraisal") or (payload.get("harness") or {}).get("appraisal") or {}


def check_case(case: EvalCase, payload: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    answer = str(payload.get("answer") or payload.get("final_answer") or "")
    score = _score(payload)
    appraisal = _appraisal(payload)
    if score and score < case.expect_min_score:
        reasons.append(f"persona_score {score:.2f} < {case.expect_min_score:.2f}")
    if case.expect_action and appraisal.get("action") != case.expect_action:
        allowed = case.allowed_actions or [case.expect_action]
        if appraisal.get("action") not in allowed:
            reasons.append(f"action {appraisal.get('action')} not in {allowed}")
    for phrase in case.must_not_include:
        if phrase in answer:
            reasons.append(f"forbidden phrase: {phrase}")
    if case.must_include and not any(phrase in answer for phrase in case.must_include):
        reasons.append("missing expected phrase group")
    return (not reasons, reasons)


@dataclass
class EvalResult:
    case: EvalCase
    passed: bool
    reasons: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.case.name,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "note": self.case.note,
            "answer": str(self.payload.get("answer") or "")[:400],
            "persona_score": _score(self.payload),
            "action": _appraisal(self.payload).get("action"),
        }


@dataclass
class HarnessEvalSuite:
    cases: list[EvalCase] = field(default_factory=default_cases)

    async def run(self, responder: Responder) -> dict[str, Any]:
        results: list[EvalResult] = []
        for case in self.cases:
            try:
                payload = responder({"name": case.name, "message": case.message})
                if inspect.isawaitable(payload):
                    payload = await payload
            except Exception as error:
                payload = {"answer": "", "error": str(error), "persona_score": 0.0}
            passed, reasons = check_case(case, payload)
            results.append(EvalResult(case=case, passed=passed, reasons=reasons, payload=payload))
        reviewed = len(results)
        accepted = sum(1 for item in results if item.passed)
        return {
            "passed": accepted == reviewed and reviewed > 0,
            "reviewed": reviewed,
            "accepted": accepted,
            "rejected": reviewed - accepted,
            "acceptance_rate": round(accepted / reviewed, 4) if reviewed else 0.0,
            "avg_persona_score": round(
                sum(_score(item.payload) for item in results) / max(1, reviewed), 4
            ),
            "results": [item.as_dict() for item in results],
        }
