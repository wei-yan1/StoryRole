"""PostgreSQL adapter.

``save`` is a full replace for one novel: the graph is built offline in one
pass, so replacing is cheaper and safer than reconciling partial upserts. The
DDL lives in ``schema.py``; ids are strings, matching ``models.py``.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg.rows import tuple_row

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
from .schema import init_graph_schema
from .store import InMemoryGraphStore


def prepare(connection: Any) -> None:
    init_graph_schema(connection)


def save(connection: Any, store: InMemoryGraphStore, *, graph_version: str = "v3.2") -> dict[str, int]:
    novel_id = store.novel_id
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM kg_event_participants WHERE event_id IN "
            "(SELECT id FROM kg_events WHERE novel_id = %s)",
            (novel_id,),
        )
        for table in (
            "kg_visibility",
            "kg_beliefs",
            "kg_events",
            "kg_facts",
            "kg_patterns",
            "kg_emotion_transitions",
            "storyrole_character_state",
            "storyrole_scenes",
            "storyrole_chapters",
            "kg_entities",
            "storyrole_rolerag_meta",
        ):
            cursor.execute(f"DELETE FROM {table} WHERE novel_id = %s", (novel_id,))
        cursor.execute(
            "INSERT INTO storyrole_rolerag_meta (novel_id, graph_version) VALUES (%s,%s)",
            (novel_id, graph_version),
        )

        for row in store.chapters():
            cursor.execute(
                "INSERT INTO storyrole_chapters (id, novel_id, chapter_ordinal, title, content) "
                "VALUES (%s,%s,%s,%s,%s)",
                (f"{novel_id}:c{row.ordinal}", novel_id, row.ordinal, row.title, row.text),
            )
        counts["chapters"] = len(store.chapters())

        for row in store.entities():
            cursor.execute(
                "INSERT INTO kg_entities (id, novel_id, canonical_name, entity_type, aliases, "
                "description, first_chapter, last_chapter, mention_count) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    row.id, novel_id, row.name, row.type, Jsonb(list(row.aliases)),
                    row.description, row.first_chapter, row.last_chapter, row.mention_count,
                ),
            )
        counts["entities"] = len(store.entities())

        for row in store.scenes():
            cursor.execute(
                "INSERT INTO storyrole_scenes (id, novel_id, chapter_ordinal, scene_index, title, "
                "location, atmosphere, roster) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    row.id, novel_id, row.chapter, row.index, row.title, row.location,
                    row.atmosphere,
                    Jsonb([{"entity_id": entry.entity_id, "presence": entry.presence} for entry in row.roster]),
                ),
            )
        counts["scenes"] = len(store.scenes())

        for row in store.events():
            cursor.execute(
                "INSERT INTO kg_events (id, novel_id, scene_id, chapter_ordinal, title, summary, "
                "importance, cause, source, thread_id, effects) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    row.id, novel_id, row.scene_id or None, row.chapter, row.title, row.summary,
                    row.importance, row.cause, row.source, row.thread_id,
                    Jsonb([_effect_dict(effect) for effect in row.effects]),
                ),
            )
            for participant in row.participants:
                cursor.execute(
                    "INSERT INTO kg_event_participants (event_id, entity_id, role, presence) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (row.id, participant.entity_id, participant.role, participant.presence),
                )
        counts["events"] = len(store.events())

        for row in store.facts():
            cursor.execute(
                "INSERT INTO kg_facts (id, novel_id, source_id, target_id, kind, sign, weight, "
                "valid_from, valid_to, cause, caused_by_event, confidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    row.id, novel_id, row.source_id, row.target_id, row.kind, row.sign,
                    row.weight, row.valid_from, row.valid_to, row.cause,
                    row.caused_by_event, row.confidence,
                ),
            )
        counts["facts"] = len(store.facts())

        for entity in store.entities():
            for row in store.visibility(entity.id):
                cursor.execute(
                    "INSERT INTO kg_visibility (novel_id, character_id, event_id, fact_id, route, "
                    "from_chapter, certainty) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        novel_id, row.character_id, row.event_id, row.fact_id, row.route,
                        row.from_chapter, row.certainty,
                    ),
                )
            for row in store.beliefs(entity.id):
                cursor.execute(
                    "INSERT INTO kg_beliefs (novel_id, character_id, subject_id, target_id, kind, "
                    "sign, certainty, since_chapter, source, channel, retracted) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        novel_id, row.character_id, row.subject_id, row.target_id, row.kind,
                        row.sign, row.certainty, row.since_chapter, row.source, row.channel,
                        row.retracted,
                    ),
                )
            for row in store.patterns(entity.id):
                cursor.execute(
                    "INSERT INTO kg_patterns (id, novel_id, character_id, description, excerpts, "
                    "tags, centroid) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                    (
                        row.id, novel_id, row.character_id, row.description,
                        Jsonb(list(row.excerpts)), Jsonb(list(row.tags)),
                        Jsonb(list(row.centroid)),
                    ),
                )
            for row in store.emotions(entity.id):
                cursor.execute(
                    "INSERT INTO kg_emotion_transitions (novel_id, character_id, scene_id, emotion, "
                    "intensity, trigger_text, intent, chapter_ordinal, seq) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        novel_id, row.character_id, None, row.emotion, row.intensity,
                        row.trigger, row.intent, row.chapter, row.seq,
                    ),
                )
            state = store.state(entity.id)
            cursor.execute(
                "INSERT INTO storyrole_character_state (character_id, novel_id, alertness, fatigue, "
                "indebtedness, shame, interest, hostility, version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    state.character_id, novel_id, state.alertness, state.fatigue,
                    state.indebtedness, state.shame, state.interest, state.hostility, state.version,
                ),
            )
        counts["visibility"] = store.count_visibility()
    connection.commit()
    return counts


def save_settlement(connection: Any, store: InMemoryGraphStore, character_id: str) -> dict[str, int]:
    """Incremental write for the few rows a chat turn can change.

    Replacing the whole graph after every turn costs seconds on a real novel.
    Settlement only adds dialogue events/participants, dialogue beliefs and one
    character-state row, so this path is deliberately narrow.
    """
    novel_id = store.novel_id
    counts = {"events": 0, "beliefs": 0, "state": 0}
    with connection.cursor() as cursor:
        for row in store.events():
            if row.source != "dialogue":
                continue
            cursor.execute(
                "INSERT INTO kg_events (id, novel_id, scene_id, chapter_ordinal, title, summary, "
                "importance, cause, source, thread_id, effects) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                (
                    row.id, novel_id, row.scene_id or None, row.chapter, row.title, row.summary,
                    row.importance, row.cause, row.source, row.thread_id,
                    Jsonb([_effect_dict(effect) for effect in row.effects]),
                ),
            )
            for participant in row.participants:
                cursor.execute(
                    "INSERT INTO kg_event_participants (event_id, entity_id, role, presence) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (row.id, participant.entity_id, participant.role, participant.presence),
                )
            counts["events"] += 1

        cursor.execute(
            "DELETE FROM kg_beliefs WHERE novel_id = %s AND character_id = %s AND source = 'dialogue'",
            (novel_id, character_id),
        )
        for row in store.beliefs(character_id):
            cursor.execute(
                "INSERT INTO kg_beliefs (novel_id, character_id, subject_id, target_id, kind, "
                "sign, certainty, since_chapter, source, channel, retracted) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    novel_id, row.character_id, row.subject_id, row.target_id, row.kind,
                    row.sign, row.certainty, row.since_chapter, row.source, row.channel,
                    row.retracted,
                ),
            )
            counts["beliefs"] += 1

        state = store.state(character_id)
        cursor.execute(
            "INSERT INTO storyrole_character_state (character_id, novel_id, alertness, fatigue, "
            "indebtedness, shame, interest, hostility, version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (character_id) DO UPDATE SET alertness=EXCLUDED.alertness, "
            "fatigue=EXCLUDED.fatigue, indebtedness=EXCLUDED.indebtedness, "
            "shame=EXCLUDED.shame, interest=EXCLUDED.interest, "
            "hostility=EXCLUDED.hostility, version=EXCLUDED.version, updated_at=NOW()",
            (
                state.character_id, novel_id, state.alertness, state.fatigue,
                state.indebtedness, state.shame, state.interest, state.hostility, state.version,
            ),
        )
        counts["state"] = 1
    connection.commit()
    return counts


def load(connection: Any, novel_id: str) -> InMemoryGraphStore:
    store = InMemoryGraphStore(novel_id)
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT chapter_ordinal, title, content FROM storyrole_chapters "
            "WHERE novel_id = %s ORDER BY chapter_ordinal",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_chapter(Chapter(ordinal=row[0], title=row[1], text=row[2]))

        cursor.execute(
            "SELECT id, canonical_name, entity_type, aliases, description, first_chapter, "
            "last_chapter, mention_count FROM kg_entities WHERE novel_id = %s ORDER BY id",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_entity(
                Entity(
                    id=row[0], name=row[1], type=row[2], aliases=tuple(row[3]),
                    description=row[4], first_chapter=row[5], last_chapter=row[6],
                    mention_count=row[7],
                )
            )

        cursor.execute(
            "SELECT id, chapter_ordinal, scene_index, title, location, atmosphere, roster "
            "FROM storyrole_scenes WHERE novel_id = %s ORDER BY chapter_ordinal, scene_index",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_scene(
                Scene(
                    id=row[0], novel_id=novel_id, chapter=row[1], index=row[2], title=row[3],
                    location=row[4], atmosphere=row[5],
                    roster=tuple(RosterEntry(entity_id=entry["entity_id"], presence=entry["presence"]) for entry in row[6]),
                )
            )

        cursor.execute(
            "SELECT id, scene_id, chapter_ordinal, title, summary, importance, cause, source, "
            "thread_id, effects FROM kg_events WHERE novel_id = %s ORDER BY chapter_ordinal, id",
            (novel_id,),
        )
        event_rows = cursor.fetchall()
        cursor.execute(
            "SELECT event_id, entity_id, role, presence FROM kg_event_participants"
        )
        participants: dict[str, list[Participant]] = {}
        for row in cursor.fetchall():
            participants.setdefault(row[0], []).append(
                Participant(entity_id=row[1], role=row[2], presence=row[3])
            )
        for row in event_rows:
            store.add_event(
                Event(
                    id=row[0], novel_id=novel_id, scene_id=row[1] or "", chapter=row[2],
                    title=row[3], summary=row[4], importance=row[5], cause=row[6],
                    source=row[7], thread_id=row[8],
                    participants=tuple(participants.get(row[0], [])),
                    effects=tuple(Effect(**entry) for entry in row[9]),
                )
            )

        cursor.execute(
            "SELECT id, source_id, target_id, kind, sign, weight, valid_from, valid_to, cause, "
            "caused_by_event, confidence FROM kg_facts WHERE novel_id = %s ORDER BY id",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_fact(
                Fact(
                    id=row[0], novel_id=novel_id, source_id=row[1], target_id=row[2],
                    kind=row[3], sign=row[4], weight=row[5], valid_from=row[6],
                    valid_to=row[7], cause=row[8], caused_by_event=row[9], confidence=row[10],
                )
            )

        cursor.execute(
            "SELECT character_id, event_id, fact_id, route, from_chapter, certainty "
            "FROM kg_visibility WHERE novel_id = %s ORDER BY id",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_visibility(
                Visibility(
                    character_id=row[0], event_id=row[1], fact_id=row[2], route=row[3],
                    from_chapter=row[4], certainty=row[5],
                )
            )

        cursor.execute(
            "SELECT character_id, subject_id, target_id, kind, sign, certainty, since_chapter, "
            "source, channel, retracted FROM kg_beliefs WHERE novel_id = %s ORDER BY id",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_belief(
                Belief(
                    character_id=row[0], subject_id=row[1], target_id=row[2], kind=row[3],
                    sign=row[4], certainty=row[5], since_chapter=row[6], source=row[7],
                    channel=row[8], retracted=row[9],
                )
            )

        cursor.execute(
            "SELECT id, character_id, description, excerpts, tags, centroid "
            "FROM kg_patterns WHERE novel_id = %s ORDER BY id",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_pattern(
                Pattern(
                    id=row[0], character_id=row[1], description=row[2],
                    excerpts=tuple(row[3]), tags=tuple(row[4]), centroid=tuple(row[5]),
                )
            )

        cursor.execute(
            "SELECT character_id, emotion, intensity, trigger_text, intent, chapter_ordinal, seq "
            "FROM kg_emotion_transitions WHERE novel_id = %s ORDER BY character_id, seq",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.add_emotion(
                EmotionTurn(
                    character_id=row[0], emotion=row[1], intensity=row[2], trigger=row[3],
                    intent=row[4], chapter=row[5], seq=row[6],
                )
            )

        cursor.execute(
            "SELECT character_id, alertness, fatigue, indebtedness, shame, interest, "
            "hostility, version FROM storyrole_character_state WHERE novel_id = %s",
            (novel_id,),
        )
        for row in cursor.fetchall():
            store.set_state(
                State(
                    character_id=row[0], alertness=row[1], fatigue=row[2],
                    indebtedness=row[3], shame=row[4], interest=row[5],
                    hostility=row[6], version=row[7],
                )
            )
    return store


def _effect_dict(effect: Effect) -> dict:
    return {
        "subject_id": effect.subject_id,
        "target_id": effect.target_id,
        "kind": effect.kind,
        "sign": effect.sign,
        "delta": effect.delta,
        "reason": effect.reason,
    }


__all__ = ["prepare", "save", "load"]
