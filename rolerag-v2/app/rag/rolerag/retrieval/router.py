"""Query routing.

Two orthogonal decisions, deliberately kept separate:

1. scope  — can he answer at all (``reject``), from ``scope.py``
2. shape  — recall / probe / stance, from the wording of the question

v1 conflated these with quick/deep, which is a latency axis, not a semantics one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .scope import ScopeReport

RouteKind = Literal["recall", "probe", "stance", "reject"]

_RECALL = ("那次", "当时", "还记得", "那天", "后来", "之前", "从前", "当年", "听说")
_PROBE = ("为什么", "怎么会", "凭什么", "动机", "原因", "如何", "怎么想", "你怎么看", "关系", "知不知道", "是否知道", "认识")
_RELATION = ("关系", "怎么看", "知不知道", "是否知道", "背叛", "信任", "敌对", "欠", "恨", "认识")


@dataclass(frozen=True)
class RouteDecision:
    kind: RouteKind
    reason: str
    entities: tuple[str, ...] = ()
    query: str = ""
    multi_hop: bool = False


def route(query: str, scope: ScopeReport, *, plan: dict | None = None) -> RouteDecision:
    if scope.all_out_of_scope:
        reason = (
            f"越界：{('、'.join(scope.external_terms))}" if scope.external_terms else "越界：无可达实体"
        )
        return RouteDecision("reject", reason, tuple(e.name for e in scope.entities))

    unfamiliar = [item for item in scope.entities if not item.familiar]
    if unfamiliar:
        # A name he has no path to is not a name he may discuss, even if the
        # rest of the question is inside his world.
        return RouteDecision(
            "reject",
            "越界：不认识 " + "、".join(item.name for item in unfamiliar),
            tuple(item.name for item in unfamiliar),
        )

    text = query or ""
    intent = str((plan or {}).get("intent") or "")
    if intent == "future_probe" or (plan or {}).get("future_probe"):
        return RouteDecision(
            "reject",
            "Laya 判定为未来/结局问题；角色没有未来记忆",
            tuple(e.name for e in scope.entities),
            text,
        )
    if plan and plan.get("needs_relationship") and scope.entities:
        return RouteDecision(
            "probe", "Laya 判定为关系问题，走 ego-network",
            tuple(e.name for e in scope.entities), text, multi_hop=True,
        )
    if plan and (plan.get("needs_novel_search") or intent == "plot_or_fact") and scope.entities:
        return RouteDecision("recall", "Laya 判定为小说事实问题", tuple(e.name for e in scope.entities), text)
    if any(marker in text for marker in _RECALL):
        return RouteDecision("recall", "时间指代，按事件锚定", tuple(e.name for e in scope.entities), text)
    if any(marker in text for marker in _PROBE):
        return RouteDecision("probe", "动机或因果追问，走子图", tuple(e.name for e in scope.entities), text)
    from ..extract.events import TRIGGERS

    if any(verb in text for verb in TRIGGERS):
        # A bare action question ("潘寒杀申玉菲") is an event lookup, not a
        # stance question; otherwise it would return unrelated beliefs.
        return RouteDecision("recall", "动作事件，按事件锚定", tuple(e.name for e in scope.entities), text)
    if scope.is_general:
        return RouteDecision("stance", "抽象态度问题，不检索", ())
    return RouteDecision("stance", "默认表态", tuple(e.name for e in scope.entities))
