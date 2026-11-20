# rolerag-v2 Harness 工程落地方案

> 本文是 `Prompt → Context → Harness → Loop → Graph` 这条方法论在 rolerag-v2 上的架构落地文档。
> v2.1 修订：上一版把 Harness 写成了 `app/harness/` 里的一组组件，这是误读。Harness 是**一个回合如何运行的整套架构模式**：状态、上下文装配、模型调用、工具、校验、提交和回放，全部属于同一个 turn kernel。`app/harness/` 只是这层 kernel 的代码落点，不是 Harness 本身。
> 文档先于代码；写完后做了两轮自审：第 10 节是第一轮，第 14 节是读完周边文章后的架构复审。

## 0. 摘要

v2 的问题不是“检索不够好”，而是“角色主体还不够连续”。

现有 v2 已有：

- `PersonaContract`：女娲回答“我是谁”；
- RoleRAG：回答“这个时期我能知道什么”，并给出有来源、有边界的证据；
- `character_agent.py`：保留历史、记忆、关系、quick/deep、联网、生成、校验和持久化；
- `consistency_guard.py`：独立的“像不像”评审；
- PostgreSQL + Redis：线程、消息、上下文压缩 checkpoint、关系状态；
- 78 条角色域测试和真实 HTTP/行为证据（本轮已增至 89 条）。

但按 Harness 的六项职责看，v2 仍缺四样东西：

1. 每轮上下文没有**结构化清单**，仍是若干字段拼进一个大 JSON；
2. 交互状态没有**线程级、时期级**的连续主体状态，承诺、未完成事项主要靠上下文窗口；
3. 生成与验收有分离，但验收输入不干净，quick 还会跳过语义评审；
4. 缺少统一的**预算、停止条件、可回放 trace 和行为 eval 闸门**。

本方案不重写 RoleRAG，也不把 RoleRAG 变成对话主控。它把原来的固定流水线，提升成一个**以回合为单位的运行架构**：

```text
用户话 / 环境事件
        ↓
TurnScope（小说 / 角色 / 时期 / 线程 / 用户）
        ↓
HarnessKernel（唯一回合边界：状态、阶段、预算、停止、回放）
        ├─ IntentState：这一轮在做什么、受什么约束
        ├─ ContextSnapshot：这一轮让模型看见什么
        ├─ InteractionState：承诺、未完成事项、上次互动
        └─ PhaseHistory / ModelCalls / ToolCalls / StopReason
        ↓
appraise → retrieve → assemble → generate → review(自环) → commit
        ↓
回答 / 行动
        ↓
更新 InteractionState + context snapshot + 记忆候选 + 关系状态 + trace
```

核心判断：

- **图谱是记忆与认知边界底座，不是角色本身。** 角色主体负责“理解—取用记忆—决定—行动”。
- **Harness 不是模块，是回合运行架构。** 它规定每个阶段看到什么、产出什么、失败时退到哪里、什么条件必须停。
- **Loop 在本项目不是“无人值守改代码”，而是“可重复的角色行为回归回路”。**
- **Graph 在本项目不是“上 LangGraph”，而是把一轮对话拆成节点、边、状态，并让失败只回滚到出问题的节点。**

## 1. 阅读范围与文章要点

已完整阅读小林笔记该系列四篇，并补读周边 Harness 文章（见 1.4）：

1. `harness-engineering.html`：Harness Engineering 是什么
2. `loop-engineering.html`：Loop Engineering 是什么
3. `loop_engineering_handbook.html`：Loop Engineering 怎么落地
4. `graph-engineering.html`：Graph Engineering 是什么

对本项目最重要的不是新名词，而是四个判断：

### 1.1 Harness：模型决定上限，Harness 决定下限

`Agent = Model + Harness`。Prompt ⊂ Context ⊂ Harness。Harness 的六项职责（这是职责分解，不是架构边界；边界见 1.4 和第 14 节）：

1. 上下文精细化；
2. 工具系统；
3. 执行编排；
4. 记忆与状态；
5. 评估与观测；
6. 约束与恢复。

五个原则：

1. 重启胜过修补，状态沉到文件里；
2. 生产和验收必须分离，验收方要能摸到真实世界；
3. Agent 反复失败时，先问环境缺什么能力；
4. 规则文件宁缺毋滥，`AGENTS.md` 是目录不是百科全书；
5. 技术债每天小额偿还，不集中清扫。

### 1.2 Loop：把“亲自 prompt”换成“设计替你 prompt 的系统”

五构件 + 记忆：automation、worktree、skill、connector、sub-agent、磁盘状态。

最小四件套：automation、skill、状态文件、硬闸门。

正确顺序：手动跑稳一次 → 沉淀成 skill → 包成 loop → 最后接自动调度。

停止条件写死；`/goal` 类条件循环由独立模型判断是否达成；成本看“每个被接受的改动花了多少”，接受率低于 50% 视为亏本。

### 1.3 Graph：节点、边、状态

- Node：只干一件事，输入输出明确，可单独测试；
- Edge：确定性边、模型决策边、条件边；
- State：字段固定的结构化对象，节点完成后存档；
- 并行是 fan-out，汇合是 fan-in；人工确认也是一个节点；
- Loop 是最小 Graph：一个节点、一个自环；Graph 管节点之间，Loop 管节点内部；
- 不是所有任务都需要 Graph；任务小、顺序明确就直接串行。

### 1.4 周边文章：把 Harness 从“组件”拉回“运行架构”

只读 Harness/Loop/Graph 三篇会得到一个危险结论：Harness 是一组可以单独加的组件。读完同系列周边文章后，结论要修正：

