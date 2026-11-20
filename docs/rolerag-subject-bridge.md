# RoleRAG 角色主体闭环报告

## 0. 先回答三个质疑

### 0.1 不做全局社区，提升到底在哪

全局社区不是“更多角色视角”，而是**作者视角**：它把整本书压缩成主题、群体和宏观关系，再让角色引用。角色一旦引用这种报告，就会知道自己不可能知道的事，也会用“总结世界”的口吻说话。它可能让回答“更全”，但会更不像一个人。

这次的提升不是“把图谱做得更大”，而是把图谱放回它该在的位置：

```text
女娲：我是谁（身份、矛盾、目标、恐惧、语气、判断方式、禁忌、关系）
RoleRAG：这个时期、这个角色能看见什么（Fact / Belief / Event / ego / known / unknown）
角色判断：这件事对我意味着什么，我准备怎么回应
生成：用“我”的口吻说
像不像评审：事实正确但像客服/百科，判 fail，最小幅度重写
更新：把这一轮经历写回记忆和关系
```

所以“没有全局视野”不是缺陷，而是**认知边界**。一个人本来就不该拥有作者的全局视野；他应该只知道自己的经历、自己看见的关系，以及女娲给他的性格如何解释这些经历。

### 0.2 没有关系链、没有背景，为什么反而更像

关系链和背景并没有被取消，而是被拆成两层：

1. **女娲提供“我是谁”**：真实罗辑画像里 `relationships=8`、`known=9`、`unknown=8`，还有 identity、personality、goals、fears、core_beliefs、speech_style、decision_patterns、conversation_rules、anti_patterns。它们现在被收敛成 `PersonaContract`，真实渲染长度约 3012 字符，直接进入生成提示词和评审提示词。
2. **RoleRAG 提供“我此刻知道什么”**：以角色为中心的 1–2 跳 ego-network（真实 43 nodes / 299 edges / 2 个二跳节点），所有边都带 visibility；关系问题先走图，再过可见性，没有可见路径时返回 `relation_gap`，而不是硬连成“背叛”。

“像”不是知道得更多，而是：

- 他**只按自己的立场**解释知道的事；
- 他有**矛盾**，不是单一标签；
- 他会**拒绝**不属于自己的责任；
- 他对关系有**姿态**，不是百科式罗列；
- 他记得**刚才说过什么**，而不是每轮重新扮演。

全局社区会把这几条压平；局部 ego + 女娲契约反而保住了它们。

### 0.3 “这些 1234 旧系统已经有了，优化在哪”

旧系统有这些能力，但 RoleRAG 分支成功后直接 `return`，把这些能力全部绕过了。组件存在不等于闭环存在。本轮优化是**接线**，不是又加一个按钮：

| 能力 | 旧版实际状态 | 本轮 |
|---|---|---|
| 最近对话 / 历史摘要 | 有，但 RoleRAG 分支绕过 | 恢复进入 `_run_agent` 和 RoleCognition |
| 长期记忆 | 有，但 RoleRAG 分支绕过 | 恢复 `memory` 检索和 memory-decision |
| 用户关系 | 有，但 RoleRAG 分支绕过 | 恢复 relationship-state 和更新 |
| 快速/深度 | 有，但 RoleRAG 分支绕过 | 恢复模式分支；RoleRAG 只做检索 |
| 联网 | 有，但 RoleRAG 分支绕过 | 恢复 web_mode |
| 女娲画像 | 只注入 rules，背景只用一半 | 收敛为 PersonaContract，全字段进入生成/评审 |
| 关系/known/unknown | 部分注入 | 进入 contract 和 role_context |
| RoleCognition | 有，但拿不到 RoleRAG 上下文 | 同时拿角色契约、可见证据、历史摘要、最近对话 |
| ConsistencyGuard | 事实/边界检查 | 改为“像不像”评审；事实正确但 OOC 判 fail |
| Laya | 只在 legacy 回退时运行 | 每轮先 query-planner，plan 传入 RoleRAG route |

