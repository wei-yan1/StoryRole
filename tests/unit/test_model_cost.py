import json

from app.observability.core import model_cost


def test_ollama_is_explicitly_free(monkeypatch):
    monkeypatch.setenv("MODEL_PRICING_JSON", json.dumps({"*": {"input_per_million": 99, "output_per_million": 99}}))
    assert model_cost("bge-m3", {"input_tokens": 1000, "output_tokens": 1000}, "ollama") == 0.0


def test_provider_scoped_price_and_cached_input(monkeypatch):
    monkeypatch.setenv(
        "MODEL_PRICING_JSON",
        json.dumps({"deepseek": {"deepseek-flash": {
            "input_per_million": 2,
            "cached_input_per_million": 0.2,
            "output_per_million": 8,
        }}}),
    )
    usage = {"input_tokens": 1_000_000, "cached_tokens": 400_000, "output_tokens": 1_000_000}
    assert model_cost("deepseek-flash", usage, "deepseek") == 9.28


def test_unconfigured_remote_price_is_unknown(monkeypatch):
    monkeypatch.setenv("MODEL_PRICING_JSON", "{}")
    assert model_cost("new-model", {"input_tokens": 1, "output_tokens": 1}, "deepseek") is None


def test_maas_endpoint_is_billed_as_dashscope(monkeypatch):
    monkeypatch.setenv(
        "MODEL_PRICING_JSON",
        json.dumps({"dashscope": {"deepseek-v4.1-flash-1017": {
            "input_per_million": 2,
            "cached_input_per_million": 0.2,
            "output_per_million": 8,
        }}}),
    )
    monkeypatch.setenv(
        "OPENAI_BASE_URL",
        "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    usage = {"input_tokens": 1_000_000, "cached_tokens": 400_000, "output_tokens": 1_000_000}
    assert model_cost("deepseek-v4.1-flash-1017", usage, "openai") == 9.28