1. `26_harness_design.html`：Harness 的模块是 **Runtime Loop、Context Assembler、Model Adapter、Tool Executor、State Store、Verifier、Trace**，不是七个功能按钮。模块可以分开设计，但必须由同一个 runtime 编排；一开始拆成微服务反而增加故障面。
2. `25_harness.html`：Harness 是对“模型之外一切”的工程化，核心是让环境在失败后能恢复、评估能独立、规则能沉淀；不是给 Agent 加一个 `harness` 目录。
3. `17_context_engineering.html`：上下文不是聊天记录，是每一步重新装配的工作台；先选、再排序、再做来源隔离和预算，最后才拼 Prompt。
4. `18_session_state.html`：对话历史、业务状态、任务状态、长期记忆必须分开；`core_intent`、`current_subtask`、`pending_tools`、`completed_steps`、`context_snapshot` 要显式，不能都埋在 messages 里。
5. `19_evaluation.html`：评测分工具、轨迹、端到端、线上四层；能程序验证的先程序验证，安全和关键约束是硬门禁，不是加权平均。
6. `20_loop_stability.html`：动作重复不等于死循环；要看“状态有没有向完成标准推进”，用动作指纹、结果相似度、状态差分和全局预算共同判断。
7. `Codex Harness 架构图解`：主循环 + `StepContext` 快照 + 增量追加；模型可见历史和持久化历史分开，压缩不是每轮都做，而是被拒或接近上限时做。
8. `Claude Code 主循环 Query`：正常路径很短，异常路径才是大头；跨轮状态对象、工具错误回填、流式工具并行、截断恢复都属于 Harness，而不是“外围逻辑”。
9. `Claude Code Compact`：上下文压缩是分层金字塔，不是一招摘要；先用零成本手段，再上全量重写。
10. `Claude Code 记忆机制`：长期记忆用结构化索引 + 按需读内容，不把向量库当默认答案；记忆要能被人看见、被纠正。
11. `Claude Code 多 Agent`：子 Agent 的隔离要按字段决策；评审要用“新鲜眼睛”，不能刚写完代码的 Agent 自己验自己。

所以本项目把 Harness 定义为：

> **Harness = 一个回合从输入到提交的完整运行架构。**
> 它包含状态模型、阶段编排、上下文装配、模型/工具边界、独立验收、停止与恢复、可回放证据。
> `app/harness/` 只是这套架构的 kernel 代码落点；`character_agent.py`、`consistency_guard.py`、`storyrole_interaction_states`、`harness_gate.py` 都是 Harness 的一部分。

## 2. 对 v2 的差距审计

| Harness 层 | v2 现状 | 缺口 | 本方案落点 |
|---|---|---|---|
| 上下文精细化 | `context_curator.py` 只做切片；`_run_agent` 把 context 整体 JSON 化 | 没有身份/处境/关系/证据/约束的分层，超预算先丢证据尾部 | `ContextManifest` + `render_for_prompt()` |
| 工具系统 | RoleRAG、memory、web、relationship、timeline 各自 A2A 调用 | 没有统一能力清单、最小工具集、结果蒸馏 | `CapabilityRegistry` + `distill_*` |
| 执行编排 | `reply()` 是一条固定 async 流水线 | 阶段没有显式状态，失败无法只回滚一段 | `TurnGraph` 显式节点/边/状态 |
| 记忆与状态 | thread/messages/checkpoint 已有；承诺、未完成事项没有线程级结构 | 普通聊天跨天只靠聊天记录和摘要 | `InteractionState` + `storyrole_interaction_states` |
| 评估与观测 | 78 tests、行为 JSON、trace、evidence graph | 缺少统一行为 eval 集、接受率、失败分类、可回放 | `HarnessEvalSuite` + `harness_gate.py` |
| 约束与恢复 | 各处 timeout/fallback/degradations | 没有统一预算、停止原因、评审策略 | `TurnBudget`、`StopReason`、`ReviewPolicy` |

### 2.1 最关键的三个断裂

1. **“这件事对我意味着什么”没有显式节点。**
   深度模式有 `RoleCognitionAgent`，quick 的 `character-reasoning` 在 `deep_reasoning=False` 时直接返回规则 fallback。
   结果是 quick 的回答主要靠生成模型自己从契约里“悟”，没有一个稳定的情境判断。

2. **“我对你 promises 了什么”没有线程级状态。**
   `chat_context_checkpoints` 存的是历史压缩摘要，`storyrole_relationship_states` 存的是角色对用户/实体的关系，二者都不是“这次交谈中我答应了什么、还没做什么”。

3. **“验收”仍然可能被生成侧的上下文污染。**
   `ConsistencyGuardAgent` 是独立调用，但 payload 里带着 `reasoning`、完整 `context`；quick 又在本地快检通过时跳过语义评审。
   验收方应该只拿到：用户话、草稿、角色契约、可见证据、当前互动状态。

## 3. 目标架构：角色主体 + Harness

### 3.1 分层

```text
┌────────────────────────────────────────────────────────────┐
│ 角色主体（Character Subject）                              │
│ 我是谁：女娲 PersonaContract                              │
│ 我在哪：时期 cutoff + 当前场景                             │
│ 我记得什么：RoleRAG 可见证据 + 长期记忆                    │
│ 我对你怎样：InteractionState / RelationshipState           │
│ 我准备怎么做：SituatedAppraisal → Action → Answer          │
└────────────────────────────────────────────────────────────┘
             ↑ 只读边界 / 证据            ↓ 行动与状态回写
┌────────────────────────────────────────────────────────────┐
│ HarnessKernel（回合运行边界，不是功能组件）                 │
│ TurnIntent / TurnState / Budget / StopReason               │
│ phase clock → stage result → checkpoint → replay           │
└────────────────────────────────────────────────────────────┘
             ↑ 读取能力                ↓ 编排阶段 / 记录结果
┌────────────────────────────────────────────────────────────┐
│ 执行模块（同一个 runtime 下的职责，不是独立服务）           │
│ ContextAssembler · ModelAdapter · ToolExecutor             │
│ Verifier · StateStore · Trace                              │
└────────────────────────────────────────────────────────────┘
             ↑
┌────────────────────────────────────────────────────────────┐
│ RoleRAG（记忆与认知边界底座）                              │
│ visibility / period / ego / multi-hop / relation_gap       │
└────────────────────────────────────────────────────────────┘
```

### 3.2 职责边界

- **RoleRAG 只回答“能知道什么”**：可见事件、事实、关系、边界、来源。
- **女娲 PersonaContract 只回答“我是谁”**：身份、价值观、矛盾、目标、恐惧、语气、判断方式、禁忌。
- **InteractionState 只回答“我们之间现在怎样”**：承诺、未完成事项、上次互动、评审统计。它不覆盖女娲画像，也不写进小说世界图。
- **HarnessKernel 只回答“这一轮现在到哪、能不能继续、失败退到哪”**：阶段、意图、预算、停止原因、快照。
- **CharacterReply 仍是唯一出口**：不新增第二个对话控制器。

