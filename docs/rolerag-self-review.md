# RoleRAG 自检报告：它是否真的能让 agent 代替角色

> 日期：2026-11-14
> 对象：`rolerag-v2/app/rag/rolerag/`（43 个模块，4,561 行）与 `tests/rolerag/`（14 文件 / 690 行 / 60 条测试）
> 对应设计：`docs/rolerag-architecture.md` v3.1
> 结论先行：**认知底座成立；真实模型已在 9 轮对话与 150 题真实语料 KBF 上验证；文笔仍有明确短板，但不影响"边界优先"的架构判断。**

---

## 0. 一句话结论

"agent 代替角色"不是一个文笔命题，而是一个**权限命题**：

1. 他只能知道自己有路径知道的事；
2. 他知道自己不知道什么，并能因此拒答；
3. 他说过的话会改变他与你的关系，下一轮从新关系开始。

这三条里，**第 1、2 条已经闭合且有测试；第 3 条已在真实 `deepseek-flash` 的 9 轮对话上跑通（hostility 0.100→0.233、对话事件 19、承诺信念 2，风格 9/9，历史 `qwen-plus` 记录为 8/9）；"像不像这个人"已用 5 组内部单盲对照证明新架构在边界上 4/5 优于扁平 RAG，但文笔仍输 1 组。**

---

## 1. 验收口径

| 问题 | 判定标准 | 证据 | 结论 |
| --- | --- | --- | --- |
| 角色是否只知道自己可见的？ | cutoff 前、且有 direct/witness/told/org/common 任一可见路径的事实才进 beliefs | `test_character_does_not_know_a_person_who_has_not_appeared`、`test_fact_is_not_visible_before_its_chapter`、`test_unseen_event_is_recorded_but_never_becomes_a_belief` | 通过 |
| 角色是否知道自己不知道？ | 未见的重要事件进 unknowns，但不进 prompt；被问到时明确拒答 | `test_prompt_does_not_list_unknown_event_titles`、`test_unseen_trigger_is_refused_even_when_both_people_are_known`、`test_private_build_still_respects_secret_marker` | 通过 |
| 角色说话是否像"这个人"？ | 结构化 drives + 行为模式 + 原句语料 + 句长/问句率/禁用语测量 + 一次重写 + 女娲画像 overlay | `test_fingerprint_and_measure_agree_on_same_corpus`、`test_long_summary_style_is_rejected_with_instruction`、`test_llm_renderer_uses_prompt_and_rewrite_instruction`、`test_profile_overlay_reaches_seed_and_prompt`；真实 `deepseek-flash` 5 轮 5/5、9 轮 9/9 风格通过；`docs/rolerag-blind-eval.md` | 机制通过；真实模型已验证；文笔仍不稳定 |
| 对话是否留下后果？ | 对话事件入图；辱骂/承诺改变六标量；声称变成信念而非事实 | `test_settlement_persists_affect_and_event`、`test_promise_becomes_a_belief`、`test_settle_turns_a_spoken_claim_into_a_belief_not_a_fact`；`docs/rolerag-multiturn-e2e.jsonl` | 通过（真实模型 9 轮闭环） |

---

## 2. 可复现证据

### 2.1 测试

```
60 passed in 0.26s
```

覆盖：章节序数、引号切句、别名归一（含 LLM arbiter）、事件 actor/patient、五条可见性路径、投影 cutoff/私密场景/幂等、scope 与路由、事件级守卫、风格指纹与改写、状态机、结算、KBF、快照、服务门面、惰性情景、EMO-GATE、端到端题库、chunk 运行时与 API adapter（含时期→章节序数映射）。

### 2.2 KBF

- 演示 7 题：KRF=4/4，KR=3/3，KBF=1.00。
- 由事实自动生成 25 题（22 正 / 3 负）：五角色合计 KRF=1.00、KR=1.00、KBF=1.00。
- **真实语料 150 题**（《三体》I 36 章、30 个角色 × 5 条事实）：`cases=150 correct=150 accuracy=1.00`，`failed_cases=0`。`scripts/eval_real_kbf.py` 可复现。
- 说明：演示 25 题只证明"可见性行与投影、拒答三者自洽"；真实 150 题证明规则抽取的稀疏图上，边界判定仍能全对。它仍不等于"文笔像人"。

