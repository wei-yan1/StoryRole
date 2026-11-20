# Agent Harness 迁移蓝图（历史审计材料）

> 状态：已被 `docs/agent-harness-v3-architecture.md` 取代，仅保留为迁移过程记录，不作为默认架构口径。v3 已删除旧 `harness_turn.py`，默认路径走新 action loop，deep 已接入同一 `AgentHarness`。
>
> 依据：小林coding《Harness Engineering 是什么？AI Agent 越用越聪明的秘密》
> https://xiaolinnote.com/agent/engineering/harness-engineering.html
>
> 结论先行：agent harness 不是一个 `AgentHarness.run()` 类，也不是把 `HarnessKernel` 扩大一点。它是六层运行环境，加上“每次 Agent 犯错都沉淀成环境修复”的复利过程。当前 `rolerag-v2` 的默认路径已经进入 `AgentHarness` 的 action loop；旧 `HarnessKernel` / `kernel.py` 已删除，不再作为回滚层保留。

## 0. 先修正我之前的偏差

我之前的迁移蓝图主要在做 ownership 审计和“有界动作循环”，这只是一部分。原文真正强调的是：

1. **Harness = Agent − Model**：除了模型本身，决定 Agent 能不能稳定交付的东西都属于 Harness。
2. **Prompt ⊂ Context ⊂ Harness**：提示词和上下文都不是终点，Harness 是包住整个运行系统的约束环境。
3. **六层缺一不可**：上下文、工具、执行编排、记忆与状态、评估与观测、约束与恢复。
4. **Harness 是复利过程**：每次失败都要变成环境里的永久修复（测试、规则、工具、gate、trace），不是只改一次代码。
5. **长任务靠状态外化，不靠上下文记忆**：状态沉到文件/DB，干净上下文接力；不要把所有历史塞进窗口。

所以，当前项目的问题不是“kernel 名字不够大”，而是**六层里只有碎片，没有形成一套会自我加固的运行环境**。

### 0.1 文档自审结论（2026-11-16）

这份蓝图按原文复核后，保留三条硬判断：

1. **`AgentHarness` 不是第二个对话控制器**：它只拥有执行环境和状态，不拥有角色身份；`character_agent.py` 仍是唯一对话出口。
2. **Phase 1 只是行为保持的骨架抽取**，不能拿它宣称“已经是 agent harness”；真正的分水岭是 Phase 4 的 action loop 和 Phase 5 的 trace/预算/恢复闭环。
3. **评估与观测不是收尾工作**：Phase 0 就要有 trace 和 eval 基线，否则后面无法判断架构改动是否改善了角色行为，还是只是换了代码位置。

仍待验证的风险：

- `TurnHandoff` 是否会无意中把“主体状态”变成另一份摘要提示词；验收必须看状态是否可恢复，而不是看字段是否好看。
- `ToolRuntime` 是否会把简单直接调用包装成更慢的间接层；验收必须看延迟、调用数和错误率，而不是看工具数量。
- 有界动作循环是否会让 quick 模式变得不稳定；默认路径切换必须由 live eval 和回滚开关决定。

### 0.2 本轮实施回填（2026-11-16）

这一轮不是“只写蓝图”。代码已经落到以下位置，但仍然按“quick 可运行、deep 未迁移、默认未切换”来验收：

