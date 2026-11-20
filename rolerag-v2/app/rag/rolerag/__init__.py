"""RoleRAG: perspective-bounded retrieval for character agents.

The package is deliberately import-light: it must be usable from a unit test
without PostgreSQL, an LLM key, or a network. Heavier adapters (PostgreSQL,
OpenAI-compatible models) live behind lazily imported modules.
"""

from __future__ import annotations

from .build import BuildOutcome, build_all
from .chat import Reply, chat_turn, settle
from .eval import REFUSE, Case, evaluate, kbf
from .extract import build_graph, split_chapters
from .models import CognitionState, Entity, Event, Fact, Scene
from .project import project
from .store import InMemoryGraphStore

__all__ = [
    "BuildOutcome",
    "build_all",
    "Reply",
    "chat_turn",
    "settle",
    "REFUSE",
    "Case",
    "evaluate",
    "kbf",
    "build_graph",
    "split_chapters",
    "CognitionState",
    "Entity",
    "Event",
    "Fact",
    "Scene",
    "project",
    "InMemoryGraphStore",
]
