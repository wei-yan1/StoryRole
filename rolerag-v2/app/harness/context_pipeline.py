"""Per-action context views for the bounded agent harness.

The old `build_context_manifest()` assembled one big block and the controller
decided when to show it. This pipeline keeps the same sections but exposes only
the sections an action is allowed to see. That is the difference between
"context as a pile" and "context as an action-scoped view".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _estimate(lines: list[str]) -> int:
    return max(1, sum(len(item) for item in lines) // 2)


@dataclass
class ContextView:
    action: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    withheld: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    rendered: str = ""
    trimmed: bool = False
    level: str = "detail"

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "sections": {key: list(value) for key, value in self.sections.items()},
            "withheld": list(self.withheld),
            "estimated_tokens": self.estimated_tokens,
            "rendered_chars": len(self.rendered),
            "trimmed": bool(self.trimmed),
            "level": self.level,
        }


# Actions may see only the sections listed here. The review action deliberately
# does not see `situation` (the generator's interpretation) or raw history;
# the independent review packet is built separately.
_ACTION_VIEWS: dict[str, set[str]] = {
    "plan_turn": {"identity", "situation", "constraints"},
    "understand_event": {"identity", "self_state", "situation", "history", "constraints"},
    "recall_role": {"identity", "self_state", "situation", "constraints"},
    "recall_user_memory": {"identity", "self_state", "situation", "constraints"},
    "recall_web": {"identity", "self_state", "situation", "constraints"},
    "relation_state": {"identity", "self_state", "situation", "constraints"},
    "timeline_guard": {"identity", "self_state", "situation", "constraints"},
    "cognition": {"identity", "self_state", "situation", "memory", "constraints"},
    "decide": {"identity", "self_state", "situation", "memory", "constraints"},
    "assemble_context": {"identity", "self_state", "situation", "memory", "decision", "history", "constraints"},
    "express": {"identity", "self_state", "situation", "decision", "memory", "history", "constraints"},
    "review": {"identity", "decision", "memory", "constraints"},
    "learn": {"identity", "self_state", "decision", "constraints"},
    "stop": {"identity", "self_state", "constraints"},
}

# Early actions get summaries and pointers. Only express/assemble need detail.
_SUMMARY_ACTIONS: set[str] = {
    "plan_turn", "understand_event", "recall_role", "recall_user_memory",
    "recall_web", "relation_state", "timeline_guard", "review", "learn",
}

# Order matters when the view has to fit a token budget. Identity and
# constraints are never dropped; tail material is dropped first.
_TRIM_ORDER: tuple[str, ...] = (
    "history", "memory", "role_detail", "situation", "self_state",
    "decision", "identity", "constraints",
)



class ContextPipeline:
    """Turn a `ContextManifest` into one action-scoped view at a time."""

    def __init__(self, manifest: Any, *, max_tokens: int = 0) -> None:
        self.manifest = manifest
        self.max_tokens = max(0, int(max_tokens))
        self._sections = {section.name: section for section in manifest.sections}

    def _section_lines(self, name: str, *, level: str = "detail") -> list[str]:
        section = self._sections.get(name)
        if section is None:
            return []
        lines = list(section.lines)
        if level == "summary" and name in {"history", "memory", "situation"}:
            # Early actions need enough to decide what to recall, not the whole
            # evidence body. Keep the first lines as pointers, not a teaser pile.
            return lines[:2]
        return lines

    def allowed_sections(self, action: str) -> set[str]:
        return set(_ACTION_VIEWS.get(action, {"identity", "constraints"}))

    def _trim(self, sections: dict[str, list[str]]) -> tuple[dict[str, list[str]], bool]:
        if self.max_tokens <= 0:
            return sections, False
        budget = self.max_tokens
        trimmed = False
        for name in _TRIM_ORDER:
            if name not in sections:
                continue
            lines = sections[name]
            cost = _estimate(lines)
            if cost <= budget:
                budget -= cost
                continue
            if name in {"identity", "decision", "constraints", "self_state"}:
                # These are non-negotiable: keep at least one faithful line.
                keep = max(1, len(lines))
                sections[name] = lines[:keep]
                trimmed = True
                continue
            keep = 0
            while keep < len(lines) and _estimate(lines[: keep + 1]) <= budget:
                keep += 1
            if keep == 0:
                sections.pop(name, None)
            else:
                sections[name] = lines[:keep]
            trimmed = True
            budget = max(0, budget - _estimate(sections.get(name, [])))
        return sections, trimmed

    def view(self, action: str, *, level: str | None = None) -> ContextView:
        allowed = self.allowed_sections(action)
        effective_level = level or ("summary" if action in _SUMMARY_ACTIONS else "detail")
        sections: dict[str, list[str]] = {}
        withheld: list[str] = []
        for name in self._sections:
            lines = self._section_lines(name, level=effective_level)
            if name in allowed:
                if lines:
                    sections[name] = lines
            elif lines:
                withheld.append(name)
        sections, trimmed = self._trim(sections)
        rendered_blocks: list[str] = []
        labels = {
            "identity": "身份｜我是谁",
            "self_state": "连续自我｜我最近在意什么、做过什么",
            "situation": "处境｜我怎样理解这件事",
            "decision": "行动｜本轮我选择怎样回应",
            "memory": "回忆｜本轮实际取回的材料与来源",
            "history": "历史｜当前话题之前的来往",
            "constraints": "约束｜不能越过的边界",
        }
        for name, lines in sections.items():
            rendered_blocks.append(f"[{labels.get(name, name)}]\n" + "\n".join(lines))
        rendered = "\n\n".join(rendered_blocks)
        return ContextView(
            action=action,
            sections=sections,
            withheld=withheld,
            estimated_tokens=_estimate([line for lines in sections.values() for line in lines]),
            rendered=rendered,
            trimmed=trimmed or self.manifest.trimmed,
            level=effective_level,
        )


    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": {
                name: sorted(self.allowed_sections(name))
                for name in sorted(_ACTION_VIEWS)
            },
            "sections": [section.name for section in self.manifest.sections],
            "estimated_tokens": self.manifest.estimated_tokens,
        }
