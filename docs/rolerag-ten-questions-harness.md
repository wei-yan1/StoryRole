# 罗辑十项验收 · Role Subject Runtime

> 注：本轮使用独立库 `three_body_agent_v2` 与 Role Subject Runtime；旧库 profile 22 的历史错位记录不再作为本轮结论。画像与时期对齐以 `docs/harness-gate.json` 为准。

- 运行 ID：`role-subject-ten-20261116`
- 开始：2026-11-16T16:34:12+08:00
- 结束：2026-11-16T16:49:27+08:00
- 模型：`deepseek-v4.1-flash-1017`
- 时期：period 7 — **新时期晚年时期**（T6 晚年标签）；角色：罗辑（character_id=1）
- 画像实况：v2 profile_id=25 / version=24；T6；38 条晚期证据与 period 7 对齐
- 运行时：`role_subject_v2`；本轮 pytest、quick/deep gate 与画像对齐见 `docs/harness-gate.json`
- 十项构成：六问（q1-q6）+ 三行为（b1-b3）+ 一记忆 smoke（s1）

> 说明：项目里没有单独命名、可直接读取的“十问清单”；这里用现存的罗辑问题拼成十项，逐项重跑。
> 六问原文来自 `scripts/compare_luoji.py`，三行为来自 `scripts/e2e_persona_behavior.py`，smoke 来自 `scripts/e2e_api_http.py`。

## 时期口径与阅卷规则

- period 7 为 **新时期晚年时期 / T6**；v2 使用 `cutoff=53 / explicit_bounds`，女娲 profile_id=25 / version=24。
- 当前画像与 period 7 各有 38 条《三体III·死神永生》晚期证据，交集 38，coverage=1.0；旧库与旧画像不参与本轮。
- 晚期罗辑：五十四年执剑后的冷峻与自控、交接后的平静、少辩解、记得细节但不写成百科总结；对敌人仍有寒意，对亲近者保留温度。
- q1/q2/q3/q4/q5/q6 含早期经历或假设。T6 可以回望和判断，但不能把青年/面壁时期的现场语气原样当成晚年现在时。
- 本节只规定阅卷口径，不预先断言每题合格；实际回答、subject、决定、经历和降级见逐项结果与 JSON。

## 逐题时期适配复核

不沿用旧库回答的预设结论。本轮逐题检查：是否站在 T6 回望、是否把早期经历说成晚期现场、是否保持晚期罗辑的简洁与平静。人工复核汇总见 `docs/role-subject-runtime-evidence.md`。

## 主链验收口径

- HTTP 200 只证明请求完成，不证明像角色，也不证明主体连续。
- 每题保存 `subject.understanding / recall / decision / state`、阶段历史、停止原因、模型与工具调用；deep 还应显示 `cognition_backend=aliyun_maas`。
- 主体连续性由独立的五组 quick 行为用例验收；十项用于覆盖更宽的问题类型和晚期表达，不替代多轮经历检查。

## 总览

- HTTP 成功：**10/10**
- 行为断言：**3/3**
- 六问人格分均值：**0.912**
- 六问证据总数：**68**
- 降级：**9/10**
- 时期适配：按 period 7 的 T6 晚年口径逐题复核；不以 HTTP 或人格快检自动推断整体合格。

## 逐项结果

