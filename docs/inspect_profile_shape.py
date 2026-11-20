import json
from app.storage.postgres.client import postgres_connection

with postgres_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT character_id, version, period_id, profile FROM storyrole_persona_profiles "
            "WHERE owner_id IS NOT NULL ORDER BY id DESC LIMIT 3"
        )
        for row in cursor.fetchall():
            profile = row.get("profile") or {}
            print(row["character_id"], row["version"], row["period_id"], list(profile.keys()))
            print(json.dumps(profile, ensure_ascii=False)[:1800])
            print("---")
