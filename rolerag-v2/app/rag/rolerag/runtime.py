"""Runtime bridging processed novel chunks to RoleRAG.

The API stores one JSONL chunk file per imported novel. RoleRAG needs chapter
ordinals, so chunks are grouped by (book, section_index) when present, otherwise
by a fixed window. This module is pure: no database, no HTTP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .build import BuildOutcome, build_all
from .chat.orchestrator import Reply, chat_turn, LLMRenderer, TemplateRenderer
from .extract.chapters import ordinal_by_title
from .store import InMemoryGraphStore


@dataclass
class RoleRAGRuntime:
    store: InMemoryGraphStore
    cutoff: int
    persisted: bool = False

    def answer(
        self,
        character_name: str,
        message: str,
        *,
        cutoff: int | None = None,
        renderer=None,
        profile_overlay=None,
        plan: dict | None = None,
    ) -> Reply:
        entity = self.store.find_entity(character_name)
        if entity is None:
            raise KeyError(f"character not found: {character_name}")
        return chat_turn(
            self.store,
            entity.id,
            cutoff if cutoff is not None else self.cutoff,
            message,
            renderer=renderer,
            profile_overlay=profile_overlay,
            plan=plan,
        )

    def match_cutoff_for_period(self, chapter_start: str | None, chapter_end: str | None = None) -> int | None:
        for title in (chapter_end, chapter_start):
            if title:
                ordinal = ordinal_by_title(self.store.chapters(), title)
                if ordinal is not None:
                    return max(1, ordinal)
        return None

    def cutoff_for_period(self, chapter_start: str | None, chapter_end: str | None = None) -> int:
        matched = self.match_cutoff_for_period(chapter_start, chapter_end)
        return matched if matched is not None else self.cutoff


def build_from_chunks(
    chunks_path: str | Path,
    *,
    novel_id: str,
    hints: list[dict] | None = None,
    org_members: dict[str, set[str]] | None = None,
    arbiter=None,
    embed=None,
    fact_llm=None,
) -> BuildOutcome:
    rows = [
        json.loads(line)
        for line in Path(chunks_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("empty chunk file")

    groups: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for index, row in enumerate(rows):
        metadata = row.get("metadata") or {}
        book = str(metadata.get("book") or metadata.get("section_title") or "")
        chapter_number = str(metadata.get("chapter_number") or "").strip()
        section = metadata.get("section_index")
        if chapter_number:
            # The API's import chunks carry a real chapter number; grouping by
            # it is what makes period titles map to the right ordinal.
            key = (book, f"chapter:{chapter_number}")
        elif section is not None:
            key = (book, f"section:{section}")
        else:
            key = ("", f"window:{index // 5}")
        groups.setdefault(key, []).append((index, str(row.get("text") or "")))

    blocks = []
    for ordinal, key in enumerate(sorted(groups, key=lambda k: min(i for i, _ in groups[k])), start=1):
        book, marker = key
        if marker.startswith("chapter:"):
            label = f"第{marker.split(':', 1)[1]}章"
        elif marker.startswith("section:"):
            label = f"{book} 第{marker.split(':', 1)[1]}节" if book else f"第{marker.split(':', 1)[1]}节"
        else:
            label = f"第{marker.split(':', 1)[1]}节" if book else "正文"
        body = "\n".join(text for _, text in sorted(groups[key]))
        if marker.startswith("chapter:"):
            # Do not prepend a second "第N章": the real chapter heading is
            # already the label, and duplicated headings inflate chapter count.
            blocks.append(f"{label}\n{body}")
        else:
            blocks.append(f"第{_cn(ordinal)}章 {label}\n{body}")
    return build_all(
        "\n\n".join(blocks),
        novel_id=novel_id,
        hints=hints,
        org_members=org_members,
        arbiter=arbiter,
        embed=embed,
        fact_llm=fact_llm,
    )


def renderer_from_env(*, force_template: bool = False):
    """Real model when credentials exist, deterministic template otherwise."""
    if force_template:
        return TemplateRenderer()
    import os

    model = os.getenv("ROLERAG_LLM_MODEL") or os.getenv("STORYROLE_CHAT_MODEL") or os.getenv(
        "DEFAULT_CHAT_MODEL", "deepseek-v4.1-flash-1017"
    )
    # 项目固定约束：所有语言模型统一经阿里云 MaaS 转发，优先 OPENAI_*。
    # deepseek-v4.1-flash-1017 是阿里云上的模型 ID，不代表 DeepSeek 官方
    # API；DEEPSEEK_* 只作回滚配置，禁止按模型名前缀自动切换。
    key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
    if not key:
        return TemplateRenderer()
    from .llm import OpenAICompatLLM

    return LLMRenderer(
        OpenAICompatLLM(
            model,
            base_url=base_url,
            api_key=key,
            temperature=0.4,
            max_tokens=int(os.getenv("ROLERAG_MAX_TOKENS", "2048")),
        )
    )


def _cn(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value - 10] if value > 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)
