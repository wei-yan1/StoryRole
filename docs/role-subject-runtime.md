# Role Subject Runtime：从提问到行动的角色主链

> **历史设计文档（2026-11-16）**：本文记录“角色主体”从感知到行动、以及连续状态的数据结构来源。默认运行路径已经切换为 `app/agents/storyrole/harness/turn.py` 的 `AgentHarness`（quick/deep 同一 runtime，不同 policy），旧 `TurnKernel` / `kernel.py` 已删除。当前架构、六层职责和验收口径以 `docs/agent-harness-v3-architecture.md` 为准；本文的“legacy 默认”描述不再代表现状。

> 目标不是让模型根据更长的提示词“扮演一下”，而是让同一个角色主体在每轮接收事件、形成理解、决定是否回忆、选择行动，并把行动结果带入下一轮。
>
> 本文从职责和数据流重新设计，不继承旧 Harness 文档里的组件划分。实现必须改变核心数据结构、调用顺序和状态更新；只改提示词不算完成。

## 1. 主体与能力的边界

### 角色主体拥有

- 当前时期中的自我认识：女娲契约给出的身份、目标、恐惧、信念、关系和判断方式。
- 当前线程中的连续状态：正在关注什么、顾虑什么、对来客形成的关系姿态、最近做过什么决定、经历过哪些互动。
- 本轮的情境理解：对方做了什么，这件事与我有什么关系，我为什么在意。
- 本轮的行动决定：坦然回答、追问、安慰、拒绝、保留、沉默或调整此前判断。
- 行动后的经历：我如何理解、如何决定、实际怎样表达，以及这段经历对后续状态的影响。

### 外围能力只提供材料

- 女娲：稳定的“我是谁”，不直接替主体决定本轮行动。
- RoleRAG：有时期、来源和可见性约束的“我可能记得什么”，不控制对话。
- 长期记忆与关系服务：按主体的回忆需求提供补充材料。
- 生成模型：把已经形成的情境理解和行动决定表达出来，不负责从零决定“我是谁”。
- Review：独立检查表达是否像本人；时期和知识可见性只做轻量认知检查。
- Harness：记录阶段产物、执行共享 deadline、停止条件和 checkpoint，不另建第二个对话控制器。

## 2. 旧主链的结构性问题

1. RoleRAG、长期记忆和联网在角色理解之前执行，检索需求由通用问题分类决定，而不是由“我为什么需要回忆”决定。
2. `InteractionState` 主要保存承诺、对方声称的承诺和未完成问句，无法表示角色的当前关注、顾虑、关系姿态与连续决定。
3. `appraise()` 只有单次关键词分类，没有“初步理解 → 回忆 → 修正决定”的两阶段过程。
4. 没有证据时直接 `refuse_fact`，把记忆边界错误地变成行动禁令。
5. 回合结束主要提取承诺句，角色做过什么判断、为什么这样做、是否改变决定都没有进入后续状态。
6. API 只能看到回答和一次 appraisal，看不到感知、回忆需求、决定与状态变化，无法验收主体是否真的连续。

## 3. 新主链

```text
用户话 / 环境事件
        ↓
ROUTE：Laya 分类与 quick/deep 选择；同一 TurnState 和 deadline 已建立
        ↓
PERCEIVE：形成 Perception，确定事件边界
        ↓
INTERPRET：女娲自我认识 + SubjectState + 最近经历
          形成 SubjectUnderstanding 与 MemoryNeed
        ↓
RECALL：只按 MemoryNeed 调用 RoleRAG / 长期记忆 / 关系 / 联网
        ↓
DECIDE：理解 + 回忆结果 + 当前关系
        可选 COGNITION（deep 的 RoleCognition）修正同一 ActionDecision
        形成 ActionDecision；可继续、调整或改变此前决定
        ↓
ASSEMBLE：把自我状态、理解、决定和已取回忆组织成明确输入
        ↓
EXPRESS：生成模型执行 ActionDecision，产生语言或行动
        ↓
REVIEW：主评像不像本人，轻查当前认知是否越界
        ↓
LEARN：把最终事件、理解、决定和实际回答写成 Experience
       更新 SubjectState，影响下一轮 INTERPRET
```

