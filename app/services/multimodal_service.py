"""Multimodal model calls behind the shared gateway key.

The language model stays on ``deepseek-v4.1-flash-1017``. This module covers
the non-LLM capabilities that the same key can reach:

- image generation: ``qwen-image-3.0-pro`` via OpenAI-compatible ``/images``
- image understanding: ``qwen3.8-max`` via chat vision input
- OCR: ``qwen3.5-ocr`` via chat vision input
- ASR: ``fun-asr-flash-2026-06-15`` via native DashScope HTTP;
  ``qwen-audio-3.0-asr-flash`` remains available as a model override fallback
- TTS: ``qwen3-tts-flash`` via native DashScope qwen_tts call
  (MiniMax speech-2.8-hd is listed by the gateway but this workspace has not
  activated the product, so it cannot be the default)
- translation: ``qwen-mt-plus`` via native DashScope Generation call

Only model ids and the gateway credentials are shared; each capability keeps
the protocol its provider actually supports. The compatible endpoint accepts
image generation and vision chat, while speech and translation need the native
DashScope SDK.
"""

from __future__ import annotations

import base64
import mimetypes
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.config.model_catalog import gateway, resolve_model


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = PROJECT_ROOT / "data" / "generated"
IMAGE_DIR = MEDIA_ROOT / "images"
AUDIO_DIR = MEDIA_ROOT / "audio"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}

_AUDIO_FORMATS = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".m4a": "m4a",
    ".ogg": "ogg",
    ".flac": "flac",
}
_AUDIO_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

DEFAULT_OCR_PROMPT = "识别图片中的所有文字，按行输出，不要解释。"
DEFAULT_DESCRIBE_PROMPT = "用一句话描述这张图片的内容。"
DEFAULT_ASR_PROMPT = "转写这段音频，只输出文字。"

_LANGUAGE_HINTS = {
    "中文": "zh",
    "chinese": "zh",
    "english": "en",
    "英语": "en",
    "日语": "ja",
    "japanese": "ja",
    "한국어": "ko",
    "韩语": "ko",
}


class MultimodalError(RuntimeError):
    """A multimodal model call failed or its input was unsupported."""


def _gateway_client() -> Any:
    from openai import OpenAI

    base_url, api_key = gateway()
    if not base_url or not api_key:
        raise MultimodalError("网关凭据缺失：需要 OPENAI_BASE_URL 与 OPENAI_API_KEY")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=1)


def _gateway_credentials() -> tuple[str, str]:
    base_url, api_key = gateway()
    if not base_url or not api_key:
        raise MultimodalError("网关凭据缺失：需要 OPENAI_BASE_URL 与 OPENAI_API_KEY")
    return base_url, api_key


def _native_generation_url() -> str:
    """Build the native multimodal-generation URL from the compatible endpoint."""
    base_url, _ = _gateway_credentials()
    if "/compatible-mode" in base_url:
        root = base_url.split("/compatible-mode", 1)[0]
    else:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
    return root.rstrip("/") + "/api/v1/services/aigc/multimodal-generation/generation"


def _suffix(filename: str, allowed: set[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise MultimodalError(
            f"不支持的格式: {suffix or '无扩展名'}；可用: {', '.join(sorted(allowed))}"
        )
    return suffix


def _data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _save_media(data: bytes, suffix: str, kind: str) -> Path:
    if not data:
        raise MultimodalError("模型返回了空内容")
    directory = IMAGE_DIR if kind == "images" else AUDIO_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)
    return path


def media_url(path: Path) -> str:
    """Map a generated file to the public ``/media`` mount."""
    try:
        relative = path.relative_to(MEDIA_ROOT)
    except ValueError as error:
        raise MultimodalError(f"生成文件不在媒体目录内: {path}") from error
    return "/media/" + relative.as_posix()


def _download(url: str) -> tuple[bytes, str]:
    try:
        response = httpx.get(url, timeout=90.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise MultimodalError(f"下载模型产物失败: {error}") from error
    return response.content, response.headers.get("content-type", "")


def _content_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts).strip()
    return str(content).strip()


def _vision_text(model: str, prompt: str, data_uri: str, max_tokens: int = 2048) -> str:
    client = _gateway_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            max_tokens=max_tokens,
            temperature=0,
        )
    except Exception as error:  # noqa: BLE001 - provider errors vary
        raise MultimodalError(f"图片模型调用失败: {error}") from error
    if not response.choices:
        raise MultimodalError("图片模型没有返回候选结果")
    text = _content_text(response.choices[0].message)
    if not text:
        raise MultimodalError("图片模型返回了空文本")
    return text