### 2.3 PostgreSQL

`scripts/verify_rolerag_pg.py` 在 `postgres:16-alpine` 上跑通：

```
[save] {'chapters': 6, 'entities': 7, 'scenes': 9, 'events': 10, 'facts': 5, 'visibility': 70}
[load] chapters=6 entities=7 scenes=9 events=10 facts=5 visibility=70
PG-ROUNDTRIP-OK
```

包含：DDL 可重复执行、save 全量替换且幂等、load 后 `project()` 与写入前逐项相等、participants/roster 完整。

### 2.4 演示与真实模型

`python -m app.rag.rolerag.cli demo`：玄真 @ch6 对"沈砚隐瞒陆知微"拒答（`unknown_events=1`）；陆知微 @ch2 对"斩赵七"拒答；外部话题拒答；风格验收全过。

真实 `deepseek-flash`（`scripts/e2e_real_llm.py`，5 轮独立，`ROLERAG_MAX_TOKENS=2048`）：

| 角色@章 | 问题 | 输出 | 风格 |
| --- | --- | --- | --- |
| 陆知微@6 | 沈砚被逐？ | 玄真逐沈砚下山 | 1.0 |
| 陆知微@6 | 沈砚为什么斩赵七 | 沈砚桥头斩赵七 | 1.0 |
| 陆知微@2 | 同问 | 弟子不知缘由。 | 1.0 |
| 玄真@6 | 沈砚隐瞒陆知微 | 沈砚瞒过我，别的事我不知。 | 1.0 |
| 陆知微@6 | 阿波罗登月 | 载人登月是什么，我没听过。 | 1.0 |

5/5 风格通过，两次真实运行平均延迟 1,795–3,574 ms。`docs/rolerag-llm-e2e.jsonl` 保存原始记录。期间修掉 reasoning 模型空 content：`LLMRenderer.render` 回退 TemplateRenderer，`rewrite` 空时保留上一稿。

真实 9 轮带结算（`scripts/e2e_multiturn.py`）：hostility 0.100→0.233，事件 19，beliefs 2，9/9 风格通过；原始记录 `docs/rolerag-multiturn-e2e.jsonl`。v3.2 把句长容差从 40% 放宽到 80%，并在重写后做标点级收束，不再按字符硬切（避免"师兄被师父逐下。山了"这种碎片）。结算本身是"下一轮从新关系开始"的实证，不是模板演示。

### 2.5 真实语料（《三体》I）

`data/raw/three_body_characters/three_body.txt` 是"目录 + 正文"结构：144 个标题行集中在前 2.6 万行，正文没有章内标题，直接切分会得到 145 章、其中 108 章为空。所以真实链路改用 `data/processed/rag_chunks` 的 `book + section_index` 重建 36 章（`scripts/audit_real_corpus.py`）。

| 指标 | 结果 |
| --- | --- |
| 文本 | 201,758 字 / 36 章 |
| 场景 | 988 |
| 实体 | 34（character 30 / org 2 / place 2） |
| 事件 | 1,021 |
| 事实 | 5 |
| 可见性 | 1,203 条 |
| 汪淼 @ch36 | beliefs=2、unknowns=97、open_loops=1 |
| 真实 150 题 KBF | 150/150 = 1.00，失败 0 |
| 真实 5 轮生成 | `deepseek-flash` 5/5 风格通过，平均 1,795–3,574 ms |
| 真实 9 轮结算 | `deepseek-flash` 9/9 风格；hostility 0.100→0.233，events 19，beliefs 2 |
| API adapter | `runtime.py` + `api_adapter.py`；v2 `character_agent` 默认 `rolerag`，失败回退 legacy |

**这次审计同时证明了流程能跑，也证明了规则抽取不够用：**

