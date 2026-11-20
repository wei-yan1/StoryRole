"""LLM boundary.

Extraction and profiling are written against this protocol so the whole
pipeline can be exercised with ``FakeLLM`` (deterministic, no network) and
swapped for a real model in production.
"""

from __future__ import annotations

import json
from typing import Callable, Protocol


class LLMClient(Protocol):
    def complete(self, prompt: str, *, system: str = "") -> str: ...


class CallableLLM:
    """Adapt a plain function for tests and notebooks."""

    def __init__(self, fn: Callable[[str], str]) -> None:
        self._fn = fn

    def complete(self, prompt: str, *, system: str = "") -> str:
        return self._fn(system + "\n" + prompt if system else prompt)


class FakeLLM:
    """Queued responses, then a stable fallback. Never touches the network."""

    def __init__(self, responses: list[str] | None = None, fallback: str = "") -> None:
        self._responses = list(responses or [])
        self._fallback = fallback
        self.calls: list[str] = []

    def complete(self, prompt: str, *, system: str = "") -> str:
        self.calls.append(prompt)
        if self._responses:
            return self._responses.pop(0)
        return self._fallback


class OpenAICompatLLM:
    """Lazy adapter for OpenAI-compatible chat endpoints (DashScope, DeepSeek…)."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # imported lazily on purpose

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def complete(self, prompt: str, *, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""


def parse_json_object(raw: str) -> dict:
    """Tolerant JSON extraction for model output."""
    text = (raw or "").strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence) :]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


__all__ = ["LLMClient", "CallableLLM", "FakeLLM", "OpenAICompatLLM", "parse_json_object"]
