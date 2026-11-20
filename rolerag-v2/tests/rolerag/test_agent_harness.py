"""Regression tests for the v3 Agent Harness runtime.

The tests exercise the runtime as a runtime: the policy only proposes actions,
handlers are isolated, dependencies and hard budgets are enforced, context is
action-scoped, and a checkpoint can be resumed.
"""

from __future__ import annotations

import asyncio
from contextlib import nullcontext

import pytest

from app.harness.actions import ActionRegistry, ActionSpec, AgentAction, Observation
from app.agents.storyrole.harness.context_manifest import ContextManifest, ContextSection
from app.harness.context_pipeline import ContextPipeline
from app.agents.storyrole.harness.handoff import TurnHandoff
from app.harness.runtime import AgentHarness, AgentView
from app.harness.state import InMemoryInteractionStateStore
from app.harness.tool_runtime import ToolRuntime, ToolSpec, validate_args
from app.harness.types import SubjectState, TurnBudget, TurnScope
from app.agents.storyrole.harness.update import update_interaction_state


def _scope() -> TurnScope:
    return TurnScope("novel", 1, 2, 7, thread_id="harness-test", user_id=2)


def _manifest() -> ContextManifest:
    sections = [
        ContextSection("identity", "identity", 0, ["我是罗辑。"]),
        ContextSection("self_state", "state", 1, ["我仍在观察。"]),
        ContextSection("situation", "situation", 2, ["对方在试探。"]),
        ContextSection("decision", "decision", 3, ["先守住边界。"]),
        ContextSection("memory", "memory", 4, ["可见证据 A"]),
        ContextSection("history", "history", 5, ["用户：你好"]),
        ContextSection("constraints", "constraints", 6, ["不编造。"]),
    ]
    return ContextManifest(
        sections=sections, estimated_tokens=100, dropped_lines=0,
        trimmed=False, snapshot=None,  # type: ignore[arg-type]
    )


class _Policy:
    def __init__(self, sequence: list[str], *, loop: bool = False) -> None:
        self.sequence = sequence
        self.loop = loop

    def next_action(self, view: AgentView, state: dict) -> AgentAction | None:
        if self.loop:
            return AgentAction("express", reason="repeat")
        if not self.sequence:
            return None
        return AgentAction(self.sequence.pop(0))

    def finalize(self, state: dict, execution: object) -> dict:
        return {"final_answer": state.get("final_answer", "")}


def _registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(ActionSpec("understand_event", "理解", (), "state", 1), lambda *_: Observation("understand_event"))
    registry.register(ActionSpec("decide", "决定", ("understand_event",), "state", 1), lambda *_: Observation("decide"))
    registry.register(ActionSpec("express", "生成", ("decide",), "model", 1), lambda *_: Observation("express"))
    registry.register(ActionSpec("review", "评审", ("express",), "model", 1), lambda *_: Observation("review"))
    registry.register(ActionSpec("learn", "学习", ("review",), "state", 1), lambda *_: Observation("learn"))
    registry.register(ActionSpec("stop", "结束", ("learn",), "control", 1, terminal=True), lambda *_: Observation("stop"))
    return registry


def _full_registry(tool_runtime: ToolRuntime) -> ActionRegistry:
    registry = ActionRegistry()

    async def recall(action, context, execution):
        result = await execution.call_tool("role.evidence", {})
        return Observation("recall_role", status=result.status, data=result.data, error=result.error)

    def express(action, context, execution):
        execution.charge_model(stage="express", tokens=12)
        return Observation("express", data={"answer": "我不会替所有人决定。"})

    def review(action, context, execution):
        execution.charge_model(stage="review", tokens=3)
        return Observation("review", data={"pass": True, "score": 0.8})

    def learn(action, context, execution):
        state = update_interaction_state(
            execution.subject_state,
            user_message="你必须替所有人决定。",
            answer="我不会替所有人决定。",
            appraisal={"action": "hold_boundary", "stakes": "守住判断"},
            accepted=True, score=0.8, attempts=1,
        )
        execution.state["subject_state"] = state
        execution.state["final_answer"] = "我不会替所有人决定。"
        return Observation("learn", data={"turn": state.turn_count})

    registry.register(ActionSpec("understand_event", "理解", (), "state", 1), lambda *_: Observation("understand_event"))
    registry.register(ActionSpec("recall_role", "检索", ("understand_event",), "tool", 1), recall)
    registry.register(ActionSpec("decide", "决定", ("recall_role",), "state", 1), lambda *_: Observation("decide"))
    registry.register(ActionSpec("express", "生成", ("decide",), "model", 1), express)
    registry.register(ActionSpec("review", "评审", ("express",), "model", 1), review)
    registry.register(ActionSpec("learn", "学习", ("review",), "state", 1), learn)
    registry.register(ActionSpec("stop", "结束", ("learn",), "control", 1, terminal=True), lambda *_: Observation("stop"))
    return registry