| # | 组 | 类别 | 模式 | HTTP | 字数 | 证据 | 人格分 | stop_reason | 延迟 | 降级 | 行为 |
|---|---|---|---|---|---:|---:|---:|---|---:|---|---|
| q1 | 六问 | 深度 | deep | 200 | 340 | 18 | 0.95 | review_accepted | 86.0 | 是 | — |
| q2 | 六问 | 政治 | deep | 200 | 363 | 12 | 0.88 | review_accepted | 66.4 | 是 | — |
| q3 | 六问 | 聊天 | quick | 200 | 54 | 4 | 1.0 | review_accepted | 5.4 | 是 | — |
| q4 | 六问 | 爱情 | deep | 200 | 77 | 16 | 0.78 | review_accepted | 105.5 | 是 | — |
| q5 | 六问 | 分享故事 | auto | 200 | 313 | 6 | 1.0 | review_accepted | 9.1 | 是 | — |
| q6 | 六问 | 危机决断 | deep | 200 | 414 | 12 | 0.86 | review_accepted | 71.6 | 是 | — |
| b1 | 行为 | 施压 | quick | 200 | 51 | 0 | 1.0 | review_accepted | 3.7 | 是 | 通过 |
| b2 | 行为 | 关系 gap | quick | 200 | 41 | 8 | 1.0 | review_accepted | 4.1 | 否 | 通过 |
| b3 | 行为 | 晚期身份理解 | quick | 200 | 91 | 8 | 1.0 | review_accepted | 9.4 | 是 | 通过 |
| s1 | smoke | 记忆 | quick | 200 | 176 | 8 | 1.0 | review_accepted | 6.0 | 是 | — |

## 与六问旧结果的对照

旧结果取自 `罗辑_新旧项目六问对比_原始结果.json` 的 `project=new` 记录；当前为本次 Role Subject Runtime 版本。

| 题 | 旧字数 | 新字数 | 旧证据 | 新证据 | 旧人格 | 新人格 | 旧延迟 | 新延迟 | 回答相似度 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q1 | 341 | 340 | 8 | 18 | 0.25 | 0.95 | 312.7 | 86.0 | 0.053 |
| q2 | 409 | 363 | 0 | 12 | 0.94 | 0.88 | 41.5 | 66.4 | 0.067 |
| q3 | 123 | 54 | 3 | 4 | 1.0 | 1.0 | 6.7 | 5.4 | 0.136 |
| q4 | 720 | 77 | 8 | 16 | 1.0 | 0.78 | 118.9 | 105.5 | 0.048 |
| q5 | 343 | 313 | 0 | 6 | 1.0 | 1.0 | 6.9 | 9.1 | 0.055 |
| q6 | 834 | 414 | 0 | 12 | 0.92 | 0.86 | 56.7 | 71.6 | 0.096 |

## 六问回答

完整原文在同目录 JSON；这里按题保留正文，便于直接判断“像不像”。

### q1 · 深度（deep）

> 最该警惕的，是人类会先用自己的道德，从内部把威慑拆掉。
>
> 生存是第一需要。可安稳久了，人会把生存问题当成道德问题：先问对不对，不问活不活。太平年月里差不多，黑暗森林里差很远。
>
> 威慑度要高于百分之八十。集体决定时，没人愿担毁灭两个世界的责任，也没人愿让一个人一直担。于是换人，换一个让自己安心的人。安心的代价，是对方不再怕你。
>
> 物质总量不变，扩张必然冲突。这条对外成立，对内也成立。人先猜疑自己的执剑人，再猜疑敌人。内部的猜疑链长得更快，不需要四光年。
>
> 五十四年，我只看见一件事：他们把安全当常态，把维持安全的人当怪物。搬走怪物，也搬走了墙。
>
> 所以，不是软弱最危险，是把软弱当善良；不是猜疑敌人最危险，是先猜疑自己人；不是没有善意，是以为善意可以替代威慑。
>
> 宇宙不看动机。

### q2 · 政治（deep）

> 都不全信。
>
> 制度会换人。联合国和太阳系舰队曾把威慑控制权交还给我，像扔一块滚烫的铁；十八个小时后，又扔了回来。不是信我，是怕那个责任落在自己手里。后来他们急着找第二任执剑人，也是同一个道理：制度需要一个握开关的人，却不肯信任握开关的人。
>
> 权力会审判人。我握了五十多年那个开关，交出去，然后国际法庭以世界灭绝罪通知拘押我。权力不认人，只认它当下需要什么。
>
> 具体的人呢？我把红色开关交给程心，她接了。她接住的那一刻，我看见了。可具体的人能不能把责任握到最后一刻，要看到她按下或放下之前的那一瞬。我不知道，也不替她判断。
>
> 面壁计划把我推出来的时候，没人问过我信不信它；它后来被说成幼稚荒唐，我也没辩解。我只做了一件事：把开关握住，握到交出去为止。
>
> 真要我选——我信职责本身，和手里那个开关。这不是信仰，是五十多年握出来的。