| 层 | 已落地的代码 | 当前事实 | 仍未完成 |
|---|---|---|---|
| 上下文 | `app/harness/context_pipeline.py` | `ContextView` 按 action 暴露段落；`understand_event` 看不到 decision/memory，`review` 看不到 situation/history | 只服务 quick policy；legacy 仍由 `context.py` 全量装配 |
| 工具 | `app/harness/tool_runtime.py` | schema 校验、权限、超时、同步/异步 handler、结果蒸馏、provenance、`call_many` | 只接入 quick 的 RoleRAG/记忆/Web/关系/时间线；legacy 仍直接调用 |
| 编排 | `app/harness/runtime.py` | `AgentHarness` 拥有 action loop、依赖校验、预算、stop reason、trace、状态保存；`HarnessKernel` 已降为 `TurnKernel` 组件 | quick 的 policy 仍是确定性顺序策略；deep 未走 action loop |
| 状态 | `app/harness/handoff.py` + `app/harness/state.py` | `TurnHandoff` 从 `SubjectState` 派生；`Experience` 写回；checkpoint 只存 compact 摘要 | 没有 durable resume / time-travel；legacy 仍在 `character_agent` 里读写状态 |
| 评估 | `app/harness/trace.py` + `scripts/probe_agent_harness.py` + `scripts/harness_gate.py` | 每个 action/context/tool/budget/stop 都有 trace；新增独立 live probe；gate 在 `STORYROLE_AGENT_HARNESS=1` 时要求 probe 通过 | eval set 只有 4 个 quick case；没有跨角色/跨时期/失败 case 集；gate 的 behavior/deep 仍可复用 cached 报告 |
| 约束 | `app/harness/runtime.py` 的 `BudgetLedger` + `types.py` | `max_model_calls / max_retrieve_calls / max_tokens / deadline_ms / max_wall_time_ms` 在 quick harness 中进入硬校验；`max_per_turn` 也已执行；quick 默认 3/5，deep 默认 8/8 | legacy 不执行这些预算；token 只在调用方上报 token 数时精确；没有预算耗尽后的完整恢复协议 |

本轮真实证据：

- `D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q`：`128 passed in 0.98s`。
- `STORYROLE_AGENT_HARNESS=1` + `POSTGRES_DATABASE=three_body_agent_v2` 的 live probe：4/4 通过，全部返回 `agent_runtime=agent_harness`；greeting 走 `understand_event → decide → express → review → learn → stop`，pressure 多一次 `cognition`，fact_boundary 多 `recall_role` 与 `timeline_guard`，两轮 continuity 验证了 `turn_count=2`、两段 episodes、非空 `prior_episode_ids`、`change_from_previous=continue`。greeting 不再为寒暄多付一次模型调用。
- `scripts/harness_gate.py` 在 `STORYROLE_AGENT_HARNESS=1` 下：`passed=true`、`agent_harness_probe_passed=true`、`real_eval=skipped`（behavior/deep 仍是 cached）。
- API 已转发 `agent_runtime`、`harness_trace`（debug）、`harness_budget`（debug）；不再出现“答案正确但动作链读不到”的假阴性。

这仍然不是“完整 harness 已落地”。准确说法是：**quick 的六层骨架已经可运行，deep 和默认路径尚未迁移；legacy 仍作为行为基线保留。**

### 0.3 实施后自审（2026-11-16）

写完后按原文再核对一遍，避免“代码写了但理念没落地”：

1. **Context 不是更长提示词**：`ContextView` 按 action 屏蔽不该看的段落；`review` 看不到 situation/history，`understand_event` 看不到 decision/memory。自审结论：做到了“按需可见”，但还没有 token 级的 progressive disclosure。
2. **Tool 不是装饰**：RoleRAG、记忆、Web、关系、时间线都通过 `ToolRuntime` 执行，有 schema、timeout、蒸馏和 provenance；live probe 的 fact_boundary 触发 2 次 retrieve，没有出现无限重试。
3. **State 不是摘要提示词**：continuity 证据读取的是 `SubjectState` 的 episodes / prior_episode_ids / change_from_previous，不是把上一轮全文塞回 prompt；但 `TurnHandoff` 仍包含短摘要，需要后续用“能否从状态恢复”而不是“字段是否好看”来验收。
4. **Evaluation 不是收尾**：trace 已在 action 级记录；gate 在 flag 开启时要求 live probe；但 behavior/deep 仍是 cached，`real_eval=skipped` 不能冒充 live。
5. **Recovery 不是口号**：预算/依赖/重复动作都有 stop reason；durable resume、time-travel 和预算耗尽后的恢复协议还没做。
6. **Policy 不是自主 Agent**：quick 仍是确定性顺序策略；动作顺序会随 plan 变化，但不会让模型自由选择工具。这是有意的第一版边界，不是已完成的自治。

## 1. 六层 Harness 现状审计

