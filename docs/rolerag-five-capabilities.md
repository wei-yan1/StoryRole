# RoleRAG：角色中心 ego-network 与 Laya 接入（实现与验证）

> 工作区：`D:\AgentCode\two\rolerag-v2`
> 本文记录的是已经落地的代码、测试和真实链路，不是设计稿。源码包 `docs/rolerag-v2-source.zip` 已按最新 persona contract / guard / 查询索引重新打包；角色主体闭环详见 `docs/rolerag-subject-bridge.md`，查询层优化详见 `docs/rolerag-query-optimization.md`。

## 五项能力与代码落点

| 能力 | 代码 | 做什么 |
|---|---|---|
| 1–2 跳 ego-network | `app/rag/rolerag/retrieval/ego.py`：`build_ego_network`、`EgoEdge`、`EgoNetwork.path_between` | 从可见 Fact、角色自己的 Belief、可见事件的 `participants` 建边；边带 `sign/weight/valid_from/visibility/certainty/origin`；第一跳含角色本人，第二跳从第一跳邻居扩展到未直接同场的人 |
| 可见性内局部聚类 | `ego.py`：`local_clusters`、`ego_summary` | 不是全书 Leiden 社区；只把 ego 里的邻居按第一人称关系分成“我信得过的 / 我防着的 / 我拿不准的 / 我见过的 / 只在远处见过的”，摘要以“我眼里的他们”开头 |
| 多跳关系检索 | `retrieval/subgraph.py` 的 `relation_query` + `ego.py.relation_evidence`；`retrieval/router.py` 的 `_RELATION`、`RouteDecision.multi_hop` | 两个实体且关系类问题触发；直接边、BFS 路径都先经过可见性；只有同场、没有 Fact/Belief 时明确写成“只见过同场，没看见直接关系”，不把同场冒充背叛/信任 |
| 女娲事实注入 | `persona/seed.py`：`ProfileOverlay.relationships/known/unknown`、`_relationship_strings`；`chat/orchestrator.py`：`build_messages` | `relationships` 对象列表转成 `姓名：关系`；`knowledge_boundary.known/unknown` 进入 system prompt；不再只注入 `rules` |
| Laya 接入 RoleRAG | `agents/storyrole/character_agent.py` 的 RoleRAG 分支；`api_adapter.py`/`runtime.py`/`orchestrator.py` 的 `plan` 参数 | 先跑 `query-planner`（默认 `STORYROLE_DECISION_BACKEND=laya`），把 plan 传给 `answer_from_manifest`；`route(..., plan=...)` 按 `needs_relationship/future_probe/plot_or_fact` 改路由；Laya 不可用时 planner 自身回退规则，不阻断 RoleRAG |

## 真实证据

### 测试

```text
78 passed
```

新增覆盖：
- `tests/rolerag/test_ego.py`：可见性截断、第二跳、边契约、第一人称摘要、多跳路径、未知实体拒答、Laya plan 路由。
- `tests/rolerag/test_profile_overlay.py`：relationships、known、unknown 真进入 prompt。
- `tests/rolerag/test_persona_contract.py`：女娲 contract、render、快检、A2A round-trip。
- `tests/rolerag/test_persona_behavior.py`：同一事件不同角色、同一角色不同时期、施压时仍保持角色立场与口吻。
- `tests/rolerag/test_character_agent_bridge.py`：RoleRAG 检索后旧历史/生成路径仍在。
- `tests/rolerag/test_ego.py::test_visibility_and_scene_indexes_match_bruteforce_filters`：visibility 目标索引与暴力过滤一致，`events_in_scene` 与全表过滤一致。

### 查询层基准

真实图（罗辑 @ period 7 / cutoff 44），`scripts/bench_rolerag_query.py`：

| 阶段 | 优化前 p50 | 优化后 p50 |
|---|---:|---:|
| `analyze_scope` | 176.3 ms | ≈1.7 ms |
| `retrieve`（recall） | 580.1 ms | ≈8.1 ms |
| `retrieve`（relation） | 430.8 ms | ≈9.5 ms |
| `build_ego_network` | 168.9 ms | ≈5.3 ms |
| `ego_summary` | 0.46 ms | ≈0.43 ms |

查询层从约 0.8–0.95 秒降到约 16–18 ms；quick HTTP 仍是 11.16 秒，瓶颈在模型/deep 链路。`kg_visibility` 现有唯一索引已够用，不新增物化表。证据见 `docs/rolerag-query-bench.json`。

