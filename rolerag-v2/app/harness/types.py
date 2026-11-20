"""Data structures for a persistent role subject and one bounded turn.

The subject owns experiences and decisions; RoleRAG owns world evidence and
Nuwa owns identity.  Nothing in this module writes ordinary chat into the
shared novel graph.
"""

from __future__ import annotations

import copy
import hashlib
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Experience:
    """Something the subject understood, decided and actually did."""

    episode_id: str
    turn: int
    event: str
    interpretation: str
    action: str
    decision: str
    answer: str
    emotion: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    salience: float = 0.5
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Experience":
        return cls(
            episode_id=str(data.get("episode_id") or f"episode-{int(data.get('turn') or 0)}"),
            turn=int(data.get("turn") or 0),
            event=str(data.get("event") or "")[:600],
            interpretation=str(data.get("interpretation") or "")[:400],
            action=str(data.get("action") or "natural_reply"),
            decision=str(data.get("decision") or "")[:500],
            answer=str(data.get("answer") or "")[:800],
            emotion=str(data.get("emotion") or "")[:120],
            evidence_ids=[str(item) for item in (data.get("evidence_ids") or [])][:12],
            salience=max(0.0, min(1.0, float(data.get("salience") or 0.5))),
            created_at=float(data.get("created_at") or time.time()),
        )


def _bigrams(text: str) -> set[str]:
    """Small lexical index for episodic recall; no embeddings or model call."""
    result: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", text.lower()):
        if not run.isascii():
            if len(run) == 2:
                result.add(run)
            result.update(run[index:index + 2] for index in range(max(0, len(run) - 1)))
        elif len(run) >= 2:
            result.add(run)
    return {
        item for item in result
        if item not in {"什么", "怎么", "为什么", "这个", "那个", "我们", "你们", "他们", "就是", "还是", "已经", "现在"}
    }


