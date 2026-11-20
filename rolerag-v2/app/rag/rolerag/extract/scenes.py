"""Scene segmentation and presence roster.

A chapter is too coarse to be a memory unit: an event happens in a room with
three people in it. Scenes are the unit that events, rosters and visibility
all hang from.
"""

from __future__ import annotations

import re

from ..models import Chapter, RosterEntry, Scene
from ..store import InMemoryGraphStore

_SENTENCE = re.compile(r"[^。！？!?]+[。！？!?]?[”」』]?")


def split_sentences(text: str) -> list[str]:
    """Keep the closing quote attached: ``他救过你。”`` is one sentence.

    A lookbehind split would strand the closing quote at the head of the next
    sentence, which silently breaks speaker attribution for every quoted line.
    """
    return [match.group(0).strip() for match in _SENTENCE.finditer(text or "") if match.group(0).strip()]


_SPEECH = re.compile(
    r"(?P<name>[\u4e00-\u9fa5]{2,5})"
    r"(?:道|说道|低声说|开口|问|答|笑|叹|怒道|喝道)"
    r"[：:，,]?\s*[“\"]"
)
_REFERENCE = re.compile(r"(提起|说到|想起|听说|传闻|据说)")


def build_scenes(
    chapters: list[Chapter],
    store: InMemoryGraphStore,
    *,
    novel_id: str,
    max_paragraphs: int = 5,
) -> list[Scene]:
    scenes: list[Scene] = []
    for chapter in chapters:
        paragraphs = [line.strip() for line in chapter.text.splitlines() if line.strip()]
        if not paragraphs:
            continue
        for group_index, group in enumerate(_group(paragraphs, max_paragraphs), start=1):
            text = "\n".join(group)
            title = _title(text)
            roster = build_roster(text, store)
            location = _location(text, store)
            scenes.append(
                Scene(
                    id=f"{novel_id}:s{chapter.ordinal:03d}.{group_index:02d}",
                    novel_id=novel_id,
                    chapter=chapter.ordinal,
                    index=group_index,
                    title=title,
                    text=text,
                    location=location,
                    atmosphere=_atmosphere(text),
                    roster=tuple(roster),
                )
            )
    return scenes


def _group(paragraphs: list[str], size: int) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    for paragraph in paragraphs:
        current.append(paragraph)
        # A long dialogue exchange closes a dramatic beat even if short.
        if len(current) >= size or (len(current) >= 2 and _dialogue_ratio(current) > 0.6):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _dialogue_ratio(paragraphs: list[str]) -> float:
    dialogue = sum(1 for p in paragraphs if "“" in p or '"' in p)
    return dialogue / max(1, len(paragraphs))


def _title(text: str) -> str:
    first = split_sentences(text)[0] if text else ""
    first = re.sub(r"[“”\"\n]", "", first).strip()
    return first[:24] or "无名场景"


def _location(text: str, store: InMemoryGraphStore) -> str:
    places = [e for e in store.entities() if e.type == "place" and e.name in text]
    return places[0].name if places else ""


def _atmosphere(text: str) -> str:
    tone = []
    for word, label in (("血", "肃杀"), ("雨", "阴冷"), ("笑", "松弛"), ("夜", "沉郁"), ("雪", "清寒")):
        if word in text:
            tone.append(label)
    return "、".join(tone[:2])


def build_roster(text: str, store: InMemoryGraphStore) -> list[RosterEntry]:
    mentions = store.scan(text)
    seen: dict[str, RosterEntry] = {}
    for entity_id, position, _surface in mentions:
        if entity_id in seen and seen[entity_id].presence == "active":
            continue
        window_before = text[max(0, position - 8) : position]
        window_after = text[position : position + 10]
        if _REFERENCE.search(window_before):
            presence = "referenced"
        elif _SPEECH.match(text[position : position + 12]) or re.match(r"[\u4e00-\u9fa5]{2,4}(道|说|问|答)[：:]", window_after):
            presence = "active"
        else:
            presence = "silent"
        # active beats silent beats referenced
        rank = {"active": 2, "silent": 1, "referenced": 0}
        if entity_id not in seen or rank[presence] > rank[seen[entity_id].presence]:
            seen[entity_id] = RosterEntry(entity_id=entity_id, presence=presence)
    return list(seen.values())