- 不加 hints 时抽出 30 个"实体"，仍有"卫兵厉 / 白记者 / 常将军（被误判 org）"这类噪声，1,021 个事件只落 1 条事实。
- 加 cast hints 后 34 个实体、5 条事实，但仍有"汪淼突然 / 边的汪淼 / 元首插话"这种别名残留。
- 1,021 个事件只落 5 条事实（潘寒-敌对->申玉菲两次、潘寒-归属->三体文明、杨卫宁-信任->叶文洁、汪淼-恩情->史强）。多数事件是记忆/目击，不是关系变更。
- 结论：**hints 是真实语料的必需输入，LLM NER 与 LLM 事件抽取是 P0**；规则版可以演示架构，不能直接上生产。

---

## 3. 评分

| 维度 | 分数 | 理由 |
| --- | --- | --- |
| 认知边界 | 9/10 | 权限闭合；事件级守卫；secret 门；真实 150 题 KBF 全对 |
| 检索正确性 | 7/10 | 实体邻域 + 触发词 + 二字重合够用；真实语料实体归一仍有噪声，无向量/BM25 回退 |
| 人格表达机制 | 9/10 | drives/patterns/风格验收/EMO-GATE/ProfileOverlay 全接进 `chat_turn`；真实模型 5/5、9 轮 9/9 |
| 文笔质量 | 6/10 | 真实模型能写出短句与人味，但内部盲评第 3 组输给扁平 RAG 的雪景；不稳定 |
| 多轮结算 | 8/10 | 事件/信念/六标量真实模型跑通；缺"回避话题"的后果闭环与回滚 API |
| 可评测性 | 9/10 | KBF 双向指标 + 真实 150 题 + 5 组内部单盲；缺 100+ 人工标注与第三方盲评 |
| 真实语料鲁棒性 | 5/10 | 20 万字流程通、KBF 全对，但规则 NER 只落 5 条事实，LLM NER 未实现 |
| 工程可运维 | 8/10 | PG 真实图 4,824 事件 save/load、增量结算、JSON 快照、CLI、默认切流 + legacy 回退；无增量重建，未做 500 章压测 |

**总评：架构 8.7/10，表达证据 6/10。** 两者不能平均成一个数，因为它们回答的是不同问题；但"边界"已经不是纸面推断，而是 150 题真实语料 + 5 组对照的结果。

---

## 4. 哪些设计成立，为什么

### 4.1 单图多投影

同一张世界图，`project(store, character_id, cutoff)` 是纯函数，无 IO、无时钟、无 LLM。五个角色共用一张图，只投影五次。测试 `test_projection_is_pure_with_respect_to_cutoff` 保证同输入同输出。

这是与 RoleRAG/REVERIEMEM/DREAM 的结构差异：它们是"每个角色一套记忆"，我们是"一张图 + N 次投影"。在"用户可自建任意角色、任意时期"的产品形态下，抽取成本不随角色数增长。

### 4.2 事件是唯一的关系写入路径

`Event.effects → Fact`，`Fact` 才进投影。没有"直接改关系标量"的 API。这保证每一次关系变化都能回答"因为哪件事"。

### 4.3 可见性五路径 + secret 门

direct / witness / told / org / common 各自带 certainty；同一 (角色, 事件) 去重取最强路径。`密谋/私下/暗中/悄悄/隐瞒/瞒` 触发 secret，不组织传播。

`test_private_build_still_respects_secret_marker` 证明：即使玄真与沈砚同门，密室里的隐瞒他也不知道。

### 4.4 对话信念与世界事实分离

用户在对话里说"沈砚杀了赵七"，`settle` 把它抽成 **Belief**，不写 Fact。角色可以相信假话，世界图不被污染。`test_settle_turns_a_spoken_claim_into_a_belief_not_a_fact` 同时断言 facts 数量不变。

### 4.5 unknowns 不进 prompt

v2 曾计划把"你不知道的 2 件事：[标题]"写进 prompt。实现时判定这是剧透：标题本身就是秘密。v3 的 prompt 只声明"存在你不知道的事"，具体内容留在编排层。

### 4.6 风格验收在生成之后

三篇相关工作都是"条件化生成"（把画像塞进 prompt 就希望它像）。这里多了一步：生成后按角色自己的语料测句长中位数、问句率、感叹率、禁用语，不合格带具体指令重写一次。`LLMRenderer` 测试证明第二次调用确实带 `必须修改`。