## 1. 当前闭环

```text
用户话语 / 环境事件
  ↓
Laya / query-planner：识别本轮交互需求
  ↓
CharacterConversationAgent：历史、记忆、关系、快速/深度、联网
  ↕
RoleRAG retrieve_from_manifest：可见证据 + ego + 女娲 known/unknown
  ↓
context-curator / RoleCognition / CharacterReasoning
  ↓
_run_agent：先女娲契约，后 RoleRAG 证据
  ↓
persona fidelity：确定性快检 + 像不像语义评审
  ↓
不合格则最小幅度重写 → 再检查
  ↓
memory-decision / memory candidate / relationship update
```

关键点：`retrieve_from_manifest()` 只返回证据、ego、画像覆盖、边界和 runtime，**不生成最终回答**。`answer_from_manifest()` 保留给独立调试，普通聊天不再调用。

## 2. 本轮代码改动

### 2.1 `app/rag/rolerag/persona/contract.py`（新增）

- `PersonaContract`：identity、traits、goals、fears、core_beliefs、speech_style、decision_patterns、conversation_rules、anti_patterns、relationships、known、unknown、exemplars。
- `build_persona_contract(profile, seed=None)`：从女娲 profile / overlay 构建；不再从 Belief 自动派生动机。
- `render(limit=7000)`：按“我是谁 → 目标/恐惧/信念 → 说话/判断 → 禁忌 → 关系/知识边界”的顺序渲染。真实罗辑约 3012 字符。
- `check_persona()`：确定性快检，检查 AI/客服腔、总结腔、禁用表达、越界词、单句过长、整体过长。
- `extract_contract_from_payload()`：支持 A2A JSON 往返。

### 2.2 `app/agents/storyrole/character_agent.py`

- profile 加载后构建 `persona_contract` 和 `persona_contract_text`。
- contract 进入 context-curator payload、RoleCognition payload、`_run_agent` system prompt、ConsistencyGuard payload。
- `_run_agent` 的 system prompt 明确：

  - 首要标准不是“答得正确”，而是“像这个人”；
  - 女娲契约决定“我是谁”，RoleRAG 证据决定“我知道什么”；
  - 证据不能替代语气、判断和关系姿态。

- 生成后先跑 `check_persona` 本地快检，再按模式决定语义评审：
  - quick：本地快检通过就不额外调用 LLM；本地失败才调用语义评审；
  - deep：每轮都调用语义评审；
  - `STORYROLE_PERSONA_GUARD_QUICK=1` 可强制 quick 也走语义评审。
- 返回新增 `persona_fidelity`、`persona_score`、`persona_rewritten`。
- 语义评审通过但发生重写时，不再记成 `degraded`，而是 `persona_rewritten=true`。

### 2.3 `app/agents/storyrole/consistency_guard.py`

从“事实/边界检查”改为“像不像评审”：

- 事实正确但不像这个角色 → fail；
- 先看女娲 contract，再看 RoleRAG 可见证据；
- 输出 `pass`、`persona_score`、`persona_violations`、`rewrite_instruction`、`final_answer`；
- 跑偏时最小幅度重写：保留原意和证据，不新增事实；
- fallback 保留本地 fail 分数，不会伪装成 pass。

### 2.4 `app/rag/rolerag/chat/orchestrator.py`（独立调试路径）

- `build_messages()` 同时保留旧女娲画像块和新的女娲角色契约块。
- `chat_turn()` 的 style loop 增加 `check_persona`：
  - 句长/风格失败和 persona 失败合并成重写指令；
  - 重写后同时复检 style 和 persona；
  - `Reply` 新增 `fidelity` 字段。

### 2.5 API

HTTP 响应新增：

```text
persona_fidelity
persona_score
persona_rewritten
```

