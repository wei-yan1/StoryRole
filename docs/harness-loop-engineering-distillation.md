# Harness Engineering / Loop Engineering 提炼与本项目落地

> 目的：先把两篇长文的核心说清楚，再判断 `rolerag-v2` 哪里只是“套壳”，哪里真正符合 Agent Harness 的规范思想。
>
> 这不是读书笔记的堆砌。每一节末尾都对应到本项目的代码、测试或明确的不采纳理由。

## 一、Harness Engineering 说了什么

### 1.1 一句话定义

```text
Agent = Model + Harness
Harness = Agent - Model
Prompt ⊂ Context ⊂ Harness
```

模型决定“上限”，Harness 决定“下限”。同一个模型，换一套 Harness，效果可以天差地别。Harness 不是某个组件，而是“一个 Agent 如何运行”的整体设计：上下文、工具、循环、状态、评估、约束、恢复。

### 1.2 三阶段是包含，不是替代

文章把大模型应用分成三个阶段：

1. **Prompt Engineering**：研究“怎么问”，解决单轮表达；
2. **Context Engineering**：研究“模型此刻该看到什么”，解决事实、记忆、工具结果和窗口预算；
3. **Harness Engineering**：研究“Agent 如何持续运行”，解决循环、状态、失败、评估和边界。

三者不是“后者淘汰前者”，而是同心圆：Prompt 是 Context 的子集，Context 是 Harness 的子集。只改提示词，永远解决不了长链路跑偏、上下文腐化、工具越权和失败恢复。

### 1.3 六层结构

1. **上下文精细化**：不是把资料全塞进窗口，而是按当前动作做最小必要披露；先摘要/指针，后细节；预算不足时裁历史、裁细节，不裁身份、决定和约束。
2. **工具系统**：工具要有 schema、权限、超时、结果蒸馏、来源（provenance）和幂等；工具是受限能力，不是万能函数。
3. **执行编排**：有界循环、动作依赖、步数/预算/截止时间、明确 stop reason；ReAct 的 Reason→Act→Observation 要落到可检查的 action/observation 上。
4. **记忆与状态**：任务状态、会话状态、长期记忆分层；状态要外化到文件/存储，不能只靠上下文窗口；checkpoint 要能恢复，不能只是一句摘要。
5. **评估与观测**：固定 eval set、完整 trace、独立 evaluator；生产与验收分离；真实证据和缓存证据分离。
6. **约束与恢复**：硬预算、guardrail、失败分类、重试/降级/停止；失败不是例外，限流、上下文溢出、预算耗尽、工具超时都要有路径。

### 1.4 五个难点

1. **长跑偏**：链路越长，目标越容易被中间结果带偏；靠“再提醒模型”不够，要靠状态、检查点和阶段验收。
2. **自评乐观**：生成侧给自己打分天然偏高；评审必须独立，不能共享生成侧的隐藏推理和决定。
3. **失败工程**：大多数系统只写成功路径；真正需要工程化的是超时、限流、空结果、权限失败和恢复。
4. **AGENTS.md 过长**：百科全书式规则会被模型忽略；应该是索引，细节按需加载。
5. **AI code slop**：Agent 会模仿仓库里的坏模式，越写越腐；必须有 lint、测试、评审和“宁缺毋滥”的规则。

### 1.5 七条原则

1. **重启胜过修补**：旧壳层已经扭曲了 ownership，继续打补丁只会把错误固化；该删就删。
2. **状态沉到文件**：上下文窗口不是状态存储；checkpoint、loop memory、eval report 要落盘。
3. **生产与验收分家**：生成侧不能修改评审结论；评审只拿用户话、草稿、契约、关系、可见证据。
4. **与其催模型，不如改环境**：模型不听话时，先改上下文视图、工具边界、动作依赖和 guardrail，而不是再加一段提示词。
5. **规则宁缺毋滥**：动作和工具都要有明确 allow-list；规则越多，模型越容易抓错重点。
6. **技术债天天还**：旧测试、旧文档、旧 feature flag 不清理，就会继续给旧路径背书。
7. **Harness 是复利过程**：每次失败都沉淀成 eval case、guardrail 或恢复策略，系统才会越用越稳。

## 二、Loop Engineering 说了什么

### 2.1 一句话定义

```text
Prompt → Context → Loop
Loop = 触发 + 隔离 + 技能 + 连接器 + 子 Agent + 磁盘记忆 + 停止条件
```

`while` 本身不是 Loop Engineering。一个真正的 loop 需要：谁触发、在哪个隔离环境跑、按需加载哪些技能、能连接哪些外部能力、哪些子 Agent 分工、进度写到哪里、什么时候必须停。

### 2.2 六个坑

1. **为 loop 而 loop**：没有明确产出和验收，只是让 Agent 反复跑。
2. **验证问题**：生成很快，验证很慢；没有独立 evaluator，loop 只会生产更多未验证内容。
3. **认知投降**：把判断权全部交给 Agent，工程师不再定义“什么算对”。
4. **调试地狱**：没有 trace、没有 checkpoint、没有磁盘记忆，失败后无法复现。
5. **工作树混乱**：多个 loop 并发改同一份代码，互相覆盖。
6. **糟糕的代码库**：仓库本身没有测试和规范，Agent 会把坏模式放大。

