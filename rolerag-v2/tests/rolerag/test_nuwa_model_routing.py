"""Aliyun MaaS credential routing for all language-model entry points."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents.storyrole.nuwa_profiler import NuwaProfilerAgent
from app.agents.storyrole import consistency_guard as guard_module
from app.agents.storyrole import evidence_analyst as evidence_module
from app.agents.storyrole import role_cognition_agent as cognition_module
from app.rag.rolerag.runtime import renderer_from_env


def _set_competing_endpoints(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "maas-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://maas.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://dashscope.example/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "official-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


def test_deepseek_model_uses_aliyun_maas_not_official_endpoint(monkeypatch):
    _set_competing_endpoints(monkeypatch)
    key, base_url = NuwaProfilerAgent._resolve_model_credentials("deepseek-v4.1-flash-1017")
    assert key == "maas-key"
    assert base_url == "https://maas.aliyuncs.com/compatible-mode/v1"


def test_rolerag_renderer_uses_same_aliyun_maas(monkeypatch):
    _set_competing_endpoints(monkeypatch)
    monkeypatch.setenv("ROLERAG_LLM_MODEL", "deepseek-v4.1-flash-1017")
    renderer = renderer_from_env()
    assert renderer.llm.api_key == "maas-key"
    assert renderer.llm.base_url == "https://maas.aliyuncs.com/compatible-mode/v1"


def test_dashscope_is_fallback_when_openai_is_absent(monkeypatch):
    _set_competing_endpoints(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("OPENAI_BASE_URL")
    key, base_url = NuwaProfilerAgent._resolve_model_credentials("qwen3.7-plus")
    assert key == "dashscope-key"
    assert base_url == "https://dashscope.example/v1"


def _install_fake_model(monkeypatch, module, content: str) -> None:
    class FakeModel:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(content=content)

    def fake_init(*_args, **_kwargs):
        import os
        assert os.environ["OPENAI_API_KEY"] == "maas-key"
        assert os.environ["OPENAI_BASE_URL"] == "https://maas.aliyuncs.com/compatible-mode/v1"
        return FakeModel()

    async def fake_observe(call, **_kwargs):
        return await call()

    monkeypatch.setattr(module, "init_chat_model", fake_init)
    monkeypatch.setattr(module, "observe_async_call", fake_observe)


def test_role_cognition_uses_aliyun_maas_priority(monkeypatch):
    _set_competing_endpoints(monkeypatch)
    _install_fake_model(monkeypatch, cognition_module, "{}")
    result = asyncio.run(cognition_module.RoleCognitionAgent().decide({
        "profile": {},
        "subject_state": {"relationship_stance": {"posture": "仍在观察"}},
        "subject_understanding": {"user_move": "pressure"},
    }))
    assert result["response_action"]
    assert result["decision_backend"] == "aliyun_maas"


def test_consistency_guard_uses_aliyun_maas_priority(monkeypatch):
    _set_competing_endpoints(monkeypatch)
    _install_fake_model(
        monkeypatch,
        guard_module,
        '{"pass": true, "persona_score": 0.9, "final_answer": "我在。"}',
    )
    result = asyncio.run(guard_module.ConsistencyGuardAgent().review({
        "draft_answer": "我在。",
        "review_packet": {"contract_text": "罗辑", "criteria": "像不像角色"},
    }))
    assert result["final_answer"] == "我在。"


def test_evidence_analysis_uses_maas_and_bounded_prompt(monkeypatch):
    _set_competing_endpoints(monkeypatch)
    captured = {}

    class FakeModel:
        async def ainvoke(self, prompt):
            captured["prompt"] = prompt
            return SimpleNamespace(content='{"supported_facts": [{"fact": "事实", "evidence_ids": ["e0"]}]}')

    def fake_init(*_args, **kwargs):
        import os
        captured["model_kwargs"] = kwargs
        assert os.environ["OPENAI_API_KEY"] == "maas-key"
        return FakeModel()

    async def fake_observe(call, **_kwargs):
        return await call()

    monkeypatch.setattr(evidence_module, "init_chat_model", fake_init)
    monkeypatch.setattr(evidence_module, "observe_async_call", fake_observe)
    result = asyncio.run(evidence_module.EvidenceAnalysisAgent().analyze({
        "message": "晚年回望",
        "deep_plan": {
            "analysis_type": "fact",
            "claims_to_resolve": [f"claim-{index}" for index in range(10)],
            "large_unused_field": "规划" * 5000,
        },
        "context": {
            "profile": {"identity": "罗辑", "personality": ["克制"]},
            "novel_evidence": [
                {"chunk_id": f"e{index}", "text": "证据" * 3000}
                for index in range(6)
            ],
        },
    }))
    assert result["supported_facts"][0]["evidence_ids"] == ["e0"]
    assert captured["model_kwargs"]["max_tokens"] == 1400
    assert len(captured["prompt"]) < 15000
    assert "e5" not in captured["prompt"]
    assert "claim-7" not in captured["prompt"]
    assert "规划规划规划" not in captured["prompt"]