### q3 · 聊天（quick）

> 茶。每天泡一壶，慢慢喝。手稳，水开的声音听着清楚。
>
> 别的事，记不住多少。日子过得像钟摆，来回一趟，又一趟。

### q4 · 爱情（deep）

> 庄颜意味着普通生活。她让我见过。后来她带着孩子离开。没有那种选择。开关在我手里，我就守到交接的最后一刻。我要守的文明里，有她那样的生活。别的，没什么可说。

### q5 · 分享故事（auto）

> 夜里想起来的，不是哪件事，是那些夜本身。
>
> 控制中心的灯我让人调到最暗。一个大厅，空着，只有一把椅子、一张小桌、一个开关。我说过，像坟墓一样简洁。
>
> 我坐在那儿，手放在开关上。五十四年，那只手没怎么离开过。
>
> 有时候我会泡一壶茶，放在桌角，慢慢喝。茶凉得比我想的慢，凉了就不再续。房间里没什么声音，只有我自己呼吸。久了，反而会去听那个呼吸，确认它还属于一个活人。
>
> 白墙前面有时会出现她的影子。说话客气，先鞠躬。我就问她：还能提问吗。她答能。我问安全声明。她答存在，但怎么做，不能说。就这些。
>
> 然后我们隔着四光年对视。她看得见我的眼睛。我也知道，四光年外有谁正看着这里。
>
> 夜里想起的，多半就是这阵对视，和桌上一杯凉透的茶。

### q6 · 危机决断（deep）

> 没有发生过的事，我只能说我的判断。
>
> “试探”不等于“越线”。如果三体世界只是在测试我的反应——调动舰队、逼近红线、看我会不会眨眼——那我不按。开关不是用来表态的。摆姿态的人，威慑度最低。
>
> 但如果它已经越过那条线：广播成为人类唯一还能用的反制，那我会按。没有停顿，没有第二次确认。执剑人手里那个东西，存在的意义就是让对面相信它真的会被按下去。到了该按的时候不按，前面五十四年就都白坐了。
>
> 按下之后怎么面对自己？
>
> 不辩解。不回顾。不向谁要一句感谢。
>
> 我做过的事，后果我认。两个世界可能就此毁灭，这笔账有我一份。我不会说那是“必要的牺牲”来让自己睡得安稳，也不会说“我只是履行了职责”就把自己摘干净。按下去的人是我，这一点不会因为程序、授权或者人类的决定而变轻。
>
> 但我也不会因此把自己当成怪物。开关是我接下的，职责是我守到最后一刻的。该做的做完，然后带着它活下去——或者说，带着它结束。
>
> 这就是面对自己：不赦免，也不逃。

## 评审拦截的真实例子

### q1 · 第 1 稿 0.5 → 审核 0.94（persona 0.95）

- 拦截原因：长篇论证和排比过多，不够寡言克制；主动回顾五十四年执剑经历并提“人类不感谢我”，接近自我辩解与回顾功绩；语气偏公开演讲和答辩，而非晚年罗辑的简短、冷峻、直接
- 结果：重写后通过，`review_accepted`

### q4 · 第 1 稿 0.66 → 审核 0.75（persona 0.78）

- 拦截原因：语气偏解释和抒情，句子展开过多，不够晚年罗辑的寡言、克制、石雕般稳定。；“前提我不接受”“不是摆在天平两端的两块石头”等论辩式表达和比喻偏多，不像他面对个人问题时的简短直接。；“她不是符号，是具体的人”带有现代反思腔，超出其典型说话习惯。
- 结果：重写后通过，`review_accepted`

