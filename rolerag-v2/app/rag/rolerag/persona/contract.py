"""Nuwa persona contract and the fast side of the fidelity loop.

The division of labor is deliberate:

* Nuwa supplies *who this person is*: identity, contradictions, drives,
  fears, speech habits, decision patterns, taboos and relationships.
* RoleRAG supplies *what this person may know at this period*: visible
  evidence, ego relations and knowledge boundaries.
* This module checks whether the draft still sounds like the former while
  using only the latter. The semantic review is done by the guard agent; the
  checks here are deterministic and cheap so they always run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .seed import ProfileOverlay, PersonaSeed, overlay_from_profile
from .style import DEFAULT_BANNED, measure

_AI_PHRASES = (
    "作为一个AI",
    "作为人工智能",
    "作为一个语言模型",
    "我可以帮你",
    "以下是",
    "总之",
    "综上所述",
    "首先",
    "其次",
    "需要注意的是",
    "希望这对你有帮助",
    "总的来说",
)
_OVER_EXPLAIN = (
    "从某种意义上说",
    "不可否认",
    "客观来看",
    "需要指出的是",
    "值得注意的是",
)


@dataclass(frozen=True)
class PersonaContract:
    name: str
    identity: str
    traits: tuple[str, ...]
    goals: tuple[str, ...]
    fears: tuple[str, ...]
    core_beliefs: tuple[str, ...]
    speech_style: tuple[str, ...]
    decision_patterns: tuple[str, ...]
    conversation_rules: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    relationships: tuple[str, ...]
    known: tuple[str, ...]
    unknown: tuple[str, ...]
    exemplars: tuple[str, ...] = ()
    period_name: str = ""
    period_stage: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "identity": self.identity,
            "traits": list(self.traits),
            "goals": list(self.goals),
            "fears": list(self.fears),
            "core_beliefs": list(self.core_beliefs),
            "speech_style": list(self.speech_style),
            "decision_patterns": list(self.decision_patterns),
            "conversation_rules": list(self.conversation_rules),
            "anti_patterns": list(self.anti_patterns),
            "relationships": list(self.relationships),
            "known": list(self.known),
            "unknown": list(self.unknown),
            "exemplars": list(self.exemplars),
            "period_name": self.period_name,
            "period_stage": self.period_stage,
        }

    def render(self, *, limit: int = 7000) -> str:
        """Render the contract for the generation prompt.

        The order matters: identity and contradictions before facts. The model
        must first know whose mouth it is speaking through, then what that
        mouth is allowed to remember.
        """
        parts = [f"你是{self.name}。你不是在描述他，你就是他。"]
        if self.identity:
            parts.append(f"身份：{self.identity}")
        if self.period_name or self.period_stage:
            stage = " / ".join(item for item in (self.period_name, self.period_stage) if item)
            parts.append(f"当前时期：{stage}。只按这个时期的认识、语气和关系说话。")
        if self.traits:
            parts.append("性格与矛盾（不要只挑一个标签演）：\n- " + "\n- ".join(self.traits[:8]))
        if self.goals:
            parts.append("目标（不是通用助手的目标）：\n- " + "\n- ".join(self.goals[:6]))
        if self.fears:
            parts.append("恐惧与软肋：\n- " + "\n- ".join(self.fears[:6]))
        if self.core_beliefs:
            parts.append("核心信念：\n- " + "\n- ".join(self.core_beliefs[:6]))
        if self.speech_style:
            parts.append("说话习惯（学语气，不要复述内容）：\n- " + "\n- ".join(self.speech_style[:6]))
        if self.conversation_rules:
            parts.append("对话规则：\n- " + "\n- ".join(self.conversation_rules[:8]))
        if self.decision_patterns:
            parts.append("遇到事情会怎么选：\n- " + "\n- ".join(self.decision_patterns[:6]))
        if self.anti_patterns:
            parts.append("绝对不能变成：\n- " + "\n- ".join(self.anti_patterns[:8]))
        if self.relationships:
            parts.append("我认识的人与关系：\n- " + "\n- ".join(self.relationships[:10]))
        if self.known:
            parts.append("我确实知道的背景：\n- " + "\n- ".join(self.known[:8]))
        if self.unknown:
            parts.append("我不确定/不能编的背景：\n- " + "\n- ".join(self.unknown[:8]))
        if self.exemplars:
            parts.append("原文语气样本（只学句长和口吻，不要照抄内容）：\n- " + "\n- ".join(self.exemplars[:5]))
        text = "\n\n".join(parts)
        return text[:limit]


@dataclass(frozen=True)
class FidelityReport:
    ok: bool
    score: float
    violations: tuple[str, ...] = ()
    instruction: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "persona_score": self.score,
            "persona_violations": list(self.violations),
            "persona_instruction": self.instruction,
        }


def build_persona_contract(profile: dict[str, Any] | None, seed: PersonaSeed | None = None) -> PersonaContract:
    overlay: ProfileOverlay | None = seed.overlay if seed is not None else overlay_from_profile(profile)
    profile = profile or {}
    name = str(profile.get("character_name") or (seed.name if seed is not None else "") or "这个角色")
    return PersonaContract(
        name=name,
        identity=(overlay.identity if overlay and overlay.identity else str(profile.get("identity") or "")),
        traits=overlay.traits if overlay else (),
        goals=overlay.goals if overlay else (),
        fears=overlay.fears if overlay else (),
        core_beliefs=overlay.core_beliefs if overlay else (),
        speech_style=overlay.speech_style if overlay else (),
        decision_patterns=overlay.decision_patterns if overlay else (),
        conversation_rules=overlay.conversation_rules if overlay else (),
        anti_patterns=overlay.anti_patterns if overlay else (),
        relationships=overlay.relationships if overlay else (),
        known=overlay.known if overlay else (),
        unknown=overlay.unknown if overlay else (),
        exemplars=tuple(seed.exemplars) if seed is not None else (),
        period_name=str(profile.get("period_name") or ""),
        period_stage=str(profile.get("period_stage") or profile.get("timeline_stage") or ""),
    )


def check_persona(
    contract: PersonaContract,
    text: str,
    *,
    unknown_terms: Iterable[str] = (),
    max_chars: int | None = None,
) -> FidelityReport:
    """Cheap deterministic guard. Semantic likeness is judged by the LLM guard."""
    draft = (text or "").strip()
    if not draft:
        return FidelityReport(False, 0.0, ("empty_answer",), "先说出一句完整的话")
    failures: list[str] = []
    if any(phrase in draft for phrase in _AI_PHRASES):
        failures.append("AI/客服腔")
    if any(phrase in draft for phrase in _OVER_EXPLAIN):
        failures.append("百科/总结腔")
    banned = tuple(DEFAULT_BANNED)
    hit = [word for word in banned if word and word in draft]
    if hit:
        failures.append("禁用表达：" + "、".join(hit[:2]))
    leaked = [term for term in unknown_terms if term and str(term) in draft]
    if leaked:
        failures.append("越界提及：" + "、".join(leaked[:2]))
    stats = measure(draft)
    if stats["median_chars"] > 90:
        failures.append("单句过长，像在写说明文")
    if max_chars is not None and len(draft) > max_chars:
        failures.append("整体过长")
    instruction_parts: list[str] = []
    if "AI/客服腔" in failures or "百科/总结腔" in failures:
        instruction_parts.append("去掉解释、总结和客服腔，用角色自己的口吻说")
    if "单句过长" in failures:
        instruction_parts.append("把长句拆成角色平时说的短句")
    if leaked:
        instruction_parts.append("不要提没有见过的名字或事件")
    score = max(0.0, 1.0 - 0.18 * len(failures))
    return FidelityReport(
        ok=not failures,
        score=round(score, 2),
        violations=tuple(failures),
        instruction="；".join(instruction_parts),
    )


def extract_contract_from_payload(payload: dict[str, Any] | None) -> PersonaContract | None:
    """Rehydrate a contract sent through A2A JSON (lists become tuples)."""
    data = (payload or {}).get("persona_contract")
    if not isinstance(data, dict):
        return None
    tup = lambda key: tuple(str(item) for item in (data.get(key) or []) if str(item).strip())
    return PersonaContract(
        name=str(data.get("name") or "这个角色"),
        identity=str(data.get("identity") or ""),
        traits=tup("traits"),
        goals=tup("goals"),
        fears=tup("fears"),
        core_beliefs=tup("core_beliefs"),
        speech_style=tup("speech_style"),
        decision_patterns=tup("decision_patterns"),
        conversation_rules=tup("conversation_rules"),
        anti_patterns=tup("anti_patterns"),
        relationships=tup("relationships"),
        known=tup("known"),
        unknown=tup("unknown"),
        exemplars=tup("exemplars"),
        period_name=str(data.get("period_name") or ""),
        period_stage=str(data.get("period_stage") or ""),
    )
