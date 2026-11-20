"""StoryRole tool catalog for the action runtime.

Only five reads and no writes. A turn may query what the character can know,
what the user remembers, the relationship posture and the period boundary; it
may not execute arbitrary shell, SQL or HTTP.
"""

from __future__ import annotations

from typing import Any

from app.harness.tool_runtime import ToolRuntime, ToolSpec
from app.harness.tools import (
    distill_evidence,
    distill_memories,
    distill_relationship,
    distill_web,
)
from app.services.novel_import_service import novel_import_service
from app.storage.repositories.storyrole_repository import (
    get_character_period,
    get_latest_period_analysis,
    list_characters,
)


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _role_distiller(value: Any, args: dict[str, Any]) -> dict[str, Any]:
    value = value or {}
    return {
        "evidence": distill_evidence(value.get("evidence") or [], limit=10),
        "ego_summary": _clip(value.get("ego_summary"), 800),
        "profile_overlay": dict(value.get("profile_overlay") or {}),
        "route": str(value.get("route") or ""),
        "route_reason": _clip(value.get("route_reason"), 300),
        "cutoff": value.get("cutoff"),
        "multi_hop": bool(value.get("multi_hop")),
        "boundary_source": value.get("boundary_source"),
        "boundary_confidence": value.get("boundary_confidence"),
        "scope": dict(value.get("scope") or {}),
    }


def _permission(turn: Any):
    def check(scope: Any, args: dict[str, Any]) -> bool:
        if scope is None:
            return False
        return (
            str(getattr(scope, "novel_id", "")) == turn.novel_id
            and int(getattr(scope, "owner_id", -1)) == turn.owner_id
            and int(getattr(scope, "character_id", -1) or -1) == turn.character_id
        )
    return check


def build_tool_runtime(turn: Any) -> ToolRuntime:
    runtime = ToolRuntime()
    permission = _permission(turn)

    def role_evidence() -> dict[str, Any]:
        manifest = novel_import_service.get_job(turn.novel_id, owner_id=turn.owner_id)
        period = (
            get_character_period(period_id=turn.period_id, owner_id=turn.owner_id)
            if turn.period_id is not None else None
        )
        period_analysis = get_latest_period_analysis(
            character_id=turn.character_id, owner_id=turn.owner_id
        ) if turn.period_id is not None else None
        characters = list_characters(novel_id=turn.novel_id, owner_id=turn.owner_id)
        from app.rag.rolerag.api_adapter import retrieve_from_manifest

        return retrieve_from_manifest(
            manifest,
            novel_id=turn.novel_id,
            character_name=turn.character_name,
            message=turn.message,
            characters=characters,
            period=period,
            profile=turn.profile,
            period_analysis=(period_analysis or {}).get("result"),
            plan=turn.plan,
        )

    runtime.register(ToolSpec(
        "rolerag.evidence", "角色当前时期可见的小说证据",
        {"type": "object", "properties": {}},
        role_evidence, source="rolerag", timeout_ms=18000,
        distiller=_role_distiller, permission=permission,
        idempotent=True,
    ))

    def memory_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        del query  # the memory tool already scopes by character/thread
        return turn.agent._load_memories(
            turn.payload, character_name=turn.character_name,
        )[:limit]

    runtime.register(ToolSpec(
        "memory.search", "与当前用户有关的长期记忆",
        {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]},
        memory_search, source="memory", timeout_ms=8000,
        distiller=lambda value, args: distill_memories(value, limit=5),
        permission=permission,
    ))

    async def web_search(query: str, max_results: int = 4) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client

        result = await turn.agent._dispatch_timeout(
            a2a_client,
            "web-search",
            {"query": query, "max_results": max_results, "trace_id": turn.trace.trace_id},
            timeout=10.0,
            fallback={"results": [], "degraded": True, "reason": "web_search_timeout"},
        )
        return result

    runtime.register(ToolSpec(
        "web.search", "仅在用户显式开启联网时使用",
        {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]},
        web_search, source="web-search", timeout_ms=10000,
        distiller=lambda value, args: distill_web(value.get("results") or [], limit=4),
        permission=permission,
    ))

    async def relationship_state(character_id: int) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client

        return await turn.agent._dispatch_timeout(
            a2a_client, "relationship-state",
            {
                "profile": turn.profile, "character_id": character_id,
                "owner_id": turn.owner_id, "trace_id": turn.trace.trace_id,
            },
            timeout=8.0, fallback={},
        )

    runtime.register(ToolSpec(
        "relationship.state", "角色与当前来客的关系姿态",
        {"type": "object", "properties": {"character_id": {"type": "integer"}}, "required": ["character_id"]},
        relationship_state, source="relationship-state", timeout_ms=8000,
        distiller=lambda value, args: distill_relationship(value),
        permission=permission,
    ))

    async def timeline_guard(message: str) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client

        return await turn.agent._dispatch_timeout(
            a2a_client, "timeline-guard",
            {"plan": turn.plan, "profile": turn.profile, "message": message,
             "trace_id": turn.trace.trace_id},
            timeout=8.0,
            fallback={"allowed": False, "future_probe": False, "notes": "时间线检查不可用；按严格边界处理"},
        )

    runtime.register(ToolSpec(
        "timeline.guard", "角色可见时期与未来探测边界",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
        timeline_guard, source="timeline-guard", timeout_ms=8000,
        distiller=lambda value, args: dict(value or {}),
        permission=permission,
    ))
    return runtime
