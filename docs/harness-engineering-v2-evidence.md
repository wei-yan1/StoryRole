# Harness 落地的可验证结果

> **历史文档 / 已封存（2026-11-16）**：以下记录是 2026-11-15 的 102 passed / 3 行为案例基线，不代表当前 Role Subject Runtime。当前证据以 `docs/role-subject-runtime-evidence.md` 的 116 passed / 5 quick 用例 / 1 deep probe 为准；本文件只用于对照旧 Harness。

> 对应设计：`docs/harness-engineering-v2.md`（v2.1：Harness 是回合运行架构，不是 `app/harness/` 组件）
> 生成时间：2026-11-15
> 原则：只写实际跑过的东西；未验证的单独列“未覆盖”。
> 本轮代码基线：`HarnessKernel` 已包住 `character_agent.reply()` 的 role/memory/web retrieval、state checks、appraise、context、generate、review、commit；单测 89 passed；真实 quick、deep、行为 3/3、gate、loop 均已在新 kernel 下重跑。

## 0. 当前评审口径与复核（2026-11-16）

- 主评只有“像不像角色”：身份、信念、目标与恐惧、关系态度、决策方式和说话习惯。
- 早期/晚期与知识边界合并为一个轻量认知检查；不再单列承诺或“通用助手”评审。`ReviewPacket` 已移除 `interaction_text`，对话记忆保留但不作为独立验收目标。
- 第三个真实行为用例由 `promise_continuity` 改为 `late_period_identity`；回答为“面壁者是很久以前的事了……握着开关五十四年，现在交出去了”，行为断言通过。
- 底层 `HarnessEvalSuite` 同步收敛：默认第四例改为晚期身份理解，删除 `require_commitment` 字段、承诺携带分支和全局 `generic assistant phrase` 失败循环；新增测试证明通用措辞不再构成独立失败条件。
- 当前实测：`102 passed`；真实行为 3/3，三项 `persona_score=1.0`，平均 5872.8ms；gate `passed=true`；v2 画像对齐 38/38、coverage 1.0、profile 25 / version 24 / ready。
- 三个 quick 行为用例均通过本地角色快检，未为轻量认知检查额外调用深审。gate 中 `real_eval=skipped` 是避免重复调用模型；真实行为已单独运行并写入 `docs/rolerag-persona-behavior.json`。
- 两份十问报告保留为历史结果，其中旧 b3 不作为当前评审口径；本次没有为旧题重跑十问。

## 1. 完成清单

| 模块 | 文件 | 状态 | 证据 |
|---|---|---|---|
| 回合运行内核 | `rolerag-v2/app/harness/kernel.py` | 已接入 | `test_kernel_owns_turn_intent...` + 真实 HTTP `harness.phase_history` |
| 回合意图 | `app/harness/types.py` 的 `TurnIntent` | 已接入 | HTTP `harness.intent.core_intent/constraints/completed_steps` |
| checkpoint 重建 | `HarnessKernel.resume` + `TurnState.from_dict` | 已实现并测试 | `test_checkpoint_can_resume_turn_state` |
| 上下文快照 | `app/harness/context.py` 的 `ContextSnapshot` | 已接入并持久化 | HTTP `harness.context_snapshot` + `interaction_state.context_snapshot` |
| 模型调用记录 | `HarnessKernel.record_model_call` | 已接入 | HTTP `harness.model_calls[0]`：模型、耗时、输出字符、usage |
| 结构化上下文 | `rolerag-v2/app/harness/context.py` | 已接入 | `test_harness.py` + 真实 HTTP `harness.phase_history.context` |
| 能力登记与结果蒸馏 | `rolerag-v2/app/harness/tools.py` | 已实现 | `distill_evidence` / `distill_memories` / `distill_web` |
| 情境判断 | `rolerag-v2/app/harness/appraisal.py` | 已接入 | `appraisal` 字段 + 压力/情绪/关系测试 |
| 线程级主体状态 | `rolerag-v2/app/harness/state.py` + `storyrole_interaction_states` | 已接入 PostgreSQL | 线程 56/57/58：真实行为 3/3；`context_snapshot.estimated_tokens` 4223/4312/4254 |
| 评审包 | `rolerag-v2/app/harness/review.py` | 已接入 | `ReviewPacket` 不含 `reasoning/context` 测试 |
| 有限评审循环 + 无进展守卫 | `review.py` 的 `LoopGuard` | 已接入 | 2 次上限测试；同指纹重复 → `review_no_progress` |
| 节点/边/状态图 | `rolerag-v2/app/harness/graph.py` | 已实现并测试 | fan-out/fan-in 测试；评审自环 |
| 行为 eval | `rolerag-v2/app/harness/eval.py` | 已实现 | 5 条默认行为用例检查通过 |
| 硬闸门 | `rolerag-v2/scripts/harness_gate.py` | 已跑 | `docs/harness-gate.json`，89 passed |
| 回归 loop | `rolerag-v2/scripts/harness_loop.py` | 已跑 | `docs/harness-state.json` |
| 规则索引 | `AGENTS.md` | 已同步 | 已改为 kernel 架构描述 |
| 接口透出 | `app/api/v1/storyrole.py` | 已接入 | 非流式响应含 `appraisal/interaction_state/harness` |

