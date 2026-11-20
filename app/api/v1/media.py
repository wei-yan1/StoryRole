"""Multimodal API routes: image generation/understanding, OCR, speech, translation."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.v1.auth import current_user
from app.core.config.model_catalog import MODEL_ROLES, resolve_model
from app.schemas.auth import UserOut
from app.services import multimodal_service as multimodal


router = APIRouter(prefix="/api/v1/media", tags=["media"])

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    size: str = Field(
        default="1024x1024",
        max_length=32,
        pattern=r"^\d{3,4}x\d{3,4}$",
    )
    model: str | None = Field(default=None, max_length=128)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice: str = Field(default="Cherry", max_length=64)
    model: str | None = Field(default=None, max_length=128)


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    source_lang: str = Field(default="Chinese", max_length=32)
    target_lang: str = Field(default="English", max_length=32)
    model: str | None = Field(default=None, max_length=128)


def _provider_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"多模态模型调用失败: {error}",
    )


async def _read_upload(
    file: UploadFile,
    *,
    allowed: set[str],
    max_bytes: int,
    kind: str,
) -> tuple[bytes, str]:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的{kind}格式: {suffix or '无扩展名'}；可用: {', '.join(sorted(allowed))}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{kind}内容为空",
        )
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{kind}超过大小上限 {max_bytes} 字节",
        )
    return data, filename


@router.get("/models")
def media_models(user: UserOut = Depends(current_user)) -> dict[str, object]:
    """Expose the model id this project uses for each multimodal role."""
    del user  # 仅用于鉴权
    roles = ["image", "image_fast", "ocr", "omni", "asr", "tts", "translate"]
    return {
        "models": {role: resolve_model(role) for role in roles},
        "verified": {role: MODEL_ROLES[role].verified for role in roles},
    }


@router.post("/images/generate")
def generate_image(
    payload: ImageGenerateRequest,
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    del user
    try:
        result = multimodal.generate_image(
            payload.prompt,
            size=payload.size,
            model=payload.model,
        )
    except multimodal.MultimodalError as error:
        raise _provider_error(error) from error
    return {
        "model": result["model"],
        "size": result["size"],
        "url": result["url"],
        "bytes": result["bytes"],
    }


@router.post("/images/describe")
async def describe_image(
    file: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    del user
    data, filename = await _read_upload(
        file,
        allowed=multimodal.IMAGE_SUFFIXES,
        max_bytes=MAX_IMAGE_BYTES,
        kind="图片",
    )
    try:
        return await run_in_threadpool(
            multimodal.describe_image,
            data,
            filename,
            prompt=prompt,
            model=model,
        )
    except multimodal.MultimodalError as error:
        raise _provider_error(error) from error


@router.post("/ocr")
async def ocr_image(
    file: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    del user
    data, filename = await _read_upload(
        file,
        allowed=multimodal.IMAGE_SUFFIXES,
        max_bytes=MAX_IMAGE_BYTES,
        kind="图片",
    )
    try:
        return await run_in_threadpool(
            multimodal.ocr_image,
            data,
            filename,
            prompt=prompt,
            model=model,
        )
    except multimodal.MultimodalError as error:
        raise _provider_error(error) from error


@router.post("/audio/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    del user
    data, filename = await _read_upload(
        file,
        allowed=multimodal.AUDIO_SUFFIXES,
        max_bytes=MAX_AUDIO_BYTES,
        kind="音频",
    )
    try:
        return await run_in_threadpool(
            multimodal.transcribe_audio,
            data,
            filename,
            language=language,
            model=model,
        )
    except multimodal.MultimodalError as error:
        raise _provider_error(error) from error


@router.post("/audio/speech")
async def synthesize_speech(
    payload: SpeechRequest,
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    del user
    try:
        result = await run_in_threadpool(
            multimodal.synthesize_speech,
            payload.text,
            voice=payload.voice,
            model=payload.model,
        )
    except multimodal.MultimodalError as error:
        raise _provider_error(error) from error
    return {
        "model": result["model"],
        "voice": result["voice"],
        "url": result["url"],
        "bytes": result["bytes"],
    }


@router.post("/translate")
def translate_text(
    payload: TranslateRequest,
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    del user
    try:
        return multimodal.translate_text(
            payload.text,
            source_lang=payload.source_lang,
            target_lang=payload.target_lang,
            model=payload.model,
        )
    except multimodal.MultimodalError as error:
        raise _provider_error(error) from error
