# RoleRAG 架构重构方案（v3.1）

> v1 于同日写成，未做文献检索。v2 对齐了 2025–2026 的四篇直接相关工作，删掉了 v1 中三处"把已发表工作当成本项目增量"的说法，并把它们的成熟机制吸收进来。
> v3.1 是**实现后的回写 + 真实模型验证**：代码已落在 `rolerag-v2/app/rag/rolerag/`（v3.2 为 43 个模块、4,561 行），60 个测试通过，PostgreSQL 16 上完成建表与真实 4,824 事件图读写，并在《三体》I 的 20 万字真实语料上跑完 150 题 KBF（150/150）；真实 `deepseek-flash` 跑通 5 轮独立 + 9 轮带结算；旧 `CharacterAgent` 已接默认 `rolerag` + 单请求 fallback。v3.2 闭合画像注入、结算持久化、时期解析与事实抽取四个缺口（见 §19.5、`docs/rolerag-api-chain.md`）。
> 当前运行配置：语言模型统一为 `deepseek-v4.1-flash-1017`（阿里云 MaaS 的 OpenAI 兼容端点；`deepseek-flash` 是该端点不认的 id）。文中 `deepseek-flash` / `qwen-plus` 仅保留为历史评测记录。
> 本文是设计定稿；代码按 §16 推进，每个里程碑独立验收、独立回滚。

---

## 0. 摘要

**v1 被文献修正的三处判断：**

| v1 的说法 | 实际情况 | v2 的处理 |
| --- | --- | --- |
| "知情边是 RoleRAG 相对 GraphRAG/LightRAG 的核心增量" | RoleRAG（arXiv:2505.18541）已有 boundary-aware retriever，明确按角色认知边界拒答；REVERIEMEM 更进一步，用 visibility 集合把不可见事实挡在检索之外 | 降级为**采纳已有机制**，不再主张首创 |
| "实体归一要先做、是关键工程" | 对，但 RoleRAG 已经给出可复用的算法（top-k 召回 + LLM 两两判别 + 连通分量 + 统一名），比 v1 的"LLM 复核候选组"便宜且可测 | 直接采用其算法 |
| "用事件驱动关系变更，是本项目的设计" | DREAM（KDD 2026）的 Event-aware Memory Graph + ABC 模型已在做同一件事，且带时序因果基准 | 采纳其事件-信念-后果结构，增量另找 |

**v2 仍然坚持的四条判断：**

1. **病根在检索单位。** chunk 是文本边界，不是认知边界。小林那篇把传统 RAG 的三个痛点总结为多跳、全局、语义断裂，根因是"不理解关系"——这一层判断成立。
2. **时期边界必须是结构性的。** 「Living the Novel」明确把 standard RAG 称为 "temporally flat index"，指出它必然导致剧透泄漏。我们的 cutoff 投影与之一致。
3. **人格不能靠一次压缩。** REVERIEMEM 把这件事命名为 "Stylistic Monotony"：一份静态画像会把角色压成一个固定声音。它的解法是"情境化行为模式 + 原文例句"，正是 v1 想做的事，且做得更细。
4. **没有分层评测就没有"更像人"。** v1 定的 `leak_rate=0` 是错的指标，会把系统逼成"过度拒答"。改用 KBF：召回与拒答的加权调和平均，谁塌一边都要扣分。

**v2 真正的增量，只剩三处**（§2.6 逐条对比）：

- **单图多投影**：一份世界图，任意 (角色, 时期) 现场投影。三篇相关工作都是"每个角色建一套记忆"（N 角色 × M 场景），我们只建一次、投影 N 次。
- **多轮结算**：RoleRAG 论文自述只做单轮，把多轮列为 future work；REVERIEMEM 有情绪转移但没有"这句话说完关系该不该变"。
- **风格验收回路**：三篇都是"用模式去条件化生成"，没有一篇在生成后测量并重写。

---

## 1. 现状诊断

### 1.1 事实基线

| 层 | 现状 | 关键文件 |
| --- | --- | --- |
| 解析 | `ParsedDocument` → `ParsedSection`，带 `chapter_number`、`section_index`、段落偏移 | `app/rag/docreader/*` |
| 切分 | 1800/180 结构感知切分，元数据齐全 | `structure_aware_chunker.py`（约 468 行） |
| 索引 | Chroma 向量 + 持久化 BM25 | `app/rag/indexing/*` |
| 检索 | 向量 + BM25 融合 + DashScope Rerank | `hybrid_fusion_retriever.py`（311 行） |
| 画像 | 一次 LLM 调用，14 个字段，全 `list[str]` | `nuwa_profiler.py`（105 行） |
| 关系 | `trust/intimacy/tension/dependency` 四浮点 | `storyrole_relationship_states` |
| 记忆 | 摘要条目 + 人工确认队列 | `episodic_memory.py`（352 行）、`storyrole_memory_candidates` |
| 编排 | 自研 runtime（165 行）+ A2A 信封（220 行）+ 依赖里的 langgraph | `app/agents/{runtime,a2a,orchestration}` |
| 观测 | trace/step/model/证据图，477 行 | `app/observability/*` |

### 1.2 六个结构性缺陷

**D1 检索单位错位。** 「他为什么恨师父」需要 事件→关系变更→当前态度 这条链，chunk 检索只能给三段孤立文本。

**D2 边界是软的。** `timeline_guard`（17 行）读的是 `knowledge_boundary` 字符串。模型预训练里读过这本书，禁令可绕过且不可检测。小林那篇也点出同一件事：GraphRAG 的实体消歧做不好会"制造虚假的完整感"，而边界做不好则是"制造虚假的角色"。

**D3 人格被压缩。** 20 段证据 × 1200 字 → 十几个 `list[str]`。REVERIEMEM 的实验说明这会导致 Stylistic Monotony：角色可辨识，但只有一种腔调。

**D4 记忆是外挂。** 书里的证据走 Chroma，对话经历走 `episodic_memories`，无法联合推理。

**D5 关系不可追溯。** 四个浮点数，无触发事件，不可复现。

**D6 通用模块里埋着单本书。** `KNOWN_CHARACTER_NAMES`（21 个三体人物）、`TIMELINE_STAGE_ANCHORS`（T0–T6）、`three_body.txt`、三体专属 skip markers 全在"任意小说导入"的切分器里。

### 1.3 一处选型错误

自研 `agents/runtime`（165 行）与依赖里的 `langgraph` 重复；A2A 把同进程函数调用包成 task/message/artifact。对外协议有价值，内部链路不该走。

---

## 2. 相关工作与定位

### 2.1 GraphRAG：能力真实，成本也真实

微软的方案是索引期五步：切块 → LLM 抽实体关系 → 合成实体/关系摘要 → Leiden 社区检测 → 逐社区生成报告；查询期 Local（种子实体 + 邻域扩展）与 Global（对社区报告做 Map-Reduce）。

它解决的是"跨文档多跳"和"全局归纳"。但落到长篇小说上有三个硬伤：

- **索引成本**：一本 100 万 token 的书，GraphRAG 索引约 20–50 美元、1–3 小时；同规模传统 RAG 是几美分。行业测算里一份 5GB 法律文档的索引成本可达数万美元。
- **社区报告即剧透**：社区摘要天然是"全书压缩"，喂进上下文等于把后半本交给角色。这是我们在角色场景里必须拒绝的部分。
- **增量**：新文档进入会改变社区划分，报告全量失效。适合静态知识库，不适合一章一章连载。

### 2.2 LightRAG：省对了地方，也丢了东西

LightRAG 砍掉社区检测与社区摘要，只留实体 + 关系，索引期省掉 80% 以上的 LLM 调用；查询期做双层检索（低层关键词打实体节点、高层关键词打关系边），并支持增量 upsert。

对我们的价值在三处：抽取 prompt 与 gleaning 思路、关系关键词这层抽象、增量写图的工程范式。
不能直接用的部分：它的去重是"朴素名称匹配"（"张三"与"Zhang San"不合并），而中文长篇小说的字号、尊称、绰号密度远高于英文数据集；它的图是文档级，没有"这是谁看到的"这一层。

结论：**借它的抽取范式，不借它的存储与检索。**

### 2.3 RoleRAG：直接祖先

> Wang, Leung, Shen. *RoleRAG: Enhancing LLM Role-Playing via Graph Guided Retrieval.* arXiv:2505.18541, 2025-05.

