"""Role-specific decision layer for deep conversations."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain.chat_models import init_chat_model
from app.observability import observe_async_call


class RoleCognitionAgent:
    agent_id = "role-cognition"

    async def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile = payload.get("profile") or {}
        evidence_analysis = payload.get("evidence_analysis") or {}
        role_context = payload.get("role_context") or {}
        subject_state = payload.get("subject_state") or {}
        subject_understanding = payload.get("subject_understanding") or {}
        history_summary = str(payload.get("history_summary") or "")
        recent_messages = list(payload.get("recent_messages") or [])
        fallback_action = {
            "emotion": "先承接对方情绪，再按角色立场回应",
            "pressure": "守住角色自己的选择，不因施压屈从",
            "relationship_probe": "按可见关系回答，不确定处追问",
            "fact_question": "只依据可见记忆回答，不确定处保留",
            "greeting": "自然回应",
        }.get(str(subject_understanding.get("user_move") or ""), "先回应用户真正的困惑，再保留角色立场")
        fallback = {
            "character_emotion": subject_understanding.get("emotional_register") or (profile.get("emotional_patterns") or ["保持角色原有情绪底色"])[0],
            "value_judgment": (profile.get("core_beliefs") or ["依据自己的价值观而非讨好用户"])[0],
            "response_action": fallback_action,
            "relationship_posture": (subject_state.get("relationship_stance") or {}).get("posture") or "结合当前关系自然回应",
            "answer_shape": "观点 + 原因 + 必要的不确定性",
            "must_not_say": profile.get("anti_patterns") or ["全知全能", "百科式解释"],
            "analysis_type": str(payload.get("analysis_type") or "mixed"),
            "change_from_previous": "",
            "decision_backend": "deterministic_fallback",
        }
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return fallback
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
            if base_url:
                os.environ["OPENAI_BASE_URL"] = base_url
            model = init_chat_model(
                os.getenv("STORYROLE_COGNITION_MODEL", os.getenv("STORYROLE_REASONING_MODEL", "deepseek-v4.1-flash-1017")),
                model_provider="openai", temperature=0,
            )
            prompt = f"""
你是角色的内部认知决策 Agent，不负责写最终答案，不输出思维链。
根据角色画像、当前时期、连续自我状态、检索前理解、用户问题和证据分析，决定角色应该如何行动。
如果 analysis_type 是 emotion，先承接用户情绪，再保持角色边界；如果是 relationship，结合真实关系状态；如果是 fact，也只使用可见记忆，事实正确不能替代角色立场。
优先保留角色的价值观、矛盾、情绪和关系姿态，不要把角色变成中立讲解员。你可以继续、调整或改变此前的决定，但必须依据当前处境与经历。
只输出 JSON：character_emotion, value_judgment, response_action,
relationship_posture, answer_shape, must_not_say, change_from_previous。
change_from_previous 只能是 new / continue / adjust / reverse；解释或确认此前边界是 continue，不是 reverse。
分析类型：{payload.get('analysis_type', 'mixed')}
回答计划：{json.dumps(payload.get('deep_plan') or {}, ensure_ascii=False)[:5000]}
角色当前可用的记忆与认知边界（RoleRAG）：{json.dumps(role_context, ensure_ascii=False)[:8000]}
线程中的连续自我状态：{json.dumps(subject_state, ensure_ascii=False)[:5000]}
检索前形成的主体理解：{json.dumps(subject_understanding, ensure_ascii=False)[:4000]}
较早对话摘要：{history_summary[:3000]}
最近对话：{json.dumps(recent_messages[-8:], ensure_ascii=False)[:4000]}
角色画像：{json.dumps(profile, ensure_ascii=False)[:12000]}
证据分析：{json.dumps(evidence_analysis, ensure_ascii=False)[:12000]}
用户问题：{payload.get('message', '')}
""".strip()
            raw = str((await observe_async_call(lambda: model.ainvoke(prompt), operation="role_cognition", trace_id=payload.get("trace_id"), model=model, prompt=prompt)).content)
            parsed = self._parse_json(raw)
            if isinstance(parsed, dict):
                return {**fallback, **parsed, "decision_backend": "aliyun_maas"}
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
