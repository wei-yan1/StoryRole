"""Entity normalisation (RoleRAG Algorithm 1, re-implemented).

For each candidate, pull its top-k nearest neighbours from an entity vector
index, ask an arbiter whether they are the same character, union the answers,
then take connected components. A canonical name is picked per component.

The arbiter is injectable: tests use a deterministic rule arbiter, production
passes an LLM call. That keeps the algorithm measurable without a network.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Callable

from .entities import EntityCandidate
from ..llm import LLMClient, parse_json_object

Vector = tuple[float, ...]
Arbiter = Callable[[EntityCandidate, EntityCandidate], bool]


@dataclass(frozen=True)
class EntityGroup:
    canonical: str
    type: str
    aliases: tuple[str, ...]
    description: str
    mention_count: int
    first_chapter: int
    last_chapter: int

    @property
    def entity_id(self) -> str:
        digest = hashlib.sha1(self.canonical.encode("utf-8")).hexdigest()[:10]
        return f"ent:{digest}"


def normalize_candidates(
    candidates: list[EntityCandidate],
    *,
    top_k: int = 5,
    embed: Callable[[str], Vector] | None = None,
    arbiter: Arbiter | None = None,
) -> list[EntityGroup]:
    if not candidates:
        return []
    embed = embed or hashed_embedding
    arbiter = arbiter or rule_arbiter
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        roots = (find(left), find(right))
        if roots[0] != roots[1]:
            parent[roots[1]] = roots[0]

    # Cheap rule pass first: shared surface or containment. This is what saves
    # the LLM budget in Chinese novels where 字/号/官职 variants are common.
    for left, first in enumerate(candidates):
        for right in range(left + 1, len(candidates)):
            second = candidates[right]
            if first.type != second.type:
                continue
            if rule_arbiter(first, second):
                union(left, right)

    vectors = [embed(_profile_text(c)) for c in candidates]
    for index, candidate in enumerate(candidates):
        neighbours = _top_k(index, vectors, top_k)
        for neighbour in neighbours:
            if find(index) == find(neighbour):
                continue
            if arbiter(candidate, candidates[neighbour]):
                union(index, neighbour)

    groups: dict[int, list[EntityCandidate]] = {}
    for index in range(len(candidates)):
        groups.setdefault(find(index), []).append(candidates[index])

    result: list[EntityGroup] = []
    for members in groups.values():
        canonical = _pick_canonical(members)
        aliases = sorted({surface for member in members for surface in member.surfaces()} - {canonical.name})
        description = max((m.description for m in members), key=len, default="")
        result.append(
            EntityGroup(
                canonical=canonical.name,
                type=canonical.type,
                aliases=tuple(aliases),
                description=description,
                mention_count=sum(m.mention_count for m in members),
                first_chapter=min((m.first_chapter for m in members if m.first_chapter), default=0),
                last_chapter=max((m.last_chapter for m in members), default=0),
            )
        )
    return sorted(result, key=lambda g: (-g.mention_count, g.canonical))


def llm_arbiter(llm: LLMClient) -> Arbiter:
    """Production arbiter: one short JSON call per ambiguous pair."""

    def decide(left: EntityCandidate, right: EntityCandidate) -> bool:
        prompt = (
            "判断下面两个名字是否指同一实体。只输出 JSON：{\"same\": true/false}。\n"
            f"A：{left.name} / 别名 {left.aliases} / {left.description}\n"
            f"B：{right.name} / 别名 {right.aliases} / {right.description}"
        )
        return parse_json_object(llm.complete(prompt)).get("same") is True

    return decide


def rule_arbiter(left: EntityCandidate, right: EntityCandidate) -> bool:
    """Conservative same-entity check that never invents a merge."""
    left_surfaces = set(left.surfaces())
    right_surfaces = set(right.surfaces())
    if left_surfaces & right_surfaces:
        return True
    for small, big in ((left.name, right.name), (right.name, left.name)):
        if len(small) >= 2 and small in big:
            return True
    for alias in left.aliases:
        if len(alias) >= 2 and any(alias in surface for surface in right_surfaces):
            return True
    for alias in right.aliases:
        if len(alias) >= 2 and any(alias in surface for surface in left_surfaces):
            return True
    return False


def hashed_embedding(text: str, dimensions: int = 64) -> Vector:
    """Deterministic character-bigram hashing. No model, no network."""
    vector = [0.0] * dimensions
    cleaned = "".join(ch for ch in (text or "") if not ch.isspace())
    for index in range(max(1, len(cleaned) - 1)):
        bigram = cleaned[index : index + 2]
        slot = int(hashlib.md5(bigram.encode("utf-8")).hexdigest()[:8], 16) % dimensions
        vector[slot] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


def cosine(left: Vector, right: Vector) -> float:
    return sum(a * b for a, b in zip(left, right))


def _top_k(index: int, vectors: list[Vector], k: int) -> list[int]:
    scored = [
        (cosine(vectors[index], vectors[other]), other)
        for other in range(len(vectors))
        if other != index
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [other for _, other in scored[:k]]


def _profile_text(candidate: EntityCandidate) -> str:
    return " ".join([candidate.name, *candidate.aliases, candidate.description])


def _pick_canonical(members: list[EntityCandidate]) -> EntityCandidate:
    return max(members, key=lambda m: (m.mention_count, len(m.name), -len(m.name)))
