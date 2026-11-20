# Agent Harness v3 架构

> 状态：已实施并切换默认路径。旧 `harness_turn.py`、`character_agent.reply()` 的旧编排体和旧 `kernel.py` 已删除；当前只有 `AgentHarness` 一条回合编排路径。
>
> 本文不是组件清单，而是“一个角色回合如何运行”的 ownership 约定。两篇长文的逐条提炼和落地审计见 `docs/harness-loop-engineering-distillation.md`。

## 0. 这次为什么重建

### 0.1 旧实现的问题

旧 `app/agents/storyrole/harness_turn.py` 有 633 行，名字叫 action loop，实质仍是旧 workflow：

1. `StoryRoleQuickPolicy` 同时持有身份、计划、检索结果、上下文、草稿、评审结果和领域方法；
2. policy 直接调用 `interpret_event`、`recall_plan`、`choose_action`、`_run_agent`、`run_review_loop`；
3. 同一轮里至少构造三次上下文：`context_result`、`build_context_manifest`、`generation_context`；
4. `AgentHarness` 只负责“允许执行哪些 action”，但 action 做什么、什么时候做、做到什么程度，仍由 policy 和旧流程决定；
5. deep 没有进入 harness，默认路径仍是 legacy；
6. checkpoint 只是 compact 摘要，不能从“做到第 3 个 action”的位置恢复；
7. 自评和生成共享同一个回合对象，独立评估只是字段上的分离，不是执行上的分离；
8. `harness_turn.py` 的失败回落到 legacy，导致新路径永远可以用旧路径兜底，真实能力没有被验收。

结论：旧实现是 **Harness facade**，不是 Agent Harness。它的类名和字段可以保留一部分，但编排壳层必须丢弃。

### 0.2 保留什么

只保留领域能力，不保留领域编排：

- 女娲 `PersonaContract` 的身份边界；
- RoleRAG 的可见证据、时期 cutoff、越界拒绝；
- `SubjectState` / `Experience` / `current_reality`；
- 现有的模型调用、检索、评审、持久化函数；
- API 契约和真实数据。

丢弃的是“谁先调用谁、失败后调用谁、上下文怎么拼、状态怎么传”的旧 workflow 壳层。

### 0.3 两篇文章的核心

**《Harness Engineering》**：`Agent = Model + Harness`，`Harness = Agent - Model`，`Prompt ⊂ Context ⊂ Harness`。三阶段是包含不是替代；六层是上下文、工具、编排、状态、评估、约束恢复；五个难点是长跑偏、自评乐观、失败工程、AGENTS.md 过长、AI code slop；七条原则是重启胜过修补、状态沉到文件、生产验收分家、与其催模型不如改环境、规则宁缺毋滥、技术债天天还、Harness 是复利过程。

**《Loop Engineering》**：`Prompt → Context → Loop`；Loop = 触发 + 隔离 + 技能 + 连接器 + 子 Agent + 磁盘记忆 + 停止条件；`while` 本身不是 Loop Engineering；六个坑是为 loop 而 loop、验证问题、认知投降、调试地狱、工作树混乱、糟糕的代码库；安全护栏是 scratch 隔离、只读 Token、沙盒、原子合并；冷思考是瓶颈在验证而不是生成，工程师价值转为判断力，组织架构比工具更难改。

本项目的落地不是“把文章名词写成类名”，而是把上述职责落到可执行、可测试、可恢复的运行时。逐条映射见 `docs/harness-loop-engineering-distillation.md`。

## 1. 总原则

```text
Agent = Model + Harness
Harness = Agent - Model
Prompt subset Context subset Harness
```

本项目里：

- **Model** 只负责理解、生成、轻量判断；
- **Harness** 拥有回合循环、动作注册、动作依赖、上下文视图、工具执行、状态接力、预算、截止时间、评估、约束、恢复和 trace；
- **Domain Service** 只提供“能力”，不决定“下一步”；
- **Policy** 只根据当前观察提出“下一步动作”，不能直接执行动作，也不能直接拼上下文；
- **Action Handler** 只执行一个动作，返回 `Observation`，不拥有循环；
- **CharacterAgent** 只做入口适配和领域身份解析，不拥有回合编排。

## 2. 六层落地

