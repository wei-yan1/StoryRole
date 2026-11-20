(() => {
  if (!App.requireAuth()) return;
  const state = { days: 30 };
  const $ = App.qs;

  function duration(ms) {
    const value = Number(ms || 0);
    if (value < 1000) return `${Math.round(value)} ms`;
    return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} s`;
  }

  function metricCards(totals) {
    const calls = Number(totals.calls || 0);
    const errors = Number(totals.errors || 0);
    const tokens = Number(totals.total_tokens || 0);
    const cost = App.formatCost(totals.total_cost);
    const p95 = totals.p95_latency_ms;
    const cards = [
      { label: "模型调用", value: App.formatNumber(calls), sub: `${errors} 次失败 · ${calls ? ((1 - errors / calls) * 100).toFixed(1) : "100"}% 成功` },
      { label: "Token 总量", value: App.formatNumber(tokens), sub: `${App.formatNumber(totals.input_tokens)} 输入 / ${App.formatNumber(totals.output_tokens)} 输出` },
      { label: "预估费用", value: cost, sub: "所有实际调用合计" },
      { label: "P95 延迟", value: duration(p95), sub: `平均 ${duration(totals.avg_latency_ms)}` },
    ];
    $("#metric-grid").innerHTML = cards.map(card => `
      <div class="metric-card card">
        <div class="metric-label">${card.label}</div>
        <div class="metric-value">${card.value}</div>
        <div class="metric-sub">${card.sub}</div>
      </div>`).join("");
  }

  function localDayKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function dailyChart(items) {
    const map = new Map(items.map(item => [String(item.day).slice(0, 10), item]));
    const days = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let offset = state.days - 1; offset >= 0; offset -= 1) {
      const date = new Date(today.getTime() - offset * 86400000);
      const key = localDayKey(date);
      days.push({ key, item: map.get(key) || null });
    }
    const max = Math.max(1, ...days.map(day => Number(day.item?.calls || 0)));
    $("#daily-chart").innerHTML = days.map((day, index) => {
      const calls = Number(day.item?.calls || 0);
      const height = calls ? Math.max(7, (calls / max) * 100) : 4;
      const hot = index === days.length - 1 && calls > 0;
      return `<span class="spark-bar ${hot ? "is-hot" : ""}" style="height:${height}%;" title="${day.key} · ${calls} 次调用"></span>`;
    }).join("");
    $("#daily-start").textContent = days[0]?.key || "";
    const total = days.reduce((sum, day) => sum + Number(day.item?.calls || 0), 0);
    $("#daily-note").textContent = `${total} 次调用`;
  }

  function agentBars(items) {
    const root = $("#agent-bars");
    if (!items.length) {
      root.innerHTML = `<p class="faint" style="font-size:11px;line-height:1.7">这个范围内还没有调用记录。</p>`;
      return;
    }
    const max = Math.max(1, ...items.map(item => Number(item.calls || 0)));
    root.innerHTML = items.map(item => {
      const calls = Number(item.calls || 0);
      const width = Math.round((calls / max) * 100);
      return `<div class="bar-row"><div class="bar-row-top"><span class="bar-row-name">${App.escapeHtml(item.name || "未命名")}</span><span class="bar-row-value">${App.formatNumber(calls)} 次</span></div><div class="bar-track"><div class="bar-fill mint" style="width:${width}%"></div></div></div>`;
    }).join("");
  }

  function recentTable(items) {
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
        <td data-label="操作" title="${App.escapeHtml(item.operation || "")}">${App.escapeHtml(item.operation || "—")}</td>
        <td data-label="模型" title="${App.escapeHtml(item.model || "")}"><span class="mono">${App.escapeHtml(item.model || "—")}</span></td>
        <td data-label="模块" title="${App.escapeHtml(item.agent_id || "")}">${App.escapeHtml(item.agent_id || "—")}</td>
        <td data-label="Token">${App.formatNumber(item.total_tokens)}</td>
        <td data-label="耗时">${duration(item.duration_ms)}</td>
        <td data-label="时间">${App.escapeHtml(App.formatDateTime(item.started_at))}</td>
      </tr>`).join("");
  }

  async function load() {
    try {
      const data = await App.api(`/api/app/usage?days=${state.days}`);
      metricCards(data.totals || {});
      dailyChart(data.daily || []);
      agentBars(data.by_agent || []);
      recentTable(data.recent || []);
    } catch (error) {
      App.toast(error.message || "读取用量失败", "error");
      $("#metric-grid").innerHTML = `<div class="empty-state" style="grid-column:1/-1"><h3>读取失败</h3><p>${App.escapeHtml(error.message)}</p></div>`;
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