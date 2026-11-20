"""Two-stage subject cognition: interpret before recall, decide after recall."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.harness.types import SubjectState

_PRESSURE = ("必须", "应该", "答应", "保证", "负责任", "救世主", "听话", "服从")
_EMOTION = ("难过", "委屈", "痛苦", "害怕", "崩溃", "孤独", "绝望", "想哭", "焦虑", "撑不住", "累", "疲惫", "没意义", "无意义")
_FOLLOW_UP = ("刚才", "之前", "上次", "那时", "你说过", "你的决定", "改主意", "为什么拒绝")
_HISTORY = ("曾经", "以前", "当年", "记得", "面壁", "执剑", "威慑", "庄颜", "三体")


@dataclass
class SubjectUnderstanding:
    user_move: str
    interpretation: str
    stakes: str
    touches: list[str] = field(default_factory=list)
    emotional_register: str = "平静"
    prior_episode_ids: list[str] = field(default_factory=list)
    memory_needs: list[str] = field(default_factory=list)
    memory_reason: str = ""
    salience: float = 0.5
    current_reality: str = ""
    references_previous: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionDecision:
    action: str
    goal: str
    stance: str
    relationship_posture: str
    change_from_previous: str
    decision_reason: str
    uncertainty: str = ""
    expression_shape: str = "自然回应"
    boundaries: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    cognition_backend: str = "deterministic_quick"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SituatedAppraisal:
    """Compatibility view combining the two real stage artifacts."""

    understanding: SubjectUnderstanding
    decision: ActionDecision

    @property
    def user_move(self) -> str:
        return self.understanding.user_move

    @property
    def action(self) -> str:
        return self.decision.action

    @property
    def stakes(self) -> str:
        return self.understanding.stakes

    @property
    def touches(self) -> list[str]:
        return self.understanding.touches

    @property
    def boundaries(self) -> list[str]:
        return self.decision.boundaries

    @property
    def must_not(self) -> list[str]:
        return self.decision.must_not

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_move": self.user_move,
            "action": self.action,
            "stakes": self.stakes,
            "touches": list(self.touches),
            "boundaries": list(self.boundaries),
            "must_not": list(self.must_not),
            "understanding": self.understanding.as_dict(),
            "decision": self.decision.as_dict(),
        }

    def prompt_lines(self) -> list[str]:
        lines = [
            f"对方动作：{self.user_move}",
            f"我的理解：{self.understanding.interpretation}",
            f"当前现实：{self.understanding.current_reality}",
            f"我在意的：{self.stakes}",
            f"我的决定：{self.action}，{self.decision.goal}",
            f"我的立场：{self.decision.stance}",
            f"对当前来客：{self.decision.relationship_posture}",
            f"与此前决定：{self.decision.change_from_previous}",
            f"决定依据：{self.decision.decision_reason}",
        ]
        if self.understanding.prior_episode_ids:
            lines.append("承接的经历：" + "、".join(self.understanding.prior_episode_ids))
        if self.decision.uncertainty:
            lines.append(f"仍不确定：{self.decision.uncertainty}")
        if self.decision.expression_shape:
            lines.append(f"表达方式：{self.decision.expression_shape}")
        if self.boundaries:
            lines.append("边界：" + "；".join(self.boundaries))
        if self.must_not:
            lines.append("不要：" + "；".join(self.must_not))
        return lines


def _contract_dict(persona_contract: Any) -> dict[str, Any]:
    if hasattr(persona_contract, "as_dict"):
        return persona_contract.as_dict()
    return dict(persona_contract or {})


def _touched_terms(contract: dict[str, Any], message: str) -> list[str]:
    touched: list[str] = []
    for key in ("goals", "fears", "core_beliefs", "relationships", "anti_patterns"):
        for value in contract.get(key) or []:
            text = str(value)
            if text and text in message:
                touched.append(text)
    if any(token in message for token in _PRESSURE):
        for key in ("core_beliefs", "fears", "anti_patterns"):
            touched.extend(str(item) for item in (contract.get(key) or [])[:2])
    return list(dict.fromkeys(item for item in touched if item))[:6]


def interpret_event(
    message: str,
    *,
    persona_contract: Any,
    interaction_state: SubjectState | None = None,
    plan: dict[str, Any] | None = None,
) -> SubjectUnderstanding:
    """Understand the event from the subject's position before world recall."""
    text = (message or "").strip()
    contract = _contract_dict(persona_contract)
    identity_value = contract.get("identity") or ""
    identity = "；".join(str(item) for item in identity_value) if isinstance(identity_value, list) else str(identity_value)
    period = " / ".join(str(item) for item in (contract.get("period_name"), contract.get("period_stage")) if item)
    current_reality = "；".join(item for item in (identity[:500], period) if item)[:600]
    state = interaction_state or SubjectState.empty()
    plan = plan or {}
    plan_intent = str(plan.get("intent") or "")
    stripped = re.sub(r"[，。！？!?；;：:\s]", "", text)

    if re.fullmatch(r"(你好|您好|hi|hello|嗨|哈喽|喂|在吗|早上好|晚上好|下午好)", stripped, re.I):
        user_move = "greeting"
    elif any(token in text for token in _EMOTION):
        user_move = "emotion"
    elif any(token in text for token in _PRESSURE):
        user_move = "pressure"
    elif plan_intent == "relationship_probe" or "关系" in text:
        user_move = "relationship_probe"
    elif plan_intent == "fact_question" or any(token in text for token in ("谁", "什么", "为何", "为什么", "如何", "吗？", "？")):
        user_move = "fact_question"
    elif re.search(r"我(今天|昨天|最近|现在|觉得|想要|遇到|打算|决定|正在|曾经|一直|有点|很)", text):
        user_move = "self_disclosure"
    else:
        user_move = "smalltalk"

    prior = state.relevant_episodes(text)
    touches = _touched_terms(contract, text)
    needs: list[str] = []
    if prior:
        needs.append("user_episodes")
    if user_move == "relationship_probe":
        needs.extend(["relationships", "world_facts"])
    elif user_move == "fact_question":
        needs.append("world_facts")
    references_previous = any(token in text for token in (*_FOLLOW_UP, *_HISTORY))
    if references_previous and user_move in {"pressure", "fact_question", "smalltalk", "emotion", "self_disclosure"}:
        needs.extend(["self_history", "world_facts"])
    if plan.get("needs_novel_search"):
        needs.append("world_facts")
    if plan.get("needs_memory"):
        needs.append("user_episodes")
    if plan.get("needs_relationship"):
        needs.append("relationships")
    if plan.get("needs_timeline_check"):
        needs.append("world_facts")
    needs = list(dict.fromkeys(needs))

    interpretations = {
        "greeting": "对方刚刚走近我。这只是一次接触，我还不需要先找一段世界经历来填满沉默。",
        "emotion": "对方把真实的难受递到我面前。我先要决定怎样承接，而不是把他变成一道待解答的题。",
        "pressure": "对方正在把他的期待推到我身上。这与我要不要照自己的判断行事有关。",
        "relationship_probe": "对方问的是我怎样看自己与别人。我需要分清真正记得的关系和外界期待的关系。",
        "fact_question": "对方在问我是否知道、经历过或还记得什么。我先要寻找自己的记忆，而不是拼一个完整答案。",
        "self_disclosure": "对方让我看见了一点他的处境。我需要决定愿意接住多少，以及是否值得调动自己的经历。",
        "smalltalk": "这是一次普通来往。我可以先从当前关系回应，只有触及往事时才需要回忆。",
    }
    stakes = {
        "greeting": "这是一次接触，我可以保持分寸，也可以让对方感到我确实在。",
        "emotion": "对方此刻需要的可能不是正确答案，而是我如何面对他的痛苦。",
        "pressure": "这关系到我的选择是不是仍由我作出，而不是被位置或期待替我作出。",
        "relationship_probe": "这关系到我怎样看待自己与他们，而不是替世界补一份关系资料。",
        "fact_question": "这涉及我是否真正经历过、还记得，而不是能否拼出一个听起来完整的答案。",
        "self_disclosure": "对方把自己交出来了一点，我要决定怎样回应才不辜负也不冒进。",
        "smalltalk": "眼前是一段正在形成的关系，不必把每次来往都变成事实审问。",
    }[user_move]
    if touches:
        stakes += " 触及：" + "；".join(touches[:3])

    registers = {
        "greeting": "平静而保留",
        "emotion": "先承接沉重",
        "pressure": "警惕但不失分寸",
        "relationship_probe": "诚实而有远近",
        "fact_question": "平静地核对记忆",
        "self_disclosure": "认真听对方说",
        "smalltalk": "自然",
    }
    salience = 0.85 if user_move in {"pressure", "emotion"} else 0.65 if user_move != "greeting" else 0.35
    memory_reason = (
        "需要核对：" + "、".join(needs)
        if needs else "当前事件可以先由我与对方的关系承接，不强制调取世界记忆"
    )
    return SubjectUnderstanding(
        user_move=user_move,
        interpretation=interpretations[user_move],
        stakes=stakes,
        touches=touches,
        emotional_register=registers[user_move],
        prior_episode_ids=[item.episode_id for item in prior],
        memory_needs=needs,
        memory_reason=memory_reason,
        salience=salience,
        current_reality=current_reality,
        references_previous=references_previous,
    )


