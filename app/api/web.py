"""Product-facing API used by the conversational web app.

The historical ``/api/v1`` surface remains the integration API.  This module is
deliberately small and read-oriented: it gives the new UI a stable, human-readable
resource model (conversations, characters, sources and account usage) while the
existing chat/tool endpoints keep owning execution details.
"""

from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.v1.auth import current_user, login, register
from app.core.config.model_catalog import MODEL_ROLES, resolve_model
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.schemas.character import CharacterChatRequest
from app.schemas.novel import NovelRenameRequest
from app.api.v1.settings import SETTING_DEFINITIONS, SettingsUpdate, get_settings, update_settings
from app.api.v1.media import (
    ImageGenerateRequest,
    SpeechRequest,
    TranslateRequest,
    describe_image,
    generate_image,
    media_models,
    ocr_image,
    synthesize_speech,
    transcribe_audio,
    translate_text,
)
from app.storage.postgres.client import postgres_connection
from app.storage.repositories.storyrole_repository import (
    get_character,
    get_latest_period_analysis,
    get_latest_persona_profile,
    get_novel,
    get_persona_profile_for_period,
    list_character_periods,
)

router = APIRouter(prefix="/api/app", tags=["app"])


def _as_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def _has_persona_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() not in {"", "—", "-", "暂无", "无"}
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return value is not None


def _persona_ready(profile: Any) -> bool:
    if not isinstance(profile, dict):
        return False
    return any(
        _has_persona_value(profile.get(key))
        for key in (
            "语言风格", "speech_style", "情绪底色", "emotional_patterns", "personality",
            "核心信念", "core_beliefs", "当前人格状态", "当前状态", "current_state", "identity",
        )
    )


def _character_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "novel_id": row["novel_id"],
        "source_name": row.get("source_name") or "未命名资料",
        "source_kind": row.get("source_kind") or "imported",
        "name": row["canonical_name"],
        "aliases": row.get("aliases") or [],
        "mention_count": int(row.get("mention_count") or 0),
        "summary": row.get("evidence_summary") or "",
        "period_count": int(row.get("period_count") or 0),
        "profile_count": int(row.get("profile_count") or 0),
        "persona_ready": _persona_ready(row.get("latest_profile")),
        "latest_profile_version": row.get("latest_profile_version"),
        "latest_period_name": row.get("latest_period_name"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.post("/auth/login", response_model=AuthResponse)
def app_login(payload: LoginRequest) -> AuthResponse:
    return login(payload)


@router.post("/auth/register", response_model=AuthResponse)
def app_register(payload: RegisterRequest) -> AuthResponse:
    return register(payload)


@router.get("/auth/me", response_model=UserOut)
def app_me(user: UserOut = Depends(current_user)) -> UserOut:
    return user


@router.get("/summary")
def app_summary(user: UserOut = Depends(current_user)) -> dict[str, Any]:
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM storyrole_characters WHERE owner_id=%s) AS character_count,
              (SELECT COUNT(*) FROM storyrole_novels WHERE owner_id=%s) AS source_count,
              (SELECT COUNT(*) FROM chat_threads
               WHERE user_id=%s AND character_id IS NOT NULL AND mode='storyrole') AS conversation_count,
              (SELECT COUNT(*) FROM chat_messages m
               JOIN chat_threads t ON t.id=m.thread_id
               WHERE t.user_id=%s AND t.character_id IS NOT NULL AND t.mode='storyrole') AS message_count
            """,
            (user.id, user.id, user.id, user.id),
        )
        counts = cursor.fetchone() or {}
    return {
        "user": user.model_dump(),
        "counts": {key: int(value or 0) for key, value in counts.items()},
    }


def _character_items(user_id: int, novel_id: str | None = None) -> list[dict[str, Any]]:
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.*, n.name AS source_name, n.source_kind,
                   COALESCE(pc.period_count, 0) AS period_count,
                   COALESCE(pp.profile_count, 0) AS profile_count,
                   pp.latest_profile_version,
                   pr.profile AS latest_profile,
                   lp.name AS latest_period_name
            FROM storyrole_characters c
            JOIN storyrole_novels n
              ON n.novel_id=c.novel_id AND n.owner_id=c.owner_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS period_count
                FROM storyrole_character_periods p
                WHERE p.character_id=c.id AND p.owner_id=c.owner_id
            ) pc ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS profile_count, MAX(version) AS latest_profile_version
                FROM storyrole_persona_profiles pf
                WHERE pf.character_id=c.id AND pf.owner_id=c.owner_id
            ) pp ON TRUE
            LEFT JOIN LATERAL (
                SELECT p.name
                FROM storyrole_persona_profiles pf
                JOIN storyrole_character_periods p ON p.id=pf.period_id
                WHERE pf.character_id=c.id AND pf.owner_id=c.owner_id
                ORDER BY pf.version DESC LIMIT 1
            ) lp ON TRUE
            LEFT JOIN LATERAL (
                SELECT pf.profile
                FROM storyrole_persona_profiles pf
                WHERE pf.character_id=c.id AND pf.owner_id=c.owner_id
                ORDER BY pf.version DESC LIMIT 1
            ) pr ON TRUE
            WHERE c.owner_id=%s
              AND (%s::text IS NULL OR c.novel_id=%s::text)
            ORDER BY c.updated_at DESC, c.id DESC
            """,
            (user_id, novel_id, novel_id),
        )
        rows = list(cursor.fetchall())
    return [_character_summary(row) for row in rows]


