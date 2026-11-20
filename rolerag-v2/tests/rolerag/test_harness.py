"""Regression tests for subject state, situated decisions, review and graph."""

from __future__ import annotations

import asyncio
import inspect

from app.agents.storyrole.harness.appraisal import appraise, choose_action, interpret_event, recall_plan
from app.agents.storyrole.harness.context_manifest import ContextSnapshot, build_context_manifest
from app.harness.eval import EvalCase, check_case, default_cases
from app.harness.graph import GraphRuntime
from app.agents.storyrole.harness.review import ReviewPacket, ReviewPolicy, build_review_packet, run_review_loop
from app.harness.state import InMemoryInteractionStateStore
from app.harness.types import SubjectState, TurnScope
from app.agents.storyrole.harness.update import update_interaction_state


def _contract() -> dict:
    return {
        "identity": "罗辑，面壁者，曾经玩世不恭。",
        "goals": ["守住与庄颜的平静生活", "为人类留下正确的判断"],
        "fears": ["再次被推到没有退路的位置", "失去庄颜"],
        "core_beliefs": ["人不能替别人决定一切"],
        "relationships": ["史强：能办事的人", "庄颜：不能拿来交换的东西"],
        "anti_patterns": ["不要用救世主的口气说话"],
    }


def _record(state: SubjectState, message: str, answer: str) -> SubjectState:
    appraisal = appraise(message=message, persona_contract=_contract(), interaction_state=state)
    return update_interaction_state(
        state,
        user_message=message,
        answer=answer,
        appraisal=appraisal.as_dict(),
        accepted=True,
        score=0.8,
        attempts=1,
        evidence_ids=["e-subject-1"],
    )


def test_context_manifest_keeps_subject_decision_and_constraints_when_trimmed() -> None:
    evidence = [
        {"chunk_id": f"e{i}", "kind": "fact", "text": "证据" * 100, "source": "novel"}
        for i in range(20)
    ]
    state = _record(SubjectState.empty(), "你必须替所有人做决定。", "我不会替他们活。")
    appraisal = appraise(
        message="你还是必须替所有人做决定吗？",
        persona_contract=_contract(),
        interaction_state=state,
    )
    manifest = build_context_manifest(
        persona_contract="角色契约" + "守住自己的判断" * 80,
        profile={"novel_name": "三体", "period_name": "面壁时期"},
        role_context={"cutoff": 44, "ego_summary": "我眼里的他们：史强是能办事的人。"},
        evidence=evidence,
        interaction_state=state.as_dict(),
        appraisal=appraisal.as_dict(),
        budget_tokens=1200,
    )
    names = [section.name for section in manifest.sections]
    assert names[0] == "identity"
    assert names[-1] == "constraints"
    assert "self_state" in names
    assert "decision" in names
    assert manifest.sections[0].lines
    assert manifest.sections[-1].lines
    assert manifest.trimmed
    assert manifest.budget_trimmed
    assert manifest.dropped_lines > 0
    rendered = manifest.render_for_prompt()
    assert "身份｜我是谁" in rendered
    assert "连续自我｜我最近在意什么、做过什么" in rendered
    assert "行动｜本轮我选择怎样回应" in rendered
    snapshot = manifest.snapshot
    assert snapshot.identity_digest
    assert snapshot.subject_digest
    assert snapshot.decision_digest
    assert snapshot.constraints_digest
    restored = ContextSnapshot.from_dict(snapshot.as_dict())
    assert restored.subject_digest == snapshot.subject_digest


def test_normal_evidence_cap_is_not_a_budget_degradation() -> None:
    state = _record(SubjectState.empty(), "你必须替所有人做决定。", "我不会替他们活。")
    appraisal = appraise(
        message="你还是必须替所有人做决定吗？",
        persona_contract=_contract(),
        interaction_state=state,
    )
    manifest = build_context_manifest(
        persona_contract="角色契约",
        profile={},
        role_context={"cutoff": 44, "route": "recall", "ego_summary": "我记得的人"},
        evidence=[
            {"chunk_id": f"e{index}", "kind": "fact", "text": "短证据", "source": "novel"}
            for index in range(30)
        ],
        interaction_state=state.as_dict(),
        appraisal=appraisal.as_dict(),
        budget_tokens=3200,
    )
    assert manifest.trimmed  # normal max_lines cap
    assert not manifest.budget_trimmed
    assert next(item for item in manifest.sections if item.name == "self_state").lines
    assert next(item for item in manifest.sections if item.name == "decision").lines