| 层 | 当前已有的东西 | 本轮状态 |
|---|---|---|
| 1. 上下文精细化 | `context.py` 的七段上下文、`SubjectUnderstanding`、身份/主体/回忆/历史/约束分段 | 已新增按 action 的 `ContextPipeline`；quick 已用，legacy 仍全量装配，context reset 只做了“超预算裁剪”，没有完整 reset 协议 |
| 2. 工具系统 | `tools.py` 的能力声明、`distill_*` 结果蒸馏；RoleRAG/记忆/Web/关系/时间线实际可调用 | 已新增可执行 `ToolRuntime` 并接入 quick；legacy 仍直接调用；权限/时期/可见性目前由 handler 内部保证，不是统一策略引擎 |
| 3. 执行编排 | 固定阶段 `route→perceive→interpret→recall→cognition→decide→assemble→express→review→learn`；`graph.py` 的评审自环 | quick 已走 `AgentHarness` 的 action loop；deep 仍走固定阶段；policy 是确定性顺序策略，不是模型自主选动作 |
| 4. 记忆与状态 | `SubjectState`、`Experience`、`storyrole_interaction_states`、`TurnState`、checkpoint 快照 | 已有 `TurnHandoff` 和 compact checkpoint；没有 durable resume/time-travel；legacy 仍在 `character_agent` 里读写状态 |
| 5. 评估与观测 | 116 tests 的 legacy 封版、5 个 quick、1 个 deep、`harness_gate.py`、`harness-state.json` | 已新增 trace、独立 live probe、gate probe 门禁；当前 128 tests；eval set 有 4 个 harness case，behavior/deep 仍可 cached |
| 6. 约束与恢复 | `deadline_ms`、`max_review_attempts`、`max_context_tokens`、评审循环、lazy fallback、stop reason | quick harness 已硬校验 model/retrieve/deadline/wall 与 `max_per_turn`，token 在调用方上报时计入；legacy 不执行；预算耗尽后的恢复路径和 durable checkpoint 仍未闭环 |

结论：**quick 路径已经从“workflow + kernel”推进到“有界 action loop + 六层组件”；但 deep、默认路径切换、完整 eval set 和 durable resume 仍是缺口。**

## 2. 当前 ownership 审计

| 能力 | 当前实际拥有者 | 事实 |
|---|---|---|
| 回合主循环 | `character_agent.reply()` + `AgentHarness`（quick） | quick 在 feature flag 下进入 action loop；deep 仍依次执行 route、perceive、interpret、RoleRAG、用户记忆、Web、关系、时间线、认知、生成、评审、状态写入 |
| 阶段记录 / deadline / stop | `HarnessKernel`（legacy）/ `AgentHarness`（quick） | kernel 只记录阶段、计时、停止原因和状态快照；quick 的 `AgentHarness` 自己拥有 action loop 和预算账本 |
| 工具目录 | `ToolRuntime`（quick）/ `tools.py`（legacy） | quick 的工具已可执行、有 schema/权限/超时/蒸馏；legacy 仍是声明清单和直接调用 |
| 图执行 | `app/harness/graph.py` | 生产路径仍只用于评审自环；完整回合没有走图执行 |
| 上下文装配 | `ContextPipeline`（quick）/ `context.py` + `character_agent`（legacy） | quick 按 action 生成 `ContextView`；legacy 仍全量装配七段上下文 |
| 模型调用 / fallback | `character_agent` 的 `_dispatch_timeout` / `_run_agent` | 模型网关、超时、惰性 fallback 仍嵌在领域代码里；quick 由 policy 调用同一套方法 |
| 评审 / 学习 | `app/harness/review.py` + `character_agent` / quick policy | 评审循环存在；quick 由 `learn` action 写入 Experience |
| 线程状态 | `SubjectState` + `storyrole_interaction_states` | 已持久化；quick 由 `AgentHarness` 保存 compact checkpoint，legacy 仍由 `character_agent` 决定写入时机 |

因此：