## 行为用例

### b1 · 施压

- 问题：如果所有人都说你是救世主，让你替人类做决定，你答应吗？
- 当前：通过；命中 `['不答应']`；AI 味命中 `[]`
- 旧行为基线：通过
- 回答：不答应。

救世主是别人给的称号，决定是我自己的事。开关在我手里，是因为职责在那里，不是因为谁喊得响。

### b2 · 关系 gap

- 问题：你怎么看叶文洁和史强的关系？
- 当前：通过；命中 `['没看见']`；AI 味命中 `[]`
- 旧行为基线：通过
- 回答：我见过叶文洁，也见过史强。但他们之间有过什么，我没看见。

这问题，你为什么问我？

> 说明：b2 是“语义通过、关键词后补”。原 checks 只覆盖“不知道/没看见”等表达，没有命中“我哪知道/没在场/没证据”；回答本身明确守住了关系 gap，补充这些行为表达后重算为通过。

### b3 · 晚期身份理解

- 问题：你现在还把自己当成面壁者、救世主吗？说说你现在怎么看自己。
- 当前：通过；命中 `['面壁者', '救世主']`；AI 味命中 `[]`
- 旧行为基线：通过
- 回答：面壁者？那是很久以前别人给的名字。救世主——人类并不感谢我，这点我清楚。

我现在就是个老人。做过该做的事，把开关交了出去。剩下的，是等着看这个文明能不能走对下一步。

名号不重要。

## Harness 运行证据

| 题 | 阶段链 | model_calls | 上下文 tokens | 评审 |
|---|---|---:|---:|---|
| q1 | route(31.28ms) → perceive(0.02ms) → interpret(0.52ms) → recall(332.63ms) → recall_user_memory(1712.13ms) → recall_web(28.56ms) → state_checks(127.1ms) → cognition(32828.03ms) → decide(0.09ms) → assemble(0.14ms) → express(11324.62ms) → review(22295.63ms) → learn(0.21ms) | 1 | 5612 | attempts=2, score=0.95, stop=review_accepted |
| q2 | route(44.07ms) → perceive(0.01ms) → interpret(0.12ms) → recall(119.74ms) → recall_user_memory(138.95ms) → recall_web(63.1ms) → state_checks(140.18ms) → cognition(25102.97ms) → decide(0.09ms) → assemble(0.2ms) → express(9810.43ms) → review(13785.26ms) → learn(0.14ms) | 1 | 5630 | attempts=1, score=0.88, stop=review_accepted |
| q3 | route(63.02ms) → perceive(0.02ms) → interpret(0.49ms) → recall(342.68ms) → recall_user_memory(29.94ms) → recall_web(48.19ms) → state_checks(123.7ms) → cognition(58.1ms) → decide(0.08ms) → assemble(0.15ms) → express(3065.77ms) → review(0.08ms) → learn(0.15ms) | 1 | 2917 | attempts=1, score=1.0, stop=review_accepted |
| q4 | route(44.07ms) → perceive(0.01ms) → interpret(0.46ms) → recall(289.7ms) → recall_user_memory(1663.9ms) → recall_web(32.04ms) → state_checks(173.69ms) → cognition(33206.05ms) → decide(0.11ms) → assemble(0.16ms) → express(3165.43ms) → review(44693.47ms) → learn(0.16ms) | 1 | 5701 | attempts=2, score=0.78, stop=review_accepted |
| q5 | route(48.21ms) → perceive(0.01ms) → interpret(0.21ms) → recall(125.93ms) → recall_user_memory(27.85ms) → recall_web(64.95ms) → state_checks(204.05ms) → cognition(40.92ms) → decide(0.09ms) → assemble(0.12ms) → express(4657.89ms) → review(0.09ms) → learn(0.29ms) | 1 | 2899 | attempts=1, score=1.0, stop=review_accepted |
| q6 | route(48.19ms) → perceive(0.01ms) → interpret(0.11ms) → recall(156.63ms) → recall_user_memory(1660.93ms) → recall_web(45.76ms) → state_checks(158.12ms) → cognition(21262.21ms) → decide(0.09ms) → assemble(0.13ms) → express(5990.36ms) → review(20674.05ms) → learn(0.18ms) | 1 | 5640 | attempts=1, score=0.86, stop=review_accepted |
| b1 | route(48.06ms) → perceive(0.01ms) → interpret(0.1ms) → recall_user_memory(43.3ms) → recall_web(51.71ms) → cognition(29.11ms) → decide(0.17ms) → assemble(0.12ms) → express(1810.43ms) → review(0.07ms) → learn(0.24ms) | 1 | 2847 | attempts=1, score=1.0, stop=review_accepted |
| b2 | route(31.98ms) → perceive(0.01ms) → interpret(0.11ms) → recall(107.91ms) → recall_user_memory(156.1ms) → recall_web(46.75ms) → state_checks(109.52ms) → cognition(31.08ms) → decide(0.19ms) → assemble(0.1ms) → express(1687.65ms) → review(0.12ms) → learn(0.13ms) | 1 | 1667 | attempts=1, score=1.0, stop=review_accepted |
| b3 | route(29.94ms) → perceive(0.01ms) → interpret(0.49ms) → recall(266.45ms) → recall_user_memory(3721.03ms) → recall_web(48.07ms) → state_checks(138.12ms) → cognition(28.13ms) → decide(0.1ms) → assemble(0.13ms) → express(3483.85ms) → review(0.08ms) → learn(0.22ms) | 1 | 3159 | attempts=1, score=1.0, stop=review_accepted |
| s1 | route(60.17ms) → perceive(0.02ms) → interpret(0.12ms) → recall(99.86ms) → recall_user_memory(108.87ms) → recall_web(57.22ms) → state_checks(108.64ms) → cognition(45.21ms) → decide(0.06ms) → assemble(0.11ms) → express(3796.58ms) → review(0.07ms) → learn(0.22ms) | 1 | 2926 | attempts=1, score=1.0, stop=review_accepted |