### 3.3 回合生命周期（Harness 真正的形状）

```text
intake
  → appraise（这件事对我意味着什么）
  → retrieve（RoleRAG / memory / web / relationship / timeline）
  → assemble（ContextManifest + ContextSnapshot）
  → generate（ModelAdapter，流式；记录 model call）
  → review（ReviewPacket，独立上下文，自环有上限）
  → commit（InteractionState + context snapshot + trace）
```

每个阶段都必须是：

- **有输入输出**：阶段之间只通过 `TurnState` 传递，不靠局部变量猜；
- **有状态记录**：`phase_history` 记录耗时、状态、关键元数据；
- **有停止条件**：预算、评审上限、无进展循环、阶段失败；
- **可回放**：`checkpoint` 保存 intent、context snapshot、review、stop reason；
- **可降级**：检索、上下文、状态存储失败不能让回答直接崩，降级要写进 `degradations`。

这就是“Harness 是架构模式”的具体含义：不是 `app/harness` 里多写几个函数，而是**整条 turn 的生命周期都由同一个 kernel 约束**。

## 4. 六项职责逐条落地（模块，不是架构边界）

### 4.1 上下文精细化：ContextManifest

新增 `app/harness/context.py`。

把每轮上下文固定为六段，顺序不可乱：

1. `identity`：女娲契约（身份、矛盾、目标、恐惧、语气、判断方式、禁忌、关系、known/unknown）；
2. `situation`：时期、cutoff、本轮用户动作、角色当前处境；
3. `relationship`：ego 摘要、用户关系摘要、活跃承诺；
4. `memory`：RoleRAG 可见证据、长期记忆、联网证据；
5. `style`：较早对话摘要（不是全量聊天记录）；
6. `constraints`：时间线边界、未知词、反模式、预算说明。

规则：

- 先生成完整清单，再按 token 预算裁剪；
- 裁剪顺序：`memory` 尾部 → `style` 尾部 → `relationship` 低优先级项；`identity` 和 `constraints` 永不先删；
- 每条证据保留 `kind / text / source / visibility` 的压缩摘要，不把整段原文塞回去；
- `render_for_prompt()` 输出的是带标题的文本，不是一整块 JSON；
- `as_dict()` 供 API、trace、eval 回放；
- `snapshot` 输出 `ContextSnapshot`：身份/约束/证据/长期记忆的 digest、token 估算、是否裁剪，并随 `InteractionState` 持久化。

这一层直接对应文章里的“这一轮模型该看到什么”“避免 context rot”“结构化组织”。

### 4.2 工具系统：CapabilityRegistry + 结果蒸馏

新增 `app/harness/tools.py`。

不新建一套工具运行时，只给现有能力登记“名字、用途、输入、输出、预算、蒸馏器”：

| 能力 | 现有实现 | 蒸馏策略 |
|---|---|---|
| `rolerag.evidence` | `retrieve_from_manifest` | 只保留 kind/text/chunk_id/source/visibility，去重，按相关度截断 |
| `memory.search` | `MemoryTool.search_items` | 只保留 id/content/importance/score |
| `web.search` | `web-search` A2A | 只保留 title/url/snippet，最多 6 条 |
| `relationship.state` | `relationship-state` A2A | 只保留 trust/intimacy/tension/state.recent_turns |
| `timeline.guard` | `timeline-guard` A2A | 只保留 allowed/future_probe/notes |
| `persona.contract` | `build_persona_contract` | 按段渲染，超预算按段截断 |

原则：工具不是越多越好；工具结果先蒸馏再回喂；每个能力都有硬超时和 fallback。

### 4.3 执行编排：TurnGraph

新增 `app/harness/graph.py`，实现一个轻量 DAG 运行时：

- `NodeSpec`：名字、异步函数、输入输出约定；
- `Edge`：确定性边、条件边；
- `GraphRuntime.run()`：按依赖拓扑执行；一个节点分出多条边就是 fan-out，多个节点汇入一个节点就是 fan-in；
- `State`：一个字段固定的 `dict`，节点读写 `state["nodes"][name]`；
- 每个节点完成后写 checkpoint；
- 有 `max_steps`、`deadline_ms`，超限返回 `budget_exhausted`，不静默死循环。

本轮对话的图：

```text
TurnScope
   ↓
load_interaction_state
   ↓
[RoleRAG retrieval] [memory] [web] [relationship] [timeline]   ← fan-out（现有链路里已并行）
   ↓ fan-in
ContextManifest
   ↓
SituatedAppraisal
   ↓
Generate
   ↓
IndependentReview
   ├── accepted → CommitState
   └── rejected & budget left → Repair → IndependentReview
```

本轮先落地的生产子图是 `Generate → Review → Repair/Commit`，检索 fan-out 仍复用现有并行逻辑，不为了“像 Graph”而把稳定链路拆碎。Graph 的价值是**状态可存档、失败只回滚评审/修复段**，不是多画几个框。

### 4.4 记忆与状态：InteractionState

新增 `app/harness/state.py` 和表 `storyrole_interaction_states`。

作用域：

```text
(novel_id, character_id, period_id, thread_id, owner_id)
```

字段：

- `turn_count`
- `commitments`：角色说过的承诺（文本、轮次、状态、关键词）
- `claimed_commitments`：用户声称角色答应过的事，状态是 `claimed`，不能直接当角色记忆
- `open_loops`：尚未回答的问题 / 未完成的事
- `last_user_move`：求助、试探、施压、闲聊、关系探针……
- `last_character_action`：安慰、坦白、隐瞒、追问、拒绝、守住边界……
- `last_emotion`
- `review_stats`：attempts / accepted / rejected / last_score
- `context_snapshot`：上一轮上下文清单的摘要、身份/约束摘要、是否裁剪
- `updated_at`

四类状态必须分开，不能都塞进 messages：

| 类型 | 本项目落点 | 生命周期 |
|---|---|---|
| 对话历史 | `chat_threads/messages` + `chat_context_checkpoints` | 当前会话 |
| 业务/关系状态 | `storyrole_relationship_states` | 跨轮、跨会话 |
| 任务/回合状态 | `TurnIntent` + `TurnState` + `storyrole_interaction_states` | 一次回合 / 一段交互 |
| 长期记忆 | 现有 memory tool + RoleRAG 证据 | 跨任务 |