### 2.3 安全护栏

- **scratch 隔离**：每次 loop 在独立作用域跑，不污染主状态；
- **只读 Token**：默认只读，写入要单独授权；
- **沙盒**：工具在受限环境执行，不直接拿到任意 shell/网络；
- **原子合并**：结果先产出报告，人工审核后再合并，不做无人值守自动合并。

### 2.4 冷思考

- 瓶颈通常不是“生成”，而是“验证”；loop 的价值取决于验证能力。
- 工程师的价值从“写每一步”转为“定义目标、边界、验收和恢复策略”。
- 组织架构比工具更难改：maker/checker 不分离，loop 就会自己给自己盖章。

## 三、逐条落到 `rolerag-v2`

| 文章细节 | 本项目落点 | 状态 |
|---|---|---|
| `Agent = Model + Harness` | `character_agent.reply()` 只做身份解析和入口适配；回合交给 `app/agents/storyrole/harness/turn.py` 的 `AgentHarness` | 已落地 |
| `Prompt ⊂ Context ⊂ Harness` | `ContextPipeline` + `StoryRoleContextBuilder` 按 action 暴露 section；prompt 只是 `express` 的一个输入 | 已落地 |
| 上下文精细化 | 每个 `ActionSpec` 声明 `context_sections`；早段 action 用轻量 view；`express` 才拿完整 decision/回忆 | 已落地 |
| 渐进披露 | `ContextPipeline` 支持 summary/detail、`max_tokens` 裁剪；SkillCatalog 索引与正文分离 | 已落地 |
| 工具 schema/权限/超时/蒸馏/provenance/幂等 | `app/harness/tool_runtime.py`；StoryRole 只注册 5 个只读工具 | 已落地 |
| 有界执行编排 | `AgentHarness.run()` 唯一循环；`ActionRegistry` 一 action 一 handler；`StoryRolePolicy` 只选动作 | 已落地 |
| 动作依赖与 stop reason | `DependencyGuard` / `ActionLimitGuard` / `BudgetGuard` / `TerminalGuard`；`missing_dependency`、`max_per_turn_exceeded`、`no_progress` 等 | 已落地 |
| 状态三层 | `SubjectState` + `storyrole_interaction_states` + RoleRAG/长期记忆；`TurnHandoff` 只带摘要 | 已落地 |
| checkpoint 可恢复 | `TurnCheckpoint` 含 turn/scope/mode/step/completed_actions/action_history/budget/subject_state/artifacts_digest；`resume=True` 跳过已完成 action | 已落地，测试覆盖 |
| 独立评估 | `GenerationService.review` 与生成分离；`review` 不拿生成侧推理；trace 记录 action/context/tool/budget/observation | 已落地 |
| 生产验收分家 | `review.py` 独立评审；probe 与 gate 分开；`real_eval=skipped` 不写成 live | 已落地，gate 已强制 harness probe |
| 失败工程 | `recovery.py` 的 `RecoveryDecision`；timeout/error 有 retry/degrade/replan/stop；失败写 trace | 已落地 |
| 重启胜过修补 | 删除旧 `harness_turn.py`、`character_agent.reply()` 旧编排体和旧 `kernel.py`；旧测试改为 v3 合同 | 已落地 |
| 状态沉到文件 | `TurnCheckpoint` + `LoopMemory` 落盘；`harness-loop-memory.json` | 已落地 |
| 与其催模型不如改环境 | 用 policy/guardrail/context section 约束，而不是继续加提示词 | 已落地 |
| 规则宁缺毋滥 | 20 个 ActionSpec、5 个只读工具、无任意 shell/SQL/HTTP | 已落地 |
| 技术债天天还 | 旧 feature flag 不再决定默认路径；旧测试/旧文档更新；旧 evaluator 的 `phase_history` 判定已替换 | 已落地 |
| Harness 复利 | `docs/agent-harness-eval.jsonl` 固定 10 条（5 行为 + 4 quick + 1 deep），三个探针直接加载；失败可沉淀 | 已落地，覆盖面仍小 |
| Loop 触发器 | API 对话是事件触发；`harness_loop.py` 是回归触发 | 已落地 |
| Loop 隔离 | `TurnScope` 的 thread/state scope；loop 用独立 namespace | 已落地 |
| Loop 技能 | `LoopSpec.skill_paths` + `SkillCatalog` 索引/按需加载 | 已落地，测试覆盖 |
| Loop 连接器 | `ToolRuntime` 的 allow-list，不是任意工具 | 已落地 |
| Loop 子 Agent 分工 | 生成 `express` 与独立 `review` 分离；A2A 的 consistency-guard 仍是外部检查 | 已落地到边界，maker/checker 组织层仍靠人 |
| Loop 磁盘记忆 | `LoopMemory` 持久化 iteration/summary/last_gate | 已落地，测试覆盖 |
| Loop 停止条件 | max_iterations、interval、no_progress_limit、body stop、人工 gate | 已落地，测试覆盖 |
| Loop 反模式 | 不无人值守改代码、不自动合并、不无限重试 | 已落地为约束 |
| 安全护栏 | 只读工具、scope 权限、timeout、scratch namespace、人工 gate | 已落地；沙盒是进程/工具边界，不是完整 VM |
| 冷思考：验证是瓶颈 | gate 以 pytest + 真实 probe + deep probe 为主，不以 persona 分数单独证明 | 已落地为原则 |

