"""Live smoke test for the multimodal API routes.

Uses a disposable local account and the configured DashScope gateway. Results are
written to docs/media-api-smoke.json for the delivery evidence; tokens are never
persisted.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media-api-smoke.json"
USERNAME = "media_api_smoke"
PASSWORD = "smoke-pass-1234"


def auth_headers() -> dict[str, str]:
    payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(f"{BASE}/api/v1/auth/login", json=payload, timeout=15)
    if response.status_code == 401:
        response = requests.post(f"{BASE}/api/v1/auth/register", json=payload, timeout=15)
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def record(results: list[dict], name: str, call):
    started = time.time()
    try:
        value = call()
        results.append({"name": name, "ok": True, "elapsed_ms": round((time.time() - started) * 1000), "result": value})
        return value
    except Exception as error:  # noqa: BLE001 - report the provider error as evidence
        results.append({"name": name, "ok": False, "elapsed_ms": round((time.time() - started) * 1000), "error": str(error)[:600]})
        return None


def main() -> None:
    headers = auth_headers()
    results: list[dict] = []

    record(results, "models", lambda: requests.get(f"{BASE}/api/v1/media/models", headers=headers, timeout=20).json())

    def translate():
        response = requests.post(
            f"{BASE}/api/v1/media/translate",
            headers=headers,
            json={"text": "你好，很高兴见到你。", "source_lang": "Chinese", "target_lang": "English"},
            timeout=90,
        )
        response.raise_for_status()
        return response.json()

    record(results, "translate", translate)

    page_shot = ROOT / "docs" / "ui-shots" / "media-read-1440.png"
    if page_shot.exists():
        def ocr():
            with page_shot.open("rb") as handle:
                response = requests.post(
                    f"{BASE}/api/v1/media/ocr",
                    headers=headers,
                    files={"file": (page_shot.name, handle, "image/png")},
                    data={"prompt": "只提取页面中的主要标题与栏目文字。"},
                    timeout=120,
                )
            response.raise_for_status()
            return response.json()

        record(results, "ocr", ocr)

        def describe():
            with page_shot.open("rb") as handle:
                response = requests.post(
                    f"{BASE}/api/v1/media/images/describe",
                    headers=headers,
                    files={"file": (page_shot.name, handle, "image/png")},
                    data={"prompt": "用两句话说明这张界面截图的主要区域和用途。"},
                    timeout=120,
                )
            response.raise_for_status()
            return response.json()

        record(results, "describe", describe)

    def generate():
        response = requests.post(
            f"{BASE}/api/v1/media/images/generate",
            headers=headers,
            json={"prompt": "黄昏的雪原上，一座巨大的射电望远镜，暖金色天光，电影感，广角", "size": "1024x1024"},
            timeout=180,
        )
        response.raise_for_status()
        return response.json()

    image = record(results, "image_generate", generate)

    speech = record(
        results,
        "speech",
        lambda: requests.post(
            f"{BASE}/api/v1/media/audio/speech",
            headers=headers,
            json={"text": "你好，这是 StoryRole 的语音测试。", "voice": "Cherry"},
            timeout=120,
        ).json(),
    )

    if speech and speech.get("url"):
        def transcribe():
            audio_url = speech["url"]
            if audio_url.startswith("/"):
                audio_url = BASE + audio_url
            audio = requests.get(audio_url, timeout=60)
            audio.raise_for_status()
            response = requests.post(
                f"{BASE}/api/v1/media/audio/transcribe",
                headers=headers,
                files={"file": ("speech.wav", audio.content, "audio/wav")},
                data={"language": "zh"},
                timeout=180,
            )
            response.raise_for_status()
            return response.json()

        record(results, "transcribe", transcribe)

    summary = {
        "server": BASE,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": sum(1 for item in results if item["ok"]),
        "total": len(results),
        "results": results,
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("passed", "total", "results")}, ensure_ascii=False, indent=2)[:6000])


if __name__ == "__main__":
    main()