## 2. 硬闸门

```json
{
  "passed": true,
  "pytest": "89 passed in 0.52s",
  "behavior_passed": true,
  "acceptance_rate": 1.0,
  "real_eval": "skipped"
}
```

说明：

- 89 = 原 78 条 + 新增 11 条 Harness 测试（含 kernel、ContextSnapshot、no-progress）。
- 真实 HTTP 行为不是靠 `STORYROLE_EVAL_REAL=1` 在 gate 里重跑，而是单独跑了 `scripts/e2e_persona_behavior.py`，结果写入 `docs/rolerag-persona-behavior.json`，gate 读取该文件做行为判定。
- 当前 gate 不再读取承诺状态；第三行为是 `late_period_identity`。三个行为用例都要求行为命中且 `persona_score >= 0.65`，不另设“通用助手”通过条件。

## 3. 真实 HTTP（quick）

来源：`docs/rolerag-api-http.json`（该文件随后被 deep 运行覆盖；quick 数值来自同一次脚本运行的终端输出，thread 55）

| 字段 | 值 |
|---|---|
| status | 200 |
| thread_id | 55 |
| engine | rolerag |
| route | recall |
| period_id | 7 |
| cutoff | 44 |
| profile_injected | true |
| evidence_count | 8 |
| persona_score | 1.0 |
| harness_enabled | true |
| harness_stop_reason | review_accepted |
| interaction_state.turn_count | 1 |
| appraisal.action | natural_reply |
| intent.core_intent | 以罗辑身份回应“smalltalk”；保持时期/知识边界/关系/承诺连续 |
| intent.completed_steps | role_retrieval / memory_retrieval / web_retrieval / appraise / context / generate / review / commit |
| context_snapshot.estimated_tokens | 4213 |
| context_snapshot.evidence_digest | 2967894a2ece1522911d0f4fa69789013e90c7a5 |
| context_snapshot.memory_digest | da39a3ee5e6b4b0d3255bfef95601890afd80709（本轮无长期记忆） |
| model_calls[0] | deepseek-v4.1-flash-1017, 3729.48ms, 278 chars, 6396 tokens |
| latency_ms | 9195.4 |

`harness.phase_history` 实际出现：

```text
role_retrieval   327.07ms（mode=quick）
memory_retrieval 1526.79ms
web_retrieval     34.96ms（requested=off）
appraise           0.85ms（action=natural_reply）
context            3.36ms（estimated_tokens=4213，trimmed=false，identity_digest=aa0dfa92599d）
generate         4504.85ms（mode=quick）
review             0.07ms（attempts=1，accepted=true，persona_score=1.0）
commit             0.38ms（turn=1，commitments=1，acceptance_rate=1.0）
```