@dataclass
class SubjectState:
    """Continuous, thread-local state that changes after real actions."""

    version: int = 2
    turn_count: int = 0
    current_focus: str = ""
    concerns: list[str] = field(default_factory=list)
    relationship_stance: dict[str, Any] = field(default_factory=lambda: {
        "familiarity": 0.0,
        "openness": 0.0,
        "posture": "仍在观察",
    })
    episodes: list[Experience] = field(default_factory=list)
    last_action: str = ""
    last_emotion: str = ""
    last_decision: dict[str, Any] = field(default_factory=dict)
    affect: dict[str, float] = field(default_factory=dict)
    review_stats: dict[str, Any] = field(default_factory=lambda: {
        "attempts_total": 0,
        "accepted_turns": 0,
        "last_score": None,
    })
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def empty(cls) -> "SubjectState":
        return cls()

    def copy(self) -> "SubjectState":
        return copy.deepcopy(self)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 2,
            "turn_count": self.turn_count,
            "current_focus": self.current_focus,
            "concerns": list(self.concerns),
            "relationship_stance": dict(self.relationship_stance),
            "episodes": [item.as_dict() for item in self.episodes],
            "last_action": self.last_action,
            "last_emotion": self.last_emotion,
            "last_decision": copy.deepcopy(self.last_decision),
            "affect": dict(self.affect),
            "review_stats": dict(self.review_stats),
            "context_snapshot": dict(self.context_snapshot),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SubjectState":
        data = data or {}
        # v1 commitment/open-loop payloads are deliberately not projected into
        # the new prompt or state.  The next save replaces them with v2.
        state = cls(
            turn_count=max(0, int(data.get("turn_count") or 0)),
            current_focus=str(data.get("current_focus") or "")[:300],
            concerns=[str(item)[:160] for item in (data.get("concerns") or []) if str(item).strip()][-8:],
            relationship_stance=dict(data.get("relationship_stance") or {
                "familiarity": 0.0,
                "openness": 0.0,
                "posture": "仍在观察",
            }),
            episodes=[Experience.from_dict(item) for item in (data.get("episodes") or []) if isinstance(item, dict)][-12:],
            last_action=str(data.get("last_action") or ""),
            last_emotion=str(data.get("last_emotion") or "")[:120],
            last_decision=dict(data.get("last_decision") or {}),
            affect=dict(data.get("affect") or {}),
            review_stats=dict(data.get("review_stats") or {}),
            context_snapshot=dict(data.get("context_snapshot") or {}),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )
        stats = {"attempts_total": 0, "accepted_turns": 0, "last_score": None}
        stats.update(state.review_stats)
        state.review_stats = stats
        stance = {"familiarity": 0.0, "openness": 0.0, "posture": "仍在观察"}
        stance.update(state.relationship_stance)
        stance["familiarity"] = max(0.0, min(1.0, float(stance.get("familiarity") or 0.0)))
        stance["openness"] = max(-1.0, min(1.0, float(stance.get("openness") or 0.0)))
        state.relationship_stance = stance
        return state

    def relevant_episodes(self, message: str, *, limit: int = 3) -> list[Experience]:
        if not self.episodes:
            return []
        message_terms = _bigrams(message)
        follow_up = any(token in message for token in ("刚才", "之前", "上次", "那时", "你说过", "你的决定", "改主意", "为什么拒绝"))
        scored: list[tuple[float, int, Experience]] = []
        total = len(self.episodes)
        for index, episode in enumerate(self.episodes):
            episode_text = " ".join((episode.event, episode.interpretation, episode.decision, episode.answer))
            overlap = len(message_terms & _bigrams(episode_text))
            recency = (index + 1) / total
            score = overlap * 3.0 + recency + episode.salience * 0.2
            if follow_up and index == total - 1:
                score += 4.0
            if overlap or (follow_up and index == total - 1):
                scored.append((score, index, episode))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]

    def recent_decisions(self, *, limit: int = 3) -> list[Experience]:
        return [item for item in self.episodes if item.decision or item.action][-limit:]

    def continuity_text(self) -> str:
        lines: list[str] = []
        if self.current_focus:
            lines.append(f"我最近仍在在意：{self.current_focus}")
        if self.concerns:
            lines.append("我的顾虑：" + "；".join(self.concerns[-4:]))
        posture = str(self.relationship_stance.get("posture") or "")
        if posture:
            lines.append(f"我对当前来客：{posture}")
        recent = self.recent_decisions(limit=2)
        if recent:
            lines.append("我最近的选择：")
            lines.extend(f"- 第{item.turn}轮 {item.action}：{item.decision}" for item in recent)
        return "\n".join(lines)

    @property
    def acceptance_rate(self) -> float:
        attempts = int(self.review_stats.get("attempts_total") or 0)
        if attempts <= 0:
            return 0.0
        return float(self.review_stats.get("accepted_turns") or 0) / attempts

    def record_experience(
        self,
        *,
        event: str,
        understanding: dict[str, Any],
        decision: dict[str, Any],
        answer: str,
        accepted: bool,
        score: float | None,
        attempts: int,
        evidence_ids: list[str] | None = None,
    ) -> "SubjectState":
        state = self.copy()
        state.turn_count += 1
        turn = state.turn_count
        interpretation = str(understanding.get("interpretation") or understanding.get("stakes") or "")
        decision_text = str(decision.get("decision_reason") or decision.get("goal") or decision.get("stance") or "")
        digest = hashlib.sha1(f"{turn}|{event}|{answer}".encode("utf-8")).hexdigest()[:10]
        action = str(decision.get("action") or "natural_reply")
        emotion = str(understanding.get("emotional_register") or "")
        salience = 0.85 if action in {"hold_boundary", "comfort", "probe"} else 0.55
        episode = Experience(
            episode_id=f"episode-{turn}-{digest}",
            turn=turn,
            event=event[:600],
            interpretation=interpretation[:400],
            action=action,
            decision=decision_text[:500],
            answer=answer[:800],
            emotion=emotion[:120],
            evidence_ids=list(evidence_ids or [])[:12],
            salience=salience,
        )
        state.episodes = [*state.episodes, episode][-12:]
        state.current_focus = str(
            decision.get("goal") or understanding.get("stakes") or state.current_focus
        )[:300]
        touches = [str(item)[:160] for item in (understanding.get("touches") or []) if str(item).strip()]
        if emotion:
            touches.append(emotion[:160])
        state.concerns = list(dict.fromkeys([*state.concerns, *touches]))[-8:]
        state.last_action = action
        state.last_emotion = emotion
        state.last_decision = copy.deepcopy(decision)

        stance = state.relationship_stance
        familiarity = min(1.0, float(stance.get("familiarity") or 0.0) + 0.05)
        openness = float(stance.get("openness") or 0.0)
        if action == "comfort":
            openness += 0.06
        elif action in {"answer", "natural_reply"}:
            openness += 0.025
        elif action == "hold_boundary":
            openness -= 0.045
        elif action in {"probe", "uncertain"}:
            openness -= 0.005
        openness = max(-1.0, min(1.0, openness))
        if openness <= -0.15:
            posture = "谨慎设防"
        elif familiarity < 0.15:
            posture = "仍在观察"
        elif openness >= 0.18:
            posture = "愿意多说一点"
        else:
            posture = "保持分寸"
        state.relationship_stance = {
            "familiarity": round(familiarity, 3),
            "openness": round(openness, 3),
            "posture": posture,
        }
        state.review_stats["attempts_total"] = int(state.review_stats.get("attempts_total") or 0) + attempts
        state.review_stats["accepted_turns"] = int(state.review_stats.get("accepted_turns") or 0) + int(accepted)
        state.review_stats["last_score"] = score
        state.updated_at = time.time()
        return state