关键约束：

- 先理解需要回忆什么，再检索；不是先把所有材料塞给模型。
- 回忆不到不等于拒绝行动。事实不确定时可以追问、保留或表达不知道，当前互动仍可安慰、拒绝或沉默。
- 决定先于表达。quick 用有界的确定性决策，deep 可以让 RoleCognitionAgent 修正决策，但两者产出同一种 `ActionDecision`。
- A2A 的模型型 fallback 必须惰性执行：远端成功时本地回退零调用；失败时最多执行一次；共享 deadline 耗尽时不再发起新的模型型回退。
- 最终回答而不是草稿进入经历；评审改写过决定表达时，经历必须记录实际说出的内容。

## 4. 一等数据结构

### 4.1 Perception

- `event_kind`：user_message / environment_event。
- `content`：本轮原始事件，不替角色解释。
- `turn`、`thread_id`、`period_id`：事件边界。
- `recent_message_count`：当前可见的近期交互量。

### 4.2 SubjectState（线程级、持续保存）

- `version=2`。
- `turn_count`。
- `current_focus`：我最近在意的事情。
- `concerns`：当前顾虑，来自实际触及的目标、恐惧、信念或关系。
- `relationship_stance`：`familiarity`、`openness`、`posture`，只表示我与当前来客，不写进小说共享图。
- `episodes`：最近若干 `Experience`，用于下一轮主动寻找相关经历。
- `last_action`、`last_emotion`、`review_stats`、`context_snapshot`、时间戳。

旧 `commitments / claimed_commitments / open_loops` 不再进入新状态输出。读取旧 JSON 时只保留仍能兼容的轮次和统计字段；下一次保存写成 v2。旧库不改，影响范围只限 v2 的新互动状态。

### 4.3 Experience

- `turn`、`event`、`interpretation`、`action`、`decision`、`answer`、`emotion`。
- `evidence_ids`：本轮实际参考的回忆来源。
- `salience`、`created_at`。
- 不抽取“承诺句”，不根据一句话擅自改写人格。

### 4.4 SubjectUnderstanding

- `user_move`：对方在做什么。
- `interpretation`：从“我”的立场看，这是什么。
- `current_reality`：来自女娲契约的当前身份与时期。已交接、离开、审判或结束的职责属于现实约束，不能在行动时被改写成“仍在执行”。
- `stakes`：为什么与我的目标、恐惧、信念或关系有关。
- `touches`：被触及的自我认识。
- `emotional_register`：当前情绪承接方式。
- `prior_episode_ids`：从 SubjectState 主动找出的相关经历。
- `memory_needs`：self_history / world_facts / relationships / user_episodes / none。
- `memory_reason`：为什么需要这些回忆。
- `references_previous`：本轮是否引用此前决定/经历；与 user_move 并列，避免把事实追问误变成单独的 follow_up 类型。

### 4.5 ActionDecision

- `action`：answer / probe / comfort / hold_boundary / natural_reply / uncertain。
- `goal`：这次行动要维护或推进什么。
- `stance`：我的立场。
- `relationship_posture`：我如何对待当前来客。
- `change_from_previous`：new / continue / adjust / reverse。解释或确认此前边界属于 continue；reverse 必须由决策层明确给出，不能仅因 action 从 hold_boundary 变成 answer 就机械判定。
- `decision_reason`：依据了哪些当前现实、自我认识、经历和可见回忆。
- `boundaries / must_not`：包含当前现实和画像禁忌；决定必须消费 current_reality，不能只把画像留在生成 prompt 里。
- `uncertainty`：哪些部分没有把握。
- `expression_shape`：只约束表达结构，不预写答案。
- `cognition_backend`：deterministic_quick / local_quick / aliyun_maas / deterministic_fallback / deadline_fallback，区分真实模型认知与回退。