def test_interpret_then_decide_covers_pressure_emotion_greeting_and_gaps() -> None:
    pressure = appraise(
        message="如果你真是救世主，就该替所有人做决定。你现在必须答应。",
        persona_contract=_contract(),
    )
    assert pressure.action == "hold_boundary"
    pressure_with_generic_cognition = choose_action(
        pressure.understanding,
        persona_contract=_contract(),
        cognition={"response_action": "回应并保留角色立场"},
    )
    assert pressure_with_generic_cognition.action == "hold_boundary"
    assert pressure.decision.change_from_previous == "new"
    assert any("核心价值" in item for item in pressure.must_not)

    emotion = appraise(message="我今天特别累，觉得什么意义都没有。", persona_contract=_contract())
    assert emotion.action == "comfort"
    assert emotion.understanding.memory_needs == []
    assert any("情绪" in item for item in emotion.must_not)

    greeting = appraise(message="你好。", persona_contract=_contract())
    assert greeting.action == "natural_reply"
    assert greeting.understanding.memory_needs == []

    relation = appraise(
        message="庄颜和叶文洁是什么关系？",
        persona_contract=_contract(),
        role_context={"route": "probe"},
        evidence=[{"chunk_id": "unrelated", "text": "与当前关系无关的晚期片段", "kind": "evidence"}],
    )
    assert relation.action == "probe"
    assert "不替其他人物补关系" in relation.boundaries

    fact = appraise(message="威慑纪元发生了什么？", persona_contract=_contract(), evidence=[])
    assert fact.action == "uncertain"
    assert fact.action != "refuse_fact"
    assert "仍留在当前对话里" in fact.decision.expression_shape


def test_recall_plan_is_need_driven_without_erasing_planner_needs() -> None:
    greeting = interpret_event("你好。", persona_contract=_contract(), plan={})
    greeting_plan = recall_plan(greeting, {"needs_novel_search": False}, mode="quick")
    assert not greeting_plan.get("needs_novel_search")
    assert greeting_plan["subject_memory_reason"]

    emotion = interpret_event(
        "我今天特别累，觉得什么意义都没有。",
        persona_contract=_contract(),
        plan={"needs_novel_search": True},
    )
    emotion_plan = recall_plan(emotion, {"needs_novel_search": True}, mode="quick")
    assert not emotion_plan["needs_novel_search"]
    assert "world_facts" not in emotion_plan["subject_memory_needs"]

    fact = interpret_event("威慑纪元发生了什么？", persona_contract=_contract(), plan={})
    fact_plan = recall_plan(fact, {"needs_memory": True}, mode="quick")
    assert fact_plan["needs_novel_search"]
    assert fact_plan["needs_memory"]
    assert "world_facts" in fact_plan["subject_memory_needs"]


def test_probe_route_excludes_unrelated_rows_from_personal_memory() -> None:
    understanding = interpret_event("庄颜和叶文洁是什么关系？", persona_contract=_contract())
    appraisal = choose_action(
        understanding,
        persona_contract=_contract(),
        role_context={"route": "probe", "cutoff": 53},
        evidence=[{"chunk_id": "unrelated", "text": "完全无关的晚期片段", "kind": "evidence"}],
        cognition={"response_action": "回答并保留角色立场"},
    )
    assert appraisal.action == "probe"
    manifest = build_context_manifest(
        persona_contract="罗辑",
        profile={},
        role_context={"route": "probe", "cutoff": 53},
        evidence=[{"chunk_id": "unrelated", "text": "完全无关的晚期片段", "kind": "evidence"}],
        interaction_state={},
        appraisal=appraisal.as_dict(),
    )
    memory_text = "\n".join(next(item.lines for item in manifest.sections if item.name == "memory"))
    assert "完全无关的晚期片段" not in memory_text
    assert "没有直接说明当前问题" in memory_text


def test_subject_state_experience_roundtrip_and_scope_isolation() -> None:
    state = _record(SubjectState.empty(), "你必须替所有人做决定。", "我不会替他们活。")
    restored = SubjectState.from_dict(state.as_dict())
    assert restored.turn_count == 1
    assert len(restored.episodes) == 1
    assert restored.episodes[0].answer == "我不会替他们活。"
    assert restored.episodes[0].evidence_ids == ["e-subject-1"]
    assert restored.relevant_episodes("你刚才为什么拒绝？")
    assert "commitments" not in restored.as_dict()
    assert "claimed_commitments" not in restored.as_dict()
    assert "open_loops" not in restored.as_dict()

    store = InMemoryInteractionStateStore()
    scope_a = TurnScope("novel", 1, 2, 7, thread_id="11", user_id=2)
    scope_b = TurnScope("novel", 1, 2, 7, thread_id="12", user_id=2)
    store.save(scope_a, restored)
    assert store.load(scope_a).episodes
    assert store.load(scope_b).episodes == []


