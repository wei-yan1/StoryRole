from app.core.config.model_catalog import classify_model, resolve_model


def test_role_env_override_wins(monkeypatch):
    monkeypatch.setenv("MODEL_IMAGE", "custom-image-model")
    assert resolve_model("image") == "custom-image-model"


def test_rerank_role_reads_project_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_RERANK_MODEL", "qwen3.7-text-rerank")
    assert resolve_model("rerank") == "qwen3.7-text-rerank"


def test_default_roles_use_flagship_multimodal_models(monkeypatch):
    for variable in (
        "MODEL_IMAGE",
        "MODEL_OCR",
        "MODEL_ASR",
        "MODEL_TTS",
        "MODEL_OMNI",
        "MODEL_TRANSLATE",
    ):
        monkeypatch.delenv(variable, raising=False)

    assert resolve_model("image") == "qwen-image-3.0-pro"
    assert resolve_model("asr") == "fun-asr-flash-2026-06-15"
    assert resolve_model("omni") == "qwen3.8-max"
    assert resolve_model("translate") == "qwen-mt-plus"


def test_classify_model_groups_non_llm_capabilities():
    assert classify_model("qwen3.7-text-embedding") == "embedding"
    assert classify_model("qwen3.7-text-rerank") == "rerank"
    assert classify_model("qwen-image-3.0-pro") == "image"
    assert classify_model("qwen3-tts-flash") == "tts"
    assert classify_model("qwen3.5-ocr") == "ocr"
    assert classify_model("qwen3.8-omni-flash-realtime") == "omni"
    assert classify_model("qwen-mt-uni") == "translation"
    assert classify_model("deepseek-v4.1-flash-1017") == "chat"
