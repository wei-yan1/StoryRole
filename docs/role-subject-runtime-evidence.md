# Role Subject Runtime：实现与真实验证证据

> 当前状态：本文件主体是 **legacy 主链的历史封版证据**（116 passed / 5 quick / 1 deep），只用于回滚对照。2026-11-16 默认路径已切换为 `AgentHarness`（quick/deep），旧 kernel 已删除，当前 pytest 为 **132 passed**；真实证据以 `docs/agent-harness-live-probe.json`、`docs/role-subject-deep-probe.json`、`docs/rolerag-persona-behavior.json` 和 `docs/harness-gate.json` 为准，不能拿本文件的旧封版给新 runtime 背书。
>
> 当前 live gate：pytest 132 passed、固定 eval set 10 条有效、5 个行为用例 5/5、quick 4/4、deep 1/1，`real_eval=passed`。

## 1. 这次改的不是提示词，而是回答的产生顺序

旧链路主要是：提问 → 检索画像/小说材料 → 组装 prompt → 生成 → 评审。角色在每轮临时拿材料“扮演”，上一轮的决定没有成为下一段可引用的经历。

新主链为：

```text
route → perceive → interpret → recall → cognition(可选)
      → decide → assemble → express → review → learn
```

关键区别：

- `SubjectUnderstanding` 在检索前形成：用户做了什么、角色当前处境、还缺什么记忆。
- `RecallManifest` 只负责“我可能记得什么、来源是什么”；无关 probe 片段不能因数量大于零就变成亲身记忆。
- `ActionDecision` 在检索后形成：回答、追问、安慰、拒绝、隐瞒或调整；deep 的 RoleCognition 修正同一种决定，而不是另写一条回答链。
- `SubjectState` 跨线程保存当前关注、顾虑、关系姿态、最后行动/情绪和最近经历。
- 每段 `Experience` 保存事件、当时理解、行动、决定依据、实际回答、情绪和证据 id；不再提取“我答应”式承诺。
- 下一轮通过 `prior_episode_ids` 和 `continue / adjust / reverse / new` 引用前一段经历。连续性不是由 action 名称机械推断。
- `character_agent.py` 仍是唯一对话出口；HarnessKernel 只拥有回合状态、阶段、共享预算、停止条件和 checkpoint。

## 2. 代码落点

| 文件 | 结构职责 |
|---|---|
| `app/harness/types.py` | SubjectState、Experience、Perception、理解/决定/回忆、TurnState 和预算契约 |
| `app/harness/appraisal.py` | 检索前理解、按需回忆、检索后行动、probe 相关性、连续性语义和 cognition_backend |
| `app/harness/context.py` | 主体上下文装配、无关 probe 材料过滤、超预算裁剪与主体状态保护 |
| `app/harness/kernel.py` | 路由前建立回合、阶段记录、剩余预算、停止原因和 checkpoint |
| `app/harness/update.py` | 用最终实际回答形成 Experience，不生成承诺清单 |
| `app/agents/storyrole/character_agent.py` | 真实主链编排、共享 deadline、惰性 A2A fallback、降级表达和状态保存 |
| `app/agents/storyrole/role_cognition_agent.py` | deep 认知决策、真实/回退后端标识、change_from_previous |
| `app/agents/storyrole/reasoning_agent.py` | quick 的 A2A 实现，消费主体理解和决定 |
| `app/agents/storyrole/evidence_analyst.py` | 有界证据归纳；不替角色作价值判断 |
| `app/api/v1/storyrole.py` | 正式返回 `subject`，保留 appraisal / interaction_state 兼容字段 |
| `tests/rolerag/` | 主体、probe、连续性、共享预算、惰性回退、MaaS 路由和证据分析边界测试 |

旧 JSON 的 `commitments / claimed_commitments / open_loops` 只允许反序列化兼容，不投射进新主体上下文；下一次保存写为 version=2，数据库表结构未改。普通聊天仍不强行写入共享小说世界图。

改动范围的可核验口径：直接涉及 15 个生产文件（当前合计 4877 行）、3 个测试文件（874 行）和 4 个真实验收脚本（1195 行）。这些是当前文件规模，不是净增行数；`rolerag-v2` 没有独立 tracked diff 基线，因此不伪造“本次新增/删除多少行”的 git 数字。核心变化是上表中的数据流和运行职责，而不是行数本身。

## 3. 已修复的真实问题

### 3.1 无关材料被当成关系记忆

RoleRAG 的 `route=probe` 现在优先于检索条数。即使返回 8 条片段，只要没有直接回答当前关系，行动保持 probe，无关原文也不进入“我的记忆”。行为验收加入“我没见过叶文洁”等错误说法负例。

### 3.2 把持续立场误判为反悔

真实跨轮回答为“现在还是这个决定”，旧规则却标成 `reverse`。现在：

- 是否引用上一轮由独立的 `references_previous` 表示，不与用户问题类型混为一个字段。
- 解释或确认此前边界标为 `continue`。
- 其他行动变化通常为 `adjust`。
- `reverse` 必须由决策层明确给出，不能由“hold_boundary → answer”机械推断。

