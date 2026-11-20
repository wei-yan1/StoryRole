"""Event extraction.

Events are the only legal source of relation changes. A sentence becomes an
event if it contains a trigger verb; the actor is the nearest entity before the
verb, the patient the nearest after it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Effect, Event, Participant, Scene
from ..store import InMemoryGraphStore
from .scenes import split_sentences


@dataclass(frozen=True)
class Trigger:
    kind: str
    sign: int
    delta: float
    strength: float


TRIGGERS: dict[str, Trigger] = {
    "杀": Trigger("敌对", -1, -0.45, 0.9),
    "斩": Trigger("敌对", -1, -0.45, 0.9),
    "刺": Trigger("敌对", -1, -0.4, 0.8),
    "背叛": Trigger("信任", -1, -0.4, 0.85),
    "骗": Trigger("信任", -1, -0.3, 0.7),
    "隐瞒": Trigger("信任", -1, -0.3, 0.75),
    "逐": Trigger("归属", -1, -0.35, 0.8),
    "辱": Trigger("尊重", -1, -0.25, 0.6),
    "救": Trigger("恩情", 1, 0.35, 0.8),
    "护": Trigger("亲近", 1, 0.2, 0.6),
    "拜": Trigger("师徒", 1, 0.4, 0.8),
    "许诺": Trigger("承诺", 1, 0.3, 0.7),
    "原谅": Trigger("信任", 1, 0.3, 0.7),
}

_CAUSE = re.compile(r"(因为|因|由于|为着|为了)")
_MAX_EVENTS_PER_SCENE = 5

# A substring match is not a predicate. "杀气" is an atmosphere, "讽刺" is
# speech, "刺激" is perception; treating them as relation changes is exactly
# how a live character came to accuse 史强 of trying to kill 罗辑.
_TRIGGER_EXCLUDES: dict[str, tuple[str, ...]] = {
    "杀": ("杀气", "杀意", "杀机", "自杀", "厮杀", "杀青", "杀价"),
    "斩": ("斩获", "斩草", "斩首示众"),
    "刺": ("讽刺", "刺激", "刺眼", "刺耳", "刺骨", "刺探"),
    "骗": ("骗局", "骗术"),
    "逐": ("逐字", "逐条", "逐月", "逐年"),
    "辱": ("辱骂",),
    "护": ("护照", "护栏", "护航"),
    "拜": ("拜年", "拜读", "拜金"),
}


def extract_events(scene: Scene, store: InMemoryGraphStore, *, novel_id: str) -> list[Event]:
    events: list[Event] = []
    for sentence in split_sentences(scene.text):
        match = _find_trigger(sentence)
        if not match:
            continue
        verb_position, verb, trigger = match
        if _inside_quote(sentence, verb_position):
            # "他救过你" inside quotation marks is a claim, not a rescue.
            continue
        mentions = store.scan(sentence)
        actor = _nearest(mentions, verb_position, before=True)
        patient = _nearest(mentions, verb_position, before=False)
        participants: list[Participant] = []
        if actor:
            participants.append(Participant(entity_id=actor, role="actor", presence="active"))
        if patient and patient != actor:
            participants.append(Participant(entity_id=patient, role="patient", presence="active"))
        for entity_id in sorted({mention[0] for mention in mentions} - {actor, patient}):
            # Witnesses come from the sentence that describes the act, not from
            # the whole scene: a paragraph-grouped "scene" is not a room, and
            # treating it as one leaks secrets to everyone in the chapter.
            participants.append(
                Participant(entity_id=entity_id, role="witness", presence="silent")
            )

        effects: list[Effect] = []
        if actor and patient and actor != patient:
            effects.append(
                Effect(
                    subject_id=actor,
                    target_id=patient,
                    kind=trigger.kind,
                    sign=trigger.sign,
                    delta=trigger.delta,
                    reason=sentence[:60],
                )
            )

        importance = min(1.0, 0.35 + 0.12 * len(participants) + (0.2 if trigger.strength >= 0.8 else 0.0))
        events.append(
            Event(
                id=f"{novel_id}:e{scene.chapter:03d}.{scene.index:02d}.{len(events) + 1:02d}",
                novel_id=novel_id,
                scene_id=scene.id,
                chapter=scene.chapter,
                title=_title(sentence, store, actor, patient, verb),
                summary=sentence[:100],
                importance=round(importance, 2),
                cause=_cause(sentence),
                participants=tuple(participants),
                effects=tuple(effects),
                source="novel",
            )
        )
        if len(events) >= _MAX_EVENTS_PER_SCENE:
            break

    if not events:
        # Keep the scene addressable ("do you remember that day") even when no
        # relation changed in it.
        events.append(
            Event(
                id=f"{novel_id}:e{scene.chapter:03d}.{scene.index:02d}.00",
                novel_id=novel_id,
                scene_id=scene.id,
                chapter=scene.chapter,
                title=scene.title,
                summary=scene.text[:100],
                importance=0.25,
                participants=tuple(
                    Participant(entity_id=entry.entity_id, role="witness", presence=entry.presence)
                    for entry in scene.roster
                ),
                source="novel",
            )
        )
    return events


def _find_trigger(sentence: str) -> tuple[int, str, Trigger] | None:
    candidates: list[tuple[int, str, Trigger]] = []
    for verb, trigger in TRIGGERS.items():
        start = 0
        while True:
            position = sentence.find(verb, start)
            if position < 0:
                break
            window = sentence[max(0, position - 2) : position + len(verb) + 2]
            if not any(phrase in window for phrase in _TRIGGER_EXCLUDES.get(verb, ())):
                candidates.append((position, verb, trigger))
                break
            start = position + len(verb)
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])


def _inside_quote(sentence: str, position: int) -> bool:
    opening = sentence.rfind("“", 0, position + 1)
    closing = sentence.rfind("”", 0, position + 1)
    return opening > closing


def _nearest(mentions: list[tuple[str, int, str]], position: int, *, before: bool) -> str | None:
    candidates = [(abs(pos - position), entity_id) for entity_id, pos, _ in mentions
                  if (pos < position if before else pos > position)]
    if not candidates:
        return None
    return min(candidates)[1]


def _cause(sentence: str) -> str:
    if _CAUSE.search(sentence):
        return sentence[:80]
    return ""


def _title(sentence: str, store: InMemoryGraphStore, actor: str | None, patient: str | None, verb: str) -> str:
    if actor and patient:
        return f"{store.entity_name(actor)}{verb}{store.entity_name(patient)}"
    cleaned = re.sub(r"[“”\"\n]", "", sentence).strip()
    return cleaned[:24] or "未命名事件"
