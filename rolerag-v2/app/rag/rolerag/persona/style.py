"""Style fingerprint and post-generation acceptance.

Style is not a sentence in a profile ("speaks concisely"). It is a measurable
distribution plus a negative list. The loop is: generate, measure, rewrite once
with a concrete instruction, then give up and log a score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENTENCE = re.compile(r"[^。！？!?]+[。！？!?]?")
DEFAULT_BANNED = (
    "作为一个AI",
    "作为人工智能",
    "总而言之",
    "综上所述",
    "首先",
    "其次",
    "需要注意的是",
    "希望这对你有帮助",
    "总的来说",
    "综上所述",
)


@dataclass(frozen=True)
class StyleProfile:
    median_chars: float = 12.0
    question_rate: float = 0.2
    exclamation_rate: float = 0.05
    catchphrases: tuple[str, ...] = ()
    banned: tuple[str, ...] = DEFAULT_BANNED
    address_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StyleReport:
    ok: bool
    failures: tuple[str, ...] = ()
    instruction: str = ""
    score: float = 1.0


def sentences(text: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE.findall(text or "") if piece.strip()]


def fingerprint(texts: list[str], *, catchphrases: tuple[str, ...] = ()) -> StyleProfile:
    all_sentences = [sentence for text in texts for sentence in sentences(text)]
    if not all_sentences:
        return StyleProfile(catchphrases=catchphrases)
    lengths = sorted(_char_len(s) for s in all_sentences)
    median = lengths[len(lengths) // 2]
    question_rate = sum(1 for s in all_sentences if "？" in s or "?" in s) / len(all_sentences)
    exclamation_rate = sum(1 for s in all_sentences if "！" in s or "!" in s) / len(all_sentences)
    return StyleProfile(
        median_chars=float(median),
        question_rate=round(question_rate, 2),
        exclamation_rate=round(exclamation_rate, 2),
        catchphrases=catchphrases,
    )


def measure(text: str) -> dict[str, float]:
    rows = sentences(text)
    if not rows:
        return {"median_chars": 0.0, "question_rate": 0.0, "exclamation_rate": 0.0}
    lengths = sorted(_char_len(row) for row in rows)
    return {
        "median_chars": float(lengths[len(lengths) // 2]),
        "question_rate": round(sum(1 for r in rows if "？" in r or "?" in r) / len(rows), 2),
        "exclamation_rate": round(sum(1 for r in rows if "！" in r or "!" in r) / len(rows), 2),
    }


def check(
    profile: StyleProfile,
    text: str,
    *,
    banned_extra: tuple[str, ...] = (),
    unknown_terms: tuple[str, ...] = (),
    allow_terse: bool = False,
) -> StyleReport:
    failures: list[str] = []
    stats = measure(text)

    if profile.median_chars > 0 and not allow_terse:
        deviation = abs(stats["median_chars"] - profile.median_chars) / profile.median_chars
        if deviation > 0.8:
            failures.append(f"句长偏离{deviation:.0%}")
    if abs(stats["question_rate"] - profile.question_rate) > 0.15:
        failures.append(f"问句率{stats['question_rate']:.2f}")
    if abs(stats["exclamation_rate"] - profile.exclamation_rate) > 0.15:
        failures.append(f"感叹率{stats['exclamation_rate']:.2f}")

    banned = tuple(DEFAULT_BANNED) + tuple(profile.banned) + tuple(banned_extra)
    hit_words = [word for word in banned if word and word in (text or "")]
    if hit_words:
        failures.append("禁用表达：" + "、".join(hit_words[:3]))

    leaked = [term for term in unknown_terms if term and term in (text or "")]
    if leaked:
        failures.append("越界提及：" + "、".join(leaked[:3]))

    score = max(0.0, 1.0 - 0.2 * len(failures))
    instruction = _instruction(stats, profile, failures, unknown_terms)
    return StyleReport(ok=not failures, failures=tuple(failures), instruction=instruction, score=round(score, 2))


def _instruction(
    stats: dict[str, float],
    profile: StyleProfile,
    failures: list[str],
    unknown_terms: tuple[str, ...],
) -> str:
    parts: list[str] = []
    if any("句长" in item for item in failures):
        parts.append(f"句子压到{int(profile.median_chars)}字上下")
    if any("问句率" in item for item in failures):
        parts.append("加一个反问" if stats["question_rate"] < profile.question_rate else "去掉多余的提问")
    if any("禁用表达" in item for item in failures):
        parts.append("去掉总结腔与书面语")
    if any("越界" in item for item in failures):
        parts.append(f"不要提：{'、'.join(unknown_terms[:2])}")
    return "；".join(parts)


def _char_len(sentence: str) -> int:
    return len(re.sub(r"[，,、；;\s“”\"']", "", sentence))
