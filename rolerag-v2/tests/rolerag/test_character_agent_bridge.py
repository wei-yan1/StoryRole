"""The RoleRAG bridge must not become a second conversation controller.

These tests pin the ownership boundary introduced after the architecture
review: RoleRAG supplies visible memory, but history, mode, cognition,
validation and persistence stay in the old CharacterConversationAgent.
"""

from __future__ import annotations

import asyncio
from contextlib import nullcontext

import pytest

from app.agents.storyrole.character_agent import CharacterConversationAgent
from app.agents.storyrole import character_agent as character_module
from app.agents.a2a import registry as registry_module
from app.rag.rolerag import api_adapter


class _Trace:
    trace_id = "test-trace"

    def start(self) -> None:
        pass

    def step(self, *_args, **_kwargs):
        return nullcontext()

    def finish(self, *_args, **_kwargs) -> None:
        pass


class _Prepared:
    messages = [{"role": "user", "content": "上一轮"}]
    summary = "上一轮摘要"


class _FakeA2A:
    async def send(self, agent_id, payload):
        if agent_id == "query-planner":
            message = str(payload.get("message") or "")
            intent = "emotion" if "难过" in message else "fact_question"
            return {
                "intent": intent, "needs_memory": False,
                "needs_relationship": False, "needs_timeline_check": False,
                "decision_backend": "fake",
            }
        if agent_id == "context-curator":
            return {"context": {"profile": {"identity": "面壁者"}, "novel_evidence": []}}
        if agent_id == "character-reasoning":
            return {"response_action": "按当前处境自然回应"}
        if agent_id == "memory-decision":
            return {"requires_confirmation": False, "should_save": False}
        return {}


