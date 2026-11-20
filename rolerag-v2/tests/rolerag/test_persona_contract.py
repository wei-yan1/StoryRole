"""Persona contract checks: likeness is the first acceptance criterion."""

from __future__ import annotations

from app.rag.rolerag.persona.contract import (
    build_persona_contract,
    check_persona,
    extract_contract_from_payload,
)
from app.agents.storyrole.harness.review import build_review_packet


def _profile() -> dict:
    return {
        "character_name": "罗辑",
        "identity": "玩世不恭的社会学学者，不是救世主",
        "personality": ["自嘲", "冷静", "情感疏离"],
        "goals": ["先把自己活明白", "不替任何人扮演英雄"],
        "fears": ["被当成救世主", "再次被卷入不属于自己的事"],
        "speech_style": ["短句", "反问", "带讽刺"],
        "conversation_rules": ["称史强为“大史”", "不解释设定"],
        "anti_patterns": ["不要写成客服", "不要总结"],
        "knowledge_boundary": {"known": ["宇宙社会学两条公理"], "unknown": ["猜疑链细节"]},
        "relationships": [{"name": "史强", "relation": "护送我、试探我"}],
    }


def test_contract_keeps_identity_and_contradictions() -> None:
    contract = build_persona_contract(_profile())
    rendered = contract.render()
    assert "罗辑" in rendered
    assert "自嘲" in rendered
    assert "不是救世主" in rendered
    assert "史强" in rendered
    assert "猜疑链细节" in rendered


def test_fast_fidelity_check_flags_out_of_character_voice() -> None:
    contract = build_persona_contract(_profile())
    report = check_persona(contract, "作为一个AI，我首先需要说明，这个问题可以从三个方面来看。")
    assert report.ok is False
    assert any("AI" in item or "总结" in item for item in report.violations)
    assert report.instruction


def test_fast_fidelity_check_accepts_in_character_answer() -> None:
    contract = build_persona_contract(_profile())
    report = check_persona(contract, "你老问这句，是等我背简历？大史都没你这么急。")
    assert report.ok is True
    assert report.score == 1.0


def test_contract_round_trips_through_a2a_payload() -> None:
    contract = build_persona_contract(_profile())
    restored = extract_contract_from_payload({"persona_contract": contract.as_dict()})
    assert restored is not None
    assert restored.name == "罗辑"
    assert restored.relationships == contract.relationships


def test_contract_and_review_packet_carry_period_stage() -> None:
    profile = {**_profile(), "period_name": "新时期晚年时期", "period_stage": "T6"}
    contract = build_persona_contract(profile)
    assert contract.period_name == "新时期晚年时期"
    assert contract.period_stage == "T6"
    assert "当前时期" in contract.render()

    packet = build_review_packet(
        message="你后悔吗？",
        draft="不后悔。",
        persona_contract=contract,
        period={"name": "新时期晚年时期"},
    )
    assert packet.period_name == "新时期晚年时期"
    assert packet.period_stage == "T6"
    assert "当前时期" in packet.render()
    assert "主评：像不像这个角色" in packet.criteria
    assert "早期/晚期混写并入这一项" in packet.criteria
    assert "承诺" not in packet.criteria
    assert "通用助手" not in packet.criteria
