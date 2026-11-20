"""Visibility assignment.

Five routes, following REVERIEMEM plus a ``told`` channel for dialogue:

    direct   — the character was the actor or the patient
    witness  — present in the scene (active or silent)
    org      — one hop through an organisation membership
    common   — world-level public knowledge
    told     — explicitly informed inside the text

The org route is what lets "the whole sect knows, he does not" be expressible.
"""

from __future__ import annotations

import re

from ..models import Event, Scene, Visibility
from ..store import InMemoryGraphStore

PUBLIC_MARKERS = ("公告", "众人", "天下", "当着", "传遍", "众弟子", "满城", "世人")
SECRET_MARKERS = ("密谋", "私下", "暗中", "悄悄", "隐瞒", "瞒")
_TOLD = re.compile(r"(告诉|告知|听说|听闻|来信|传信|转告)")


def grant_event_visibility(
    store: InMemoryGraphStore,
    events: list[Event],
    scenes: dict[str, Scene],
    *,
    org_members: dict[str, set[str]] | None = None,
    characters: list[str] | None = None,
) -> list[Visibility]:
    org_members = org_members or {}
    characters = characters or [e.id for e in store.entities() if e.type == "character"]
    rows: list[Visibility] = []

    for event in events:
        scene = scenes.get(event.scene_id)
        covered: set[str] = set()

        for participant in event.participants:
            if participant.role in {"actor", "patient"}:
                rows.append(_row(participant.entity_id, event, "direct", 1.0))
                covered.add(participant.entity_id)
            elif participant.presence in {"active", "silent"}:
                rows.append(_row(participant.entity_id, event, "witness", 0.9))
                covered.add(participant.entity_id)

        if scene:
            text = f"{event.title}{event.summary}{scene.text[:200]}"
            if any(marker in text for marker in PUBLIC_MARKERS):
                for character in characters:
                    rows.append(_row(character, event, "common", 0.8))
                covered = set(characters)
            target = _told_target(text, store)
            if target:
                # A listener is "told", not a generic witness.
                rows = [
                    row
                    for row in rows
                    if not (row.character_id == target and row.event_id == event.id)
                ]
                rows.append(_row(target, event, "told", 0.85))
                covered.add(target)

        secret = _is_secret(event)
        if not secret:
            for character in list(covered):
                for org, members in org_members.items():
                    if character in members:
                        for peer in members - {character}:
                            if peer not in covered:
                                rows.append(_row(peer, event, "org", 0.7))
                                covered.add(peer)

    return _dedupe(rows)


def grant_fact_visibility(event_rows: list[Visibility], *, event_id: str, fact_id: str) -> list[Visibility]:
    """A relation inherits the visibility of the event that caused it."""
    return [
        Visibility(
            character_id=row.character_id,
            event_id=None,
            fact_id=fact_id,
            route=row.route,
            from_chapter=row.from_chapter,
            certainty=row.certainty,
        )
        for row in event_rows
        if row.event_id == event_id
    ]


def _row(character_id: str, event: Event, route: str, certainty: float) -> Visibility:
    return Visibility(
        character_id=character_id,
        event_id=event.id,
        route=route,  # type: ignore[arg-type]
        from_chapter=event.chapter,
        certainty=certainty,
    )


def _is_secret(event: Event) -> bool:
    text = f"{event.title}{event.summary}"
    return any(marker in text for marker in SECRET_MARKERS)


def _told_target(text: str, store: InMemoryGraphStore) -> str | None:
    match = _TOLD.search(text)
    if not match:
        return None
    tail = text[match.end() : match.end() + 12]
    for entity_id, _position, _surface in store.scan(tail):
        return entity_id
    return None


def _dedupe(rows: list[Visibility]) -> list[Visibility]:
    """Keep the strongest route per (character, event)."""
    strength = {"direct": 5, "told": 4, "witness": 3, "common": 2, "org": 1}
    best: dict[tuple[str, str], Visibility] = {}
    for row in rows:
        key = (row.character_id, row.event_id or row.fact_id or "")
        if key not in best or strength[row.route] > strength[best[key].route]:
            best[key] = row
    return list(best.values())