def test_context_pipeline_is_action_scoped_and_review_is_clean() -> None:
    pipeline = ContextPipeline(_manifest())
    understand = pipeline.view("understand_event")
    recall = pipeline.view("recall_role")
    express = pipeline.view("express")
    review = pipeline.view("review")
    assert "decision" not in understand.sections
    assert "memory" not in understand.sections
    assert set(express.sections) == {
        "identity", "self_state", "situation", "decision", "memory", "history", "constraints",
    }
    assert "situation" not in review.sections
    assert "history" not in review.sections
    assert "decision" in review.sections
    assert review.withheld


def test_turn_handoff_is_compact_and_roundtrips() -> None:
    state = update_interaction_state(
        SubjectState.empty(), user_message="你必须替所有人决定。",
        answer="我不会替他们活。", appraisal={"action": "hold_boundary", "stakes": "守住判断"},
        accepted=True, score=0.8, attempts=1,
    )
    handoff = TurnHandoff.from_subject_state(state)
    data = handoff.as_dict()
    assert data["turn_count"] == 1
    assert data["current_focus"]
    assert data["recent_episodes"][0]["answer"] == "我不会替他们活。"
    assert "subject_state" not in data
    assert "raw_history" not in data
    assert TurnHandoff.from_dict(data).turn_count == handoff.turn_count


def test_tool_runtime_validates_permission_timeout_and_idempotency() -> None:
    runtime = ToolRuntime()
    runtime.register(ToolSpec(
        "role.evidence", "可见证据",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
        lambda message: {"items": [{"text": message}], "provenance": ["novel"]},
        source="rolerag", timeout_ms=500,
        distiller=lambda value, args: value["items"], idempotent=True,
    ))
    missing = asyncio.run(runtime.call("role.evidence", {}))
    assert missing.status == "error" and "message" in missing.error
    result = asyncio.run(runtime.call("role.evidence", {"message": "你好"}))
    assert result.status == "ok" and result.data == [{"text": "你好"}]
    cached = asyncio.run(runtime.call("role.evidence", {"message": "你好"}))
    assert cached.cached is True and cached.status == "ok"
    runtime.register(ToolSpec("denied.tool", "拒绝", {"type": "object"}, lambda: "nope",
                              permission=lambda scope, args: False))
    assert asyncio.run(runtime.call("denied.tool", {})).status == "denied"
    runtime.register(ToolSpec("slow.tool", "超时", {"type": "object"},
                              lambda: __import__("time").sleep(0.2), timeout_ms=20))
    assert asyncio.run(runtime.call("slow.tool", {})).status == "timeout"


def test_action_dependency_is_enforced() -> None:
    harness = AgentHarness(scope=_scope(), mode="quick", max_steps=3, registry=_registry())
    result = asyncio.run(harness.run(_Policy(["express"]), persist=False))
    assert result.observations[0]["status"] == "denied"
    assert "missing_dependency:decide" in result.observations[0]["error"]
    assert result.stop_reason == "completed"


def test_budget_is_hard_and_model_call_overflow_is_denied() -> None:
    tools = ToolRuntime()
    tools.register(ToolSpec("role.evidence", "可见证据", {"type": "object"},
                            lambda **_: {"evidence": ["e1"]}, source="rolerag"))
    harness = AgentHarness(
        scope=_scope(), mode="quick", registry=_full_registry(tools), tool_runtime=tools,
        budget=TurnBudget(max_model_calls=1, max_retrieve_calls=1, deadline_ms=10000),
        max_steps=6,
    )
    policy = _Policy(["understand_event", "recall_role", "decide", "express", "review"])
    result = asyncio.run(harness.run(policy, persist=False))
    assert result.actions[3]["name"] == "express"
    assert result.observations[3]["status"] == "ok"
    assert result.observations[4]["status"] == "denied"
    assert "max_model_calls_exceeded" in result.observations[4]["error"]
    assert result.stop_reason == "max_model_calls_exceeded"