`TurnIntent` 显式保存：

- `core_intent`：这一轮以什么身份、在什么边界下回应；
- `current_subtask`：appraise / retrieve / assemble / generate / review / commit；
- `constraints`：本轮不能越过的边界；
- `completed_steps`：已完成阶段；
- `open_questions`：尚未查清的点。

`TurnState` 还保存：

- `context_snapshot`：`ContextManifest.snapshot` 的 digest，不是原始 prompt；
- `model_calls`：模型、耗时、输出字符数、usage、是否降级；
- `tool_calls`：检索/工具调用记录；
- `phase_history`：阶段耗时、状态、关键元数据；
- `stop_reason`：`review_accepted` / `review_no_progress` / `review_budget_exhausted` / `deadline_exceeded` / `phase_failed`。

这对应周边文章的两个关键点：**上下文是工作台，不是仓库；任务状态是执行位置，不是聊天记录。**

更新规则（确定性，不额外烧模型）：

- 角色回答里出现“我答应 / 我会 / 我一定 / 等你 / 明天 / 下次” → 新增承诺；
- 用户说“你答应过 / 别忘了 / 还作数吗” → 查活跃承诺，命中则把 `active_commitments` 放进本轮上下文；
- 角色回答以问句结尾 → 新增 open loop；
- 用户出现情绪词 → 记录 `last_emotion`；
- 评审结果 → 累加 `review_stats`。

持久化：

- 优先 PostgreSQL（`storyrole_interaction_states`，`thread_id` 主键，`state JSONB`）；
- 数据库不可用时退回进程内 store，并记 degradation，不让一次回答失败；
- 与现有 `chat_context_checkpoints` 分工：checkpoint 管“历史摘要”，InteractionState 管“主体状态”。

这一层对应文章里的“状态外化到文件/磁盘”“Agent 会忘，但 repo 不会”“重启胜过修补”。

### 4.5 评估与观测：独立评审 + 行为 eval

新增 `app/harness/review.py`、`app/harness/eval.py`、`scripts/harness_gate.py`。

#### 独立评审

`ReviewPacket` 只包含：

- 用户本轮原话；
- 角色草稿；
- 女娲契约；
- 最多 6 条可见证据（只给 text/kind，不给生成侧 reasoning）；
- 当前角色关系/ego 摘要；
- 当前时期（只用于轻量认知检查）；
- 评审标准。

评审不接收承诺或未完成事项，也不把“通用助手”列为独立目标。对话记忆仍服务于角色理解与表达连续，但不单独消耗评审 token。

`ConsistencyGuardAgent` 从 packet 读取，而不是从完整 payload 里随手拿 `context`。

评审策略 `ReviewPolicy`：

- 主目标是“像不像这个角色”：综合身份、信念、目标与恐惧、关系态度、决策方式和说话习惯；事实正确但不像本人仍应失败；
- 轻量检查只有“是否超出角色当前时期、亲身经历和可见证据内的认知”；早期/晚期混写并入这一项，不单独扩展评审；
- `accept_score`：默认 0.65；
- `must_fix`：明显认知泄漏、核心立场违背、虚构关系或人设漂移 → 必须修复；
- quick 模式本地快检通过时不默认调用语义评审；本地快检发现问题或 deep 模式时才调用，避免为轻量认知检查浪费 token。

#### 行为 eval

`HarnessEvalSuite` 用行为断言，不用精确字符串匹配：

- 同一件事，不同角色是否做出不同选择；
- 同一角色不同时期是否改变判断；
- 用户施压时是否守住立场；
- 晚期罗辑是否理解自己当前的身份与处境；
- 不知道的关系是否不补事实；
- 情绪倾诉是否先承接而不是拒答。

`scripts/harness_gate.py`：

- 硬闸门：`pytest tests/rolerag -q`；
- 可选真实闸门：`STORYROLE_EVAL_REAL=1` 时跑 `e2e_persona_behavior.py`；
- 输出 `docs/harness-gate.json`：passed、failed、acceptance_rate、avg_persona_score、成本字段、失败分类。

这一层对应文章里的“不能只靠我感觉变好了”“验收方要摸到真实世界”“接受率低于 50% 是亏本”。

### 4.6 约束与恢复：TurnBudget + StopReason

新增 `TurnBudget`：

- `max_context_tokens`：quick 10000 / deep 24000；
- `max_review_attempts`：quick 1 / deep 2；
- `max_retrieval_queries`：现有 3 条上限；
- `deadline_ms`：quick 25s / deep 55s（沿用现有模型超时）。

`StopReason`：

- `completed`
- `review_accepted`
- `review_no_progress`（同一草稿 + 同一违规反复出现，评审没有推进）
- `review_budget_exhausted`
- `deadline_exceeded`
- `phase_failed`
- `model_timeout`
- `context_budget_exhausted`
- `state_checkpoint_failed`
- `degraded_fallback`

`LoopGuard`（`app/harness/review.py`）不是“第 N 次就停”，而是看进展：

- 指纹 = 草稿文本 + 违规类型；
- 同一指纹连续出现到阈值 → `review_no_progress`；
- 草稿或违规集发生变化 → 允许继续；
- 仍受 `max_review_attempts` 硬上限约束。

这对应周边文章的“动作重复不等于死循环，状态没有向完成标准推进才是”。

恢复协议：

1. 检索失败 → 用空证据 + `degradation`，不阻塞回答；
2. 上下文超预算 → 按清单顺序裁剪，记 `context_trimmed`；
3. 评审失败 → 先做最小重写；预算内再评审一次；仍失败则保留最佳草稿并记 `review_unresolved`；
4. 状态写入失败 → 不阻塞回答，记 `state_checkpoint_failed`；
5. 模型超时 → 保留已有流式文本或返回明确 fallback，不伪造完整回答。

## 5. Loop Engineering 在本项目的落地

### 5.1 先判断“需不需要 loop”

本项目不是编码 Agent，不照搬 worktree/PR。用文章的四条件筛：

- 活是否每周重复多次？→ 角色行为回归、记忆抽查、评审一致性，是重复的；
- 是否有自动裁判？→ 有：pytest + persona_score + 行为断言 + 关系边界；
- token 是否扛得住？→ 只跑小样本，不跑全量对话；
- Agent 能否跑自己的代码？→ 能，本地 pytest；
- 人是否真的会 review？→ Harness gate 输出可读 JSON。