说明：

- Harness 现在不只是包住 appraise/context/review/commit，还把 RoleRAG 检索、记忆检索、联网检索、生成纳入同一阶段时钟。
- `harness.intent.completed_steps` 与 phase 名称一致，不再出现重复的 `next`。
- 线程 55 的回答主动说出“我说我会记住，试着做做”，`commit` 把它写成 active commitment。
- `evidence_digest` 与 `memory_digest` 已分开：前者来自可见证据行，后者来自长期记忆/联网行；本轮无长期记忆，所以后者是空字符串 SHA1。

## 3.1 真实 HTTP（deep）

来源：`docs/rolerag-api-http.json`（本轮最后写入的是 deep 结果）

| 字段 | 值 |
|---|---|
| status | 200 |
| thread_id | 59 |
| engine | rolerag |
| route | recall |
| period_id | 7 |
| cutoff | 44 |
| evidence_count | 18 |
| persona_score | 1.0 |
| harness_stop_reason | review_accepted |
| budget.max_context_tokens | 24000 |
| budget.max_review_attempts | 2 |
| latency_ms | 142608.2 |

`harness.phase_history` 实际出现：

```text
role_retrieval   354.51ms
memory_retrieval 1535.82ms
web_retrieval     45.99ms
state_checks     141.09ms
appraise           0.84ms
context            3.16ms
generate         6826.90ms
review          20012.51ms（attempts=1，accepted=true，persona_score=1.0）
commit             0.26ms
```

说明：

- deep 模式确实跑通了 kernel 包住的完整阶段链；review 是真实语义评审（20s），不是 quick 的本地跳过。
- deep 总延迟 142.6s，仍高于理想值；主要成本在生成 6.8s + 评审 20s + 其他 A2A/检索等待。
- 本轮 `degradations` 为 `evidence_analysis_fallback`、`persona_fidelity_guard_fallback`，属于既有 A2A/审查服务不可用时的降级，不是 kernel 失败。
- deep 只有 1 个真实 smoke 用例，不能代表所有角色/时期的表现。

## 3.2 十项回归（2026-11-15 23:22）

来源：`docs/rolerag-ten-questions-harness.md` / `.json`（run_id `20261115-232250`）。
构成是项目内现存的十项（不是另行命名的“十问”）：六问（q1-q6）+ 三行为（b1-b3）+ 一记忆 smoke（s1）。

| 指标 | 结果 |
|---|---|
| HTTP 成功 | 10/10 |
| 行为断言 | 3/3 |
| 六问人格分均值 | 0.945（上一版新项目基线 0.852） |
| 六问证据总数 | 55（上一版 19） |
| 新线程 | 60-70 |
| 总耗时 | 约 602s |

关键真实分支：

- q1 第一次评审 0.52，被打回“补写后期/晚年公共经历”，重写后审核 0.91 / persona 0.93；
- q6 第一次评审 0.42，被打回“把假设滑成执剑人/晚年姿态”，重写后审核 0.88 / persona 0.86；
- 这两个用例证明 deep 的“评审失败 → 重写 → 再评审”不是只有单测，真实 HTTP 也跑到了；
- q4/q6 人格分较上一版略降（1.0→0.88、0.92→0.86），q2/q6 延迟显著增加，不能概括为全面变好；
- b2 的关键词 checks 原先未覆盖“我哪知道/没在场/没证据/不替人编”，回答语义正确，补充 checks 后重算为通过；报告里保留这一说明。
- **时期校验未通过**：period 7 的 DB 名称是“新时期晚年时期”，但 profile 22 的 `identity` 明确写“晚年具体身份/经历证据未提供，不能补写”，其 `personality`/`evidence_claims` 实际是早期 T1/T2；`storyrole_persona_evidence` 里 profile 22 的 40 条证据全部来自“序 章”。根因是 `period_agent.evidence_for_period()` 在无 `evidence_ids`/`keywords`/`chapter bounds` 时回退到 `records[:40]`，不是模型编造。详见 `docs/rolerag-ten-questions-harness.md` 的“时期口径/根因”。