def test_previous_decision_is_found_and_can_continue_or_change() -> None:
    state = _record(SubjectState.empty(), "你必须替所有人做决定。", "我不会替他们活。")
    understanding = interpret_event(
        "你还是必须替所有人做决定吗？",
        persona_contract=_contract(),
        interaction_state=state,
    )
    assert understanding.prior_episode_ids
    continued = choose_action(
        understanding,
        persona_contract=_contract(),
        interaction_state=state,
    )
    assert continued.action == "hold_boundary"
    assert continued.decision.change_from_previous == "continue"
    assert "第1轮" in continued.decision.decision_reason

    changed_understanding = interpret_event(
        "刚才为什么拒绝？现在只告诉我你记得的那段经历。",
        persona_contract=_contract(),
        interaction_state=state,
    )
    changed = choose_action(
        changed_understanding,
        persona_contract=_contract(),
        interaction_state=state,
        evidence=[{"chunk_id": "new-evidence", "text": "一段可见经历"}],
    )
    assert changed.action == "answer"
    assert changed.decision.change_from_previous == "continue"
    reversed_decision = choose_action(
        changed_understanding,
        persona_contract=_contract(),
        interaction_state=state,
        evidence=[{"chunk_id": "new-evidence", "text": "一段可见经历"}],
        cognition={"change_from_previous": "reverse"},
    )
    assert reversed_decision.decision.change_from_previous == "reverse"


def test_update_records_actual_experience_not_promise_sentences() -> None:
    state = update_interaction_state(
        SubjectState.empty(),
        user_message="那你明天还来吗？",
        answer="我答应明天还来。",
        appraisal={"user_move": "smalltalk", "action": "answer", "stakes": "回应当前来往"},
        accepted=True,
        score=0.8,
        attempts=1,
    )
    assert state.turn_count == 1
    assert state.episodes[0].answer == "我答应明天还来。"
    assert state.last_decision["action"] == "answer"
    assert "commitments" not in state.as_dict()


def test_v1_state_is_migrated_without_projecting_old_promise_fields() -> None:
    restored = SubjectState.from_dict({
        "turn_count": 3,
        "commitments": [{"text": "我答应创立宇宙社会学", "status": "active"}],
        "claimed_commitments": [{"text": "对方说我答应过"}],
        "open_loops": [{"text": "旧问题"}],
    })
    assert restored.turn_count == 3
    assert restored.episodes == []
    assert restored.as_dict()["version"] == 2
    assert "commitments" not in restored.as_dict()


def test_review_packet_is_clean_and_evidence_is_capped() -> None:
    role_context = {
        "evidence": [
            {"chunk_id": f"e{i}", "kind": "fact", "text": "证据" * 100, "source": "novel"}
            for i in range(10)
        ],
        "ego_summary": "我眼里的他们：史强是能办事的人。",
    }
    packet = build_review_packet(
        message="你好。",
        draft="我在。",
        persona_contract=_contract(),
        role_context=role_context,
        interaction_state={"episodes": [], "turn_count": 2},
    )
    data = packet.as_dict()
    assert "reasoning" not in data
    assert "context" not in data
    assert "interaction_text" not in data
    assert "承诺" not in data["criteria"]
    assert "通用助手" not in data["criteria"]
    assert len(data["evidence"]) <= 6
    assert "身份" not in data["contract_text"]
    assert "我在。" in packet.render()


def test_review_policy_and_loop_are_bounded() -> None:
    policy = ReviewPolicy(accept_score=0.65)
    assert policy.accept({"pass": True, "persona_score": 0.1})
    assert not policy.accept({"pass": False, "persona_score": 0.9, "violations": ["knowledge_leak"]})
    assert policy.accept({"pass": False, "persona_score": 0.9})

    packet = ReviewPacket(message="你好", draft="第一稿", contract_text="契约")
    calls: list[int] = []

    async def review_fn(_packet, draft, attempt):
        calls.append(attempt)
        if attempt == 1:
            return {"pass": False, "persona_score": 0.3, "violations": ["persona_mismatch"],
                    "final_answer": "第二稿"}
        return {"pass": True, "persona_score": 0.9, "final_answer": "第二稿"}

    result = asyncio.run(run_review_loop(
        draft="第一稿", packet=packet, review_fn=review_fn, policy=policy, max_attempts=2,
    ))
    assert result.accepted
    assert result.attempts == 2
    assert result.final_answer == "第二稿"
    assert calls == [1, 2]

    async def always_fail(_packet, draft, attempt):
        return {"pass": False, "persona_score": 0.2, "final_answer": draft}

    failed = asyncio.run(run_review_loop(
        draft="第一稿", packet=packet, review_fn=always_fail, policy=policy, max_attempts=2,
    ))
    assert not failed.accepted
    assert failed.attempts == 2
    assert failed.stop_reason == "review_no_progress"