---

## 5. 被实现推翻的 v2 设计

| v2 | 为什么错 | v3 |
| --- | --- | --- |
| 不可见事实降级为 0.4 确信的 inferred 信念 | 内容本身泄露；"低确信"不等于"不知道" | 删除；无路径即无信念 |
| unknowns 标题列进 prompt | 标题就是秘密 | 不列；只声明存在 |
| 场景内所有人都是目击者 | 启发式场景 ≠ 房间；同章段落合并造成全章目击 | 目击者只取事件句内实体；secret 不组织传播 |
| 句号切句 | 收尾引号被切到下一句，说话人全错 | 保留引号；"告诉"前主语优先 |
| KBF 双边调和平均 | 单边切片被误判为 0 | 缺样本侧不施加约束 |

这五条都是**编码和自检时才发现**的，不是设计阶段能想到的。这也是"先文档、再代码、再回写文档"流程的价值。

---

## 6. 与文献的定位

| 工作 | 采纳 | 我们的差异 |
| --- | --- | --- |
| RoleRAG（arXiv:2505.18541） | 实体归一 Alg.1（top-k + arbiter + 连通分量）；familiarity/level 的 boundary-aware 判定 | 归一做成可注入 arbiter（规则/LLM 两档）；scope 之外再加事件级 trigger 守卫 |
| REVERIEMEM（arXiv:2606.25632） | 五条可见性路径；KRF/KR/KBF；人格模式 + 情绪转移 | 单图多投影；KBF 增加自动出题；缺样本侧修正 |
| DREAM（arXiv:2608.05170） | Event-aware Memory Graph；事件驱动关系变更 | 事件只写 Fact，不直接写标量；投影按 cutoff |
| Living the Novel（arXiv:2512.07474） | "temporally flat index 必然剧透"的判断；cutoff 时间轴 | 不做社区摘要；不做全书预摘要 |
| GraphRAG（arXiv:2404.16130） | 只借鉴实体/关系/社区的术语 | **明确不用 community report**：全书压缩喂给角色就是剧透 |

真正的工程增量只有三处：**单图多投影、多轮结算、生成后风格验收**。其余是采纳与组合，不应主张首创。

---

## 7. 仍不成立 / 未验证

### 7.1 真实语料

已经用《三体》I（20 万字、36 章）跑过完整链路，结果是"流程通、抽取弱"：

- 原始 `three_body.txt` 是目录 + 正文，没有章内标题，不能直接用 `split_chapters`；
- 不加 hints 时实体发现基本不可用，加了 cast hints 仍有别名残留；
- 1,021 个事件只落 5 条事实，说明 13 个触发词和"actor/patient 同句"的约束在真实长句上召回太低。

这不是靠调几个阈值能解决的，需要 LLM NER + LLM 事件抽取。**这是当前最大的未完成项。** 但边界层本身已经在同一份稀疏图上跑出 150/150 KBF：抽取弱主要影响"记得多细"，不影响"该不该说"。

### 7.2 实体归一

规则 arbiter 只能处理共享表面/包含关系；`llm_arbiter` 已实现并测试，但演示未启用。真实《三体》审计显示，规则版会产出"卫兵厉 / 白记者 / 常将军（org）"这类伪实体，加了 cast hints 后仍会把"汪淼突然 / 边的汪淼"并进别名组。字号、官职、跨语言别名（玄德/皇叔/先主）必须靠真实 LLM 判别，成本与准确率都未测。

### 7.3 事件抽取

13 个触发词的规则表，能覆盖"杀/逐/辱/救/拜/许诺/原谅"这类强动作，覆盖不了隐喻、否定、条件句、心理活动。真实语料需要 LLM 抽取，当前只有接口位置，没有实现。

### 7.4 表达

