(() => {
  const stageNames = {
    parse: "解析文档", chunk: "切分文本", embedding_and_index: "向量化与建索引",
    "a2a:query-planner": "问题规划", "a2a:deep-question-planner": "深度问题规划",
    "a2a:context-curator": "上下文整理", "a2a:relationship-state": "关系状态读取",
    "a2a:relationship-update": "关系状态更新", "a2a:timeline-guard": "时间线检查",
    "a2a:evidence-analysis": "证据分析", "a2a:role-cognition": "角色认知",
    "a2a:character-reasoning": "角色推理", "a2a:nuwa-profiler": "女娲角色画像",
    "a2a:memory-decision": "记忆决策", "a2a:consistency-guard": "一致性审查",
    "a2a:character-period-analysis": "时期分析", "a2a:web-search": "联网检索",
    answer_generation: "回答生成", query_planning: "问题规划", retrieval: "小说检索",
    context_curator: "上下文整理", reasoning: "角色推理", consistency_guard: "一致性审查",
    persistence: "结果持久化"
  };
  const statusText = { completed: "已完成", failed: "失败", running: "进行中", degraded: "降级" };
  const $ = selector => document.querySelector(selector);
  const number = value => Studio.formatNumber(Number(value || 0));
  const ms = value => value == null ? "—" : Studio.formatDuration(value);
  const cost = value => value == null ? "未配置" : Number(value).toFixed(4);
  const stageName = value => stageNames[value] || value || "未命名阶段";

  async function load() {
    try {
      $("#error").classList.add("hidden");
      const data = await Studio.api("/api/v1/models/dashboard?days=14");
      render(data);
    } catch (error) {
      $("#error").textContent = error.message;
      $("#error").classList.remove("hidden");
    }
  }

  function render(data) {
    const totals = data.totals || {};
    const runs = data.pipeline_runs || [];
    const stages = data.pipeline_stage_summary || [];
    const completedRuns = runs.filter(run => run.status === "completed" || run.status === "degraded");
    const avgRun = completedRuns.length ? completedRuns.reduce((sum, run) => sum + Number(run.duration_ms || 0), 0) / completedRuns.length : 0;
    const slowest = runs.reduce((current, run) => Number(run.duration_ms || 0) > Number(current?.duration_ms || 0) ? run : current, null);
    const errors = Number(totals.errors || 0);
    $("#period").textContent = `最近 ${data.days || 14} 天`;
    $("#pipeline-window").textContent = `最近 ${data.days || 14} 天`;
    $("#summary-title").textContent = errors ? `有 ${number(errors)} 次调用失败，先看这里。` : "系统运行平稳，继续观察成本。";
    $("#summary-copy").textContent = `当前账号：${number(totals.calls)} 次模型调用，${number(totals.total_tokens)} tokens，P95 延迟 ${ms(totals.p95_latency_ms)}。${errors ? "失败记录需要优先排查。" : "没有失败记录。"}`;
    $("#updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
    $("#totals").innerHTML = [
      ["账号调用", number(totals.calls), `${number(errors)} 次失败`],
      ["账号 token", number(totals.total_tokens), `输入 ${number(totals.input_tokens)} / 输出 ${number(totals.output_tokens)}`],
      ["账号费用", cost(totals.total_cost), "仅当前登录账号"],
      ["P95 延迟", ms(totals.p95_latency_ms), `平均 ${ms(totals.avg_latency_ms)}`],
      ["缓存命中", `${(Number(totals.cache_hit_rate || 0) * 100).toFixed(1)}%`, `命中 ${number(totals.cache_hits)} 次`]
    ].map(([label, value, note]) => `<article class="metric"><small>${label}</small><strong>${value}</strong><span>${note}</span></article>`).join("");

    const daily = data.daily || [];
    const maxCalls = Math.max(1, ...daily.map(item => Number(item.calls || 0)));
    const maxTokens = Math.max(1, ...daily.map(item => Number(item.total_tokens || 0)));
    $("#daily").innerHTML = daily.length ? daily.map(item => {
      const callHeight = Math.max(2, Number(item.calls || 0) / maxCalls * 100);
      const tokenHeight = Math.max(2, Number(item.total_tokens || 0) / maxTokens * 100);
      return `<div class="bar-col" title="${Studio.escapeHtml(String(item.usage_date))} · ${number(item.calls)} 次 · ${number(item.total_tokens)} tokens">
        <div class="bar-stack"><div class="bar" style="height:${callHeight}%"></div><div class="bar alt" style="height:${tokenHeight}%"></div></div>
        <span class="bar-label">${Studio.escapeHtml(String(item.usage_date || "").slice(5))}</span>
      </div>`;
    }).join("") : `<div class="tool-result-empty">最近 14 天没有调用记录。</div>`;

    const cache = data.embedding_cache || {};
    $("#cache").innerHTML = `<div class="cache-row"><div class="cache-cell"><small>缓存条目</small><strong>${number(cache.entries)}</strong></div><div class="cache-cell"><small>向量维度</small><strong>${number(cache.dimensions)}</strong></div></div><p class="inline-note" style="margin-top:11px">导入和检索会按模型版本与文本指纹复用向量，重复运行不会重复请求 embedding 服务。</p>`;

    const agents = data.agents || [];
    $("#agents").innerHTML = agents.length ? agents.map(item => `<div class="agent-row"><div><strong>${Studio.escapeHtml(item.agent_id || "未命名 Agent")}</strong><small>${number(item.calls)} 次 · ${number(item.total_tokens)} tokens · ${number(item.errors)} 次失败</small></div><div class="agent-stat"><b>${ms(item.avg_latency_ms)}</b>平均延迟</div></div>`).join("") : `<div class="empty-state" style="padding:10px 0"><strong>暂无 Agent 记录。</strong><p>完成一次对话或导入后，这里会出现模型在内网的调用分布。</p></div>`;

    $("#run-metrics")?.remove();
    const runMetrics = [
      ["最近运行", number(runs.length), "条流程记录"],
      ["平均耗时", ms(avgRun), `${number(completedRuns.length)} 条已结束`],
      ["最长运行", ms(slowest?.duration_ms), slowest ? stageName(slowest.run_type) : "暂无"],
      ["流程失败", number(runs.filter(run => run.status === "failed").length), "需要关注"]
    ];
    const stagesRoot = $("#pipeline-stages");
    if (stagesRoot) {
      const maxStage = Math.max(1, ...stages.map(stage => Number(stage.avg_duration_ms || 0)));
      stagesRoot.innerHTML = stages.length ? stages.map(stage => `<div class="stage-row"><span class="stage-name" title="${Studio.escapeHtml(stage.step_name || "")}">${Studio.escapeHtml(stageName(stage.step_name))}</span><div class="stage-track"><div class="stage-fill" style="width:${Math.max(2, Number(stage.avg_duration_ms || 0) / maxStage * 100)}%"></div></div><span class="stage-time">${ms(stage.avg_duration_ms)}</span></div>`).join("") : `<div class="empty-state" style="padding:10px 0"><strong>暂无阶段记录。</strong><p>完成一次导入或对话后，这里会显示耗时拆解。</p></div>`;
      const oldMetrics = document.querySelector("#pipeline-stages .run-metrics");
      if (oldMetrics) oldMetrics.remove();
      const metricBlock = document.createElement("div");
      metricBlock.className = "run-metrics";
      metricBlock.style.cssText = "display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0;margin-top:15px;border-top:1px solid var(--line)";
      metricBlock.innerHTML = runMetrics.map(([label, value, note]) => `<div class="cache-cell"><small>${label}</small><strong>${value}</strong><small>${note}</small></div>`).join("");
      stagesRoot.append(metricBlock);
    }

    $("#pipeline-runs").innerHTML = runs.length ? runs.slice(0, 7).map(run => `<div class="list-row"><div class="list-row-main"><strong>${Studio.escapeHtml(stageName(run.run_type))}</strong><small>${Studio.formatDate(run.started_at, true)} · ${number(run.model_call_count)} 次模型调用 · ${number(run.total_tokens)} tokens</small></div><span class="status-badge ${run.status === "failed" ? "fail" : run.status === "running" ? "run" : "ok"}">${statusText[run.status] || run.status || "—"} · ${ms(run.duration_ms)}</span></div>`).join("") : `<div class="empty-state" style="padding:10px 0"><strong>暂无流程记录。</strong><p>流程运行后会出现这里。</p></div>`;

    $("#recent").innerHTML = (data.recent || []).length ? data.recent.map(item => `<tr>
      <td>${Studio.formatDate(item.started_at, true)}</td>
      <td>${Studio.escapeHtml(item.agent_id || "—")}<small>${Studio.escapeHtml(item.operation || "—")}</small></td>
      <td>${Studio.escapeHtml(item.model || "—")}</td>
      <td><span class="status-badge ${item.status === "failed" ? "fail" : item.status === "running" ? "run" : "ok"}">${item.cache_hit ? "缓存命中" : statusText[item.status] || item.status || "—"}</span></td>
      <td>${number(item.total_tokens)}</td>
      <td>${ms(item.duration_ms)}</td>
      <td>${cost(item.cost)}</td>
    </tr>`).join("") : `<tr><td colspan="7"><div class="empty-state"><strong>还没有调用记录。</strong><p>完成一次对话或导入后，这里会出现逐条记录。</p></div></td></tr>`;
  }

  $("#refresh").addEventListener("click", load);
  load();
  window.setInterval(load, 30000);
})();