| 层 | 本项目职责 | 代码落点 | 不允许 |
|---|---|---|---|
| 1 上下文精细化 | 按 action 暴露最小必要上下文；渐进披露；预算不足时先裁历史/角色细节/记忆尾部 | `app/harness/context_pipeline.py`、`app/agents/storyrole/harness/context.py` | 每个 action 重新拼一份大 context；把完整历史塞进窗口 |
| 2 工具系统 | 工具 schema、权限、超时、结果蒸馏、provenance、幂等键 | `app/harness/tool_runtime.py` | 工具直接改对话状态；工具越权访问 owner/novel |
| 3 执行编排 | 有界 action loop、依赖、max steps、stop reason、ReAct/Plan-Execute 混合 | `app/harness/runtime.py`、`app/harness/actions.py`、`app/harness/policy.py` | policy 自己调用领域函数；action 自己决定下一个 action |
| 4 记忆与状态 | 任务状态、会话状态、长期记忆分层；checkpoint 可恢复；原始对话/完整检索结果不跨轮 | `app/harness/state.py`、`app/harness/checkpoint.py`、`app/harness/handoff.py` | 把完整历史当记忆；checkpoint 只有一句摘要 |
| 5 评估与观测 | 固定 eval set、trace、独立 evaluator、真实/缓存证据分离 | `app/harness/eval.py`、`app/harness/trace.py`、`scripts/probe_agent_harness.py` | 生成侧给自己打分；用 HTTP 200 代替行为验收 |
| 6 约束与恢复 | 硬预算、deadline、guardrail、失败分类、重试/降级/停止、断点恢复 | `app/harness/guardrails.py`、`app/harness/recovery.py`、`app/harness/budget.py` | 静默循环；失败后无标记地回落；用无限重试掩盖问题 |

### 2.1 上下文层

每个 action 必须声明 `context_sections`。运行时只把声明允许的 section 交给 action：

| action | 允许 section | 禁止 section |
|---|---|---|
| `plan_turn` | identity、situation、constraints | decision、memory、history |
| `understand_event` | identity、self_state、situation、history、constraints | decision、memory |
| `recall_role` / `recall_memory` / `recall_web` | identity、self_state、situation、constraints | decision、draft |
| `relation_state` / `timeline_guard` | identity、situation、constraints | memory、draft |
| `cognition` / `decide` | identity、self_state、situation、memory、constraints | draft、review |
| `assemble_context` | identity、self_state、situation、memory、decision、history、constraints | draft、review |
| `express` | identity、self_state、situation、memory、decision、history、constraints | review、trace |
| `review` | identity、decision、memory、constraints | situation、history、生成侧隐藏推理 |
| `learn` | identity、self_state、decision、constraints | 完整历史、原始检索大块 |

上下文不足时只做两件事：

1. 先裁 `history`、`role_detail`、`memory_tail`；
2. 永不裁 `identity`、`self_state`、`decision`、`constraints`。

渐进披露：早段 action 只给摘要和指针；`express` 才拿完整契约、完整 decision、实际回忆；`review` 拿草稿和可核对证据，不拿生成侧推理。

### 2.2 工具层

工具统一走 `ToolRuntime`：

- schema 校验参数；
- `scope` 校验 owner/novel/character/period；
- 同步/异步 handler；
- timeout；
- 结果蒸馏（只回传必要字段）；
- provenance（来源、时期、可见性）；
- `idempotency_key`，避免重试造成重复写入；
- 工具错误分类为 `timeout / permission / not_found / invalid_args / backend_error`。

角色对话的工具不是“万能函数”，是有限能力：`recall_role`、`recall_memory`、`recall_web`、`relation_state`、`timeline_guard`、`persist_*`。

### 2.3 编排层

`AgentHarness.run()` 是唯一循环拥有者：

```text
load state / checkpoint
while steps < max_steps:
  action = policy.next_action(view)
  guardrail.check(action)
  context = context_pipeline.build(action, execution)
  observation = action_registry.execute(action, context, execution)
  budget.charge(observation)
  trace.record(action, context, observation)
  state.apply(observation)
  checkpoint.save()
  if action.terminal: break
finalize / evaluate / persist
```

`max_steps`、`max_per_turn`、`max_model_calls`、`max_retrieve_calls`、token、deadline、wall time 都是硬约束；超限必须写明确 `stop_reason`，不能静默继续。

动作依赖：

- `understand_event` 依赖 `plan_turn`
- `cognition` 依赖 `understand_event` + 必需要的 recall
- `decide` 依赖 `cognition`
- `express` 依赖 `decide` + `assemble_context`
- `review` 依赖 `express`
- `learn` 依赖 `review`
- `stop` 依赖 `learn`

依赖不满足时，guardrail 返回 `missing_dependency`，由 policy 重新规划，而不是执行一个空 action。

### 2.4 状态层

三层记忆：

1. **任务状态**：本轮 `TurnExecution`，只在运行时内存，结束后压缩成 checkpoint；
2. **会话状态**：`SubjectState` / `InteractionState`，按 thread scope 持久化，含当前关注、顾虑、关系姿态、最近行动/情绪/决定、最近 3 条经历；
3. **长期记忆**：用户记忆候选、RoleRAG 证据、关系图，按领域规则持久化，不塞进上下文窗口。