@router.get("/characters")
def list_app_characters(
    novel_id: str | None = Query(default=None),
    user: UserOut = Depends(current_user),
) -> dict[str, Any]:
    return {"items": _character_items(user.id, novel_id)}


@router.get("/characters/{character_id}")
def get_app_character(character_id: int, user: UserOut = Depends(current_user)) -> dict[str, Any]:
    character = get_character(character_id=character_id, owner_id=user.id)
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    source = get_novel(novel_id=str(character["novel_id"]), owner_id=user.id) or {}
    periods = list_character_periods(character_id=character_id, owner_id=user.id)
    profile = get_latest_persona_profile(character_id=character_id, owner_id=user.id)
    period_payload = []
    for period in periods:
        period_profile = get_persona_profile_for_period(
            character_id=character_id, owner_id=user.id, period_id=int(period["id"])
        )
        period_payload.append({
            **period,
            "profile_ready": bool(period_profile) and _persona_ready(period_profile.get("profile")),
            "profile_version": period_profile.get("version") if period_profile else None,
            "profile_model": period_profile.get("model") if period_profile else None,
        })
    return {
        "character": {
            "id": int(character["id"]),
            "novel_id": character["novel_id"],
            "name": character["canonical_name"],
            "aliases": character.get("aliases") or [],
            "mention_count": int(character.get("mention_count") or 0),
            "summary": character.get("evidence_summary") or "",
            "first_chapter": character.get("first_chapter"),
            "last_chapter": character.get("last_chapter"),
            "created_at": character.get("created_at"),
            "updated_at": character.get("updated_at"),
        },
        "source": {
            "novel_id": source.get("novel_id") or character["novel_id"],
            "name": source.get("name") or "未命名资料",
            "slug": _novel_slug(source.get("name") or "未命名资料"),
            "source_kind": source.get("source_kind") or "imported",
            "status": source.get("status"),
        },
        "periods": period_payload,
        "profile": profile,
    }


@router.get("/characters/{character_id}/analysis")
def get_app_character_analysis(character_id: int, user: UserOut = Depends(current_user)) -> dict[str, Any]:
    character = get_character(character_id=character_id, owner_id=user.id)
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    row = get_latest_period_analysis(character_id=character_id, owner_id=user.id)
    return {"analysis": ({**row, **(row.get("result") or {})} if row else None)}


