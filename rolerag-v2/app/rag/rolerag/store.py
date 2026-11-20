"""Graph storage.

``GraphStore`` is the seam between the pure algorithm layer and persistence.
The in-memory implementation is what unit tests and the offline demo use; the
PostgreSQL adapter lives in ``pg_store`` and implements the same protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    Belief,
    Chapter,
    EmotionTurn,
    Entity,
    Event,
    Fact,
    Pattern,
    Scene,
    State,
    Visibility,
)


@runtime_checkable
class GraphStore(Protocol):
    novel_id: str

    def entities(self) -> list[Entity]: ...
    def scenes(self, lte: int | None = None) -> list[Scene]: ...
    def events(self, lte: int | None = None) -> list[Event]: ...
    def facts(self, lte: int | None = None) -> list[Fact]: ...
    def visibility(self, character_id: str) -> list[Visibility]: ...
    def beliefs(self, character_id: str, lte: int | None = None) -> list[Belief]: ...
    def patterns(self, character_id: str) -> list[Pattern]: ...
    def emotions(self, character_id: str, lte: int | None = None) -> list[EmotionTurn]: ...
    def state(self, character_id: str) -> State: ...


class InMemoryGraphStore:
    """Small, dependency-free graph store with longest-match surface lookup."""

    def __init__(self, novel_id: str) -> None:
        self.novel_id = novel_id
        self._chapters: dict[int, Chapter] = {}
        self._entities: dict[str, Entity] = {}
        self._scenes: dict[str, Scene] = {}
        self._events: dict[str, Event] = {}
        self._events_by_scene: dict[str, list[Event]] = {}
        self._facts: dict[str, Fact] = {}
        self._visibility: dict[str, list[Visibility]] = {}
        # Visibility is queried per event/fact far more often than it is
        # written. Keeping target-first indexes turns the old O(all visibility
        # rows) scan into O(rows for this target).
        self._visibility_events: dict[tuple[str, str], list[Visibility]] = {}
        self._visibility_facts: dict[tuple[str, str], list[Visibility]] = {}
        self._beliefs: dict[str, list[Belief]] = {}
        self._patterns: dict[str, list[Pattern]] = {}
        self._emotions: dict[str, list[EmotionTurn]] = {}
        self._state: dict[str, State] = {}
        self._surface: dict[str, str] = {}
        self._surface_max = 1
        self.revision = 0

    # ---------------------------------------------------------------- writes
    def _touch(self) -> None:
        self.revision += 1

    def add_chapter(self, chapter: Chapter) -> None:
        self._chapters[chapter.ordinal] = chapter
        self._touch()

    def add_entity(self, entity: Entity) -> None:
        self._entities[entity.id] = entity
        for surface in (entity.name, *entity.aliases):
            if not surface:
                continue
            self._surface[surface] = entity.id
            self._surface_max = max(self._surface_max, len(surface))
        self._touch()

    def add_scene(self, scene: Scene) -> None:
        self._scenes[scene.id] = scene
        self._touch()

    def add_event(self, event: Event) -> None:
        self._events[event.id] = event
        if event.scene_id:
            self._events_by_scene.setdefault(event.scene_id, []).append(event)
        self._touch()

    def add_fact(self, fact: Fact) -> None:
        self._facts[fact.id] = fact
        self._touch()

    def add_visibility(self, row: Visibility) -> None:
        self._visibility.setdefault(row.character_id, []).append(row)
        if row.event_id:
            self._visibility_events.setdefault((row.character_id, row.event_id), []).append(row)
        if row.fact_id:
            self._visibility_facts.setdefault((row.character_id, row.fact_id), []).append(row)
        self._touch()

    def add_belief(self, belief: Belief) -> None:
        self._beliefs.setdefault(belief.character_id, []).append(belief)
        self._touch()

    def add_pattern(self, pattern: Pattern) -> None:
        self._patterns.setdefault(pattern.character_id, []).append(pattern)
        self._touch()

    def add_emotion(self, turn: EmotionTurn) -> None:
        self._emotions.setdefault(turn.character_id, []).append(turn)
        self._touch()

    def set_state(self, state: State) -> None:
        self._state[state.character_id] = state
        self._touch()

    # ---------------------------------------------------------------- reads
    def entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def entity_name(self, entity_id: str) -> str:
        entity = self._entities.get(entity_id)
        return entity.name if entity else entity_id

    def find_entity(self, surface: str) -> Entity | None:
        return self._entities.get(self._surface.get(surface, ""))

    def entities(self) -> list[Entity]:
        return sorted(self._entities.values(), key=lambda e: (-e.mention_count, e.name))

    def chapters(self) -> list[Chapter]:
        return sorted(self._chapters.values(), key=lambda c: c.ordinal)

    def scenes(self, lte: int | None = None) -> list[Scene]:
        rows = sorted(self._scenes.values(), key=lambda s: (s.chapter, s.index))
        return [s for s in rows if lte is None or s.chapter <= lte]

    def events(self, lte: int | None = None) -> list[Event]:
        rows = sorted(self._events.values(), key=lambda e: (e.chapter, e.id))
        return [e for e in rows if lte is None or e.chapter <= lte]

    def events_in_scene(self, scene_id: str, lte: int | None = None) -> list[Event]:
        """Events for one scene; avoids sorting the whole book once per scene."""
        rows = sorted(self._events_by_scene.get(scene_id, []), key=lambda e: (e.chapter, e.id))
        return [e for e in rows if lte is None or e.chapter <= lte]

    def event(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def facts(self, lte: int | None = None) -> list[Fact]:
        rows = sorted(self._facts.values(), key=lambda f: (f.valid_from, f.id))
        if lte is not None:
            rows = [f for f in rows if f.valid_from <= lte]
        return rows

    def visibility(self, character_id: str) -> list[Visibility]:
        return list(self._visibility.get(character_id, []))

    def beliefs(self, character_id: str, lte: int | None = None) -> list[Belief]:
        rows = self._beliefs.get(character_id, [])
        return [b for b in rows if not b.retracted and (lte is None or b.since_chapter <= lte)]

    def patterns(self, character_id: str) -> list[Pattern]:
        return list(self._patterns.get(character_id, []))

    def emotions(self, character_id: str, lte: int | None = None) -> list[EmotionTurn]:
        rows = sorted(self._emotions.get(character_id, []), key=lambda t: (t.chapter, t.seq))
        return [t for t in rows if lte is None or t.chapter <= lte]

    def state(self, character_id: str) -> State:
        return self._state.get(character_id) or State(character_id=character_id)

    # ------------------------------------------------------------ projections
    def _visibility_rows(
        self,
        character_id: str,
        *,
        event_id: str | None,
        fact_id: str | None,
    ) -> list[Visibility]:
        if event_id is not None:
            return self._visibility_events.get((character_id, event_id), [])
        if fact_id is not None:
            return self._visibility_facts.get((character_id, fact_id), [])
        return self._visibility.get(character_id, [])

    def is_visible(
        self,
        character_id: str,
        *,
        event_id: str | None = None,
        fact_id: str | None = None,
        at: int,
    ) -> bool:
        if event_id is None and fact_id is None:
            return False
        return any(
            row.from_chapter <= at
            for row in self._visibility_rows(character_id, event_id=event_id, fact_id=fact_id)
        )

    def best_route(
        self,
        character_id: str,
        *,
        event_id: str | None = None,
        fact_id: str | None = None,
        at: int,
    ) -> Visibility | None:
        """Strongest path by which this character could know the row."""
        if event_id is None and fact_id is None:
            return None
        hits = [
            row
            for row in self._visibility_rows(character_id, event_id=event_id, fact_id=fact_id)
            if row.from_chapter <= at
        ]
        return max(hits, key=lambda row: row.certainty) if hits else None

    def scan(self, text: str) -> list[tuple[str, int, str]]:
        found: list[tuple[str, int, str]] = []
        index = 0
        length = len(text)
        while index < length:
            matched = False
            upper = min(self._surface_max, length - index)
            for size in range(upper, 0, -1):
                piece = text[index : index + size]
                entity_id = self._surface.get(piece)
                if entity_id:
                    found.append((entity_id, index, piece))
                    index += size
                    matched = True
                    break
            if not matched:
                index += 1
        return found

    def count_visibility(self) -> int:
        return sum(len(rows) for rows in self._visibility.values())


__all__ = ["GraphStore", "InMemoryGraphStore"]
