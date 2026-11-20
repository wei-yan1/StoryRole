"""PostgreSQL DDL for the RoleRAG layer.

Ids are strings, exactly as they are in ``models.py``. The old schema used
BIGSERIAL surrogates; mixing the two produces the dual-ID problem that makes
projections join the wrong rows, so this layer is explicit: every entity,
scene, event and fact carries the same logical id the offline builder wrote.

``owner_id`` is deliberately absent: tenancy maps a novel to its owner at the
API boundary, and keeping the graph novel-scoped makes the DDL portable to a
single-tenant deployment.
"""

from __future__ import annotations

from typing import Any

DDL = """
CREATE TABLE IF NOT EXISTS storyrole_chapters (
    id              VARCHAR(96) PRIMARY KEY,
    novel_id        VARCHAR(96) NOT NULL,
    chapter_ordinal INTEGER NOT NULL,
    title           VARCHAR(255) NOT NULL,
    section_index   INTEGER,
    book            VARCHAR(128),
    part            VARCHAR(128),
    content_hash    VARCHAR(64),
    content         TEXT NOT NULL DEFAULT '',
    UNIQUE (novel_id, chapter_ordinal)
);

CREATE TABLE IF NOT EXISTS storyrole_scenes (
    id              VARCHAR(96) PRIMARY KEY,
    novel_id        VARCHAR(96) NOT NULL,
    chapter_ordinal INTEGER NOT NULL,
    scene_index     INTEGER NOT NULL,
    title           VARCHAR(255) NOT NULL DEFAULT '',
    location        VARCHAR(255) NOT NULL DEFAULT '',
    atmosphere      VARCHAR(255) NOT NULL DEFAULT '',
    roster          JSONB NOT NULL DEFAULT '[]'::jsonb,
    provenance      JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (novel_id, chapter_ordinal, scene_index)
);

CREATE TABLE IF NOT EXISTS kg_entities (
    id              VARCHAR(96) PRIMARY KEY,
    novel_id        VARCHAR(96) NOT NULL,
    canonical_name  VARCHAR(255) NOT NULL,
    entity_type     VARCHAR(32) NOT NULL,
    aliases         JSONB NOT NULL DEFAULT '[]'::jsonb,
    description     TEXT NOT NULL DEFAULT '',
    first_chapter   INTEGER NOT NULL DEFAULT 0,
    last_chapter    INTEGER NOT NULL DEFAULT 0,
    mention_count   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (novel_id, entity_type, canonical_name)
);

CREATE TABLE IF NOT EXISTS kg_events (
    id              VARCHAR(96) PRIMARY KEY,
    novel_id        VARCHAR(96) NOT NULL,
    scene_id        VARCHAR(96),
    chapter_ordinal INTEGER NOT NULL,
    title           VARCHAR(255) NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    importance      DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    cause           TEXT NOT NULL DEFAULT '',
    source          VARCHAR(24) NOT NULL DEFAULT 'novel',
    thread_id       BIGINT,
    effects         JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_event_participants (
    event_id  VARCHAR(96) NOT NULL,
    entity_id VARCHAR(96) NOT NULL,
    role      VARCHAR(32) NOT NULL,
    presence  VARCHAR(16) NOT NULL DEFAULT 'active',
    PRIMARY KEY (event_id, entity_id, role)
);

CREATE TABLE IF NOT EXISTS kg_facts (
    id               VARCHAR(128) PRIMARY KEY,
    novel_id         VARCHAR(96) NOT NULL,
    source_id        VARCHAR(96) NOT NULL,
    target_id        VARCHAR(96) NOT NULL,
    kind             VARCHAR(48) NOT NULL,
    sign             SMALLINT NOT NULL DEFAULT 0,
    weight           DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    valid_from       INTEGER NOT NULL,
    valid_to         INTEGER,
    cause            TEXT NOT NULL DEFAULT '',
    caused_by_event  VARCHAR(96),
    confidence       DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    CHECK (sign IN (-1, 0, 1))
);

CREATE TABLE IF NOT EXISTS kg_visibility (
    id            BIGSERIAL PRIMARY KEY,
    novel_id      VARCHAR(96) NOT NULL,
    character_id  VARCHAR(96) NOT NULL,
    event_id      VARCHAR(96),
    fact_id       VARCHAR(128),
    route         VARCHAR(24) NOT NULL,
    from_chapter  INTEGER NOT NULL,
    certainty     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    CHECK (route IN ('direct', 'witness', 'org', 'common', 'told')),
    CHECK ((event_id IS NOT NULL)::int + (fact_id IS NOT NULL)::int = 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_visibility_event
    ON kg_visibility (character_id, event_id, route) WHERE event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_visibility_fact
    ON kg_visibility (character_id, fact_id, route) WHERE fact_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS kg_beliefs (
    id             BIGSERIAL PRIMARY KEY,
    novel_id       VARCHAR(96) NOT NULL,
    character_id   VARCHAR(96) NOT NULL,
    subject_id     VARCHAR(96) NOT NULL,
    target_id      VARCHAR(96) NOT NULL,
    kind           VARCHAR(48) NOT NULL,
    sign           SMALLINT NOT NULL DEFAULT 1,
    certainty      DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    since_chapter  INTEGER NOT NULL,
    source         VARCHAR(24) NOT NULL DEFAULT 'dialogue',
    channel        VARCHAR(24) NOT NULL DEFAULT 'told',
    retracted      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kg_patterns (
    id              VARCHAR(96) PRIMARY KEY,
    novel_id        VARCHAR(96) NOT NULL,
    character_id    VARCHAR(96) NOT NULL,
    description     VARCHAR(255) NOT NULL,
    excerpts        JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    centroid        JSONB NOT NULL DEFAULT '[0, 0]'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_emotion_transitions (
    id              BIGSERIAL PRIMARY KEY,
    novel_id        VARCHAR(96) NOT NULL,
    character_id    VARCHAR(96) NOT NULL,
    scene_id        VARCHAR(96),
    emotion         VARCHAR(48) NOT NULL,
    intensity       DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    trigger_text    VARCHAR(255) NOT NULL DEFAULT '',
    intent          VARCHAR(255) NOT NULL DEFAULT '',
    chapter_ordinal INTEGER NOT NULL,
    seq             INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS storyrole_character_state (
    character_id VARCHAR(96) PRIMARY KEY,
    novel_id     VARCHAR(96) NOT NULL,
    period_id    BIGINT,
    alertness    DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    fatigue      DOUBLE PRECISION NOT NULL DEFAULT 0.3,
    indebtedness DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    shame        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    interest     DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    hostility    DOUBLE PRECISION NOT NULL DEFAULT 0.1,
    version      INTEGER NOT NULL DEFAULT 0,
    triggers     JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS storyrole_rolerag_meta (
    novel_id      VARCHAR(96) PRIMARY KEY,
    graph_version VARCHAR(64) NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chapters_novel ON storyrole_chapters(novel_id, chapter_ordinal);
CREATE INDEX IF NOT EXISTS idx_scenes_novel ON storyrole_scenes(novel_id, chapter_ordinal);
CREATE INDEX IF NOT EXISTS idx_entities_novel_type ON kg_entities(novel_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_events_novel_chapter ON kg_events(novel_id, chapter_ordinal);
CREATE INDEX IF NOT EXISTS idx_participants_entity ON kg_event_participants(entity_id);
CREATE INDEX IF NOT EXISTS idx_facts_pair ON kg_facts(novel_id, source_id, target_id);
CREATE INDEX IF NOT EXISTS idx_facts_valid ON kg_facts(novel_id, valid_from);
CREATE INDEX IF NOT EXISTS idx_visibility_char ON kg_visibility(character_id, from_chapter);
CREATE INDEX IF NOT EXISTS idx_beliefs_char ON kg_beliefs(character_id, since_chapter);
CREATE INDEX IF NOT EXISTS idx_emotions_char ON kg_emotion_transitions(character_id, chapter_ordinal, seq);
"""


def init_graph_schema(connection: Any) -> None:
    """Execute the DDL on an open psycopg connection."""
    with connection.cursor() as cursor:
        cursor.execute(DDL)
    connection.commit()