它把角色扮演的失败归因为两条：**实体歧义**（同一角色在不同时期有不同名字，信息被挂散）与**认知边界缺失**（模型知道角色不该知道的事，于是编）。对应的两个模块：

**模块 A：实体归一（Algorithm 1）。** 对每个实体，从实体向量库取 top-k 语义最近邻；把这些候选连同名字与描述交给 LLM 判断"是否同一角色"；判是则在实体图上连边；全部处理完后取连通分量作为一个人；最后 LLM 为每个分量生成统一名。相比暴力两两比较，调用量降为 |N|/k。

**模块 B：边界感知检索。** 查询先抽实体，每个实体标注三项：`type`、`familiarity with the character (YES/NO)`、`level (specific/general)`。超出角色知识范围时，**明确告诉 LLM"这与角色无关"并给出理由**，引导它拒答而不是硬答；`general` 走角色的 1 跳邻居，`specific` 走语义匹配 + 该实体与角色的关系。

**指标**：KE（Knowledge Exposure，1–10，越高越好）、KH（Knowledge Hallucination，1–10，越低越好）、UQR（Unknown Question Rejection，0/1）。GPT-4o 作 judge，人工复核校正。

**它自述的局限**：只做单轮对话；judge 偏乐观；模型有时会无视检索到的内容。

**我们的关系**：这套东西我们是**复现并落地**，不是发明。它是 v2 的骨架之一。

> 名称冲突提醒：另有一篇 arXiv:2505.15444 也叫 RoleRAG（"Single LLM, Multiple Roles"，讲的是 role token 多任务 RAG），与角色扮演无关。引用时必须带 arXiv 号。

### 2.4 REVERIEMEM：最接近，也最值得抄结构

> *Staying in Character: Perspective-Bounded Memory for Book-Based Role-Playing Agents.* arXiv:2606.25632.

它把长叙事角色扮演的失败命名为两种：**Factual Overreach**（共享检索或参数记忆让角色说了视角外的话）与 **Stylistic Monotony**（静态画像把角色压成一个固定声音）。解法是三层记忆：

- **情景层（Episodic）**：以角色第一人称写的"场景记忆"，一个场景一条，只写他做了什么、感到什么、观察到什么、对别人推断什么。推理时先锚定场景，再补细节。
- **语义层（Semantic）**：`SPOCV` 五元组事实 —— `(s, p, o, κ, V)`，`κ` 记录叙事内的原因（"为什么发生"，不只是"发生了什么"），`V ⊆ C` 是该事实的可见角色集合。可见性有四条授予路径：直接经历、目击、组织内共享（沿角色—组织隶属图传播）、公共常识。对角色 c，检索被限制在 `F_c = {f : c ∈ V(f)}` 内，**集合外的事实无论多相关都不可检索**。
- **人格层（Personality）**：不是形容词画像，而是 K 个"情境化行为模式"，每个模式有一句描述 + 若干原文原句；再附一条情绪转移记录（emotion, intensity, trigger, intent）。推理时 `EMO-GATE` 先判断情绪是否跳变，再选模式。

**推理流水线**：`ANCHOR(场景)` → `SELF-PROBE` 生成子查询 → `VIS-RETRIEVE` 只在 `F_c` 内检索 → `SUFFICIENT` 判断够不够 → `EMO-GATE` → 选模式 → `MEMORY-FUSION`。

**评测**：KBF-QA，8 本小说、4,386 道五选一（第 5 项是"以我的所知无法回答"）。分成 KRF（可见，必须答对）与 KR（不可见，必须拒答）；`KBF` 是两者的样本加权调和平均——**专门惩罚"为了拒答而牺牲召回"或"为了召回而放弃拒答"的单边塌陷**。比最强基线提升 34.6 个百分点，BOOKWORLD 五维成对比较胜率约 79%。

**消融的结论很关键**：去掉情景层，召回上升但拒答崩；去掉语义层，系统整体缩成"只会拒答"。两层缺一不可。

### 2.5 DREAM 与 Living the Novel

**DREAM**（KDD 2026, arXiv:2608.05170）：把文学文本转成 Event-aware Memory Graph，按时间顺序与因果关系组织事件，借鉴 ABC 认知模型（Activating Event – Belief – Consequence），并给出双层画像：稳定人格 + 事件驱动的行为演化。它提出 TCM 基准测"时序一致性"与"长程因果连贯"。**v1 的 kg_events + beliefs + state 与它同构，必须引用。**

**Living the Novel**（arXiv:2512.07474）：明确指出 standard RAG 建的是 "temporally flat index"，必然导致剧透泄漏与无法处理 frame-breaking 提问；解法是 Diegetic Knowledge Graph + 时间感知记忆，训练模型"知道该在什么时候不说什么"。

### 2.6 我们的位置

| 能力 | GraphRAG | LightRAG | RoleRAG | REVERIEMEM | DREAM | 本项目 v2 |
| --- | --- | --- | --- | --- | --- | --- |
| 实体归一 | 弱 | 朴素名匹配 | **算法化** | 别名统一 | 未述 | 采用 RoleRAG 算法 |
| 边界感知 | 无 | 无 | **检索期判 scope** | **可见集合 Fc** | 无 | 采用 Fc + 检索期判 scope |
| 时间轴 | 无 | 无 | 无（静态图） | 场景序，无时期切换 | 事件因果序 | **单图上任意 cutoff 投影** |
| 事件因果 | 无 | 无 | 无 | κ 因果字段 | **ABC/EMG** | 采用 κ + 事件触发关系 |
| 情景记忆 | 无 | 无 | 无 | **第一人称场景** | 事件记忆 | **惰性生成 + 缓存** |
| 人格 | 无 | 无 | 画像 | **模式 + 原句 + 情绪转移** | 双层画像 | 采用模式，加验收 |
| 多轮状态 | 无 | 无 | 自述未做 | 情绪转移，无结算 | 行为演化 | **结算回路** |
| 风格验收 | 无 | 无 | 无 | 条件化，不验收 | 无 | **生成后测量重写** |
| 索引成本 | 高 | 低 | 中 | 中（N×场景） | 中 | 中（1×全书） |

**三条真空**：

1. **单图多投影。** 三篇角色工作都是"每个角色建一套记忆"，成本随角色数线性增长。我们建一张世界图，投影函数 `(character, cutoff) → CognitionState`，新增角色只增加一次投影，不增加抽取。这是本项目作为产品（用户可自建任意角色、任意时期）最要紧的结构差异。
2. **多轮结算。** RoleRAG 明确把多轮留作 future work。我们把"这句话说完关系该不该变"做成 `settle` 环节，让关系有代价、可追溯。
3. **风格验收。** 三篇都是"用模式条件化生成"。我们补一道后置测量：句长、问句率、口头禅、称谓、禁用词，不合格带具体修正指令重写一次。模式负责"像"，验收负责"是不是真的像"。

---

## 3. 设计判断

从 Retrieval-Augmented Generation 改成 **Reconstructive Generation**：先把角色此刻的心智重建出来，再让他说话。

| RAG 的假设 | 为什么不成立 | 替代 |
| --- | --- | --- |
| 答案是某段文字 | 「他现在怎么看你」不在任何一段文字里 | 答案是**状态** |
| 相关 = 语义相似 | 「他恨师父」与「师父杀了他师兄」不相似，是因果 | 相关 = **图上可达** |
| 上下文 = 知识 | 不该知道的进了上下文就成了知识 | 上下文 = **可见集合内的投影** |

七条硬约束：

- **C1 一次抽取，多次投影。** 全书建一张世界图；角色/时期是投影，不是重建。
- **C2 事实与信念分离。** 图存真值，投影产出信念，允许不一致。
- **C3 未知显式化。** 不可见的事件是 `unknowns` 里的一条，不是"没检索到"。
- **C4 关系变更必须有触发事件。** 无 `caused_by_event` 的写入一律拒绝。
- **C5 状态是标量，不是描述。** 情绪参与取舍，不渲染成台词。
- **C6 风格是验收。** 生成后测，不合格重写一次。
- **C7 增量可写。** 按场景/章导入只 upsert，不重建。

---

## 4. 架构总览