跨轮只带：

- `SubjectState` 摘要；
- 最近 3 条 `Experience`；
- 未完成约定/边界；
- 当前关系姿态。

不带：

- 原始对话全文；
- 完整检索结果；
- 生成侧隐藏推理；
- 评审内部 trace。

checkpoint 必须包含：

- `turn_id`、`scope_key`、`mode`；
- `status`、`step`、`completed_actions`、`action_history`；
- `budget_snapshot`；
- `subject_state`；
- `artifacts_digest`（不保存完整大对象，只保存可恢复的 ID/摘要）；
- `updated_at`、`version`。

能从 checkpoint 恢复时，已完成 action 不重复执行；如果恢复后依赖已失效，必须重新从最近的稳定点开始。

### 2.5 评估层

- 固定 eval set：`docs/agent-harness-eval.jsonl`，当前固定 5 个行为用例、4 个 quick probe、1 个 deep probe。每条包含 `id/suite/name/message`，按需带 `setup`、`checks`、`expected_action`、`forbidden`、`require_current_reality`、`expect_no_role_recall`、`require_continuity`、`expected_tokens`。三个探针脚本直接从该文件加载用例，gate 校验 suite 数量和唯一 id，避免脚本常量与报告各写一份。
- trace：每个 action 记录输入 section、输出 observation、预算、耗时、错误。
- 独立 evaluator：只看用户话、草稿、契约、关系、可见证据；不看生成侧 reasoning、decision 内部字段。
- 真实/缓存分离：`real_eval=skipped` 不能写成“live passed”；cached behavior/deep 不能给新代码背书。`scripts/harness_loop.py` 写独立的 `docs/harness-loop-gate.json`，不得覆盖 `docs/harness-gate.json` 的 live 报告。
- 回归门禁：`pytest`、`probe_agent_harness.py`、`harness_gate.py` 三者分开，gate 必须显示证据来源。

### 2.6 约束与恢复层

失败分类：

| 类型 | 处理 |
|---|---|
| `timeout` | 记录 deadline，降级为本地 fallback；不重试大模型 |
| `invalid_args` | 不重试，返回结构化错误，policy 换 action |
| `permission` | 不重试，标记 boundary，停止越权调用 |
| `backend_error` | 可重试一次（幂等工具），否则降级 |
| `budget_exceeded` | 立即停止，写 stop_reason |
| `review_no_progress` | 停止重写，保留最佳草稿并标记未解决 |

恢复不是“fallback=await model()”这种重复执行；恢复必须显式记录 `RecoveryDecision`，并在 trace 中可见。

## 3. Loop Engineering 的落地

Loop Engineering 不是把 `while` 写成 `while`。本项目落地为：

1. **触发器**：手动、定时、事件；角色对话本身是事件触发，`harness_loop.py` 是定时回归。
2. **隔离**：每次 loop 用独立 `thread_name`/`state scope`，不共享全局 subject state；v2 没有 git worktree，等价隔离是状态命名空间。
3. **技能**：渐进披露的 Skill catalog，不在主上下文塞完整 Skill 文档。
4. **连接器**：ToolRuntime 的受限能力，不是任意 shell/网络。
5. **子 Agent 分工**：maker / checker 分离；评审不能被生成侧覆盖。
6. **磁盘记忆**：`progress.json` / checkpoint / eval report，不靠上下文窗口记忆。
7. **停止条件**：max iterations、预算、连续无进展、人工 gate。
8. **反模式**：为 loop 而 loop；无验收的自动改代码；无限重试；把 AI slop 合并进仓库。

`scripts/harness_loop.py` 必须通过 `app/harness/loop.py` 的 `LoopRuntime` 运行，写磁盘 state，接受 max runs/interval/stop condition，不直接 `subprocess.run` 裸跑。

## 4. StoryRole 目标结构

```text
app/agents/storyrole/
  character_agent.py          # 唯一入口：解析身份、构造 TurnRequest、调用 harness、格式化响应
  harness/
    __init__.py
    turn.py                   # StoryRoleHarness 装配，不再包含领域逻辑
    context.py                # 按 action 生成 StoryRole ContextView
    services.py               # Planning/Recall/Cognition/Generation/Persistence 能力
    actions.py                # 每个 action 的 handler + ActionSpec
    policy.py                 # QuickPolicy / DeepPolicy，只选动作
    response.py               # 统一响应字段
    appraisal.py              # StoryRole 的理解/决定/连续性逻辑
    context_manifest.py       # StoryRole 的 section/manifest 数据结构
    review.py                 # 角色评审 packet 与有界修复
    update.py                 # 把实际经历写回 SubjectState
    handoff.py                # 跨轮 compact handoff
```