### 真实图（罗辑 @ period 7 / cutoff 44）

`scripts/e2e_ego_layers.py` 输出：

```text
ego_nodes = 43
ego_edges = 299
ego_nodes_at_depth_2 = 2
all_edges_have_visibility = true
summary_is_first_person = true
nuwa.relationships = 8
nuwa.known = 9
nuwa.unknown = 8
route = probe
multi_hop = true
```

真实摘要节选（不是作者视角社区报告）：

```text
我眼里的他们（只按我在这个时期能感知到的关系）：
我信得过的：罗辑亲近熊文……；我防着的：罗辑不再信任周围……；我见过的：罗辑和东方延绪同场……
```

真实多跳查询「我怎么看叶文洁和史强的关系」在图里只有同场、没有直接 Fact/Belief，因此证据是：

```text
我只见过叶文洁和史强分别与我同场（第27章起），但没有看见他们之间发生过直接关系
```

这正是“先走图、再过可见性”，而不是用同一句话把两个人硬连起来。

### 真实 HTTP

`scripts/e2e_api_http.py`：

```text
status 200
mode = rolerag
cutoff = 44
profile_injected = true
persona_score = 1.0
persona_rewritten = false
graph_persisted = null（普通聊天不写共享小说图，预期）
planner_intent = plot_or_fact
route = recall
```

`scripts/e2e_relation_http.py`（同一 HTTP/A2A/CharacterAgent/RoleRAG 链路）：

```text
status 200
route = probe
ego_evidence_count = 1
planner_intent = relationship_reflection
profile_injected = true
answer = “他俩没直接来往，关系我哪说得清？”
```

这说明关系问题确实走了 ego evidence，而不是只做直接实体重叠；模型在证据不足时也没有编造“背叛”。

### 像不像闭环

- 女娲 profile → `PersonaContract`（`app/rag/rolerag/persona/contract.py`），真实罗辑 contract 约 3012 字符；
- 生成 prompt 先放 contract，再放 RoleRAG 可见证据；
- quick 本地 `check_persona` 通过则不额外调用语义评审；deep 每轮调用 `consistency-guard`；
- 语义评审按“像不像”判 fail，事实正确但像客服/百科也 fail，并最小幅度重写；
- HTTP/SSE 返回 `persona_fidelity`、`persona_score`、`persona_rewritten`。

真实行为探针（`scripts/e2e_persona_behavior.py`，`docs/rolerag-persona-behavior.json`）：

```text
施压当救世主：不答应，3/3 checks，persona_score=1.0
追问叶文洁与史强：不知道直接关系，不硬编，persona_score=1.0
昨日承诺今天是否作数：还作数，人物连续性成立，persona_score=1.0
```

真实 deep 语义评审：`persona_score=0.72`、`persona_rewritten=true`，说明本地快检通过不等于语义足够像。

### 其它回归

```text
KBF: cases=150 correct=150 accuracy=1.00 failed_cases=0
真实 deepseek 模型 5 轮：5/5 style pass
```

## 已知边界（不粉饰）

1. Laya 0.4.35 已安装到项目 `.venv`；`STORYROLE_DECISION_BACKEND=laya` 默认生效，quick 与 deep 每轮都先走 query-planner 的真实 Laya Router（multilingual checkpoint），Laya 异常时才回退 `rule_fallback`。权重缓存在 Hugging Face cache；首次下载走 `HF_ENDPOINT=https://hf-mirror.com`，启动时后台预热 multilingual，热调用约 0.3–0.4s。
2. 真实图只有 7 条 Fact，关系事实稀疏；因此真实关系查询经常只能得到“同场、无直接关系”。这不是 ego 代码的错，后续要提高 Fact/关系抽取或允许更可信的来源。
3. 当前“局部聚类”是关系 stance 分组，不是 Leiden/标签传播的社区算法；它保证不越出可见性和第一人称，但仍可继续升级为局部连通分量/标签传播。
4. `ego.py` 默认 `max_nodes=60`；真实罗辑图 43 个节点、299 条边，构建约 0.2s 量级；事件参与人数特别大的图仍应继续做边预算。

## 复现命令

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_ego_layers.py
D:\AgentCode\two\.venv\Scripts\python.exe scripts\eval_real_kbf.py
```

HTTP/SSE 需要 `.env` 中的数据库与模型配置：

```powershell
$env:STORYROLE_E2E_PERIOD_ID='7'
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_api_http.py
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_api_stream.py
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_relation_http.py
```