@pytest.mark.parametrize(
    ("intent", "message", "answer", "expected_engine", "expected_action"),
    [
        ("fact_question", "叶文洁提出了什么？", "我记得两条公理。", "rolerag", "answer"),
        ("emotion", "我今天很难过", "我在。", "not_needed", "comfort"),
    ],
)
def test_subject_recall_keeps_history_and_generation_path(
    monkeypatch, intent, message, answer, expected_engine, expected_action,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.delenv("STORYROLE_AGENT_HARNESS", raising=False)

    monkeypatch.setattr(character_module, "TraceContext", lambda **_kwargs: _Trace())
    async def fake_prepare_history(**_kwargs):
        return _Prepared()

    monkeypatch.setattr(
        "app.services.chat_context_compaction.prepare_history",
        fake_prepare_history,
    )
    monkeypatch.setattr(
        character_module,
        "get_persona_profile_for_period",
        lambda **_kwargs: {"profile": {"identity": "面壁者", "goals": ["守住庄颜"]}, "version": 22},
    )
    monkeypatch.setattr(
        character_module,
        "get_character",
        lambda **_kwargs: {"canonical_name": "罗辑", "novel_id": "novel-1"},
    )
    monkeypatch.setattr(
        api_adapter,
        "retrieve_from_manifest",
        lambda *_args, **_kwargs: {
            "cutoff": 44,
            "route": "recall",
            "route_reason": "可见事实",
            "evidence": [{"id": "e1", "chunk_id": "e1", "text": "叶文洁提出公理", "kind": "fact"}],
            "ego_summary": "我眼里的他们：史强是能办事的人。",
            "profile_overlay": {"relationships": ["史强：护送我"], "known": ["两条公理"], "unknown": []},
            "boundary_source": "period_terms",
            "boundary_confidence": 0.75,
        },
    )
    monkeypatch.setattr(character_module.novel_import_service, "get_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(character_module, "get_character_period", lambda **_kwargs: None)
    monkeypatch.setattr(character_module, "get_latest_period_analysis", lambda **_kwargs: None)
    monkeypatch.setattr(character_module, "list_characters", lambda **_kwargs: [])
    monkeypatch.setattr(registry_module, "client", _FakeA2A())

    async def fake_run_agent(self, **kwargs):
        captured.update(kwargs)
        return answer

    monkeypatch.setattr(CharacterConversationAgent, "_run_agent", fake_run_agent)
    async def fake_update_relationship(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        CharacterConversationAgent,
        "_update_relationship",
        fake_update_relationship,
    )
    monkeypatch.setattr(
        CharacterConversationAgent,
        "_persist_memory_candidate",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        CharacterConversationAgent,
        "_record_evidence_graph",
        lambda *_args, **_kwargs: None,
    )

    payload = {
        "owner_id": 2,
        "novel_id": "novel-1",
        "character_id": 1,
        "period_id": 7,
        "message": message,
        "thread": {"id": 11},
        "mode": "quick",
        "web_mode": "off",
        "debug": True,
    }
    result = asyncio.run(CharacterConversationAgent().reply(payload))

    assert result["answer"] == answer
    assert result["engine"] == expected_engine
    assert result["cutoff"] == (44 if expected_engine == "rolerag" else None)
    assert result["profile_injected"] is (expected_engine == "rolerag")
    assert captured["recent_messages"] == [{"role": "user", "content": "上一轮"}]
    assert "面壁者" in captured["persona_contract"]
    assert captured["context_manifest"] is not None
    role_context = captured["context"]["role_context"]
    if expected_engine == "rolerag":
        assert role_context["ego_summary"].startswith("我眼里的他们")
        assert role_context["profile_overlay"]["known"] == ["两条公理"]
    assert result["persona_fidelity"]["ok"] is True
    assert result["harness_enabled"] is True
    assert result["appraisal"]["action"] == expected_action
    assert result["subject"]["recall"]["role_recall_executed"] is (expected_engine == "rolerag")
    assert result["harness"]["stop_reason"] == "review_accepted"


def test_dispatch_fallback_is_lazy_when_a2a_succeeds() -> None:
    class Client:
        async def send(self, _agent_id, _payload):
            return {"decision_backend": "aliyun_maas"}

    fallback_calls = 0

    async def fallback():
        nonlocal fallback_calls
        fallback_calls += 1
        return {"decision_backend": "local_fallback"}

    result = asyncio.run(CharacterConversationAgent._dispatch_timeout(
        Client(), "role-cognition", {}, timeout=1.0, fallback=fallback,
    ))
    assert result["decision_backend"] == "aliyun_maas"
    assert fallback_calls == 0


def test_dispatch_fallback_runs_once_after_a2a_failure() -> None:
    class Client:
        async def send(self, _agent_id, _payload):
            raise RuntimeError("a2a unavailable")

    fallback_calls = 0

    async def fallback():
        nonlocal fallback_calls
        fallback_calls += 1
        return {"decision_backend": "local_fallback"}

    wrapped = asyncio.run(CharacterConversationAgent._dispatch_timeout(
        Client(), "role-cognition", {}, timeout=1.0, fallback=fallback,
    ))
    value, degraded = CharacterConversationAgent._unwrap_fallback(wrapped)
    assert degraded
    assert value["decision_backend"] == "local_fallback"
    assert fallback_calls == 1


def test_exhausted_turn_budget_skips_remote_and_model_fallback() -> None:
    class Kernel:
        def __init__(self):
            self.notes = 0

        def remaining_seconds(self):
            return 0.0

        def note_deadline(self):
            self.notes += 1

    class Client:
        async def send(self, _agent_id, _payload):
            raise AssertionError("remote call must not start after deadline")

    kernel = Kernel()
    fallback_calls = 0

    async def fallback():
        nonlocal fallback_calls
        fallback_calls += 1
        return {"decision_backend": "local_fallback"}

    wrapped = asyncio.run(CharacterConversationAgent._dispatch_timeout(
        Client(), "role-cognition", {}, timeout=1.0, fallback=fallback, kernel=kernel,
    ))
    value, degraded = CharacterConversationAgent._unwrap_fallback(wrapped)
    assert degraded
    assert value["decision_backend"] == "deadline_fallback"
    assert fallback_calls == 0
    assert kernel.notes == 1