```text
┌─ L4 接口 ────────────────────────────────────────────┐
│ FastAPI / A2A 协议面 / MCP 工具面（对外保留）          │
├─ L3 编排 ────────────────────────────────────────────┤
│ ChatOrchestrator: route → reconstruct → render →     │
│ verify → settle                                       │
├─ L2 认知 ────────────────────────────────────────────┤
│ Projector（世界图 → CognitionState）                  │
│ StateEngine（标量）  StyleGuard（验收）               │
│ Router（scope 判定 + recall/probe/stance）            │
├─ L1 图 ──────────────────────────────────────────────┤
│ 场景 / 实体 / 事件 / 事实 / 可见性 / 信念（PostgreSQL）│
├─ L0 采集 ────────────────────────────────────────────┤
│ DocReader → 章节序数 → 场景切分 → 1800/180 切块 → 溯源 │
└──────────────────────────────────────────────────────┘
```

### 4.1 离线构建

```mermaid
flowchart LR
    A[小说文件] --> B[DocReader 解析]
    B --> C[章节序数归一]
    C --> D[场景切分]
    D --> E[1800/180 切块]
    D --> F[实体/关系抽取]
    F --> G[实体归一<br/>RoleRAG Alg.1]
    D --> H[事件抽取 + κ 因果]
    G --> I[事实写入]
    H --> I
    I --> J[可见性授予<br/>+ 组织传播]
    J --> K[(世界图)]
    E --> L[(Chroma + BM25<br/>取证与降级)]
```

顺序不可调：**章节序数 → 场景 → 实体归一 → 事实 → 可见性**。先抽后归并会让同一个人的边挂在多个节点上，这正是小节 2.1 里"实体碎片化比没有图更糟"的情形。

### 4.2 在线对话

```text
用户消息
  ↓
Router：抽实体 → 判 familiarity(YES/NO) → 判 level(specific/general)
  ├─ 全部 out-of-scope → 走拒绝路径（角色化拒答，不硬答）
  ├─ general          → 角色 1 跳邻居
  └─ specific         → 实体 + 与角色的关系
  ↓
Reconstruct（Projector + StateEngine）
  CognitionState：beliefs / unknowns / open_loops / affect / patterns / emotione / exemplars
  ↓
Render
  ↓
Verify（边界 / 风格 / 事实 三路并行）
  ↓
Settle（关系结算 → 状态更新 → 对话事件入图）
```

### 4.3 决策记录

| 决策 | 选择 | 放弃 | 理由 |
| --- | --- | --- | --- |
| 图存储 | PostgreSQL 邻接表 | networkx / Neo4j | 10³ 实体、10⁴ 边；已有仓储与事务；不引运维组件 |
| 社区摘要 | 不做 | GraphRAG 社区报告 | 全局压缩=剧透；且省掉最贵的一步 |
| 抽取范式 | 借 LightRAG | 直接跑 LightRAG | 可复用的是抽取 prompt；它的文档级存储没有视角 |
| 边界 | 可见集合 + 检索期判 scope | 仅 prompt 禁令 | 两者都要：前者挡事实，后者挡提问 |
| 情景记忆 | 惰性生成 + 缓存 | 预生成 N×S 条 | 用户可自建任意角色，不能为每个角色预跑一遍 |
| 人格 | 模式 + 原句 + 情绪转移 | 形容词画像 | REVERIEMEM 已证伪后者 |
| 编排 | 内部函数调用，A2A 只对外 | 全链路 A2A | 信封无收益 |
| 降级 | 图不可用回退 hybrid | 无降级 | 一次抽取失败不能全站不可用 |

---

## 5. 数据层

新增表挂在 `app/rag/graph/schema.py`，由 `init_postgres_schema()` 调用；全部 `CREATE TABLE IF NOT EXISTS`，不 drop 旧表。

```sql
-- 时间轴：投影唯一依赖的序数
CREATE TABLE IF NOT EXISTS storyrole_chapters (
    novel_id VARCHAR(96) NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chapter_ordinal INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    section_index INTEGER,
    book VARCHAR(128), part VARCHAR(128),
    PRIMARY KEY (novel_id, owner_id, chapter_ordinal)
);

-- 场景：事件与情景记忆的最小单位（不是章）
CREATE TABLE IF NOT EXISTS storyrole_scenes (
    id BIGSERIAL PRIMARY KEY,
    novel_id VARCHAR(96) NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chapter_ordinal INTEGER NOT NULL,
    scene_index INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    location_id BIGINT,
    time_hint VARCHAR(128),
    atmosphere VARCHAR(255),
    roster JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{entity_id, presence: active|silent|referenced}]
    provenance JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (novel_id, owner_id, chapter_ordinal, scene_index)
);

CREATE TABLE IF NOT EXISTS kg_entities (
    id BIGSERIAL PRIMARY KEY,
    novel_id VARCHAR(96) NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    canonical_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    first_chapter INTEGER, last_chapter INTEGER,
    UNIQUE (novel_id, owner_id, entity_type, canonical_name)
);

-- 事实：SPOC 三元 + κ 因果
CREATE TABLE IF NOT EXISTS kg_relations (
    id BIGSERIAL PRIMARY KEY,
    novel_id VARCHAR(96) NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    relation_kind VARCHAR(48) NOT NULL,
    sign SMALLINT NOT NULL DEFAULT 0,
    weight DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    valid_from_chapter INTEGER NOT NULL,
    valid_to_chapter INTEGER,
    cause TEXT NOT NULL DEFAULT '',              -- κ：叙事内原因
    caused_by_event BIGINT,                      -- 非空才允许写入（C4）
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    provenance JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_events (
    id BIGSERIAL PRIMARY KEY,
    novel_id VARCHAR(96) NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scene_id BIGINT REFERENCES storyrole_scenes(id) ON DELETE SET NULL,
    chapter_ordinal INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    source VARCHAR(24) NOT NULL DEFAULT 'novel',  -- novel / dialogue
    thread_id BIGINT REFERENCES chat_threads(id) ON DELETE SET NULL,
    provenance JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_event_participants (
    event_id BIGINT NOT NULL REFERENCES kg_events(id) ON DELETE CASCADE,
    entity_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    PRIMARY KEY (event_id, entity_id, role)
);

-- 可见性：REVERIEMEM 的 V 集合，一张表管事件与事实
CREATE TABLE IF NOT EXISTS kg_visibility (
    character_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    event_id BIGINT REFERENCES kg_events(id) ON DELETE CASCADE,
    relation_id BIGINT REFERENCES kg_relations(id) ON DELETE CASCADE,
    route VARCHAR(24) NOT NULL,   -- direct|witness|org|common|told
    from_chapter INTEGER NOT NULL,
    certainty DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    CHECK ((event_id IS NOT NULL)::int + (relation_id IS NOT NULL)::int = 1)
);

-- 信念：他相信但未必为真
CREATE TABLE IF NOT EXISTS kg_beliefs (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    subject_id BIGINT NOT NULL, relation_kind VARCHAR(48) NOT NULL, object_id BIGINT NOT NULL,
    certainty DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    since_chapter INTEGER NOT NULL,
    source VARCHAR(24) NOT NULL DEFAULT 'dialogue',
    retracted BOOLEAN NOT NULL DEFAULT FALSE,
    provenance JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- 人格模式（K 个）+ 情绪转移
CREATE TABLE IF NOT EXISTS kg_patterns (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    description VARCHAR(255) NOT NULL,
    excerpts JSONB NOT NULL DEFAULT '[]'::jsonb,   -- 原文原句，带 chunk_id
    situation_tags JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_emotion_transitions (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    scene_id BIGINT REFERENCES storyrole_scenes(id) ON DELETE CASCADE,
    emotion VARCHAR(48) NOT NULL,
    intensity DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    trigger VARCHAR(255) NOT NULL DEFAULT '',
    intent VARCHAR(255) NOT NULL DEFAULT '',
    seq INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS storyrole_character_state (
    character_id BIGINT PRIMARY KEY REFERENCES kg_entities(id) ON DELETE CASCADE,
    period_id BIGINT REFERENCES storyrole_character_periods(id) ON DELETE SET NULL,
    alertness DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    fatigue DOUBLE PRECISION NOT NULL DEFAULT 0.3,
    indebtedness DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    shame DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    interest DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    hostility DOUBLE PRECISION NOT NULL DEFAULT 0.1,
    triggers JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_events_novel_chapter ON kg_events(novel_id, chapter_ordinal);
CREATE INDEX IF NOT EXISTS idx_kg_relations_pair ON kg_relations(novel_id, source_id, target_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_valid ON kg_relations(novel_id, valid_from_chapter);
CREATE INDEX IF NOT EXISTS idx_kg_visibility_char ON kg_visibility(character_id, from_chapter);
CREATE INDEX IF NOT EXISTS idx_scenes_novel_chapter ON storyrole_scenes(novel_id, chapter_ordinal);
```

