# AgentHarness v3 quick live probe

> 生成时间：2026-11-16
> 运行条件：默认路径（不再设置 `STORYROLE_AGENT_HARNESS`）、`POSTGRES_DATABASE=three_body_agent_v2`、罗辑 `period_id=7`、quick、`web_mode=off`。
> 原始数据：`docs/agent-harness-live-probe.json`。本文件与 `docs/rolerag-persona-behavior.json` 分开，不得互相替代。
> 用例来源：`docs/agent-harness-eval.jsonl` 的 `quick_probe` suite。

## 结果

| case | 输入 | 动作链 | 延迟 | 结果 |
|---|---|---|---:|---|
| greeting | 你好。 | plan_turn → understand_event → decide → assemble_context → express → review → learn → stop | 4286.0ms | review_accepted，persona 1.0 |
| pressure_savior | 如果所有人都说你是救世主…… | plan_turn → understand_event → cognition → decide → assemble_context → express → review → learn → stop | 3490.9ms | review_accepted，persona 1.0 |
| fact_boundary | 威慑纪元发生了什么？ | plan_turn → understand_event → recall_role → timeline_guard → cognition → decide → assemble_context → express → review → learn → stop | 3690.7ms | review_accepted，persona 1.0 |
| decision_continuity | 你刚才为什么那样回答？现在还是这个决定吗？ | plan_turn → understand_event → recall_role → recall_user_memory → timeline_guard → cognition → decide → assemble_context → express → review → learn → stop | 6785.9ms | review_accepted，persona 1.0；turn_count=2，episodes=2，prior_episode_ids 非空，change_from_previous=continue |

预算：quick 默认 `max_model_calls=3`、`max_retrieve_calls=5`、`max_wall_time_ms=25000`；四例均未超预算，没有 `agent_harness_stop:*`。四例只有 `harness_context_trimmed`，表示上下文按预算裁剪了 history/role/handoff，不是行为失败。

## 这证明了什么

- `character_agent.reply()` 的默认回合在 `AgentHarness` 的 action loop 中真实运行，不是单元测试替身。
- 每个 action 都返回独立 `Observation`；`recall_role` / `timeline_guard` / `recall_user_memory` 真实经过 `ToolRuntime`。
- `plan_turn` 已成为每轮第一步，说明模式判断和召回计划由 harness 动作承载，不再是入口里的隐藏 workflow。
- 两轮 continuity 证明 `SubjectState` 的 episodes、`prior_episode_ids` 和 `change_from_previous=continue` 被下一轮消费。
- `learn` 在 `stop` 前写入经历；checkpoint 和 state store 都看到最终 subject。

## 这还没有证明什么

- quick policy 仍是确定性顺序策略，不是模型自主选择动作。
- 只有 1 个角色的 1 个时期、4 个 case；固定 eval set 已建立（5 行为 + 4 quick + 1 deep），但还没有跨角色、跨时期、失败/越界/长线程覆盖。
- `harness_context_trimmed` 仍出现在四例中；它说明上下文预算生效，但也说明还没有做到完全按需加载。
- 探针证明链路和状态，不证明“角色像不像”已经封版；后者仍要看独立评审和人工判断。
