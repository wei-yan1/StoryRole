"""Externalized turn handoff for clean-context continuation.

A long thread should not be carried by the raw transcript. This module turns a
`SubjectState` into the compact handoff the next turn needs: current focus,
concerns, relationship posture, last decision and the few episodes worth
continuing. It is deliberately derived from persisted state, not from a model
summary, so it can be replayed and tested.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.harness.types import Experience, SubjectState


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


@dataclass
class TurnHandoff:
    turn_count: int = 0
    current_focus: str = ""
    concerns: list[str] = field(default_factory=list)
    relationship_stance: dict[str, Any] = field(default_factory=dict)
    last_action: str = ""
    last_emotion: str = ""
    last_decision: dict[str, Any] = field(default_factory=dict)
    recent_episodes: list[dict[str, Any]] = field(default_factory=list)
    boundary_note: str = "只接续主体状态，不携带原始对话全文或生成侧隐藏推理"
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_subject_state(cls, state: SubjectState, *, max_episodes: int = 3) -> "TurnHandoff":
        episodes = [
            {
                "turn": item.turn,
                "event": _clip(item.event, 180),
                "interpretation": _clip(item.interpretation, 160),
                "action": item.action,
                "decision": _clip(item.decision, 200),
                "answer": _clip(item.answer, 220),
                "emotion": _clip(item.emotion, 80),
            }
            for item in state.episodes[-max(1, int(max_episodes)):]
        ]
        return cls(
            turn_count=int(state.turn_count),
            current_focus=_clip(state.current_focus, 240),
            concerns=[_clip(item, 140) for item in state.concerns[-6:]],
            relationship_stance=dict(state.relationship_stance),
            last_action=str(state.last_action or ""),
            last_emotion=_clip(state.last_emotion, 80),
            last_decision=dict(state.last_decision),
            recent_episodes=episodes,
            updated_at=float(state.updated_at or time.time()),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_count": self.turn_count,
            "current_focus": self.current_focus,
            "concerns": list(self.concerns),
            "relationship_stance": dict(self.relationship_stance),
            "last_action": self.last_action,
            "last_emotion": self.last_emotion,
            "last_decision": dict(self.last_decision),
            "recent_episodes": [dict(item) for item in self.recent_episodes],
            "boundary_note": self.boundary_note,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TurnHandoff":
        data = data or {}
        return cls(
            turn_count=max(0, int(data.get("turn_count") or 0)),
            current_focus=_clip(data.get("current_focus"), 240),
            concerns=[_clip(item, 140) for item in (data.get("concerns") or [])][-6:],
            relationship_stance=dict(data.get("relationship_stance") or {}),
            last_action=str(data.get("last_action") or ""),
            last_emotion=_clip(data.get("last_emotion"), 80),
            last_decision=dict(data.get("last_decision") or {}),
            recent_episodes=[
                dict(item) for item in (data.get("recent_episodes") or [])
                if isinstance(item, dict)
            ][-3:],
            boundary_note=str(data.get("boundary_note") or ""),
            updated_at=float(data.get("updated_at") or 0.0),
        )

    def render(self) -> str:
        lines: list[str] = []
        if self.turn_count:
            lines.append(f"已经历回合：{self.turn_count}")
        if self.current_focus:
            lines.append(f"当前关注：{self.current_focus}")
        if self.concerns:
            lines.append("当前顾虑：" + "；".join(self.concerns))
        stance = self.relationship_stance
        if stance:
            lines.append(
                "对当前来客："
                f"{stance.get('posture', '仍在观察')}；"
                f"熟悉度={stance.get('familiarity', 0)}，开放度={stance.get('openness', 0)}"
            )
        if self.last_action:
            lines.append(f"上一轮行动：{self.last_action}")
        if self.last_emotion:
            lines.append(f"上一轮情绪：{self.last_emotion}")
        if self.last_decision:
            decision = _clip(
                self.last_decision.get("decision_reason")
                or self.last_decision.get("goal")
                or self.last_decision.get("stance"),
                220,
            )
            if decision:
                lines.append(f"上一轮决定：{decision}")
        if self.recent_episodes:
            lines.append("需要接续的经历：")
            for item in self.recent_episodes:
                lines.append(
                    f"- 第{item.get('turn', 0)}轮：对方说“{item.get('event', '')}”；"
                    f"我理解为“{item.get('interpretation', '')}”；"
                    f"我选择 {item.get('action', '')}：{item.get('decision', '')}；"
                    f"我实际说“{item.get('answer', '')}”"
                )
        if not lines:
            lines.append("这是这段对话的开始；没有需要接续的旧状态。")
        return "\n".join(lines)

    def merge_into(self, state: SubjectState) -> SubjectState:
        """Attach the handoff-derived fields without overwriting episodes."""
        merged = state.copy()
        merged.current_focus = self.current_focus
        merged.concerns = list(self.concerns)
        merged.relationship_stance = dict(self.relationship_stance)
        merged.last_action = self.last_action
        merged.last_emotion = self.last_emotion
        merged.last_decision = dict(self.last_decision)
        return merged


def recent_episode_ids(state: SubjectState, *, limit: int = 3) -> list[str]:
    return [item.episode_id for item in state.episodes[-limit:]]


def experience_digest(experience: Experience) -> str:
    return f"{experience.turn}:{experience.action}:{experience.decision[:60]}"