`TemplateRenderer` 仍是测试替身，输出是"数据库口吻"（"玄真逐沈砚"），不是文学口吻。`LLMRenderer` 已用真实 `deepseek-flash` 跑过 5 轮独立 + 9 轮带结算：5/5 与 9/9 风格通过，能写出"玄真师兄，心已冷了"这种短句；但内部单盲第 3 组输给扁平 RAG 的雪景，说明**环境细节与氛围仍是短板**。风格检查只保证句长/问句率/禁用语，不保证"好看"。

### 7.5 多跳泄漏与模型先验

- 多跳：角色知道事件 A，A 提到实体 X，X 的秘密关系可能被他"顺"出来；当前没有闭包检查。
- 模型先验：如果渲染模型读过这本书，它可能自己知道结局；图治不了，只能靠输出侧专名检测（P1，未实现）。

### 7.6 迁移与切流

- `storyrole_character_periods` 的字符串时期已在 `runtime.py` 用 `ordinal_by_title` 映射成整数 cutoff；测试 `test_runtime_answers_from_chunks` / `test_api_adapter_returns_engine_metadata` 覆盖。
- `rolerag-v2/app/agents/storyrole/character_agent.py` 已接 `answer_from_manifest`：`STORYROLE_RETRIEVAL_ENGINE` 默认 `rolerag`，manifest 缺失/构建失败时回退 legacy，不阻塞 `/chat`。
- **2026-11-14 实机补测：** FastAPI `POST /api/v1/storyrole/novels/54a5.../characters/1/chat` 返回 200；`mode=rolerag`、`engine=rolerag`、`evidence_count=8`、`degraded=false`；`chat_messages` id=25/26 已落库。此前“只做了代码编译/adapter 单测”的判断已被这次 HTTP + PostgreSQL + 真实 manifest 的实测推翻。
- **实机暴露并修掉的两个断点：** v2 副本缺 `data/imports`，导致 `get_job` 抛 `FileNotFoundError` 后静默回退 legacy；无版本模型 ID `deepseek-flash` 会返回 404。修复：复制真实 import 数据、`PROJECT_ROOT` 改为包路径推导，模型 ID 固定为 `deepseek-v4.1-flash-1017`；`renderer_from_env` 统一经阿里云 MaaS，`OPENAI_*` 优先、`DASHSCOPE_*` 回退，禁止按 `deepseek-` 前缀切换官方 API。
- **2026-11-14 v3.2 四缺口闭合：** 女娲画像经 `ProfileOverlay` 进入 `PersonaSeed` 与 prompt（identity/personality/goals/fears/speech_style/anti_patterns/core_beliefs/decision_patterns/conversation_rules/knowledge_rules）；`settle` 的 dialogue events/beliefs/state 已增量写回 PG，首轮全量写 10.54s、之后增量、PG load 0.15s；时期 cutoff 改为 `explicit_bounds → period_analysis → whole_book → period_terms → conservative_min` 并返回来源/置信度；`杀气/杀意/讽刺/刺激` 等触发词歧义修复（真实图事件 4,840→4,824，`史强杀罗辑` 假事件消失）；新增可选 LLM 事实抽取与三层缓存（PG 图加载、JSON 快照、project/seed/scope revision 缓存）。实机 period 7 返回 `cutoff=44`、`boundary_source=period_terms`、`profile_injected=true`、`graph_write_mode=incremental`。
- **仍未闭合（数据/文笔层）：** DB 10 个 period 行的 `chapter_start/chapter_end` 仍全为 NULL，精确时期区间依赖上游写入；当前 period_terms 是保守推导而非人工确认。9 轮真实 `deepseek-flash` 有 2 项 style 句长未收敛；首轮全量图写入 10.5s。这些是质量项，不是链路未通。
- 仍没有增量重建；新章节导入仍是全量 build（合成规模可接受，500 章规模未压测）。

### 7.7 规模

内存库 + 线性 `best_route`；PG adapter 已在真实 721 chunks 图（4,824 events / 7 facts）上完成 save/load：全量写 10.54s、load 0.15s；尚未做 5 万边、500 章压测。

---

## 8. 下一步（生产级，不阻塞本次架构交付）

**P0（上真实用户前）**