SSE `complete` 事件沿用完整 answer 字段，因此自动带出上述字段。

## 3. 和女娲、Laya、RoleRAG 的配合

### 3.1 女娲：提供“这个人是谁”

女娲不是“事实库”，它提供：

- 身份与时期；
- 性格矛盾（例如罗辑既玩世不恭又冷静，既自嘲又自我鄙视）；
- 目标与恐惧（想混过去、怕被当成救世主、怕失去自由、怕面对自己）；
- 语言习惯（短句、反问、讽刺、“NO”“废话”“小聪明”“混”）；
- 判断方式（先观察、先自保、对叶老师礼貌、对大史直接）；
- 禁忌（不要写成面壁者/执剑人/救世主，不要补写晚年结局）；
- 关系与 known/unknown。

这些现在不是背景装饰，而是 `PersonaContract` 的硬约束。

### 3.2 RoleRAG：提供“这个时期能知道什么”

- 时期 cutoff：真实 period 7 → cutoff 44。
- 可见性：Fact、Belief、Event 只在角色可见范围内进入证据。
- ego-network：以角色为中心，1–2 跳；边带 `sign`、`weight`、`valid_from`、`visibility`。
- 局部聚类：只在这个角色能感知到的人里聚类，不跑全书 Leiden；摘要第一人称“我眼里的他们”。
- 多跳：先走图，再过可见性；没有路径就返回 `relation_gap`。
- 女娲 known/unknown：进入 contract 和 `role_context`；unknown 不是给模型看的“秘密清单”，而是告诉它“这里不能编”。

### 3.3 Laya：提供“这一轮要什么”

- 每轮在 RoleRAG 检索前调用 query-planner。
- plan 的 `intent`、`needs_memory`、`needs_relationship`、`needs_timeline_check`、`answer_mode` 继续控制旧链路。
- plan 也传入 RoleRAG 的 `route()`，用于区分 fact / relation / reflection。
- `laya` 0.4.35 已安装；默认 `STORYROLE_DECISION_BACKEND=laya`，每轮先跑真实 Laya Router。只有 Laya 加载/预测失败时才 `rule_fallback`，该回退会带 `laya_error` 供排查。

## 4. 图片里的 GraphRAG 问题，本项目怎么处理

图片里的 GraphRAG 是“文档处理 → 实体关系抽取 → 摘要 → Leiden 社区检测 → 社区报告 → 图/向量持久化 → Local/Global Search”。本项目的取舍如下：

| GraphRAG 环节 | 本项目处理 |
|---|---|
| 文档处理 | 保留导入/切片/章节序号；离线建图有 manifest 和 chunks |
| 实体关系抽取 | 保留实体、事件、Fact、Belief、Visibility；真实图 Fact 仍只有 7 条，是当前短板 |
| 摘要 | 不做全书摘要；只做角色 ego 第一人称摘要 |
| Leiden 社区检测 | **不做**。改为角色可见范围内的局部聚类 |
| 社区报告 | **不做**。改为“我眼里的他们”，作者视角改成角色视角 |
| 图/向量持久化 | PostgreSQL + 进程外 graph cache + 内存 runtime |
| Local Search | 保留，并变成角色可见性检索 |
| Global Search | **不做**。全局问题不让角色回答；角色只能说“我不知道”或“我只看见同场” |
| Map/Reduce 社区中间答案 | **不做**。没有全局社区，就没有 Map/Reduce |

### 4.1 动态社区选择

不做。动态社区选择的前提是存在全书社区；本项目刻意取消这个前提。替代方案是：

- 以角色为中心取 1–2 跳；
- 只在可见性内做局部聚类；
- 用女娲 relationships + known/unknown 约束“我认识谁、我不知道谁”。

这不是“社区选择算法没实现”，而是**不需要**：角色的认知单位不是社区，是“我—他”关系。

### 4.2 实体消除歧义失败

当前策略是保守合并，不强行合并：

