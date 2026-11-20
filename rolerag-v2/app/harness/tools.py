"""Minimal capability registry and result distillation.

Harness engineering's tool layer is not "more tools". It is a small, explicit
set of capabilities with a bounded result shape, so a large MCP result cannot
crowd out the character's identity on the next turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    purpose: str
    source: str
    schema: dict[str, Any] = field(default_factory=dict)
    distiller: str = "identity"


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit]


def _unique(items: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        value = str(item.get(key) or item.get("text") or "")
        if value in seen:
            continue
        seen.add(value)
        output.append(item)
    return output


def distill_evidence(items: list[dict[str, Any]] | None, *, limit: int = 6, text_limit: int = 240) -> list[dict[str, Any]]:
    """Keep provenance, drop the full document text and duplicate rows."""
    rows: list[dict[str, Any]] = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("text") or item.get("summary") or item.get("content"), text_limit)
        if not text:
            continue
        rows.append({
            "kind": str(item.get("kind") or "evidence"),
            "text": text,
            "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
            "source": str(item.get("source") or item.get("thread_id") or ""),
            "visibility": str(item.get("visibility") or ""),
        })
    rows = _unique(rows, "chunk_id")
    return rows[:limit]


def distill_memories(items: list[dict[str, Any]] | None, *, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("content") or item.get("summary"), 220)
        if not text:
            continue
        rows.append({
            "content": text,
            "importance": round(float(item.get("importance") or 0.0), 2),
            "score": round(float(item.get("score") or 0.0), 2),
        })
    return _unique(rows, "content")[:limit]


def distill_web(items: list[dict[str, Any]] | None, *, limit: int = 6) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        title = _clip(item.get("title") or "", 80)
        snippet = _clip(item.get("snippet") or item.get("content") or item.get("text"), 160)
        if not (title or snippet):
            continue
        rows.append({"title": title, "url": str(item.get("url") or ""), "snippet": snippet})
    return _unique(rows, "url")[:limit]


def distill_relationship(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    user = value.get("user_relationship") or value
    if not isinstance(user, dict):
        return {}
    return {
        "trust": round(float(user.get("trust", 0.5)), 2),
        "intimacy": round(float(user.get("intimacy", 0.0)), 2),
        "tension": round(float(user.get("tension", 0.0)), 2),
        "dependency": round(float(user.get("dependency", 0.0)), 2),
        "recent_turns": list((user.get("state") or {}).get("recent_turns") or [])[-3:],
    }


class CapabilityRegistry:
    """A declarative list, not a second execution framework."""

    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> CapabilitySpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "purpose": spec.purpose,
                "source": spec.source,
                "distiller": spec.distiller,
            }
            for spec in self._specs.values()
        ]


def default_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(
        "rolerag.evidence", "Visible evidence inside the character's period boundary",
        "retrieve_from_manifest", {"message": "str", "period_id": "int|null"}, "distill_evidence",
    ))
    registry.register(CapabilitySpec(
        "memory.search", "User long-term memory relevant to this turn",
        "MemoryTool.search_items", {"query": "str", "limit": "int"}, "distill_memories",
    ))
    registry.register(CapabilitySpec(
        "web.search", "External evidence when web mode is explicitly on",
        "web-search", {"query": "str", "max_results": "int"}, "distill_web",
    ))
    registry.register(CapabilitySpec(
        "relationship.state", "Relationship state toward the current user",
        "relationship-state", {"character_id": "int"}, "distill_relationship",
    ))
    registry.register(CapabilitySpec(
        "timeline.guard", "Knowledge and spoiler boundary for this turn",
        "timeline-guard", {"message": "str"}, "identity",
    ))
    registry.register(CapabilitySpec(
        "persona.contract", "Who this character is, owned by Nuwa",
        "build_persona_contract", {"profile": "dict"}, "contract",
    ))
    return registry


def tool_trace(registry: CapabilityRegistry, called: list[str]) -> list[dict[str, Any]]:
    """Return a compact trace of which capabilities this turn actually used."""
    output = []
    for name in called:
        spec = registry.get(name)
        if spec is not None:
            output.append({"name": name, "source": spec.source, "distiller": spec.distiller})
    return output
