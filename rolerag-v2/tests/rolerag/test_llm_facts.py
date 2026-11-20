import json

from app.rag.rolerag.extract.events import _find_trigger
from app.rag.rolerag.extract.llm_facts import extract_llm_facts
from app.rag.rolerag.models import Entity, Event, Participant
from app.rag.rolerag.runtime import build_from_chunks
from app.rag.rolerag.store import InMemoryGraphStore


class _FakeLLM:
    def __init__(self, rows):
        self.rows = rows

    def complete(self, prompt: str, system: str = "") -> str:
        return json.dumps(self.rows, ensure_ascii=False)


def _chunks(tmp_path):
    rows = [
        {"text": "青霄门在雪线之上。玄真道人收陆知微为徒。", "metadata": {"book": "测试书", "section_index": 0}},
        {"text": "沈砚隐瞒了陆知微偷药的事。玄真逐沈砚下山。", "metadata": {"book": "测试书", "section_index": 1}},
    ]
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_trigger_word_is_not_a_predicate() -> None:
    assert _find_trigger("他眼中藏着杀气，令罗辑生出一股恐慌。") is None
    assert _find_trigger("史强杀罗辑。") is not None


def test_llm_fact_extraction_validates_names_and_deduplicates(tmp_path) -> None:
    store = InMemoryGraphStore("test")
    store.add_entity(Entity(id="a", name="陆知微", type="character"))
    store.add_entity(Entity(id="b", name="沈砚", type="character"))
    candidate = Event(
        id="test:e001.01.01",
        novel_id="test",
        scene_id="test:s001",
        chapter=1,
        title="沈砚隐瞒偷药",
        summary="沈砚隐瞒了陆知微偷药的事。",
        importance=0.6,
        participants=(
            Participant(entity_id="a", role="witness", presence="silent"),
            Participant(entity_id="b", role="actor", presence="active"),
        ),
        source="novel",
    )
    store.add_event(candidate)
    fake = _FakeLLM(
        [
            {
                "event_id": candidate.id,
                "subject": "陆知微",
                "target": "沈砚",
                "kind": "信任",
                "sign": -1,
                "confidence": 0.7,
                "reason": "隐瞒导致信任破裂",
            },
            {
                "event_id": candidate.id,
                "subject": "不存在的人",
                "target": "沈砚",
                "kind": "信任",
                "sign": -1,
            },
        ]
    )
    facts = extract_llm_facts([candidate], store, fake)
    assert len(facts) == 1
    assert facts[0].kind == "信任"
    assert facts[0].caused_by_event == candidate.id