def generate_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    model: str | None = None,
) -> dict[str, Any]:
    """Generate one image and persist it under ``data/generated/images``."""
    if not prompt or not prompt.strip():
        raise MultimodalError("图片描述不能为空")
    selected = model or resolve_model("image")
    client = _gateway_client()
    try:
        response = client.images.generate(
            model=selected,
            prompt=prompt.strip(),
            size=size,
            n=1,
        )
    except Exception as error:  # noqa: BLE001
        raise MultimodalError(f"图片生成失败: {error}") from error
    if not response.data:
        raise MultimodalError("图片生成没有返回结果")
    item = response.data[0]
    if getattr(item, "b64_json", None):
        data = base64.b64decode(item.b64_json)
        suffix = ".png"
    elif getattr(item, "url", None):
        data, content_type = _download(item.url)
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".png"
        if suffix == ".jpe":
            suffix = ".jpg"
        if suffix not in IMAGE_SUFFIXES:
            suffix = ".png"
    else:
        raise MultimodalError("图片生成结果既没有 URL 也没有 base64")
    path = _save_media(data, suffix, "images")
    return {
        "model": selected,
        "prompt": prompt.strip(),
        "size": size,
        "path": str(path),
        "url": media_url(path),
        "bytes": len(data),
    }


def describe_image(
    data: bytes,
    filename: str,
    *,
    prompt: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Describe an image with the flagship vision model."""
    suffix = _suffix(filename, IMAGE_SUFFIXES)
    selected = model or resolve_model("omni")
    text = _vision_text(
        selected,
        (prompt or DEFAULT_DESCRIBE_PROMPT).strip(),
        _data_uri(data, _IMAGE_MIME[suffix]),
        max_tokens=1024,
    )
    return {"model": selected, "text": text}


def ocr_image(
    data: bytes,
    filename: str,
    *,
    prompt: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Extract text from an image with the OCR model."""
    suffix = _suffix(filename, IMAGE_SUFFIXES)
    selected = model or resolve_model("ocr")
    text = _vision_text(
        selected,
        (prompt or DEFAULT_OCR_PROMPT).strip(),
        _data_uri(data, _IMAGE_MIME[suffix]),
        max_tokens=2048,
    )
    return {"model": selected, "text": text}


def _asr_text(output: Any) -> str:
    """Pull text out of the several shapes the ASR response can take.

    Fun-ASR returns ``sentence``/``sentences`` at the top level; Qwen-Audio
    returns text under ``output``.
    """
    if not isinstance(output, dict):
        return ""
    direct = output.get("text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    sentence = output.get("sentence")
    if isinstance(sentence, dict):
        text = sentence.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    sentences = output.get("sentences")
    if isinstance(sentences, list):
        parts = [
            str(item.get("text", "")).strip()
            for item in sentences
            if isinstance(item, dict) and item.get("text")
        ]
        if parts:
            return "\n".join(parts)
    nested = output.get("output")
    if isinstance(nested, dict):
        return _asr_text(nested)
    return ""


def _transcribe_fun_asr(
    data: bytes,
    suffix: str,
    language: str | None,
    selected: str,
) -> dict[str, Any]:
    """Call Fun-ASR's non-real-time HTTP endpoint with local audio."""
    _, api_key = _gateway_credentials()
    parameters: dict[str, Any] = {
        "format": _AUDIO_FORMATS[suffix],
        "sample_rate": "16000",
    }
    key = (language or "").strip()
    hint = _LANGUAGE_HINTS.get(key) or _LANGUAGE_HINTS.get(key.lower())
    if hint:
        parameters["language_hints"] = [hint]
    payload = {
        "model": selected,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": _data_uri(data, _AUDIO_MIME[suffix])
                            },
                        }
                    ],
                }
            ]
        },
        "parameters": parameters,
    }
    try:
        response = httpx.post(
            _native_generation_url(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-DashScope-SSE": "disable",
            },
            json=payload,
            timeout=90.0,
        )
    except httpx.HTTPError as error:
        raise MultimodalError(f"语音转写失败: {error}") from error
    if response.status_code != 200:
        try:
            body = response.json()
            message = body.get("message") or body.get("code") or response.text
        except ValueError:
            message = response.text
        raise MultimodalError(f"语音转写失败: {message}")
    try:
        body = response.json()
    except ValueError as error:
        raise MultimodalError("语音转写返回了无法解析的响应") from error
    if isinstance(body, dict) and body.get("code"):
        raise MultimodalError(
            f"语音转写失败: {body.get('message') or body.get('code')}"
        )
    text = _asr_text(body)
    if not text:
        raise MultimodalError("语音转写没有返回文字")
    return {"model": selected, "text": text, "format": _AUDIO_FORMATS[suffix]}


