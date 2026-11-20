"""API-side adapter: manifest + character rows -> RoleRAG reply.

No FastAPI import here, so it can be unit-tested without a database. The old
agent calls `answer_from_manifest` only when STORYROLE_RETRIEVAL_ENGINE=rolerag.
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from .runtime import RoleRAGRuntime, build_from_chunks, renderer_from_env
from .persona.seed import ProfileOverlay, overlay_from_profile
from .persistence import load_store, save_settlement_store, save_store
from .periods import resolve_period_cutoff
from .retrieval.ego import build_ego_network, ego_summary
from .retrieval.router import route
from .retrieval.scope import analyze_scope
from .retrieval.subgraph import retrieve
from . import graph_cache

PROJECT_ROOT = Path(
    os.getenv("STORYROLE_PROJECT_ROOT") or Path(__file__).resolve().parents[3]
)


@lru_cache(maxsize=64)
def _overlay_from_key(profile_key: str) -> ProfileOverlay | None:
    return overlay_from_profile(json.loads(profile_key))


def profile_overlay(profile: dict[str, Any] | None) -> ProfileOverlay | None:
    if not profile:
        return None
    key = json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str)
    return _overlay_from_key(key)


@lru_cache(maxsize=8)
def _cached_build(chunks_path: str, mtime: float, novel_id: str, hints_key: str) -> RoleRAGRuntime:
    persisted = load_store(novel_id)
    if persisted is not None and persisted.chapters():
        cutoff = max((chapter.ordinal for chapter in persisted.chapters()), default=0)
        return RoleRAGRuntime(persisted, cutoff, persisted=True)
    cached = graph_cache.load(chunks_path, mtime, novel_id, hints_key)
    if cached is not None and cached.chapters():
        cutoff = max((chapter.ordinal for chapter in cached.chapters()), default=0)
        return RoleRAGRuntime(cached, cutoff)
    hints = json.loads(hints_key)
    outcome = build_from_chunks(chunks_path, novel_id=novel_id, hints=hints)
    graph_cache.save(outcome.store, chunks_path, mtime, novel_id, hints_key)
    return RoleRAGRuntime(outcome.store, outcome.cutoff)


def runtime_from_manifest(
    manifest: dict[str, Any],
    *,
    novel_id: str,
    characters: list[dict[str, Any]] | None = None,
) -> RoleRAGRuntime:
    chunks_path = str(manifest.get("chunks_path") or "")
    if not chunks_path:
        raise FileNotFoundError("manifest has no chunks_path")
    path = Path(chunks_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(path)
    hints = hints_from_characters(characters or [])
    key = json.dumps(hints, ensure_ascii=False, sort_keys=True)
    return _cached_build(str(path), path.stat().st_mtime, novel_id, key)


def hints_from_characters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("canonical_name") or row.get("name") or "").strip()
        if not name:
            continue
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except json.JSONDecodeError:
                aliases = [part.strip() for part in aliases.split(",") if part.strip()]
        hints.append({
            "name": name,
            "type": str(row.get("character_type") or "character"),
            "aliases": [str(alias) for alias in aliases if str(alias).strip()],
            "description": str(row.get("description") or row.get("evidence_summary") or ""),
        })
    return hints


def _evidence_rows(evidence) -> list[dict[str, Any]]:
    return [
        {
            "id": item.ref_id,
            "chunk_id": item.ref_id,
            "text": item.text,
            "chapter": item.chapter,
            "score": item.score,
            "kind": item.kind,
            "source": "rolerag",
        }
        for item in evidence
    ]


def retrieve_from_manifest(
    manifest: dict[str, Any],
    *,
    novel_id: str,
    character_name: str,
    message: str,
    characters: list[dict[str, Any]] | None = None,
    period: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    period_analysis: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retrieval-only RoleRAG entry point.

    The character agent keeps ownership of history, memory, mode, web,
    cognition, generation, validation and persistence. This function only
    resolves the character's visible memory and cognitive boundary, then hands
    the rows to the old pipeline. It deliberately does not generate prose.
    """
    runtime = runtime_from_manifest(manifest, novel_id=novel_id, characters=characters)
    boundary = resolve_period_cutoff(
        runtime, period, profile=profile, period_analysis=period_analysis
    )
    cutoff = boundary.cutoff
    entity = runtime.store.find_entity(character_name)
    if entity is None:
        raise KeyError(f"character not found: {character_name}")
    overlay = profile_overlay(profile)
    scope = analyze_scope(message, runtime.store, entity.id, cutoff)
    decision = route(message, scope, plan=plan)
    evidence = retrieve(runtime.store, entity.id, cutoff, decision)
    network = build_ego_network(runtime.store, entity.id, cutoff, hops=2)
    return {
        "cutoff": cutoff,
        "character_id": entity.id,
        "route": decision.kind,
        "route_reason": decision.reason,
        "multi_hop": decision.multi_hop,
        "entities": list(decision.entities),
        "scope": {
            "entities": [item.name for item in scope.entities],
            "external_terms": list(scope.external_terms),
            "has_in_scope": scope.has_in_scope,
            "is_general": scope.is_general,
        },
        "evidence": _evidence_rows(evidence),
        "ego_summary": ego_summary(network),
        "profile_overlay": {
            "relationships": list(overlay.relationships) if overlay else [],
            "known": list(overlay.known) if overlay else [],
            "unknown": list(overlay.unknown) if overlay else [],
            "knowledge_rules": list(overlay.knowledge_rules) if overlay else [],
        } if overlay else {},
        "boundary_source": boundary.source,
        "boundary_confidence": boundary.confidence,
        "runtime": runtime,
    }