def test_deadline_stops_before_any_action() -> None:
    harness = AgentHarness(
        scope=_scope(), mode="quick", registry=_registry(),
        budget=TurnBudget(deadline_ms=0), max_steps=2,
    )
    result = asyncio.run(harness.run(_Policy(["understand_event"]), persist=False))
    assert result.stop_reason == "deadline_exceeded"
    assert not result.actions


def test_no_progress_stops_a_denied_loop() -> None:
    harness = AgentHarness(scope=_scope(), mode="quick", registry=_registry(), max_steps=4)
    result = asyncio.run(harness.run(_Policy([], loop=True), persist=False))
    assert result.stop_reason == "no_progress"


def test_terminal_allows_stop_after_critical_failure() -> None:
    registry = _registry()

    def fail(*_):
        raise RuntimeError("boom")

    registry.register(ActionSpec("plan_turn", "计划", (), "state", 1), fail)
    registry._specs.pop("understand_event")
    registry._handlers.pop("understand_event")
    harness = AgentHarness(scope=_scope(), mode="quick", registry=registry, max_steps=3)
    result = asyncio.run(harness.run(_Policy(["plan_turn", "stop"]), persist=False))
    assert result.observations[0]["status"] in {"degraded", "error"}
    # A degraded plan is a terminal failure: stop is allowed without learn, and
    # the turn ends instead of cycling through denied stop actions.
    assert result.stop_reason == "completed"


def test_full_bounded_loop_traces_tool_context_and_state() -> None:
    store = InMemoryInteractionStateStore()
    tools = ToolRuntime()
    tools.register(ToolSpec("role.evidence", "可见证据", {"type": "object"},
                            lambda **_: {"evidence": ["e1"]}, source="rolerag"))
    harness = AgentHarness(
        scope=_scope(), mode="quick", state_store=store,
        context_pipeline=ContextPipeline(_manifest()), tool_runtime=tools,
        registry=_full_registry(tools),
        budget=TurnBudget(max_model_calls=2, max_retrieve_calls=1, deadline_ms=10000),
        max_steps=8,
    )
    policy = _Policy(["understand_event", "recall_role", "decide", "express", "review", "learn", "stop"])
    result = asyncio.run(harness.run(policy, persist=True))
    assert [item["name"] for item in result.actions] == [
        "understand_event", "recall_role", "decide", "express", "review", "learn", "stop",
    ]
    assert result.answer == "我不会替所有人决定。"
    assert result.stop_reason == "completed"
    assert result.budget["used"]["retrieve_calls"] == 1
    assert result.budget["used"]["model_calls"] == 2
    assert "context_view" in [event["kind"] for event in result.trace["events"]]
    assert store.load(_scope()).episodes
    assert store.load(_scope()).episodes[0].answer == "我不会替所有人决定。"


def test_checkpoint_resume_replays_completed_actions() -> None:
    store = InMemoryInteractionStateStore()
    harness = AgentHarness(scope=_scope(), mode="quick", state_store=store,
                           registry=_registry(), max_steps=8)
    result = asyncio.run(harness.run(_Policy(["understand_event", "decide"]), persist=True))
    assert result.stop_reason == "completed"
    checkpoint = harness.checkpoint
    assert checkpoint.completed_actions[:2] == ["understand_event", "decide"]
    resumed = AgentHarness(scope=_scope(), mode="quick", state_store=store,
                           registry=_registry(), max_steps=8, checkpoint=checkpoint)
    result2 = asyncio.run(resumed.run(_Policy(["express", "review", "learn", "stop"]), persist=True, resume=True))
    assert result2.stop_reason == "completed"
    assert result2.actions[0]["name"] == "express"