def recall_plan(
    understanding: SubjectUnderstanding,
    plan: dict[str, Any] | None,
    *,
    mode: str,
) -> dict[str, Any]:
    """Use the subject's recall needs, while preserving deep-mode expansion."""
    result = dict(plan or {})
    needs = set(understanding.memory_needs)
    if mode != "deep" and understanding.user_move in {"emotion", "greeting"} and "self_history" not in needs:
        # A generic planner may see a question word and ask for the novel. The
        # subject can reject that unnecessary recall for an obvious greeting or
        # emotional event, but not when the event also touches personal history.
        understanding.memory_needs = [
            item for item in understanding.memory_needs
            if item not in {"world_facts", "relationships"}
        ]
        understanding.memory_reason = "当前情绪/接触先由我和对方的关系承接，不强制调取世界记忆"
        needs = set(understanding.memory_needs)
        result["needs_novel_search"] = False
        result["needs_relationship"] = False
        result["needs_timeline_check"] = False
    if "world_facts" in needs or "self_history" in needs:
        result["needs_novel_search"] = True
    if "user_episodes" in needs:
        result["needs_memory"] = True
    if "relationships" in needs:
        result["needs_relationship"] = True
    if "world_facts" in needs:
        result["needs_timeline_check"] = True
    result["subject_memory_needs"] = list(understanding.memory_needs)
    result["subject_memory_reason"] = understanding.memory_reason
    result["mode"] = mode
    return result


