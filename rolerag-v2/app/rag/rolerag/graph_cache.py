"""Process-external snapshot cache for the expensive offline graph build.

PostgreSQL is the durable, settlement-aware store. This cache is different:
it lets a restarted worker skip re-running chapter/scene/event extraction when
the chunk file and build code are unchanged. Key includes chunk mtime and the
mtime of the extractor source, so a logic fix cannot serve a stale graph.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import snapshot
from .store import InMemoryGraphStore


def enabled() -> bool:
    return os.getenv("STORYROLE_ROLERAG_SNAPSHOT", "0").lower() in {"1", "true", "yes", "on"}


def _code_stamp() -> str:
    here = Path(__file__).resolve().parent
    files = [here / "extract" / "events.py", here / "extract" / "pipeline.py", here / "runtime.py"]
    mtimes = [path.stat().st_mtime for path in files if path.exists()]
    return str(max(mtimes, default=0))


def _key(chunks_path: str, mtime: float, novel_id: str, hints_key: str) -> str:
    raw = f"{Path(chunks_path).resolve()}|{mtime}|{novel_id}|{hints_key}|{_code_stamp()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _path(chunks_path: str, mtime: float, novel_id: str, hints_key: str) -> Path:
    root = Path(os.getenv("STORYROLE_ROLERAG_CACHE_DIR") or Path(__file__).resolve().parents[3] / "data" / "cache" / "rolerag")
    return root / novel_id / f"{_key(chunks_path, mtime, novel_id, hints_key)}.json"


def load(chunks_path: str, mtime: float, novel_id: str, hints_key: str) -> InMemoryGraphStore | None:
    if not enabled():
        return None
    path = _path(chunks_path, mtime, novel_id, hints_key)
    if not path.exists():
        return None
    try:
        return snapshot.load(path)
    except Exception:  # noqa: BLE001 - a corrupt cache is a cache miss
        return None


def save(store: InMemoryGraphStore, chunks_path: str, mtime: float, novel_id: str, hints_key: str) -> Path | None:
    if not enabled():
        return None
    try:
        path = _path(chunks_path, mtime, novel_id, hints_key)
        snapshot.save(store, path)
        metadata = {
            "novel_id": novel_id,
            "chunks_path": str(Path(chunks_path).resolve()),
            "chunks_mtime": mtime,
            "code_stamp": _code_stamp(),
            "events": len(store.events()),
            "facts": len(store.facts()),
        }
        path.with_suffix(".meta.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )
        return path
    except Exception:  # noqa: BLE001 - cache write must never break answering
        return None


__all__ = ["enabled", "load", "save"]