@router.get("/conversations")
def list_app_conversations(
    limit: int = Query(default=60, ge=1, le=200),
    novel_id: str | None = Query(default=None),
    user: UserOut = Depends(current_user),
) -> dict[str, Any]:
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT t.id, t.thread_name, t.character_id, t.novel_id, t.period_id,
                   t.created_at, t.updated_at,
                   c.canonical_name AS character_name,
                   n.name AS source_name,
                   p.name AS period_name,
                   lm.content AS last_message,
                   lm.role AS last_role,
                   lm.created_at AS last_message_at,
                   COALESCE(mc.message_count, 0) AS message_count
            FROM chat_threads t
            JOIN storyrole_characters c
              ON c.id=t.character_id AND c.owner_id=t.user_id
            JOIN storyrole_novels n
              ON n.novel_id=t.novel_id AND n.owner_id=t.user_id
            LEFT JOIN storyrole_character_periods p
              ON p.id=t.period_id AND p.owner_id=t.user_id
            LEFT JOIN LATERAL (
                SELECT content, role, created_at
                FROM chat_messages m
                WHERE m.thread_id=t.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) lm ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS message_count
                FROM chat_messages m
                WHERE m.thread_id=t.id
            ) mc ON TRUE
            WHERE t.user_id=%s AND t.character_id IS NOT NULL AND t.mode='storyrole'
              AND (%s::text IS NULL OR t.novel_id=%s::text)
            ORDER BY GREATEST(t.updated_at, COALESCE(lm.created_at, t.updated_at)) DESC, t.id DESC
            LIMIT %s
            """,
            (user.id, novel_id, novel_id, limit),
        )
        rows = list(cursor.fetchall())
    items = []
    for row in rows:
        item = dict(row)
        item["id"] = int(item["id"])
        item["character_id"] = int(item["character_id"]) if item.get("character_id") else None
        item["message_count"] = int(item.get("message_count") or 0)
        items.append(item)
    return {"items": items}


@router.get("/conversations/{thread_id}")
def get_app_conversation(thread_id: int, user: UserOut = Depends(current_user)) -> dict[str, Any]:
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT t.*, c.canonical_name AS character_name,
                   n.name AS source_name, p.name AS period_name
            FROM chat_threads t
            JOIN storyrole_characters c ON c.id=t.character_id AND c.owner_id=t.user_id
            JOIN storyrole_novels n ON n.novel_id=t.novel_id AND n.owner_id=t.user_id
            LEFT JOIN storyrole_character_periods p ON p.id=t.period_id AND p.owner_id=t.user_id
            WHERE t.id=%s AND t.user_id=%s AND t.character_id IS NOT NULL
            """,
            (thread_id, user.id),
        )
        thread = cursor.fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="对话不存在")
        cursor.execute(
            """SELECT id, role, content, metadata, created_at
            FROM chat_messages WHERE thread_id=%s ORDER BY created_at, id""",
            (thread_id,),
        )
        messages = list(cursor.fetchall())
    thread_payload = dict(thread)
    thread_payload["id"] = int(thread_payload["id"])
    thread_payload["message_count"] = len(messages)
    profile = get_persona_profile_for_period(
        character_id=int(thread["character_id"]), owner_id=user.id,
        period_id=int(thread["period_id"]) if thread.get("period_id") else None,
    )
    return {
        "conversation": thread_payload,
        "messages": messages,
        "profile_ready": bool(profile) and _persona_ready(profile.get("profile")),
    }


def _usage_stage(agent_id: Any, operation: Any) -> str:
    agent = str(agent_id or "")
    op = str(operation or "")
    if agent == "character-conversation" or op.startswith("storyrole_answer_generation"):
        return "dialogue"
    if agent == "character-period-analysis" or op == "period_analysis":
        return "scenario"
    if agent == "nuwa-profiler" or op == "nuwa_profile":
        return "persona"
    if agent in {"character-reasoning", "role-cognition", "evidence-analysis", "deep-question-planner", "consistency-guard"}:
        return "assistant"
    if op in {"character_reasoning", "role_cognition", "evidence_analysis", "deep_question_planning", "consistency_guard"}:
        return "assistant"
    if agent in {"embedding", "reranker"} or op in {"embedding", "rerank"}:
        return "retrieval"
    if op.startswith("media_") or op.startswith("tool_") or agent.startswith("tool-"):
        return "tools"
    return "other"


def _p95(values: list[float]) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
    return float(ordered[index])


