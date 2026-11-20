(() => {
  if (!App.requireAuth()) return;
  const state = { detail: null, conversations: [] };
  const $ = App.qs;
  const characterId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

  function renderValue(value) {
    if (value === null || value === undefined || value === "") return `<span class="faint">—</span>`;
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

  function render() {
    const detail = state.detail;
    const character = detail.character;
    const source = detail.source;
    const periods = detail.periods || [];
    const profile = detail.profile?.profile || null;
    const ready = firstReadyPeriod(periods);
    const profileVersion = detail.profile?.version ? `人设 v${detail.profile.version}` : "还没有人设";
    const startHref = ready
      ? `/chats/new?character=${encodeURIComponent(character.id)}&period=${ready.id}`
      : `/characters/${encodeURIComponent(character.id)}/scenes`;
    const recent = state.conversations.filter(item => Number(item.character_id) === Number(character.id)).slice(0, 4);
    $("#detail-root").innerHTML = `
      <div class="card hero-card">
        <div class="hero-inner detail-hero">
          <div class="detail-hero-main">
            ${App.avatar(character.name, "avatar-xl")}
            <div class="detail-hero-copy">
              <p class="page-kicker" style="margin-bottom:6px">角色主页</p>
              <h1>${App.escapeHtml(character.name)}</h1>
              <p class="detail-hero-sub">来自 ${App.escapeHtml(source.name || "未知资料")} · ${periods.length} 个场景</p>
              <div class="character-meta" style="margin-top:12px">
                <span class="pill ${ready ? "pill-mint pill-dot" : ""}">${ready ? "可以开始对话" : "需要先准备人设"}</span>
                <span class="pill">${App.escapeHtml(source.source_kind === "bundled" ? "内置资料" : "导入资料")}</span>
              </div>
            </div>
          </div>
          <div class="detail-hero-actions">
            <a class="btn btn-primary" href="${startHref}">${ready ? "开始对话" : "准备人设"}</a>
            <a class="btn" href="/characters/${encodeURIComponent(character.id)}/scenes">场景管理</a>
          </div>
        </div>
      </div>

      <div class="two-column" style="margin-top:18px">
        <section>
          ${profile ? `
          <div class="card card-pad">
            <div class="section-head"><h2 class="section-title">人设摘要</h2><span class="pill">${App.escapeHtml(profileVersion)}</span></div>
            <div class="profile-grid">
              <div class="profile-note"><div class="profile-note-label">语言风格</div><div class="profile-note-value">${renderValue(profile["语言风格"])}</div></div>
              <div class="profile-note"><div class="profile-note-label">情绪底色</div><div class="profile-note-value">${renderValue(profile["情绪底色"])}</div></div>
              <div class="profile-note"><div class="profile-note-label">核心信念</div><div class="profile-note-value">${renderValue(profile["核心信念"])}</div></div>
              <div class="profile-note"><div class="profile-note-label">当前状态</div><div class="profile-note-value">${renderValue(profile["当前人格状态"])}</div></div>
              <div class="profile-note" style="grid-column:1/-1"><div class="profile-note-label">阶段定位</div><div class="profile-note-value">${renderValue(profile["阶段定位"])}</div></div>
              <div class="profile-note" style="grid-column:1/-1"><div class="profile-note-label">典型回答倾向</div><div class="profile-note-value">${renderValue(profile["典型回答倾向"])}</div></div>
            </div>
          </div>` : `
          <div class="empty-state" style="min-height:260px">
            <span class="empty-icon">${App.icons?.spark || ""}</span>
            <h3>还没有可用的角色人设</h3>
            <p>先到场景页为这个角色准备一个阶段的人设。准备好之后，就可以开始对话。</p>
            <a class="btn btn-primary" href="/characters/${encodeURIComponent(character.id)}/scenes">去准备人设</a>
          </div>`}

          <div class="card card-pad" style="margin-top:14px">
            <div class="section-head"><h2 class="section-title">场景时间线</h2><a class="section-link" href="/characters/${encodeURIComponent(character.id)}/scenes">管理场景</a></div>
            <div class="timeline">
              ${periods.length ? periods.map(period => `
                <div class="timeline-item">
                  <span class="timeline-dot ${period.profile_ready ? "ready" : ""}"></span>
                  <div class="timeline-copy">
                    <div class="timeline-title">${App.escapeHtml(period.name || "未命名场景")}
                      ${period.profile_ready ? `<span class="pill pill-mint pill-dot">可对话</span>` : `<span class="pill">待准备</span>`}
                    </div>
                    <div class="timeline-meta">${App.escapeHtml([period.chapter_start, period.chapter_end].filter(Boolean).join(" → ") || "")}</div>
                    <div class="timeline-actions">
                      ${period.profile_ready ? `<a class="text-link" href="/chats/new?character=${encodeURIComponent(character.id)}&period=${period.id}">从这个场景开始 →</a>` : `<a class="text-link" href="/characters/${encodeURIComponent(character.id)}/scenes">准备人设 →</a>`}
                    </div>
                  </div>
                </div>`).join("") : `<div class="source-note">${App.icons?.info || ""}<span>还没有场景。先到场景页添加一个阶段，或让系统从资料里分析时间线。</span></div>`}
            </div>
          </div>
        </section>

        <aside>
          <div class="card card-pad">
            <div class="section-head"><h2 class="section-title">背景资料</h2><a class="section-link" href="/library">资料库</a></div>
            <div class="source-note">${App.icons?.library || ""}<span><strong>${App.escapeHtml(source.name || "未知资料")}</strong><br>${source.source_kind === "bundled" ? "内置示范资料" : "你导入的资料"} · ${source.status === "ready" ? "已就绪" : App.escapeHtml(source.status || "处理中")}<br>资料只作为角色背景，不会出现在对话首页。</span></div>
            <div class="divider" style="margin:16px 0"></div>
            <div class="profile-note-label">角色摘要</div>
            <p class="source-excerpt" id="source-summary">${App.escapeHtml(character.summary || "还没有摘要。打开资料库查看更多原始内容。")}</p>
            <button class="text-link" type="button" data-expand-summary>展开摘要</button>
          </div>

          <div class="card card-pad" style="margin-top:14px">
            <div class="section-head"><h2 class="section-title">最近对话</h2><a class="section-link" href="/chats">全部</a></div>
            ${recent.length ? recent.map(item => `
              <a class="mini-character" href="/chats/${encodeURIComponent(item.id)}">
                ${App.avatar(character.name, "avatar-sm")}
                <span class="mini-character-copy"><span class="mini-character-name">${App.escapeHtml(item.period_name || "对话")}</span><span class="mini-character-meta">${App.escapeHtml((item.last_message || "还没有消息").slice(0, 26))}</span></span>
                <span class="faint" style="font-size:10px">${App.escapeHtml(App.formatRelative(item.last_message_at))}</span>
              </a>`).join("") : `<p class="faint" style="font-size:11px;line-height:1.7">还没有和这个角色对话。选择一个场景，说第一句话。</p><a class="btn btn-sm" style="margin-top:10px" href="${startHref}">开始对话</a>`}
          </div>
        </aside>
      </div>`;
    const summaryToggle = $("#source-summary") ? $("#detail-root").querySelector("[data-expand-summary]") : null;
    if (summaryToggle) {
      summaryToggle.addEventListener("click", () => {
        const summary = $("#source-summary");
        const expanded = summary.classList.toggle("is-expanded");
        summaryToggle.textContent = expanded ? "收起摘要" : "展开摘要";
      });
    }
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
      $("#detail-root").innerHTML = `<div class="empty-state"><h3>这个角色打不开</h3><p>${App.escapeHtml(error.message)}</p><a class="btn" href="/characters">返回角色库</a></div>`;
      App.toast(error.message, "error");
    }
  }

  init();
})();