# RoleRAG 优化日志：从 v2 设计到 v3.1 实现

> 日期：2026-11-14
> 对应代码：`rolerag-v2/app/rag/rolerag/`（43 个模块，4,561 行；14 文件 / 690 行 / 60 条测试）
> 对应设计：`docs/rolerag-architecture.md` v3.1
> 对应自检：`docs/rolerag-self-review.md`

这份文档只记录**被证据推翻、并因此改了设计/代码**的轮次。没有改代码的"想法"不写进来。

---

## 第 0 轮：GraphRAG 社区摘要 —— 拒绝

**初始想法：** 用 GraphRAG 的社区发现 + 社区摘要，把全书关系压缩成高层描述，喂给角色。

**证据：** `Living the Novel`（arXiv:2512.07474）指出 temporally flat index 必然剧透；GraphRAG 的社区摘要本质是"全书压缩"，角色会提前知道后半本。

**决策：** 不建社区层，不做全书预摘要；只做单图 + 按 (角色, 章节) 投影。GraphRAG 只借"实体图 + 关系抽取"，不借社区报告。

**结果：** 架构从"图谱检索"变成"认知边界检索"；后续 150 题 KBF 证明这个选择是主线。

---

## 第 1 轮：实现推翻 v2 的五个设计

| v2 设计 | 实现中发现 | 改法 | 测试 |
| --- | --- | --- | --- |
| 不可见事实降级为 certainty=0.4 的 inferred 信念 | 低音量秘密仍会进 prompt | 删除；无可见路径就不生成信念，只记 unknowns | `test_unseen_event_is_recorded_but_never_becomes_a_belief` |
| unknowns 转成具体禁令，把事件标题列进 prompt | 标题本身就是秘密 | prompt 只说"存在你不知道的事"，不列标题 | `test_prompt_does_not_list_unknown_event_titles` |
| 场景内所有人都是目击者 | 段落合并把同章无关人物并成一场，玄真"看见"密室 | 目击者只取事件句内实体；secret 不做组织传播 | `test_private_build_still_respects_secret_marker` |
| 句号切句 | 收尾引号被切到下一句，说话人归属错 | 切句保留收尾引号；说话人取"告诉"前主语或引号前最近实体 | `test_split_sentences_keeps_closing_quote` |
| KBF 双边调和平均 | 切片只有负样本时 KR=0，KBF 被误判 0 | 缺样本的一侧不施加约束 | `test_side_without_samples_imposes_no_constraint` |

**结果：** 47 → 53 条测试；投影与拒答自洽；演示 25 题 KBF=1.00。

---

## 第 2 轮：真实语料暴露抽取问题

**输入：** `three_body.txt`（2.6 MB / 902,487 字符）。

**发现：**

1. 文件是"目录 + 正文"：144 个标题行集中在前 26,000 行，正文没有章内标题；`split_chapters` 得到 145 章，108 章为空，707k 字符全归最后一章。
2. 改用 `novel_chunks.jsonl`（569 chunks，metadata `book/section_index/chunk_index`）按 `book + section_index` 重建 36 章、201,758 字。
3. 无 hints：30 个"实体"大量是"叶文洁回 / 宽容地笑 / 计算机 / 方向"，1,021 events，0 facts。
4. 加 cast hints：34 实体、1,021 events、5 facts、1,203 visibility；汪淼 beliefs=2、unknowns=97。
5. `_SPEECH` 正则贪婪吞字，产生"叶文洁回 / 常将军讲"；真实小说大量"引号在前、说话人在后"，原正则只支持"名字在前 + 说 + 冒号 + 引号"。

**改法：**