`app/harness/`：

```text
actions.py        # AgentAction / Observation / ActionSpec / ActionRegistry
policy.py         # HarnessPolicy / PolicyView
runtime.py        # AgentHarness 唯一循环
budget.py         # BudgetLedger
guardrails.py     # 依赖、预算、动作上限、终止、评审守卫
recovery.py       # 失败分类与恢复决策
checkpoint.py     # TurnCheckpoint codec
context_pipeline.py
tool_runtime.py
trace.py
loop.py           # LoopRuntime / LoopMemory / LoopSpec
state.py          # 状态存储接口与实现
eval.py           # 固定 eval set 加载与行为评分
graph.py          # 有界节点图执行器（只服务评测修复，不是回合控制器）
tools.py          # 能力目录与结果蒸馏
types.py          # SubjectState / TurnScope / TurnBudget 等共享数据结构
```

## 5. 迁移顺序

1. 先建核心与测试，不动 `character_agent` 主链；
2. 建 StoryRole services/actions/policy，quick 先接；
3. quick 真实探针通过后，接 deep；
4. deep 通过后，默认路径切到 harness；
5. 旧 `harness_turn.py` 删除；旧 `kernel.py` 删除，不再保留第二套阶段编排；
6. 更新 AGENTS.md、迁移文档、证据报告。

## 6. 验收口径

必须同时满足：

- `pytest tests/rolerag -q` 全绿；
- `tests/rolerag/test_agent_harness.py` 覆盖：
  - 依赖不满足不执行；
  - action 上限；
  - context section 屏蔽；
  - 工具权限/超时/幂等；
  - guardrail、recovery、checkpoint resume；
  - quick/deep policy 动作序列；
- `tests/rolerag/test_harness_loop_runtime.py` 覆盖 Loop memory/stop condition/skill catalog；
- 默认路径真实 quick probe 4/4，`docs/agent-harness-live-probe.json` 必须 `passed=true`；
- deep probe 至少 1 个真实 case，证明 `cognition` 进入同一 `ActionDecision`；
- `docs/harness-gate.json` 显示 `real_eval` 的真实状态，不得用 cached 冒充 live；gate 不再用旧 `STORYROLE_AGENT_HARNESS` 开关决定是否检查 harness probe。

### 6.1 本轮 live 验收结果

`STORYROLE_EVAL_REAL=1 scripts/harness_gate.py` 已真实重跑：

```json
{"passed": true, "pytest": "132 passed in 1.11s", "eval_set_passed": true, "eval_set_counts": {"behavior": 5, "quick_probe": 4, "deep_probe": 1}, "behavior_passed": true, "deep_subject_passed": true, "agent_harness_probe_passed": true, "acceptance_rate": 1.0, "real_eval": "passed"}
```

5 个行为用例全部 `review_accepted`、`persona_score=1.0`；quick 4/4、deep 1/1 通过。行为评估器原先读旧 `harness.phase_history`，在 v3 下必然得到 `phases=[]`；本轮已改为读 `harness_trace.summary.actions`，按 `plan_turn → understand_event → [可选召回] → decide → assemble_context → express → review → learn` 判定，没有给 response 补假兼容字段。

## 7. 非目标

- 不把 Harness 变成第二个对话控制器；
- 不让 policy 直接调用模型/数据库；
- 不把 deep 的全部领域逻辑塞进一个 action；
- 不删除用户数据、迁移脚本或无关前端文件；
- 不在没有真实 eval 的情况下宣称“更优异”。

## 8. 自审

本轮已经完成默认路径切换，但仍有三个现实约束：

1. deep 第一版仍是确定性顺序策略，不是模型自主选动作。这不是缺陷，而是有界自治的中间态；`PolicyView` 和 `ActionRegistry` 已分离，后续可以替换成模型策略而不动领域代码。
2. checkpoint 第一版只保存可恢复摘要和 action 历史，不保存完整模型上下文；这是为了可恢复性和体积的折中。若要做到 time-travel，需要再引入事件日志存储，不在本轮范围。
3. 固定 eval set 已经建立，但仍只有 10 条（5 行为 + 4 quick + 1 deep），覆盖罗辑 T6 的少量场景；还不能证明跨角色、跨时期和更多失败路径。下一步是把线上失败沉淀进 JSONL，而不是把 10 条当成完整覆盖。

另外，`real_eval=skipped` 时 gate 通过只代表“当前代码测试 + 缓存证据”通过；报告必须保留这个区别，不得把 cached 写成 live。真实 deep/quick 证据在 `docs/role-subject-deep-probe.json` 与 `docs/agent-harness-live-probe.json` 中，均已带 `runtime` 标识。
