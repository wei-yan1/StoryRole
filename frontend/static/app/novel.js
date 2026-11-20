(() => {
  if (!App.requireAuth()) return;
  const state = { novelId: "", detail: null, conversations: [] };
  const $ = App.qs;
  const statusLabels = {
    ready: "已就绪",
    processing: "解析中",
    queued: "排队中",
    uploaded: "已上传",
    failed: "解析失败",
  };

  function pathNovelId() {
    const parts = location.pathname.split("/").filter(Boolean);
    return decodeURIComponent(parts[parts.length - 1] || "");
  }

  function statusOf(novel) {
    return statusLabels[novel.status] || novel.stage || novel.status || "处理中";
  }

  function characterCard(character) {
    const ready = Number(character.profile_count || 0) > 0;
    const chatHref = `/chats/new?character=${encodeURIComponent(character.id)}`;
    return `
      <article class="cast-card" data-character-id="${character.id}">
        <div class="cast-head">
          ${App.avatar(character.name, "avatar-lg")}
          <div class="cast-copy">
            <h3 class="cast-name">${App.escapeHtml(character.name)}</h3>
            <p class="cast-meta">${character.mention_count || 0} 次提及 · ${character.period_count || 0} 个场景</p>
          </div>
          <span class="cast-state ${ready ? "is-ready" : ""}">${ready ? "可对话" : "待准备"}</span>
        </div>
        <p class="cast-summary">${App.escapeHtml(character.summary || "还没有角色摘要。进入角色页可以查看已经整理的人设与场景。")}</p>
        <div class="cast-foot">
          <span class="cast-version">${character.latest_profile_version ? `人设 v${character.latest_profile_version}` : "还没有人设"}</span>
          <div class="cast-actions">
            <a class="btn btn-sm" href="/characters/${encodeURIComponent(character.id)}">进入角色</a>
            <a class="btn btn-sm btn-primary" href="${ready ? chatHref : `/characters/${encodeURIComponent(character.id)}/scenes`}">${ready ? "开始对话" : "准备人设"}</a>
          </div>
        </div>
      </article>`;
  }

  function render() {
    const detail = state.detail;
    const novel = detail.novel;
    const characters = detail.characters || [];
    const ready = characters.filter(item => Number(item.profile_count || 0) > 0).length;
    const periods = characters.reduce((sum, item) => sum + Number(item.period_count || 0), 0);
    const status = statusOf(novel);
    const recent = state.conversations.slice(0, 4);
    $("#novel-root").innerHTML = `
      <nav class="novel-breadcrumb" aria-label="面包屑">
        <a href="/">书架</a><span>/</span><span>${App.escapeHtml(novel.name)}</span>
      </nav>

      <section class="novel-hero">
        <div class="novel-cover-wrap">${App.bookCover(novel.name, "book-cover-large")}</div>
        <div class="novel-copy">
          <p class="novel-kicker">${novel.source_kind === "bundled" ? "内置示例小说" : "我的小说"}</p>
          <h1 class="novel-title">${App.escapeHtml(novel.name)}</h1>
          <p class="novel-lead">这本书是角色的世界。先浏览角色，再选择一个角色进入对话；每个角色只知道自己这本书里的事。</p>
          <div class="novel-status-line">
            <span class="novel-status-dot ${novel.status === "ready" ? "is-ready" : ""}"></span>
            <span>${App.escapeHtml(status)}</span>
            ${novel.chunk_count ? `<span class="novel-dot">·</span><span>${App.formatNumber(novel.chunk_count)} 个片段</span>` : ""}
            <span class="novel-dot">·</span><span>更新于 ${App.escapeHtml(App.formatRelative(novel.updated_at))}</span>
          </div>
          <div class="novel-stats">
            <div class="novel-stat"><strong>${characters.length}</strong><span>位角色</span></div>
            <div class="novel-stat"><strong>${periods}</strong><span>个场景</span></div>
            <div class="novel-stat"><strong>${novel.conversation_count || 0}</strong><span>段对话</span></div>
            <div class="novel-stat"><strong>${ready}</strong><span>可对话角色</span></div>
          </div>
          <div class="novel-actions">
            <a class="btn btn-primary" href="/characters/new?source=${encodeURIComponent(novel.novel_id)}" id="add-character">添加角色</a>
            <a class="btn" href="/novels/new">导入另一本小说</a>
          </div>
        </div>
      </section>

      <section class="roster-section">
        <div class="section-head roster-head">
          <div>
            <h2 class="section-title">这本书里的角色</h2>
            <p class="section-desc">点开一个角色，查看人设与场景，或者直接开始对话。</p>
          </div>
          <span class="roster-count">${characters.length} 位</span>
        </div>
        ${characters.length ? `<div class="cast-grid">${characters.map(characterCard).join("")}</div>` : `
          <div class="empty-state novel-empty">
            <span class="empty-icon">${App.icons.people}</span>
            <h3>这本书还没有角色</h3>
            <p>先从一个在原文里出现过的名字开始。系统会从这本书里为它整理身份、场景与人设。</p>
            <a class="btn btn-primary" href="/characters/new?source=${encodeURIComponent(novel.novel_id)}">添加第一个角色</a>
          </div>`}
      </section>

      ${recent.length ? `
      <section class="novel-recent">
        <div class="section-head">
          <h2 class="section-title">最近在这本书里发生</h2>
          <a class="section-link" href="/chats">全部对话</a>
        </div>
        <div class="novel-chat-list">
          ${recent.map(item => `
            <a class="novel-chat-row" href="/chats/${encodeURIComponent(item.id)}">
              ${App.avatar(item.character_name || "?", "avatar-sm")}
              <span class="novel-chat-copy">
                <span class="novel-chat-name">${App.escapeHtml(item.character_name || "角色")}</span>
                <span class="novel-chat-preview">${App.escapeHtml((item.last_message || "刚刚开始").slice(0, 68))}</span>
              </span>
              <span class="novel-chat-period">${App.escapeHtml(item.period_name || "对话")}</span>
              <span class="novel-chat-time">${App.escapeHtml(App.formatRelative(item.last_message_at || item.updated_at))}</span>
            </a>`).join("")}
        </div>
      </section>` : ""}
    `;
    $("#add-character").innerHTML = `${App.icons.plus} 添加角色`;
    App.qsa(".cast-card").forEach(card => {
      card.addEventListener("click", event => {
        if (event.target.closest("a")) return;
        location.href = `/characters/${encodeURIComponent(card.dataset.characterId)}`;
      });
    });
    App.pageTitle(`${novel.name} · 小说`);
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("shelf");
    state.novelId = pathNovelId();
    if (!state.novelId) { location.replace("/"); return; }
    try {
      const detail = await App.api(`/api/app/novels/${encodeURIComponent(state.novelId)}`);
      state.detail = detail;
      state.novelId = String(detail.novel?.novel_id || state.novelId);
      const conversations = await App.api(`/api/app/conversations?limit=8&novel_id=${encodeURIComponent(state.novelId)}`).catch(() => ({ items: [] }));
      state.conversations = conversations.items || [];
      render();
    } catch (error) {
      $("#novel-root").innerHTML = `<div class="empty-state"><h3>这本书暂时打不开</h3><p>${App.escapeHtml(error.message || "请稍后再试。")}</p><a class="btn" href="/">回到书架</a></div>`;
      App.toast(error.message || "读取失败", "error");
    }
  }

  init();
})();