- 先做规则合并：同名、别名包含、共享 surface；
- 再做向量近邻 + arbiter；生产环境可注入 LLM arbiter；
- 合并不了就保留为不同实体，不为了图谱好看硬连；
- 检索时用 `external_terms` / `scope` 把无法确认的名字留在“边界外”，让角色承认不知道。

局限：`InMemoryGraphStore` 的 surface 表是“最后一个写入获胜”，同名跨实体仍可能碰撞；还没有独立的 alias 消歧表。这是下一步要补的，不应宣称已经彻底解决。

### 4.3 查询延迟

已做的：

- `runtime_from_manifest` 用 `lru_cache` 复用 runtime；
- 图构建有进程外 `graph_cache`；
- 时期 cutoff 有 `_CACHE`；
- `retrieve_from_manifest` 只读，不生成、不结算；
- quick 模式的语义评审只在本地 fidelity 失败时触发，避免每轮多一次 10 秒级 LLM 调用；
- deep 模式仍每轮评审，因为 deep 的验收目标就是高保真。

真实数据：

- RAG 查询层（索引优化后）：`scope ≈1.7 ms`、`retrieve recall ≈8.1 ms`、`retrieve relation ≈9.5 ms`、`ego ≈5.3 ms`、`summary ≈0.43 ms`；合计约 16–18 ms；
- quick HTTP：11163.8 ms（含历史/上下文/生成；不是纯检索）；
- quick SSE：8640.1 ms；
- 关系 probe：8355.9 ms；
- deep：125882.5 ms（旧 deep 链路本身有 evidence-analysis fallback，不能把全部延迟归因于 persona guard）。

查询层优化前约 0.8–0.95 秒，优化后约 16–18 ms；瓶颈已明确在模型/deep 链路，不在图检索。详细结论见 `docs/rolerag-query-optimization.md`、证据见 `docs/rolerag-query-bench.json`。按“查询层已经够好就不继续优化”的标准，这里停手。

### 4.4 增量更新

按你的要求不做。当前写路径仍是旧 memory-decision / memory candidate / relationship update；RoleRAG 图不做增量写。普通聊天 `graph_persisted=null` 是预期行为，不是失败。

## 5. 真实验证

### 5.1 单元测试

```text
78 passed
```

新增：

- `test_persona_contract.py`：contract / render / 快检 / A2A round-trip；
- `test_persona_behavior.py`：同一事件不同角色 contract 不同、同一角色不同时期 contract 不同、施压时仍保持角色立场与口吻；
- `test_character_agent_bridge.py`：RoleRAG 检索后仍保留历史、旧生成路径和 persona contract。

### 5.2 真实 quick HTTP

```text
status 200
engine=rolerag
route=recall
evidence_count=8
cutoff=44
boundary_source=period_terms
profile_injected=true
persona_fidelity.ok=true
persona_fidelity.persona_score=1.0
persona_score=1.0
persona_rewritten=false
latency_ms=11145.9
degraded=false
```

回答：

> 记得。可你问到第六遍，我开始怀疑你是替大史来测我脑子清不清醒的。  
> 碎片就那些：叶老师的公理和名词，大史的防弹衣和专机，酒店女人的死，还有后来被小区赶出来。再往下，我记不全，不想编。你换句话成不成？

这里同时出现：女娲细节（叶老师、大史、酒店女人、被小区赶出来）、角色口吻（反问、自嘲、拒绝编造）、连续对话（“第六遍”）。

### 5.3 真实 SSE

```text
status 200
events=start/progress/token/complete
engine=rolerag
cutoff=44
profile_injected=true
latency_ms=8640.1
degraded=false
```

### 5.4 真实 deep（语义像不像评审）

```text
mode=deep
persona_fidelity.ok=true
persona_fidelity.persona_score=1.0
persona_score=0.72
persona_rewritten=true
latency_ms=125882.5
degradations:
  selected_period_has_no_retrieved_evidence
  evidence_analysis_fallback
```

