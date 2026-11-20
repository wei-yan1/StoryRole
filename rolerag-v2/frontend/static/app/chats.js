(() => {
  if (!App.requireAuth()) return;
  const state = { conversations: [], characters: [], summary: null, query: "" };
  const $ = App.qs;

  function renderConversations() {
    const root = $("#conversation-list");
    if (!root) return;
    const query = state.query.trim().toLowerCase();
    const items = state.conversations.filter(item => !query || [
      item.character_name, item.source_name, item.period_name, item.last_message,
    ].filter(Boolean).join(" ").toLowerCase().includes(query));
    $("#conversation-count").textContent = query ? `${items.length} / ${state.conversations.length} 段` : `${state.conversations.length} 段`;
    if (!state.conversations.length) {
      $("#inbox-stat").textContent = "还没有对话";
      root.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">${App.icons.chat}</span>
          <h3>还没有开始一段对话</h3>
          <p>从角色库选择一个角色，或者先导入一份资料来创建角色。打开对话后，你们说的每句话都会留在这里。</p>
          <a class="btn btn-primary" href="${state.characters.length ? "/chats/new" : "/characters/new"}">${state.characters.length ? "选择角色开始对话" : "先创建一个角色"}</a>
        </div>`;
      return;
    }
    if (!items.length) {
      root.innerHTML = `<div class="empty-state"><h3>没有匹配的对话</h3><p>换一个角色名、资料名或消息关键词试试。</p></div>`;
      return;
    }
    root.innerHTML = items.map(item => {
      const name = item.character_name || "未命名角色";
      const preview = (item.last_message || "这段对话还没有消息。").replace(/\s+/g, " ").trim();
      return `
        <a class="conversation-row" href="/chats/${encodeURIComponent(item.id)}">
          ${App.avatar(name)}
          <span class="conversation-main">
            <span class="conversation-top">
              <span class="conversation-name">${App.escapeHtml(name)}</span>
              ${item.period_name ? `<span class="pill">${App.escapeHtml(item.period_name)}</span>` : ""}
              <span class="pill pill-accent">${item.message_count} 条</span>
            </span>
            <span class="conversation-preview">${App.escapeHtml(preview)}</span>
            <span class="conversation-time">${App.escapeHtml(item.source_name || "资料")}</span>
          </span>
          <span class="conversation-side">
            <span class="conversation-time">${App.escapeHtml(App.formatRelative(item.last_message_at || item.updated_at))}</span>
            <span class="conversation-count">${item.last_role === "user" ? "你" : "角色"}${App.icons.arrow}</span>
          </span>
        </a>`;
    }).join("");
  }

  function renderCharacters() {
    const root = $("#recent-characters");
    if (!root) return;
    if (!state.characters.length) {
      root.innerHTML = `<p class="faint" style="font-size:11px;line-height:1.7">还没有角色。先导入一份资料，再从中创建角色。</p><a class="btn btn-sm" style="margin-top:10px" href="/characters/new">创建角色</a>`;
      $("#inbox-note").innerHTML = `${App.icons.info}<span>角色来自你导入的资料；资料只作为角色背景，不占据对话首页。</span>`;
      return;
    }
    root.innerHTML = state.characters.slice(0, 6).map(character => `
      <a class="mini-character" href="/characters/${encodeURIComponent(character.id)}">
        ${App.avatar(character.name, "avatar-sm")}
        <span class="mini-character-copy">
          <span class="mini-character-name">${App.escapeHtml(character.name)}</span>
          <span class="mini-character-meta">${character.period_count || 0} 个场景 · ${App.escapeHtml(character.source_name)}</span>
        </span>
        <span class="faint" style="font-size:10px">${character.profile_count ? "可对话" : "待准备"}</span>
      </a>`).join("");
    $("#inbox-note").innerHTML = `${App.icons.info}<span>每个角色、每个场景是独立对话；切换角色不会混在一起。</span>`;
  }

  async function init() {
    const user = await App.syncUser();
    App.mountSidebar("chats");
    App.pageTitle("对话");
    $("#new-chat-icon").innerHTML = App.icons.plus;
    $("#conversation-search").addEventListener("input", App.debounce(event => {
      state.query = event.target.value;
      renderConversations();
    }, 160));
    try {
      const [summary, conversations, characters] = await Promise.all([
        App.api("/api/app/summary"),
        App.api("/api/app/conversations"),
        App.api("/api/app/characters"),
      ]);
      state.summary = summary;
      state.conversations = conversations.items || [];
      state.characters = characters.items || [];
      const counts = summary.counts || {};
      $("#inbox-stat").textContent = `${counts.conversation_count || 0} 段对话 · ${counts.character_count || 0} 位角色`;
      renderCharacters();
      renderConversations();
    } catch (error) {
      $("#conversation-list").innerHTML = `<div class="empty-state"><h3>暂时读不到你的对话</h3><p>${App.escapeHtml(error.message)}</p><button class="btn" onclick="location.reload()">重新加载</button></div>`;
      App.toast(error.message, "error");
    }
  }

  init();
})();