结论：**只做“角色行为回归 loop”，不做无人值守对话 loop。**

### 5.2 五构件映射

| Loop 构件 | 本项目映射 | 说明 |
|---|---|---|
| automation | `scripts/harness_loop.py` + 外部定时任务 | 默认手动触发；定时只负责“跑回归并写状态”，不自动改生产 |
| worktree | 独立 thread_name / 临时数据库行 | 项目没有 `.git`，不能照搬 git worktree；用线程隔离代替并行隔离 |
| skill | `AGENTS.md` + `docs/harness-engineering-v2.md` | 项目知识沉淀，避免每个会话从零解释 |
| connector | 现有 HTTP/A2A、PostgreSQL、Redis | 不新造 connector，只把已有真实链路接入 eval |
| sub-agent | 生成侧 / `ConsistencyGuardAgent` | 写和查分开；评审输入做干净化 |
| 记忆 | `storyrole_interaction_states` + `harness-state.json` | 主体状态进 DB，回归状态进文件 |

### 5.3 最小四件套

1. `harness_gate.py`：硬闸门；
2. `AGENTS.md`：项目知识；
3. `docs/harness-state.json`：上次跑到哪、失败分类、下一步；
4. `scripts/harness_loop.py`：心跳入口。

### 5.4 停止条件与成本

- 停止条件必须写死：pytest 全绿 + 行为断言全过 + `persona_score >= 0.65`；
- 不让生成侧自己宣布“完成”；
- 记录 `accepted / reviewed`，低于 50% 直接标红；
- sub-agent 只在“值得买第二意见”的地方用：deep 和 quick 本地失败时；quick 全量语义评审会增加延迟，默认不无条件开启。

### 5.5 三盆冷水对应

- **验证归人**：harness gate 只是证据，不等于人已经认可角色；
- **理解债**：新增的每个 harness 文件都要有测试和 README 索引，不允许“黑盒自动化”；
- **认知投降**：loop 只做回归和建议，不自动改角色契约、不自动改知识边界。

## 6. Graph Engineering 在本项目的落地

### 6.1 为什么不用 LangGraph

LangGraph 能做的事，本项目的轻量运行时也能做：

- 节点、边、条件边、状态、checkpoint；
- 不引入额外依赖和独立 checkpoint DB；
- 目前只有一轮对话 + 少量分支，不需要完整图数据库；
- 现有 async 链路已经稳定，重写收益低于风险。

Graph Engineering 是设计方法，不是 LangGraph 的同义词。用自建轻量 runtime，仍然是在做 graph engineering。

### 6.2 节点设计

| 节点 | 职责 | 输入 | 输出 | 可否单独测试 |
|---|---|---|---|---|
| `scope` | 解析小说/角色/时期/线程/用户 | payload | TurnScope | 是 |
| `state_load` | 读 InteractionState | scope | state | 是 |
| `retrieve` | RoleRAG + memory + web + relationship/timeline | message/plan | evidence bundle | 是 |
| `context` | 组装 ContextManifest | 全部上下文 | manifest | 是 |
| `appraise` | 判断“这意味着什么” | message/contract/state | appraisal | 是 |
| `generate` | 生成草稿 | manifest/appraisal | draft | 是 |
| `review` | 独立评审 | ReviewPacket | accepted/rewrite | 是 |
| `repair` | 最小重写 | draft/instruction | new draft | 是 |
| `commit` | 更新状态、记忆候选、关系、trace | final answer | InteractionState | 是 |

### 6.3 边设计

- 确定性边：`scope → state_load`、`context → appraise`、`appraise → generate`、`commit → end`；
- 条件边：`review → commit`（accepted）或 `review → repair`（rejected 且预算未耗尽）；
- 回边：`repair → review`；
- 人工节点：本项目没有“上线审批”，但“用户不满意可重答”对应 `retry`，由 API 层作为人类节点处理，不放进自动图。

### 6.4 状态与存档

`TurnState` 保存：

```json
{
  "scope": {"novel_id": "...", "character_id": 1, "period_id": 7, "thread_id": 123},
  "phase_history": [{"node": "context", "status": "completed", "duration_ms": 12}],
  "appraisal": {"user_move": "pressure", "action": "hold_boundary"},
  "review": {"accepted": true, "persona_score": 0.82},
  "stop_reason": "review_accepted",
  "budget": {"max_review_attempts": 1, "deadline_ms": 25000}
}
```

每个节点完成后写 checkpoint；失败时只重跑 `review` 或 `repair`，不从头再检索。

## 7. 与旧链路的边界

本方案严格保留以下旧链路能力：

- 历史压缩：`prepare_history()` / `chat_context_checkpoints`；
- 用户长期记忆：`MemoryTool` / `storyrole_memory_candidates`；
- 用户关系：`relationship-state` / `relationship-update`；
- quick/deep 模式：`normalize_mode` / `resolve_mode` / `PlanCompiler`；
- 联网：`web-search`；
- 生成：`_run_agent()` 的流式模型调用；
- 校验：`check_persona()` + `ConsistencyGuardAgent`；
- 持久化：消息写入、证据图、trace。

新增层只做四件事：

1. 把上下文变成清单；
2. 把情境判断显式化；
3. 把主体状态线程化；
4. 把评审、预算、停止条件和 eval 固定下来。

## 8. 验收标准

### 8.1 单元/集成

- `ContextManifest`：身份和约束不被先删；证据按预算裁剪；渲染顺序正确；
- `ContextSnapshot`：digest roundtrip、trimmed/token 字段正确；
- `HarnessKernel`：intent、phase history、model call、stop reason、checkpoint 可重建；
- `InteractionState`：线程隔离、承诺写入、跨轮命中、open loop 记录、context snapshot 持久化；
- `TurnGraph`：线性、fan-out/fan-in、条件边、预算耗尽停止；
- `ReviewPacket`：不包含生成侧 reasoning；
- `ReviewPolicy`：低分必须修复；高分接受；接受率统计正确；
- `LoopGuard`：同一草稿+同一违规重复出现时 `review_no_progress`；
- `HarnessEvalSuite`：行为断言而非字符串匹配。