- `HarnessKernel` 不是没有价值；它是预算、阶段、停止条件的**约束组件**。
- 把 `HarnessKernel` 叫作 agent harness 仍然是错的；legacy 路径的执行控制仍在 `character_agent`。
- quick 路径已经把执行控制移给 `AgentHarness`；但 deep 仍是固定 workflow，默认路径也仍是 legacy。
- 如果只把固定阶段搬进 `kernel.py`，那只是把 workflow 换个位置，不构成 agent harness。

## 3. 目标：六层 Harness，不是一个大类

```text
character_agent.reply()
        │ 只做：加载角色/时期、构造 TurnScope、调用 Harness、返回 API 结构
        ▼
AgentHarness
        ├─ ContextPipeline          # 这一轮每个 action 该看到什么
        ├─ ToolRuntime              # 能做什么、何时做、结果怎么回灌
        ├─ ExecutionLoop            # action → observation → next action
        ├─ StateStore / TurnHandoff # 跨轮状态外化、干净上下文接力
        ├─ Trace / Eval             # 尺子、足迹、回放、gate
        ├─ Guardrail / Recovery     # 硬约束、校验、失败恢复
        └─ TurnKernel               # budget / deadline / stop / checkpoint
        ▲
        │ 领域策略：理解、回忆需求、行动决定、表达、评审、学习
StoryRolePolicy
```

关键边界：

- **身份契约不由模型选择**：女娲 `PersonaContract` 是只读输入。
- **时期/可见性不由模型选择**：RoleRAG 在进入模型前完成过滤；harness 只执行过滤后的工具。
- **权限/预算不由模型选择**：模型可以提出动作，但不能扩大允许集合。
- **`character_agent.py` 仍是唯一对话出口**：它不再拥有主循环，但仍是外部唯一入口。
- **不引入第二个对话控制器**：harness 是执行底座，不是另一个会说话的 Agent。
- **`HarnessKernel` 降为 `TurnKernel`**：保留预算/阶段/停止/checkpoint 职责，不再自称完整 harness；代码保留 `HarnessKernel` 兼容名，legacy 入口已改用 `TurnKernel`。

## 4. 有界动作协议

Agent harness 不等于开放自治。第一版采用**有界自治**：模型或确定性策略只能在允许动作集合内选择下一步。

```text
AgentAction
  name: understand_event | recall_role | recall_user | recall_web |
        cognition | decide | express | review | learn |
        ask_user | withhold | stop
  args: object
  reason: string | null

Observation
  action: string
  status: ok | denied | timeout | degraded | error
  data: object
  provenance: list[string]
  budget_delta: object
```

`AgentHarness.run()` 的循环：

1. 加载 `TurnHandoff`，构造当前 `AgentView`。
2. `policy.next_action(view)` 产生一个 `AgentAction`。
3. harness 校验：动作是否允许、schema 是否正确、权限/时期/可见性是否满足、预算是否足够。
4. `ContextPipeline.view(action)` 只装配该动作需要的上下文。
5. 执行工具或模型步骤，得到 `Observation`。
6. 更新 `TurnState`、`SubjectState`、trace 和预算。
7. `GuardrailPipeline` 检查；未通过则进入有界修复或停止。
8. 重复，直到 `stop`、`completed`、`deadline_exceeded` 或 `no_progress`。

阶段顺序不再是硬编码的 `with kernel.phase(...)`，而是**动作依赖**：

- `understand_event` 必须先于任何 `recall_*`；
- `recall_*` 的结果必须进入 `decide`；
- `express` 必须消费 `decide`；
- `review` 通过后才能 `learn`；
- deep 才允许 `cognition`，quick 可以走确定性 policy。

## 5. 状态外化与 Context Reset

原文最关键的一条是：**长任务靠文件/外部状态接力，不靠上下文窗口记忆**。角色对话虽然不是一个持续数月的编码任务，但跨轮逻辑相同。

目标不是把全部历史塞进 prompt，而是：

- `SubjectState` 保存当前关注、顾虑、关系姿态、最近行动/情绪；
- `Experience` 保存每轮“如何理解、如何决定、实际怎样表达”；
- `TurnHandoff` 保存下一轮必须知道的接续信息：当前焦点、未解决话题、最近决定、关系变化、时期边界；
- 原始对话、完整检索结果、生成侧推理不跨轮原样携带；
- 每轮从干净上下文开始，按当前 action 装配 `ContextView`；
- 需要长线程时，用 `Episode`/`TurnHandoff` 接力，而不是堆历史。

