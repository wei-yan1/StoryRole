"""Explicit context assembly for one role-subject turn."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContextSection:
    name: str
    purpose: str
    priority: int
    lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContextSnapshot:
    identity_digest: str
    subject_digest: str
    decision_digest: str
    constraints_digest: str
    estimated_tokens: int
    trimmed: bool
    included_sections: list[str]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ContextSnapshot":
        data = data or {}
        return cls(
            identity_digest=str(data.get("identity_digest") or ""),
            subject_digest=str(data.get("subject_digest") or ""),
            decision_digest=str(data.get("decision_digest") or ""),
            constraints_digest=str(data.get("constraints_digest") or ""),
            estimated_tokens=int(data.get("estimated_tokens") or 0),
            trimmed=bool(data.get("trimmed")),
            included_sections=list(data.get("included_sections") or []),
            created_at=float(data.get("created_at") or 0),
        )


@dataclass
class ContextManifest:
    sections: list[ContextSection]
    estimated_tokens: int
    dropped_lines: int
    trimmed: bool
    snapshot: ContextSnapshot
    budget_trimmed: bool = False

    def render_for_prompt(self) -> str:
        names = {
            "identity": "身份｜我是谁",
            "self_state": "连续自我｜我最近在意什么、做过什么",
            "situation": "处境｜我怎样理解这件事",
            "decision": "行动｜本轮我选择怎样回应",
            "memory": "回忆｜本轮实际取回的材料与来源",
            "history": "历史｜当前话题之前的来往",
            "constraints": "约束｜不能越过的边界",
        }
        blocks = []
        for section in self.sections:
            if section.lines:
                blocks.append(f"[{names.get(section.name, section.name)}]\n" + "\n".join(section.lines))
        return "\n\n".join(blocks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sections": [item.as_dict() for item in self.sections],
            "estimated_tokens": self.estimated_tokens,
            "dropped_lines": self.dropped_lines,
            "trimmed": self.trimmed,
            "snapshot": self.snapshot.as_dict(),
            "budget_trimmed": self.budget_trimmed,
        }


def _estimate(lines: list[str]) -> int:
    return max(1, sum(len(item) for item in lines) // 2)


def _digest(lines: list[str], limit: int = 600) -> str:
    return "\n".join(lines)[:limit]


def _evidence_lines(role_context: dict[str, Any], evidence: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    cutoff = role_context.get("cutoff")
    if cutoff is not None:
        lines.append(f"可见范围：cutoff={cutoff}；只取当前时期可见材料。")
    route = role_context.get("route")
    if route:
        lines.append(f"回忆路径：{route}；{role_context.get('route_reason', '')}")
    ego = str(role_context.get("ego_summary") or "").strip()
    if ego:
        lines.append(ego[:600])
    for index, item in enumerate(evidence[:12], start=1):
        source = item.get("source") or item.get("chapter") or "unknown"
        chunk = item.get("chunk_id") or item.get("id") or f"e{index}"
        kind = item.get("kind") or "evidence"
        text = str(item.get("text") or item.get("summary") or "").strip()
        if text:
            lines.append(f"[{chunk} | {kind} | {source}] {text}")
    return lines


def _nested(appraisal: Any, key: str) -> dict[str, Any]:
    value = appraisal.get(key) if isinstance(appraisal, dict) else None
    return value if isinstance(value, dict) else {}


def _state_lines(interaction: dict[str, Any], understanding: dict[str, Any]) -> list[str]:
    if not interaction:
        return []
    lines: list[str] = []
    focus = str(interaction.get("current_focus") or "").strip()
    if focus:
        lines.append(f"当前关注：{focus}")
    concerns = [str(item) for item in (interaction.get("concerns") or []) if str(item).strip()]
    if concerns:
        lines.append("当前顾虑：" + "；".join(concerns[-4:]))
    stance = interaction.get("relationship_stance") or {}
    if stance:
        lines.append(
            "我与当前来客："
            f"{stance.get('posture', '仍在观察')}；"
            f"熟悉度={stance.get('familiarity', 0)}，开放度={stance.get('openness', 0)}"
        )
    episodes = [item for item in (interaction.get("episodes") or []) if isinstance(item, dict)]
    selected_ids = set(understanding.get("prior_episode_ids") or [])
    selected = [item for item in episodes if item.get("episode_id") in selected_ids]
    if not selected and episodes and not selected_ids:
        selected = episodes[-1:]
    if selected:
        lines.append("与此刻有关的经历：")
        for item in selected[-3:]:
            lines.append(
                f"- 第{item.get('turn', 0)}轮，对方说：{str(item.get('event') or '')[:100]}；"
                f"我的理解：{str(item.get('interpretation') or '')[:100]}；"
                f"我选择 {item.get('action', '')}：{str(item.get('decision') or '')[:140]}；"
                f"我实际说：{str(item.get('answer') or '')[:160]}"
            )
    return lines


def _situation_lines(appraisal: dict[str, Any]) -> list[str]:
    if not appraisal:
        return []
    understanding = _nested(appraisal, "understanding")
    move = understanding.get("user_move") or appraisal.get("user_move") or ""
    interpretation = understanding.get("interpretation") or appraisal.get("stakes") or ""
    stakes = understanding.get("stakes") or appraisal.get("stakes") or ""
    register = understanding.get("emotional_register") or ""
    memory_reason = understanding.get("memory_reason") or ""
    lines = [f"对方动作：{move}", f"我的理解：{interpretation}", f"我在意的：{stakes}"]
    if register:
        lines.append(f"情绪承接：{register}")
    if memory_reason:
        lines.append(f"回忆动机：{memory_reason}")
    return lines


def _decision_lines(appraisal: dict[str, Any]) -> list[str]:
    if not appraisal:
        return []
    decision = _nested(appraisal, "decision")
    action = decision.get("action") or appraisal.get("action") or "natural_reply"
    lines = [f"行动：{action}"]
    for key, label in (
        ("goal", "目标"),
        ("stance", "立场"),
        ("relationship_posture", "关系姿态"),
        ("change_from_previous", "与此前决定"),
        ("decision_reason", "决定依据"),
        ("uncertainty", "不确定"),
        ("expression_shape", "表达结构"),
    ):
        value = decision.get(key)
        if value:
            lines.append(f"{label}：{value}")
    return lines


def _constraint_lines(
    appraisal: dict[str, Any],
    timeline: dict[str, Any],
    persona_contract: str,
) -> list[str]:
    lines: list[str] = []
    decision = _nested(appraisal, "decision")
    boundaries = decision.get("boundaries") or appraisal.get("boundaries") or []
    must_not = decision.get("must_not") or appraisal.get("must_not") or []
    for item in list(boundaries) + list(must_not):
        text = str(item).strip()
        if text:
            lines.append(f"- {text}")
    if timeline and timeline.get("allowed") is False:
        lines.append("- 当前问题超过可见时期：不剧透、不编造，但仍可选择怎样回应对方")
    if "不能" in persona_contract or "不要" in persona_contract:
        lines.append("- 女娲契约中的反模式与知识边界仍然有效")
    if not lines:
        lines.extend([
            "- 不替自己编造没有来源的经历",
            "- 不让事实正确取代角色自己的价值判断和关系姿态",
        ])
    return lines


def build_context_manifest(
    *,
    persona_contract: str,
    profile: dict[str, Any],
    role_context: dict[str, Any],
    evidence: list[dict[str, Any]],
    interaction_state: dict[str, Any],
    appraisal: dict[str, Any],
    recent_messages: list[dict[str, Any]] | None = None,
    timeline: dict[str, Any] | None = None,
    budget_tokens: int = 3200,
    now: float = 0,
) -> ContextManifest:
    identity_lines = [persona_contract.strip()] if persona_contract.strip() else []
    period = profile.get("period_name") or profile.get("timeline_stage")
    if period:
        identity_lines.append(f"当前时期：{period}")
    novel = profile.get("novel_name")
    if novel:
        identity_lines.append(f"所属作品：{novel}")
    understanding = _nested(appraisal, "understanding")
    decision_data = _nested(appraisal, "decision")
    memory_evidence = evidence
    probe_without_direct_memory = (
        str(role_context.get("route") or "") == "probe"
        and decision_data.get("action") in {"probe", "uncertain"}
    )
    if probe_without_direct_memory:
        memory_evidence = [
            item for item in evidence
            if str(item.get("kind") or "") in {"relation", "relation_gap"}
        ]
    memory_lines = _evidence_lines(role_context, memory_evidence)
    if probe_without_direct_memory:
        memory_lines.append("本轮片段没有直接说明当前问题；不要把它们当成我的相关经历。")
    sections = [
        ContextSection("identity", "稳定自我认识", 0, identity_lines),
        ContextSection("self_state", "持续经历与当前自我状态", 1, _state_lines(interaction_state, understanding)),
        ContextSection("situation", "检索前形成的处境理解", 2, _situation_lines(appraisal)),
        ContextSection("decision", "检索后形成的行动决定", 3, _decision_lines(appraisal)),
        ContextSection("memory", "按回忆需求取得的有来源材料", 4, memory_lines),
        ContextSection(
            "history",
            "当前话题之前的对话",
            5,
            [f"{item.get('role', 'unknown')}: {item.get('content', '')}" for item in (recent_messages or [])[-8:]],
        ),
        ContextSection("constraints", "行动与表达的轻量边界", 6, _constraint_lines(appraisal, timeline or {}, persona_contract)),
    ]

    original_count = sum(len(section.lines) for section in sections)
    max_lines = {
        "identity": 20,
        "self_state": 12,
        "situation": 8,
        "decision": 10,
        "memory": 14,
        "history": 8,
        "constraints": 10,
    }
    for section in sections:
        section.lines = section.lines[:max_lines.get(section.name, 10)]
    all_lines = [line for section in sections for line in section.lines]
    estimated = _estimate(all_lines)
    budget_trimmed = False
    if estimated > budget_tokens:
        # History and recall yield first. The continuous subject, its current
        # interpretation and its chosen action must survive a tight budget.
        for section in sorted(sections, key=lambda item: item.priority, reverse=True):
            while section.lines and estimated > budget_tokens and section.name in {"history", "memory"}:
                removed = section.lines.pop()
                budget_trimmed = True
                estimated = max(1, estimated - _estimate([removed]))

    identity = next(item.lines for item in sections if item.name == "identity")
    state_lines = next(item.lines for item in sections if item.name == "self_state")
    decision_lines = next(item.lines for item in sections if item.name == "decision")
    constraints = next(item.lines for item in sections if item.name == "constraints")
    final_count = sum(len(section.lines) for section in sections)
    snapshot = ContextSnapshot(
        identity_digest=_digest(identity),
        subject_digest=_digest(state_lines),
        decision_digest=_digest(decision_lines),
        constraints_digest=_digest(constraints),
        estimated_tokens=estimated,
        trimmed=final_count < original_count,
        included_sections=[item.name for item in sections if item.lines],
        created_at=now,
    )
    return ContextManifest(
        sections=sections,
        estimated_tokens=estimated,
        dropped_lines=max(0, original_count - final_count),
        trimmed=final_count < original_count,
        snapshot=snapshot,
        budget_trimmed=budget_trimmed,
    )
