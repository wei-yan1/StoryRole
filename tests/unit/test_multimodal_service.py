from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import media
from app.api.v1.auth import current_user
from app.schemas.auth import UserOut
from app.services import multimodal_service as m


def test_generate_image_saves_to_media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(m, "IMAGE_DIR", tmp_path / "images")

    class FakeImages:
        def generate(self, **kwargs):
            assert kwargs["model"] == "qwen-image-3.0-pro"
            assert kwargs["size"] == "1024x1024"
            return SimpleNamespace(
                data=[SimpleNamespace(url="https://example.com/image.png", b64_json=None)]
            )

    monkeypatch.setattr(
        m, "_gateway_client", lambda: SimpleNamespace(images=FakeImages())
    )
    monkeypatch.setattr(m, "_download", lambda url: (b"\x89PNG-data", "image/png"))

    result = m.generate_image("雨夜里的青石台阶")

    assert result["model"] == "qwen-image-3.0-pro"
    assert result["url"].startswith("/media/images/")
    assert Path(result["path"]).read_bytes() == b"\x89PNG-data"


def test_ocr_and_describe_use_capability_models(monkeypatch):
    calls = {}

    def fake_vision(model, prompt, data_uri, max_tokens=2048):
        calls["model"] = model
        calls["prompt"] = prompt
        calls["data_uri"] = data_uri
        return "识别结果"

    monkeypatch.setattr(m, "_vision_text", fake_vision)

    ocr = m.ocr_image(b"image-bytes", "page.png")
    assert ocr["model"] == "qwen3.5-ocr"
    assert ocr["text"] == "识别结果"
    assert calls["data_uri"].startswith("data:image/png;base64,")

    describe = m.describe_image(b"photo-bytes", "photo.jpg")
    assert describe["model"] == "qwen3.8-max"
    assert calls["data_uri"].startswith("data:image/jpeg;base64,")


def test_transcribe_audio_sends_format_and_base64(monkeypatch):
    monkeypatch.setattr(m, "_gateway_credentials", lambda: ("https://gateway", "key"))
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, output={"text": "你好，我是沈砚。"})

    monkeypatch.setattr("dashscope.MultiModalConversation.call", fake_call)

    result = m.transcribe_audio(
        b"RIFF-wav",
        "voice.wav",
        language="中文",
        model="qwen-audio-3.0-asr-flash",
    )

    assert result["text"] == "你好，我是沈砚。"
    assert captured["model"] == "qwen-audio-3.0-asr-flash"
    assert captured["format"] == "wav"
    assert captured["messages"][0]["content"][0]["audio"].startswith(
        "data:audio/wav;base64,"
    )


def test_transcribe_audio_uses_fun_asr_http(monkeypatch):
    monkeypatch.setattr(m, "_gateway_credentials", lambda: ("https://gateway.example/v1", "key"))
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return httpx.Response(
            200,
            json={"sentence": {"text": "你好，我是沈砚。"}},
        )

    monkeypatch.setattr(m.httpx, "post", fake_post)

    result = m.transcribe_audio(b"RIFF-wav", "voice.wav", language="中文")

    assert result["model"] == "fun-asr-flash-2026-06-15"
    assert result["text"] == "你好，我是沈砚。"
    payload = captured["json"]
    assert payload["parameters"]["format"] == "wav"
    assert payload["parameters"]["language_hints"] == ["zh"]
    assert payload["input"]["messages"][0]["content"][0]["input_audio"]["data"].startswith(
        "data:audio/wav;base64,"
    )


def test_transcribe_audio_rejects_unknown_suffix(monkeypatch):
    with pytest.raises(m.MultimodalError, match="不支持的格式"):
        m.transcribe_audio(b"data", "voice.txt")