def test_validate_args_accepts_declared_types_and_rejects_bad_types() -> None:
    spec = ToolSpec(
        "typed", "typed",
        {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
        lambda count: count,
    )
    assert validate_args(spec, {"count": 2})[0]
    assert not validate_args(spec, {"count": "2"})[0]
    assert not validate_args(spec, {})[0]


def test_unknown_action_fails_fast() -> None:
    harness = AgentHarness(scope=_scope(), mode="quick", registry=_registry(), max_steps=2)
    result = asyncio.run(harness.run(_Policy(["teleport"]), persist=False))
    assert result.stop_reason == "unknown_action:teleport"
    assert result.observations[0]["status"] == "error"


def test_action_max_per_turn_is_enforced() -> None:
    harness = AgentHarness(scope=_scope(), mode="quick", registry=_registry(), max_steps=3)
    result = asyncio.run(harness.run(
        _Policy(["understand_event", "understand_event"]), persist=False,
    ))
    assert result.stop_reason == "max_per_turn_exceeded:understand_event"


def test_storyrole_turn_uses_agent_harness(monkeypatch) -> None:
    from app.agents.decision.factory import get_decision_backend
    from app.agents.storyrole.harness import turn as turn_module
    from app.rag.rolerag.persona.contract import PersonaContract

    # The harness contract test uses the deterministic rule planner; Laya is
    # exercised separately with a fake router and by the live probe.
    monkeypatch.setenv("STORYROLE_DECISION_BACKEND", "rule")
    get_decision_backend.cache_clear()
    store = InMemoryInteractionStateStore()
    monkeypatch.setattr(turn_module, "get_interaction_state_store", lambda: store)

    contract = PersonaContract(
        name="罗辑", identity="罗辑，一个不愿替别人做决定的人。",
        traits=("克制",), goals=("守住自己的判断",), fears=("被推上神坛",),
        core_beliefs=("人不能替别人决定一切",), speech_style=("短句",),
        decision_patterns=("先观察",), conversation_rules=("不解释系统",),
        anti_patterns=("不要用救世主口气",), relationships=("史强：能办事",),
        known=(), unknown=(), period_name="新时期晚年时期", period_stage="T6",
    )

    class FakeAgent:
        def _unwrap_fallback(self, value):
            if isinstance(value, dict) and value.get("_fallback_used"):
                return dict(value.get("_fallback_value") or {}), True
            return value, False

        async def _dispatch_timeout(self, _client, agent_id, payload, *, timeout, fallback, kernel=None):
            if agent_id == "character-reasoning":
                return {"response_action": "自然回应并保留角色立场", "decision_backend": "fake"}
            if agent_id == "consistency-guard":
                return {"pass": True, "persona_score": 0.8, "final_answer": payload.get("draft_answer")}
            if callable(fallback):
                return fallback()
            return fallback

        async def _run_agent(self, **kwargs):
            return "在。"

        def _record_evidence_graph(self, **kwargs):
            return None

        def _load_memories(self, payload, *, character_name):
            return []

        async def _persist_memory_candidate_async(self, *args, **kwargs):
            return None

        async def _update_relationship(self, *args, **kwargs):
            return None

        def _log_background_failure(self, task):
            return None

    class FakeTrace:
        trace_id = "trace-adapter"

        def step(self, *_args, **_kwargs):
            return nullcontext()

        def finish(self, status="completed"):
            self.status = status

    payload = {
        "novel_id": "novel", "owner_id": 1, "character_id": 2,
        "period_id": None, "thread_id": "adapter-thread", "user_id": 1,
        "message": "你好。", "mode": "quick", "recent_messages": [],
    }
    identity = {
        "owner_id": 1, "novel_id": "novel", "character_id": 2, "period_id": None,
        "character": {"canonical_name": "罗辑"},
        "profile_row": {"version": 1},
        "profile": {"novel_name": "三体", "period_name": "新时期晚年时期"},
        "profile_evidence": [], "period": None,
        "persona_contract": contract, "persona_contract_text": contract.render(),
        "message": "你好。", "requested_mode": "quick",
    }
    result = asyncio.run(turn_module.run_harness_turn(
        FakeAgent(), payload, trace=FakeTrace(), identity=identity,
    ))
    assert result["agent_runtime"] == "agent_harness"
    assert result["harness_stop_reason"] == "review_accepted"
    assert result["answer"]
    assert result["harness_trace"]["summary"]["actions"][0] == "plan_turn"
    assert store.load(TurnScope("novel", 1, 2, None, thread_id="adapter-thread", user_id=1)).episodes


def test_checked_in_eval_set_covers_all_probe_suites():
    from pathlib import Path

    from app.harness.eval import validate_eval_set

    docs = Path(__file__).resolve().parents[3] / "docs" / "agent-harness-eval.jsonl"
    report = validate_eval_set(docs)
    assert report["passed"]
    assert report["counts"] == {"behavior": 5, "quick_probe": 4, "deep_probe": 1}
    assert len(report["ids"]) == len(set(report["ids"]))