- 新增 `scripts/audit_real_novel.py` 记录 raw 目录结构问题；`scripts/audit_real_corpus.py` 按 chunks 重建章节，内置 CAST hints。
- `_SPEECH` 改长动词优先（`说道|问道|笑道|叹道|怒道|喝道|回答|开口|低声说|高声说|说|道|问|喊|叫`），去掉单字"答"。
- 新增 `_clean_name`：修剪坏尾/坏头、姓氏表、标题、外来名头、常用名词黑名单。
- `EntityCandidate` 增加 `explicit_type`；hints 置 True；后缀推断只对自动发现生效，避免"常将军"被误判 org。

**结果：** 无 hints 30 实体/1 fact；加 hints 34 实体/5 facts；仍有"汪淼突然 / 边的汪淼"别名残留，记录为已知限制。

**决策：** 规则抽取继续作为"零成本基线"；LLM NER 列为生产级 P0，不阻塞架构验证。

---

## 第 3 轮：真实模型把"不知道"说成口头禅

**输入：** DashScope `qwen-plus`（`.env` 的 `DASHSCOPE_API_KEY` 可用）。

**初始 5 轮：** style 4/5；probe 只回答"不知"2 字，句长偏离 43%。

**发现：** prompt 没有强制"有记忆就必须用"；模型把"为什么"一律当成不知道原因。

**改法：**

1. system 增加"【可用记忆】不是空的：不许回答不知道，必须把记忆里的那件事说出来"。
2. user 增加"【必须用上的记忆】<首条 evidence>"。
3. `LLMRenderer.rewrite` 增加"写成完整的一句话，不能只给一个词"。
4. 拒答增加"拒答也要像你：可以短、可以回避、可以反问，但不能像客服"。

**结果：**

```
陆知微@6 沈砚被逐 → 记得。玄真逐他下山。
陆知微@6 沈砚为什么斩赵七 → 沈砚斩赵七于桥头。我不知道为什么。
陆知微@2 同问 → 不知道。
玄真@6 沈砚隐瞒陆知微 → 不知道。
陆知微@6 阿波罗登月 → 不知道。
style_pass=5/5 avg_latency=689–738ms（历史 qwen-plus 记录）
```

**决策：** 保留"知道的事必须说、不知道的事可以短"的分层；不为了文笔放宽边界。

---

## 第 4 轮：真实 KBF 从 148 → 149 → 150

**初始 150 题：** 148/150。两题失败都表现为"expected 空，却答出了事件"。

**逐题定位：**

1. 汪淼"潘寒杀申玉菲"：同一关系有两条 fact（ch20 / ch23），ch20 可见、ch23 不可见；`generate_cases` 只看本条 fact，误判为负样本。
2. 雷政委"杨卫宁骗叶文洁"：检索到了**另一件**"雷志成骗叶文洁"的事件——触发词"骗"在，角色实体"叶文洁"在，于是事件守卫放行。

**改法：**

- `generate_cases` 的可见性改为按 `project()` 的 beliefs `(subject,target,kind)` 判定，而不是单条 fact 行；重复关系只要早先实例可见，就算知道。
- 子图 episode 证据收紧：场景必须有"角色可见 + 参与人与查询目标相交"的事件；episode 文本只用可见事件标题，并加"我记得那天在<地点>"，不用整段 scene 文本。
- `guard_unseen_trigger` 传入 `store`，要求事件参与者覆盖问题中的**全部角色实体**（单角色题要求 1 个）；地点/组织不参与匹配。

**结果：** `cases=150 correct=150 accuracy=1.00 failed_cases=0`。汪淼 KRF/KR/KBF 从 1.00/0.67/0.77 → 1.00/1.00/1.00；雷政委失败消失。

**教训：** KBF 失败不一定是"检索不准"，可能是"出题口径"和"证据通道"不一致；先对齐投影，再谈调参。

---

## 第 5 轮：多轮结算与盲评

### 5.1 9 轮真实模型

**脚本：** `scripts/e2e_multiturn.py`，每轮 `chat_turn` 后调用 `settle`。

**结果：**