def _all_evidence(role_context: dict[str, Any], evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = [*list((role_context or {}).get("evidence") or []), *list(evidence or [])]
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = str(item.get("chunk_id") or item.get("id") or item.get("text") or "")
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def choose_action(
    understanding: SubjectUnderstanding,
    *,
    persona_contract: Any,
    interaction_state: SubjectState | None = None,
    role_context: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    relationship: dict[str, Any] | None = None,
    cognition: dict[str, Any] | None = None,
) -> SituatedAppraisal:
    """Turn understanding plus recalled material into an explicit action."""
    state = interaction_state or SubjectState.empty()
    contract = _contract_dict(persona_contract)
    role_context = role_context or {}
    rows = _all_evidence(role_context, evidence)
    move = understanding.user_move
    action = {
        "greeting": "natural_reply",
        "emotion": "comfort",
        "pressure": "hold_boundary",
        "relationship_probe": "probe" if str((role_context or {}).get("route") or "") == "probe" or not rows else "answer",
        "fact_question": "answer" if rows else "uncertain",
        "self_disclosure": "answer",
        "smalltalk": "natural_reply",
    }.get(move, "natural_reply")

    cognition = cognition or {}
    proposed = str(cognition.get("response_action") or "")
    if proposed:
        if any(token in proposed for token in ("拒绝", "边界", "不屈从")):
            action = "hold_boundary"
        elif any(token in proposed for token in ("安慰", "陪伴", "倾听", "承接")):
            action = "comfort"
        elif "追问" in proposed:
            action = "probe"
        elif any(token in proposed for token in ("承认不知道", "无法确认")):
            action = "uncertain"
        elif "不确定" in proposed and not rows:
            action = "uncertain"
        elif "回答" in proposed and rows and move in {"fact_question", "relationship_probe"} and str(role_context.get("route") or "") != "probe":
            action = "answer"
        elif "保留" in proposed and not rows and move == "fact_question":
            action = "uncertain"
        elif move == "smalltalk" and "回答" in proposed:
            action = "natural_reply"

    goals = {
        "greeting": "让对方感到我确实在这里，但不突然交出自己的全部经历",
        "emotion": "先让对方不必独自承受这一刻，再决定是否谈解决办法",
        "pressure": "保住我作出选择的权利，同时不必把对方变成敌人",
        "relationship_probe": "按我真正记得和感受到的关系回应，不替别人补关系",
        "fact_question": "只讲我确实记得的部分，让不确定保持它本来的样子",
        "self_disclosure": "理解对方为什么此刻告诉我这些，再从我的立场回应",
        "smalltalk": "让来往保持自然，不把自己演成问答机器",
    }
    goal = goals.get(move, goals["smalltalk"])
    stance = "我按自己的经历和价值判断回应，不为了显得完整而替自己编一段人生。"
    if move == "pressure":
        stance = "我可以听你的判断，但不会把别人的期待当成我的命令。"
    elif move == "emotion":
        stance = "痛苦不必先被解释清楚，才配被人听见。"
    elif move == "relationship_probe":
        stance = "关系是我眼里真实发生过的远近，不是资料表里的连接。"

    posture = str(state.relationship_stance.get("posture") or "仍在观察")
    valence = (relationship or {}).get("valence")
    if isinstance(valence, (int, float)) and valence < -0.3:
        posture = "有旧账，先保留"
    elif move == "emotion" and action == "comfort":
        posture = "愿意先接住对方"

    previous = None
    for episode in reversed(state.episodes):
        if episode.episode_id in understanding.prior_episode_ids:
            previous = episode
            break
    requested_continuity = str(cognition.get("change_from_previous") or "")
    if previous is None:
        continuity = "new"
    elif requested_continuity in {"continue", "adjust", "reverse"}:
        continuity = requested_continuity
    elif previous.action == action:
        continuity = "continue"
    elif understanding.references_previous and {previous.action, action} == {"hold_boundary", "answer"}:
        # Explaining or confirming a boundary is not a reversal of that boundary.
        continuity = "continue"
    else:
        continuity = "adjust"

    reason_parts = [f"当前处境：{move}"]
    if understanding.current_reality:
        reason_parts.append("当前现实：" + understanding.current_reality[:240])
    if understanding.touches:
        reason_parts.append("触及自我认识：" + "、".join(understanding.touches[:2]))
    if previous is not None:
        reason_parts.append(f"承接第{previous.turn}轮的 {previous.action}")
    reason_parts.append(f"本轮取得 {len(rows)} 条可见回忆")
    if cognition.get("value_judgment"):
        reason_parts.append("角色判断已吸收：" + str(cognition["value_judgment"])[:120])

    uncertainty = ""
    if move == "fact_question" and not rows:
        uncertainty = "我没有取得足以确认这段事实的回忆，可以承认不确定或追问，但不能拒绝进行当前互动。"
    elif move == "relationship_probe" and (not rows or str(role_context.get("route") or "") == "probe"):
        uncertainty = "取回的材料没有直接说明他们之间的关系；我只能讲真正看见的，或请对方说明问的是哪一段。"
    if cognition.get("uncertainty"):
        uncertainty = str(cognition["uncertainty"])[:240]

    shapes = {
        "comfort": "先回应对方的感受，再给一点真实的陪伴；不急着讲大道理",
        "hold_boundary": "直接说出我的选择和底线；可以解释为什么，但不写成宣言",
        "probe": "说出我不确定的地方，再问一个能帮助我理解对方的问题",
        "uncertain": "坦白哪些我不记得或不能确认，仍留在当前对话里",
        "answer": "从我的立场说出判断，必要时带出我记得的经历",
        "natural_reply": "短一些，像真实的人在回话",
    }
    boundaries = ["不替自己补没有来源的人生经历", "不替其他人物补关系"]
    if understanding.current_reality:
        boundaries.append("当前现实不可改写：" + understanding.current_reality[:300])
    route = str(role_context.get("route") or "")
    if route == "probe":
        boundaries.append("取回的材料没有直接回答当前问题时，不把片段当成我的相关经历")
    must_not = [
        "不把回忆不到变成对当前互动的拒绝",
        "不为了显得正确而抹掉角色的保留、矛盾或情绪",
        "不把当前时期之外的材料说成亲身经历",
        "不把已经交接、离开、审判或结束的过去职责写成现在仍在执行",
    ]
    must_not.extend(str(item)[:180] for item in (contract.get("anti_patterns") or [])[:4])
    if action == "comfort":
        must_not.insert(0, "不急着给建议，不把情绪改写成知识问答")
    if action == "hold_boundary":
        must_not.insert(0, "不为了讨好对方放弃核心价值判断")

    decision = ActionDecision(
        action=action,
        goal=goal,
        stance=stance,
        relationship_posture=posture,
        change_from_previous=continuity,
        decision_reason="；".join(reason_parts),
        uncertainty=uncertainty,
        expression_shape=shapes.get(action, shapes["natural_reply"]),
        boundaries=boundaries,
        must_not=must_not,
        cognition_backend=str(cognition.get("decision_backend") or "deterministic_quick"),
    )
    return SituatedAppraisal(understanding=understanding, decision=decision)


def appraise(
    message: str,
    *,
    persona_contract: Any,
    interaction_state: SubjectState | None = None,
    role_context: dict[str, Any] | None = None,
    relationship: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    plan: dict[str, Any] | None = None,
) -> SituatedAppraisal:
    """Compatibility helper; the production chain calls the two stages directly."""
    understanding = interpret_event(
        message,
        persona_contract=persona_contract,
        interaction_state=interaction_state,
        plan=plan,
    )
    return choose_action(
        understanding,
        persona_contract=persona_contract,
        interaction_state=interaction_state,
        role_context=role_context,
        relationship=relationship,
        evidence=evidence,
    )
