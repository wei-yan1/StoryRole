"""Chapter segmentation and ordinal normalisation."""

from __future__ import annotations

import re

from ..models import Chapter

_HEADING = re.compile(
    r"^\s*(?P<title>(第[一二三四五六七八九十百零〇0-9]+章|序章|楔子|尾声|后记|Chapter\s+\d+))"
    r"\s*(?P<rest>.*)$"
)


def split_chapters(text: str) -> list[Chapter]:
    """Split raw novel text into ordered chapters.

    The ordinal is the only time axis the projection is allowed to use, so it
    is assigned here and never recomputed from the title later.
    """
    lines = (text or "").splitlines()
    heads: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if not match:
            continue
        title = match.group("title").strip()
        rest = match.group("rest").strip()
        heads.append((index, f"{title} {rest}".strip()))

    if not heads:
        body = text.strip()
        return [Chapter(1, "全文", body)] if body else []

    chapters: list[Chapter] = []
    for position, (start, title) in enumerate(heads):
        end = heads[position + 1][0] if position + 1 < len(heads) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        chapters.append(Chapter(position + 1, title, body))

    preface = "\n".join(lines[: heads[0][0]]).strip()
    if preface:
        chapters.insert(0, Chapter(0, "前言", preface))
    return chapters


def ordinal_by_title(chapters: list[Chapter], title: str) -> int | None:
    """Best-effort mapping used when migrating string periods to ordinals."""
    title = (title or "").strip()
    if not title:
        return None
    if title.replace(" ", "") in {"序章", "序", "前言", "引子"}:
        return chapters[0].ordinal if chapters else None
    for chapter in chapters:
        if chapter.title == title or chapter.title.startswith(title):
            return chapter.ordinal
    number = _cn_number(title)
    if number is not None:
        for chapter in chapters:
            if _cn_number(chapter.title) == number:
                return chapter.ordinal
    return None


def _cn_number(text: str) -> int | None:
    match = re.search(r"第([一二三四五六七八九十百零〇0-9]+)章", text)
    if not match:
        return None
    raw = match.group(1)
    if raw.isdigit():
        return int(raw)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    if "百" in raw:
        left, _, right = raw.partition("百")
        hundreds = digits.get(left, 1) if left else 1
        tail = _cn_number(f"第{right}章") if right else 0
        return hundreds * 100 + (tail or 0)
    value = 0
    for char in raw:
        value = value * 10 + digits.get(char, 0)
    return value or None
