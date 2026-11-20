"""RoleRAG graph persistence boundary.

The graph is built offline from chunks, then settlement mutates it. This module
is deliberately small: it is the only place the API path touches PostgreSQL for
beliefs/events/state, so a persistence failure can be reported without
corrupting the user-visible answer.
"""

from __future__ import annotations

import logging
import os

from .pg_store import load, prepare, save, save_settlement
from .store import InMemoryGraphStore

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("STORYROLE_ROLERAG_PG", "1").lower() in {"1", "true", "yes", "on"}


def graph_version() -> str:
    return os.getenv("STORYROLE_ROLERAG_GRAPH_VERSION", "v3.2")


def load_store(novel_id: str) -> InMemoryGraphStore | None:
    """Load a previously persisted graph, or return None when it is absent."""
    if not enabled():
        return None
    try:
        from app.storage.postgres.client import postgres_connection

        with postgres_connection() as connection:
            prepare(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT graph_version FROM storyrole_rolerag_meta WHERE novel_id = %s",
                    (novel_id,),
                )
                meta = cursor.fetchone()
                if not meta or str(meta["graph_version"]) != graph_version():
                    return None
                cursor.execute(
                    "SELECT count(*) AS n FROM kg_events WHERE novel_id = %s",
                    (novel_id,),
                )
                row = cursor.fetchone()
                if not row or int(row["n"]) == 0:
                    return None
            return load(connection, novel_id)
    except Exception as error:  # noqa: BLE001 - persistence is optional
        logger.warning("RoleRAG graph load failed: %s", error)
        return None


def save_store(store: InMemoryGraphStore) -> tuple[bool, str | None]:
    """Full-replace one novel's graph. Returns (ok, error message)."""
    if not enabled():
        return False, "disabled"
    try:
        from app.storage.postgres.client import postgres_connection

        with postgres_connection() as connection:
            prepare(connection)
            save(connection, store, graph_version=graph_version())
        return True, None
    except Exception as error:  # noqa: BLE001 - persist failure must not break chat
        logger.warning("RoleRAG graph save failed: %s", error)
        return False, f"{type(error).__name__}: {str(error)[:180]}"


def save_settlement_store(store: InMemoryGraphStore, character_id: str) -> tuple[bool, str | None]:
    """Persist only the rows a single dialogue turn changed."""
    if not enabled():
        return False, "disabled"
    try:
        from app.storage.postgres.client import postgres_connection

        with postgres_connection() as connection:
            prepare(connection)
            save_settlement(connection, store, character_id)
        return True, None
    except Exception as error:  # noqa: BLE001
        logger.warning("RoleRAG settlement save failed: %s", error)
        return False, f"{type(error).__name__}: {str(error)[:180]}"


__all__ = ["enabled", "graph_version", "load_store", "save_store", "save_settlement_store"]