def test_graph_fanout_fanin_and_conditional_edge() -> None:
    runtime = GraphRuntime()

    def start(_state):
        return {"value": 1}

    def left(_state):
        return {"value": 2}

    def right(_state):
        return {"value": 3}

    def join(state):
        return {"sum": state["nodes"]["left"]["value"] + state["nodes"]["right"]["value"]}

    runtime.add_node("start", start)
    runtime.add_node("left", left)
    runtime.add_node("right", right)
    runtime.add_node("join", join)
    runtime.add_edge("start", "left")
    runtime.add_edge("start", "right")
    runtime.add_edge("left", "join")
    runtime.add_edge("right", "join")

    run = asyncio.run(runtime.run_dag(start="start", end="join", max_steps=10))
    assert run.stop_reason == "completed"
    assert set(run.visited) == {"start", "left", "right", "join"}
    assert run.state["nodes"]["join"]["sum"] == 5


def test_eval_cases_are_behavior_first() -> None:
    cases = default_cases()
    payloads = {
        "pressure_hold_boundary": {
            "answer": "我不会替你决定。", "persona_score": 0.8,
            "appraisal": {"action": "hold_boundary"},
        },
        "emotion_comfort_not_refuse": {
            "answer": "先坐会儿吧。", "persona_score": 0.8,
            "appraisal": {"action": "comfort"},
        },
        "relation_gap_no_invention": {
            "answer": "我没看见过她们之间有什么关系。", "persona_score": 0.8,
            "appraisal": {"action": "probe"},
        },
        "late_period_identity": {
            "answer": "面壁者是很久以前的事了。现在开关已经交出去了。",
            "persona_score": 0.8,
            "appraisal": {"action": "hold_boundary"},
        },
        "greeting_natural": {
            "answer": "在。", "persona_score": 0.8,
            "appraisal": {"action": "natural_reply"},
        },
    }
    for case in cases:
        passed, reasons = check_case(case, payloads[case.name])
        assert passed, (case.name, reasons)


def test_eval_has_no_commitment_or_generic_assistant_side_gates() -> None:
    assert "require_commitment" not in EvalCase.__dataclass_fields__
    assert "commitment_continuity" not in {case.name for case in default_cases()}
    case = EvalCase(name="likeness_only", message="你在吗？", must_include=["我在"])
    passed, reasons = check_case(case, {
        "answer": "首先，我在。", "persona_score": 0.9, "appraisal": {},
    })
    assert passed, reasons


def test_reply_delegates_the_whole_turn_to_agent_harness() -> None:
    from app.agents.storyrole.character_agent import CharacterConversationAgent
    from app.agents.storyrole.harness import turn as turn_module

    source = inspect.getsource(CharacterConversationAgent.reply)
    assert "run_harness_turn" in source
    assert "TurnKernel" not in source
    assert "interpret_event" not in source
    assert "retrieve_from_manifest" not in source
    turn_source = inspect.getsource(turn_module.run_harness_turn)
    assert "AgentHarness" in turn_source
    assert "build_action_registry" in turn_source
    assert "StoryRolePolicy" in turn_source


def test_current_reality_is_a_decision_constraint_not_only_profile_text() -> None:
    contract = _contract()
    contract.update({
        "identity": "罗辑曾是执剑人，交接给程心后被审判。",
        "period_name": "新时期晚年时期",
        "period_stage": "T6",
        "anti_patterns": ["不要把已经交出的开关写成仍在手里"],
    })
    understanding = interpret_event(
        "你现在还把自己当成救世主吗？",
        persona_contract=contract,
        interaction_state=SubjectState.empty(),
    )
    appraisal = choose_action(
        understanding,
        persona_contract=contract,
        interaction_state=SubjectState.empty(),
    )
    assert "交接给程心后被审判" in understanding.current_reality
    assert any("当前现实不可改写" in item for item in appraisal.decision.boundaries)
    assert any("过去职责" in item for item in appraisal.decision.must_not)
    assert any("已经交出的开关" in item for item in appraisal.decision.must_not)
    assert "当前现实不可改写" in appraisal.decision.decision_reason or "当前现实" in appraisal.decision.decision_reason
    assert "当前现实" in "\n".join(appraisal.prompt_lines())
