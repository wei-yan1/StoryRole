from __future__ import annotations

from app.storage.postgres.client import postgres_connection

QUERIES = {
    "characters": """
        SELECT COUNT(*) AS bad
        FROM storyrole_characters c
        LEFT JOIN storyrole_novels n ON n.novel_id = c.novel_id AND n.owner_id = c.owner_id
        WHERE n.id IS NULL
    """,
    "memory_candidates": """
        SELECT COUNT(*) AS bad
        FROM storyrole_memory_candidates c
        LEFT JOIN storyrole_novels n ON n.novel_id = c.novel_id AND n.owner_id = c.owner_id
        WHERE n.id IS NULL
    """,
    "relationship_states": """
        SELECT COUNT(*) AS bad
        FROM storyrole_relationship_states c
        LEFT JOIN storyrole_novels n ON n.novel_id = c.novel_id AND n.owner_id = c.owner_id
        WHERE n.id IS NULL
    """,
}

with postgres_connection() as connection, connection.cursor() as cursor:
    for label, sql in QUERIES.items():
        cursor.execute(sql)
        print(label, cursor.fetchone())
