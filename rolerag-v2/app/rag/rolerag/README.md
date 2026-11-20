# RoleRAG subsystem

Perspective-bounded retrieval for character agents. One world graph, projected
per (character, chapter). The character only ever sees his own projection.

## Layout

```
models.py        domain objects (Entity/Event/Fact/Visibility/Belief/State)
store.py         GraphStore protocol + in-memory store (longest-match surfaces)
schema.py        PostgreSQL DDL (string ids, mirrors models.py)
pg_store.py      full replace / load for one novel
snapshot.py      JSON round-trip
project.py       pure (character, cutoff) -> CognitionState
episodic.py      lazy first-person scene memory
build.py         text -> graph + personas
extract/         chapters, scenes, entities, aliases, events, visibility
retrieval/       scope, route, subgraph
persona/         seed, patterns, state, style, emotion gate
chat/            chat_turn (render + style rewrite), settle
eval/            KBF metric + automatic case generation
service.py       façade + STORYROLE_RETRIEVAL_ENGINE flag
runtime.py       JSONL chunks -> chapters -> RoleRAGRuntime
api_adapter.py   manifest + character rows -> answer; period -> cutoff
cli.py           demo / eval / auto
```

## Commands

```powershell
python -m app.rag.rolerag.cli demo
python -m app.rag.rolerag.cli eval
python -m app.rag.rolerag.cli auto
python scripts/verify_rolerag_pg.py --dsn "<dsn>"
python scripts/eval_real_kbf.py
python scripts/e2e_real_llm.py
python scripts/e2e_multiturn.py
python scripts/blind_eval.py
pytest tests/rolerag -q
```

`STORYROLE_RETRIEVAL_ENGINE` defaults to `rolerag` in the v2 agent; a missing
manifest or build failure degrades to the legacy pipeline for that request.

## Invariants

1. No path to a fact means no belief. Unseen important events are recorded as
   unknowns for refusal, never shown to the renderer.
2. Events are the only write path to relations (`Event.effects -> Fact`).
3. A claim made in dialogue becomes a `Belief`, never a `Fact`.
4. Visibility has five routes; the strongest route wins per (character, event).
5. Style is measured after generation, not assumed from the prompt.