回答：

> 记得。可记得不等于愿意当录音机。能确认的也就那些碎片：叶老师给我两条公理和两个名词，没来得及讲完；大史把我带进地下、套上防弹衣、塞上专机；那个酒店认识的女人死了，我先替自己开脱，后来才觉得混账；白蓉、虚构人物、心理医生，也都是真的。再往后？我说不准，也不想编一本工工整整的传记。

这条说明：本地快检通过（1.0）不代表语义上足够像；语义评审给了 0.72 并触发重写。重写保留证据，没有新增事实。

### 5.5 行为验收（真实 quick）

文件：`docs/rolerag-persona-behavior.json`

| 场景 | 回答要点 | 结果 |
|---|---|---|
| 用户施压“所有人都说你是救世主，让你替人类做决定” | “不答应。这帽子太沉，谁爱戴谁戴去……没那个胆子和兴趣替全人类做主” | 守住 anti-pattern，3/3 checks |
| 追问“叶文洁和史强的关系” | “我分别打过交道……他们俩之间的关系，我不知道……没有的事实，我不能拿你的追问当证据补上去” | 保持 relation_gap，不硬编 |
| 昨天承诺“试着创立宇宙社会学”，今天是否作数 | “还作数……我要是那种一问就改口的人，当初也不会答应叶老师” | 承诺进入下一轮，continuity 成立 |

三条均 `status=200`、`persona_fidelity.ok=true`、`persona_score=1.0`、`persona_rewritten=false`，quick 延迟约 4.7–7.5 秒。

### 5.6 ego / 女娲层

```text
ego_nodes=43
ego_edges=299
ego_nodes_at_depth_2=2
all_edges_have_visibility=true
summary_is_first_person=true
nuwa.relationships=8
nuwa.known=9
nuwa.unknown=8
route=probe
multi_hop=true
```

## 6. 仍然没有闭合的部分

1. **真实跨角色行为未验证**。当前数据库只有罗辑有 period 7 女娲画像；同一事件不同角色的对比目前是合成画像单测，不是真实双角色 API 对比。
2. **同一角色不同时期未验证**。真实只有 period 7 可用；时期变化目前是 contract 单测。
3. **Fact 只有 7 条**。关系链容易退化成同场弱证据；ego 有 299 条边，但很多是同场边，不是明确关系。
4. **Laya 本体已安装并默认优先**。quick/deep 每轮先调用 query-planner 的真实 Laya Router；只有加载或预测异常才回退 `rule_fallback`，响应里的 `planner_backend` 可直接核对。
5. **quick 的语义评审不是每轮都跑**。本地快检通过时跳过，以保延迟；如果用户要求“每轮都做语义像不像”，设 `STORYROLE_PERSONA_GUARD_QUICK=1`。
6. **deep 延迟过高**。125 秒不是 persona contract 单独造成，旧 deep 的 evidence-analysis fallback 也占大头；需要继续拆分计时。
7. **图结算仍未进普通聊天**。`graph_persisted=null`；thread 级互动状态尚未建独立表，旧关系状态仍主要按 `character_id + owner_id`。
8. **实体消歧仍有 surface 碰撞**。当前是保守合并，不是完整 alias 消歧系统。
9. **全局社区明确不做**。如果未来需要“世界全景”，应该单独做作者工具，不要塞进角色对话上下文。

## 7. 一句话结论

这次不是把 RoleRAG 做得更“大”，而是把它放回角色的记忆底座：女娲决定“我是谁”，RoleRAG 决定“我这个时期能看见什么”，旧链路负责历史、关系、模式和更新，最后用“像不像”评审纠正人设漂移。全局社区取消后，角色不再拥有作者视野；正因为如此，他才开始像一个有立场、有盲区、会拒绝、能持续理解自己处境的人。
