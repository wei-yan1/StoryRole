"""Model registry for the Aliyun MaaS OpenAI-compatible gateway.

One API key serves a large catalog of models. Language-model roles stay on
deepseek flash; non-LLM work (embedding, rerank, image, speech, translation)
resolves to the model that fits that capability instead of borrowing the chat
model.

The endpoint and key come from the same environment used by StoryRole:
``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` (falling back to the DashScope pair).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRole:
    role: str
    capability: str
    model: str
    env: str
    api: str
    # True only for models this project has actually called end to end.
    verified: bool = False


MODEL_ROLES: dict[str, ModelRole] = {
    "chat": ModelRole("chat", "chat", "deepseek-v4.1-flash-1017", "STORYROLE_CHAT_MODEL", "chat", True),
    "reasoning": ModelRole("reasoning", "chat", "deepseek-v4.1-flash-1017", "STORYROLE_REASONING_MODEL", "chat", True),
    "guard": ModelRole("guard", "chat", "deepseek-v4.1-flash-1017", "STORYROLE_GUARD_MODEL", "chat", True),
    "embedding": ModelRole("embedding", "embedding", "qwen3.7-text-embedding", "MODEL_EMBEDDING", "embeddings", True),
    "rerank": ModelRole("rerank", "rerank", "qwen3.7-text-rerank", "DASHSCOPE_RERANK_MODEL", "rerank", True),
    "image": ModelRole("image", "image", "qwen-image-3.0-pro", "MODEL_IMAGE", "images", True),
    "image_fast": ModelRole("image_fast", "image", "wan2.7-image", "MODEL_IMAGE_FAST", "images", False),
    "asr": ModelRole("asr", "asr", "fun-asr-flash-2026-06-15", "MODEL_ASR", "audio", True),
    "tts": ModelRole("tts", "tts", "qwen3-tts-flash", "MODEL_TTS", "audio", True),
    "omni": ModelRole("omni", "omni", "qwen3.8-max", "MODEL_OMNI", "chat", True),
    "translate": ModelRole("translate", "translation", "qwen-mt-plus", "MODEL_TRANSLATE", "chat", True),
    "ocr": ModelRole("ocr", "ocr", "qwen3.5-ocr", "MODEL_OCR", "chat", True),
}

_CAPABILITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("embedding", ("embedding",)),
    ("rerank", ("rerank",)),
    ("ocr", ("ocr",)),
    ("image", ("image", "wan2", "z-image")),
    ("omni", ("omni",)),
    ("translation", ("mt-", "translate")),
    ("tts", ("tts", "speech")),
    ("asr", ("asr", "realtime")),
    ("code", ("code", "coder")),
    ("long_context", ("long",)),
)


def gateway() -> tuple[str, str]:
    """Return (base_url, api_key) for the shared model gateway."""
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL") or ""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    if base_url and api_key:
        return base_url, api_key

    # Ad-hoc scripts may import this module before the app entrypoint loads .env.
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    return (
        os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL") or "",
        os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "",
    )


def resolve_model(role: str) -> str:
    """Resolve a role to its model id, honouring the role's env override."""
    try:
        spec = MODEL_ROLES[role]
    except KeyError as error:
        raise KeyError(f"unknown model role: {role}") from error
    return os.getenv(spec.env) or spec.model


def available_models(*, timeout: float = 30.0) -> list[str]:
    """List every model id this key can call on the gateway."""
    from openai import OpenAI

    base_url, api_key = gateway()
    if not base_url or not api_key:
        raise RuntimeError("gateway credentials missing: set OPENAI_BASE_URL and OPENAI_API_KEY")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
    return [item.id for item in client.models.list().data]


def classify_model(model_id: str) -> str:
    """Coarse capability label for an arbitrary model id.

    The gateway exposes 180+ ids across vendors; this is a discovery aid, not
    a promise about protocol support. A chat-shaped id can still be an audio
    or vision model, so callers should confirm the API before wiring it in.
    """
    lowered = model_id.lower()
    for capability, needles in _CAPABILITY_RULES:
        if any(needle in lowered for needle in needles):
            return capability
    return "chat"


def models_by_capability(model_ids: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for model_id in model_ids:
        grouped.setdefault(classify_model(model_id), []).append(model_id)
    return {capability: sorted(items) for capability, items in sorted(grouped.items())}


def missing_role_models(model_ids: list[str]) -> list[tuple[str, str]]:
    """Return (role, model) pairs whose configured id is absent from the gateway."""
    known = set(model_ids)
    missing: list[tuple[str, str]] = []
    for role in MODEL_ROLES:
        model = resolve_model(role)
        if model not in known:
            missing.append((role, model))
    return missing


__all__ = [
    "MODEL_ROLES",
    "ModelRole",
    "available_models",
    "classify_model",
    "gateway",
    "missing_role_models",
    "models_by_capability",
    "resolve_model",
]