def _aggregate_stages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(_usage_stage(row.get("agent_id"), row.get("operation")), []).append(row)
    result = []
    for stage, items in buckets.items():
        durations = [float(item.get("duration_ms") or 0) for item in items]
        costs = [item.get("cost") for item in items]
        total_cost = None if any(cost is None for cost in costs) else sum(float(cost or 0) for cost in costs)
        result.append({
            "stage": stage,
            "calls": len(items),
            "errors": sum(1 for item in items if item.get("status") == "failed"),
            "total_tokens": sum(int(item.get("total_tokens") or 0) for item in items),
            "total_cost": total_cost,
            "avg_latency_ms": sum(durations) / len(durations) if durations else 0,
            "p95_latency_ms": _p95(durations),
        })
    result.sort(key=lambda item: item["calls"], reverse=True)
    return result


@router.get("/usage")
def get_app_usage(days: int = Query(default=30, ge=1, le=90), user: UserOut = Depends(current_user)) -> dict[str, Any]:
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS calls,
                   COUNT(*) FILTER (WHERE status='failed') AS errors,
                   COUNT(*) FILTER (WHERE cache_hit) AS cache_hits,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   CASE WHEN COUNT(*) FILTER (WHERE cost IS NULL) > 0
                        THEN NULL ELSE COALESCE(SUM(cost), 0) END AS total_cost,
                   COALESCE(AVG(duration_ms), 0) AS avg_latency_ms,
                   COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms), 0) AS p95_latency_ms
            FROM model_invocations
            WHERE owner_id=%s AND started_at >= CURRENT_DATE - (%s * INTERVAL '1 day')
            """,
            (user.id, days),
        )
        totals = dict(cursor.fetchone() or {})
        cursor.execute(
            """
            SELECT DATE(started_at) AS day, COUNT(*) AS calls,
                   COUNT(*) FILTER (WHERE status='failed') AS errors,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(cost), 0) AS total_cost
            FROM model_invocations
            WHERE owner_id=%s AND started_at >= CURRENT_DATE - (%s * INTERVAL '1 day')
            GROUP BY DATE(started_at) ORDER BY day
            """,
            (user.id, days),
        )
        daily = list(cursor.fetchall())
        cursor.execute(
            """
            SELECT agent_id, operation, status, total_tokens, cost, duration_ms
            FROM model_invocations
            WHERE owner_id=%s AND started_at >= CURRENT_DATE - (%s * INTERVAL '1 day')
            """,
            (user.id, days),
        )
        invocation_rows = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT COALESCE(agent_id, operation) AS name, agent_id, operation,
                   COUNT(*) AS calls,
                   COUNT(*) FILTER (WHERE status='failed') AS errors,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(AVG(duration_ms), 0) AS avg_latency_ms
            FROM model_invocations
            WHERE owner_id=%s AND started_at >= CURRENT_DATE - (%s * INTERVAL '1 day')
            GROUP BY COALESCE(agent_id, operation), agent_id, operation
            ORDER BY calls DESC LIMIT 12
            """,
            (user.id, days),
        )
        by_agent = []
        for row in cursor.fetchall():
            item = dict(row)
            item["stage"] = _usage_stage(item.get("agent_id"), item.get("operation"))
            by_agent.append(item)
        cursor.execute(
            """
            SELECT id, COALESCE(agent_id, operation) AS agent_id, operation, provider, model, status,
                   duration_ms, total_tokens, cost, cache_hit, started_at, error
            FROM model_invocations
            WHERE owner_id=%s ORDER BY started_at DESC, id DESC LIMIT 12
            """,
            (user.id,),
        )
        recent = []
        for row in cursor.fetchall():
            item = dict(row)
            item["stage"] = _usage_stage(item.get("agent_id"), item.get("operation"))
            recent.append(item)
    return {
        "days": days,
        "totals": totals,
        "daily": daily,
        "by_stage": _aggregate_stages(invocation_rows),
        "by_agent": by_agent,
        "recent": recent,
    }


