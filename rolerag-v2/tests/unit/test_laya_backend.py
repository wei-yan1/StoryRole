from __future__ import annotations

import pytest

from app.agents.decision.laya_backend import LayaDecisionBackend, SafeLayaDecisionBackend


class FakeRouter:
    def __init__(self) -> None:
        self.calls = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        return {
            "model": "fake-laya",
            "routing": {"model": "multilingual", "reason": "test"},
            "answers": {
                "intent": {"choice": "relationship_reflection", "confidence": 0.82},
                "needs_novel_search": {"noul": 0.05},
                "needs_memory": {"noul": 0.91},
                "needs_relationship": {"noul": 0.88},
                "needs_timeline_check": {"noul": 0.12},
                "auto_deep": {"noul": 0.10},
                "response_action": {"choice": "安慰"},
            },
        }


def test_laya_plan_maps_typed_answers_and_applies_domain_guards() -> None:
    router = FakeRouter()
    plan = LayaDecisionBackend(router=router).plan("你还记得我们上次说过的选择吗？")

    assert router.calls
    assert router.calls[0][0] == {"body": "你还记得我们上次说过的选择吗？"}
    assert plan["decision_backend"] == "laya"
    assert plan["intent"] == "relationship_reflection"
    assert plan["needs_memory"] is True
    assert plan["needs_relationship"] is True
    assert plan["response_action"] == "安慰"
    assert plan["laya_model"] == "multilingual"


def test_safe_laya_keeps_laya_ahead_of_rule() -> None:
    plan = SafeLayaDecisionBackend(router=FakeRouter()).plan("你还记得我吗？")
    assert plan["decision_backend"] == "laya"


@pytest.mark.asyncio
async def test_quick_reasoning_uses_laya_plan_when_available(monkeypatch) -> None:
    from app.agents.storyrole.reasoning_agent import CharacterReasoningAgent

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    result = await CharacterReasoningAgent().reason({
        "message": "你还记得我吗？",
        "plan": {
            "decision_backend": "laya",
            "intent": "relationship_reflection",
            "response_action": "安慰",
        },
        "context": {},
        "subject_understanding": {},
        "subject_state": {},
    })
    assert result["response_action"] == "安慰"
    assert result["decision_backend"] == "laya_quick"
