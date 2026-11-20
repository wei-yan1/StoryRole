import json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.rag.rolerag.build import build_all
from app.rag.rolerag.retrieval.scope import analyze_scope
from app.rag.rolerag.retrieval.router import route
from app.rag.rolerag.retrieval.subgraph import retrieve
from app.rag.rolerag.chat.orchestrator import guard_unseen_trigger
from scripts.audit_real_corpus import CAST, CHUNKS

rows = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if "三体I" in l]
groups = defaultdict(list)
for r in rows:
    groups[r["metadata"]["section_index"]].append(r["text"])
text = "\n\n".join(f"第{i}章\n" + "\n".join(groups[s]) for i, s in enumerate(sorted(groups), 1))
out = build_all(text, novel_id="three_body", hints=CAST)
store = out.store
name = "雷政委"
entity = store.find_entity(name)
print("character", entity.id, entity.name)
for fact in store.facts():
    names = store.entity_name(fact.source_id), store.entity_name(fact.target_id)
    if "杨卫宁" in names and "叶文洁" in names:
        print("fact", fact.id, names, fact.kind, "ch", fact.valid_from, "event", fact.caused_by_event)
        print("  fact visible", store.is_visible(entity.id, fact_id=fact.id, at=fact.valid_from))
        print("  event visible", store.is_visible(entity.id, event_id=fact.caused_by_event, at=fact.valid_from))
        e = store.event(fact.caused_by_event)
        print("  event title", e.title, "summary", e.summary[:60])
        print("  participants", [(p.role, store.entity_name(p.entity_id)) for p in e.participants])
q = "你还记得杨卫宁骗叶文洁那件事吗"
scope = analyze_scope(q, store, entity.id, 23)
print("scope entities", [(e.name, e.familiar, e.level) for e in scope.entities], "general", scope.is_general)
d = route(q, scope)
print("decision", d.kind, d.reason, "entities", d.entities)
ev = retrieve(store, entity.id, 23, d)
print("evidence")
for item in ev[:6]:
    print(" ", item.kind, item.ref_id, item.text[:60])
d2, ev2 = guard_unseen_trigger(q, d, ev, store=store)
print("after guard", d2.kind, d2.reason, "n", len(ev2))
