from app.rag.rolerag.chat.orchestrator import LLMRenderer, TurnContext, build_messages
from app.rag.rolerag.llm import FakeLLM
from app.rag.rolerag.models import CognitionState, Entity
from app.rag.rolerag.persona.seed import build_seed, overlay_from_profile
from app.rag.rolerag.store import InMemoryGraphStore


def test_belief_does_not_auto_generate_motive() -> None:
    from app.rag.rolerag.models import Belief

    store = InMemoryGraphStore("test")
    store.add_entity(Entity(id="a", name="罗辑", type="character"))
    store.add_entity(Entity(id="b", name="史强", type="character"))
    store.add_belief(
        Belief(
            character_id="a",
            subject_id="a",
            target_id="b",
            kind="信任",
            sign=1,
            certainty=0.9,
            since_chapter=1,
            channel="saw",
        )
    )
    seed = build_seed(store, "a", 3)
    assert seed.drives == []

    store = InMemoryGraphStore("test")
    store.add_entity(Entity(id="a", name="罗辑", type="character"))
    overlay = overlay_from_profile(
        {
            "identity": "面壁者，宇宙社会学学者",
            "personality": ["玩世不恭", "内里孤独"],
            "goals": ["守住庄颜", "找到宇宙社会学的答案"],
            "fears": ["失去庄颜", "被面壁者身份吞掉"],
            "speech_style": ["短句", "反问多"],
            "anti_patterns": ["不解释设定", "不总结"],
            "core_beliefs": ["人类需要自己的面壁者"],
            "decision_patterns": ["先退一步再出手"],
            "conversation_rules": ["不主动交底"],
            "knowledge_boundary": {
                "rules": ["只能谈序章见过的事"],
                "known": ["我知道宇宙社会学两条公理"],
                "unknown": ["我不知道猜疑链的具体内容"],
            },
            "relationships": [
                {"name": "史强", "relation": "护送我、教我审讯", "evidence": "序章"},
                {"name": "叶文洁", "relation": "杨冬的母亲，向我提出公理", "evidence": "序章"},
            ],
        }
    )
    seed = build_seed(store, "a", 3, overlay=overlay)
    assert seed.identity.startswith("面壁者")
    assert seed.drives[0].want == "守住庄颜"
    assert overlay.relationships[0].startswith("史强：")
    assert overlay.known
    assert overlay.unknown
    context = TurnContext(
        character_id="a",
        cutoff=3,
        message="你是谁",
        state=CognitionState(character_id="a", cutoff=3),
        evidence=[],
        decision=type("D", (), {"kind": "stance", "entities": [], "reason": ""})(),
        scope=type("S", (), {"external_terms": []})(),
        seed=seed,
    )
    prompt = build_messages(context, draft="")[0]["content"]
    assert "女娲画像" in prompt
    assert "守住庄颜" in prompt
    assert "只能谈序章见过的事" in prompt
    assert "史强：护送我、教我审讯" in prompt
    assert "我知道宇宙社会学两条公理" in prompt
    assert "我不知道猜疑链的具体内容" in prompt
    assert "我眼里的他们" in prompt
    assert LLMRenderer(FakeLLM()).render(context).strip()
