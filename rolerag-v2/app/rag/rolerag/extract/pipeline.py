"""Offline construction pipeline: text -> chapters -> scenes -> entities ->
aliases -> events -> visibility -> facts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..models import Entity, Fact, Scene, Visibility
from ..store import InMemoryGraphStore
from .aliases import Arbiter, EntityGroup, Vector, normalize_candidates
from .chapters import split_chapters
from .entities import collect_candidates
from .events import extract_events
from .scenes import build_scenes
from .visibility import grant_event_visibility, grant_fact_visibility


@dataclass
class BuildResult:
    novel_id: str
    chapters: int = 0
    scenes: int = 0
    entities: int = 0
    events: int = 0
    facts: int = 0
    visibility_rows: int = 0
    alias_groups: list[EntityGroup] = field(default_factory=list)


def build_graph(
    text: str,
    store: InMemoryGraphStore,
    *,
    novel_id: str,
    hints: list[dict] | None = None,
    org_members: dict[str, set[str]] | None = None,
    arbiter: Arbiter | None = None,
    embed: Callable[[str], Vector] | None = None,
    fact_llm=None,
) -> BuildResult:
    chapters = split_chapters(text)
    for chapter in chapters:
        store.add_chapter(chapter)
    candidates = collect_candidates(chapters, hints=hints)
    groups = normalize_candidates(candidates, arbiter=arbiter, embed=embed)

    for group in groups:
        store.add_entity(
            Entity(
                id=group.entity_id,
                name=group.canonical,
                type=group.type,
                aliases=group.aliases,
                description=group.description,
                first_chapter=group.first_chapter,
                last_chapter=group.last_chapter,
                mention_count=group.mention_count,
            )
        )

    scenes = build_scenes(chapters, store, novel_id=novel_id)
    for scene in scenes:
        store.add_scene(scene)

    scenes_by_id: dict[str, Scene] = {scene.id: scene for scene in scenes}
    events = []
    for scene in scenes:
        events.extend(extract_events(scene, store, novel_id=novel_id))
    for event in events:
        store.add_event(event)

    name_to_id = {group.canonical: group.entity_id for group in groups}
    for group in groups:
        for alias in group.aliases:
            name_to_id.setdefault(alias, group.entity_id)
    org_map = {
        org: {name_to_id.get(member, member) for member in members}
        for org, members in (org_members or {}).items()
    }

    rows: list[Visibility] = grant_event_visibility(
        store, events, scenes_by_id, org_members=org_map
    )
    for row in rows:
        store.add_visibility(row)

    facts = 0
    for event in events:
        for effect in event.effects:
            fact = Fact(
                id=f"{novel_id}:f{event.id.split(':')[-1]}",
                novel_id=novel_id,
                source_id=effect.subject_id,
                target_id=effect.target_id,
                kind=effect.kind,
                sign=effect.sign,
                weight=abs(effect.delta),
                valid_from=event.chapter,
                cause=event.cause,
                caused_by_event=event.id,
                confidence=0.6 if event.source == "novel" else 0.5,
            )
            store.add_fact(fact)
            for row in grant_fact_visibility(rows, event_id=event.id, fact_id=fact.id):
                store.add_visibility(row)
            facts += 1

    if fact_llm is not None:
        from .llm_facts import extract_llm_facts

        for fact in extract_llm_facts(events, store, fact_llm):
            rows_for_fact = [row for row in rows if row.event_id == fact.caused_by_event]
            for row in grant_fact_visibility(rows_for_fact, event_id=fact.caused_by_event or "", fact_id=fact.id):
                store.add_visibility(row)
            facts += 1

    return BuildResult(
        novel_id=novel_id,
        chapters=len(chapters),
        scenes=len(scenes),
        entities=len(groups),
        events=len(events),
        facts=facts,
        visibility_rows=store.count_visibility(),
        alias_groups=groups,
    )