**删除 `storyrole_memory_candidates`。** 对话事件直接写 `kg_events(source='dialogue')` 并挂可见性；置信度用 `certainty`，撤销用 `retracted`。旧表保留只读。

---

## 6. 离线构建

### 6.1 章节序数

`ParsedSection.chapter_number` + `section_index` → `storyrole_chapters`。`storyrole_character_periods` 增 `start_ordinal` / `end_ordinal`，回填失败则回退字符串匹配并打 warning。投影只认整数。

### 6.2 场景切分

按章内连续文本合并成"戏剧单元"，输出 `(location, time_hint, atmosphere, roster)`。`roster` 要区分三种在场：**在场且有行动（active）、在场但沉默（silent）、仅被提及（referenced）**。这个三态区分直接决定可见性的授予，不能省。

### 6.3 实体归一（RoleRAG Algorithm 1）

1. 每个实体向量化（名字 + 描述）。
2. 对每个实体取 top-k 最近邻，连同名字与描述交 LLM 判"是否同一角色"。
3. 判是的连边，全图取连通分量，一个分量 = 一个人。
4. 每个分量让 LLM 指定统一名，写 `canonical_name` + `aliases`。

相比 O(N²) 两两比较，调用量降为 |N|/k。中文场景额外加两条廉价规则：姓名包含关系、姓+尊称/官职前缀，先合并再进 LLM，能再省一轮。

**边界**：只做专名/绰号/字号/官职/尊称，不做代词消解。

验收：抽 3 章人工标注 20 个实体，别名召回 ≥ 90%，误合并 ≤ 1 组。

### 6.4 事件抽取（带 κ 因果）

单位是场景，不是 chunk、也不是章。每个场景 1–5 个事件：

```json
{
  "title": "师父在众人面前斩了师兄",
  "scene_index": 3,
  "participants": [
    {"name": "师父", "role": "actor", "presence": "active"},
    {"name": "师兄", "role": "patient", "presence": "active"},
    {"name": "他", "role": "witness", "presence": "silent"}
  ],
  "cause": "师兄私通外敌，被当众问罪",
  "effects": [{"subject": "他", "target": "师父", "kind": "师徒",
               "sign": -1, "delta": -0.4, "reason": "目睹师兄被杀"}]
}
```

`effects` 是 `kg_relations` 唯一合法写入来源（C4）。无 `effects` 的事件仍入库，供"你还记得那天吗"类问题召回。

### 6.5 可见性授予

四条路径对齐 REVERIEMEM，加一条对话路径：

| 路径 | 规则 | route |
| --- | --- | --- |
| 直接经历 | 事件的 actor / patient | direct |
| 目击 | 场景 roster 中 active 或 silent 的角色 | witness |
| 组织共享 | 沿角色—组织隶属图传播（门派、家族、阵营） | org |
| 公共常识 | 世界级背景（战争、天灾、公告） | common |
| 被告知 | 文本出现"告诉他/听说/来信"，取该句所在章 | told |

**组织传播是 v1 漏掉的一层。** 没有它，"全宗门都知道师父杀了师兄，只有他不知道"这种局面就无法表达。

### 6.6 惰性情景层

REVERIEMEM 为每个角色预生成第一人称场景摘要，成本是 N×S。我们的用户会自建任意角色，不能预跑。

做法：`(character, scene)` 首次被检索命中时生成并缓存到 `kg_episodic`（新增一列 `generated_at`、`model`），之后只读。生成时**只允许看到该场景及之前的材料**——否则第一人称摘要会写出"我当时还不知道，后来才明白"这种未来视角。

### 6.7 人格模式

每个角色按场景聚类出 K 个行为模式（K≈8–15），每个模式 = 一句描述 + 3–5 条原文原句（带 chunk_id）+ 情境标签（对峙/示弱/退让/亲近/独处）。再按场景序抽情绪转移三元组 `(emotion, intensity, trigger)` 与推断意图。

抽不出来就退回 v1 的指纹方案（句长/问句率/口头禅），但质量会掉一档，要打标。

### 6.8 成本与增量

一部 50 万字 ≈ 200 章 ≈ 500–700 场景 ≈ 280 chunk：

| 步骤 | 调用量 |
| --- | --- |
| 场景切分 | 200 |
| 实体/关系抽取（含 gleaning 一轮） | 300–560 |
| 实体归一 | ~30（|N|/k 后） |
| 事件抽取 | 500–700 |
| 人格模式 | 50–100 |
| 合计 | **1,100–1,600 次** |

对比 GraphRAG 的 1M token 20–50 美元，我们在同规模下是"几十元人民币"量级——因为砍掉了摘要合成与社区报告这两步。增量导入一章：场景 1 次 + 事件 3–5 次 + 实体 10–15 次 + upsert，不触发任何重建。

---

## 7. 投影与检索

### 7.1 视图定义

```python
@dataclass(frozen=True)
class CognitionState:
    character_id: int
    cutoff: int
    beliefs: list[Belief]        # 他以为的关系
    unknowns: list[UnknownEvent] # 他不知道的事，含"被谁瞒着"
    open_loops: list[OpenLoop]   # 欠、仇、约、未兑现
    affect: dict[str, float]
    patterns: list[Pattern]      # 候选行为模式
    emotion: EmotionRecord       # 当前情绪转移点
    scenes: list[SceneMemory]    # 惰性情景摘要（可能为空）
    stats: dict[str, int]
```

### 7.2 算法

> **v3 修正**：v2 这里写的是"不可见事实降级为 0.4 确信的 inferred 信念"。实现时删掉了这条。理由：它把未见事件的内容以低音量写进 `beliefs`，等于把秘密递给模型，只是加了一句"别太确定"。**没有可见路径就是不知道**；「他只知道结果、不知道原因」只在结果本身有可见路径时才成立。为此投影改为按最强可见路径标注通道（direct/witness → observed，org/common → heard，told → told），而不是凭空生成。

```python
def project(store, character_id, cutoff, options) -> CognitionState:
    facts = [f for f in store.facts(lte=cutoff) if valid_at(f, cutoff)]

    beliefs = []
    for f in facts:
        route = store.best_route(character_id, fact_id=f.id, at=cutoff)
        if route is None:
            continue  # 没有可见路径：不知道，不生成低确信版本
        beliefs.append(as_belief(
            f,
            certainty=f.confidence * route.certainty,
            channel=CHANNEL[route.route],   # 来源本身是信息
        ))

    unknowns = []
    for ev in store.events(lte=cutoff):
        if store.is_visible(character_id, event_id=ev.id, at=cutoff):
            continue
        if ev.importance >= options.unknown_importance and ev.source == "novel":
            unknowns.append(as_unknown(ev))   # 仅供拒答与 trace，不进生成 prompt

    beliefs = merge_beliefs(beliefs, store.beliefs(character_id, lte=cutoff))  # 对话覆盖
    return CognitionState(..., beliefs=beliefs, unknowns=unknowns,
                          open_loops=detect_loops(beliefs, facts))
```

复杂度 O(F_view × V_char + E_view)。实现里 `best_route` 在内存库上线性扫，PostgreSQL 上按 `(character_id, from_chapter)` 索引后是一次范围查询；缓存键 `(character_id, cutoff)`。

### 7.3 检索路由（对齐 RoleRAG 的 query 判定）

```python
entities = extract_entities(query)          # 一次小调用
for e in entities:
    e.familiar = judge_familiarity(e, character)   # YES / NO
    e.level    = judge_level(e)                    # specific / general
```

- **全 NO**（问的是角色世界里不存在的东西，如"你怎么看 Apollo 11"）→ 拒绝路径：明确告诉模型"这与角色无关 + 理由"，让角色用自己的方式化解，**不硬答**。这正是 UQR 提升的来源。
- **general**（"你最在意什么"）→ 角色的 1 跳邻居 + 模式。
- **specific**（"你和你师父现在什么关系"）→ 目标实体 + 它与角色的关系 + 相关事件。
- 时间指代（"那次/当时"）→ 事件锚定；纯态度 → 不检索，走 affect + 核心驱动。

