"""Affect state machine.

Six scalars, deterministic updates. The LLM may decide *whether* something
lands, never *how much*: the magnitude comes from a rule table, so the same
conversation replayed twice produces the same trajectory.
"""

from __future__ import annotations

from ..models import State

FIELDS = ("alertness", "fatigue", "indebtedness", "shame", "interest", "hostility")

BASELINE = {
    "alertness": 0.5,
    "fatigue": 0.3,
    "indebtedness": 0.0,
    "shame": 0.0,
    "interest": 0.5,
    "hostility": 0.1,
}

# keyword -> (field, delta)
TRIGGERS: dict[str, tuple[str, float]] = {
    "骗子": ("hostility", 0.18),
    "懦夫": ("hostility", 0.15),
    "废物": ("hostility", 0.15),
    "你算什么": ("hostility", 0.12),
    "闭嘴": ("hostility", 0.10),
    "欠": ("indebtedness", 0.12),
    "还你": ("indebtedness", 0.10),
    "对不起": ("shame", 0.10),
    "我错了": ("shame", 0.12),
    "谢谢": ("interest", 0.08),
    "救我": ("indebtedness", 0.10),
    "杀": ("alertness", 0.15),
    "血": ("alertness", 0.12),
}


def detect_triggers(text: str) -> list[str]:
    return [keyword for keyword in TRIGGERS if keyword in (text or "")]


def apply_deltas(state: State, deltas: dict[str, float]) -> State:
    values = state.as_dict()
    for field, delta in deltas.items():
        if field in values:
            values[field] = values[field] + delta
    return State(character_id=state.character_id, version=state.version + 1, **values).clamped()


def decay_toward_baseline(state: State, rate: float = 0.02) -> State:
    values = state.as_dict()
    for field in FIELDS:
        values[field] = values[field] + (BASELINE[field] - values[field]) * rate
    return State(character_id=state.character_id, version=state.version + 1, **values).clamped()


def deltas_for(triggers: list[str], *, scale: float = 1.0) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for keyword in triggers:
        field, delta = TRIGGERS[keyword]
        deltas[field] = deltas.get(field, 0.0) + delta * scale
    return deltas


def describe(affect: dict[str, float]) -> str:
    """One short clause, never numbers: the prompt must not read like a dashboard."""
    if affect.get("hostility", 0) > 0.55:
        return "绷着，不愿多解释"
    if affect.get("shame", 0) > 0.5:
        return "回避，话变少"
    if affect.get("fatigue", 0) > 0.65:
        return "倦，能省一句是一句"
    if affect.get("interest", 0) > 0.65:
        return "愿意多说两句"
    return "克制，按平日的分寸"