严格 quick gate 已读到：`turn_count=2`、两段 episodes、非空 `prior_episode_ids`、`change_from_previous=continue`，与回答“现在还是这个决定”一致。

### 3.3 eager fallback 重复执行模型

旧写法把 `fallback=await RoleCognitionAgent().decide(...)` 作为实参提前执行：A2A 之前本地模型已经完整跑过一遍，远端成功也浪费了这次调用，deadline 也没有约束后续阶段。首次 deep 因此跑到 252.804 秒，却仍被记成正常结束。

现在 A2A 模型型 fallback 是惰性 callable：远端成功时零调用，失败时最多一次，预算耗尽时不再调用模型型 fallback。route 在预算建立后执行，quick/deep 只切换同一回合预算，不重启计时；route/cognition 都有独立阶段记录。

### 3.4 辅助证据分析挤占主体认知和表达时间

精简前，最终 gate 的 deep 为 119.1275/120 秒，虽然通过但余量不足；其中 EvidenceAnalysis 61.55 秒、RoleCognition 9.63 秒、评审 25.96 秒。十项 q1 的旧实现为 121.9 秒、`deadline_exceeded`。

EvidenceAnalysis 现在最多使用 4 段证据、每段 1400 字，画像只取决策相关字段，claims 最多 6 条，输出上限 1400 tokens。它不是人格评分器，也不输出最终回答。

优化后同一 q1：86.3 秒、`review_accepted`、persona_score=0.95；q2：66.7 秒、`review_accepted`、persona_score=0.88。两者 `cognition_backend=aliyun_maas`，没有关键模型 fallback。

### 3.5 当前身份被过去职责覆盖

第一次合并十项时，b3 虽为 persona=1.0、review_accepted，却回答“开关在手里、还在值守、职责没结束”，与同一 T6 下 q1/q2 的“已经交接”矛盾。这证明 HTTP 和人格快检都不能替代主体一致性检查。

修复不是补一句“请注意时期”：

- `SubjectUnderstanding` 新增 `current_reality`，显式保存女娲契约里的当前身份与时期。
- ActionDecision 的 `decision_reason / boundaries / must_not` 必须消费这份现实；已交接、离开、审判或结束的职责不能写成现在仍执行。
- 轻量评审把“过去职责写成现在仍执行”列为 fail，不增加独立事实评分器。
- quick 晚期身份验收要求 current_reality 存在且已进入决定边界，并加入“开关在手里 / 还在值守 / 职责没结束”负例。

修复后的真实 b3：“我现在就是个老人。做过该做的事，把开关交了出去。”回答、current_reality、决定边界三者一致。

## 4. 最终严格 gate 与 loop

最后一次 `harness_loop.py --runs 1` 在 `STORYROLE_EVAL_REAL=1` 下重新执行严格 gate，磁盘结果如下：

- **pytest：116 passed in 0.71s**。
- **quick：5 用例、6 轮，5/5，acceptance_rate=1.0**，平均 5.5708 秒；五项均为 review_accepted。
- **跨轮连续性**：turn_count=2、两段 episodes、非空 prior_episode_ids、`change_from_previous=continue`，与“现在还是这个决定”的回答语义一致。
- **晚期身份**：current_reality 已进入决定边界；最终 quick 回答为“面壁者、救世主——都是别人给的名头。我做了我该做的事，做完了”，没有仍在值守/开关仍在手里的负例。
- **deep：68.7263 秒、persona_score=0.9、cognition_backend=aliyun_maas**，HTTP、阶段、真实认知、认知写入同一决定、经历保存、评审、晚期细节和无关键 fallback 全部通过。
- deep 阶段：cognition 18.27 秒、express 3.96 秒、review 24.63 秒；EvidenceAnalysis 工具耗时 10.86 秒，RoleCognition 7.33 秒。总时长低于 120 秒预算，未用调大预算制造通过。
- **画像/数据库**：three_body_agent_v2，profile_id=25 / version=24 / ready / T6；画像与 period 7 各 38 条晚期证据，交集 38，coverage=1.0。
- **real_eval=passed，loop passed=true，next_step=continue**。

**证据口径说明（2026-11-16 核对）**：这里的 `real_eval=passed` 是最后一次显式设置 `STORYROLE_EVAL_REAL=1` 的严格运行结果。默认运行 `harness_gate.py`、不设置该变量时，只复用已有 quick/deep 报告，输出 `real_eval=skipped`；此时 `passed=true` 表示 pytest、已存行为/deep 证据和画像对齐通过，不表示刚刚重跑了真实 HTTP。当前 gate 尚未把报告与代码 revision 绑定，这是已知的证据新鲜度缺口，不能把 cached gate 当作 live eval。

最终 quick/deep 仍记录 `harness_context_trimmed`，其含义与限制见第 6 节；没有关键模型 fallback。

## 5. 十项新主链回归结果

