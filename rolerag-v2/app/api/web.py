"""Product-facing API used by the conversational web app.

The historical ``/api/v1`` surface remains the integration API.  This module is
deliberately small and read-oriented: it gives the new UI a stable, human-readable
resource model (conversations, characters, sources and account usage) while the
existing chat/tool endpoints keep owning execution details.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.v1.auth import current_user, login, register
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.schemas.character import CharacterChatRequest
from app.schemas.novel import NovelRenameRequest
from app.api.v1.settings import SettingsUpdate, get_settings, update_settings
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


@router.get("/characters")
def list_app_characters(user: UserOut = Depends(current_user)) -> dict[str, Any]:
    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.*, n.name AS source_name, n.source_kind,
                   COALESCE(pc.period_count, 0) AS period_count,
                   COALESCE(pp.profile_count, 0) AS profile_count,
                   pp.latest_profile_version,
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
            WHERE c.owner_id=%s
            ORDER BY c.updated_at DESC, c.id DESC
            """,
            (user.id,),
        )
        rows = list(cursor.fetchall())
    return {"items": [_character_summary(row) for row in rows]}


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
            "profile_ready": bool(period_profile),
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
            ORDER BY GREATEST(t.updated_at, COALESCE(lm.created_at, t.updated_at)) DESC, t.id DESC
            LIMIT %s
            """,
            (user.id, limit),
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
        "profile_ready": bool(profile),
    }


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
            SELECT COALESCE(agent_id, operation) AS name, COUNT(*) AS calls,
                   COUNT(*) FILTER (WHERE status='failed') AS errors,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(AVG(duration_ms), 0) AS avg_latency_ms
            FROM model_invocations
            WHERE owner_id=%s AND started_at >= CURRENT_DATE - (%s * INTERVAL '1 day')
            GROUP BY COALESCE(agent_id, operation)
            ORDER BY calls DESC LIMIT 8
            """,
            (user.id, days),
        )
        by_agent = list(cursor.fetchall())
        cursor.execute(
            """
            SELECT id, COALESCE(agent_id, operation) AS agent_id, operation, provider, model, status, duration_ms, total_tokens,
                   cost, cache_hit, started_at, error
            FROM model_invocations
            WHERE owner_id=%s ORDER BY started_at DESC, id DESC LIMIT 12
            """,
            (user.id,),
        )
        recent = list(cursor.fetchall())
    return {
        "days": days,
        "totals": totals,
        "daily": daily,
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


@router.get("/settings")
def app_get_settings(user: UserOut = Depends(current_user)):
    return get_settings(user)


@router.put("/settings")
def app_update_settings(payload: SettingsUpdate, user: UserOut = Depends(current_user)):
    return update_settings(payload, user)


@router.get("/sources")
def list_app_sources(user: UserOut = Depends(current_user)) -> dict[str, Any]:
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
    for item in result:
        item["character_count"] = counts.get(str(item["novel_id"]), 0)
    result.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"items": result}
