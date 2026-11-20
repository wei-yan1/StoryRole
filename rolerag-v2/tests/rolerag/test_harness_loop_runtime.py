"""Loop Engineering contract tests: iteration, no-progress, disk memory, skills."""

from __future__ import annotations

import asyncio
import json

from app.harness.loop import LoopMemory, LoopRuntime, LoopSpec, LoopStep, SkillCatalog


def _spec(**overrides) -> LoopSpec:
    values = {
        "name": "test-loop",
        "max_iterations": 3,
        "interval_seconds": 0.0,
        "no_progress_limit": 2,
        "isolation": "test-scope",
    }
    values.update(overrides)
    return LoopSpec(**values)


def test_loop_stops_on_repeated_no_progress(tmp_path) -> None:
    memory = LoopMemory(tmp_path / "memory.json", namespace="test")
    calls: list[int] = []

    def body(iteration: int, _memory: LoopMemory) -> LoopStep:
        calls.append(iteration)
        return LoopStep(iteration=iteration, status="error", progress=False, reason="same failure")

    report = asyncio.run(LoopRuntime(_spec(), memory).run(body))
    assert calls == [1, 2]
    assert report.stop_reason == "no_progress"
    assert report.as_dict()["passed"] is False
    assert json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))["iterations"]


def test_loop_stops_on_body_stop_and_persists_iterations(tmp_path) -> None:
    memory = LoopMemory(tmp_path / "memory.json", namespace="test")
    calls: list[int] = []

    def body(iteration: int, _memory: LoopMemory) -> LoopStep:
        calls.append(iteration)
        return LoopStep(iteration=iteration, status="ok", progress=True, stop=True, reason="gate passed")

    report = asyncio.run(LoopRuntime(_spec(max_iterations=5), memory).run(body))
    assert calls == [1]
    assert report.stop_reason == "gate passed"
    assert report.as_dict()["passed"] is True


def test_loop_memory_is_disk_backed_and_does_not_reset_on_corruption(tmp_path) -> None:
    path = tmp_path / "memory.json"
    memory = LoopMemory(path, namespace="test")
    memory.append(LoopStep(iteration=1, status="ok", output={"run": 1}))
    assert LoopMemory(path, namespace="test").last_iteration() == 1
    path.write_text("{broken", encoding="utf-8")
    corrupted = LoopMemory(path, namespace="test")
    assert corrupted.data["load_error"] == "invalid_json"
    assert corrupted.data["iterations"] == []


def test_skill_catalog_is_progressive_index_not_full_body(tmp_path) -> None:
    skill = tmp_path / "example.md"
    skill.write_text("# Example Skill\n\nBody that should only load on demand.\n", encoding="utf-8")
    catalog = SkillCatalog([tmp_path / "missing.md", skill])
    index = catalog.index()
    assert index == [{"name": "example", "title": "Example Skill", "path": str(skill)}]
    assert "Body" not in json.dumps(index)
    assert "Body that should only load" in catalog.load("example")
