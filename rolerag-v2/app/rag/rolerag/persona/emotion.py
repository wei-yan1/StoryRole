"""EMO-GATE: decide whether this turn is an emotional jump.

The gate does not invent an emotion from nothing. It compares the previous
emotion transition with cues in the current message; a jump selects a different
behaviour pattern, no jump keeps the previous register (emotional inertia).
"""

from __future__ import annotations

from ..models import CognitionState, Pattern

_CUES: dict[str, tuple[str, ...]] = {
    "怒": ("骗子", "废物", "闭嘴", "滚", "恨", "你算什么"),
    "悲": ("死", "走了", "离开", "对不起", "没了"),
    "惧": ("杀", "血", "怕", "逃"),
    "喜": ("笑", "谢谢", "好的", "答应"),
}


def gate(state: CognitionState, message: str) -> tuple[str, bool]:
    previous = state.emotion.emotion if state.emotion else "静"
    for emotion, cues in _CUES.items():
        if any(cue in (message or "") for cue in cues):
            return emotion, emotion != previous
    return previous, False


def select_pattern(patterns: list[Pattern], emotion: str) -> Pattern | None:
    for pattern in patterns:
        if emotion in pattern.tags:
            return pattern
    return patterns[0] if patterns else None