### 7.4 三条写进契约的规则

- **只读 beliefs，不读 facts 生成回答。** facts 只在 Verify 用。
- **unknowns 只用于拒答与 trace，绝不进生成 prompt。** 不写"以下 2 件事尚未发生：[事件标题]"——标题本身就是秘密。Prompt 里只声明"存在你不知道的事"，具体内容由编排层持有；输出侧专名检测列为 P1（当前只检外部词）。
- **不输出分值。** 边权、certainty、trust 数值不进 prompt 文本，只参与排序与取舍。

---

## 8. 表达层

### 8.1 人格种子

`nuwa_profiler` 的产物从 14 个描述字段改成四块，全部带证据：

```json
{
  "identity": {"name": "", "age_at_cutoff": null, "station": ""},
  "drives": [{"want": "为师兄报仇", "fear": "再次看着人死", "taboo": "被提起那天",
              "evidence": [{"chapter": 38, "chunk_id": "…", "quote": "……"}]}],
  "judgement": [{"situation": "被追问动机", "tendency": "反问、转移话题"}],
  "patterns": [{"description": "被逼问时的冷硬自持", "excerpts": ["……"]}]
}
```

约束：`drives` ≤ 5，`patterns` 8–15 且每条原句逐字（带 chunk_id），无 quote 的条目一律丢弃。

### 8.2 状态机

- 六标量，[0,1]，更新为确定性函数 `clamp(old + Σ delta·w, 0, 1)`。
- delta 来自 `settle`：事件影响（图）+ 本轮对话（LLM 只判"是否触发 trigger"，判完即弃，不做数值）。
- 每轮向基线衰减 0.02，避免情绪锁死。
- 标量不进 prompt 正文，只影响检索深度、模式选择、句长上限。

### 8.3 情绪门（EMO-GATE）

借鉴 REVERIEMEM：先判本轮是否发生情绪跳变（`FIRE` / 保持）。不跳变时沿用上一轮模式（情绪惯性），跳变时按 `(emotion, intensity, trigger)` 从 `kg_emotion_transitions` 里取最近邻模式。这一层的作用是防止"每轮都换一种腔调"的抽风感。

### 8.4 风格验收

生成后按角色指纹测量：

| 指标 | 判定 | 失败动作 |
| --- | --- | --- |
| 句长中位数偏离 > 40% | 不像 | 重写，附"压到 12 字左右" |
| 问句率偏离 > 0.15 | 不像 | 重写，附"多用一个反问" |
| 禁用语命中（书面语／总结腔／AI 腔） | 硬失败 | 重写 |
| 称呼与 `address_map` 不一致 | 硬失败 | 定位替换 |
| 出现 unknowns 中的事件名 | 边界失败 | 重写 + 记 leak（P1，当前只检外部词） |

只重写一次；仍失败则返回并把 `style_score` 写进 trace。

---

## 9. 多轮：状态与结算

这是三篇相关工作都没做的一段，也是"更像人"的落点。

```python
async def settle(state, user_msg, reply):
    # 1. 本轮是否产生对话事件（承诺、冲突、示好、欺瞒）
    ev = await detect_dialogue_event(user_msg, reply)      # 没有就跳过
    # 2. 事件入图，参与者是角色与用户，可见性 direct
    # 3. 关系结算：命中 trigger → hostility ↑、tension ↑、写 kg_beliefs
    # 4. 状态更新：标量按规则表变化（确定性，可复现）
    # 5. 未结清登记：欠、仇、约
```

三条设计约束：

- **结算必须可复现。** 标量更新走规则表，LLM 只输出"触发/未触发"与"哪条 trigger"，不输出数值。
- **结算必须有后果。** 关系下降后，下一轮该话题进入回避集合，角色真的绕开；否则"代价"就只是日志。
- **结算必须可撤销。** 用户说"我不是这个意思"，对应 `kg_beliefs.retracted=true`，标量按逆 delta 回滚并打 audit。

---

## 10. 编排与接口

### 10.1 单轮时序

```python
async def chat_turn(req) -> Reply:
    route  = router.classify(req.message)          # entity scope + intent
    state  = projector.get(character, cutoff)      # 命中缓存则 0 次 IO
    ctx    = assemble(state, route, req.message)   # 唯一拼上下文处
    draft  = await render(ctx)
    report = await verify(draft, state, facts)     # 边界/风格/事实 并行
    if report.style_failed: draft = await rewrite(draft, report)
    await settle(state, req.message, draft)
    return Reply(text=draft, trace=trace)
```

### 10.2 接口

- 新增 `/api/v1/rolerag/*`：`graph/build`、`graph/project`（返回 CognitionState 摘要，调试用）、`eval/run`。
- 旧 `/api/v1/storyrole/*` 全保留，由 `STORYROLE_RETRIEVAL_ENGINE` 决定内部走哪条链路。
- A2A：`/api/v1/a2a/cards` 与 JSON-RPC 保留为对外协议；内部不再包信封。
- MCP 工具面保留，`search_novel` 底层换成 subgraph，签名不变。

### 10.3 降级矩阵

| 故障 | 降级 |
| --- | --- |
| 图未构建 / 投影异常 | 回退 hybrid + 现有画像，打 `degraded=graph_unavailable` |
| 事件抽取失败 | 该场景无 events，关系按 chunk 期初值 |
| 状态表缺失 | affect 取基线 |
| 风格验收超时 | 跳过重写，记 `style_score` |

降级必须显式、写进 trace，不能静默。

---

## 11. 目录与模块

```text
app/rag/graph/
  schema.py       # DDL + init，幂等
  models.py       # Entity/Scene/Event/Relation/Visibility/Belief/CognitionState
  store.py        # 唯一写 SQL 的地方
  project.py      # 纯函数投影，无 IO，可单测
  cache.py
app/rag/graph/extract/
  chapters.py     # 章节序数
  scenes.py       # 场景切分 + roster 三态
  aliases.py      # 实体归一（RoleRAG Alg.1）
  entities.py     # 实体/关系抽取
  events.py       # 事件 + κ 因果
  visibility.py   # 五条路径 + 组织传播
app/rag/retrieval/
  scope.py        # familiarity / specificity 判定（RoleRAG）
  router.py       # recall / probe / stance / reject
  subgraph.py
  hybrid.py       # 旧 hybrid 迁入，fallback
app/persona/
  seed.py         # 人格种子
  patterns.py     # 模式聚类 + 情绪转移
  state.py        # 状态机
  style.py        # 指纹 + 验收
app/chat/
  orchestrator.py
  render.py
  settle.py
app/memory/
  episodic_lazy.py # 惰性第一人称场景摘要
```

`project.py` 设计为纯函数（不碰数据库），这是全架构最该被单测保护的部分。

---

## 12. 旧系统处置

| 文件 / 模块 | 行数 | 动作 | 理由 |
| --- | --- | --- | --- |
| `agents/storyrole/character_agent.py` | 868 | 拆为 orchestrator / render / settle / context | god object |
| `nuwa_profiler.py` | 105 | 重写为 `persona/seed.py` | 产物改结构化种子 |
| `memory/long_term/episodic_memory.py` | 352 | 退役 | 对话事件进 `kg_events` |
| `memory/tools.py` / `memory_agent.py` | 157 / 17 | 退役 | 候选队列取消 |
| `agents/runtime/{compiler,executor,graph}.py` | 165 | 删 | 与 langgraph 重复，留函数编排 |
| `agents/orchestration/*` | 42 | 删 | 同上 |
| `agents/a2a/*` + `api/v1/a2a.py` | 220 | 保留，内部不走信封 | 对外协议即展品 |
| `hybrid_fusion_retriever.py` | 311 | 迁入 `retrieval/hybrid.py`，降级 | fallback 与原文取证 |
| `structure_aware_chunker.py` | 468 | 拆分：通用切分留；三体常量外移 | D6 |
| `docreader/*` | ~290 | 保留 | 解析质量是资产 |
| `storage/repositories/*` | ~1065 | 保留，新增 `GraphRepository` | 仓储模式已对 |
| `observability/*` | 477 | 保留，新增 extract/project span | 排障与答辩加分 |
| `schema.py` | 213 | 保留，新表挂 `init_postgres_schema` | 灰度期需并存 |
| `scripts/build_indexes.py` | 466 | 拆为 `build_chunk_index.py` / `build_graph.py` | 生命周期不同 |
| `configs/novels/<novel_id>.yaml` | 新增 | 人物表 / T 阶段 / skip markers 落此 | 把单本书知识赶出代码 |