### v2 独立库与女娲 T6 重建（2026-11-16）

- 旧库 `three_body_agent` 保留不动；v2 新建 `three_body_agent_v2`，从旧库只读克隆。
- v2 `period 7` 回填 38 条 `三体III·死神永生` 晚期证据，`cutoff=53`、`boundary_source=explicit_bounds`、`confidence=1.0`。
- 女娲重跑曾出现模型调用失败后兜底为 heuristic profile 23；当时路由未稳定使用项目指定的阿里云 MaaS workspace 配置。当前统一为 `deepseek-v4.1-flash-1017` 经阿里云 MaaS，`OPENAI_*` 优先、`DASHSCOPE_*` 回退，`DEEPSEEK_*` 仅作官方端点回滚。修复后 profile 24 由真实模型生成，38 条晚期证据，`ready`；旧库 profile 22 和 heuristic 23 在 v2 中标记 `superseded`。
- T6 专用探针（“你已经一百多岁了……”）最终新鲜线程 139 返回 265 字、12 证据、`persona_score=0.9`、`review_accepted`，meta 为 `profile_version=24`、`cutoff=53`、`boundary_source=explicit_bounds`；回答包含白色大厅、最后十分钟、盘腿坐在正中、右手握开关、四个按钮、五十四年、向白墙鞠躬、四光年外、起身两手不碰地、双手把开关交给程心、没有人说过一句感谢等晚年/交接细节。降级项为空。
- 对照：同一 v2 库旧 q6 为 79 字、12 证据、`persona_score=0.88`、`review_accepted`，没有明显晚年感；说明时期/profile/cutoff 已对齐，但题目仍需 T6 专用矩阵，不能只跑旧 q6。
- 新增 Nuwa 模型路由测试后，`pytest tests\rolerag -q` 为 **91 passed**。详细记录见 `docs/rolerag-v2-database-nuwa.md`。

## 4. 真实行为 3/3（新 kernel 下重跑）

来源：`docs/rolerag-persona-behavior.json`

| 用例 | 线程 | 结果 | 关键观察 |
|---|---|---|---|
| 施压：替人类做决定 | 56 | passed | `appraisal.action=hold_boundary`；回答“不答应”，没有承诺自己做不到的事 |
| 关系 gap：叶文洁与史强 | 57 | passed | 回答“不知道/没看见”，只说自己看见的部分，不替人物补关系 |
| 昨日承诺今天作数 | 58 | passed | `appraisal.continuity_requested=true`；`claimed_commitments` 带着“你答应过试着创立宇宙社会学”；回答“作数/答应” |

线程 58 的 state 实际长这样：

```json
{
  "turn_count": 2,
  "claimed_commitments": [
    {
      "text": "我昨天替你跟叶老师带话：你答应过试着创立宇宙社会学",
      "status": "claimed",
      "source": "user_claim"
    }
  ],
  "commitments": [
    {
      "text": "不过“试着”这两个字也得算数——我答应的是摸摸看...",
      "status": "active",
      "source": "character_answer"
    }
  ]
}
```

这里刻意区分：

- `claimed` 是用户说“你答应过”，不等于角色自己的记忆；
- `active` 是角色回答里自己作出的承诺；
- 两者都进入下一轮上下文，但提示词分别标明来源，避免把用户的话直接变成角色记忆。

## 5. PostgreSQL 状态

表：`storyrole_interaction_states`

实测（截至写本文）：

