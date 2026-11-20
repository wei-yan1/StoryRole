(() => {
  if (!App.requireAuth()) return;
  const state = { novels: [], conversations: [], query: "" };
  const $ = App.qs;

  const statusLabels = {
    ready: "已就绪",
    processing: "解析中",
    queued: "排队中",
    uploaded: "已上传",
    failed: "解析失败",
  };

  function statusOf(novel) {
    return statusLabels[novel.status] || novel.stage || novel.status || "处理中";
  }

  function filteredNovels() {
    const query = state.query.trim().toLowerCase();
    if (!query) return state.novels;
    return state.novels.filter(novel => String(novel.name || "").toLowerCase().includes(query));
  }

  function renderStats() {
    const counts = state.summary?.counts || {};
    $("#stat-novels").textContent = counts.source_count ?? state.novels.length;
    $("#stat-characters").textContent = counts.character_count ?? "—";
    $("#stat-conversations").textContent = counts.conversation_count ?? "—";
  }

  function bookCard(novel) {
    const ready = novel.status === "ready";
    const pending = ["processing", "queued", "uploaded"].includes(novel.status);
    const statusText = statusOf(novel);
    const progress = pending && novel.total_files
      ? ` · ${novel.processed_files || 0}/${novel.total_files} 个文件`
      : "";
    return `
      <a class="book-card${ready ? "" : " is-pending"}" href="/novels/${encodeURIComponent(novel.slug || novel.novel_id)}" data-search="${App.escapeHtml(String(novel.name || "").toLowerCase())}">
        ${App.bookCover(novel.name)}
        <div class="book-caption">
          <div class="book-caption-top">
            <h3 class="book-name">${App.escapeHtml(novel.name)}</h3>
            <span class="book-arrow">${App.icons.arrow}</span>
          </div>
          <div class="book-meta">
            <span>${novel.character_count || 0} 位角色</span>
            <span class="book-meta-sep"></span>
            <span>${novel.conversation_count || 0} 段对话</span>
          </div>
          <div class="book-foot">
            <span class="book-status ${ready ? "is-ready" : ""}">${App.escapeHtml(statusText)}${progress}</span>
            <span>${App.escapeHtml(App.formatRelative(novel.last_conversation_at || novel.updated_at))}</span>
          </div>
        </div>
      </a>`;
  }

  function addCard() {
    return `
      <a class="book-card book-add" href="/novels/new">
        <span class="book-add-art">
          <span class="book-add-plus">${App.icons.plus}</span>
          <span class="book-add-label">导入小说</span>
        </span>
        <div class="book-caption">
          <div class="book-caption-top"><h3 class="book-name">新增一本小说</h3><span class="book-arrow">${App.icons.arrow}</span></div>
          <div class="book-meta"><span>TXT / Markdown</span></div>
          <div class="book-foot"><span class="book-status">放上书架</span><span>随时可以开始</span></div>
        </div>
      </a>`;
  }

  function renderBooks() {
    const items = filteredNovels();
    const grid = $("#book-grid");
    $("#novel-count").textContent = items.length ? `${items.length} 本小说` : "还没有小说";
    $("#shelf-empty").classList.toggle("hidden", state.novels.length > 0);
    grid.classList.toggle("hidden", state.novels.length === 0);
    if (!state.novels.length) {
      grid.innerHTML = "";
      return;
    }
    grid.innerHTML = items.length
      ? items.map(bookCard).join("") + addCard()
      : `<div class="book-no-match"><h3>没有找到这本小说</h3><p>换一个关键词，或者直接新增一本。</p></div>` + addCard();
  }

  function renderRecent() {
    const root = $("#recent-conversations");
    if (!state.conversations.length) {
      root.innerHTML = `<p class="aside-empty">还没有开始过的对话。从书架上选一本小说，挑一个角色，说第一句话。</p>`;
      return;
    }
    root.innerHTML = state.conversations.slice(0, 4).map(item => `
      <a class="shelf-chat-row" href="/chats/${encodeURIComponent(item.id)}">
        <span class="shelf-chat-avatar">${App.avatar(item.character_name || "?" , "avatar-sm")}</span>
        <span class="shelf-chat-copy">
          <span class="shelf-chat-name">${App.escapeHtml(item.character_name || "角色")}</span>
          <span class="shelf-chat-meta">${App.escapeHtml(item.source_name || "未命名小说")} · ${App.escapeHtml(item.period_name || "对话")}</span>
          <span class="shelf-chat-preview">${App.escapeHtml((item.last_message || "还没有消息").slice(0, 42))}</span>
        </span>
        <span class="shelf-chat-time">${App.escapeHtml(App.formatRelative(item.last_message_at || item.updated_at))}</span>
      </a>`).join("");
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("shelf");
    App.pageTitle("书架");
    $("#add-novel-top").innerHTML = `${App.icons.plus} 新增小说`;
    $("#novel-search").addEventListener("input", App.debounce(event => {
      state.query = event.target.value;
      renderBooks();
    }, 120));

    try {
      const [summary, novels, conversations] = await Promise.all([
        App.api("/api/app/summary").catch(() => ({ counts: {} })),
        App.api("/api/app/novels"),
        App.api("/api/app/conversations?limit=6").catch(() => ({ items: [] })),
      ]);
      state.summary = summary;
      state.novels = novels.items || [];
      state.conversations = conversations.items || [];
      renderStats();
      renderBooks();
      renderRecent();
    } catch (error) {
      $("#book-grid").innerHTML = `<div class="empty-state"><h3>书架暂时打不开</h3><p>${App.escapeHtml(error.message || "请稍后再试。")}</p><a class="btn" href="/">重新加载</a></div>`;
      $("#novel-count").textContent = "读取失败";
      App.toast(error.message || "读取失败", "error");
    }
  }

  init();
})();
