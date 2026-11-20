import os

# Unit tests must not mutate the developer's production graph. Persistence is
# covered by the dedicated PostgreSQL smoke script, not by every unit test.
os.environ.setdefault("STORYROLE_ROLERAG_PG", "0")
