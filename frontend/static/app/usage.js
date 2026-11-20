(() => {
  if (!App.requireAuth()) return;
  const state = { days: 30 };
  const $ = App.qs;

  const STAGES = {
    dialogue: { label: "角色对话", desc: "聊天回合与角色回答", order: 1 },
    scenario: { label: "场景分析", desc: "从小说整理时间线与场景", order: 2 },
    persona: { label: "人设生成", desc: "女娲画像与阶段人设", order: 3 },
    assistant: { label: "对话辅助", desc: "理解、推理与一致性检查", order: 4 },
    retrieval: { label: "检索与重排", desc: "向量检索与候选重排", order: 5 },
    tools: { label: "工具调用", desc: "图片、文字、语音与翻译", order: 6 },
    other: { label: "其他调用", desc: "尚未归类的模型请求", order: 7 },
  };

  const OPERATION_LABELS = {
    storyrole_answer_generation: "角色回答生成",
    nuwa_profile: "人设画像生成",
    period_analysis: "场景时间线分析",
    character_reasoning: "角色推理",
    role_cognition: "角色认知",
    evidence_analysis: "证据分析",
    deep_question_planning: "深度问题规划",
    consistency_guard: "一致性检查",
    embedding: "向量检索",
    rerank: "候选重排",
    media_image: "图片生成",
    media_ocr: "文字识别",
    media_describe: "图片理解",
    media_speech: "语音合成",
    media_transcribe: "语音转写",
    media_translate: "翻译",
  };

  const AGENT_LABELS = {
    "character-conversation": "对话回合",
    "character-period-analysis": "场景时间线",
    "nuwa-profiler": "人设画像",
    "character-reasoning": "角色推理",
    "role-cognition": "角色认知",
    "evidence-analysis": "证据分析",
    "deep-question-planner": "深度问题规划",
    "consistency-guard": "一致性检查",
    embedding: "向量检索",
    reranker: "候选重排",
  };

  function duration(ms) {
    const value = Number(ms || 0);
    if (value < 1000) return `${Math.round(value)} ms`;
    return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} s`;
  }

  function stageInfo(stage) {
    return STAGES[stage] || STAGES.other;
  }

  function operationLabel(item) {
    return OPERATION_LABELS[item.operation] || item.operation || item.agent_id || "—";
  }

  function agentLabel(item) {
    return AGENT_LABELS[item.name] || AGENT_LABELS[item.agent_id] || operationLabel(item);
  }

  function renderOverview(totals, days) {
    const calls = Number(totals.calls || 0);
    const errors = Number(totals.errors || 0);
    const success = calls ? ((1 - errors / calls) * 100).toFixed(1) : "100";
    $("#stat-calls").textContent = App.formatNumber(calls);
    $("#stat-calls-sub").textContent = `${errors} 次失败 · ${success}% 成功`;
    $("#stat-tokens").textContent = App.formatNumber(totals.total_tokens);
    $("#stat-tokens-sub").textContent = `${App.formatNumber(totals.input_tokens)} 输入 / ${App.formatNumber(totals.output_tokens)} 输出`;
    $("#stat-cost").textContent = App.formatCost(totals.total_cost);
    $("#stat-latency").textContent = duration(totals.p95_latency_ms);
    $("#stat-latency-sub").textContent = `平均 ${duration(totals.avg_latency_ms)}`;
    $("#usage-period").textContent = `近 ${days} 天 · 当前账号`;
  }

  function renderStages(items) {
    const root = $("#stage-grid");
    if (!items || !items.length) {
      root.innerHTML = `<div class="stage-empty"><h3>这个范围内还没有可分组的数据</h3><p>开始一段对话或使用一次工具后，这里会按任务环节自动出现统计。</p></div>`;
      return;
    }
    const sorted = [...items].sort((a, b) => stageInfo(a.stage).order - stageInfo(b.stage).order);
    const maxCalls = Math.max(1, ...sorted.map(item => Number(item.calls || 0)));
    root.innerHTML = sorted.map(item => {
      const info = stageInfo(item.stage);
      const calls = Number(item.calls || 0);
      const width = Math.max(4, Math.round((calls / maxCalls) * 100));
      return `
        <article class="stage-card stage-${App.escapeHtml(item.stage || "other")}">
          <div class="stage-card-head">
            <span class="stage-index">${String(info.order).padStart(2, "0")}</span>
            <div class="stage-title-wrap"><h3 class="stage-title">${info.label}</h3><p class="stage-desc">${info.desc}</p></div>
            <strong class="stage-calls">${App.formatNumber(calls)} 次</strong>
          </div>
          <div class="stage-metrics">
            <span><label>Token</label><strong>${App.formatNumber(item.total_tokens)}</strong></span>
            <span><label>费用</label><strong>${App.formatCost(item.total_cost)}</strong></span>
            <span><label>平均延迟</label><strong>${duration(item.avg_latency_ms)}</strong></span>
            <span><label>失败</label><strong>${App.formatNumber(item.errors)}</strong></span>
          </div>
          <div class="stage-bar"><span style="width:${width}%"></span></div>
        </article>`;
    }).join("");
  }

  function localDayKey(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  function renderDaily(items) {
    const map = new Map(items.map(item => [String(item.day).slice(0, 10), item]));
    const days = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let offset = state.days - 1; offset >= 0; offset -= 1) {
      const date = new Date(today.getTime() - offset * 86400000);
      days.push({ key: localDayKey(date), item: map.get(localDayKey(date)) || null });
    }
    const max = Math.max(1, ...days.map(day => Number(day.item?.calls || 0)));
    $("#daily-chart").innerHTML = days.map((day, index) => {
      const calls = Number(day.item?.calls || 0);
      const height = calls ? Math.max(8, (calls / max) * 100) : 4;
      return `<span class="spark-bar ${index === days.length - 1 && calls > 0 ? "is-hot" : ""}" style="height:${height}%" title="${day.key} · ${calls} 次调用"></span>`;
    }).join("");
    $("#daily-start").textContent = days[0]?.key || "";
    $("#daily-note").textContent = `${App.formatNumber(days.reduce((sum, day) => sum + Number(day.item?.calls || 0), 0))} 次`;
  }

  function renderAgents(items) {
    const root = $("#agent-bars");
    if (!items.length) {
      root.innerHTML = `<p class="field-hint">没有可细分的操作。</p>`;
      return;
    }
    const max = Math.max(1, ...items.map(item => Number(item.calls || 0)));
    root.innerHTML = items.slice(0, 10).map(item => `
      <div class="bar-row">
        <div class="bar-row-top"><span class="bar-row-name">${App.escapeHtml(stageInfo(item.stage).label)} · ${App.escapeHtml(agentLabel(item))}</span><span class="bar-row-value">${App.formatNumber(item.calls)} 次</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.round((Number(item.calls || 0) / max) * 100)}%"></div></div>
      </div>`).join("");
  }

  function renderRecent(items) {
    const tbody = $("#recent-table tbody");
    if (!items.length) {
      tbody.innerHTML = "";
      $("#recent-table-wrap").classList.add("hidden");
      $("#usage-empty").classList.remove("hidden");
      return;
    }
    $("#recent-table-wrap").classList.remove("hidden");
    $("#usage-empty").classList.add("hidden");
    tbody.innerHTML = items.map(item => `
      <tr>
        <td data-label="任务环节"><span class="table-stage">${App.escapeHtml(stageInfo(item.stage).label)}</span></td>
        <td data-label="具体操作" title="${App.escapeHtml(item.operation || "")}">${App.escapeHtml(operationLabel(item))}</td>
        <td data-label="模型"><span class="mono">${App.escapeHtml(item.model || "—")}</span></td>
        <td data-label="Token">${App.formatNumber(item.total_tokens)}</td>
        <td data-label="耗时">${duration(item.duration_ms)}</td>
        <td data-label="时间">${App.escapeHtml(App.formatDateTime(item.started_at))}</td>
      </tr>`).join("");
  }

  async function load() {
    try {
      const data = await App.api(`/api/app/usage?days=${state.days}`);
      renderOverview(data.totals || {}, data.days || state.days);
      renderStages(data.by_stage || []);
      renderDaily(data.daily || []);
      renderAgents(data.by_agent || []);
      renderRecent(data.recent || []);
    } catch (error) {
      App.toast(error.message || "读取用量失败", "error");
      $("#stage-grid").innerHTML = `<div class="empty-state"><h3>读取失败</h3><p>${App.escapeHtml(error.message || "请稍后再试。")}</p></div>`;
    }
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("usage");
    App.pageTitle("用量");
    $("#usage-range").value = String(state.days);
    $("#usage-range").addEventListener("change", event => {
      state.days = Number(event.target.value);
      load();
    });
    await load();
  }

  init();
})();
