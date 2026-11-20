(() => {
  if (!App.requireAuth()) return;
  const state = { characters: [], selectedId: null, detail: null, periodId: null, busy: false };
  const $ = App.qs;
  const prompts = [
    "你好，最近怎么样？",
    "给我讲讲你记得的一个夜晚。",
    "如果重新选择一次，你会怎么做？",
    "你现在最在意的是什么？",
  ];

  function renderCharacters() {
    const root = $("#character-picker");
    if (!state.characters.length) {
      root.innerHTML = `<div class="source-note">${App.icons.info}<span>还没有角色。先到角色库创建一个，再回来开始对话。</span></div><a class="btn btn-primary btn-sm" href="/characters/new" style="margin-top:12px">创建角色</a>`;
      $("#stage-placeholder").classList.remove("hidden");
      $("#stage-content").classList.add("hidden");
      return;
    }
    root.innerHTML = state.characters.map(character => `
      <button class="picker-card ${character.id === state.selectedId ? "is-current" : ""}" type="button" data-character="${character.id}">
        ${App.avatar(character.name, "avatar-sm")}
        <span class="picker-copy">
          <span class="picker-name">${App.escapeHtml(character.name)}</span>
          <span class="picker-meta">${character.profile_count ? `${character.period_count || 0} 个场景 · 可对话` : "待准备人设"}</span>
        </span>
      </button>`).join("");
    App.qsa("[data-character]").forEach(button => button.addEventListener("click", () => selectCharacter(Number(button.dataset.character))));
    $("#stage-placeholder-actions")?.classList.add("hidden");
  }

  function renderStageHeader() {
    if (!state.detail) return;
    const character = state.detail.character;
    $("#stage-avatar").innerHTML = App.avatar(character.name, "avatar-md");
    $("#stage-name").textContent = character.name;
    $("#stage-meta").textContent = `${state.detail.source?.name || "未命名资料"} · ${state.detail.periods?.length || 0} 个场景`;
    $("#stage-link").href = `/characters/${character.id}`;
  }

  function renderScenes() {
    const periods = state.detail?.periods || [];
    const root = $("#scene-picker");
    if (!periods.length) {
      root.innerHTML = "";
      $("#scene-note").innerHTML = `这个角色还没有场景。先到 <a href="/characters/${state.selectedId}/scenes">角色场景</a> 分析或添加一个场景。`;
      updateSend();
      return;
    }
    const ready = periods.filter(period => period.profile_ready);
    if (!state.periodId || !ready.some(period => period.id === state.periodId)) {
      state.periodId = ready[0]?.id || null;
    }
    root.innerHTML = periods.map(period => `
      <button class="scene-chip ${period.id === state.periodId ? "is-current" : ""}" type="button" data-period="${period.id}" ${period.profile_ready ? "" : "disabled"}>
        <span class="scene-chip-name">${App.escapeHtml(period.name || "未命名场景")}</span>
        <span class="scene-chip-meta">${period.profile_ready ? "可对话" : "待准备人设"}</span>
      </button>`).join("");
    App.qsa("[data-period]").forEach(button => {
      if (!button.disabled) button.addEventListener("click", () => selectPeriod(Number(button.dataset.period)));
    });
    if (!ready.length) {
      $("#scene-note").innerHTML = `还没有可用的人设。先到 <a href="/characters/${state.selectedId}/scenes">角色场景</a> 生成一个。`;
    } else {
      const period = periods.find(item => item.id === state.periodId);
      $("#scene-note").textContent = period ? `当前场景：${period.name || "未命名场景"}。角色只会记得这个阶段可见的事。` : "";
    }
    updateSend();
  }

  function selectPeriod(id) {
    state.periodId = id;
    App.qsa("[data-period]").forEach(button => button.classList.toggle("is-current", Number(button.dataset.period) === id));
    const period = state.detail?.periods?.find(item => item.id === id);
    if (period) $("#scene-note").textContent = `当前场景：${period.name || "未命名场景"}。角色只会记得这个阶段可见的事。`;
    updateSend();
  }

  function updateSend() {
    const hasReadyPeriod = Boolean(state.periodId);
    $("#first-send").disabled = state.busy || !state.selectedId || !hasReadyPeriod;
  }

  async function selectCharacter(id, preferredPeriod = null) {
    if (state.busy) return;
    state.selectedId = id;
    state.detail = null;
    state.periodId = null;
    renderCharacters();
    $("#stage-placeholder").classList.add("hidden");
    $("#stage-content").classList.remove("hidden");
    $("#stage-name").textContent = "正在载入…";
    $("#stage-meta").textContent = "";
    $("#stage-avatar").innerHTML = `<span class="avatar avatar-md" style="background:var(--line-strong)"></span>`;
    $("#scene-picker").innerHTML = `<div class="skeleton" style="height:34px;width:35%"></div><div class="skeleton" style="height:34px;width:35%"></div>`;
    $("#scene-note").textContent = "";
    try {
      const detail = await App.api(`/api/app/characters/${encodeURIComponent(id)}`);
      state.detail = detail;
      const periods = detail.periods || [];
      const preferred = preferredPeriod && periods.find(period => period.id === Number(preferredPeriod) && period.profile_ready);
      state.periodId = preferred ? preferred.id : (periods.find(period => period.profile_ready)?.id || null);
      renderStageHeader();
      renderScenes();
    } catch (error) {
      $("#scene-picker").innerHTML = "";
      $("#scene-note").textContent = error.message || "角色载入失败";
    }
  }

  async function sendFirst() {
    if (state.busy || !state.selectedId || !state.periodId) return;
    const message = $("#first-message").value.trim();
    if (!message) { $("#new-chat-error").textContent = "先写一句开场白。"; return; }
    state.busy = true;
    updateSend();
    $("#new-chat-error").className = "chat-error";
    $("#new-chat-error").textContent = "正在准备这段对话…";
    const threadName = `新对话 ${new Date().toISOString().slice(0, 19).replace("T", " ")}`;
    try {
      const complete = await App.streamChat({
        characterId: state.selectedId,
        message,
        periodId: state.periodId,
        threadName,
        mode: $("#new-chat-mode").value,
        webMode: $("#new-chat-web").checked ? "on" : "off",
        onProgress: payload => {
          $("#new-chat-error").textContent = payload.deep ? "角色正在深入思考…" : "角色正在准备回答…";
        },
      });
      if (complete.thread_id) {
        location.href = `/chats/${encodeURIComponent(complete.thread_id)}`;
        return;
      }
      throw new Error("没有拿到对话 id");
    } catch (error) {
      state.busy = false;
      updateSend();
      $("#new-chat-error").className = "chat-error";
      $("#new-chat-error").textContent = error.message || "发送失败，请重试。";
      $("#first-message").focus();
    }
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("chats");
    App.pageTitle("新对话");
    $("#back-to-chats").innerHTML = `${App.icons.back} 返回对话`;
    $("#prompt-chips").innerHTML = prompts.map(prompt => `<button class="prompt-chip" type="button" data-prompt="${App.escapeHtml(prompt)}">${App.escapeHtml(prompt)}</button>`).join("");
    App.qsa("[data-prompt]").forEach(button => button.addEventListener("click", () => {
      $("#first-message").value = button.dataset.prompt;
      $("#first-message").focus();
    }));
    $("#first-send").addEventListener("click", sendFirst);
    $("#first-message").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendFirst(); }
    });
    $("#first-message").addEventListener("input", event => {
      const node = event.target;
      node.style.height = "auto";
      node.style.height = `${Math.min(node.scrollHeight, 150)}px`;
      updateSend();
    });
    try {
      const data = await App.api("/api/app/characters");
      state.characters = data.items || [];
      renderCharacters();
      const params = new URLSearchParams(location.search);
      const preferredId = Number(params.get("character") || params.get("character_id") || 0);
      if (preferredId && state.characters.some(character => character.id === preferredId)) {
        await selectCharacter(preferredId, Number(params.get("period") || 0) || null);
      }
      updateSend();
    } catch (error) {
      $("#character-picker").innerHTML = `<div class="source-note">${App.icons.info}<span>${App.escapeHtml(error.message)}</span></div>`;
    }
  }
  init();
})();