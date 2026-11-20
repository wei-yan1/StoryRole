import json
from pathlib import Path

from app.rag.rolerag.api_adapter import answer_from_manifest, hints_from_characters
from app.rag.rolerag.demo import DEMO_HINTS
from app.rag.rolerag.runtime import RoleRAGRuntime, build_from_chunks


def _chunks(tmp_path: Path) -> Path:
    rows = [
        {"text": "青霄门在雪线之上。玄真道人收陆知微为徒。", "metadata": {"book": "测试书", "section_index": 0}},
        {"text": "沈砚隐瞒了陆知微偷药的事。玄真逐沈砚下山。", "metadata": {"book": "测试书", "section_index": 1}},
    ]
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_build_from_chunks_keeps_chapter_order(tmp_path) -> None:
    outcome = build_from_chunks(_chunks(tmp_path), novel_id="test", hints=DEMO_HINTS)
    store = outcome.store
    assert len(store.chapters()) == 2
    assert [row.ordinal for row in store.chapters()] == [1, 2]
    assert store.find_entity("陆知微") is not None
    assert len(store.events()) >= 1


def test_runtime_answers_from_chunks(tmp_path) -> None:
    outcome = build_from_chunks(_chunks(tmp_path), novel_id="test", hints=DEMO_HINTS)
    runtime = RoleRAGRuntime(outcome.store, outcome.cutoff)
    reply = runtime.answer("陆知微", "沈砚为什么被逐", cutoff=2)
    assert reply.text
    assert reply.route in {"recall", "probe", "reject"}
    assert runtime.cutoff_for_period("第二章") == 2
    assert runtime.cutoff_for_period("不存在") == runtime.cutoff


def test_api_adapter_returns_engine_metadata(tmp_path) -> None:
    path = _chunks(tmp_path)
    characters = [
        {"canonical_name": hint["name"], "character_type": hint["type"], "aliases": hint.get("aliases", [])}
        for hint in DEMO_HINTS
    ]
    result = answer_from_manifest(
        {"chunks_path": str(path)},
        novel_id="test",
        character_name="陆知微",
        message="你还记得沈砚被逐出山门那天吗",
        characters=characters,
        period={"chapter_start": "第一章", "chapter_end": "第二章"},
        force_template=True,
    )
    assert result["engine"] == "rolerag"
    assert result["cutoff"] == 2
    assert result["answer"]
    assert result["degraded"] is False


def test_hints_from_characters_accepts_json_aliases() -> None:
    rows = [{"canonical_name": "沈砚", "aliases": '["沈师兄", "砚儿"]'}]
    hints = hints_from_characters(rows)
    assert hints[0]["name"] == "沈砚"
    assert hints[0]["aliases"] == ["沈师兄", "砚儿"]


def test_build_from_chunks_prefers_real_chapter_number(tmp_path) -> None:
    rows = [
        {"text": "玄真收陆知微为徒。沈砚在旁看着。", "metadata": {"book": "书", "section_index": 1, "chapter_number": 1}},
        {"text": "沈砚隐瞒陆知微，随后被逐。", "metadata": {"book": "书", "section_index": 2, "chapter_number": 2}},
    ]
    path = tmp_path / "numbered.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    outcome = build_from_chunks(path, novel_id="test", hints=DEMO_HINTS)
    assert [row.ordinal for row in outcome.store.chapters()] == [1, 2]
    assert outcome.store.chapters()[0].title.startswith("第1章")