| 用例 | 耗时 | persona 快检 | 停止原因 | 主体/时期复核 |
|---|---:|---:|---|---|
| q1 | 86.3 秒 | 0.95 | review_accepted | T6 回望威慑、人类道德与五十四年执剑 |
| q2 | 66.7 秒 | 0.88 | review_accepted | 交代制度、权力、具体的人及交接后的拘押 |
| q3 | 5.7 秒 | 1.0 | review_accepted | 简短日常，不借闲聊强行讲小说 |
| q4 | 105.8 秒 | 0.78 | review_accepted | 以克制方式守住庄颜与私人生活的边界 |
| q5 | 9.3 秒 | 1.0 | review_accepted | quick；控制中心、五十四年、对视与交接前记忆 |
| q6 | 71.8 秒 | 0.86 | review_accepted | 明确假设边界；不逃避按下的责任，也不自称怪物 |
| b1 | 4.0 秒 | 1.0 | review_accepted | 行为断言通过；拒绝“救世主”施压 |
| b2 | 4.4 秒 | 1.0 | review_accepted | 行为断言通过；见过两人但没有看见他们之间发生什么 |
| b3 | 9.6 秒 | 1.0 | review_accepted | 修复后明确“把开关交了出去”；无当前职责负例 |
| s1 | 6.3 秒 | 1.0 | review_accepted | 记忆有取舍，庄颜与孩子没有来源的部分不补写 |

合计：10/10 HTTP 200，10/10 review_accepted，10/10 返回完整 subject，三项行为断言 3/3；q1/q2/q4/q6 四个 deep 的 `cognition_backend=aliyun_maas`。分组与一次 b3 修复重跑累计 377.506 秒。

十项脚本已去除 profile 22、cutoff=44 和“十项一律不合格”的旧结论，保存 `subject`、阶段、预算、工具调用和当前画像口径。最终 JSON/Markdown 已按 q1–q6、b1–b3、s1 合并。

## 6. 降级与未覆盖项

- quick/deep 仍可能出现 `harness_context_trimmed`。只有实际超 token 预算才记录；正常限制证据条数不再算故障。裁剪只针对历史和回忆，身份、主体状态、理解、决定和轻量约束保留。
- 当前只证明有界裁剪不牺牲主体状态，尚未证明更长线程中的连续性完全不受影响。
- 真实数据仍只有罗辑 period 7；未做跨角色、跨时期压力验证。
- quick 的确定性理解不是完整人格认知；不能把它包装成 RoleCognition。
- `reverse` 已有明确认知输出的单元测试；真实多轮 gate 当前证明的是 `continue`，真实 reverse 场景仍待补。
- deep 延迟已明显下降，但模型服务波动仍可能接近预算；不得通过简单调大 deadline 掩盖问题。
- `TurnBudget` 目前只有 `deadline_ms`、`max_review_attempts`、`max_context_tokens` 真正参与执行约束；`max_model_calls`、`max_retrieve_calls`、`max_tokens`、`max_wall_time_ms` 仍是声明/记录口径，尚未形成逐项硬闸门。因此不能把“有预算字段”写成“所有预算都已执行”。
- 2026-11-16 补充：上述预算缺口只在 legacy 路径成立；quick 的 `AgentHarness` 已经硬执行 model/retrieve/token/deadline/wall，但 deep 和 legacy 仍未执行，不能把新路径的预算能力反推给旧路径。
- quick `AgentHarness` 当前覆盖 greeting / pressure / fact_boundary / decision_continuity 四个真实 case；两轮 continuity 已证明 `turn_count=2`、两段 episodes、`prior_episode_ids` 和 `continue`，但关系缺口、晚期身份、reverse 和更长线程尚未在 harness 路径跑过。
- `StoryRoleQuickPolicy` 是确定性顺序策略，不是模型自主选择动作；action loop 存在，但“策略选择”仍是固定逻辑。
- `AgentHarness` 的 checkpoint 是 compact 摘要，不是 durable resume/time-travel；进程崩溃后不能从上次 action 继续。
- gate 在 `STORYROLE_AGENT_HARNESS=1` 时会要求 `agent-harness-live-probe.json` 通过，但 behavior/deep 仍是 cached；这不等于新路径的完整 live eval。
- 严格 gate、完整十项和真实 loop 已闭合；本节剩余项不能用“全绿”自动视为已覆盖。

## 7. 原始证据

- `docs/role-subject-runtime.md`：架构蓝图与边界。
- `docs/role-subject-before.json`：重构前基线，不能作为新架构证据。
- `docs/rolerag-persona-behavior.json`：五组 quick 行为与跨轮经历。
- `docs/role-subject-deep-probe.json`：deep 的真实认知、决定、经历和阶段耗时。
- `docs/agent-harness-live-probe.json`：quick `AgentHarness` 的 3 个真实 case、action 链、预算和 trace；与 legacy 5 quick 证据分开。
- `docs/harness-gate.json`：pytest、quick/deep、画像对齐的硬闸门。
- `docs/rolerag-ten-questions-harness.json/.md`：新主链十项结果。
- `docs/harness-state.json`：最终 loop 状态。
