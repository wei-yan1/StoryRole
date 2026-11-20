"""JSON snapshot: the persistence contract used by tests and offline demos.

PostgreSQL stores the same shapes; this module proves the graph survives a
round-trip without any database at all.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import (
    Belief,
    Chapter,
    Effect,
    EmotionTurn,
    Entity,
    Event,
    Fact,
    Participant,
    Pattern,
    RosterEntry,
    Scene,
    State,
    Visibility,
)
from .store import InMemoryGraphStore


def dump(store: InMemoryGraphStore) -> dict:
    return {
        "novel_id": store.novel_id,
        "chapters": [asdict(row) for row in store.chapters()],
        "entities": [asdict(row) for row in store.entities()],
        "scenes": [asdict(row) for row in store.scenes()],
        "events": [asdict(row) for row in store.events()],
        "facts": [asdict(row) for row in store.facts()],
        "visibility": [
            asdict(row)
            for character in [entity.id for entity in store.entities()]
            for row in store.visibility(character)
        ],
        "beliefs": [
            asdict(row)
            for character in [entity.id for entity in store.entities()]
            for row in store.beliefs(character)
        ],
        "patterns": [
            asdict(row)
            for character in [entity.id for entity in store.entities()]
            for row in store.patterns(character)
        ],
        "emotions": [
            asdict(row)
            for character in [entity.id for entity in store.entities()]
            for row in store.emotions(character)
        ],
        "states": [asdict(store.state(entity.id)) for entity in store.entities()],
    }


def save(store: InMemoryGraphStore, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dump(store), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load(path: str | Path) -> InMemoryGraphStore:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    store = InMemoryGraphStore(payload["novel_id"])
    for row in payload.get("chapters", []):
        store.add_chapter(Chapter(**row))
    for row in payload["entities"]:
        row["aliases"] = tuple(row["aliases"])
        store.add_entity(Entity(**row))
    for row in payload["scenes"]:
        row["roster"] = tuple(RosterEntry(**entry) for entry in row["roster"])
        store.add_scene(Scene(**row))
    for row in payload["events"]:
        row["participants"] = tuple(Participant(**entry) for entry in row["participants"])
        row["effects"] = tuple(Effect(**entry) for entry in row["effects"])
        store.add_event(Event(**row))
    for row in payload["facts"]:
        store.add_fact(Fact(**row))
    for row in payload["visibility"]:
        store.add_visibility(Visibility(**row))
    for row in payload["beliefs"]:
        store.add_belief(Belief(**row))
    for row in payload["patterns"]:
        row["excerpts"] = tuple(row["excerpts"])
        row["tags"] = tuple(row["tags"])
        row["centroid"] = tuple(row["centroid"])
        store.add_pattern(Pattern(**row))
    for row in payload["emotions"]:
        store.add_emotion(EmotionTurn(**row))
    for row in payload["states"]:
        store.set_state(State(**row))
    return store


__all__ = ["dump", "save", "load"]