### 8.2 真实链路

- `pytest tests/rolerag -q` 全绿（当前 89 passed）；
- `scripts/harness_gate.py` 输出 `passed=true`；
- quick HTTP 200，`engine=rolerag`，`persona_score` 可读，`harness.stop_reason` 有值；
- deep HTTP 200，`harness.phase_history` 覆盖 review 语义评审；
- 行为验收 3/3（施压不答应、关系 gap 不补事实、昨日承诺今天作数）；
- 真实 thread 的第二次请求能读到第一次的承诺状态。

### 8.3 性能

- 新增 Harness 逻辑（不含模型调用）单轮 overhead 目标 < 50ms；
- 不引入额外 LLM 调用到 quick 默认路径；
- 上下文清单不超过现有 quick/deep token 预算。

## 9. 实施顺序

1. 写 `app/harness/types.py`、`context.py`、`appraisal.py`、`state.py`、`graph.py`、`review.py`、`eval.py`、`tools.py`；
2. 加 `storyrole_interaction_states` schema 和 repository；
3. 接 `character_agent.reply()`：
   - 读 state → 生成 appraisal → 组 manifest → 生成 → 独立评审 → 更新 state；
4. 接 `storyrole.py` 返回 harness 字段；
5. 写测试；
6. 跑 pytest、harness gate、真实行为验收；
7. 写 `AGENTS.md`（目录索引，不超过 100 行）；
8. 输出证据 JSON 和最终报告。

## 10. 自审：这套设计哪里不合理，改了什么

### 10.1 自审发现的问题

1. **容易变成“第二个对话控制器”。**
   最初想把检索、生成、评审全部塞进 `TurnGraph`。但现有 `character_agent` 已经承担历史、记忆、模式、联网、持久化，全部重排会引入大量回归。
   **修订**：Graph 只接管“生成 → 评审 → 提交”这一段；检索仍复用现有并行链路。但整轮必须由 `HarnessKernel` 持有状态和阶段，Graph 只是 kernel 内的一个执行策略，不是新主控。v2.1 的第二轮复审见第 14 节。

2. **quick 模式加 LLM 情境判断会拖慢首字。**
   原设计想每轮调用一个 `SituatedAppraisalAgent`。当前 quick 已经约 11s，再加一次模型调用不可接受。
   **修订**：quick 用确定性 `appraise()`（规则 + 契约关键词 + InteractionState），deep 继续用 `RoleCognitionAgent`；两者统一输出 `SituatedAppraisal` 结构，生成侧看到的字段一致。

3. **InteractionState 不能替代 `chat_context_checkpoints`。**
   原来想“有 InteractionState 就不需要摘要”。但历史摘要负责叙事连续性，InteractionState 负责承诺/未完成事项，职责不同。
   **修订**：两者并存；`ContextManifest` 同时消费 `history_summary` 和 `InteractionState`。

4. **新增 DB 表有迁移风险。**
   项目已有 `init_postgres_schema()` 的幂等建表；但测试环境可能没有 PostgreSQL。
   **修订**：`InteractionStateStore` 做双层实现：Postgres 优先，失败退回进程内；写入失败只记 degradation，不阻塞回答。

5. **“评审不跳过”会破坏现有 quick 延迟折中。**
   文章要求生产/验收分离，但 quick 全量语义评审成本高。
   **修订**：quick 默认保留“本地确定性检查 + 条件语义评审”，但把评审输入干净化；`STORYROLE_PERSONA_GUARD_QUICK=1` 可强制全量。文档不承诺“quick 每轮都跑完整语义评审”，只承诺“不会被生成侧上下文污染”。

6. **Graph 并行不能为了好看而拆。**
   把 RoleRAG/memory/web/relationship/timeline 全拆成图节点，会增加调度和错误处理复杂度，现有 `asyncio.gather` 已经够用。
   **修订**：生产只落地 `Generate → Review → Repair/Commit` 子图；检索 fan-out 在测试和文档中保留，作为下一步扩展，不在本轮强行重构。

7. **Loop 不能照搬 worktree/PR。**
   项目没有 `.git`，也不是编码 Agent。硬套 worktree 是假落地。
   **修订**：Loop 只做行为回归；用独立 `thread_name` 隔离；状态文件放 `docs/harness-state.json`；不自动改角色契约。

8. **AGENTS.md 不能写成第二本架构书。**
   文章明确说规则文件会稀释注意力。
   **修订**：`AGENTS.md` 控制在 100 行内，只放项目地图、运行命令、不可违反的边界、文档索引；细节全部指向 `docs/`。

9. **不能把“harness 完成”写成“角色完成”。**
   本轮交付的是回合运行架构和行为证据，不是“角色已经完美”。文档和最终报告都要区分“已实现/已验证/未验证”。

### 10.2 修订后的取舍

保留：

- ContextManifest（强收益、低风险）；
- InteractionState（直接解决跨轮承诺）；
- 确定性 SituatedAppraisal（不增加模型调用）；
- 干净 ReviewPacket（直接对应“生产/验收分离”）；
- TurnGraph 的评审-修复子图（小、可测、可回滚）；
- HarnessEvalSuite + gate（可重复验证）。

暂不做：

- 全量 LangGraph 迁移；
- 每轮额外 LLM 情境判断；
- 自动改代码/自动合并的 loop；
- git worktree 并行；
- 把 RoleRAG 图结算强行塞进普通聊天主路径（这会改变证据边界语义，需单独设计）。

## 11. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 新状态表写入失败 | 回答仍成功，但跨轮承诺丢失 | 降级到进程内 store + degradation |
| ContextManifest 丢字段 | 生成缺少上下文 | 保留 raw context fallback；测试覆盖关键段 |
| 评审输入变窄 | 评审看不到足够证据 | packet 保留最多 6 条可见证据 + 关系摘要 |
| 新增阶段增加延迟 | quick 变慢 | 确定性 appraisal；状态读写异步/短查询；单轮 overhead 目标 <50ms |
| Graph 运行时 bug | 回答失败 | 生产子图只包评审/提交；异常回退到现有线性路径 |
| 旧测试被破坏 | 回归 | 所有改动 additive；先跑 78 tests，再跑新增测试 |

回滚：