def test_synthesize_speech_saves_wav(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(m, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(m, "_gateway_credentials", lambda: ("https://gateway", "key"))

    def fake_call(**kwargs):
        assert kwargs["voice"] == "Cherry"
        return SimpleNamespace(
            status_code=200,
            output={"audio": {"url": "https://example.com/voice.wav", "data": ""}},
        )

    monkeypatch.setattr("dashscope.audio.qwen_tts.SpeechSynthesizer.call", fake_call)
    monkeypatch.setattr(m, "_download", lambda url: (b"RIFF-wav", "audio/wav"))

    result = m.synthesize_speech("沈砚下山了。")

    assert result["model"] == "qwen3-tts-flash"
    assert result["url"].startswith("/media/audio/")
    assert Path(result["path"]).read_bytes() == b"RIFF-wav"


def test_translate_text_uses_translation_options(monkeypatch):
    monkeypatch.setattr(m, "_gateway_credentials", lambda: ("https://gateway", "key"))
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=200,
            output={
                "choices": [
                    {"message": {"role": "assistant", "content": "Shen Yan left."}}
                ]
            },
        )

    monkeypatch.setattr("dashscope.Generation.call", fake_call)

    result = m.translate_text("沈砚下山了。", target_lang="English")

    assert result["text"] == "Shen Yan left."
    assert captured["model"] == "qwen-mt-plus"
    assert captured["translation_options"] == {
        "source_lang": "Chinese",
        "target_lang": "English",
    }


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(media.router)
    app.dependency_overrides[current_user] = lambda: UserOut(id=1, username="tester")
    return TestClient(app)


def test_media_models_route(api_client):
    response = api_client.get("/api/v1/media/models")
    assert response.status_code == 200
    body = response.json()
    assert body["models"]["ocr"] == "qwen3.5-ocr"
    assert body["models"]["asr"] == "fun-asr-flash-2026-06-15"
    assert body["models"]["omni"] == "qwen3.8-max"
    assert body["models"]["translate"] == "qwen-mt-plus"


def test_generate_image_route(api_client, monkeypatch):
    monkeypatch.setattr(
        media.multimodal,
        "generate_image",
        lambda prompt, size="1024x1024", model=None: {
            "model": "qwen-image-3.0-pro",
            "size": size,
            "url": "/media/images/test.png",
            "bytes": 10,
        },
    )

    response = api_client.post(
        "/api/v1/media/images/generate",
        json={"prompt": "雨夜青石台阶", "size": "1024x1024"},
    )

    assert response.status_code == 200
    assert response.json()["url"] == "/media/images/test.png"


def test_generate_image_route_accepts_2k(api_client, monkeypatch):
    monkeypatch.setattr(
        media.multimodal,
        "generate_image",
        lambda prompt, size="1024x1024", model=None: {
            "model": "qwen-image-3.0-pro",
            "size": size,
            "url": "/media/images/test-2k.png",
            "bytes": 5308118,
        },
    )

    response = api_client.post(
        "/api/v1/media/images/generate",
        json={"prompt": "雨夜青石台阶", "size": "2048x2048"},
    )

    assert response.status_code == 200
    assert response.json()["size"] == "2048x2048"


def test_generate_image_route_rejects_bad_size(api_client):
    response = api_client.post(
        "/api/v1/media/images/generate",
        json={"prompt": "雨夜青石台阶", "size": "large"},
    )
    assert response.status_code == 422


def test_ocr_route_returns_text(api_client, monkeypatch):
    monkeypatch.setattr(
        media.multimodal,
        "ocr_image",
        lambda data, filename, prompt=None, model=None: {
            "model": "qwen3.5-ocr",
            "text": "沈砚被逐出山门",
        },
    )

    response = api_client.post(
        "/api/v1/media/ocr",
        files={"file": ("page.png", b"image", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "沈砚被逐出山门"


def test_ocr_route_rejects_unsupported_file_type(api_client):
    response = api_client.post(
        "/api/v1/media/ocr",
        files={"file": ("notes.txt", b"text", "text/plain")},
    )
    assert response.status_code == 400


def test_multimodal_page_and_assets_are_registered():
    from app.main import PROJECT_ROOT, app

    assert any(getattr(route, "path", None) == "/multimodal" for route in app.routes)
    assert (PROJECT_ROOT / "frontend" / "multimodal.html").is_file()
    assert (PROJECT_ROOT / "frontend" / "static" / "multimodal.css").is_file()
    assert (PROJECT_ROOT / "frontend" / "static" / "multimodal.js").is_file()