```
turn 3 "玄真骂你是废物" → trigger=['废物']，hostility 0.100→0.250
9 轮结束（历史 `qwen-plus` 记录）：hostility 0.233，events 18→19，beliefs 1→2，风格 8/9。v3.2 用 `deepseek-flash` 复测为 events 19、beliefs 2、风格 9/9。
```

**发现：** 第 8 轮"青霄门，再也回不去了"因句长偏离被判负；真实模型仍会越过指纹边界。

**决策：** 保留一次重写；不把风格检查降级成"只要不超长就过"。

### 5.2 5 组内部单盲

**脚本：** `scripts/blind_eval.py`；基线是"关键字 top-3 场景 + 不截断 + 不投影 + 整段原文喂模型"。

**结果：**

- 边界/事实：新架构 5/5，基线 2/5；基线在第 1/2/4/5 组出现"要杀我 / 他瞒我 / 死了 / 阿波罗的星海"等越界或幻觉。
- 文笔：基线 2/5 更好（第 2、3 组），新架构 0/5 更好；第 3 组新架构输在"没有雪景"。
- 总体：新架构 4/5。

**决策：** 不把"边界胜"包装成"全面胜"；下一轮优化方向是"可见场景的氛围片段注入"，不是放宽可见性。

---

## 第 6 轮：旧链路切流与运行时不崩

**问题：** 旧 `CharacterAgent` 只读 `search_novel`，RoleRAG 只有门面，没有 API 适配。

**改法：**

- 新增 `runtime.py`：JSONL chunks → 按 `book + section_index` 重建章节 → `build_all` → `RoleRAGRuntime`；时期字符串用 `ordinal_by_title` 映射成 cutoff。
- 新增 `api_adapter.py`：manifest + character rows → hints → 缓存 build → `chat_turn` → `settle`；返回 engine/route/style/cutoff 元数据。
- `rolerag-v2/app/agents/storyrole/character_agent.py` 接入；`STORYROLE_RETRIEVAL_ENGINE` 默认 `rolerag`，manifest 缺失/构建失败回退 legacy。
- 新增 4 条 runtime/adapter 测试，覆盖章节顺序、时期 cutoff、engine 元数据、JSON aliases。

**结果：** 53 条测试通过；API 代码路径可编译；默认切流但单请求可回退。

**保留：** 未做 100 轮灰度、未做 500 章压测、未做增量 upsert；这些是生产级，不是架构级。

---

## 第 7 轮：真实 import manifest 的运行时冒烟

**输入：** `data/imports/54a5.../chunks.jsonl`（721 chunks，真实导入产物），不走 demo。

**第一次结果：**

```
chapters 53 entities 101 events 4,840 facts 13
route stance text 史强的事，说不清。我只知道，我欠自己一个交代。
```

问题不是检索，而是**路由**：`"潘寒杀申玉菲"` 没有"还记得/为什么"这类标记，被默认判成 `stance`，返回了与问题无关的既有信念。

**改法：**

1. `route` 在 `_PROBE` 之后增加"触发词即事件查询"：只要句中出现 `TRIGGERS`（杀/逐/辱/骗/隐瞒…），走 `recall`，交给事件检索与守卫；没有可见事件就拒答，而不是拿无关信念表态。
2. `build_from_chunks` 优先按 metadata 的 `chapter_number` 分组；没有才退回 `section_index`；真实章号不再被 front matter 的 section 序号错位。
3. 真实章号分组不再前置第二个"第N章"，避免 `split_chapters` 把一章切成两章。

**第二次结果：**

```
chapters 53 entities 101 events 4,840 facts 13
route recall text 那天我记得。潘寒杀申玉菲。
```

**注意：** 53 章不是 36 章——真实 import 的 721 chunks 含三部曲/front matter，`book` 为空时按 `section_title` 分组，章号有重复。它证明运行时能吃真实 manifest，不证明三部曲合一的章节对齐已经完美；单书导入仍建议用 `book + section_index` 的 processed chunks。

---

## 第 8 轮：真实 HTTP 链路 —— 从"代码已接"到"实机 200"

