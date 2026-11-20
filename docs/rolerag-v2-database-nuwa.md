# v2 独立数据库与女娲 T6 重建

## 决策

- 旧库 `three_body_agent` **保留，不修改**。
- v2 使用独立库 `three_body_agent_v2`。
- v2 是 v2 自己的数据面；旧库只作为基线/回滚，不参与 v2 运行。
- 默认 `.env` 仍指向旧库。v2 运行必须显式设置 `POSTGRES_DATABASE=three_body_agent_v2`，避免误写旧库。

## 已完成

### 1. v2 数据库

- 新建 `three_body_agent_v2`，从旧库只读克隆一份 48 MB 基线。
- 旧库克隆前后 profile 数均为 23；旧库 profile 22 仍是 40 条“序 章”证据，未被修改。
- v2 的旧 period 7 画像（id 15 / version 15、id 22 / version 22、id 24 / version 23 的 heuristic）已标记 `superseded`；id 25 / version 24 是 period 7 唯一的 `ready` 画像。

### 2. v2 period 7 数据

`storyrole_character_periods.id=7` 在 v2 中改为：

- `chapter_start = chapter_end = 第五十三章 三体III·死神永生 第161节`
- `keywords = ["晚年","老人","威慑","执剑人","三体III"]`
- `evidence_ids`：38 条 `三体III·死神永生` 中罗辑出现的原文 chunk
- `confidence = 1.0`
- `rationale = v2 晚期证据窗：三体III 死神永生中罗辑晚年出现段落；旧库未修改`

验证：

- `evidence_for_period(records, period)` 选中 **38 条**，章节全部是 `三体III·死神永生`。
- `resolve_period_cutoff()` 返回 `cutoff=53`、`boundary_source=explicit_bounds`、`confidence=1.0`；不再是 `44 / period_terms / 0.75`。

### 3. 女娲重跑

第一次重跑得到 `profile 23 / heuristic`，当时模型调用未稳定使用项目指定的阿里云 MaaS workspace 配置，失败后兜底成空画像。

现在语言模型路由统一为：阿里云 MaaS 的 `OPENAI_*` 优先、`DASHSCOPE_*` 回退；`DEEPSEEK_*` 仅作 DeepSeek 官方端点回滚，不得按 `deepseek-` 模型前缀自动切换供应商。修复后：

- `profile_id=25`，`version=24`，`status=ready`
- `model=deepseek-v4.1-flash-1017`
- profile 证据 38 条，全部在 `三体III·死神永生`
- `identity`：黑暗森林威慑的执剑人、第一任引力波宇宙广播系统最高控制权掌握者、新时期晚年时期百岁执剑人、交接给程心后被审判等
- `get_persona_profile_for_period(character_id=1, owner_id=2, period_id=7)` 返回 profile 24

### 4. 真实验收：v2 完整十项

`scripts/e2e_ten_v2.py` 在 v2 库上跑完整六问 + 三行为 + 一 smoke（共十项），结果写入 `docs/rolerag-ten-questions-v2.md` / `.json`。

结果（2026-11-16 13:07–13:22，最终复跑）：

- HTTP：**10/10 200**
- 全部 `stop_reason=review_accepted`
- 全部 `profile_version=24`
- 全部 `cutoff=53` / `boundary_source=explicit_bounds`
- 六问人格分：q1 0.76、q2 0.92、q3 1.0、q4 0.88、q5 1.0、q6 0.88（均值 0.907）
- 行为：b1/b2/b3 3/3；smoke s1 通过
- 降级：**全部 10 项 `degradations=[]`**；证据分析用最强 6 条、A2A 超时 90 秒，角色判断超时 45 秒
- 这份报告回答的是“v2 库 + T6 profile 24 下，十项链路是否跑通”；它不回答“每道题是否适合 T6”。q1/q2/q3/q4/q6 本质是早期题，适合做时期错位测试；T6 专用题见第 5 节。

### 5. T6 专用探针

问题：

> 你已经一百多岁了，执剑人的位置也交出去很久了。现在回头看，你最想对当年那个站在开关前的自己说什么？

首轮探针结果（旧线程，已被后续复跑覆盖为历史记录）：

- HTTP 200，272 字
- `profile_version=24`
- `cutoff=53`
- `boundary_source=explicit_bounds`
- `evidence_count=12`
- `persona_score=0.95`
- `harness_stop_reason=review_accepted`
- 回答出现“须发全白、黑色中山装、右手握着开关、双手递给程心、抬起身时不要扶地、向四光年外的对手鞠躬、电梯口罪名”等晚年/交接细节

2026-11-16 12:36 的新鲜线程复跑（`thread 105`，单轮，证据分析超时放宽到 60s 后）：

- HTTP 200，219 字
- `profile_version=24`、`cutoff=53`、`explicit_bounds`
- `evidence_count=6`、`persona_score=0.96`
- `harness_stop_reason=review_accepted`
- 降级：无
- 回答出现“白大厅、像坟墓一样简洁、盘坐正中、头发胡子纯白、黑色中山装、最后十分钟、起身双手不碰地、把开关交出去、向白墙鞠躬、四光年外有人在看、五十四年、别指望谁会谢你”等晚年/交接细节

2026-11-16 13:19 的最终新鲜线程复跑（`thread 139`，单轮；证据分析 90s、角色判断 45s）：

- HTTP 200，265 字
- `profile_version=24`、`cutoff=53`、`explicit_bounds`
- `evidence_count=12`、`persona_score=0.9`
- `harness_stop_reason=review_accepted`
- 降级：**无**
- 回答出现“最后十分钟、白色大厅、盘腿坐在正中、右手握着开关、四个按钮、按顺序、五十四年、向白墙鞠躬、四光年外、起身两手不碰地、双手把开关交给程心、没有人说过一句感谢”等晚年/交接细节

