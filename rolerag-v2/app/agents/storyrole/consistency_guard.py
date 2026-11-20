"""Post-generation role and boundary review."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain.chat_models import init_chat_model
from app.observability import observe_async_call


class ConsistencyGuardAgent:
    agent_id = "consistency-guard"

    async def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = str(payload.get("draft_answer") or "")
        profile = payload.get("profile") or {}
        if not draft:
            return {"pass": False, "score": 0.0, "persona_score": 0.0,
                    "violations": ["empty_answer"], "final_answer": draft}
        fallback = {
            "pass": True, "score": 0.75, "persona_score": 0.75,
            "violations": [], "rewrite_instruction": "", "final_answer": draft,
        }
        local = payload.get("persona_fidelity") or {}
        if local.get("ok") is False:
            fallback = {
                **fallback,
                "pass": False,
                "persona_score": float(local.get("persona_score") or 0.5),
                "violations": list(local.get("persona_violations") or []),
                "rewrite_instruction": str(local.get("persona_instruction") or "更像角色自己的口吻"),
            }
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not api_key or os.getenv("STORYROLE_GUARD_ENABLED", "1").lower() not in {"1", "true", "yes"}:
            return fallback
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
            if base_url:
                os.environ["OPENAI_BASE_URL"] = base_url
            from app.rag.rolerag.persona.contract import extract_contract_from_payload

            packet = payload.get("review_packet") or {}
            if isinstance(packet, dict) and packet.get("contract_text"):
                contract_text = str(packet.get("contract_text") or "")
                evidence = list(packet.get("evidence") or [])
                relationship_text = str(packet.get("relationship_text") or "")
                criteria = str(packet.get("criteria") or "")
            else:
                contract = extract_contract_from_payload(payload)
                contract_text = contract.render(limit=6000) if contract else "（未提供角色契约）"
                evidence = (
                    (payload.get("role_context") or {}).get("evidence")
                    or (payload.get("context") or {}).get("novel_evidence") or []
                )
                relationship_text = json.dumps(
                    (payload.get("role_context") or {}).get("ego_summary") or "", ensure_ascii=False
                )[:2500]
                criteria = (
                    "主评：像不像这个角色。综合身份、信念、目标与恐惧、关系态度、决策方式和说话习惯；"
                    "事实正确但不像本人，仍应判 fail。"
                    "轻查：是否超出角色在当前时期、亲身经历和可见证据内的认知；"
                    "早期/晚期混写并入这一项，不单独扩展评审。"
                    "当前身份中已交接、离开、审判或结束的职责是现实约束；把过去职责写成现在仍执行，判 fail。"
                )
            llm = init_chat_model(os.getenv("STORYROLE_GUARD_MODEL", os.getenv("STORYROLE_CHAT_MODEL", "deepseek-v4.1-flash-1017")), model_provider="openai", temperature=0)
            prompt = f"""
你是角色“像不像”评审，不是事实裁判。
首要标准：这段话是否只能由这个角色说出来；事实正确但不像本人，判 fail。
{criteria}

女娲角色契约（身份、矛盾、目标、恐惧、语气、判断方式）：
{contract_text}

RoleRAG 可见记忆（只用于轻量核对“当前是否知道”，不要把角色变成事实解说员）：
{json.dumps(evidence, ensure_ascii=False)[:9000]}

当前角色关系/ego：
{relationship_text[:2500]}

用户问题：{payload.get('message', '')}
角色草稿：{draft}

只输出 JSON，不输出解释。字段：
pass(boolean), persona_score(0-1), score(0-1), violations(list), rewrite_instruction(string), final_answer(string)。
如果草稿像角色，final_answer 原样返回；如果跑偏，做最小幅度重写：
保留原意和证据，不新增事实，优先恢复女娲契约里的语气、矛盾、关系姿态和判断方式。
""".strip()
            raw = str((await observe_async_call(lambda: llm.ainvoke(prompt), operation="consistency_guard", trace_id=payload.get("trace_id"), model=llm, prompt=prompt)).content)
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end + 1])
                if isinstance(parsed, dict) and parsed.get("final_answer"):
                    return {**fallback, **parsed}
        except Exception:
            pass
        return fallback