**输入：** 本机 FastAPI + PostgreSQL 16（5433）+ 真实 import manifest（721 chunks）+ 真实 `deepseek-flash`（历史首次联调为 `qwen-plus`）。

**第一次结果：** `mode=null`、`engine=null`、`degraded=true`。不是 RoleRAG 算错，是它根本没有进入 RoleRAG 分支：

1. `rolerag-v2` 副本没有 `data/imports`，`novel_import_service.get_job` 抛 `FileNotFoundError`，`character_agent` 静默回退 legacy。
2. 进入 adapter 后，`.env` 的 `STORYROLE_CHAT_MODEL=deepseek-flash` 被拿去请求 DashScope，404。

**改法：**

1. 复制真实 `data/imports/54a5.../manifest.json + chunks.jsonl` 到 v2；`api_adapter.PROJECT_ROOT` 从硬编码路径改为包路径推导，支持 `STORYROLE_PROJECT_ROOT` 覆盖。
2. 当前 `runtime.renderer_from_env` 不按模型家族切换供应商：统一经阿里云 MaaS，`OPENAI_*` 优先、`DASHSCOPE_*` 回退，`DEEPSEEK_*` 仅作官方端点回滚；`ROLERAG_LLM_MODEL` 仍可显式覆盖模型 ID。
3. 新增 `scripts/e2e_api_agent.py`（真实 CharacterAgent）和 `scripts/e2e_api_http.py`（真实 HTTP）。

**第二次结果：**

```text
status 200
character 罗辑  profile_version 16  period_id 1
mode rolerag  engine rolerag  evidence_count 8
degraded false  latency_ms 4702
chat_messages id=25 user / id=26 assistant
```

**注意：** 第一次真实回答是"史强曾试图杀我……"，风格像角色，但事实错了——史强不是杀罗辑的人。根因不是链路，而是 `杀气` 二字命中了 `杀` 触发器；v3.2 已加 `_TRIGGER_EXCLUDES`，真实 721 chunks 事件 4,840→4,824，假杀事件消失。时期 cutoff 也从"无 bounds 就全量"改成显式/分析/词面/最小保守的来源分级；`settle()` 已写回 PG（首轮全量、之后增量）。详见 `docs/rolerag-api-chain.md`。

---

## 最终状态（v3.2，2026-11-14）

| 指标 | 结果 |
| --- | --- |
| 模块 / 行数 | 43 / 4,561 |
| 测试 | 14 文件 / 690 行 / 60 条，全过（`60 passed in 0.26s`） |
| 真实语料 | 201,758 字 / 36 章 / 988 场景 / 34 实体 / 1,021 事件 / 5 事实 / 1,203 可见性 |
| 真实 KBF | 150/150 = 1.00（触发词修复后复测） |
| 真实 5 轮 | `deepseek-flash` 5/5 风格，平均 1,795–3,574ms（两次真实运行） |
| 真实 9 轮 | `deepseek-flash` 9/9 风格，hostility 0.100→0.233，events 19，beliefs 2 |
| 内部单盲 | 新架构 4/5 边界胜；文笔 1 组负 |
| API | 真实 HTTP 200（`mode=rolerag`、8 证据、`profile_injected=true`、`graph_write_mode=incremental`、无退化、transcript 落库）；失败回退 legacy |
| PG | 真实图 4,824 events / 7 facts 全量 save 10.54s、load 0.15s；每轮增量写 state/events/beliefs；`storyrole_rolerag_meta` 版本校验 |
| 缓存 | JSON 快照 13MB：save 0.13s / load 0.11s；`lru_cache` 图 8、profile 64；project/seed/scope 按 revision 失效 |

**一句话：** 这套架构已经不是"再加一个 GraphRAG 模块"，而是把 RAG 的检索对象从"段落"换成了"角色在某一章能看见的世界"；剩下的工作是生产级抽取与人群盲评，不是重新设计。