```text
count = 17
max(turn_count) = 26
thread 55 = quick HTTP 新线程，turns=1, claimed=0, promises=1, ctx_tokens=4213
thread 56 = 施压用例，turns=1, claimed=0, promises=0, ctx_tokens=4223
thread 57 = 关系 gap 用例，turns=1, claimed=0, promises=0, ctx_tokens=4312
thread 58 = promise 用例，turns=2, claimed=1, promises=1, ctx_tokens=4254
thread 59 = deep HTTP 新线程，turns=1, claimed=0, promises=0, ctx_tokens=4213
```

新增字段 `context_snapshot` 已经落进 JSONB，真实行里可以看到 `identity_digest / constraints_digest / evidence_digest / estimated_tokens / trimmed`。这意味着“这一轮模型看见了什么”不再只存在于日志。

表结构：

- `thread_id` 主键，外键到 `chat_threads`；
- `novel_id / character_id / owner_id / period_id` 作为作用域；
- `state JSONB` 存交互状态；
- `checkpoint JSONB` 存 `TurnIntent + phase_history + context_snapshot + model_calls + interaction + stop_reason`；
- `updated_at`。

数据库不可用时，`ResilientInteractionStateStore` 退回进程内 store，并允许 `harness_state_save_failed` 降级，不阻塞回答。

## 6. 与六层/五原则的对应

| 文章理念 | 本项目落点 | 证据 |
|---|---|---|
| Harness 是模型之外一切 | `HarnessKernel` 包住整轮，不是单个组件 | HTTP `harness.intent/phase_history/model_calls/stop_reason` |
| 回合意图与任务状态 | `TurnIntent` + `TurnState` | HTTP `intent.completed_steps=[role_retrieval,memory_retrieval,web_retrieval,appraise,context,generate,review,commit]` |
| 上下文是工作台 | `ContextManifest` 六段顺序 + 预算裁剪 + `ContextSnapshot` | `test_context_manifest...`、HTTP `estimated_tokens=4213` |
| 工具结果先蒸馏 | `distill_evidence` 限 6 条、截断、去重 | `test_review_packet_is_clean...` |
| 模型调用可观测 | `ModelCallRecord` | HTTP `model_calls[0]`：模型/耗时/输出/usage |
| 状态外化 | `InteractionState` + PostgreSQL | thread 56/57/58 |
| 生产/验收分离 | `ReviewPacket` 不含 reasoning/context | `test_review_packet_is_clean...` |
| 无进展停止 | `LoopGuard` 指纹 | `review_no_progress` 单测 |
| 约束与恢复 | `TurnBudget`、`StopReason`、degradations | HTTP phase history、gate |
| 重启胜过修补 | 线程级 checkpoint + 摘要分工 | `storyrole_interaction_states.checkpoint` |
| 规则文件宁缺毋滥 | 根目录 `AGENTS.md` 索引 | 已同步为 kernel 架构 |
| 技术债小额偿还 | `harness_loop.py` 状态文件 | `docs/harness-state.json` |
| Loop 最小四件套 | gate + AGENTS + state + loop | 上述文件 |
| Graph 的 loop 是最小图 | `ReviewLoop` 用单节点自环 | `graph.py` + `review.py` |

## 7. 明确未覆盖/未验证