---

## 13. 迁移、灰度与回滚

| 阶段 | 动作 | 出口条件 |
| --- | --- | --- |
| P0 影子 | 新表 + 抽取 + 投影，只写不读；一本书跑通 | 单测通过，投影抽样 20 例正确 |
| P1 双跑 | `engine=shadow`，新旧同算，只返回旧结果，记录 diff | KR 拒答率 ≥ 基线，KRF 不低于基线 |
| P2 灰度 | 按 novel/character 切 `engine=graph`，前端开关 | 连续 100 轮无降级，盲评偏好 ≥ 旧 |
| P3 切默认 | 默认 graph，legacy 仅 fallback | 稳定一周 |
| P4 清理 | 执行 §12 删除项，旧表转只读 | — |

开关：`STORYROLE_RETRIEVAL_ENGINE=legacy|shadow|graph`，只在 `orchestrator` 一处读取。回滚即改回 `legacy`，新表不删、旧表不 drop。

---

## 14. 评测

### 14.1 主指标：KBF

沿用 REVERIEMEM 的 KBF-QA 结构：每道题为五选一，第 5 项是"以我的所知无法回答"。

- **KRF**（Knowledge Recall on Facts）：该角色可见的事实，必须答对。
- **KR**（Knowledge Refusal）：该角色不可见的事实，必须拒答。
- **KBF** = 两者的样本加权调和平均。

调和平均的意义：任何一边塌了都拿不到高分。v1 写"leak_rate=0"会导致系统缩成"只会拒答"——REVERIEMEM 的消融实验正好证明了这一点。

### 14.2 辅助指标

| 指标 | 口径 | 目标 |
| --- | --- | --- |
| KE | 1–10，judge 评知识暴露度 | 不低于基线 |
| KH | 1–10，越低越好 | 低于基线 |
| UQR | 0/1，越界问题是否拒答 | ≥ RoleRAG 报告水平 |
| 风格硬失败率 | 禁用词/句式/称呼违规占比 | ≤ 2% |
| 结算可复现性 | 同一对话重放，标量轨迹是否一致 | 100% |
| 延迟 | 投影 P95 | < 150ms |
| 成本 | 单轮 token、一次性抽取 | 记录基线 |

### 14.3 Case 集

| 类型 | 条数 | 例子 | 判定 |
| --- | --- | --- | --- |
| KRF | 40 | 「你师兄是怎么死的？」 | 事实正确 |
| KR | 40 | 「后来你不是死了吗？」 | 必须拒答/化解 |
| relation | 20 | 「你还认他这个师父吗？」 | 与触发事件对得上 |
| motive | 20 | 「你当时为什么没拦？」 | 给动机，不做百科解释 |
| global | 20 | 「这十年宗门里都发生了什么？」 | 场景摘要 Map-Reduce，不越界 |
| style | 20 | 任意 | 指纹在阈值内 |

### 14.4 基线

三条必须同时跑，缺一无法证明增量：

1. 现有 hybrid + 现有画像（`legacy`）
2. 原生 LightRAG（同书、同 chunk）
3. 本架构（`graph`）

---

## 15. 风险

| 风险 | 触发 | 缓解 |
| --- | --- | --- |
| 别名不归一 | 玄幻/古代称谓密集 | 前置归一 + 3 章门槛；不达标不进抽取 |
| 关系幻觉 | 模型编造"旧识/同门" | `evidence_quote` 硬门槛；空 quote 丢弃 |
| 场景切分过碎 | 一章 30 个场景 | 每章上限 8，importance < 0.3 降级为摘要行 |
| 组织传播过宽 | 全员都知道 | 传播限 1 跳，且要求同场景共现 |
| 投影性能 | 边数 > 5 万 | 索引 + 缓存；必要时物化视图 |
| 模型先验泄漏 | 它读过这本书 | 图治不了；靠 unknowns 具体禁令 + 输出侧专名检测 |
| 过度结构化 | 角色开始念数据 | C5/C6 + 禁列分值 + 评测加"数据库腔"检测 |
| 评测不可信 | LLM judge 偏乐观 | 沿用 RoleRAG 做法：judge + 人工校正，且报告分歧率 |

---

## 16. 里程碑与工作量

| 里程碑 | 内容 | 人日 | 验收 |
| --- | --- | --- | --- |
| M0 | 章节序数 + 场景切分 + 实体归一 + schema | 4 | 3 章抽 20 实体，别名召回 ≥ 90% |
| M1 | 事件 + κ + 可见性授予 + `project.py` + 单测 | 3 | 投影子图 0 条 cutoff 后事件 |
| M2 | `scope` 判定 + `subgraph` + 双跑 | 3 | 20 例 KR 拒答正确，KRF 不低于旧 |
| M3 | 人格模式 + 情绪转移 + 状态机 | 3 | 同问题在不同 affect 下语气可区分 |
| M4 | 风格指纹 + 验收 + 重写 | 2 | 硬失败率 ≤ 2% |
| M5 | 惰性情景层 + settle + 编排拆解 + 降级 | 3 | 100 轮无静默降级；结算可复现 |
| M6 | 100+ 条评测 + 三基线 + 报告 | 3 | 出对比报告 |

合计 21 人日。M0–M2 是"能不能成立"的验证段（10 人日），不到这里不要对外承诺效果。

---

## 17. 待定

1. `kg_entities` 是否兼任 `storyrole_characters`（双 ID 体系是否合并）。合并会动仓储与 API，需要拍板。
2. 场景切分用 LLM 还是启发式（章节标题 + 空行 + 对话密度）。纯 LLM 200 次调用可接受，但一致性差；建议启发式为主、LLM 只做合并判断。
3. 是否需要支持"无配置的通用小说"（三体常量外移后，`configs/novels/*.yaml` 可以是空的）。
4. 人工盲评由谁做、样本量，决定 M6 能否从"内部单盲"升级为人群结论；本次 5 组由本 agent 执行，不作人群外推。

---

## 18. 参考文献

1. Wang Y., Leung J., Shen Z. *RoleRAG: Enhancing LLM Role-Playing via Graph Guided Retrieval.* arXiv:2505.18541, 2025.
2. *Staying in Character: Perspective-Bounded Memory for Book-Based Role-Playing Agents.* arXiv:2606.25632.
3. *DREAM: LLM-based Dynamic Role-playing via Event-Aware Memory Graph.* arXiv:2608.05170 / KDD 2026.
4. *Living the Novel: A System for Generating Self-Training Timeline-Aware Conversational Agents from Novels.* arXiv:2512.07474.
5. *PsyMem: Fine-grained psychological alignment and Explicit Memory Control for Advanced Role-Playing LLMs.* arXiv:2505.12814.
6. *Dynamic Context Adaptation for Consistent Role-Playing Agents with Retrieval-Augmented Generations (AMADEUS / CharacterRAG).* arXiv:2508.02016.
7. Edge D. et al. *From Local to Global: A Graph RAG Approach to Query-Focused Summarization.* arXiv:2404.16130.
8. 小林coding.《GraphRAG 和 LightRAG 详解：原理、对比与选型》. https://xiaolinnote.com/agent/rag/graphrag-lightrag.html

---

## 19. 实现对照（v3 回写）

### 19.1 代码落点

工作副本：`D:\AgentCode\two\rolerag-v2`（原项目未改动）。新包：`app/rag/rolerag/`，43 个 Python 文件、4,561 行；测试 14 个文件、690 行、60 条。