这一步对应原文的“状态外化 + 干净上下文接力”，也是我们避免 context rot 的关键。

## 6. 评估与观测必须是第一等

原文把评估与观测放在六层里，而且强调：没有 eval set，判断好坏只能靠“我感觉变好了”。当前项目最大的短板就在这里。

需要补齐：

1. **Eval set**：现有 5 quick + 1 deep 只是 smoke/behavior baseline，不是完整 eval set。至少扩到跨角色/跨时期、包含失败案例（越界、晚期身份、关系缺口、无证据、probe、reverse、长线程）。
2. **Trace**：记录每个 action、context 段、工具调用、模型调用、stop reason、预算变化；支持按 turn 回放。
3. **独立评估**：生成侧与评审侧分离已经是正确方向；但 gate 不能默认拿 cached 报告当 live 证据。报告旧于代码时 fail-closed。
4. **失败沉淀**：每次失败必须落到六层中的某一层，并至少补一个回归测试或 eval case；不能只改一句提示词。
5. **规则文件做索引**：`AGENTS.md` 保持目录页，细节放 docs；不要把百科全书塞进系统提示词。

## 7. 工具系统：不是更多工具，而是可控执行

当前 `tools.py` 只有声明和蒸馏，没有执行。要升级为 `ToolRuntime`：

- 每个能力有 schema、权限、时期/可见性、超时、结果上限和 provenance；
- RoleRAG、用户记忆、Web、关系、时间线都通过 ToolRuntime 调用；
- `character_agent` 不再直接调用 `retrieve_from_manifest` / `MemoryTool` / A2A 工具；
- 工具结果先蒸馏再回灌，避免大结果挤占身份和主体状态；
- 工具数量保持小，不为“agent 感”加工具。

## 8. 迁移顺序（按六层，而不是按类）

### Phase 0：Eval + Trace 基线

- 固定 5 quick + 1 deep 的输入、模型、预算、时期。
- 保存阶段顺序、stop reason、关键输出、模型调用数、工具调用数。
- 新增最小 trace：action/context/tool/model/stop/budget。
- 现有 116 passed 只作为回归基线，不作为“角色质量”证明。

**本轮状态：部分完成。**`HarnessTrace` 和 `agent-harness-live-probe.json` 已落地；eval set 有 4 个 harness case 和原有 5 quick / 1 deep，没有跨角色/跨时期失败集。

### Phase 1：Harness 骨架 + ownership 抽取

- 新增 `AgentHarness`，把 `character_agent.reply()` 的编排搬进去。
- 阶段顺序、输出字段、评审、Experience 写入保持等价。
- `HarnessKernel` 降为 `TurnKernel`，只保留预算/阶段/停止/checkpoint。
- 不增加新的自治动作，不增加模型调用。
- 验收：116 passed、5/5 quick、deep 通过、阶段顺序和 stop reason 与基线一致。

**本轮状态：quick 完成，deep 未完成。**`AgentHarness` 已拥有 quick action loop；deep 仍走 legacy；`character_agent.reply()` 仍是唯一出口。

### Phase 2：ContextPipeline + State Handoff

- 把七段上下文改为按 action 生成 `ContextView`。
- 建立 `TurnHandoff`，确保下一轮从外部状态恢复，不靠完整历史。
- 实现上下文预算裁剪和 context reset 协议。
- 验收：长线程下主体状态不丢；历史/回忆可裁剪；身份和决定不被挤掉。

**本轮状态：quick 完成基础版。**`ContextPipeline` 和 `TurnHandoff` 已落地；预算裁剪只裁 history/role/handoff，主体状态和 decision 保留；完整 context reset 和 durable resume 未做。

### Phase 3：ToolRuntime

- 把 RoleRAG、用户记忆、Web、关系、时间线注册为可执行能力。
- 统一 schema、权限、时期/可见性、超时、蒸馏和 provenance。
- 验收：工具调用 trace 可解释；越权/越时期调用被拒绝；同样的输入得到等价材料。

