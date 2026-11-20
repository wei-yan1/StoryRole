(() => {
  const state = { library: [], characters: [], characterId: null, characterName: "", periods: [], profile: null, novelId: null, query: "", busy: false };
  const $ = selector => document.querySelector(selector);

  function setStatus(text, error = false, success = false) {
    const node = $("#character-status");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("error", error);
    node.classList.toggle("success", success);
  }

  function setBusy(value) {
    state.busy = value;
    const button = $("#setup-button");
    if (button) {
      button.disabled = value;
      button.textContent = value ? "正在建立档案…" : "建立人物 →";
    }
  }

  function setNovelOptions() {
    const select = $("#novel-select");
    if (!select) return;
    if (!state.library.length) {
      select.innerHTML = `<option value="">还没有小说档案</option>`;
      select.disabled = true;
      $("#character-novel-tag").textContent = "先去收录小说";
      return;
    }
    select.disabled = false;
    select.innerHTML = state.library.map(item => `<option value="${Studio.escapeHtml(item.novel_id)}" ${String(item.novel_id) === String(state.novelId) ? "selected" : ""}>${Studio.escapeHtml(item.novel_name)}</option>`).join("");
    const current = state.library.find(item => String(item.novel_id) === String(state.novelId));
    $("#character-novel-tag").textContent = current ? current.novel_name : "小说未选择";
  }

  function renderCandidates() {
    const root = $("#candidate-grid");
    if (!root) return;
    const query = state.query.trim().toLowerCase();
    const items = state.characters.filter(item => !query || String(item.canonical_name || "").toLowerCase().includes(query));
    $("#candidate-count").textContent = `${items.length} 位`;
    if (!items.length) {
      root.innerHTML = `<div class="candidate-empty">${state.characters.length ? "没有匹配的人物，换一个关键词试试。" : "这本小说还没有解析出人物候选。直接输入姓名也可以建立档案。"}</div>`;
      return;
    }
    root.innerHTML = items.slice(0, 24).map(item => `
      <button class="candidate-chip" type="button" data-name="${Studio.escapeHtml(item.canonical_name)}">
        ${Studio.escapeHtml(item.canonical_name)}<span>${Studio.formatNumber(item.mention_count || 0)} 次</span>
      </button>
    `).join("");
    root.querySelectorAll("[data-name]").forEach(button => {
      button.addEventListener("click", () => {
        $("#character-name").value = button.dataset.name;
        setupCharacter();
      });
    });
  }

  function renderDossier() {
    const root = $("#dossier-root");
    if (!root) return;
    if (!state.characterId) {
      root.innerHTML = `
        <div class="dossier-empty">
          <span class="empty-mark">“</span>
          <strong>档案里还没有人。</strong>
          <p>选择左侧小说，输入一个在原文中出现过的名字。建立之后，这里会出现他的角色档案和去往时期页的下一步。</p>
          <a class="btn btn-ghost btn-sm" href="/novels">打开小说档案</a>
        </div>`;
      return;
    }
    const name = state.characterName || state.character?.canonical_name || "未命名角色";
    const monogram = String(name).slice(0, 1);
    const periods = state.periods || [];
    const profileReady = Boolean(state.profile);
    const profileVersion = state.profile?.version || state.profile?.profile_version || "—";
    const mentionCount = state.character?.mention_count;
    const periodNames = periods.slice(0, 3).map(item => item.name).filter(Boolean).join(" / ");
    const nextHref = `/periods?novel=${encodeURIComponent(state.novelId || "")}&character=${encodeURIComponent(state.characterId)}`;
    root.innerHTML = `
      <div class="dossier-cover">
        <span class="dossier-monogram">${Studio.escapeHtml(monogram)}</span>
        <div class="dossier-title"><small>PERSONA DOSSIER / ${String(state.novelId || "").slice(0, 8)}</small><strong title="${Studio.escapeHtml(name)}">${Studio.escapeHtml(name)}</strong></div>
      </div>
      <div class="dossier-body">
        <div class="dossier-meta-grid">
          <div><small>所在小说</small><strong>${Studio.escapeHtml((state.library.find(item => String(item.novel_id) === String(state.novelId)) || {}).novel_name || "当前档案")}</strong></div>
          <div><small>原文提及</small><strong>${mentionCount == null ? "—" : `${Studio.formatNumber(mentionCount)} 次`}</strong></div>
          <div><small>时期设置</small><strong>${periods.length ? `${periods.length} 段时期` : "尚未设置"}</strong></div>
          <div><small>女娲画像</small><strong>${profileReady ? `已建立 · v${Studio.escapeHtml(profileVersion)}` : "尚未生成"}</strong></div>
        </div>
        ${periodNames ? `<div class="dossier-note">已识别时期：${Studio.escapeHtml(periodNames)}${periods.length > 3 ? " …" : ""}</div>` : `<div class="dossier-note">这个角色还没有时期。时期决定他能记住什么，也决定对话的边界。</div>`}
        <div class="next-banner">
          <div><strong>${profileReady ? "身份已建立，去确认他的时期。" : "身份已建立，下一步是时期画像。"}</strong><small>${profileReady ? "已有画像，可从这里继续进入对话页。" : "时期页会生成该时期的女娲画像，完成后才能开始对话。"}</small></div>
          <a class="btn btn-accent btn-sm" href="${nextHref}">辨认时期 →</a>
        </div>
        ${profileReady ? `<a class="btn btn-ghost btn-wide" href="/chat?novel=${encodeURIComponent(state.novelId || "")}&character=${encodeURIComponent(state.characterId)}">进入角色对话 <span aria-hidden="true">→</span></a>` : ""}
      </div>`;
  }

  async function loadPeriodsAndProfile() {
    state.periods = [];
    state.profile = null;
    if (!state.novelId || !state.characterId) return;
    try {
      state.periods = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/periods`);
    } catch (_) {}
    try {
      state.profile = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/${state.characterId}/profile`);
    } catch (_) {
      state.profile = null;
    }
    renderDossier();
  }

  async function loadCharacters() {
    state.characters = [];
    if (!state.novelId) {
      renderCandidates();
      return;
    }
    try {
      state.characters = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters`);
    } catch (error) {
      setStatus(`人物候选读取失败：${error.message}`, true);
    }
    renderCandidates();
  }

  async function setupCharacter() {
    const name = $("#character-name").value.trim();
    if (!state.novelId) {
      setStatus("先选择一本小说。", true);
      return;
    }
    if (!name) {
      setStatus("请输入人物姓名。", true);
      $("#character-name").focus();
      return;
    }
    if (state.busy) return;
    setBusy(true);
    setStatus("正在核对原文并建立人物档案…");
    try {
      const result = await Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.novelId)}/characters/setup`, {
        method: "POST",
        json: { character_name: name }
      });
      if (!result.found) {
        setStatus("没有在原文里找到这个角色，请核对姓名。", true);
        return;
      }
      state.characterId = result.character_id;
      state.characterName = result.character_name || name;
      state.character = state.characters.find(item => String(item.id) === String(state.characterId)) || { canonical_name: state.characterName, mention_count: null };
      Studio.saveContext({ characterId: state.characterId, characterName: state.characterName, periodId: null, periodName: null });
      await loadPeriodsAndProfile();
      setStatus(result.reused ? "已恢复已有角色画像。" : "人物档案已建立。下一步：辨认时期。", false, true);
      Studio.toast(result.reused ? "已恢复已有角色。" : "人物档案已建立。", "success");
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function loadLibrary() {
    const params = new URLSearchParams(location.search);
    const requestedNovel = params.get("novel");
    if (requestedNovel && String(requestedNovel) !== String(Studio.getContext().novelId)) {
      Studio.saveContext({ novelId: requestedNovel });
    }
    try {
      state.library = await Studio.api("/api/v1/novels/library");
    } catch (error) {
      Studio.toast(error.message, "error");
      state.library = [];
    }
    const context = Studio.getContext();
    const preferred = state.library.find(item => String(item.novel_id) === String(context.novelId)) || state.library[0];
    if (preferred) {
      state.novelId = preferred.novel_id;
      if (String(context.novelId) !== String(preferred.novel_id) || context.novelName !== preferred.novel_name) {
        Studio.saveContext({ novelId: preferred.novel_id, novelName: preferred.novel_name });
      }
    } else {
      state.novelId = null;
    }
    if (context.characterId && String(context.novelId) === String(state.novelId)) {
      state.characterId = context.characterId;
      state.characterName = context.characterName || "";
    } else {
      state.characterId = null;
      state.characterName = "";
    }
    setNovelOptions();
    await loadCharacters();
    if (state.characterId) {
      state.character = state.characters.find(item => String(item.id) === String(state.characterId));
      if (state.character) {
        state.characterName = state.character.canonical_name || state.characterName;
        if (!Studio.getContext().characterName) Studio.saveContext({ characterId: state.characterId, characterName: state.characterName });
      }
      await loadPeriodsAndProfile();
    } else {
      renderDossier();
    }
  }

  function bind() {
    $("#novel-select").addEventListener("change", async event => {
      const item = state.library.find(entry => String(entry.novel_id) === event.target.value);
      if (!item) return;
      state.novelId = item.novel_id;
      state.characterId = null;
      state.characterName = "";
      state.periods = [];
      state.profile = null;
      Studio.saveContext({ novelId: item.novel_id, novelName: item.novel_name });
      setNovelOptions();
      renderDossier();
      await loadCharacters();
      setStatus("已切换当前小说，请选择或输入一个人物。");
    });
    $("#character-query").addEventListener("input", event => { state.query = event.target.value; renderCandidates(); });
    $("#character-name").addEventListener("keydown", event => {
      if (event.key === "Enter") { event.preventDefault(); setupCharacter(); }
    });
    $("#setup-button").addEventListener("click", setupCharacter);
  }

  bind();
  loadLibrary();
})();