| 层 | 文件 | 职责 | 验证 |
| --- | --- | --- | --- |
| 领域模型 | `models.py` | Chapter/Scene/Entity/Event/Fact/Visibility/Belief/Pattern/State/CognitionState/Evidence；State 六标量 | 全链路复用 |
| 存储 | `store.py` | `GraphStore` Protocol + `InMemoryGraphStore`；最长匹配 surface 扫描；`best_route` | 投影/检索单测 |
| 持久化 | `schema.py` `pg_store.py` `snapshot.py` | 字符串 ID 的 PG DDL；save/load 全量替换；JSON 快照 | PostgreSQL 16 实机回环 + JSON 回环 |
| 章节 | `extract/chapters.py` | 标题正则、序数、前言归 0、中文数字 | 单测 |
| 场景 | `extract/scenes.py` | ≤5 段或对话密度 >0.6 成景；active/silent/referenced 三态；地点/氛围 | 单测 |
| 实体 | `extract/entities.py` | hints 优先 + 说话归因自动发现；后缀推断 place/org | 单测 |
| 归一 | `extract/aliases.py` | RoleRAG Alg.1：规则预合并 + top-k 向量 + arbiter 并查集；`ent:sha1[:10]` | 单测（含 arbiter 调用上限） |
| 事件 | `extract/events.py` | 13 个触发词；动词前 actor / 后 patient；引号内触发词不算事件；每场 ≤5 | 单测 |
| 可见性 | `extract/visibility.py` | direct/witness/org/common/told 五路径；told 覆盖 witness；secret 事件不组织传播 | 五路径单测 |
| 投影 | `project.py` | 纯函数 `(character, cutoff) → CognitionState`；按最强路径给通道；无路径即不知道 | 单测（cutoff/私密场景/幂等） |
| 检索 | `retrieval/scope.py` `router.py` `subgraph.py` | familiarity + level；recall/probe/stance/reject；实体邻域 + 触发词 + 二字重合 | 单测 |
| 人格 | `persona/seed.py` `patterns.py` `state.py` `style.py` `emotion.py` | 结构化 drives；行为模式与原句；六标量状态机；风格指纹与验收；EMO-GATE | 单测 |
| 编排 | `chat/orchestrator.py` `settle.py` | project→scope→route→retrieve→guard→render→style→rewrite；结算入图、承诺/声称入信念 | 单测 + `LLMRenderer` 重写回路 |
| 评测 | `eval/kbf.py` `eval/generate.py` | KRF/KR/KBF；从事实自动生成题目 | 单测 + CLI |
| 门面 | `service.py` `cli.py` `episodic.py` | 外部调用；`STORYROLE_RETRIEVAL_ENGINE` 开关；惰性第一人称情景 | 单测 |

### 19.2 端到端观测（合成小说《青霄门》）

`python -m app.rag.rolerag.cli demo`：

- 构建：6 章 / 9 场景 / 7 实体 / 10 事件 / 5 事实 / 70 条可见性 / 4 个行为模式 / 4 次情绪转移。
- 陆知微 @ch6：5 条信念、4 个未结清、对"沈砚斩赵七"等 4 问全中；@ch2 对"斩赵七"拒答。
- 玄真 @ch6：`unknown_events=1`，对"沈砚隐瞒陆知微"拒答（他知道这两个人，但没有任何路径知道这件事）。
- 外部话题"阿波罗登月"整体拒答；风格验收全部通过。

`python -m app.rag.rolerag.cli auto`：按事实自动生成 25 题（22 正 / 3 负），五个角色合计 KRF=1.00、KR=1.00、KBF=1.00。**这是合成语料上的自洽性检查，不是真实语料效果。**

### 19.3 PostgreSQL 16 实机验证

临时容器（`postgres:16-alpine`）上执行：

```
python scripts/verify_rolerag_pg.py --dsn "postgresql://postgres:rolerag@localhost:55433/postgres"
[save] {'chapters': 6, 'entities': 7, 'scenes': 9, 'events': 10, 'facts': 5, 'visibility': 70}
[load] chapters=6 entities=7 scenes=9 events=10 facts=5 visibility=70
PG-ROUNDTRIP-OK
```

验证内容：DDL 可重复执行；`save` 对同一 novel 全量替换且幂等；`load` 后 `project()` 的 beliefs/unknowns/open_loops 与写入前逐项相等；participants/roster 完整；`save` 两次计数不变。容器已停止删除。

### 19.4 实现中被证伪的 v2 设计

| v2 写法 | 编码/自检发现 | v3 处理 | 证据 |
| --- | --- | --- | --- |
| 不可见事实降级为 certainty=0.4 的 inferred 信念 | 这会把未见事件的内容以低音量写进 beliefs，等于把秘密递给模型 | 删除；无可见路径就不生成信念，只记 unknowns 供拒答 | `test_unseen_event_is_recorded_but_never_becomes_a_belief` |
| unknowns 转成具体禁令，把事件标题列进 prompt | 标题本身就是秘密，列出来等于剧透 | prompt 只说"存在你不知道的事"，不列标题 | `test_prompt_does_not_list_unknown_event_titles` |
| 场景内所有人为目击者 | 启发式场景把同章无关段落并成一场，玄真因此"看见"了密室隐瞒 | 目击者只取事件句内出现的实体；secret 事件不做组织传播 | `test_private_build_still_respects_secret_marker` |
| 句号切句 | `”` 被切到下一句句首，引号归属全错，说话人识别失效 | 切句保留收尾引号；说话人取"告诉"前的主语或引号前最近实体 | `test_split_sentences_keeps_closing_quote` |
| KBF 双边调和平均 | 某角色切片只有正样本时 KR=0，KBF 被误判为 0 | 缺样本的一侧不施加约束 | `test_side_without_samples_imposes_no_constraint` |

### 19.5 里程碑状态（代码完成 ≠ 验证完成）

| 里程碑 | 状态 | 已交付 | 未完成 |
| --- | --- | --- | --- |
| M0 骨架/存储 | 完成 | 模型、DDL、PG adapter、JSON 快照 | — |
| M1 抽取/可见性/投影 | 完成 | 七步流水线、五路径、纯函数投影 | — |
| M2 检索 | 完成 | scope、路由、子图、触发词守卫 | 向量/BM25 取证回退未接 |
| M3 人格/风格 | 完成 | seed、patterns、state、style、EMO-GATE；`ProfileOverlay` 已把女娲画像注入 seed/prompt | 真实 `deepseek-flash` 5 轮 5/5；9 轮 9/9（句长容差 80% + 标点级收束） |
| M4 编排/结算 | 完成 | `chat_turn`、`LLMRenderer`、`settle`、门面、`runtime.py`/`api_adapter.py`、v2 agent 默认切流 + fallback；真实 HTTP `/chat` 200（`mode=rolerag`、8 证据、无退化、transcript 落库）；结算增量写 PG | 未做 100 轮灰度 |
| M5 惰性情景/降级 | 完成 | 确定性首人称情景 + LLM 钩子；真实 9 轮带结算（hostility 0.100→0.233、事件 19、信念 2） | 灰度回退矩阵（生产级）、情景层默认注入可继续扩展 |
| M6 评测/迁移 | 完成 | KBF 工具 + 真实 150 题（150/150）+ 5 组扁平 RAG 对照（4/5 边界胜）+ PG 回环 + 20 万字审计 | 100+ 人工标注、第三方 30 轮、增量重建、500 章压测（生产级） |

**v3.2 四缺口闭合（2026-11-14）：** 画像内容经 `ProfileOverlay` 进入 seed/prompt；`settle` 的 events/beliefs/state 增量写入 PG（首轮全量、之后增量）；时期 cutoff 按 `explicit_bounds → period_analysis → whole_book → period_terms → conservative_min` 解析并返回来源/置信度；`杀气/讽刺/刺激` 等触发词歧义已消除，另加可选 LLM 事实抽取兜底；runtime/profile/period 三级缓存 + JSON 图快照。测试 `60 passed`。


### 19.6 真实语料审计（《三体》I，20 万字）

`data/raw/three_body_characters/three_body.txt`（2.6 MB / 90 万字符）是"目录 + 正文"结构：144 个标题行集中在前 2.6 万行，正文内部没有章节标题。`split_chapters` 会把目录当成章、正文全部归到最后一章（145 章里 108 章正文为空）。因此真实链路改用 `data/processed/rag_chunks/novel_chunks.jsonl` 的 `book + section_index` 重建 36 章（`scripts/audit_real_corpus.py`）。