def answer_from_manifest(
    manifest: dict[str, Any],
    *,
    novel_id: str,
    character_name: str,
    message: str,
    characters: list[dict[str, Any]] | None = None,
    period: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    period_analysis: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    force_template: bool = False,
) -> dict[str, Any]:
    runtime = runtime_from_manifest(manifest, novel_id=novel_id, characters=characters)
    boundary = resolve_period_cutoff(
        runtime, period, profile=profile, period_analysis=period_analysis
    )
    cutoff = boundary.cutoff
    started = time.perf_counter()
    renderer = renderer_from_env(force_template=force_template)
    overlay = profile_overlay(profile)
    base_persist_error: str | None = None
    if not runtime.persisted:
        ok, base_persist_error = save_store(runtime.store)
        runtime.persisted = ok
    reply = runtime.answer(
        character_name,
        message,
        cutoff=cutoff,
        renderer=renderer,
        profile_overlay=overlay,
        plan=plan,
    )
    entity = runtime.store.find_entity(character_name)
    graph_persisted = False
    graph_persist_error: str | None = base_persist_error
    graph_write_mode = "none"
    if entity is not None:
        from .chat.settle import settle

        settle(runtime.store, entity.id, cutoff, message, reply.text)
        if runtime.persisted:
            graph_persisted, graph_persist_error = save_settlement_store(runtime.store, entity.id)
            graph_write_mode = "incremental"
        else:
            graph_persisted, graph_persist_error = save_store(runtime.store)
            graph_write_mode = "full"
            runtime.persisted = graph_persisted
    return {
        "answer": reply.text,
        "mode": "rolerag",
        "evidence_count": len(reply.evidence),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "degraded": False,
        "degradations": [],
        "engine": "rolerag",
        "route": reply.route,
        "style_ok": reply.style.ok,
        "style_score": reply.style.score,
        "persona_fidelity": reply.fidelity.as_dict() if getattr(reply, "fidelity", None) else None,
        "persona_score": getattr(getattr(reply, "fidelity", None), "score", None),
        "attempts": reply.attempts,
        "cutoff": cutoff,
        "boundary_source": boundary.source,
        "boundary_confidence": boundary.confidence,
        "settled": entity is not None,
        "graph_persisted": graph_persisted,
        "graph_persist_error": graph_persist_error,
        "graph_write_mode": graph_write_mode,
        "profile_injected": overlay is not None,
        "planner_backend": (plan or {}).get("decision_backend", "none"),
        "planner_intent": (plan or {}).get("intent", ""),
        "ego_evidence_count": sum(
            1 for evidence in reply.evidence
            if evidence.kind in {"relation", "relation_gap"}
        ),
    }