# Existing stores and orchestration use this name while the persisted meaning
# has moved from promise tracking to subject continuity.
InteractionState = SubjectState


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReviewLoopResult:
    accepted: bool
    final_answer: str
    best_answer: str
    best_score: float
    attempts: int
    stop_reason: str
    reviews: list[dict[str, Any]] = field(default_factory=list)
    phase_history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnScope:
    novel_id: str
    owner_id: int
    character_id: int | None
    period_id: int | None
    thread_id: str | None
    user_id: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TurnScope":
        thread = payload.get("thread") or {}
        thread_value = thread.get("id") if isinstance(thread, dict) else thread
        thread_value = thread_value or payload.get("thread_id")
        owner_id = int(payload.get("owner_id") or 0)
        return cls(
            novel_id=str(payload.get("novel_id") or ""),
            owner_id=owner_id,
            character_id=int(payload["character_id"]) if payload.get("character_id") is not None else None,
            period_id=int(payload["period_id"]) if payload.get("period_id") is not None else None,
            thread_id=str(thread_value) if thread_value is not None else None,
            user_id=int(payload.get("user_id") or owner_id),
        )

    @property
    def state_key(self) -> str:
        return "|".join(str(item) for item in (
            self.novel_id,
            self.owner_id,
            self.character_id,
            self.period_id,
            self.thread_id,
            self.user_id,
        ))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnBudget:
    max_tokens: int = 6000
    max_wall_time_ms: int = 25000
    max_model_calls: int = 3
    max_retrieve_calls: int = 5
    max_context_tokens: int = 3200
    max_review_attempts: int = 1
    deadline_ms: int = 25000

    @classmethod
    def for_mode(cls, mode: str) -> "TurnBudget":
        if mode == "deep":
            return cls(
                max_tokens=16000,
                max_wall_time_ms=120000,
                max_model_calls=8,
                max_retrieve_calls=8,
                max_context_tokens=6000,
                max_review_attempts=3,
                deadline_ms=120000,
            )
        return cls()
