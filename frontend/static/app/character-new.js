(() => {
  if (!App.requireAuth()) return;
  const state = { sources: [], characters: [], busy: false };
  const $ = App.qs;

  function selectedSource() {
    return state.sources.find(source => String(source.novel_id) === $("#source-select").value);
  }

  function renderSources() {
    const select = $("#source-select");
    if (!state.sources.length) {
      select.innerHTML = `<option value="">还没有小说</option>`;
      select.disabled = true;
      $("#source-hint").innerHTML = `还没有可用的小说。先到 <a href="/novels/new" style="color:var(--accent-dark);font-weight:700">新增小说</a> 导入一本。`;
      $("#existing-names").innerHTML = `<span class="faint" style="font-size:11px">导入小说后，角色候选会出现在这里。</span>`;
      return;
    }
    select.innerHTML = state.sources.map(source => `<option value="${App.escapeHtml(source.novel_id)}">${App.escapeHtml(source.name)} · ${source.status === "ready" ? "已就绪" : App.escapeHtml(source.stage || source.status)}</option>`).join("");
    select.disabled = false;
    renderExisting();
  }

  function renderExisting() {
    const source = selectedSource();
    if (!source) return;
    $("#source-hint").textContent = source.status === "ready"
      ? `小说已就绪 · ${source.character_count || 0} 位已建立角色。输入一个在这本小说中出现过的名字。`
      : "这本小说还在处理中；处理完成后再创建角色。";
    const items = state.characters.filter(character => String(character.novel_id) === String(source.novel_id));
    $("#existing-names").innerHTML = items.length
      ? items.slice(0, 12).map(character => `<button class="prompt-chip" type="button" data-name="${App.escapeHtml(character.name)}">${App.escapeHtml(character.name)}<span class="faint"> · ${character.mention_count || 0} 次</span></button>`).join("")
      : `<span class="faint" style="font-size:11px">还没有已建立角色。直接输入名字，系统会去小说里核对。</span>`;
    App.qsa("[data-name]", $("#existing-names")).forEach(button => button.addEventListener("click", () => {
      $("#character-name").value = button.dataset.name;
      $("#character-name").focus();
    }));
  }

  async function create() {
    if (state.busy) return;
    const source = selectedSource();
    const name = $("#character-name").value.trim();
    const errorNode = $("#create-error");
    errorNode.textContent = "";
    if (!source) { errorNode.textContent = "先选择一本小说。"; return; }
    if (!name) { errorNode.textContent = "请输入角色姓名。"; $("#character-name").focus(); return; }
    if (source.status !== "ready") { errorNode.textContent = "这本小说还在处理中，完成后再创建角色。"; return; }
    state.busy = true;
    const button = $("#create-character");
    button.disabled = true;
    button.textContent = "正在小说中查找…";
    try {
      const result = await App.api(`/api/v1/storyrole/novels/${encodeURIComponent(source.novel_id)}/characters/setup`, {
        method: "POST",
        json: { character_name: name },
      });
      if (!result.found) {
        errorNode.textContent = "小说里没有找到这个名字。核对姓名，或回到书架确认内容。";
        return;
      }
      App.toast(result.reused ? "已恢复这个角色的人设。" : "角色已创建，接下来准备场景人设。", "success");
      location.href = `/characters/${encodeURIComponent(result.character_id)}/scenes?created=1`;
    } catch (error) {
      errorNode.textContent = error.message || "创建失败，请重试。";
    } finally {
      state.busy = false;
      button.disabled = false;
      button.textContent = "创建角色";
    }
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("characters");
    App.pageTitle("新建角色");
    $("#back-to-characters").innerHTML = `${App.icons.back} 返回角色`;
    $("#source-select").addEventListener("change", renderExisting);
    $("#create-character").addEventListener("click", create);
    $("#character-name").addEventListener("keydown", event => {
      if (event.key === "Enter") { event.preventDefault(); create(); }
    });
    try {
      const [sources, characters] = await Promise.all([
        App.api("/api/app/sources"),
        App.api("/api/app/characters"),
      ]);
      state.sources = sources.items || [];
      state.characters = characters.items || [];
      const ready = state.sources.filter(source => source.status === "ready");
      const requested = new URLSearchParams(location.search).get("source");
      const preferred = ready.find(source => String(source.novel_id) === requested) || ready[0] || state.sources[0];
      renderSources();
      if (preferred) {
        $("#source-select").value = preferred.novel_id;
        renderExisting();
      }
    } catch (error) {
      $("#source-select").innerHTML = `<option value="">读取失败</option>`;
      $("#create-error").textContent = error.message;
    }
  }

  init();
})();