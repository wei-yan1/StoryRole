(() => {
  if (!App.requireAuth()) return;
  const state = { conversations: [], summary: null, query: "" };
  const $ = App.qs;

  function latestTime(item) {
    return new Date(item.last_message_at || item.updated_at || 0).getTime() || 0;
  }

  function filteredItems() {
    const query = state.query.trim().toLowerCase();
    if (!query) return state.conversations;
    return state.conversations.filter(item => [
      item.character_name, item.source_name, item.period_name, item.last_message,
    ].filter(Boolean).join(" ").toLowerCase().includes(query));
  }

  // 同一角色只露出最近一段，避免整个列表被同一个名字刷满；
  // 更早的对话仍然可以从角色主页进入。
  function groupedConversations(items) {
    const groups = new Map();
    items.forEach(item => {
      const key = item.character_id != null ? String(item.character_id) : `name:${item.character_name}`;
      const existing = groups.get(key);
      if (!existing || latestTime(item) > latestTime(existing.latest)) {
        groups.set(key, {
          latest: item,
          count: existing ? existing.count + 1 : 1,
        });
      } else {
        existing.count += 1;
      }
    });
    return Array.from(groups.values())
      .sort((a, b) => latestTime(b.latest) - latestTime(a.latest));
  }

  function renderConversations() {
    const root = $("#conversation-list");
    if (!root) return;
    const items = filteredItems();
    const groups = groupedConversations(items);
    if (!state.conversations.length) {
      root.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">${App.icons.chat}</span>
          <h3>还没有对话</h3>
          <p>先打开一本小说，选一个已经准备好的人设，说第一句话。</p>
          <a class="btn btn-primary" href="/">去书架</a>
        </div>`;
      return;
    }
    if (!groups.length) {
      root.innerHTML = `<div class="empty-state"><h3>没有匹配的对话</h3><p>换一个角色名或消息关键词试试。</p></div>`;
      return;
    }
    root.innerHTML = groups.map(group => {
      const item = group.latest;
      const name = item.character_name || "未命名角色";
      const preview = (item.last_message || "这段对话还没有消息。").replace(/\s+/g, " ").trim();
      const source = App.sourceLabel(item.source_name, "小说");
      return `
        <a class="conversation-row" href="/chats/${encodeURIComponent(item.id)}">
          ${App.avatar(name)}
          <span class="conversation-main">
            <span class="conversation-top"><span class="conversation-name">${App.escapeHtml(name)}</span></span>
            <span class="conversation-preview">${App.escapeHtml(preview)}</span>
            <span class="conversation-source">${App.escapeHtml(source)}${group.count > 1 ? ` · 共 ${group.count} 段对话` : ""}</span>
          </span>
          <span class="conversation-side">
            <span class="conversation-time">${App.escapeHtml(App.formatRelative(item.last_message_at || item.updated_at))}</span>
            <span class="conversation-cta">继续对话</span>
          </span>
        </a>`;
    }).join("");
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("chats");
    App.pageTitle("对话");
    $("#new-chat-icon").innerHTML = App.icons.plus;
    $("#conversation-search").addEventListener("input", App.debounce(event => {
      state.query = event.target.value;
      renderConversations();
    }, 160));
    try {
      const [summary, conversations] = await Promise.all([
        App.api("/api/app/summary"),
        App.api("/api/app/conversations"),
      ]);
      state.summary = summary;
      state.conversations = conversations.items || [];
      const counts = summary.counts || {};
      const groupCount = groupedConversations(state.conversations).length;
      $("#inbox-stat").textContent = `${groupCount} 位角色 · ${counts.conversation_count || state.conversations.length} 段对话`;
      renderConversations();
    } catch (error) {
      $("#conversation-list").innerHTML = `<div class="empty-state"><h3>暂时读不到你的对话</h3><p>${App.escapeHtml(error.message)}</p><button class="btn" onclick="location.reload()">重新加载</button></div>`;
      App.toast(error.message, "error");
    }
  }

  init();
})();