注意：`probe_t6_v2.py` 已改为每次生成唯一 `thread_name`（`t6probe-<timestamp>`）。旧的固定线程名会在第二轮带上前一轮承诺，导致探针不再是单轮 T6，不能用于验收。`thread 104` 的 148 字复跑仍带 `evidence_analysis_fallback`；放宽证据分析超时后 `thread 105` 的降级消失，说明此前主要原因是证据模型分析超过了 45s；最终 `thread 139` 在 90s + 12 条证据下仍无降级，说明 T6 单轮链路已稳定。

对比：同一 v2 库跑旧 q6（“假设你现在就是执剑人”）得到 79 字、12 证据、persona 0.88；它通过评审，但没有明显晚年感。说明 **period/profile/cutoff 已对齐，但题目本身仍需 T6 专用矩阵**。

### 6. fail-closed 与对齐闸门

- `app/agents/storyrole/period_agent.py` 的 `evidence_for_period()` 改为 fail-closed：
  - 有 `evidence_ids` 时只按 IDs 选择；IDs 全部失效抛出 `PeriodEvidenceUnavailable`，不静默回退到角色前 40 条。
  - 有 keywords/bounds 时按窗口选择。
  - 都没有时，只有“全时期/全书时期/全书”允许 `records[:40]`；其他命名时期直接抛出。
- `app/storage/storyrole_alignment.py` 的 `check_profile_period_alignment()` 检查 profile period 与 period evidence 窗口 coverage；命名 period 无证据窗口直接失败。
- `scripts/check_profile_alignment.py` 实测 v2：`ok=true`、profile 25 / version 24 / 38 条证据 / period 38 条 / overlap 38 / coverage 1.0。
- `scripts/harness_gate.py` 在 `STORYROLE_ALIGNMENT_CHECK=1` 时把上述检查并入 gate；v2 gate 为 `passed=true`、pytest 100 passed、behavior 3/3、alignment ok。

### 7. 时期字段进入契约与评审

- `PersonaContract` 新增 `period_name / period_stage`，并写入 render/as_dict；`build_persona_contract()` 从 profile 读取，`extract_contract_from_payload()` 回填。
- `ReviewPacket` 新增 `period_name / period_stage`，render 输出“当前时期”；当前评审主目标是“像不像角色”，时期与知识可见性合并为轻量认知检查，早期/晚期不再单列重型评审。
- `character_agent.py` 在 `profile_load` 加载 period，构造 contract 与 review packet 时注入时期。
- v2 profile 24 的 JSON 已补 `period_stage="T6"`；`scripts/bootstrap_v2_period7.py` 重新生成时也会带 `period_stage="T6"`。
- 深审次数最多 3 次，证据分析只取最强 6 条（A2A 90 秒），角色判断 45 秒，避免大上下文超时；女娲、证据分析、角色判断与 RoleRAG 统一经阿里云 MaaS，`OPENAI_*` 优先、`DASHSCOPE_*` 回退，`DEEPSEEK_*` 仅作官方端点回滚。

## 如何运行 v2

推荐用封装脚本，避免每开一个终端都忘记切库：

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
.\scripts\run_v2.ps1                       # API
.\scripts\run_v2.ps1 scripts\harness_gate.py
.\scripts\run_v2.ps1 scripts\e2e_ten_v2.py
.\scripts\run_v2.ps1 -m pytest tests\rolerag -q
```

不要在 v2 进程里依赖根 `.env` 的 `POSTGRES_DATABASE`；它仍指向旧库。`run_v2.ps1` 会显式设置 `POSTGRES_DATABASE=three_body_agent_v2` 和 `STORYROLE_ALIGNMENT_CHECK=1`。

## 验证

- `pytest tests\rolerag -q`：**100 passed**
- v2 gate：`passed=true`、`pytest=100 passed in 0.70s`、behavior 3/3、profile alignment ok
- v2 十项：**10/10 HTTP 200，全部 review_accepted，全部 `degradations=[]`**
- T6 探针：`thread 139`，265 字、`persona_score=0.9`、12 证据、无降级
- 旧库：profile 22 仍为 `ready`、40 条“序 章”证据，未被修改
- v2：profile 25/version 24 为唯一 ready 的 period 7 画像，T6，38 条晚期证据，cutoff 53

## 仍未完成 / 边界

- `evidence_analysis_fallback` 已在最终十项和 T6 探针中消失；但它不是结构性保证，而是“最强 6 条证据 + 90 秒 A2A 超时”下的实测结果。若模型端点变慢，仍可能回退，需要继续观测。
- `storyrole_character_periods` 没有 `timeline_stage` 列；profile 25 的 T6 是 profile JSON 字段，不是 period 表自动派生。
- 十项中的 q1/q2/q3/q4/q6 不是 T6 题，不能拿它们证明“晚年画像像不像”；T6 需要独立题矩阵（交接后、百岁、被审判、威慑记忆）。
- `profile.period_name / profile.period_stage / evidence chapter` 的严格三方一致 gate 目前主要靠 period evidence ID coverage；还没有逐条校验章节标题。
- v2 的 38 条晚期证据来自 imported chunks 的“三体III·死神永生”罗辑记录，不是 `novel_chunks` 的 27 条 `timeline_stage=T6` 精确证据；若要求严格 T6 stage，需要进一步映射/重建。
- 旧库 profile 22 的 `ready` 状态是保留的历史基线，不作为 v2 数据修正对象。