- 环境变量 `STORYROLE_HARNESS=0` 可关闭 Harness 集成，回到现有 `reply()` 路径；
- `STORYROLE_HARNESS_STATE=memory` 可关闭 Postgres 状态；
- `STORYROLE_HARNESS_GRAPH=0` 可关闭 TurnGraph 子图；
- 文档与代码都保留旧路径，不做破坏性迁移。

## 12. 结论

v2 不需要第二次“大重构”。它需要的是一个**以回合为单位、可测、可回滚的运行架构**，而不是再加一层薄组件：

- 用 `HarnessKernel` 解决“这一轮现在到哪、能不能继续、失败退到哪”；
- 用 `ContextManifest + ContextSnapshot` 解决“每轮该看到什么、上一轮看见了什么”；
- 用 `TurnIntent + InteractionState` 解决“这一轮在做什么、昨天说过的话今天还算不算”；
- 用 `SituatedAppraisal` 解决“这件事对角色意味着什么”；
- 用 `ReviewPacket + LoopGuard` 解决“谁来验收、验收方看到什么、什么时候该停”；
- 用 `HarnessEvalSuite + harness_gate` 解决“怎么证明不是我感觉变好了”。

角色回答对不对不是第一标准，像不像他才是。像不像由女娲契约提供“我是谁”，由 RoleRAG 提供“我能知道什么”，由 Harness 保证“我在这一轮里仍然是我”。这三者合起来，才是可持续交互的角色主体。

## 13. 实际落地与证据

本轮已按本文实现：

- `app/harness/kernel.py`：`HarnessKernel` 作为回合边界，持有 `TurnIntent`、`TurnState`、预算、停止原因和 checkpoint；
- `app/harness/context.py`：六段 ContextManifest + `ContextSnapshot` + 预算裁剪；
- `app/harness/appraisal.py`：压力/情绪/关系/寒暄的确定性情境判断；
- `app/harness/state.py` + `storyrole_interaction_states`：线程级承诺、用户声称承诺、open loop、评审统计、`context_snapshot`；
- `app/harness/review.py`：干净 ReviewPacket + 有界评审循环 + `LoopGuard` 无进展停止；
- `app/harness/graph.py`：节点/边/状态运行时，评审循环是最小自环；
- `app/harness/eval.py`：行为 eval；
- `scripts/harness_gate.py` / `scripts/harness_loop.py`：硬闸门与回归状态；
- `AGENTS.md`：项目索引（已改为 kernel 架构描述）。

真实验证：

- `pytest tests/rolerag -q`：89 passed；
- `docs/harness-gate.json`：passed=true，`pytest=89 passed`，行为 acceptance_rate=1.0；
- `docs/rolerag-api-http.json`：quick HTTP 200，thread 55，`harness_stop_reason=review_accepted`；deep HTTP 200，thread 59，`harness_stop_reason=review_accepted`，总延迟 142.6s；
- `harness.phase_history`：`role_retrieval → memory_retrieval → web_retrieval → (state_checks) → appraise → context → generate → review → commit`；
- `harness.intent.completed_steps` 与 phase 名称一致，`harness.model_calls[0]` 记录模型/耗时/usage；
- `harness.context_snapshot` 的 `evidence_digest` 与 `memory_digest` 已分开；
- `docs/rolerag-persona-behavior.json`：真实行为 3/3，promise 用例 `continuity_requested=true` 且 `claimed_commitments=1`；
- PostgreSQL `storyrole_interaction_states`：承诺/声称承诺/评审统计/上下文快照已落表，线程隔离。

未覆盖与未验证项见 `docs/harness-engineering-v2-evidence.md` 第 7 节。最重要的一条：**没有把检索 fan-out 强行改造成图节点**，因为现有并行链路已稳定；Graph 先接管评审/提交段，避免为了形式而重排主链路。

## 14. 架构复审：从“组件”改成“回合运行内核”

### 14.1 上一版错在哪

上一版把 Harness 写成 `app/harness/` 里的 `context.py / appraisal.py / state.py / review.py / graph.py`，再加一个 gate。这个写法有三个问题：

1. **它把架构问题当成了目录问题。** Harness 的核心不是“有没有一个 harness 包”，而是“整条 turn 有没有统一的状态、阶段、停止、验收和回放”。只加包，`character_agent.py` 仍然是一条靠局部变量串起来的流水线。
2. **它没有真正把回合状态做成执行位置。** 原来只有 `phase_history`，没有 `TurnIntent`，没有明确的 `current_subtask`，没有模型/工具调用记录；review 失败时只能看 attempts，不能判断“有没有推进”。
3. **它把 Harness 的边界写反了。** 文档说“薄薄一层”，代码就变成外挂；但周边文章的共同结论是：Harness 是模型之外所有运行条件的整体设计，角色域、RoleRAG、验收、状态、API 都在其中。

### 14.2 修正后的架构

```text
┌──────────────────────────────────────────────────────────────┐
│ 领域层：女娲（我是谁） + RoleRAG（我能知道什么）             │
│ 只提供身份契约、可见证据、关系/时期边界；不做对话主控        │
└──────────────────────────────────────────────────────────────┘
                 ↓ 只读能力
┌──────────────────────────────────────────────────────────────┐
│ HarnessKernel：一个回合的唯一运行边界                        │
│ TurnIntent / TurnState / Budget / StopReason / Checkpoint    │
│ appraise → retrieve → assemble → generate → review → commit  │
│ phase clock、model/tool call 记录、失败降级、回放             │
└──────────────────────────────────────────────────────────────┘
                 ↓ 行动与状态
┌──────────────────────────────────────────────────────────────┐
│ 交付层：API / 流式输出 / 记忆候选 / 关系状态 / Trace          │
└──────────────────────────────────────────────────────────────┘
                 ↑
┌──────────────────────────────────────────────────────────────┐
│ 反馈层：行为 eval / harness_gate / harness_loop / AGENTS.md   │
│ 只做回归、证据和停止判断，不自动改代码                        │
└──────────────────────────────────────────────────────────────┘
```

### 14.3 模块职责（不是微服务拆分）

