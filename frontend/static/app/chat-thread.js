(() => {
  if (!App.requireAuth()) return;
  const state = { detail: null, thread: null, busy: false, streamRow: null, streamText: "" };
  const $ = App.qs;
  const threadId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

  function setHeader() {
    if (!state.detail) return;
    const thread = state.detail.conversation;
    const source = App.sourceLabel(thread.source_name, "小说");
    $("#header-avatar").innerHTML = App.avatar(thread.character_name || "角色", "avatar-sm");
    $("#header-name").textContent = thread.character_name || "对话";
    $("#header-meta").innerHTML = `<span>来自 ${App.escapeHtml(source)}</span>`;
    $("#character-link").href = `/characters/${encodeURIComponent(thread.character_id)}`;
    $("#character-link").textContent = "角色主页";
  }

  function dayLabel(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const today = new Date();
    if (date.toDateString() === today.toDateString()) return "今天";
    const yesterday = new Date(today.getTime() - 86400000);
    if (date.toDateString() === yesterday.toDateString()) return "昨天";
    return date.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
  }

  function appendMessage(role, content, time = new Date().toISOString()) {
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
        <div class="message-bubble">${App.escapeHtml(content)}</div>
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
          <p>说第一句话。你们的故事从这里开始。</p>
        </div>`;
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

  function scrollBottom() {
    const scroll = $("#chat-scroll");
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }

  function setReady(ready) {
    $("#chat-input").disabled = !ready;
    $("#send-button").disabled = !ready || state.busy;
    $("#chat-input").placeholder = ready ? "写一句话…" : "这个场景还没有可用的人设";
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
        setStatus("这个场景还没有可用的人设。先到角色页准备人设，再回来对话。", true);
        const link = document.createElement("a");
        link.href = `/characters/${state.thread.character_id}/scenes`;
        link.className = "btn btn-sm";
        link.style.marginTop = "8px";
        link.textContent = "去准备人设";
        $("#chat-error").after(link);
      } else {
        setReady(true);
        setStatus("");
      }
      App.pageTitle(`${state.thread.character_name || "对话"} · 对话`);
    } catch (error) {
      $("#messages").innerHTML = `<div class="empty-state"><h3>这段对话打不开</h3><p>${App.escapeHtml(error.message)}</p><a class="btn" href="/chats">返回对话</a></div>`;
      setReady(false);
      setStatus(error.message, true);
    }
  }

  async function send() {
    if (state.busy || !state.detail || !state.thread?.period_id) return;
    const input = $("#chat-input");
    const message = input.value.trim();
    if (!message) return;
    state.busy = true;
    state.streamText = "";
    state.streamRow = null;
    input.value = "";
    input.style.height = "";
    setReady(true);
    setStatus("");
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
        mode: "quick",
        webMode: "off",
        onProgress: payload => setStatus(payload.deep ? "正在深入回答…" : "正在回答…"),
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
      setStatus("");
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
    $("#back-button").textContent = "返回对话";
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
