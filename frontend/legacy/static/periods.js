(() => {
  const state = { novelId: null, characterId: null, characterName: "", periods: [], selectedIndex: 0, traces: [], readyPeriodIds: new Set(), busy: false };
  const $ = selector => document.querySelector(selector);

  function setStatus(text, error = false, success = false) {
    const node = $("#period-status");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("error", error);
    node.classList.toggle("success", success);
  }

  function currentPeriod() {
    return state.periods[state.selectedIndex] || null;
  }

  function periodRange(period) {
    if (!period) return "范围未定";
    const start = period.chapter_start || "起点未定";
    const end = period.chapter_end || "终点未定";
    return `${start} → ${end}`;
  }

  function isReady(period) {
    return Boolean(period && period.id && state.readyPeriodIds.has(String(period.id)));
  }

  function renderTimeline() {
    const root = $("#period-timeline");
    if (!root) return;
    if (!state.periods.length) {
      root.innerHTML = `<div class="empty-state"><strong>还没有时期。</strong><p>点击“添加时期”，或者让 AI 先根据原文判断范围。</p></div>`;
      return;
    }
    root.innerHTML = state.periods.map((period, index) => {
      const ready = isReady(period);
      const title = period.name || "未命名时期";
      return `<div class="period-row" data-index="${index}">
        <div class="period-time">${Studio.escapeHtml(period.chapter_start || "范围未定")}<br>${Studio.escapeHtml(period.chapter_end || "—")}</div>
        <div class="period-axis ${ready ? "is-ready" : ""}"></div>
        <div class="period-card ${index === state.selectedIndex ? "active" : ""}" data-index="${index}">
          <div class="period-card-head"><strong title="${Studio.escapeHtml(title)}">${Studio.escapeHtml(title)}</strong><span class="tag ${ready ? "tag-forest" : ""}">${ready ? "画像就绪" : period.status === "confirmed" ? "已保存" : "草稿"}</span></div>
          <small>${Studio.escapeHtml(periodRange(period))}</small>
          <div class="period-card-meta"><span>${Studio.escapeHtml(period.rationale || "等待补充判断依据")}</span><span class="${ready ? "ready" : "draft"}">${ready ? "可进入对话" : "画像待生成"}</span></div>
        </div>
      </div>`;
    }).join("");
    root.querySelectorAll("[data-index]").forEach(node => {
      node.addEventListener("click", () => {
        const index = Number(node.dataset.index);
        if (Number.isInteger(index)) selectPeriod(index);
      });
    });
  }

  function renderEditor() {
    const root = $("#period-editor");
    if (!root) return;
    const period = currentPeriod();
    $("#period-selected-tag").textContent = period ? (isReady(period) ? "画像就绪" : "编辑中") : "未选择";
    $("#period-selected-tag").classList.toggle("tag-forest", Boolean(period && isReady(period)));
    if (!period) {
      root.innerHTML = `<div class="empty-state"><strong>选择一个时期。</strong><p>从左侧时间线点进一个时期，开始编辑。</p></div>`;
      return;
    }
    const keywords = Array.isArray(period.keywords) ? period.keywords.join("、") : String(period.keywords || "");
    root.innerHTML = `
      <div class="period-editor">
        <div class="period-editor-head"><strong>${Studio.escapeHtml(period.name || "未命名时期")}</strong><small>${Studio.escapeHtml(periodRange(period))} · ${isReady(period) ? "画像已生成" : "保存后会生成画像"}</small></div>
        <div class="period-form">
          <label class="field"><span>时期名称</span><input class="input" id="period-name" value="${Studio.escapeHtml(period.name || "")}" placeholder="例如：执剑人时期"></label>
          <div class="field-row">
            <label class="field"><span>起始章节</span><input class="input" id="period-start" value="${Studio.escapeHtml(period.chapter_start || "")}" placeholder="例如：第 1 章"></label>
            <label class="field"><span>结束章节</span><input class="input" id="period-end" value="${Studio.escapeHtml(period.chapter_end || "")}" placeholder="例如：第 36 章"></label>
          </div>
          <label class="field"><span>时期关键词</span><input class="input" id="period-keywords" value="${Studio.escapeHtml(keywords)}" placeholder="用顿号或逗号分隔"></label>
          <label class="field"><span>判断依据</span><textarea class="textarea" id="period-rationale" placeholder="为什么把这段人生放在一起？">${Studio.escapeHtml(period.rationale || "")}</textarea></label>
        </div>
        <div class="period-callout">时期决定角色能看见什么。保存后会按这个范围收集原文证据，生成属于这一阶段的女娲画像。</div>
        <div class="period-actions">
          <button class="btn btn-accent btn-wide" id="confirm-periods" type="button">保存时期并生成画像 <span aria-hidden="true">→</span></button>
          <button class="btn btn-ghost btn-wide" id="delete-period" type="button">删除这个时期</button>
        </div>
      </div>`;
    const nameInput = $("#period-name");
    const startInput = $("#period-start");
    const endInput = $("#period-end");
    const keywordInput = $("#period-keywords");
    const rationaleInput = $("#period-rationale");
    nameInput.addEventListener("input", () => { period.name = nameInput.value; renderTimeline(); });
    startInput.addEventListener("input", () => { period.chapter_start = startInput.value || null; renderTimeline(); });
    endInput.addEventListener("input", () => { period.chapter_end = endInput.value || null; renderTimeline(); });
    keywordInput.addEventListener("input", () => {
      period.keywords = keywordInput.value.split(/[、,，]/).map(item => item.trim()).filter(Boolean);
    });
    rationaleInput.addEventListener("input", () => { period.rationale = rationaleInput.value; });
    $("#confirm-periods").addEventListener("click", confirmPeriods);
    $("#delete-period").addEventListener("click", deletePeriod);
  }

  function selectPeriod(index) {
    state.selectedIndex = index;
    const period = currentPeriod();
    if (period?.id) {
      Studio.saveContext({ periodId: period.id, periodName: period.name || `时期 ${period.id}` });
    }
    renderTimeline();
    renderEditor();
  }

  async function loadPeriods(selectedId) {
    const periods = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/periods`);
    state.periods = Array.isArray(periods) ? periods : [];
    const wanted = selectedId || Studio.getContext().periodId;
    const index = state.periods.findIndex(period => String(period.id) === String(wanted));
    state.selectedIndex = index >= 0 ? index : 0;
    const current = currentPeriod();
    if (current?.id) Studio.saveContext({ periodId: current.id, periodName: current.name || `时期 ${current.id}` });
    renderTimeline();
    renderEditor();
    updateChatLink();
  }

  function updateChatLink() {
    const ready = state.periods.find(period => isReady(period)) || currentPeriod();
    const link = $("#chat-next");
    if (!link) return;
    if (!ready) {
      link.classList.add("hidden");
      return;
    }
    link.classList.remove("hidden");
    link.href = `/chat?novel=${encodeURIComponent(state.novelId)}&character=${encodeURIComponent(state.characterId)}&period=${encodeURIComponent(ready.id)}`;
  }

  async function analyzePeriods() {
    if (!state.characterId || state.busy) return;
    state.busy = true;
    const button = $("#analyze-periods");
    button.disabled = true;
    button.textContent = "正在判断…";
    setStatus("正在让 AI 根据原文判断时期范围…");
    try {
      const hints = state.periods.map(item => String(item.name || "").trim()).filter(Boolean);
      const result = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/period-analysis`, {
        method: "POST",
        json: { period_hints: hints }
      });
      state.periods = (result.periods || []).map(item => ({ ...item, keywords: item.keywords || [] }));
      state.selectedIndex = 0;
      $("#period-analysis").textContent = `${result.reason || "AI 已根据原文证据判断时期范围。"}${result.confidence != null ? `　置信度 ${Math.round(Number(result.confidence) * 100)}%` : ""}`;
      setStatus("AI 建议已显示。请确认范围，或直接编辑后保存。", false, true);
      renderTimeline();
      renderEditor();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      state.busy = false;
      button.disabled = false;
      button.textContent = "AI 判断范围";
    }
  }

  async function confirmPeriods() {
    if (!state.characterId || state.busy) return;
    const periods = state.periods.map(item => ({
      name: String(item.name || "").trim(),
      chapter_start: item.chapter_start || null,
      chapter_end: item.chapter_end || null,
      keywords: Array.isArray(item.keywords) ? item.keywords : String(item.keywords || "").split(/[、,，]/).filter(Boolean),
      evidence_ids: item.evidence_ids || [],
      rationale: item.rationale || "",
      confidence: Number(item.confidence || 0)
    })).filter(item => item.name);
    if (!periods.length) {
      setStatus("至少填写一个时期名称。", true);
      return;
    }
    state.busy = true;
    const button = $("#confirm-periods");
    if (button) { button.disabled = true; button.textContent = "正在保存并生成画像…"; }
    state.traces = periods.map(item => ({ name: item.name, status: "pending", result: null }));
    renderTraces();
    setStatus("正在保存时期…");
    try {
      const saved = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/periods/confirm`, {
        method: "POST",
        json: { periods }
      });
      const savedPeriods = saved.periods || [];
      state.periods = savedPeriods;
      state.selectedIndex = 0;
      let firstReady = null;
      for (let index = 0; index < savedPeriods.length; index += 1) {
        const period = savedPeriods[index];
        const trace = state.traces[index];
        trace.status = "running";
        renderTraces();
        setStatus(`正在生成第 ${index + 1} / ${savedPeriods.length} 段画像：${period.name}`);
        try {
          const result = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/periods/${period.id}/profile`, { method: "POST" });
          trace.status = "completed";
          trace.result = result;
          state.readyPeriodIds.add(String(period.id));
          if (!firstReady) firstReady = period;
        } catch (error) {
          trace.status = "failed";
          trace.error = error.message;
          setStatus(`“${period.name}”画像生成失败：${error.message}`, true);
          renderTraces();
          continue;
        }
        renderTraces();
      }
      if (firstReady) {
        const index = state.periods.findIndex(period => String(period.id) === String(firstReady.id));
        state.selectedIndex = index >= 0 ? index : 0;
        Studio.saveContext({ periodId: firstReady.id, periodName: firstReady.name });
      }
      renderTimeline();
      renderEditor();
      updateChatLink();
      const completed = state.traces.filter(item => item.status === "completed").length;
      setStatus(`已处理 ${completed} / ${state.traces.length} 段时期画像。${firstReady ? "现在可以进入对话。" : ""}`, false, Boolean(firstReady));
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      state.busy = false;
      if (button) { button.disabled = false; button.textContent = "保存时期并生成画像 →"; }
    }
  }

  async function deletePeriod() {
    if (state.periods.length <= 1) {
      setStatus("至少保留一个时期。", true);
      return;
    }
    const period = currentPeriod();
    const ok = await Studio.confirm({
      title: "删除这个时期？",
      description: "删除只影响当前编辑列表，保存后才会同步到画像流程。",
      message: `“${period?.name || "未命名时期"}”会从这次设置中移除。`,
      confirmText: "移除时期",
      danger: true
    });
    if (!ok) return;
    state.periods.splice(state.selectedIndex, 1);
    state.selectedIndex = Math.max(0, state.selectedIndex - 1);
    renderTimeline();
    renderEditor();
    setStatus("时期已从编辑列表移除，记得保存。");
  }

  function traceSummary(result) {
    const summary = result?.trace_summary || {};
    const usage = summary.usage_complete ? `${Studio.formatNumber(summary.total_tokens || 0)} tokens` : "token 未完整返回";
    return `${Studio.formatDuration(summary.duration_ms)} · ${usage}`;
  }

  function renderTraces() {
    const root = $("#trace-list");
    if (!root) return;
    if (!state.traces.length) {
      root.innerHTML = `<div class="empty-state"><strong>还没有处理记录。</strong><p>保存时期并生成画像后，每个时期的耗时和阶段会出现在这里。</p></div>`;
      return;
    }
    root.innerHTML = state.traces.map(item => {
      const result = item.result || {};
      const summary = result.trace_summary || {};
      const steps = (result.trace_steps || []).map(step => step.step_name).filter(Boolean).join(" → ") || "等待阶段返回";
      const agents = (result.trace_agents || []).map(agent => agent.agent_id).filter(Boolean).join("、") || "未调用模型 Agent";
      const statusLabel = item.status === "completed" ? "已完成" : item.status === "running" ? "处理中" : item.status === "failed" ? "失败" : "等待处理";
      return `<article class="trace-item ${item.status}">
        <div class="trace-item-head"><strong>${Studio.escapeHtml(item.name)}</strong><span>${statusLabel} · ${Studio.escapeHtml(traceSummary(result))}</span></div>
        <div class="trace-item-body">${item.error ? `错误：${Studio.escapeHtml(item.error)}` : `Agent：${Studio.escapeHtml(agents)}<br>阶段：${Studio.escapeHtml(steps)}`}${summary.trace_id ? `<br>Trace：${Studio.escapeHtml(summary.trace_id)}` : ""}</div>
      </article>`;
    }).join("");
  }

  function openTrace() {
    renderTraces();
    $("#trace-drawer").classList.add("is-open");
    $("#trace-drawer").setAttribute("aria-hidden", "false");
  }

  function closeTrace() {
    $("#trace-drawer").classList.remove("is-open");
    $("#trace-drawer").setAttribute("aria-hidden", "true");
  }

  function bind() {
    $("#analyze-periods").addEventListener("click", analyzePeriods);
    $("#add-period").addEventListener("click", () => {
      state.periods.push({ name: "新时期", chapter_start: null, chapter_end: null, keywords: [], status: "draft" });
      state.selectedIndex = state.periods.length - 1;
      renderTimeline();
      renderEditor();
      setStatus("已添加一个新时期，填写名称和范围后保存。");
    });
    $("#open-trace").addEventListener("click", openTrace);
    $("#close-trace").addEventListener("click", closeTrace);
    $("#trace-drawer").addEventListener("click", event => {
      if (event.target.id === "trace-drawer") closeTrace();
    });
  }

  async function init() {
    bind();
    const params = new URLSearchParams(location.search);
    let context = Studio.getContext();
    if ((!context.novelId || !context.characterId) && params.get("novel") && params.get("character")) {
      Studio.saveContext({ novelId: params.get("novel"), characterId: params.get("character"), periodId: params.get("period") || null });
      context = Studio.getContext();
    }
    if (!context.novelId || !context.characterId) {
      $("#no-context").style.display = "grid";
      $("#period-layout").classList.add("hidden");
      return;
    }
    state.novelId = context.novelId;
    state.characterId = context.characterId;
    state.characterName = context.characterName || `角色 ${context.characterId}`;
    $("#period-character-name").textContent = state.characterName;
    $("#period-character-note").textContent = `小说 ${context.novelId} · 选择一段时期并生成画像。`;
    try {
      const characters = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters`);
      const character = characters.find(item => String(item.id) === String(state.characterId));
      if (character?.canonical_name) {
        state.characterName = character.canonical_name;
        Studio.saveContext({ characterName: character.canonical_name });
        $("#period-character-name").textContent = state.characterName;
      }
    } catch (_) {}
    try {
      await loadPeriods();
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  init();
})();
