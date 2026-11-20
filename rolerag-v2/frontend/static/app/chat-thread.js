(() => {
  if (!App.requireAuth()) return;
  const state = { detail: null, thread: null, busy: false, streamRow: null, streamText: "", mode: "quick" };
  const $ = App.qs;
  const threadId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

  function setHeader() {
    if (!state.detail) return;
    const thread = state.detail.conversation;
    $("#header-avatar").innerHTML = App.avatar(thread.character_name || "角色");
    $("#header-name").textContent = thread.character_name || "对话";
    $("#header-meta").innerHTML = [
      thread.period_name ? `<span class="pill pill-mint pill-dot">${App.escapeHtml(thread.period_name)}</span>` : "",
      thread.source_name ? `<span class="chat-source">${App.escapeHtml(thread.source_name)}</span>` : "",
      `<span>${thread.message_count || 0} 条消息</span>`,
    ].join("");
    $("#header-avatar").className = "avatar-ring";
    $("#character-link").href = `/characters/${encodeURIComponent(thread.character_id)}`;
    $("#new-another").href = `/chats/new?character=${encodeURIComponent(thread.character_id)}${thread.period_id ? `&period=${thread.period_id}` : ""}`;
  }

  function dayLabel(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const today = new Date();
    const same = date.toDateString() === today.toDateString();
    if (same) return "今天";
    const yesterday = new Date(today.getTime() - 86400000);
    if (date.toDateString() === yesterday.toDateString()) return "昨天";
    return date.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
  }

  function appendMessage(role, content, time = new Date().toISOString(), metaText = "") {
    const thread = state.detail?.conversation;
    const root = $("#messages");
    if (!root) return null;
    root.querySelector(".chat-empty")?.remove();
    const row = document.createElement("div");
    row.className = `message ${role === "user" ? "is-user" : ""}`;
    const name = role === "user" ? "你" : (thread?.character_name || "角色");
    row.innerHTML = `
      <span class="message-avatar">${App.avatar(name, "avatar-sm")}</span>
      <div class="message-body">
        <div class="message-meta"><span class="message-author">${App.escapeHtml(name)}</span><span>${App.escapeHtml(App.formatRelative(time) || "")}</span></div>
        <div class="message-bubble">${App.escapeHtml(content)}</div>
        ${metaText ? `<div class="message-tools"><span>${App.escapeHtml(metaText)}</span></div>` : ""}
      </div>`;
    root.append(row);
    scrollBottom();
    return row;
  }

  function renderMessages() {
    const root = $("#messages");
    const thread = state.detail.conversation;
    const messages = state.detail.messages || [];
    root.innerHTML = "";
    if (!messages.length) {
      root.innerHTML = `
        <div class="chat-empty">
          <span>${App.avatar(thread.character_name || "角色", "avatar-xl")}</span>
          <h2>${App.escapeHtml(thread.character_name || "角色")}</h2>
          <p>这段对话还没有消息。先打个招呼，或者问一句他此刻最在意的事。</p>
          <div class="prompt-chips" id="thread-prompts">
            ${["你好，最近怎么样？", "说说你最近记得的一个夜晚。", "你现在最在意的是什么？"].map(prompt => `<button class="prompt-chip" type="button" data-prompt="${App.escapeHtml(prompt)}">${App.escapeHtml(prompt)}</button>`).join("")}
          </div>
        </div>`;
      bindPrompts();
      return;
    }
    let lastDay = "";
    messages.forEach(message => {
      const day = dayLabel(message.created_at);
      if (day && day !== lastDay) {
        const divider = document.createElement("div");
        divider.className = "chat-day";
        divider.textContent = day;
        root.append(divider);
        lastDay = day;
      }
      appendMessage(message.role === "user" ? "user" : "assistant", message.content || "", message.created_at);
    });
    scrollBottom();
  }

  function bindPrompts() {
    App.qsa("[data-prompt]", $("#messages")).forEach(button => button.addEventListener("click", () => {
      $("#chat-input").value = button.dataset.prompt;
      $("#chat-input").focus();
    }));
  }

  function scrollBottom() {
    const scroll = $("#chat-scroll");
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }

  function setReady(ready) {
    $("#chat-input").disabled = !ready;
    $("#send-button").disabled = !ready || state.busy;
    $("#chat-mode").disabled = !ready || state.busy;
    $("#chat-web").disabled = !ready || state.busy;
    $("#chat-input").placeholder = ready ? "写下你想说的话…" : "这个场景还没有可用的人设";
  }

  function setStatus(text, error = false) {
    const node = $("#chat-error");
    node.textContent = text || "";
    node.className = error ? "chat-error" : "success-text";
  }

  async function load() {
    if (!threadId) { location.replace("/chats"); return; }
    try {
      const data = await App.api(`/api/app/conversations/${encodeURIComponent(threadId)}`);
      state.detail = data;
      state.thread = data.conversation;
      setHeader();
      renderMessages();
      if (!data.profile_ready) {
        setReady(false);
        setStatus("这个场景还没有可用的人设。先到角色场景页生成人设，再回来对话。", true);
        const link = document.createElement("a");
        link.href = `/characters/${state.thread.character_id}/scenes`;
        link.className = "btn btn-sm";
        link.style.marginTop = "8px";
        link.textContent = "去准备人设";
        $("#chat-error").after(link);
      } else {
        setReady(true);
        setStatus("已就绪");
      }
      App.pageTitle(`${state.thread.character_name || "对话"} · 对话`);
    } catch (error) {
      $("#messages").innerHTML = `<div class="empty-state"><h3>这段对话打不开</h3><p>${App.escapeHtml(error.message)}</p><a class="btn" href="/chats">返回对话列表</a></div>`;
      setReady(false);
      setStatus(error.message, true);
    }
  }

  async function send() {
    if (state.busy || !state.detail || !state.thread?.period_id) return;
    const input = $("#chat-input");
    const message = input.value.trim();
    if (!message) return;
    const mode = $("#chat-mode").value;
    const webMode = $("#chat-web").checked ? "on" : "off";
    state.busy = true;
    state.streamText = "";
    state.streamRow = null;
    input.value = "";
    input.style.height = "";
    setReady(true);
    setStatus("正在回答…");
    const userRow = appendMessage("user", message);
    input.focus();

    const assistantRow = appendMessage("assistant", "");
    state.streamRow = assistantRow;
    const bubble = assistantRow.querySelector(".message-bubble");
    const caret = document.createElement("span");
    caret.className = "stream-caret";
    bubble.append(caret);

    try {
      const complete = await App.streamChat({
        characterId: state.thread.character_id,
        message,
        periodId: state.thread.period_id,
        threadName: state.thread.thread_name || "主对话",
        mode,
        webMode,
        onProgress: payload => setStatus(payload.deep ? "正在深入分析…" : "正在组织回答…"),
        onReset: () => {
          state.streamText = "";
          bubble.textContent = "";
          bubble.append(caret);
        },
        onToken: text => {
          state.streamText += text;
          bubble.textContent = state.streamText;
          bubble.append(caret);
          scrollBottom();
        },
      });
      const answer = complete.answer || state.streamText || "";
      bubble.textContent = answer;
      const summary = complete.trace_summary || {};
      const usage = summary.usage_complete ? `${App.formatNumber(summary.total_tokens || 0)} tokens` : "用量未完整返回";
      const modeLabel = complete.mode === "deep" ? "深入分析" : complete.mode === "auto" ? "自动模式" : "快速交谈";
      assistantRow.querySelector(".message-tools")?.remove();
      const tools = document.createElement("div");
      tools.className = "message-tools";
      tools.innerHTML = `<span>${modeLabel} · ${App.escapeHtml(usage)}</span>`;
      assistantRow.querySelector(".message-body").append(tools);
      state.thread.message_count = Number(state.thread.message_count || 0) + 2;
      setHeader();
      setStatus("已就绪");
    } catch (error) {
      assistantRow?.remove();
      userRow?.remove();
      input.value = message;
      setStatus(error.message || "发送失败，请重试。", true);
      App.toast(error.message || "发送失败，请重试。", "error");
    } finally {
      state.busy = false;
      setReady(Boolean(state.detail?.profile_ready));
      input.focus();
    }
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("chats");
    $("#back-button").innerHTML = App.icons.back;
    $("#back-button").classList.add("icon-btn");
    $("#chat-input").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        send();
      }
    });
    $("#chat-input").addEventListener("input", event => {
      const node = event.target;
      node.style.height = "auto";
      node.style.height = `${Math.min(node.scrollHeight, 150)}px`;
    });
    $("#send-button").addEventListener("click", send);
    await load();
    App.pageTitle(`${state.thread?.character_name || "对话"} · StoryRole`);
  }

  init();
})();