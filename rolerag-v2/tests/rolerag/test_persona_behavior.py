"""Behaviour-level checks for the persona loop, not prompt text only."""

from __future__ import annotations

from app.rag.rolerag.persona.contract import build_persona_contract, check_persona


def _profile(name: str, identity: str, goal: str, fear: str, anti: str) -> dict:
    return {
        "character_name": name,
        "identity": identity,
        "goals": [goal],
        "fears": [fear],
        "anti_patterns": [anti],
        "speech_style": ["短句", "反问"],
        "decision_patterns": ["先观察，再决定要不要卷进去"],
    }


def test_same_event_produces_different_persona_contracts() -> None:
    luoji = build_persona_contract(_profile(
        "罗辑", "玩世不恭的社会学学者，不是救世主", "先把自己活明白", "被当成救世主", "不要写成英雄"
    ))
    shi = build_persona_contract(_profile(
        "史强", "粗粝但精明的警察", "把人活着带回去", "任务失败", "不要写成文弱书生"
    ))
    assert "不是救世主" in luoji.render()
    assert "把人活着带回去" in shi.render()
    assert "不是救世主" not in shi.render()


def test_same_character_period_change_changes_contract() -> None:
    early = build_persona_contract(_profile(
        "罗辑", "早期混日子的社会学教师", "混过去", "被卷入", "不要写成救世主"
    ))
    late = build_persona_contract(_profile(
        "罗辑", "晚年经历过威慑与失去的人", "守住该守的东西", "再次失去", "不要写成全知者"
    ))
    assert "早期混日子" in early.render()
    assert "晚年经历过威慑" in late.render()
    assert early.render() != late.render()


def test_pressure_answer_keeps_character_voice() -> None:
    contract = build_persona_contract(_profile(
        "罗辑", "玩世不恭的社会学学者，不是救世主", "先把自己活明白", "被当成救世主", "不要写成英雄"
    ))
    generic = "作为一个AI，我理解你的期待。首先，我们需要客观地分析这个问题。"
    report = check_persona(contract, generic)
    assert report.ok is False
    assert report.score < 0.9
    assert "AI" in " ".join(report.violations) or "总结" in " ".join(report.violations)