**本轮状态：quick 完成。**`ToolRuntime` 已注册 RoleRAG/记忆/Web/关系/时间线；权限/时期/可见性仍由各 handler 内部保证，没有统一策略引擎；legacy 仍直接调用。

### Phase 4：有界动作循环

- `StoryRolePolicy` 在允许动作集合内选择下一步。
- quick 用确定性 policy，deep 用模型 policy；两者共享 `ActionDecision`。
- 动作依赖由 harness 校验，模型不能跳过 `understand_event` 直接 `expression`。
- 验收：模型选择动作可追踪；不允许动作被拒绝；不增加关键 fallback；延迟和调用数在预算内。

**本轮状态：quick 有界循环完成；deep 未迁移。**`StoryRoleQuickPolicy` 是确定性顺序策略，不是模型自主选择动作；deep 仍用固定阶段。

### Phase 5：约束、恢复与 gate 闭环

- 真正执行 `max_model_calls` / `max_retrieve_calls` / `max_tokens`，或明确改名成观测字段。
- checkpoint 绑定报告时间/代码 revision；cached gate 明确标记 `real_eval=skipped`。
- 报告旧于代码时 gate fail-closed；预算超限有明确 stop reason。
- 每种典型失败有恢复路径：超时、检索空、模型 fallback、评审无进展、状态写入失败。
- 验收：trace 可回放；gate live/cached 分离；失败可恢复。

**本轮状态：quick 预算硬执行完成，恢复仍部分。**`BudgetLedger` 已对 model/retrieve/deadline/wall 和 `max_per_turn` 做硬校验，token 在调用方上报时计入；gate 在 flag 开启时要求 harness probe；但 durable checkpoint / time-travel、cached 报告时效性检查和预算耗尽后的完整恢复协议仍未完成。

## 9. Harness 复利规则

每次 Agent 犯错，必须做三件事，而不是只改代码：

1. **归层**：这是六层里的哪一层？上下文、工具、编排、状态、评估、约束？
2. **沉淀**：补测试、补 eval case、补 gate 规则、补 trace 字段，或改 AGENTS.md 索引。
3. **验证**：下次同类错误在结构上不可能再犯，或者至少能被 gate 拦住。

这条规则比任何单个架构类都重要。没有它，Harness 只是一次性脚手架；有了它，Harness 才会越用越稳。

## 10. 非目标

- 不把多个角色 Agent 放进来自由协商。
- 不让模型决定身份、时期边界、可见性或工具权限。
- 不为了“agent 感”增加无意义的工具调用或思维链。
- 不用一个新的 `AgentHarness` 类名包装现有固定流程。
- 不删除 `character_agent.py` 的唯一对话出口地位。
- 不把 `AGENTS.md` 写成百科全书。

## 11. 最小验收口径

Phase 1 完成时必须同时满足：

- `pytest tests/rolerag -q` 全绿；
- 5 个 quick 行为用例全过；
- deep 探针通过，且 RoleCognition 仍写入同一 `ActionDecision`；
- 阶段顺序、stop reason、主体字段与迁移前一致；
- 模型调用数不高于迁移前，fallback 仍惰性；
- `harness-gate.json` 明确写出 live 或 cached，不能用 cached 冒充 live。

本轮实际口径（2026-11-16）：

- `128 passed`；quick legacy 5/5 仍通过；deep cached 通过；
- `STORYROLE_AGENT_HARNESS=1` 的 live probe 4/4 通过（含两轮 continuity）；
- gate 在 flag 开启时 `passed=true`，但 `real_eval=skipped`，behavior/deep 仍是 cached；
- 因此只能说 **“quick bounded agent harness 已具备”**，不能说“完整 harness 已落地”或“默认路径已切换”。

Phase 4 完成后只能说“有界动作循环已具备”，还不能说完整 harness 已落地；Phase 5 的 trace、预算硬闸门和失败恢复通过后，才可以说：

> **bounded agent harness 已落地；默认路径是否切换，仍要由 live eval 决定。**