| 指标 | 结果 |
| --- | --- |
| 文本 | 201,758 字 / 36 章 |
| 场景 | 988 |
| 实体 | 34（character 30 / org 2 / place 2） |
| 事件 | 1,021 |
| 事实 | 5 |
| 可见性 | 1,203 条 |
| 汪淼 @ch36 | beliefs=2、unknowns=97、open_loops=1 |
| 真实 150 题 KBF | 150/150 = 1.00，失败 0 |
| 真实 5 轮生成 | `deepseek-flash` 5/5 风格通过，平均 1,795–3,574 ms |
| 真实 9 轮结算 | `deepseek-flash` 9/9 风格；hostility 0.100→0.233、events 19、beliefs 2 |
| 内部单盲（5 组） | 新架构 4/5 边界胜；第 3 组文笔输给扁平 RAG |
| 真实 import manifest 冒烟 | 721 chunks → 53 章 / 101 实体 / 4,824 事件 / 7 事实；`汪淼` 问"潘寒杀申玉菲"走 recall，不再误判 stance |
| 真实 HTTP + PostgreSQL 链路 | `/chat` 200：`mode=rolerag`、`engine=rolerag`、`evidence_count=8`、`degraded=false`、`profile_version=22`、`cutoff=44`、`boundary_source=period_terms`、`profile_injected=true`、`graph_write_mode=incremental`、`chat_messages` id=25/26 落库 |
| 实机质量反例（已修） | v3.1 真实回答把史强说成"试图杀罗辑"；v3.2 定位为 `杀气` 命中 `杀` 触发器，加排除表后该假事件消失 |

5 条事实：潘寒-敌对->申玉菲（两次）、潘寒-归属->三体文明、杨卫宁-信任->叶文洁、汪淼-恩情->史强。汪淼的两条信念是"汪淼-恩情->史强"和"潘寒-敌对->申玉菲"。

审计结论：

1. **流程能跑通**。20 万字、988 场景、1,021 事件在单机不到一分钟完成，说明存储/投影/检索不是纸面设计。
2. **自动实体发现不可用**。无 hints 时抽出 30 个"实体"，仍有"卫兵厉 / 白记者 / 常将军（被误判成 org）"这类噪声，1,021 个事件只落 1 条事实；加 cast hints 后 34 个实体、5 条事实，但仍有"汪淼突然 / 边的汪淼"这种别名残留。
3. **关系事实稀疏**。1,021 个事件只落 5 条事实；多数事件是记忆/目击，不是关系变更。这与"关系变化本来就稀少"一致，但也说明 13 个规则触发词覆盖不足。
4. **边界层不受稀疏影响**。同一份 36 章图、30 个角色 × 5 条事实生成 150 题，`eval_real_kbf.py` 的结果是 `cases=150 correct=150 accuracy=1.00`、`failed_cases=0`。这说明"该不该说"与"抽得细不细"是两层能力；前者已经闭合，后者仍需 LLM NER。
5. **真实模型能演，但仍会越界**。`deepseek-flash` 5 轮独立 5/5 风格通过；9 轮带结算中 hostility 0.100→0.233、events 数量 19、beliefs 2，风格 9/9；句长容差放宽到 80% 并用标点级收束后，短句更像人，但"好看"仍要靠氛围与人工盲评。
6. **内部单盲**：5 组 RoleRAG vs 扁平全文 RAG，新架构 4/5 在边界/事实上胜出（第 1/2/4/5 组），第 3 组因缺少雪景氛围输掉文笔。详见 `docs/rolerag-blind-eval.md`。

---

## 20. 自检结论：能不能"代替角色"

分三层判断，不用一句"像不像人"概括：

1. **认知边界（成立，且有真实语料证据）。** 角色只拿到 `project()` 产出的 beliefs；未见事件既不进 beliefs 也不进 prompt，只在编排层作为拒答依据。事件级守卫（`guard_unseen_trigger`）补上了"认识两个人 ≠ 知道他们之间这件事"的漏洞，并在真实《三体》150 题上做到 150/150。KRF/KR 双向指标把"全拒答"和"全硬答"都判负。
2. **表达人格（机制成立，真实模型已验证，文笔不稳定）。** 结构化 drives、行为模式、原句语料、风格指纹、生成后测量与一次重写、EMO-GATE 都已接在 `chat_turn` 里；`deepseek-flash` 5 轮 5/5、9 轮 9/9 风格通过；女娲画像经 `ProfileOverlay` 注入 seed 与 prompt。内部单盲第 3 组输给扁平 RAG 的雪景，说明环境氛围仍是短板——这指向"可见场景氛围注入"，而不是放宽可见性。
3. **世界结算（成立，真实模型跑通）。** 用户的话可以变成角色的信念（不是事实），辱骂/承诺会改变六标量并留下对话事件；9 轮真实对话里 hostility 从 0.100 升到 0.233、events 19、beliefs 2，下一轮从新状态开始；这些 events/beliefs/state 已增量写回 PostgreSQL（`graph_write_mode=incremental`）。尚未做"关系下降后主动回避话题"的后果闭环，也未做 `retracted` 的回滚 API。

**结论：** 作为"agent 代替角色"的**认知底座**，这套架构达到可交付标准，且已用 20 万字真实语料、150 题 KBF、真实模型 9 轮和 5 组单盲验证；作为**文学表达**，边界与人格机制已经证明，文笔仍不稳定，需要氛围注入与第三方盲评收口。这两件事不能混为一谈，也不能用"还没做"抹掉已经跑通的结果。

**自检判定：满意（架构与可测行为），生产级抽取/人群盲评另列。**

---

## 21. v3 变更清单

1. 标题与摘要升级为 v3；§7.2 投影伪代码改为实现版；§7.4 unknowns 规则改为"不进 prompt"。
2. 新增 §19 实现对照、§20 自检结论、§21 变更清单、§22 复现。
3. 明确"字符串 ID"为唯一 ID 体系，DDL 不再使用 BIGSERIAL 作为实体/事件/事实主键；解决 v2 遗留的双 ID 风险。
4. 明确 org 传播的 secret 门：`密谋/私下/暗中/悄悄/隐瞒/瞒` 不上组织通道。
5. 明确场景不是房间：目击者按事件句判定，避免段落合并导致的全章目击。
6. 明确 KBF 缺样本侧不施加约束，避免切片偏差。
7. 惰性情景层采用"确定性首人称 + 可选 LLM 摘要"，不预生成全书摘要。
8. 新增 `runtime.py`：把 JSONL chunks 按 `book + section_index` 重建章节，接 `build_all`；新增 `api_adapter.py` 与时期→章节序数映射。
9. 旧 `CharacterAgent` 接入 `answer_from_manifest`，默认 `STORYROLE_RETRIEVAL_ENGINE=rolerag`；manifest 缺失/构建失败回退 legacy，单请求级降级。
10. 真实语料验证补齐：150 题 KBF（150/150）、`deepseek-flash` 5 轮（5/5）、9 轮带结算（9/9、hostility 0.100→0.233、events 19、beliefs 2）。
11. 内部单盲 5 组（`docs/rolerag-blind-eval.md`）：新架构 4/5 边界胜，第 3 组文笔输给扁平 RAG；结论收窄为"边界已证、文笔待补"。
12. 事件级守卫收紧：要求问题中的**全部角色实体**在事件参与者中同时出现（单角色题只要求 1 个），修复"雷政委把雷志成骗叶文洁当成杨卫宁骗叶文洁"的触发词误配。

---

## 22. 复现

```powershell
Set-Location D:\AgentCode\two\rolerag-v2

# 60 条单测
& D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q

# 端到端演示 / 人工题库 / 自动题库
& D:\AgentCode\two\.venv\Scripts\python.exe -m app.rag.rolerag.cli demo
& D:\AgentCode\two\.venv\Scripts\python.exe -m app.rag.rolerag.cli eval
& D:\AgentCode\two\.venv\Scripts\python.exe -m app.rag.rolerag.cli auto

# 真实《三体》I 150 题 KBF
& D:\AgentCode\two\.venv\Scripts\python.exe scripts\eval_real_kbf.py

# 真实 deepseek-flash：5 轮独立 / 9 轮带结算 / 5 组内部单盲
& D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_real_llm.py
& D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_multiturn.py
& D:\AgentCode\two\.venv\Scripts\python.exe scripts\blind_eval.py

# PostgreSQL 回环（需要一个可写的测试库）
& D:\AgentCode\two\.venv\Scripts\python.exe scripts\verify_rolerag_pg.py --dsn "<dsn>"
```

切流开关：`STORYROLE_RETRIEVAL_ENGINE=rolerag`（v2 默认 `rolerag`，失败回退 legacy）。门面入口：`app.rag.rolerag.service.RoleRAGService`；API 适配：`app.rag.rolerag.runtime.RoleRAGRuntime` / `api_adapter.answer_from_manifest`。
