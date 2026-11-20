(() => {
  if (!App.requireAuth()) return;
  const state = { characters: [], query: "" };
  const $ = App.qs;

  function filtered() {
    const query = state.query.trim().toLowerCase();
    return state.characters.filter(character => {
      if (!query) return true;
      return [character.name, character.source_name, ...(character.aliases || [])].filter(Boolean).join(" ").toLowerCase().includes(query);
    });
  }

  function render() {
    const root = $("#character-grid");
    const items = filtered();
    $("#character-stat").textContent = `${items.length} 位角色`;
    if (!state.characters.length) {
      root.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><span class="empty-icon">${App.icons?.people || ""}</span><h3>还没有角色</h3><p>先选一本小说，再从小说里选择一个名字。</p><div class="row" style="margin-top:18px"><a class="btn btn-primary" href="/characters/new">从小说创建角色</a><a class="btn" href="/">回到书架</a></div></div>`;
      return;
    }
    if (!items.length) {
      root.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><h3>没有匹配的角色</h3><p>换一个名字试试。</p></div>`;
      return;
    }
    root.innerHTML = items.map(character => {
      const ready = Boolean(character.persona_ready) || (character.persona_ready === undefined && Number(character.profile_count || 0) > 0);
      const source = App.sourceLabel(character.source_name, "一本小说");
      const scenes = Number(character.period_count || 0);
      const summary = character.summary || (ready ? "人设已经准备好，可以进入对话。" : "还没有人设，先选择一个场景准备。");
      return `
        <a class="character-card" href="/characters/${encodeURIComponent(character.id)}">
          <div class="character-head">
            <div class="character-avatar-wrap">${App.avatar(character.name)}</div>
            <div class="character-info">
              <h3 class="character-name">${App.escapeHtml(character.name)}</h3>
              <p class="character-source">${App.escapeHtml(source)}${scenes ? ` · ${scenes} 个场景` : ""}</p>
            </div>
          </div>
          <p class="character-summary">${App.escapeHtml(summary)}</p>
          <div class="character-footer">
            <span class="character-state"><span class="status-dot ${ready ? "ok" : "wait"}"></span>${ready ? "已准备人设" : "还没有人设"}</span>
            <span class="open-label">${ready ? "打开角色" : "准备人设"}</span>
          </div>
        </a>`;
    }).join("");
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
    try {
      const characters = await App.api("/api/app/characters");
      state.characters = characters.items || [];
      render();
    } catch (error) {
      $("#character-grid").innerHTML = `<div class="empty-state" style="grid-column:1/-1"><h3>暂时读不到角色</h3><p>${App.escapeHtml(error.message)}</p><button class="btn" onclick="location.reload()">重新加载</button></div>`;
      App.toast(error.message, "error");
    }
  }

  init();
})();
