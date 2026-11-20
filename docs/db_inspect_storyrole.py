from __future__ import annotations

from app.storage.postgres.client import postgres_connection

SQL = """
SELECT c.conname, c.contype, pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
WHERE c.conrelid = 'storyrole_novels'::regclass
ORDER BY c.conname
"""

INDEX_SQL = """
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'storyrole_novels'
ORDER BY indexname
"""

with postgres_connection() as connection, connection.cursor() as cursor:
    cursor.execute(SQL)
    print("CONSTRAINTS")
    for row in cursor.fetchall():
        print(row)
    cursor.execute(INDEX_SQL)
    print("INDEXES")
    for row in cursor.fetchall():
        print(row)
    cursor.execute("""
        SELECT conname, conrelid::regclass AS table_name, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE confrelid = 'storyrole_novels'::regclass
        ORDER BY conrelid::regclass::text, conname
    """)
    print("REFERENCING FOREIGN KEYS")
    for row in cursor.fetchall():
        print(row)
    cursor.execute("""
        SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid IN (
            'storyrole_characters'::regclass,
            'storyrole_memory_candidates'::regclass,
            'storyrole_relationship_states'::regclass,
            'storyrole_character_mentions'::regclass
        ) AND contype = 'f'
        ORDER BY conrelid::regclass::text, conname
    """)
    print("CHILD FOREIGN KEYS")
    for row in cursor.fetchall():
        print(row)
    cursor.execute("""
        SELECT conrelid::regclass AS table_name, conname, contype, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid IN (
            'storyrole_characters'::regclass,
            'storyrole_character_periods'::regclass,
            'storyrole_persona_profiles'::regclass
        )
        ORDER BY conrelid::regclass::text, conname
    """)
    print("CHILD CONSTRAINTS")
    for row in cursor.fetchall():
        print(row)
    cursor.execute("""
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE tablename IN ('storyrole_characters', 'storyrole_character_periods')
        ORDER BY tablename, indexname
    """)
    print("CHILD INDEXES")
    for row in cursor.fetchall():
        print(row)
    cursor.execute("""
        SELECT conname, conrelid::regclass AS table_name, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE confrelid = 'storyrole_characters'::regclass
        ORDER BY conrelid::regclass::text, conname
    """)
    print("FK REFERENCES TO CHARACTERS")
    for row in cursor.fetchall():
        print(row)
