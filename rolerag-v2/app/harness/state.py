"""Thread-scoped subject state for the character Harness.

A conversation thread is the unit of "what happened between us". The shared
novel graph stays global; this store never writes into it. If PostgreSQL is
unavailable the turn still completes, and the degradation is reported instead
of silently inventing continuity.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from app.storage.postgres.client import postgres_connection
from app.storage.postgres.schema import init_postgres_schema

from .types import InteractionState, TurnScope


class InteractionStateStore(Protocol):
    def load(self, scope: TurnScope) -> InteractionState: ...
    def save(self, scope: TurnScope, state: InteractionState, checkpoint: dict[str, Any] | None = None) -> None: ...
    def load_checkpoint(self, scope: TurnScope) -> dict[str, Any]: ...


class InMemoryInteractionStateStore:
    def __init__(self) -> None:
        self._states: dict[str, InteractionState] = {}
        self._checkpoints: dict[str, dict[str, Any]] = {}

    def load(self, scope: TurnScope) -> InteractionState:
        return InteractionState.from_dict(
            self._states.get(scope.state_key, InteractionState.empty()).as_dict()
        )

    def save(
        self, scope: TurnScope, state: InteractionState,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        self._states[scope.state_key] = InteractionState.from_dict(state.as_dict())
        if checkpoint is not None:
            self._checkpoints[scope.state_key] = dict(checkpoint)

    def load_checkpoint(self, scope: TurnScope) -> dict[str, Any]:
        return dict(self._checkpoints.get(scope.state_key) or {})


class PostgresInteractionStateStore:
    def load(self, scope: TurnScope) -> InteractionState:
        if scope.thread_id is None:
            return InteractionState.empty()
        init_postgres_schema()
        with postgres_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM storyrole_interaction_states WHERE thread_id=%s",
                (scope.thread_id,),
            )
            row = cursor.fetchone()
        return InteractionState.from_dict((row or {}).get("state") or {})

    def save(
        self, scope: TurnScope, state: InteractionState,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        if scope.thread_id is None:
            return
        init_postgres_schema()
        state_json = json.dumps(state.as_dict(), ensure_ascii=False)
        checkpoint_json = json.dumps(checkpoint or {}, ensure_ascii=False)
        with postgres_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO storyrole_interaction_states
                    (thread_id, novel_id, character_id, owner_id, period_id, state, checkpoint)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (thread_id) DO UPDATE SET
                    state=EXCLUDED.state,
                    checkpoint=EXCLUDED.checkpoint,
                    updated_at=NOW()
                """,
                (
                    scope.thread_id, scope.novel_id, scope.character_id,
                    scope.owner_id, scope.period_id, state_json, checkpoint_json,
                ),
            )

    def load_checkpoint(self, scope: TurnScope) -> dict[str, Any]:
        if scope.thread_id is None:
            return {}
        init_postgres_schema()
        with postgres_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT checkpoint FROM storyrole_interaction_states WHERE thread_id=%s",
                (scope.thread_id,),
            )
            row = cursor.fetchone()
        return dict((row or {}).get("checkpoint") or {})


class ResilientInteractionStateStore:
    """Prefer PostgreSQL, never fail a turn because the state DB is down."""

    def __init__(
        self,
        primary: InteractionStateStore | None = None,
        fallback: InteractionStateStore | None = None,
    ) -> None:
        self.primary = primary or PostgresInteractionStateStore()
        self.fallback = fallback or InMemoryInteractionStateStore()
        self.degraded = False

    def load(self, scope: TurnScope) -> InteractionState:
        if not self.degraded:
            try:
                return self.primary.load(scope)
            except Exception:
                self.degraded = True
        return self.fallback.load(scope)

    def save(
        self, scope: TurnScope, state: InteractionState,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        if not self.degraded:
            try:
                self.primary.save(scope, state, checkpoint=checkpoint)
                return
            except Exception:
                self.degraded = True
        self.fallback.save(scope, state, checkpoint=checkpoint)

    def load_checkpoint(self, scope: TurnScope) -> dict[str, Any]:
        if not self.degraded:
            try:
                return self.primary.load_checkpoint(scope)
            except Exception:
                self.degraded = True
        return self.fallback.load_checkpoint(scope)


_STORE: InteractionStateStore | None = None


def get_interaction_state_store() -> InteractionStateStore:
    global _STORE
    if _STORE is None:
        backend = os.getenv("STORYROLE_HARNESS_STATE", "auto").lower()
        if backend == "memory":
            _STORE = InMemoryInteractionStateStore()
        elif backend == "postgres":
            _STORE = ResilientInteractionStateStore(
                primary=PostgresInteractionStateStore(),
                fallback=InMemoryInteractionStateStore(),
            )
        else:
            _STORE = ResilientInteractionStateStore(
                primary=PostgresInteractionStateStore(),
                fallback=InMemoryInteractionStateStore(),
            )
    return _STORE


def reset_interaction_state_store() -> None:
    """Test hook: isolate state between cases."""
    global _STORE
    _STORE = None
