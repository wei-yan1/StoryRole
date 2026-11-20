"""Deep-mode evidence synthesis without exposing hidden chain-of-thought."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain.chat_models import init_chat_model
from app.observability import observe_async_call


class EvidenceAnalysisAgent:
    agent_id = "evidence-analysis"

    async def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = payload.get("context") or {}
        evidence = list(context.get("novel_evidence") or [])
        profile = context.get("profile") or {}
        fallback = {
            "supported_facts": [item.get("chunk_id") for item in evidence if item.get("chunk_id")],
            "behavioral_observations": list(profile.get("personality") or [])[:3],
            "motivations": list(profile.get("goals") or [])[:3],
            "relationship_implications": [],
            "inferences": [],
            "uncertainties": ["回答只依据当前检索到的证据"],
            "claim_review": [],
        }
        model_name = os.getenv(
            "STORYROLE_EVIDENCE_MODEL",
            os.getenv("STORYROLE_REASONING_MODEL", "deepseek-v4.1-flash-1017"),
        )
        # 项目固定约束：语言模型统一经阿里云 MaaS 转发，优先 OPENAI_*。
        # deepseek-v4.1-flash-1017 是阿里云上的模型 ID；DEEPSEEK_* 只作
        # 官方端点回滚配置，禁止按模型名前缀自动切换；配置约定见根目录 .env 注释。
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
        if not api_key or not evidence:
            return fallback
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            if base_url:
                os.environ["OPENAI_BASE_URL"] = base_url
            model = init_chat_model(model_name, model_provider="openai", temperature=0, max_tokens=1400)
            deep_plan = payload.get("deep_plan") or {}
            compact_plan = {
                "analysis_type": deep_plan.get("analysis_type"),
                "claims_to_resolve": list(deep_plan.get("claims_to_resolve") or [])[:6],
            }
            compact_profile = {
                key: profile.get(key)
                for key in (
                    "identity", "period_name", "period_stage", "personality", "goals",
                    "fears", "core_beliefs", "relationships", "anti_patterns",
                )
                if profile.get(key)
            }
            compact_evidence = [
                {
                    "chunk_id": item.get("chunk_id"),
                    "chapter": item.get("chapter"),
                    "source": item.get("source"),
                    "text": str(item.get("text") or item.get("summary") or "")[:1400],
                }
                for item in evidence[:4]
            ]
            prompt = f"""
你是小说证据分析 Agent。只做证据归纳，不写最终回答，不输出思维链。
严格区分：原文支持的事实、基于画像的合理观察、无法确认的推断。
输出严格 JSON：supported_facts(list of objects with fact and evidence_ids),
behavioral_observations(list), motivations(list), relationship_implications(list),
inferences(list), uncertainties(list), claim_review(list of objects with claim, status, evidence_ids, reason)。
逐条核对问题规划中的 claims_to_resolve，标记 supported、partial 或 unsupported。
每条不超过80字：supported_facts≤6，observations≤4，motivations≤3，relationship_implications≤4，inferences≤2，uncertainties≤3，claim_review只覆盖输入claims。
不得新增证据之外的剧情，不写最终回答。
用户问题：{payload.get('message', '')}
问题规划：{json.dumps(compact_plan, ensure_ascii=False)}
角色画像：{json.dumps(compact_profile, ensure_ascii=False)[:6000]}
小说证据：{json.dumps(compact_evidence, ensure_ascii=False)}
""".strip()
            raw = str((await observe_async_call(lambda: model.ainvoke(prompt), operation="evidence_analysis", trace_id=payload.get("trace_id"), model=model, prompt=prompt)).content)
            parsed = self._parse_json(raw)
            if isinstance(parsed, dict):
                return {**fallback, **parsed}
        except Exception:
            pass
        return fallback

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        text = raw.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    value = json.loads(text[start:end + 1])
                    return value if isinstance(value, dict) else None
                except json.JSONDecodeError:
                    return None
        return None