@router.post("/sources/import", status_code=202)
async def import_app_source(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    novel_name: str = Form("未命名资料"),
    user: UserOut = Depends(current_user),
):
    from app.api.v1.novels import import_novel

    return await import_novel(background_tasks, files, novel_name, user)


@router.patch("/sources/{novel_id}")
def rename_app_source(novel_id: str, payload: NovelRenameRequest, user: UserOut = Depends(current_user)):
    from app.api.v1.novels import rename_novel_item

    return rename_novel_item(novel_id, payload, user)


@router.delete("/sources/{novel_id}", status_code=204)
def delete_app_source(novel_id: str, user: UserOut = Depends(current_user)) -> None:
    from app.api.v1.novels import delete_novel_item

    return delete_novel_item(novel_id, user)


@router.post("/characters/{character_id}/messages")
async def app_chat_message(
    character_id: int,
    payload: CharacterChatRequest,
    user: UserOut = Depends(current_user),
):
    from app.api.v1.storyrole import chat_with_character_stream

    character = get_character(character_id=character_id, owner_id=user.id)
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    return await chat_with_character_stream(str(character["novel_id"]), character_id, payload, user)


@router.get("/tools/models")
def app_tool_models(user: UserOut = Depends(current_user)):
    return media_models(user)


@router.post("/tools/image")
def app_tool_image(payload: ImageGenerateRequest, user: UserOut = Depends(current_user)):
    return generate_image(payload, user)


@router.post("/tools/ocr")
async def app_tool_ocr(
    file: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: UserOut = Depends(current_user),
):
    return await ocr_image(file, prompt, model, user)


@router.post("/tools/vision")
async def app_tool_vision(
    file: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: UserOut = Depends(current_user),
):
    return await describe_image(file, prompt, model, user)


@router.post("/tools/speech")
async def app_tool_speech(payload: SpeechRequest, user: UserOut = Depends(current_user)):
    return await synthesize_speech(payload, user)


@router.post("/tools/transcribe")
async def app_tool_transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: UserOut = Depends(current_user),
):
    return await transcribe_audio(file, language, model, user)


@router.post("/tools/translate")
def app_tool_translate(payload: TranslateRequest, user: UserOut = Depends(current_user)):
    return translate_text(payload, user)


class ModelTestRequest(BaseModel):
    type: str = Field(default="chat", max_length=32)
    source: str = Field(default="openai-compatible", max_length=32)
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=128)
    api_key: str = Field(default="", max_length=500)


@router.post("/models/test")
def test_model_connection(payload: ModelTestRequest, user: UserOut = Depends(current_user)) -> dict[str, Any]:
    """Test a user-supplied OpenAI-compatible endpoint without storing the key."""
    del user
    base_url = payload.base_url.strip().rstrip("/")
    if payload.source == "ollama" and not base_url:
        base_url = "http://127.0.0.1:11434/v1"
    if not base_url or not payload.model.strip():
        raise HTTPException(status_code=422, detail="请填写接口地址和模型 ID")
    api_key = payload.api_key.strip() or ("ollama" if payload.source == "ollama" else "")
    if not api_key:
        raise HTTPException(status_code=422, detail="请填写 API Key")
    from openai import OpenAI

    started = time.perf_counter()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=20.0, max_retries=0)
        models = [item.id for item in client.models.list().data]
        if payload.model not in models and models:
            return {
                "ok": False,
                "model_count": len(models),
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "message": f"接口可达，但模型清单里没有 {payload.model}",
            }
        if payload.type == "chat":
            response = client.chat.completions.create(
                model=payload.model,
                messages=[{"role": "user", "content": "连接测试"}],
                max_tokens=4,
                temperature=0,
            )
            if not response.choices:
                raise RuntimeError("模型没有返回候选结果")
        return {
            "ok": True,
            "model_count": len(models),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "message": "连接成功，模型可以调用。",
        }
    except Exception as error:  # noqa: BLE001 - provider errors vary
        return {
            "ok": False,
            "model_count": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "message": f"连接失败：{type(error).__name__}: {str(error)[:240]}",
        }


@router.get("/settings")
def app_get_settings(user: UserOut = Depends(current_user)):
    return get_settings(user)