def transcribe_audio(
    data: bytes,
    filename: str,
    *,
    language: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Transcribe local audio without needing a public URL.

    Fun-ASR accepts an ``input_audio`` data URI on its native HTTP endpoint.
    When ``MODEL_ASR`` is overridden to a Qwen-Audio model, the older
    DashScope ``MultiModalConversation`` path is kept as a fallback.
    """
    suffix = _suffix(filename, AUDIO_SUFFIXES)
    selected = model or resolve_model("asr")
    if selected.lower().startswith("fun-asr"):
        return _transcribe_fun_asr(data, suffix, language, selected)
    _, api_key = _gateway_credentials()
    prompt = DEFAULT_ASR_PROMPT
    if language:
        prompt += f" 使用{language}。"
    import dashscope

    try:
        response = dashscope.MultiModalConversation.call(
            model=selected,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"audio": _data_uri(data, _AUDIO_MIME[suffix])},
                        {"text": prompt},
                    ],
                }
            ],
            format=_AUDIO_FORMATS[suffix],
            api_key=api_key,
        )
    except Exception as error:  # noqa: BLE001
        raise MultimodalError(f"语音转写失败: {error}") from error
    if getattr(response, "status_code", None) != 200:
        raise MultimodalError(
            f"语音转写失败: {getattr(response, 'message', '') or response}"
        )
    text = _asr_text(getattr(response, "output", None))
    if not text:
        raise MultimodalError("语音转写没有返回文字")
    return {"model": selected, "text": text, "format": _AUDIO_FORMATS[suffix]}


def synthesize_speech(
    text: str,
    *,
    voice: str = "Cherry",
    model: str | None = None,
) -> dict[str, Any]:
    """Synthesize speech and persist the wav under ``data/generated/audio``."""
    if not text or not text.strip():
        raise MultimodalError("待合成文本不能为空")
    selected = model or resolve_model("tts")
    _, api_key = _gateway_credentials()
    from dashscope.audio.qwen_tts import SpeechSynthesizer

    try:
        response = SpeechSynthesizer.call(
            model=selected,
            text=text.strip(),
            voice=voice,
            api_key=api_key,
        )
    except Exception as error:  # noqa: BLE001
        raise MultimodalError(f"语音合成失败: {error}") from error
    if getattr(response, "status_code", None) != 200:
        raise MultimodalError(
            f"语音合成失败: {getattr(response, 'message', '') or response}"
        )
    output = getattr(response, "output", None)
    audio = output.get("audio") if isinstance(output, dict) else None
    if not isinstance(audio, dict):
        raise MultimodalError("语音合成没有返回音频信息")
    if audio.get("data"):
        data = base64.b64decode(audio["data"])
        suffix = ".wav"
    elif audio.get("url"):
        data, content_type = _download(str(audio["url"]))
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".wav"
        if suffix not in AUDIO_SUFFIXES:
            suffix = ".wav"
    else:
        raise MultimodalError("语音合成结果既没有 URL 也没有音频数据")
    path = _save_media(data, suffix, "audio")
    return {
        "model": selected,
        "voice": voice,
        "path": str(path),
        "url": media_url(path),
        "bytes": len(data),
        "text": text.strip(),
    }


def _generation_text(output: Any) -> str:
    if not isinstance(output, dict):
        return ""
    choices = output.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]).strip()
    text = output.get("text")
    return str(text).strip() if text else ""


def translate_text(
    text: str,
    *,
    source_lang: str = "Chinese",
    target_lang: str = "English",
    model: str | None = None,
) -> dict[str, Any]:
    """Translate text with Qwen-MT's native translation options."""
    if not text or not text.strip():
        raise MultimodalError("待翻译文本不能为空")
    selected = model or resolve_model("translate")
    _, api_key = _gateway_credentials()
    import dashscope

    try:
        response = dashscope.Generation.call(
            model=selected,
            messages=[{"role": "user", "content": text.strip()}],
            result_format="message",
            translation_options={
                "source_lang": source_lang,
                "target_lang": target_lang,
            },
            api_key=api_key,
        )
    except Exception as error:  # noqa: BLE001
        raise MultimodalError(f"翻译失败: {error}") from error
    if getattr(response, "status_code", None) != 200:
        raise MultimodalError(
            f"翻译失败: {getattr(response, 'message', '') or response}"
        )
    translated = _generation_text(getattr(response, "output", None))
    if not translated:
        raise MultimodalError("翻译没有返回文本")
    return {
        "model": selected,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "text": translated,
    }
