(() => {
  const state = { novelId: null, characterId: null, characterName: "", periods: [], periodId: null, busy: false, retrying: false, lastMessage: "" };
  const $ = selector => document.querySelector(selector);
  const stepNames = {
    query_planning: "判断问题意图",
    deep_question_planning: "深度拆解问题",
    novel_retrieval: "检索小说证据",
    evidence_rerank: "筛选相关证据",
    evidence_analysis: "分析原文证据",
    role_cognition: "梳理角色立场",
    consistency_review: "检查回答一致性",
    answer_generation: "生成角色回答"
  };

  function setStatus(text, busy = false, error = false) {
    const node = $("#chat-status");
    if (!node) return;
    node.classList.toggle("busy", busy);
    node.classList.toggle("error", error);
    const dot = node.querySelector(".status-dot");
    if (dot) {
      dot.classList.toggle("busy", busy);
      dot.classList.toggle("error", error);
      dot.classList.toggle("ok", !busy && !error);
    }
    const copy = node.querySelector("span");
    if (copy) copy.textContent = text;
  }

  function setReady(ready, busy = false) {
    const input = $("#chat-input");
    const button = $("#send-button");
    if (input) {
      input.disabled = !ready || busy;
      input.placeholder = ready ? "问问他，现在在想什么……" : "请先选择一个时期";
    }
    if (button) button.disabled = !ready || busy;
    if (busy) setStatus("正在回答", true);
  }

  function fillPeriods() {
    const select = $("#period-select");
    const list = $("#period-list");
    if (!select || !list) return;
    select.replaceChildren();
    if (!state.periods.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "还没有可用的时期";
      select.append(option);
      select.disabled = true;
      list.innerHTML = `<span class="inline-note">先到时期页生成画像。</span>`;
      return;
    }
    select.disabled = false;
    state.periods.forEach(period => {
      const option = document.createElement("option");
      option.value = period.id;
      option.textContent = period.name || "未命名时期";
      option.selected = String(period.id) === String(state.periodId);
      select.append(option);
    });
    list.innerHTML = state.periods.map(period => `
      <button class="chat-period-button ${String(period.id) === String(state.periodId) ? "active" : ""}" type="button" data-period="${Studio.escapeHtml(period.id)}">
        <span>${Studio.escapeHtml(period.name || "未命名时期")}</span><b>${period.chapter_start || "—"} → ${period.chapter_end || "—"}</b>
      </button>
    `).join("");
    list.querySelectorAll("[data-period]").forEach(button => {
      button.addEventListener("click", () => choosePeriod(button.dataset.period));
    });
    const current = state.periods.find(period => String(period.id) === String(state.periodId));
    $("#chat-period-tag").textContent = current?.name || "时期未选择";
    $("#chat-period-note").textContent = current ? `当前时期：${current.name || "未命名时期"}` : "先完成时期画像";
    state.characterName && ($("#chat-title").textContent = `与${state.characterName}交谈`);
    $("#chat-subtitle").textContent = current ? `${current.chapter_start || "起点未定"} → ${current.chapter_end || "终点未定"}` : "选择时期后开始对话";
  }

  function clearLog() {
    const root = $("#messages");
    if (root) root.replaceChildren();
  }

  function showEmptyLog(title = "先开始一段对话。", copy = "他会根据当前时期的证据、身份和关系回答你。") {
    const root = $("#messages");
    if (!root) return;
    root.innerHTML = `<div class="chat-log-empty"><div><div class="quote">“</div><h2>${Studio.escapeHtml(title)}</h2><p>${Studio.escapeHtml(copy)}</p></div></div>`;
  }

  function appendMessage(role, content, meta = "") {
    const root = $("#messages");
    if (!root) return null;
    root.querySelector(".chat-log-empty")?.remove();
    const row = document.createElement("div");
    row.className = `message-row ${role}`;
    const label = document.createElement("small");
    label.className = "message-role";
    label.textContent = role === "user" ? "你" : role === "assistant" ? (state.characterName || "角色") : "系统";
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = content;
    const info = document.createElement("small");
    info.className = "message-meta";
    if (meta) info.textContent = meta;
    row.append(label, bubble);
    if (meta) row.append(info);
    root.append(row);
    root.scrollTop = root.scrollHeight;
    return row;
  }

  function appendError(message, failedMessage) {
    const row = appendMessage("system", message, "请求失败");
    if (!row) return;
    const info = row.querySelector(".message-meta");
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "retry-button";
    retry.title = "重试";
    retry.setAttribute("aria-label", "重试");
    retry.textContent = "↻";
    retry.addEventListener("click", () => {
      row.remove();
      state.retrying = true;
      $("#chat-input").value = failedMessage;
      $("#chat-form").requestSubmit();
    });
    info.append(retry);
  }

  async function loadHistory() {
    clearLog();
    if (!state.novelId || !state.characterId || !state.periodId) {
      showEmptyLog("选择一个时期。", "时期决定角色记得什么。完成画像后，这里会出现你们的对话。");
      setReady(false);
      return;
    }
    try {
      const result = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/chat/history?period_id=${encodeURIComponent(state.periodId)}`);
      const messages = result.messages || [];
      if (!messages.length) {
        showEmptyLog("先开始一段对话。", "他会根据当前时期的证据、身份和关系回答你。");
      } else {
        messages.forEach(message => {
          appendMessage(message.role === "user" ? "user" : "assistant", message.content || "", message.role === "assistant" ? "历史消息" : "");
        });
      }
      setReady(true);
      setStatus("已就绪");
    } catch (error) {
      showEmptyLog("对话还没有准备好。", "如果这个时期还没有女娲画像，请先回到时期页生成。");
      setStatus(error.message, false, true);
    }
  }

  async function choosePeriod(id) {
    if (state.busy) return;
    const period = state.periods.find(item => String(item.id) === String(id));
    if (!period) return;
    state.periodId = period.id;
    Studio.saveContext({ periodId: period.id, periodName: period.name || `时期 ${period.id}` });
    fillPeriods();
    await loadHistory();
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const input = $("#chat-input");
    const message = input.value.trim();
    const mode = $("#chat-mode").value;
    const webMode = $("#web-mode").checked ? "on" : "off";
    if (!message || state.busy || !state.periodId) return;
    const isRetry = Boolean(state.retrying);
    state.busy = true;
    state.retrying = false;
    state.lastMessage = message;
    input.value = "";
    input.style.height = "";
    setReady(true, true);
    const userRow = appendMessage("user", message);
    let answerRow = null;
    let streamedText = "";
    let result = null;
    let streamError = null;
    try {
      const response = await fetch(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/chat/stream`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
          "Content-Type": "application/json",
          Accept: "text/event-stream"
        },
        body: JSON.stringify({
          message,
          period_id: state.periodId,
          mode,
          web_mode: webMode,
          debug: true,
          retry: isRetry
        })
      });
      if (response.status === 401) {
        Studio.logout();
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "对话请求失败");
      }
      if (!response.body) throw new Error("浏览器不支持流式响应");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const handle = block => {
        if (!block.trim()) return;
        const eventName = block.match(/^event:\s*(.+)$/m)?.[1] || "message";
        const data = block.split(/\r?\n/).filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n");
        let payload = {};
        try { payload = JSON.parse(data); } catch (_) { return; }
        if (eventName === "progress") {
          setStatus(`${payload.deep ? "深度分析 · " : "处理中 · "}${stepNames[payload.step] || payload.step || "处理中"}`, true);
        } else if (eventName === "heartbeat") {
          return;
        } else if (eventName === "reset") {
          streamedText = "";
          if (answerRow) answerRow.querySelector(".message-bubble").textContent = "";
        } else if (eventName === "token") {
          if (!answerRow) answerRow = appendMessage("assistant", "");
          const bubble = answerRow.querySelector(".message-bubble");
          streamedText += payload.text || "";
          bubble.textContent = streamedText;
          const caret = document.createElement("span");
          caret.className = "stream-caret";
          bubble.append(caret);
          $("#messages").scrollTop = $("#messages").scrollHeight;
        } else if (eventName === "complete") {
          result = payload;
        } else if (eventName === "error") {
          streamError = new Error(payload.message || "对话失败");
        }
      };
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || "";
        blocks.forEach(handle);
        if (done) break;
      }
      if (buffer.trim()) handle(buffer);
      if (streamError) throw streamError;
      if (!result) throw new Error("流式响应提前结束，未收到完成事件");
      if (!answerRow) answerRow = appendMessage("assistant", result.answer || "");
      const bubble = answerRow.querySelector(".message-bubble");
      bubble.textContent = result.answer || streamedText;
      const summary = result.trace_summary || {};
      const usage = summary.usage_complete ? `${Studio.formatNumber(summary.total_tokens || 0)} tokens` : "token 未完整返回";
      const meta = answerRow.querySelector(".message-meta") || document.createElement("small");
      meta.className = "message-meta";
      meta.textContent = `${result.mode === "deep" ? "深入分析" : result.mode === "auto" ? "自动模式" : "快速交谈"} · ${Studio.formatDuration(summary.duration_ms ?? result.latency_ms)} · ${usage}`;
      if (!meta.parentElement) answerRow.append(meta);
      const agents = (result.trace_agents || []).map(agent => agent.agent_id).filter(Boolean).join("、") || "无模型 Agent";
      const steps = (result.trace_steps || []).map(step => step.step_name).filter(Boolean).join(" → ") || "无阶段记录";
      $("#trace-display").textContent = `${agents} · ${steps}`;
      $("#trace-display").title = `${agents} · ${steps}`;
      setStatus("已就绪");
    } catch (error) {
      userRow?.remove();
      answerRow?.remove();
      appendError(error.message, message);
      setStatus(error.message, false, true);
      const inputNode = $("#chat-input");
      inputNode.value = message;
      inputNode.focus();
    } finally {
      state.busy = false;
      setReady(Boolean(state.periodId), false);
        }
  }

  function bind() {
    $("#chat-form").addEventListener("submit", sendMessage);
    $("#chat-input").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        $("#chat-form").requestSubmit();
      }
    });
    $("#chat-input").addEventListener("input", event => {
      const node = event.target;
      node.style.height = "auto";
      node.style.height = `${Math.min(node.scrollHeight, 145)}px`;
    });
    $("#period-select").addEventListener("change", event => choosePeriod(event.target.value));
    $("#chat-mode").addEventListener("change", event => {
      const labels = { quick: "快速交谈", deep: "深入分析", auto: "自动模式" };
      $("#chat-mode-tag").textContent = labels[event.target.value] || "快速交谈";
    });
    document.querySelectorAll("[data-prompt]").forEach(button => {
      button.addEventListener("click", () => {
        $("#chat-input").value = button.dataset.prompt;
        $("#chat-input").focus();
      });
    });
  }

  async function init() {
    bind();
    const params = new URLSearchParams(location.search);
    let context = Studio.getContext();
    if ((!context.novelId || !context.characterId) && params.get("novel") && params.get("character")) {
      Studio.saveContext({
        novelId: params.get("novel"),
        characterId: params.get("character"),
        periodId: params.get("period") || null
      });
      context = Studio.getContext();
    }
    if (!context.novelId || !context.characterId) {
      $("#chat-empty").style.display = "grid";
      $("#chat-layout").classList.add("hidden");
      return;
    }
    state.novelId = context.novelId;
    state.characterId = context.characterId;
    state.characterName = context.characterName || `角色 ${context.characterId}`;
    $("#chat-empty").style.display = "none";
    $("#chat-layout").classList.remove("hidden");
    $("#character-name").textContent = state.characterName;
    $("#character-note").textContent = `角色 ${context.characterId} · 只使用当前时期可见的证据。`;
    $("#chat-title").textContent = `与${state.characterName}交谈`;
    try {
      const library = await Studio.api("/api/v1/novels/library");
      const novel = library.find(item => String(item.novel_id) === String(state.novelId));
      if (novel?.novel_name) Studio.saveContext({ novelName: novel.novel_name });
    } catch (_) {}
    try {
      const characters = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters`);
      const character = characters.find(item => String(item.id) === String(state.characterId));
      if (character?.canonical_name) {
        state.characterName = character.canonical_name;
        Studio.saveContext({ characterName: character.canonical_name });
        $("#character-name").textContent = state.characterName;
        $("#chat-title").textContent = `与${state.characterName}交谈`;
        $("#character-note").textContent = `${Studio.formatNumber(character.mention_count || 0)} 次原文提及 · 当前时期可见证据。`;
      }
    } catch (_) {}
    try {
      state.periods = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/periods`);
      const wanted = context.periodId;
      const selected = state.periods.find(period => String(period.id) === String(wanted)) || state.periods[0];
      state.periodId = selected?.id || null;
      if (selected) Studio.saveContext({ periodId: selected.id, periodName: selected.name || `时期 ${selected.id}` });
      fillPeriods();
      await loadHistory();
    } catch (error) {
      fillPeriods();
      showEmptyLog("还没有可用的时期。", "先到时期画像页完成一次时期设置和画像生成。");
      setReady(false);
      setStatus(error.message, false, true);
    }
  }

  init();
})();