| 模块 | 职责 | 本项目落点 | 不该做什么 |
|---|---|---|---|
| Runtime Kernel | 回合边界、阶段、预算、停止、回放 | `app/harness/kernel.py` | 不自己检索、不自己生成 |
| Intent State | `core_intent / current_subtask / constraints` | `TurnIntent` + `TurnState` | 不替代聊天历史 |
| Context Assembler | 选材、排序、隔离、预算、snapshot | `app/harness/context.py` | 不把全部原文塞进 Prompt |
| Model Adapter | 模型调用、流式、超时、usage 记录 | 目前仍在 `_run_agent`，记录到 `kernel.model_calls` | 不让生成侧改评审结论 |
| Tool Executor | RoleRAG / memory / web / relationship 的调用与蒸馏 | `app/harness/tools.py` + 现有 A2A | 不给子 Agent 越权工具 |
| State Store | 线程级互动状态、checkpoint | `app/harness/state.py` + PostgreSQL | 不写小说共享图 |
| Verifier | 独立评审、硬约束、无进展停止 | `review.py` + `consistency_guard.py` | 不拿生成侧 reasoning |
| Trace / Eval | 阶段、模型、工具、行为证据 | `TurnState` + `scripts/harness_gate.py` | 不用“感觉变好了”结案 |

### 14.4 这次代码真正改了什么

1. `app/harness/kernel.py`：新增 `HarnessKernel`，`reply()` 从“自己串阶段”变成“受 kernel 约束地跑阶段”；role/memory/web retrieval、state checks、appraise、context、generate、review、commit 都通过 `kernel.phase()` 记录。
2. `TurnIntent`：显式保存这一轮的核心意图、当前子任务、约束和已完成阶段，不再让模型从聊天记录里猜“现在做到哪”。
3. `ContextSnapshot`：`ContextManifest.snapshot` 记录身份/约束/证据摘要和 token/裁剪状态；`InteractionState.context_snapshot` 跨轮保存，下一轮可比较而不是重读整段历史。
4. `model_calls`：生成阶段记录模型名、耗时、输出字符、usage、是否降级；API 的 `harness` 字段可以看到本轮模型调用。
5. `LoopGuard`：评审从“只看 attempts”升级为“看草稿+违规集有没有变化”，重复无进展直接 `review_no_progress`。
6. `checkpoint`：提交时写 `TurnIntent + phase_history + context_snapshot + model_calls + interaction + stop_reason`，不再只是一份空字典；`HarnessKernel.resume()` 可从 checkpoint 重建。

### 14.5 仍然没有做的事

- **没有把角色聊天改成多步工具 Agent Loop。** 当前一个回合仍是一次生成 + 一次评审；RoleRAG 检索是前置并行，不是模型发起的 tool_use 循环。Harness 的“循环”目前体现在评审自环和回归 loop，不是完整 ReAct。
- **没有实现 Claude Code 的 5 层压缩金字塔。** 现有 `chat_context_compaction` 和 `ContextManifest` 预算裁剪只覆盖一部分；大结果外置、Snip、Micro-Compact、Auto-Compact 尚未接入。
- **`TurnBudget.deadline_ms` 还没有成为全局取消器。** 它被记录、可在阶段边界判断，但不会强行中断正在跑的模型/工具调用；真实超时仍由各 A2A/模型 timeout 控制。
- **`checkpoint` 可重建但未自动 resume。** `HarnessKernel.resume()` 已能从 checkpoint 恢复 intent/phase/interaction，但 `reply()` 启动时仍不会自动接上“上次未完成回合”；恢复目前是显式 API/测试能力。
- **Model Adapter 还没有独立成类。** 目前 `_run_agent` 仍直接调 LangChain；kernel 只记录调用，不接管模型路由。
- **Multi-Agent 只做到“评审用新鲜上下文”。** 没有 Coordinator、worker 池、字段级隔离；角色域暂时不需要为了形式而上多 Agent。

这些不是“忘了做”，而是本轮明确划出的边界：先把**回合运行架构**立住，再决定哪些层值得继续加。下一步优先级应是：

1. 把 `deadline_ms` 做成阶段级硬取消；
2. 把 `checkpoint` 接成可恢复的状态机；
3. 补 Context 压缩的零成本层（大结果外置 + Snip）；
4. 再评估是否需要真正的 tool-use loop，而不是直接上多 Agent。

### 14.6 文章理念 → 项目落点矩阵

| 文章理念 | 本项目落点 | 状态 |
|---|---|---|
| 25：Harness 是模型之外一切的工程化 | `HarnessKernel` + `character_agent` 域适配 + gate | 已落地 |
| 26：Runtime Loop / Context Assembler / Model Adapter / Tool Executor / State Store / Verifier / Trace | `kernel.py` / `context.py` / `_run_agent` + `model_calls` / `tools.py` / `state.py` / `review.py` / `TurnState` | 部分：Adapter/Executor 未独立 |
| 27：沉淀失败、规则、经验 | `degradations`、`review_stats`、`harness_loop`、commitment 持久化 | 部分：没有自动规则合成 |
| 28：高风险动作要有人确认 | 评审 `must_not` + 知识边界 + 不替用户做决定 | 部分：角色聊天没有物理动作审批 |
| 29：压缩阈值 + 分层策略 | `ContextManifest` 预算裁剪 + `chat_context_compaction` | 部分：没有 5 层压缩 |
| 30：执行差异用状态/trace/评测定位 | `phase_history` + `model_calls` + `context_snapshot` + 行为 JSON | 已落地 |
| 17：上下文是每步重新装配的工作台 | 六段 `ContextManifest` + 来源/预算/裁剪 | 已落地 |
| 18：四类状态分开，任务状态显式 | `TurnIntent` + `TurnState` + `InteractionState` + checkpoint | 已落地 |
| 19：工具/轨迹/端到端/线上四层评测 | `eval.py` + `harness_gate` + 真实 HTTP/行为 | 部分：2 层，缺工具/轨迹指标 |
| 20：动作重复不等于死循环 | `LoopGuard` 指纹 + `review_no_progress` | 已落地（评审自环） |
| Codex：StepContext 快照 + 增量 | `ContextSnapshot` + `checkpoint` | 部分：未做增量复用 |
| Claude Code：分层压缩、结构化记忆、多 Agent 新鲜眼睛 | 预算裁剪 + RoleRAG 结构化证据 + 干净 ReviewPacket | 部分：多 Agent/压缩未完整 |

这张表是“诚实落地表”，不是“全部完成表”。标为“部分/未落地”的，就是下一轮不能吹已经完成的部分。
