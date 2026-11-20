"""Verify the PostgreSQL adapter against a real server.

Usage:
    python scripts/verify_rolerag_pg.py --dsn "postgresql://postgres:rolerag@localhost:55433/postgres"

Builds the synthetic book, writes it, reads it back, and compares the
projection before and after. Exits non-zero on mismatch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from app.rag.rolerag.demo import build_demo  # noqa: E402
from app.rag.rolerag.pg_store import load, prepare, save  # noqa: E402
from app.rag.rolerag.project import project  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()

    outcome = build_demo()
    source = outcome.store
    lu = source.find_entity("陆知微")

    with psycopg.connect(args.dsn) as connection:
        prepare(connection)
        counts = save(connection, source)
        print(f"[save] {counts}")

        restored = load(connection, source.novel_id)
        print(
            f"[load] chapters={len(restored.chapters())} entities={len(restored.entities())} "
            f"scenes={len(restored.scenes())} events={len(restored.events())} "
            f"facts={len(restored.facts())} visibility={restored.count_visibility()}"
        )
        assert [row.title for row in restored.chapters()] == [row.title for row in source.chapters()]

        before = project(source, lu.id, 6)
        after = project(restored, lu.id, 6)
        assert before.beliefs == after.beliefs, "projection changed after round-trip"
        assert before.unknowns == after.unknowns
        assert before.open_loops == after.open_loops
        assert len(restored.visibility(lu.id)) == len(source.visibility(lu.id))
        assert restored.scenes()[0].roster == source.scenes()[0].roster
        assert restored.events()[0].participants == source.events()[0].participants

        counts_again = save(connection, source)
        assert counts_again == counts, "save is not idempotent"
        assert load(connection, source.novel_id).count_visibility() == counts["visibility"]

    print("PG-ROUNDTRIP-OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
