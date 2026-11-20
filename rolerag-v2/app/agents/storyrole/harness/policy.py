"""StoryRole policy: propose the next action, never execute it.

The policy only reads turn flags and runtime observations. It cannot call a
model, retrieve evidence, mutate the draft or bypass a guardrail.
"""

from __future__ import annotations

from typing import Any

from app.harness.actions import AgentAction
from app.harness.policy import PolicyView


class StoryRolePolicy:
    """A deterministic first policy with quick/deep branches.

    Deterministic does not mean "fixed workflow": every branch is chosen from
    the current plan, the completed action set and failed observations. A future
    model policy can replace this class without changing any action handler.
    """

    def __init__(self, turn: Any) -> None:
        self.turn = turn

    def next_action(self, view: PolicyView, state: dict[str, Any]) -> AgentAction | None:
        completed = set(view.completed_actions)
        if "plan_turn" not in completed:
            return AgentAction("plan_turn", reason="先判断本轮需要哪些能力")
        if self._failed(view, "plan_turn"):
            return AgentAction("stop", reason="计划阶段失败")
        if self.turn.mode == "deep":
            return self._deep_next(view, completed)
        return self._quick_next(view, completed)

    def _quick_next(self, view: PolicyView, completed: set[str]) -> AgentAction | None:
        if self.turn.understanding is None:
            return AgentAction("understand_event", reason="理解对方这一句")
        if self._failed(view, "understand_event"):
            return AgentAction("stop", reason="理解阶段失败")
        plan = self.turn.plan or {}
        if plan.get("needs_novel_search") and not self._attempted(view, "recall_role"):
            return AgentAction("recall_role", reason="需要角色可见证据")
        if plan.get("needs_memory") and not self._attempted(view, "recall_user_memory"):
            return AgentAction("recall_user_memory", reason="需要用户长期记忆")
        if str(self.turn.payload.get("web_mode") or "off") == "on" and not self._attempted(view, "recall_web"):
            return AgentAction("recall_web", reason="用户显式开启联网")
        if plan.get("needs_relationship") and not self._attempted(view, "relation_state"):
            return AgentAction("relation_state", reason="需要关系姿态")
        if plan.get("needs_timeline_check") and not self._attempted(view, "timeline_guard"):
            return AgentAction("timeline_guard", reason="需要时期边界检查")
        if (
            not self._attempted(view, "cognition")
            and getattr(self.turn.understanding, "user_move", "") not in {"greeting", "smalltalk"}
        ):
            return AgentAction("cognition", reason="先形成角色认知")
        if "decide" not in completed:
            return AgentAction("decide", reason="回忆完成后再决定行动")
        if "assemble_context" not in completed:
            return AgentAction("assemble_context", reason="按决定组装本轮上下文")
        if "express" not in completed:
            return AgentAction("express", reason="按行动决定生成回答")
        if "review" not in completed:
            return AgentAction("review", reason="独立评审草稿")
        if "learn" not in completed:
            return AgentAction("learn", reason="把实际经历写回主体状态")
        return AgentAction("stop", reason="本轮完成")

    def _deep_next(self, view: PolicyView, completed: set[str]) -> AgentAction | None:
        if self.turn.understanding is None:
            return AgentAction("understand_event", reason="理解对方这一句")
        if self._failed(view, "understand_event"):
            return AgentAction("stop", reason="理解阶段失败")
        plan = self.turn.plan or {}
        if not self._attempted(view, "recall_role"):
            return AgentAction("recall_role", reason="深度模式需要角色可见证据")
        if plan.get("needs_memory") and not self._attempted(view, "recall_user_memory"):
            return AgentAction("recall_user_memory", reason="深度模式需要用户记忆")
        if plan.get("needs_relationship") and not self._attempted(view, "relation_state"):
            return AgentAction("relation_state", reason="深度模式需要关系姿态")
        if plan.get("needs_timeline_check") and not self._attempted(view, "timeline_guard"):
            return AgentAction("timeline_guard", reason="深度模式需要时期边界")
        if not self._attempted(view, "deep_plan"):
            return AgentAction("deep_plan", reason="拆解复杂问题")
        if not self._attempted(view, "deep_retrieval"):
            return AgentAction("deep_retrieval", reason="按复杂问题检索证据")
        if not self._attempted(view, "context_curate"):
            return AgentAction("context_curate", reason="整理深度上下文")
        if not self._attempted(view, "deep_evidence"):
            return AgentAction("deep_evidence", reason="综合证据")
        if not self._attempted(view, "deep_cognition"):
            return AgentAction("deep_cognition", reason="形成深度角色认知")
        if "decide" not in completed:
            return AgentAction("decide", reason="认知完成后决定行动")
        if "assemble_context" not in completed:
            return AgentAction("assemble_context", reason="按决定组装本轮上下文")
        if "express" not in completed:
            return AgentAction("express", reason="按行动决定生成回答")
        if "review" not in completed:
            return AgentAction("review", reason="独立评审草稿")
        if "memory_decision" not in completed:
            return AgentAction("memory_decision", reason="判断是否保存本轮记忆")
        if "learn" not in completed:
            return AgentAction("learn", reason="把实际经历写回主体状态")
        return AgentAction("stop", reason="本轮完成")

    @staticmethod
    def _attempted(view: PolicyView, action: str) -> bool:
        return action in view.completed_actions or any(
            item.action == action for item in view.observations
        )

    @staticmethod
    def _failed(view: PolicyView, action: str) -> bool:
        return any(
            item.action == action and item.status in {"error", "timeout"}
            for item in view.observations
        )

    def finalize(self, state: dict[str, Any], execution: Any) -> dict[str, Any]:
        return {
            "final_answer": self.turn.final_answer or self.turn.draft or state.get("final_answer") or "",
        }
