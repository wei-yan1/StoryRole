import json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.rag.rolerag.build import build_all
from scripts.audit_real_corpus import CAST, CHUNKS

rows = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if "三体I" in l]
groups = defaultdict(list)
for r in rows:
    groups[r["metadata"]["section_index"]].append(r["text"])
text = "\n\n".join(f"第{i}章\n" + "\n".join(groups[s]) for i, s in enumerate(sorted(groups), 1))
out = build_all(text, novel_id="three_body", hints=CAST)
store = out.store
wang = store.find_entity("汪淼")
print("wang", wang.id)
for f in store.facts():
    names = store.entity_name(f.source_id), store.entity_name(f.target_id)
    if "潘寒" in names or "申玉菲" in names:
        print("fact", f.id, names, "event", f.caused_by_event, "ch", f.valid_from)
        print("  fact visible", store.is_visible(wang.id, fact_id=f.id, at=f.valid_from))
        print("  event visible", store.is_visible(wang.id, event_id=f.caused_by_event, at=f.valid_from))
print("wang vis rows for facts:")
for v in store.visibility(wang.id):
    if v.fact_id or v.event_id:
        print(" ", v.route, "fact" if v.fact_id else "event", v.fact_id or v.event_id, "from", v.from_chapter)