## 5. 各阶段实现职责

### PERCEIVE

保留 Laya 作为事件分类和模式选择的输入信号，但 Laya 不再等同于角色理解。路由前已创建 TurnState；quick/deep 选定后切换同一回合预算，不重启计时。`TurnState` 必须保存 Perception。

### INTERPRET

在 RoleRAG 和长期记忆调用前运行。读取女娲契约和 SubjectState，选出相关经历，产生 MemoryNeed。寒暄和纯情绪承接可以不查小说图；事实、自我经历、关系问题按需查。

### RECALL

把 MemoryNeed 合并进检索计划：

- self_history / world_facts → RoleRAG；deep 可增加旧向量/BM25 原文检索。
- relationships → RoleRAG ego-network + 当前用户关系服务。
- user_episodes → 已有长期记忆服务。
- none → 不为了“每轮都有证据”强行检索。

RECALL 只返回材料和来源，不返回最终行动。

deep 的 EvidenceAnalysis 是辅助证据归纳，不替角色作价值判断：最多使用 4 段证据、每段 1400 字，画像只取决策相关字段，claims 最多 6 条，JSON 输出上限 1400 tokens。这样保留来源核对，同时避免辅助分析重复写成长答案、挤占 RoleCognition 和表达的共享预算。

### DECIDE

回忆完成后再次处理 SubjectUnderstanding，形成 ActionDecision：

- 有回忆支持时可以坦然回答。
- 没有回忆支持时选择 uncertain 或 probe，不再自动 refuse_fact。
- `route=probe` 表示没有直接回答当前关系的记忆；即使取回了无关片段，也不能按“证据数量大于零”升级成 answer。
- 触及核心信念时可以选择拒绝或调整，而不是为了回答而回答。
- deep 的 RoleCognitionAgent 只输出决策字段，不写最终答案。
- 与上一段相关经历比较，明确 continue / adjust / reverse；没有相关经历则为 new。

### ASSEMBLE / EXPRESS

上下文不再包含承诺清单，而是包含：

1. 女娲自我认识；
2. SubjectState 的当前关注、顾虑、关系姿态和相关经历；
3. SubjectUnderstanding；
4. ActionDecision；
5. 已取回忆及来源；
6. 较早历史摘要与轻量认知边界。

生成模型必须执行决定，但可以在语言上自然发挥。决定和状态同时进入结构化上下文与 API，不允许只存在于提示词字符串中。

`probe` 且无直接回忆时，无关原文片段不进入“我的记忆”。正常限制证据条数不算降级；真正超 token 预算时只裁历史和回忆，身份、连续自我、处境、行动决定和轻量约束必须保留，并记录 `budget_trimmed`。

### LEARN

用最终回答创建 Experience，并更新：

- current_focus；
- concerns；
- familiarity / openness / posture；
- last_action / last_emotion；
- episodes；
- review_stats / context_snapshot。

状态更新是纯函数式数据变换：复制旧状态、追加经历、限制长度、返回新状态。避免在生成途中隐式改共享人格。

## 6. TurnState 与 API 可观测性

`TurnState` 新增并持久化：

- `perception`
- `understanding`
- `recall`
- `decision`

阶段记录额外包含 `route` 与 `cognition`，避免模型认知耗时从 decide 的计时中消失；A2A 调用和降级进入 tool/model 记录，总 latency 超过 deadline 必须得到 `deadline_exceeded`，不能仍写成正常通过。

`character_agent.reply()` 保留原返回字段，新增 `subject`：

```json
{
  "perception": {},
  "understanding": {},
  "recall": {"needs": [], "role_evidence_count": 0, "prior_episode_ids": []},
  "decision": {},
  "state": {}
}
```

`appraisal` 暂时保留为 decision 的兼容视图；`interaction_state` 暂时作为 SubjectState 的兼容入口。后续调用方应改读 `subject.state`。

## 7. 实施范围

核心代码必须变化：