## 四、刻意不采纳的部分

1. **不把 Loop 做成自动改代码/自动合并**：文章本身也把“原子合并、人工审核”列为安全护栏；本项目保持“loop 只产报告，人决定是否合并”。
2. **不把 20 个 action 都交给模型自由选择**：第一版是确定性 policy（quick/deep 分支），这是有界自治的中间态；`PolicyView` 和 `ActionRegistry` 已分离，后续可以换模型策略而不动领域代码。
3. **不把完整历史塞进上下文**：跨轮只带 `SubjectState` 摘要、最近经历、约定和关系姿态；原始对话/完整检索结果不跨轮。
4. **不把 persona 分数当唯一验收**：角色“像不像”优先，但必须有真实证据、独立评审和 gate；不用 HTTP 200 或本地分数替代。

## 五、本轮证据

- `pytest tests/rolerag -q`：**132 passed**。
- 固定 eval set：`docs/agent-harness-eval.jsonl` 共 10 条（5 行为 + 4 quick + 1 deep），`e2e_persona_behavior.py`、`probe_agent_harness.py`、`probe_subject_deep.py` 直接从该文件加载；gate 校验 suite 数量和唯一 id。
- quick 真实 probe：**4/4 passed**，默认路径 `agent_runtime=agent_harness`，动作链含 `plan_turn → understand_event → [recall_role/recall_user_memory/timeline_guard] → cognition → decide → assemble_context → express → review → learn → stop`，两轮 case 的 `turn_count=2`、`episode_count=2`、`prior_episode_ids` 非空、`change_from_previous=continue`。
- deep 真实 probe：**1/1 passed**，`action_order=true`、`role_cognition_real=true`、`role_cognition_absorbed=true`、`experience_recorded=true`、`review_accepted=true`、`persona_score=0.90`，延迟 63.7s。
- 5 个真实 quick 行为用例：**5/5 passed**，`acceptance_rate=1.0`，平均 persona 1.0，平均延迟 4851.5ms；结构判定已从旧 `phase_history` 改为 `harness_trace.summary.actions`，验证 `plan_turn → understand_event → [可选召回] → decide → assemble_context → express → review → learn` 的顺序。
- `scripts/harness_gate.py`（`STORYROLE_EVAL_REAL=1`）：**`passed=true`、`real_eval=passed`**，pytest / eval set / 5 行为 / deep / quick 五项全过。证据文件为 `docs/harness-gate.json`、`docs/rolerag-persona-behavior.json`、`docs/role-subject-deep-probe.json`、`docs/agent-harness-live-probe.json`。
- `scripts/harness_loop.py --runs 1`：通过 `LoopRuntime` 跑 gate，写 `docs/harness-state.json`、`docs/harness-loop-memory.json` 和独立的 `docs/harness-loop-gate.json`；不会覆盖 `docs/harness-gate.json` 的 live 报告。

### 5.1 live gate 曾经失败的真实原因

第一轮 live gate 失败不是角色回答差：5 个行为用例的 `persona_score` 都是 1.0，但旧 `e2e_persona_behavior.py` 仍从 `harness.phase_history` 读 `perceive/interpret/decide/assemble/express/learn`。v3 harness 不再产出 `phase_history`，只产出 `checkpoint.action_history` 和 `harness_trace.summary.actions`，所以 `phases=[]`、`phase_order=false`、`structure.passed=false`、`acceptance_rate=0.0`。

修复方式不是给 response 补一个假的 `phase_history` 兼容字段，而是让评估器按 v3 的真实动作顺序判定。这是“生产与验收分家”的落地：验收读 harness 的可检查 trace，不读模型自述或旧壳层字段。


## 六、仍未完成

- `docs/agent-harness-eval.jsonl` 已建立，但只有 10 条，覆盖罗辑 T6 的少量场景；跨角色、跨时期、长失败路径还需要继续沉淀。
- deep 第一版仍是确定性顺序策略，不是模型自主选动作；这是有意保留的中间态。
- checkpoint 第一版保存可恢复摘要和 action 历史，不做完整 time-travel 事件日志。
- 沙盒边界目前是工具 allow-list + scope + timeout，不是独立 VM；如果要跑不可信代码，需要再上一层隔离。
- `real_eval=skipped` 时 gate 通过只代表“缓存证据 + 当前代码测试”通过，不代表刚刚跑过真实 HTTP；报告必须保留这个区别。