@router.put("/settings")
def app_update_settings(payload: SettingsUpdate, user: UserOut = Depends(current_user)):
    return update_settings(payload, user)


def _novel_slug(name: Any) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", str(name or ""), flags=re.UNICODE).strip("-")
    return value[:32].strip("-") or "novel"


def _source_items(user: UserOut) -> list[dict[str, Any]]:
    from app.services.novel_import_service import novel_import_service
    from app.storage.repositories.storyrole_repository import list_novels

    jobs = {str(item["import_id"]): item for item in novel_import_service.list_jobs(owner_id=user.id)}
    result: list[dict[str, Any]] = []
    for workspace in list_novels(owner_id=user.id):
        novel_id = str(workspace["novel_id"])
        job = jobs.pop(novel_id, None)
        result.append({
            "novel_id": novel_id,
            "name": workspace["name"],
            "source_kind": workspace.get("source_kind", "imported"),
            "status": workspace["status"],
            "stage": "ready" if workspace["status"] == "ready" else (job or {}).get("stage", workspace["status"]),
            "total_files": (job or {}).get("total_files", 0),
            "processed_files": (job or {}).get("processed_files", 0),
            "chunk_count": (job or {}).get("chunk_count", 0),
            "created_at": workspace["created_at"],
            "updated_at": workspace["updated_at"],
        })
    for job in jobs.values():
        result.append({
            "novel_id": job["import_id"],
            "name": job["novel_name"],
            "source_kind": "imported",
            "status": job["status"],
            "stage": job.get("stage", "uploaded"),
            "total_files": job.get("total_files", 0),
            "processed_files": job.get("processed_files", 0),
            "chunk_count": job.get("chunk_count", 0),
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        })
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT novel_id, COUNT(*) AS character_count
            FROM storyrole_characters WHERE owner_id=%s GROUP BY novel_id""",
            (user.id,),
        )
        counts = {str(row["novel_id"]): int(row["character_count"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT t.novel_id, COUNT(*) AS conversation_count,
                   MAX(GREATEST(t.updated_at, COALESCE(lm.created_at, t.updated_at))) AS last_conversation_at
            FROM chat_threads t
            LEFT JOIN LATERAL (
                SELECT m.created_at
                FROM chat_messages m
                WHERE m.thread_id=t.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) lm ON TRUE
            WHERE t.user_id=%s AND t.character_id IS NOT NULL AND t.mode='storyrole'
            GROUP BY t.novel_id
            """,
            (user.id,),
        )
        conversation_stats = {
            str(row["novel_id"]): {
                "conversation_count": int(row["conversation_count"] or 0),
                "last_conversation_at": row["last_conversation_at"],
            }
            for row in cursor.fetchall()
        }
    for item in result:
        key = str(item["novel_id"])
        item["character_count"] = counts.get(key, 0)
        stats = conversation_stats.get(key, {})
        item["conversation_count"] = stats.get("conversation_count", 0)
        item["last_conversation_at"] = stats.get("last_conversation_at")
    seen_slugs: set[str] = set()
    for item in result:
        base = _novel_slug(item.get("name"))
        slug = base
        if slug in seen_slugs:
            slug = f"{base}-{len(seen_slugs) + 1}"
        seen_slugs.add(slug)
        item["slug"] = slug
    result.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return result


@router.get("/novels")
def list_app_novels(user: UserOut = Depends(current_user)) -> dict[str, Any]:
    return {"items": _source_items(user)}


@router.get("/novels/{novel_id}")
def get_app_novel(novel_id: str, user: UserOut = Depends(current_user)) -> dict[str, Any]:
    rows = _source_items(user)
    item = next(
        (row for row in rows if str(row["novel_id"]) == str(novel_id) or str(row.get("slug")) == str(novel_id)),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="小说不存在")
    return {
        "novel": item,
        "characters": _character_items(user.id, str(item["novel_id"])),
    }


@router.get("/sources")
def list_app_sources(user: UserOut = Depends(current_user)) -> dict[str, Any]:
    return {"items": _source_items(user)}