- `app/harness/types.py`：SubjectState / Experience / TurnState 新产物。
- `app/harness/appraisal.py`：INTERPRET 与 DECIDE 两阶段，MemoryNeed 和 ActionDecision。
- `app/harness/update.py`：Experience 与 SubjectState 更新，删除承诺提取。
- `app/harness/context.py`：装配持续自我状态、理解和决定，不再装配承诺。
- `app/agents/storyrole/character_agent.py`：调整真实调用顺序和返回数据。
- `app/agents/storyrole/role_cognition_agent.py`：deep 决策输入包含主体状态与理解。
- `app/agents/storyrole/evidence_analyst.py`：有界证据归纳，不替 ActionDecision 作价值判断。
- `app/agents/storyrole/harness/turn.py` 与 `app/harness/checkpoint.py`：阶段名称、action 历史与 checkpoint 对应新主链。
- 测试与真实行为脚本：验证状态确实影响下一轮，而非只检查答案关键词。

不修改：v1 数据库、RoleRAG 的图语义和索引、女娲画像生成算法、API 的 URL 和鉴权方式。

## 8. 验收标准

### 结构验收

- 阶段顺序包含 perceive → interpret → recall → decide → assemble → express → learn。
- INTERPRET 发生在 RoleRAG 检索之前。
- 新 SubjectState 不含 commitments / claimed_commitments / open_loops。
- 回合结束产生 Experience；下一轮 INTERPRET 能选出相关经历并影响 decision。
- greeting / emotion 可以不触发小说检索；fact / relation 能产生明确 MemoryNeed。
- 无证据时不会自动变成拒答。

### 行为验收

- 同一施压事件后追问“刚才为什么拒绝”，角色能接着自己的上一决定解释，而不是重新表演。
- 情绪倾诉先承接，不因无小说证据拒答。
- 晚期罗辑根据当前身份行动，而不是只背“面壁者”标签。
- 新状态确实跨存储 round-trip，并在线程之间隔离。
- 保留至少一组主链调整前后的同题结果，区分“结构已改变”和“回答风格偶发变化”。

### 回归验收

- 全量 `pytest tests/rolerag -q`。
- 真实 v2 HTTP 行为与多轮主体状态检查。
- profile/period alignment、Harness gate、回归 state 全部通过。
- 报告模型调用次数和降级，不能用“测试多”代替主体性证据。

## 9. 批判性自审

1. **会不会只是把 appraisal 换个名字？** 防止方式：必须有检索前理解、检索后决定、回合后经历更新三个不同产物，且下一阶段实际消费上一阶段数据。
2. **确定性 quick 决策是否仍然粗糙？** 是，但它只负责低成本的行动选择，不再伪装成完整人格理解；deep 可以修正同一 ActionDecision。后续可替换决策器而不改主链。
3. **episodes 是否只是另一种聊天记录？** 不是。它包含当时的理解、决定、实际行动和证据来源，并参与下一轮相关经历选择与 continue/adjust/reverse 判断。
4. **删除承诺状态会不会损失连续性？** 会有意放弃“承诺句匹配”这种伪连续性；真正需要保留的是当时的选择、关系和处境。旧字段不再进入新生成上下文。
5. **记忆需求判断是否可能漏检？** 会。deep 保留 Laya 原始 needs 的并集；quick 只对高置信寒暄/纯情绪否决不必要的世界检索，一旦事件触及自我经历仍恢复回忆需求。
6. **是否引入第二个对话控制器？** 不引入。SubjectState/Understanding/Decision 是数据结构，character_agent 仍是唯一对话出口，HarnessKernel 只记录阶段。
7. **测试分数能否证明更像？** 不能。结构测试只证明数据流成立；主体性必须由跨轮决定连续、不同处境下的行动差异和真实前后对照共同支持。
8. **预算和回退是否只是装饰？** 不能允许 `fallback=await model()` 在 A2A 前被 eager 执行，也不能允许 120 秒预算跑 250 秒仍记为正常通过。调度器必须用剩余时间限制远端与本地回退，超时必须留下明确停止原因。
