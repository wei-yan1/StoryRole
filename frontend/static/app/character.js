(() => {
  if (!App.requireAuth()) return;
  const state = { detail: null, conversations: [] };
  const $ = App.qs;
  const characterId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

  function hasValue(value) {
    if (value === null || value === undefined || value === "") return false;
    if (typeof value === "string" && ["—", "-", "暂无", "无"].includes(value.trim())) return false;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "object") return Object.keys(value).length > 0;
    return true;
  }

  function renderValue(value) {
    if (!hasValue(value)) return "";
    if (Array.isArray(value)) {
      return `<ul>${value.map(item => `<li>${App.escapeHtml(typeof item === "object" ? JSON.stringify(item) : item)}</li>`).join("")}</ul>`;
    }
    if (typeof value === "object") {
      return `<ul>${Object.entries(value).map(([key, item]) => `<li><strong>${App.escapeHtml(key)}</strong>：${App.escapeHtml(typeof item === "object" ? JSON.stringify(item) : item)}</li>`).join("")}</ul>`;
    }
    return App.escapeHtml(value);
  }

  function firstReadyPeriod(periods) {
    return (periods || []).find(period => period.profile_ready);
  }

  function pickProfile(profile, ...keys) {
    for (const key of keys) {
      const value = profile?.[key];
      if (hasValue(value)) return value;
    }
    return null;
  }

  function renderProfile(profile, character, scenesHref) {
    if (!profile) {
      return `
        <div class="character-empty">
          <span class="character-empty-mark">${App.icons?.spark || ""}</span>
          <div class="character-empty-copy">
            <h3>还没有人设</h3>
            <p>这个角色还没有选定的场景。先准备一个阶段的人设，他才会带着那一段记忆和语气进入对话。</p>
          </div>
        </div>`;
    }
    const fields = [
      ["语言风格", pickProfile(profile, "语言风格", "speech_style")],
      ["情绪底色", pickProfile(profile, "情绪底色", "emotional_patterns", "personality")],
      ["核心信念", pickProfile(profile, "核心信念", "core_beliefs")],
      ["当前状态", pickProfile(profile, "当前人格状态", "当前状态", "current_state", "identity")],
    ].filter(([, value]) => hasValue(value));
    if (!fields.length) {
      return `
        <div class="character-empty">
          <span class="character-empty-mark">${App.icons?.spark || ""}</span>
          <div class="character-empty-copy">
            <h3>人设内容还没有整理出来</h3>
            <p>场景已经存在，但这个阶段还没有可读的人格描述。重新准备一次人设即可。</p>
          </div>
        </div>`;
    }
    const stage = pickProfile(profile, "阶段定位", "period_stage", "period_name");
    return `
      <div class="character-profile-grid">
        ${fields.map(([label, value]) => `
          <div class="character-profile-block">
            <div class="character-profile-label">${label}</div>
            <div class="character-profile-value">${renderValue(value)}</div>
          </div>`).join("")}
      </div>
      ${hasValue(stage) ? `
        <div class="character-profile-long">
          <div class="character-profile-label">这个阶段</div>
          <div class="character-profile-value">${renderValue(stage)}</div>
        </div>` : ""}`;
  }

  function profileHasContent(profile) {
    if (!profile || typeof profile !== "object") return false;
    return [
      "语言风格", "speech_style", "情绪底色", "emotional_patterns", "personality",
      "核心信念", "core_beliefs", "当前人格状态", "当前状态", "current_state", "identity",
    ].some(key => hasValue(profile[key]));
  }

  function render() {
    const detail = state.detail;
    const character = detail.character;
    const source = detail.source || {};
    const periods = detail.periods || [];
    const profile = detail.profile?.profile || null;
    const ready = profileHasContent(profile) ? firstReadyPeriod(periods) : null;
    const scenesHref = `/characters/${encodeURIComponent(character.id)}/scenes`;
    const recent = state.conversations.filter(item => Number(item.character_id) === Number(character.id)).slice(0, 5);
    const latest = recent[0];
    const startHref = ready
      ? (latest ? `/chats/${encodeURIComponent(latest.id)}` : `/chats/new?character=${encodeURIComponent(character.id)}&period=${ready.id}`)
      : scenesHref;
    const sourceName = App.sourceLabel(source.name, "一本小说");
    const sourceHref = App.novelHref(source);
    const sourceLine = `来自 <a href="${sourceHref}">${App.escapeHtml(sourceName)}</a>${periods.length ? ` · ${periods.length} 个场景` : ""}`;

    $("#detail-root").innerHTML = `
      <a class="back-link" href="/characters">${App.icons.back} 角色</a>
      <header class="character-hero">
        ${App.avatar(character.name, "avatar-xl")}
        <div class="character-hero-copy">
          <h1>${App.escapeHtml(character.name)}</h1>
          <p class="character-hero-meta">${sourceLine}</p>
          <span class="character-hero-note">${ready ? "人设已准备，可以直接进入对话。" : "还没有可用人设。先准备一个场景。"}</span>
        </div>
        <div class="character-hero-actions">
          ${ready
            ? `<a class="btn btn-primary" href="${startHref}">${latest ? "继续对话" : "开始对话"}</a>`
            : `<a class="btn btn-primary" href="${scenesHref}">准备人设</a>`}
        </div>
      </header>

      <section class="character-section" aria-labelledby="profile-title">
        <div class="section-head"><h2 class="section-title" id="profile-title">人设</h2></div>
        ${renderProfile(profile, character, scenesHref)}
      </section>

      <section class="character-section" aria-labelledby="scenes-title">
        <div class="section-head"><h2 class="section-title" id="scenes-title">场景</h2><a class="section-link" href="${scenesHref}">管理场景</a></div>
        ${periods.length ? `
          <div class="scene-lite-list">
            ${periods.map(period => `
              <div class="scene-lite-row">
                <span class="scene-lite-dot ${period.profile_ready ? "is-ready" : ""}"></span>
                <div class="scene-lite-copy">
                  <span class="scene-lite-name">${App.escapeHtml(period.name || "未命名场景")}</span>
                </div>
                <span class="scene-lite-state">${period.profile_ready ? "人设可用" : "待准备"}</span>
              </div>`).join("")}
          </div>`
        : `<p class="character-source-note">还没有场景。到场景页从原文整理，或手动加一个阶段。</p>`}
      </section>

      ${recent.length ? `
        <section class="character-section" aria-labelledby="recent-title">
          <div class="section-head"><h2 class="section-title" id="recent-title">最近对话</h2><a class="section-link" href="/chats">全部对话</a></div>
          <div class="recent-chat-list">
            ${recent.map(item => `
              <a class="recent-chat-row" href="/chats/${encodeURIComponent(item.id)}">
                <div class="recent-chat-copy">
                  <span class="recent-chat-name">${App.escapeHtml(item.period_name || "对话")}</span>
                  <span class="recent-chat-preview">${App.escapeHtml((item.last_message || "还没有消息").slice(0, 42))}</span>
                </div>
                <span class="recent-chat-time">${App.escapeHtml(App.formatRelative(item.last_message_at || item.updated_at))}</span>
              </a>`).join("")}
          </div>
        </section>` : ""}`;
    App.pageTitle(`${character.name} · 角色`);
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("characters");
    if (!characterId) { location.replace("/characters"); return; }
    try {
      const [detail, conversations] = await Promise.all([
        App.api(`/api/app/characters/${encodeURIComponent(characterId)}`),
        App.api("/api/app/conversations").catch(() => ({ items: [] })),
      ]);
      state.detail = detail;
      state.conversations = conversations.items || [];
      render();
    } catch (error) {
      $("#detail-root").innerHTML = `<a class="back-link" href="/characters">${App.icons.back} 角色</a><div class="empty-state"><h3>这个角色打不开</h3><p>${App.escapeHtml(error.message)}</p><a class="btn" href="/characters">返回角色</a></div>`;
      App.toast(error.message, "error");
    }
  }

  init();
})();