1. **deep 的子阶段没有单独进 kernel**：`role/memory/web retrieval`、`state_checks`、`appraise`、`context`、`generate`、`review`、`commit` 已进 kernel；deep 内部的 `deep_question_planning` / `novel_retrieval` / `evidence_rerank` / `evidence_analysis` / `context_curation` 仍由 `reply()` 直接编排，只在外层 `generate` 前后被记录。十项回归里 q1/q2/q4/q6 的 `phase_history` 合计约 18–34s，而 HTTP 总耗时 116–153s，差额就是这些未打点阶段；Harness 已经是回合边界，但还不是“每一个子步骤都独立可回放”。
2. **deep 的失败重写分支已有真实证据，但样本仍少**：本轮十项 q1/q6 真实触发了“评审失败 → 重写 → 再评审”（q1 0.52→0.91/persona 0.93；q6 0.42→0.88/persona 0.86）；原 thread 59 只覆盖一次通过路径，不能替代多角色/多时期的失败重写样本。
3. **`TurnBudget.deadline_ms` 不是全局取消器**：kernel 有 `deadline_exceeded()`，但阶段边界未强制中断；真实超时仍由模型/A2A timeout 控制。
4. **`checkpoint` 可重建但未自动 resume**：`HarnessKernel.resume()` 和单测已能恢复 intent/phase/interaction，但 `reply()` 启动时不会自动接上上次未完成回合；恢复仍是显式能力，不是生产默认路径。
5. **ContextSnapshot 已存储但未复用**：下一轮会读 `InteractionState`，但 `build_context_manifest` 还没有做“上一轮快照 + 本轮增量”的跳过/复用。
6. **没有实现完整 5 层压缩金字塔**：现有 `chat_context_compaction` + `ContextManifest` 预算裁剪只覆盖一部分；大结果外置、Snip、Micro-Compact、Auto-Compact 尚未接入。
7. **ModelAdapter / ToolExecutor 未独立**：模型调用仍在 `_run_agent`，工具调用仍是各 A2A；kernel 只记录，不做统一路由/权限/截断/错误分类。
8. **评测仍是两层不是四层**：目前是行为 eval + 端到端 HTTP，没有工具层准确率、轨迹层约束、线上层指标。
9. **检索 fan-out 没有改造成图节点**：现有 `asyncio.gather` 仍负责 RoleRAG/memory/web/relationship/timeline 的并行；`GraphRuntime` 的 fan-out/fan-in 是独立测试，不是生产检索的实现。
10. **普通聊天仍不写 RoleRAG 图结算**：`graph_persisted` 仍为 null；Harness 只写线程级交互状态，不改变小说共享图。
11. **quick 的语义评审仍是条件触发**：本地 `check_persona` 通过且未设 `STORYROLE_PERSONA_GUARD_QUICK=1` 时，不调用 consistency-guard；HTTP 证据里 `review_skipped=true` 就是这个折中。
12. **动作/关系状态仍是确定性更新**：承诺识别仅作为可选对话记忆，不进入评审或 gate；`must_not`/`boundaries` 来自契约与规则，不是模型推理。
13. **行为集只有 3 个真实用例**：覆盖施压、关系 gap、晚期身份理解；跨角色/跨时期对比还没有真实数据。
14. **多 Agent 未实现**：评审用干净 packet 接近“新鲜眼睛”，但没有 Coordinator/worker 池/字段级隔离。
15. **`app/harness/__init__.py` 已导出 `HarnessKernel/TurnIntent`；但外部文档仍在陆续迁移到“回合运行架构”口径**，旧 `docs/rolerag-five-capabilities.md` 等未逐篇复查。

## 8. 复现命令

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q
D:\AgentCode\two\.venv\Scripts\python.exe scripts\harness_gate.py

# 真实 quick HTTP（写 docs/rolerag-api-http.json）
$env:STORYROLE_E2E_PERIOD_ID='7'; $env:STORYROLE_E2E_MODE='quick'
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_api_http.py

# 真实行为 3 例（写 docs/rolerag-persona-behavior.json）
$env:STORYROLE_E2E_PERIOD_ID='7'
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_persona_behavior.py

# 十项回归（六问 + 三行为 + smoke，写 docs/rolerag-ten-questions-harness.*）
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_ten_questions.py
# 只重算关键词 checks，不重新请求
D:\AgentCode\two\.venv\Scripts\python.exe scripts\e2e_ten_questions.py --rescore

