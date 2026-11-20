"""Personality patterns and emotion transitions.

A character is not one voice. The same man is different in confrontation,
in deference and in retreat. We cluster his dialogue into K behaviour patterns,
keep canonical excerpts for each, and record the emotion transitions that
select between them at inference time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..extract.scenes import split_sentences
from ..models import EmotionTurn, Pattern, Scene
from ..store import InMemoryGraphStore

_QUOTE = re.compile(r"[“\"]([^”\"]{2,80})[”\"]")
_EMOTION_WORDS = {
    "怒": "怒",
    "恨": "恨",
    "杀": "怒",
    "笑": "喜",
    "喜": "喜",
    "怕": "惧",
    "惧": "惧",
    "悲": "悲",
    "哭": "悲",
    "惊": "惊",
    "愧": "愧",
    "悔": "愧",
    "冷": "静",
    "沉默": "静",
}


@dataclass(frozen=True)
class Utterance:
    chapter: int
    scene_id: str
    text: str
    emotion: str


def collect_utterances(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
) -> list[Utterance]:
    entity = store.entity(character_id)
    if not entity:
        return []
    rows: list[Utterance] = []
    for scene in store.scenes(lte=cutoff):
        roster = {entry.entity_id for entry in scene.roster}
        if character_id not in roster:
            continue
        for sentence in split_sentences(scene.text):
            quote = _QUOTE.search(sentence)
            if not quote:
                continue
            speaker = _speaker(sentence[: quote.start()], store)
            if speaker != character_id:
                continue
            text = quote.group(1).strip()
            if len(text) < 2:
                continue
            rows.append(
                Utterance(
                    chapter=scene.chapter,
                    scene_id=scene.id,
                    text=text,
                    emotion=_emotion(text),
                )
            )
    return rows


def _speaker(before_quote: str, store: InMemoryGraphStore) -> str | None:
    """Who is talking: ``X告诉Y：`` attributes to X, otherwise the last name."""
    mentions = store.scan(before_quote)
    if not mentions:
        return None
    told_at = before_quote.rfind("告诉")
    if told_at >= 0:
        before_told = [mention for mention in mentions if mention[1] < told_at]
        if before_told:
            return max(before_told, key=lambda mention: mention[1])[0]
    return max(mentions, key=lambda mention: mention[1])[0]


def build_patterns(character_id: str, utterances: list[Utterance], *, max_patterns: int = 8) -> list[Pattern]:
    buckets: dict[str, list[Utterance]] = {}
    for utterance in utterances:
        buckets.setdefault(utterance.emotion, []).append(utterance)
    patterns: list[Pattern] = []
    for emotion, rows in sorted(buckets.items(), key=lambda pair: -len(pair[1])):
        if len(rows) < 2:
            continue
        average = sum(len(row.text) for row in rows) / len(rows)
        register = "短句、话少" if average < 12 else "句子偏长、愿意解释"
        excerpts = tuple(row.text for row in sorted(rows, key=lambda r: -len(r.text))[:3])
        patterns.append(
            Pattern(
                id=f"{character_id}:p{len(patterns) + 1}",
                character_id=character_id,
                description=f"{emotion}时的{register}",
                excerpts=excerpts,
                tags=(emotion,),
                centroid=(len(rows), average),
            )
        )
        if len(patterns) >= max_patterns:
            break
    return patterns


def build_emotions(character_id: str, utterances: list[Utterance]) -> list[EmotionTurn]:
    turns: list[EmotionTurn] = []
    previous = None
    for index, utterance in enumerate(utterances):
        if utterance.emotion == previous and len(turns) > 0:
            continue
        previous = utterance.emotion
        turns.append(
            EmotionTurn(
                character_id=character_id,
                emotion=utterance.emotion,
                intensity=0.5,
                trigger=utterance.text[:20],
                intent="",
                chapter=utterance.chapter,
                seq=index,
            )
        )
    return turns


def _emotion(text: str) -> str:
    for word, emotion in _EMOTION_WORDS.items():
        if word in text:
            return emotion
    return "静"


def scenes_for(store: InMemoryGraphStore, character_id: str, cutoff: int) -> list[Scene]:
    return [
        scene
        for scene in store.scenes(lte=cutoff)
        if any(entry.entity_id == character_id for entry in scene.roster)
    ]
