# RoleRAG 查询层优化结论

> 工作区：`D:\AgentCode\two\rolerag-v2`
> 报告日期：2026-11-15
> 结论：查询层已经优化到毫秒级，继续堆图/表结构的收益远小于模型调用；这里停手。

## 1. 先测，不凭感觉优化

真实图：罗辑，period 7，cutoff 44。

```text
events          4,838
participants    3,717
facts           7
visibility      6,871
entities        96
ego nodes/edges 43 / 299
```

优化前（同一进程，图已热）：

| 阶段 | p50 | p95 |
|---|---:|---:|
| `analyze_scope` | 176.3 ms | 186.5 ms |
| `retrieve`（recall） | 580.1 ms | 623.9 ms |
| `retrieve`（relation probe） | 430.8 ms | 452.1 ms |
| `build_ego_network` | 168.9 ms | 193.2 ms |
| `ego_summary` | 0.46 ms | 0.67 ms |

查询层合计约 **0.8–0.95 秒**，而真实 quick HTTP 总耗时约 **8.6–11.1 秒**。也就是说，主要成本在模型调用，不在 RAG；但 0.9 秒里确实有非常明显的全表扫描。

## 2. 找到的两个真实热点

### 2.1 visibility 按目标全扫

`InMemoryGraphStore.is_visible()` / `best_route()` 原来每次都要遍历这个角色的全部 visibility 行。真实罗辑有 **652 行 visibility**，而 `retrieve` 会为 4,838 个事件逐个调用。

改法：`store.py` 增加目标优先索引：

```text
_visibility_events: (character_id, event_id) -> list[Visibility]
_visibility_facts:  (character_id, fact_id)  -> list[Visibility]
```

`is_visible` / `best_route` 有 event_id/fact_id 时直接命中索引，语义与原来的 `Visibility.covers()` 保持一致。

### 2.2 每个 scene 重排整本书的事件

`subgraph.retrieve()` 在 scene 分支里对每个 scene 调 `store.events(lte=cutoff)`。真实查询触发 **573 次** `events()`，每次都要排序 4,838 个事件，cProfile 里累计 **0.65 秒**。

改法：`store.py` 增加：

```text
_events_by_scene: scene_id -> list[Event]
events_in_scene(scene_id, lte)
```

`retrieve` 的 scene 分支改成只取这个 scene 的事件，不再重排全书。

## 3. 优化后

| 阶段 | p50 | p95 | 变化 |
|---|---:|---:|---:|
| `analyze_scope` | ≈1.7 ms | ≈2.1 ms | 约 100× |
| `retrieve`（recall） | ≈8.1 ms | ≈8.5 ms | 约 69× |
| `retrieve`（relation probe） | ≈9.5 ms | ≈9.8 ms | 约 43× |
| `build_ego_network` | ≈5.3 ms | ≈6.0 ms | 约 29× |
| `ego_summary` | ≈0.43 ms | ≈0.48 ms | 持平 |

RAG 查询层从 **0.8–0.95 秒** 降到 **约 16–18 毫秒**（按 recall/relation 的 scope+retrieve+ego+summary 相加）。真实 quick HTTP 仍是 **11.16 秒**，说明现在瓶颈明确在模型/上下文/生成，不在图检索。

证据文件：`docs/rolerag-query-bench.json`。

## 4. 表结构要不要继续动

### 4.1 PostgreSQL 现有索引已经够用

`kg_visibility` 已有：

```text
uq_kg_visibility_event (character_id, event_id, route) WHERE event_id IS NOT NULL
uq_kg_visibility_fact  (character_id, fact_id, route)  WHERE fact_id IS NOT NULL
idx_visibility_char    (character_id, from_chapter)
```

`kg_event_participants` 有 `idx_participants_entity`，`kg_facts` 有 `idx_facts_pair` / `idx_facts_valid`。当前请求路径是**进程内图查询**，不是每次请求回表，所以再给 `kg_visibility` 加覆盖索引不会改变这次基准。

代表性的数据库单点查询：

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT route, certainty FROM kg_visibility
WHERE character_id='ent:fcc79922d9'
  AND event_id='54a5fd53434a493abafc4005fb0c70a4:e006.27.00'
  AND from_chapter <= 44;
```

实际走 `Bitmap Index Scan on uq_kg_visibility_event`，命中 1 行，`Execution Time: 0.593 ms`。这说明 PostgreSQL 这一层的表索引已经足够，不需要再加物化表或重复索引。

### 4.2 不建物化投影表

可以建“角色 × 时期 × 可见证据”的物化表，但当前内存索引已经把查询压到 10ms 内；物化表会引入：

- 写路径同步；
- 时期/线程失效；
- 存储和一致性成本。

按当前数据规模和延迟目标，这是过度设计，不做。

### 4.3 真正的短板不是表

- 真实 `facts` 只有 **7** 条，关系链稀疏；
- 模型调用占 8–11 秒；
- deep 模式还有 evidence-analysis fallback，单次可到 125 秒。

继续优化 RAG 查询层最多再省几毫秒；继续优化 Facts 抽取和 deep 链路才可能省秒级时间。

## 5. 正确性

```text
78 passed
```

新增 `test_visibility_and_scene_indexes_match_bruteforce_filters`：

- 对每个 event，索引版 `is_visible` 与 `Visibility.covers()` 暴力过滤一致；
- 对每个 scene，`events_in_scene` 与 `events(lte)` 再按 `scene_id` 过滤一致。

没有改检索语义，只改索引。索引改动后真实行为验收仍 3/3 通过（施压不答应、关系 gap 不补事实、昨日承诺今天仍作数），`persona_score=1.0`；quick HTTP 仍 `status=200`、`evidence_count=8`。

## 6. 复现

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q
D:\AgentCode\two\.venv\Scripts\python.exe scripts\bench_rolerag_query.py
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_api_http.py
```

## 7. 一句话

这次优化的是“查询时反复扫全表/重排全书”的结构问题，不是把图做得更大。优化后 RAG 查询层约 16ms、quick HTTP 仍 11s，瓶颈已经清楚地在模型侧；按照“优化很好了就不必继续优化”的原则，查询层到此为止。

源码包 `docs/rolerag-v2-source.zip` 已重新打包，包含最新 `store.py`（visibility/scene 索引）、`retrieval/subgraph.py`、索引一致性测试和 `scripts/bench_rolerag_query.py`。