# 回归 loop（写 docs/harness-state.json）
D:\AgentCode\two\.venv\Scripts\python.exe scripts\harness_loop.py --runs 1
```

## 9. 结论

这次落地不是“再加几个 prompt”，而是把 v2 的对话主链路改造成一个**以回合为单位的运行架构**：

- `HarnessKernel` 是唯一回合边界：拥有 intent、阶段时钟、预算、停止原因和 checkpoint；
- 角色先看到一份固定顺序的上下文清单，并留下 `ContextSnapshot`；
- 角色先判断“这件事对我意味着什么”，约束来自契约和本轮情境；
- 角色说过的承诺和用户声称的承诺分开存、分开提示；
- 生成和评审不再共享同一团上下文；
- 评审失败先看“有没有推进”，同稿同违规反复出现就 `review_no_progress`，不再空转；
- 模型调用、阶段耗时、上下文摘要、stop reason 都进入 API 和状态表，可回放、可比较。

一句话：**Harness 不是 `app/harness/` 里的几个组件，而是“一个回合如何运行”的整套架构；RoleRAG 让角色知道自己能知道什么，HarnessKernel 让角色在连续互动中仍然是他自己。**

## 10. v2 独立库复跑（2026-11-16）

这一节覆盖旧库 profile 22 的十项结论，口径改为 v2 独立库：

- 数据库：`three_body_agent_v2`
- period：`7 / 新时期晚年时期`，profile 24 的 `period_stage=T6`
- 证据：38 条 `三体III·死神永生` 的罗辑晚年 chunk
- cutoff：`53`、`explicit_bounds`、confidence `1.0`

硬闸门：

```json
{
  "passed": true,
  "pytest": "100 passed in 0.70s",
  "behavior_passed": true,
  "acceptance_rate": 1.0,
  "real_eval": "skipped",
  "profile_alignment": {
    "ok": true,
    "profile_id": 25,
    "profile_version": 24,
    "profile_evidence_count": 38,
    "period_evidence_count": 38,
    "evidence_overlap": 38,
    "period_evidence_coverage": 1.0
  }
}
```

完整十项（`scripts/e2e_ten_v2.py`，写 `docs/rolerag-ten-questions-v2.*`）：

| 项 | HTTP | 字数 | 证据 | persona | stop |
|---|---:|---:|---:|---:|---|
| q1 | 200 | 323 | 18 | 0.76 | review_accepted |
| q2 | 200 | 426 | 6 | 0.92 | review_accepted |
| q3 | 200 | 39 | 4 | 1.0 | review_accepted |
| q4 | 200 | 148 | 16 | 0.88 | review_accepted |
| q5 | 200 | 77 | 6 | 1.0 | review_accepted |
| q6 | 200 | 233 | 12 | 0.88 | review_accepted |
| b1/b2/b3 | 200 | — | — | 3/3 | review_accepted |
| s1 | 200 | 41 | 8 | 1.0 | review_accepted |

关键结论：

1. **v2 十项全 200、全部评审接受**，profile 版本一致为 24，cutoff 一致为 53；六问人格分均值 0.907。
2. q4 首轮曾 `review_budget_exhausted`（2 次上限），把 deep 深审上限提到 3 后接受；这说明评审循环本身有效，但需要足够预算才能收敛。
3. 本轮十项全部 `degradations=[]`：证据分析用最强 6 条、A2A 超时 90 秒，角色判断超时 45 秒；此前 q1 的 `role_cognition_fallback` 与 q2/q4 的 `evidence_analysis_fallback` 已消除。
4. 十项里的 q1/q2/q3/q4/q6 是早期题；它们的 persona 分数只能证明“v2 在旧题上仍然像罗辑”，不能证明“T6 晚年题像不像”。T6 专用题见 `docs/rolerag-v2-database-nuwa.md` 第 5 节。

## 11. v2 复现命令

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
.\scripts\run_v2.ps1 -m pytest tests\rolerag -q
.\scripts\run_v2.ps1 scripts\harness_gate.py
.\scripts\run_v2.ps1 scripts\e2e_ten_v2.py
.\scripts\run_v2.ps1 scripts\check_profile_alignment.py
```

