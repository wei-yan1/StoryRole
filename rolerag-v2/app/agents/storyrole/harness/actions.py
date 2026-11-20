"""StoryRole action specs and handlers.

Each handler does exactly one capability and returns an `Observation`. It never
chooses the next action, never writes a checkpoint and never calls another
handler directly.
"""

from __future__ import annotations

from typing import Any

from app.harness.actions import ActionRegistry, ActionSpec, AgentAction, Observation


def _observation(action: str, data: dict[str, Any], *, degraded: bool = False) -> Observation:
    payload = dict(data or {})
    status = str(payload.pop("status", "degraded" if degraded else "ok"))
    error = str(payload.pop("error", ""))
    provenance = list(payload.pop("provenance", []) or [])
    if status not in {"ok", "degraded", "timeout", "error", "denied"}:
        status = "ok"
    return Observation(
        action=action, status=status, data=payload, error=error,
        provenance=provenance,
    )


def build_action_registry(
    planning: Any, recall: Any, cognition: Any, generation: Any, persistence: Any,
) -> ActionRegistry:
    registry = ActionRegistry()

    async def plan_turn(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("plan_turn", await planning.plan_turn(execution))

    async def understand_event(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = await planning.understand_event(execution)
        execution.state["understanding"] = data
        return _observation("understand_event", data)

    async def recall_role(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = await recall.recall_role(execution)
        execution.state["role_evidence"] = list(recall.turn.role_evidence)
        return _observation("recall_role", data)

    async def recall_memory(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("recall_user_memory", await recall.recall_memory(execution))

    async def recall_web(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("recall_web", await recall.recall_web(execution))

    async def relation_state(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("relation_state", await recall.relation_state(execution))

    async def timeline_guard(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("timeline_guard", await recall.timeline_guard(execution))

    async def cognition_action(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = await cognition.cognition(execution)
        return _observation("cognition", data, degraded=bool(data.get("degraded")))

    async def deep_plan(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("deep_plan", await cognition.deep_plan(execution))

    async def deep_retrieval(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("deep_retrieval", await cognition.deep_retrieval(execution))

    async def context_curate(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("context_curate", await cognition.context_curate(execution))

    async def deep_evidence(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("deep_evidence", await cognition.deep_evidence(execution))

    async def deep_cognition(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("deep_cognition", await cognition.deep_cognition(execution))

    def decide(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = generation.decide(execution)
        execution.state["decision"] = data
        return _observation("decide", data)

    def assemble_context(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = generation.assemble_context(execution)
        execution.state["context_manifest"] = {
            "estimated_tokens": data.get("estimated_tokens"),
            "trimmed": bool(data.get("trimmed")),
            "budget_trimmed": bool(data.get("budget_trimmed")),
        }
        if data.get("budget_trimmed"):
            generation.turn.degradations.append("harness_context_trimmed")
        # Trimming is the context layer doing its job, not a failed action.
        return _observation("assemble_context", data)

    async def express(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = await generation.express(execution)
        return _observation("express", data)

    async def review_action(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = await generation.review(execution)
        return _observation("review", data, degraded=not bool(data.get("accepted")))

    async def memory_decision(action: AgentAction, context: Any, execution: Any) -> Observation:
        return _observation("memory_decision", await generation.memory_decision(execution))

    def learn(action: AgentAction, context: Any, execution: Any) -> Observation:
        data = persistence.learn(execution)
        execution.state["final_answer"] = persistence.turn.final_answer
        return _observation("learn", data)

    def stop(action: AgentAction, context: Any, execution: Any) -> Observation:
        return Observation("stop", data={"stop_reason": "completed"})

    specs = [
        ActionSpec("plan_turn", "判断本轮需要哪些能力", (), "state", 1, ("identity", "situation", "constraints")),
        ActionSpec("understand_event", "理解用户这句话对角色意味着什么", ("plan_turn",), "state", 1, ("identity", "self_state", "situation", "history", "constraints")),
        ActionSpec("recall_role", "检索角色可见的小说证据", ("understand_event",), "tool", 1, ("identity", "self_state", "situation", "constraints")),
        ActionSpec("recall_user_memory", "检索当前用户相关长期记忆", ("understand_event",), "tool", 1, ("identity", "self_state", "situation", "constraints")),
        ActionSpec("recall_web", "显式联网时检索外部信息", ("understand_event",), "tool", 1, ("identity", "situation", "constraints")),
        ActionSpec("relation_state", "读取角色与来客的关系状态", ("understand_event",), "tool", 1, ("identity", "situation", "constraints")),
        ActionSpec("timeline_guard", "检查是否越过角色可见时期", ("understand_event",), "tool", 1, ("identity", "situation", "constraints")),
        ActionSpec("cognition", "形成角色认知", ("understand_event",), "model", 1, ("identity", "self_state", "situation", "memory", "constraints")),
        ActionSpec("deep_plan", "拆解复杂问题", ("understand_event",), "model", 1, ("identity", "situation", "constraints")),
        ActionSpec("deep_retrieval", "按复杂问题检索小说证据", ("deep_plan",), "tool", 1, ("identity", "situation", "constraints")),
        ActionSpec("context_curate", "整理本轮可用上下文", ("understand_event",), "model", 1, ("identity", "self_state", "situation", "memory", "constraints")),
        ActionSpec("deep_evidence", "综合证据而不二次检索", ("context_curate",), "model", 1, ("identity", "self_state", "situation", "memory", "constraints")),
        ActionSpec("deep_cognition", "形成深度角色认知", ("deep_evidence",), "model", 1, ("identity", "self_state", "situation", "memory", "constraints")),
        ActionSpec("decide", "形成本轮行动决定", ("understand_event",), "state", 1, ("identity", "self_state", "situation", "memory", "constraints")),
        ActionSpec("assemble_context", "按决定组装最终上下文", ("decide",), "state", 1, ("identity", "self_state", "situation", "memory", "decision", "history", "constraints")),
        ActionSpec("express", "按角色口吻生成回答", ("assemble_context",), "model", 1, ("identity", "self_state", "situation", "memory", "decision", "history", "constraints"), critical=True),
        ActionSpec("review", "独立评审草稿是否像角色", ("express",), "model", 1, ("identity", "decision", "memory", "constraints"), critical=True),
        ActionSpec("memory_decision", "判断本轮是否需要保存用户记忆", ("review",), "state", 1, ("identity", "decision", "constraints")),
        ActionSpec("learn", "把本轮实际经历写回主体状态", ("review",), "state", 1, ("identity", "self_state", "decision", "constraints")),
        ActionSpec("stop", "结束本轮", ("learn",), "control", 1, (), terminal=True),
    ]
    for spec in specs:
        registry.register(spec, {
            "plan_turn": plan_turn,
            "understand_event": understand_event,
            "recall_role": recall_role,
            "recall_user_memory": recall_memory,
            "recall_web": recall_web,
            "relation_state": relation_state,
            "timeline_guard": timeline_guard,
            "cognition": cognition_action,
            "deep_plan": deep_plan,
            "deep_retrieval": deep_retrieval,
            "context_curate": context_curate,
            "deep_evidence": deep_evidence,
            "deep_cognition": deep_cognition,
            "decide": decide,
            "assemble_context": assemble_context,
            "express": express,
            "review": review_action,
            "memory_decision": memory_decision,
            "learn": learn,
            "stop": stop,
        }[spec.name])
    return registry