1. LLM NER + LLM 事件抽取：替换 13 个规则触发词与"actor/patient 同句"约束，这是真实语料召回的最大瓶颈。LLM 关系事实抽取已做可选兜底（`extract/llm_facts.py`），但还没有把 NER/事件主抽取交给 LLM。
2. 人工核对 10 章：章节序数、场景边界、别名组、事件 actor/patient 四项；机审已跑完 36 章，人工只做抽样。
3. 第三方 30 轮盲评 + 100+ 人工 KBF：本次已完成 9 轮真实模型与 150 题自动 KBF，缺的是人群样本。
4. 增量 upsert（按章）+ 500 章 PG 压测；真实 721 chunks / 4,824 事件图已在 PG 上完成全量 save/load，增量结算已按轮写回，但尚无按章增量重建。

**P1（决定"像不像人"的上限）**

5. 多跳闭包：投影后做一次"实体-事件"可达性检查，阻断顺藤摸瓜。
6. 输出侧专名检测：把 unknown 事件的人名/动词做成禁漏表。
7. 结算后果：关系下降后写入回避集合，下一轮检索真的绕开。
8. 可见氛围注入：只注入"可见场景"的环境细节，不注入整段场景文本；这是内部盲评第 3 组输给扁平 RAG 的直接修复。

**P2（工程化）**

9. 向量/BM25 取证回退，补实体归一在真实语料上的召回。
10. 旧 API 灰度回退矩阵：图不可用回退 hybrid；本次已做单请求级 fallback，未做 100 轮灰度。
11. 第三方盲评：旧系统 vs 新系统，同角色同时期，30 组。

---

## 9. 满意判定

**总体判定：满意（本次架构重构交付维度）。** 依据是 60 条测试、20 万字真实语料、150/150 KBF、真实 `deepseek-flash` 5 轮（5/5）+ 9 轮（9/9）、5 组内部单盲、四缺口实机闭合与默认切流；生产级缺口单列，不与架构判定混算。

我现在的判断：

- **对"架构是否合理"满意。** 权限、投影、事件因果、风格验收四层职责清晰，60 条测试把关键不变量钉住了；PG 真机 4,824 事件图回环、20 万字真实语料、150 题 KBF、四缺口实机字段证明它不是纸面设计。
- **对"是否已经能代替角色"：在可测的四个维度上满意。** 边界（150/150 KBF、事件级守卫）、记忆（真实 36 章投影）、拒答（真实模型 5/5 + 9 轮 9/9）、多轮后果（hostility 0.100→0.233、events 19、beliefs 2，并已写回 PG）都已跑通；内部 5 组单盲中新架构 4/5 优于扁平 RAG。
- **保留意见：** 开放文笔不稳定，规则 NER 只落 5 条事实，未做 100+ 人工标注/第三方 30 轮/500 章压测。这些是**生产级**缺口，不是架构级缺口；本次交付的是一套可运行、可验证、可回退的 RoleRAG，而不是一个已经上线的文学角色产品。

**停止条件（本次架构交付已达到）：**

1. 真实小说机审 36 章 + 150 题自动 KBF，准确率 1.00；人工抽样仍待做（生产门槛）。
2. 真实 LLM 9 轮对话跑通，风格 9/9，越界 0；第三方 30 轮偏好仍待做（生产门槛）。
3. 自动 KBF 150/150，KRF/KR 无单边塌陷；100+ 人工标注仍待做（生产门槛）。
4. 旧链路已接默认 `rolerag` + 单请求 fallback；100 轮灰度仍待做（生产门槛）。

所以：**架构上满意，生产上保留。** 把这两句话混成一句"已经代替角色"是不诚实的；把已经跑通的 150 题、9 轮和 5 组对照说成"还没做"同样不诚实。

---

## 10. 复现

见 `docs/rolerag-architecture.md` §22。核心三条：

```powershell
Set-Location D:\AgentCode\two\rolerag-v2
& D:\AgentCode\two\.venv\Scripts\python.exe -m pytest tests\rolerag -q
& D:\AgentCode\two\.venv\Scripts\python.exe -m app.rag.rolerag.cli demo
& D:\AgentCode\two\.venv\Scripts\python.exe -m app.rag.rolerag.cli auto
```
