"""FastAPI application entrypoint."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.a2a import router as a2a_router
from app.api.v1.mcp import router as mcp_router
from app.api.v1.auth import router as auth_router
from app.api.v1.media import router as media_router
from app.api.v1.novels import router as novels_router
from app.api.v1.storyrole import router as storyrole_router
from app.api.v1.models import router as models_router
from app.api.v1.settings import router as settings_router
from app.api.v1.uploads import router as uploads_router
from app.api.web import router as web_router
from app.storage.postgres.schema import init_postgres_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = PROJECT_ROOT / "data" / "generated"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
APP_ROOT = FRONTEND_ROOT / "app"
app = FastAPI(title="StoryRole — character conversations")


@app.on_event("startup")
def initialize_database() -> None:
    """Initialize the schema once before serving requests."""
    init_postgres_schema()
    # Laya is the first-choice decision backend for every StoryRole turn,
    # including the default quick mode.  Warm its multilingual checkpoint in
    # the background so the first quick reply does not pay the model load.
    from app.agents.decision.laya_backend import warmup_laya

    threading.Thread(target=warmup_laya, name="laya-warmup", daemon=True).start()


app.include_router(a2a_router)
app.include_router(mcp_router)
app.include_router(auth_router)
app.include_router(media_router)
app.include_router(novels_router)
app.include_router(storyrole_router)
app.include_router(models_router)
app.include_router(settings_router)
app.include_router(uploads_router)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory=FRONTEND_ROOT / "static"), name="static")


def _page(name: str) -> FileResponse:
    return FileResponse(APP_ROOT / name)


def _redirect(request: Request, path: str) -> RedirectResponse:
    query = request.url.query
    url = f"{path}?{query}" if query else path
    return RedirectResponse(url=url, status_code=307)


@app.get("/")
def login_page() -> FileResponse:
    return _page("login.html")


@app.get("/login")
def login_page_alias() -> FileResponse:
    return _page("login.html")


@app.get("/chats")
def chats_page() -> FileResponse:
    return _page("chats.html")


@app.get("/chats/new")
def new_chat_page() -> FileResponse:
    return _page("chat-new.html")


@app.get("/chats/{thread_id}")
def chat_thread_page(thread_id: str) -> FileResponse:
    return _page("chat-thread.html")


@app.get("/characters")
def characters_page() -> FileResponse:
    return _page("characters.html")


@app.get("/characters/new")
def new_character_page() -> FileResponse:
    return _page("character-new.html")


@app.get("/characters/{character_id}/scenes")
def character_scenes_page(character_id: str) -> FileResponse:
    return _page("scenes.html")


@app.get("/characters/{character_id}")
def character_page(character_id: str) -> FileResponse:
    return _page("character.html")


@app.get("/library")
def library_page() -> FileResponse:
    return _page("library.html")


@app.get("/tools")
def tools_page() -> FileResponse:
    return _page("tools.html")


@app.get("/tools/image")
def image_tool_page() -> FileResponse:
    return _page("tool-image.html")


@app.get("/tools/ocr")
def ocr_tool_page() -> FileResponse:
    return _page("tool-ocr.html")


@app.get("/tools/voice")
def voice_tool_page() -> FileResponse:
    return _page("tool-voice.html")


@app.get("/tools/translate")
def translate_tool_page() -> FileResponse:
    return _page("tool-translate.html")


@app.get("/usage")
def usage_page() -> FileResponse:
    return _page("usage.html")


@app.get("/settings")
def settings_page() -> FileResponse:
    return _page("settings.html")


# Human-friendly redirects from the previous build.  Old links keep working,
# but all page transitions now speak in product terms instead of archive terms.
@app.get("/agents")
def old_agents_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/chats")


@app.get("/storyrole")
def old_storyrole_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/chats")


@app.get("/novels")
def old_novels_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/library")


@app.get("/periods")
def old_periods_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/characters")


@app.get("/chat")
def old_chat_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/chats/new")


@app.get("/models")
def old_models_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/usage")


@app.get("/media/image")
def old_media_image_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/tools/image")


@app.get("/media/read")
def old_media_read_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/tools/ocr")


@app.get("/media/voice")
def old_media_voice_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/tools/voice")


@app.get("/media/translate")
def old_media_translate_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/tools/translate")


@app.get("/multimodal")
def old_multimodal_page(request: Request) -> RedirectResponse:
    return _redirect(request, "/tools")


# Generated media stays reachable under /media after the page routes above.
app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")
