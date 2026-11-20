# AGENTS.md

本文件是索引，不是百科全书。细节放在 `docs/` 和 `rolerag-v2/` 下的代码/测试里；先读这里，再按需要加载对应文档。

## 项目地图

- 主项目：`D:\AgentCode\two`
- 工作副本：`rolerag-v2`
- 前端：`frontend/app/` 页面，`frontend/static/app/` 页面脚本与设计系统；旧单页归档在 `frontend/legacy/`，页面路由见 `app/main.py`。
- 角色域代码：`rolerag-v2/app/agents/storyrole/`
- RoleRAG：`rolerag-v2/app/rag/rolerag/`
- Harness：`rolerag-v2/app/harness/`
- 测试：`rolerag-v2/tests/rolerag/`
- 证据/报告：`docs/`

## 运行环境

- Python：`D:\AgentCode\two\.venv\Scripts\python.exe`
- 不要用全局 Python 3.14。
- pytest：`pytest 9.1.1`
- PostgreSQL：`localhost:5433`，库 `three_body_agent`，容器 `three-body-postgres`。

## 常用命令

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q
D:\AgentCode\two\.venv\Scripts\python.exe scripts\harness_gate.py
D:\AgentCode\two\.venv\Scripts\python.exe scripts\harness_loop.py --runs 1
```

## 架构边界（不可违反）

1. **RoleRAG 只回答“我能知道什么”**：可见事件、事实、关系、时期边界、来源；不负责“我是谁”。
2. **女娲 PersonaContract 只回答“我是谁”**：身份、矛盾、目标、恐惧、语气、判断方式、禁忌、关系、known/unknown。
3. **`character_agent.py` 是唯一对话出口**：解析身份后默认交给 `app/agents/storyrole/harness/turn.py` 的 `AgentHarness` action loop；旧 `TurnKernel` / `HarnessKernel` 与 `app/harness/kernel.py` 已删除，不存在第二条回合编排路径。历史、长期记忆、用户关系、联网、生成、校验、持久化由领域服务执行，但不拥有回合编排。
4. **交互状态与世界图分离**：`storyrole_interaction_states` 是线程级“我们之间发生了什么”，不写进小说共享图。
5. **生产与验收分离**：生成侧不得改评审结论；评审只拿用户话、草稿、女娲契约、角色关系和可见证据，不拿生成侧推理或主体内部决定。
6. **证据不足不得变成拒答**：小说事实要来源/时期/可见性；当前互动可以倾听、试探、安慰、沉默或拒绝。

## Harness 运行架构（改代码前先对照）

Harness 不是 `app/harness/` 里的组件集合，而是“一个回合如何运行”的整体架构。`app/harness/` 是六层运行环境的代码落点，不是第二个对话控制器。

1. 回合边界：`character_agent.reply()` 仍是唯一入口，只解析身份、构造 `identity`，然后调用 `run_harness_turn`；`AgentHarness` 拥有循环、guardrail、上下文视图、预算、trace、checkpoint、stop reason。旧 `TurnKernel` / `kernel.py` 已删除。
2. 有界动作：`AgentHarness` 按 `AgentAction → Observation` 循环，校验动作依赖、预算、deadline、stop reason；`learn` 必须发生，失败路径允许在关键 action 失败后 stop。策略在 `app/agents/storyrole/harness/policy.py`，只选动作，不执行；handler 在 `.../harness/actions.py`，一个 action 一个 handler。
3. 上下文：`app/harness/context_pipeline.py` 的 `ContextView` 按 action 暴露上下文；`understand_event` 看不到 decision/memory，`review` 看不到 situation/history；超预算只裁 history/role/handoff，主体状态与 decision 必须保留。
4. 工具：`app/harness/tool_runtime.py` 是可执行 ToolRuntime，统一 schema、权限、超时、同步/异步 handler、结果蒸馏、provenance 和幂等缓存；StoryRole 只注册 `rolerag.evidence`、`memory.search`、`web.search`、`relationship.state`、`timeline.guard` 五个只读工具，没有写工具。
5. 状态：`SubjectState` + `storyrole_interaction_states` + `app/harness/handoff.py` 的 `TurnHandoff`；原始对话、完整检索结果和生成侧隐藏推理不跨轮携带；`TurnCheckpoint` 保存 turn/scope/mode/step/completed_actions/action_history/budget/subject_state/artifacts_digest，支持 `resume=True` 跳过已完成 action。
6. 观测：`app/harness/trace.py` 记录 action/context/tool/budget/observation/stop；`scripts/probe_agent_harness.py` 写独立 `docs/agent-harness-live-probe.json`，`scripts/e2e_persona_behavior.py` 写 `docs/rolerag-persona-behavior.json`，两份证据分开，不得互相覆盖或拿旧报告背书。行为结构判定读 `harness_trace.summary.actions`，不读旧 `phase_history`。
7. 评审：`app/harness/review.py` 主评“像不像角色”，轻查“是否超出当前时期与可见认知”；同一草稿+同一违规反复出现 → `review_no_progress`；生成侧不得改评审结论。
8. 约束：`BudgetLedger` 在默认 harness 中硬校验 model/retrieve/token/deadline/wall 和 `max_per_turn`；token 只在调用方上报时计入；预算超限写明确 stop reason，不静默循环。

关键边界：`character_agent.py` 仍是唯一对话出口；RoleRAG 只提供可见证据；女娲只提供身份契约；Harness 只约束回合运行，不取代领域流程。完整六层映射见 `docs/agent-harness-v3-architecture.md`，两篇文章的逐条落地见 `docs/harness-loop-engineering-distillation.md`。

## Loop 规则

- `rolerag-v2` 没有独立 tracked diff 基线，不要照搬 git worktree；用独立 `thread_name` / 状态作用域隔离。
- 不做无人值守改代码/自动合并。
- 每次回归结果写 `docs/harness-state.json`；硬闸门失败先修闸门。
- 接受率低于 50% 视为亏本；不要用“我感觉变好了”代替证据。

## 评估闸门

- 硬闸门：`pytest tests/rolerag -q` 全绿。
- 固定 eval set：`docs/agent-harness-eval.jsonl` 必须包含 5 行为 + 4 quick + 1 deep，id 唯一；三个探针脚本不得再维护第二份 case 常量。
- 行为闸门：`docs/rolerag-persona-behavior.json` 的 5 个真实 quick 用例全过，其中含两轮决定连续与情绪不强制检索；`docs/role-subject-deep-probe.json` 必须证明 deep 的阿里云 RoleCognition 已写入同一 ActionDecision。
- Harness 闸门：默认路径必须让 `docs/agent-harness-live-probe.json` `passed=true`；该文件与 legacy 5 quick 分开，不得互相覆盖或拿旧报告背书。gate 不再用 `STORYROLE_AGENT_HARNESS` 开关决定是否检查 harness probe。
- 真实闸门：默认复用最近 quick/deep/harness 证据；设 `STORYROLE_EVAL_REAL=1` 才重跑真实 HTTP（e2e + deep + quick probe）。行为、deep 或 harness 证据缺失/失败时 gate 不得通过；`real_eval=skipped` 不等于 live。
- 报告隔离：`scripts/harness_loop.py` 跑 gate 时写 `docs/harness-loop-gate.json`（通常 `real_eval=skipped`），不得覆盖 `docs/harness-gate.json` 的最近一次 live 报告。
- 结果：`docs/harness-gate.json`。

## 已知约束

- 模型只用 flash 档：`deepseek-v4.1-flash-1017`；直接写 `deepseek-flash` 会 404。
- 语言模型统一经阿里云 MaaS 转发，优先使用 `OPENAI_API_KEY / OPENAI_BASE_URL`，`DASHSCOPE_*` 仅作回退。`deepseek-v4.1-flash-1017` 是阿里云上的模型 ID，不是切换到 DeepSeek 官方 API 的信号；禁止按模型前缀启用 `DEEPSEEK_*`。配置约束写在根目录 `.env` 的阿里云 / DeepSeek 注释中。
- Laya 已安装在 `.venv`（`laya` + torch），`STORYROLE_DECISION_BACKEND=laya` 是默认；quick 和 deep 都先走 `query-planner` 的 Laya Router，Laya 异常才回退 `rule_fallback`。Laya 权重缓存统一在 `D:\AI\Models\huggingface`（`HF_HOME` / `HUGGINGFACE_HUB_CACHE`），Ollama 模型在 `D:\Ollama\model`（`OLLAMA_MODELS`）；`rolerag-v2\scripts\run_v2.ps1` 会在本地 Laya snapshot 存在时默认离线加载，并在启动时后台预热 multilingual checkpoint。
- 真实数据只有罗辑 `period_id=7` 的女娲画像；跨角色/跨时期对比暂无数据。
- v2 RoleRAG 子路径不另设查询向量排序缓存；旧 `search_evidence()` 仍可能使用向量/BM25 原文检索。查询层已完成索引优化，不要重复优化。
- 普通聊天目前不写 RoleRAG 图结算；不要为了“闭环”强行改变证据边界。
- 罗辑 `period_id=7` 的名称是“新时期晚年时期”。旧库 `three_body_agent` 的 profile 22 只覆盖早期 T1/T2 证据，保留作历史对照，不参与当前 v2 验收。v2 独立库 `three_body_agent_v2` 已用 38 条“三体III·死神永生”证据重建 profile_id=25 / version=24（T6，cutoff 53 / explicit_bounds，`period_stage=T6`）；旧库保留不动。v2 运行必须显式设置 `POSTGRES_DATABASE=three_body_agent_v2`，不要改根 `.env` 的旧库默认值；推荐用 `rolerag-v2\scripts\run_v2.ps1` 启动。修 T6 前先补 period 7 的画像/证据，不要用提示词硬演。
- 当前十项使用 v2 T6 与 Role Subject Runtime，结果见 `docs/rolerag-ten-questions-harness.md`；早期经历只能作为晚期回望，不能原样演成青年现场。当前行为第三项为 `late_period_identity`，最新 quick/deep 结果看 `docs/rolerag-persona-behavior.json`、`docs/role-subject-deep-probe.json` 和 `docs/harness-gate.json`。命名 period 无 evidence 窗口时 `evidence_for_period` 会 fail-closed；profile/period 证据对齐检查用 `scripts/check_profile_alignment.py`。


## 文档索引

- `docs/agent-harness-v3-architecture.md`：当前默认架构。六层职责、action context 白名单、工具/状态/checkpoint、Loop Engineering 落地、迁移顺序、验收口径和自审。
- `docs/agent-harness-eval.jsonl`：固定 eval set（5 行为 + 4 quick probe + 1 deep probe），三个探针直接加载；gate 校验 suite 数量与唯一 id。
- `docs/harness-loop-engineering-distillation.md`：Harness Engineering / Loop Engineering 两篇文章的提炼、逐条落地表和未采纳部分。
- `docs/role-subject-runtime.md`：角色主体全链路架构、核心数据结构与批判性自审；legacy + kernel 路径保留为回滚层，默认路径以 `docs/agent-harness-v3-architecture.md` 为准。
- `docs/role-subject-runtime-evidence.md`：legacy 主链的严格封版（116 passed / 5 quick / 1 deep）、失败修复和未覆盖项；新路径证据见 `docs/agent-harness-live-probe.json` 和 `docs/role-subject-deep-probe.json`。
- `docs/agent-harness-migration.md`：旧六层迁移记录，已被 `docs/agent-harness-v3-architecture.md` 取代；只作历史审计材料，不作为默认架构口径。
- `docs/agent-harness-live-probe.json`：默认路径 quick AgentHarness 的 4 个真实 case、action 链、预算和 trace；与 5 个行为用例分开，不得互相替代。
- `docs/agent-harness-live-probe.md`：上述 probe 的可读摘要、开销与未证明事项。
- `docs/role-subject-before.json`：主体主链重构前的真实 quick 行为基线，不能当作新架构证据。
- `docs/role-subject-deep-probe.json`：最近一次 deep 真实 RoleCognition、共享决定、经历保存与 deadline 验收。
- `docs/harness-engineering-v2.md`：旧 Harness 与局部评审架构记录；新主链以 `docs/agent-harness-v3-architecture.md` 为准。
- `docs/harness-engineering-v2-evidence.md`：历史基线（102 passed / 3 行为案例，2026-11-15），已被 `role-subject-runtime-evidence.md` 取代，不要作为当前口径。
- `docs/rolerag-ten-questions-harness.md`：罗辑十项回归（六问 + 三行为 + smoke）与旧基线对照。
- `docs/rolerag-ten-questions-v2.md`：评审简化前的历史十项链路验收（10/10 HTTP 200）；当前口径与最新复核见 `docs/role-subject-runtime-evidence.md`。
- `docs/rolerag-v2-database-nuwa.md`：v2 独立库、period 7 晚期证据与女娲 profile_id=25 / version=24 记录。
- `docs/rolerag-five-capabilities.md`：五项能力与验证。
- `docs/rolerag-subject-bridge.md`：角色主体闭环。
- `docs/rolerag-query-optimization.md`：查询层优化与停手结论。
- `docs/harness-gate.json`：最近一次手动/真实闸门。
- `docs/harness-loop-gate.json`：LoopRuntime 跑出的回归闸门，通常复用缓存证据；不得覆盖 `docs/harness-gate.json`。
- `docs/harness-state.json`：最近一次回归 loop 状态。
- `docs/frontend-redesign-plan.md`：书架优先的信息架构、页面路由、设计系统与验收口径；旧 chat-first 与“夜航档案室”方向已废弃。
- `docs/frontend-redesign-delivery.md`：书架 / 小说 / 角色拆页、`/api/app` 接口、真实点击与响应式验收；旧单页和旧三体素材已归档到 `frontend/legacy/`。
- `docs/app-ui-report-v4.json`：书架优先版 17 个页面 × 1440 / 768 / 390 的 Playwright smoke 报告；截图在 `docs/ui-shots-v4/`。
- `docs/app-ui-report.json`：15 个页面 × 1440 / 768 / 390 的 Playwright smoke 报告；截图在 `docs/ui-shots-v3/`。
- `docs/multimodal-api.md`：多模态接口、模型选择、密钥与环境变量备注。

## 修改纪律

- 先读代码和测试，再改；不新增第二个对话控制器。
- 任何新 Harness 行为必须有测试；测试失败不标记完成。
- 不删除/覆盖用户已有文件；新增文件优先放在已有目录的同类位置。
- 只在用户明确要求时扩大范围；架构优化也不等于可以重写全部链路。