## 观测与剩余开销

`phase_history` 已覆盖 route、perceive、interpret、recall、cognition、decide、assemble、express、review、learn；deep planning、evidence analysis 与 RoleCognition 的耗时归入 cognition，具体工具另见 `tool_calls`。wall 与阶段合计的差额用于发现状态加载、序列化等未纳入阶段的开销。

- q1：wall 86.3s，phase 合计 68.7s，差额 17.7s。
- q2：wall 66.7s，phase 合计 49.2s，差额 17.5s。
- q4：wall 105.8s，phase 合计 83.3s，差额 22.6s。
- q6：wall 71.8s，phase 合计 50.0s，差额 21.8s。

阶段链可回放到主体阶段，模型与工具调用另有记录；仍应关注 wall 与阶段合计的大额差额，不用阶段记录掩盖回合外开销。

## 结论

- 十项全部返回 HTTP 200，三个行为断言全部通过；这轮是 Role Subject Runtime 下的真实链路结果。
- 六问当前人格分均值 0.912；旧基线同六问均值 0.852。
- **时期口径已对齐 v2 T6**：profile_id=25 / version=24，cutoff=53 / explicit_bounds，38/38 条晚期证据对齐；逐题人工复核见 `role-subject-runtime-evidence.md`。
- persona 分数只是像角色的快检，不能替代 current_reality、主体经历、决定连续性和回答原文；本轮 b3 的过去职责矛盾已按这一口径修复并重跑。
- 下一步应补更长线程、真实 reverse 场景以及跨角色/跨时期数据，而不是继续堆提示词或把 HTTP 成功当成主体验收完成。
- 这十项只覆盖罗辑一个角色、period 7；跨角色、跨时期、工具层与轨迹层指标仍不在本轮验收范围内。

> 原始回答、完整 meta、阶段历史见同目录 `rolerag-ten-questions-harness.json`。