(() => {
  if (!App.requireAuth()) return;
  const state = { characters: [], characterId: null, detail: null, periodId: null, busy: false };
  const $ = App.qs;

  function renderCharacterOptions() {
    const select = $("#character-select");
    if (!state.characters.length) {
      select.innerHTML = `<option value="">还没有角色</option>`;
      select.disabled = true;
      $("#start-chat-note").innerHTML = `还没有角色。先到 <a href="/characters/new">角色页</a> 创建一个。`;
      $("#first-send").disabled = true;
      $("#first-message").disabled = true;
      return;
    }
    select.disabled = false;
    select.innerHTML = state.characters.map(character => `
      <option value="${character.id}" ${character.id === state.characterId ? "selected" : ""}>
        ${App.escapeHtml(character.name)}${character.persona_ready === false ? "（还没有人设）" : ""}
      </option>`).join("");
  }

  function renderSceneOptions(preferredPeriod = null) {
    const select = $("#scene-select");
    const periods = state.detail?.periods || [];
    if (!periods.length) {
      select.innerHTML = `<option value="">还没有场景</option>`;
      select.disabled = true;
      state.periodId = null;
      $("#start-chat-note").innerHTML = `这个角色还没有场景。先到 <a href="/characters/${encodeURIComponent(state.characterId)}/scenes">场景页</a> 准备一个。`;
      updateSend();
      return;
    }
    const ready = periods.filter(period => period.profile_ready);
    let selected = preferredPeriod && ready.find(period => period.id === Number(preferredPeriod));
    if (!selected) selected = ready[0] || null;
    state.periodId = selected ? selected.id : null;
    select.disabled = false;
    select.innerHTML = periods.map(period => `
      <option value="${period.id}" ${period.profile_ready ? "" : "disabled"} ${selected && period.id === selected.id ? "selected" : ""}>
        ${App.escapeHtml(period.name || "未命名场景")}${period.profile_ready ? "" : "（还没有人设）"}
      </option>`).join("");
    const source = App.sourceLabel(state.detail?.source?.name, "这本小说");
    $("#start-chat-note").innerHTML = `${App.escapeHtml(source)} · ${periods.length} 个场景${ready.length ? "" : "。先准备一个人设才能开始。"}`;
    if (!ready.length) {
      $("#start-chat-note").innerHTML += ` <a href="/characters/${encodeURIComponent(state.characterId)}/scenes">去准备人设</a>`;
    }
    updateSend();
  }

  function updateSend() {
    $("#first-send").disabled = state.busy || !state.characterId || !state.periodId;
    $("#first-message").disabled = !state.periodId;
  }

  async function loadCharacter(id, preferredPeriod = null) {
    if (!id || state.busy) return;
    state.characterId = id;
    state.detail = null;
    state.periodId = null;
    $("#scene-select").disabled = true;
    $("#scene-select").innerHTML = `<option>正在载入…</option>`;
    $("#start-chat-note").textContent = "";
    updateSend();
    try {
      state.detail = await App.api(`/api/app/characters/${encodeURIComponent(id)}`);
      renderSceneOptions(preferredPeriod);
    } catch (error) {
      $("#scene-select").innerHTML = `<option>场景载入失败</option>`;
      $("#start-chat-note").textContent = error.message || "角色载入失败。";
    }
  }

  async function sendFirst() {
    if (state.busy || !state.characterId || !state.periodId) return;
    const message = $("#first-message").value.trim();
    if (!message) { $("#new-chat-error").textContent = "先写一句开场白。"; return; }
    state.busy = true;
    updateSend();
    $("#new-chat-error").textContent = "正在准备这段对话…";
    const threadName = `新对话 ${new Date().toISOString().slice(0, 19).replace("T", " ")}`;
    try {
      const complete = await App.streamChat({
        characterId: state.characterId,
        message,
        periodId: state.periodId,
        threadName,
        mode: "quick",
        webMode: "off",
        onProgress: () => { $("#new-chat-error").textContent = "角色正在回答…"; },
      });
      if (complete.thread_id) {
        location.href = `/chats/${encodeURIComponent(complete.thread_id)}`;
        return;
      }
      throw new Error("没有拿到对话 id");
    } catch (error) {
      state.busy = false;
      updateSend();
      $("#new-chat-error").textContent = error.message || "发送失败，请重试。";
      $("#first-message").focus();
    }
  }

  function bindEvents() {
    $("#character-select").addEventListener("change", event => loadCharacter(Number(event.target.value)));
    $("#scene-select").addEventListener("change", event => {
      const id = Number(event.target.value);
      const period = state.detail?.periods?.find(item => item.id === id);
      state.periodId = period?.profile_ready ? id : null;
      updateSend();
    });
    $("#first-send").addEventListener("click", sendFirst);
    $("#first-message").addEventListener("input", event => {
      const node = event.target;
      node.style.height = "auto";
      node.style.height = `${Math.min(node.scrollHeight, 150)}px`;
      $("#new-chat-error").textContent = "";
    });
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("chats");
    App.pageTitle("开始对话");
    $("#back-to-chats").innerHTML = `${App.icons.back} 对话`;
    bindEvents();
    try {
      const data = await App.api("/api/app/characters");
      state.characters = data.items || [];
      const params = new URLSearchParams(location.search);
      const preferredId = Number(params.get("character") || params.get("character_id") || 0);
      const firstReady = state.characters.find(character => character.persona_ready !== false) || state.characters[0];
      state.characterId = state.characters.some(character => character.id === preferredId) ? preferredId : (firstReady?.id || null);
      renderCharacterOptions();
      if (state.characterId) await loadCharacter(state.characterId, params.get("period"));
      updateSend();
    } catch (error) {
      $("#start-chat-note").textContent = error.message || "角色载入失败。";
      updateSend();
    }
  }
  init();
})();
