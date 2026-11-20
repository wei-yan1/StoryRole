(() => {
  if (!App.requireAuth()) return;
  const state = { characters: [], sources: [], query: "", source: new URLSearchParams(location.search).get("source") || "" };
  const $ = App.qs;

  function filtered() {
    const query = state.query.trim().toLowerCase();
    return state.characters.filter(character => {
      if (state.source && character.novel_id !== state.source) return false;
      if (!query) return true;
      return [character.name, character.source_name, ...(character.aliases || [])].filter(Boolean).join(" ").toLowerCase().includes(query);
    });
  }

  function render() {
    const root = $("#character-grid");
    const items = filtered();
    $("#character-stat").textContent = `${items.length} 位角色`;
    if (!state.characters.length) {
      root.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><span class="empty-icon">${App.icons?.people || ""}</span><h3>还没有角色</h3><p>先导入一份资料，再从资料里选择一个名字。角色只包含你导入的内容，不会凭空出现。</p><div class="row" style="margin-top:18px"><a class="btn btn-primary" href="/characters/new">从资料创建角色</a><a class="btn" href="/library">打开资料库</a></div></div>`;
      return;
    }
    if (!items.length) {
      root.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><h3>没有匹配的角色</h3><p>换一个名字，或清除资料筛选。</p></div>`;
      return;
    }
    root.innerHTML = items.map(character => {
      const ready = Number(character.profile_count || 0) > 0;
      const action = ready
        ? `<a class="btn btn-primary btn-sm" href="/chats/new?character=${encodeURIComponent(character.id)}">开始对话</a>`
        : `<a class="btn btn-primary btn-sm" href="/characters/${encodeURIComponent(character.id)}/scenes">准备人设</a>`;
      return `
        <article class="card card-pad card-lift character-card">
          <div class="character-head">
            <div class="character-avatar-wrap">${App.avatar(character.name)}</div>
            <div class="character-info">
              <h3 class="character-name">${App.escapeHtml(character.name)}</h3>
              <p class="character-source">${App.escapeHtml(character.source_name || "未知资料")} · ${character.mention_count || 0} 次提及</p>
            </div>
          </div>
          <p class="character-summary">${App.escapeHtml(character.summary || "还没有角色摘要。打开角色详情查看已整理的人设与场景。")}</p>
          <div class="character-meta">
            <span class="pill">${character.period_count || 0} 个场景</span>
            <span class="pill ${ready ? "pill-mint pill-dot" : ""}">${ready ? "可对话" : "待准备"}</span>
          </div>
          <div class="character-actions">
            ${action}
            <a class="btn btn-sm" href="/characters/${encodeURIComponent(character.id)}">详情</a>
          </div>
        </article>`;
    }).join("");
  }

  function renderSources() {
    const select = $("#source-filter");
    const options = state.sources.map(source => `<option value="${App.escapeHtml(source.novel_id)}">${App.escapeHtml(source.name)}</option>`).join("");
    select.innerHTML = `<option value="">全部资料</option>${options}`;
    select.value = state.source;
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("characters");
    App.pageTitle("角色");
    $("#new-character-button").innerHTML = `${App.icons.plus} 新建角色`;
    $("#character-search").addEventListener("input", App.debounce(event => {
      state.query = event.target.value;
      render();
    }, 160));
    $("#source-filter").addEventListener("change", event => {
      state.source = event.target.value;
      render();
    });
    try {
      const [characters, sources] = await Promise.all([
        App.api("/api/app/characters"),
        App.api("/api/app/sources"),
      ]);
      state.characters = characters.items || [];
      state.sources = sources.items || [];
      renderSources();
      render();
    } catch (error) {
      $("#character-grid").innerHTML = `<div class="empty-state" style="grid-column:1/-1"><h3>暂时读不到角色</h3><p>${App.escapeHtml(error.message)}</p><button class="btn" onclick="location.reload()">重新加载</button></div>`;
      App.toast(error.message, "error");
    }
  }

  init();
})();