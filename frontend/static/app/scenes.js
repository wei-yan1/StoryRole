(() => {
  if (!App.requireAuth()) return;
  const state = { detail: null, selectedId: null, busyPeriods: new Set(), analyzing: false };
  const $ = App.qs;
  const characterId = decodeURIComponent(location.pathname.split("/").filter(Boolean).slice(-2)[0] || "");

  function periodPayload(periods) {
    return periods.map(period => ({
      name: period.name || "未命名场景",
      chapter_start: period.chapter_start || null,
      chapter_end: period.chapter_end || null,
      keywords: period.keywords || [],
      evidence_ids: period.evidence_ids || [],
      rationale: period.rationale || "",
      confidence: Number(period.confidence || 0),
    }));
  }

  function selectedPeriod() {
    return (state.detail?.periods || []).find(period => period.id === state.selectedId) || null;
  }

  function renderList() {
    const periods = state.detail.periods || [];
    $("#scene-count").textContent = `${periods.length} 个场景`;
    const root = $("#scene-list");
    if (!periods.length) {
      root.innerHTML = `<p class="character-source-note" style="padding:4px 10px">还没有场景。先分析时间线，或手动添加一个阶段。</p>`;
      return;
    }
    root.innerHTML = periods.map(period => `
      <button class="scene-row ${period.id === state.selectedId ? "is-current" : ""}" type="button" data-select="${period.id}">
        <span class="scene-row-copy">
          <span class="scene-row-name">${App.escapeHtml(period.name || "未命名场景")}</span>
          <span class="scene-row-state">${period.profile_ready ? "人设可用" : "等待准备人设"}</span>
        </span>
        <span class="scene-lite-dot ${period.profile_ready ? "is-ready" : ""}"></span>
      </button>`).join("");
    App.qsa("[data-select]").forEach(button => button.addEventListener("click", () => {
      state.selectedId = Number(button.dataset.select);
      renderList();
      renderDetail();
    }));
  }

  function renderDetail() {
    const period = selectedPeriod();
    const empty = $("#scene-detail-empty");
    const content = $("#scene-detail-content");
    if (!period) {
      empty.classList.remove("hidden");
      content.classList.add("hidden");
      content.innerHTML = "";
      return;
    }
    empty.classList.add("hidden");
    content.classList.remove("hidden");
    const busy = state.busyPeriods.has(period.id);
    const chapterRange = [period.chapter_start, period.chapter_end].filter(Boolean).join(" → ");
    content.innerHTML = `
      <div class="scene-content-head">
        <div>
          <h2>${App.escapeHtml(period.name || "未命名场景")}</h2>
          <p class="scene-content-meta">${chapterRange ? `章节 ${App.escapeHtml(chapterRange)} · ` : ""}${period.profile_ready ? "人设已准备" : "还没有人设"}</p>
        </div>
      </div>
      <p class="scene-content-copy">${App.escapeHtml(period.rationale || "这个阶段还没有写描述。点“编辑”补一句它此刻的状态。")}</p>
      <div class="scene-content-action">
        <div class="scene-content-action-copy">
          <strong>${period.profile_ready ? "可以进入对话" : "先准备这个阶段的人设"}</strong>
          <span>${period.profile_ready ? "角色会带着这个阶段的记忆、关系和语气说话。" : "生成后，角色才会按这个阶段说话。"}</span>
        </div>
        <div class="row" style="gap:12px;align-items:center">
          ${period.profile_ready
            ? `<a class="btn btn-primary" href="/chats/new?character=${encodeURIComponent(state.detail.character.id)}&period=${period.id}">开始对话</a>`
            : `<button class="btn btn-primary" type="button" data-profile="${period.id}" ${busy ? "disabled" : ""}>${busy ? "正在生成…" : "生成人设"}</button>`}
          <button class="text-link" type="button" data-edit="${period.id}">编辑</button>
        </div>
      </div>`;
    content.querySelector("[data-profile]")?.addEventListener("click", () => generateProfile(period.id));
    content.querySelector("[data-edit]")?.addEventListener("click", () => openSceneModal(period));
  }

  function renderEmpty(periods) {
    const empty = $("#scene-detail-empty");
    if (periods.length) {
      empty.innerHTML = `
        <h2>选择一个场景</h2>
        <p>每个场景是角色经历中的一个阶段。准备人设之后，这个场景才可以在对话中使用。</p>`;
      return;
    }
    empty.innerHTML = `
      <h2>还没有场景</h2>
      <p>先从资料里整理角色经历过的时间线；系统会给出几个阶段，再由你决定保留哪些。</p>
      <div class="row" style="margin-top:18px">
        <button class="btn btn-primary" type="button" id="scene-empty-analyze">从原文整理场景</button>
        <button class="text-link" type="button" id="scene-empty-add">手动添加</button>
      </div>`;
    empty.querySelector("#scene-empty-analyze").addEventListener("click", analyze);
    empty.querySelector("#scene-empty-add").addEventListener("click", () => openSceneModal(null));
  }

  function render() {
    const character = state.detail.character;
    const periods = state.detail.periods || [];
    $("#back-to-character").innerHTML = `${App.icons.back} ${App.escapeHtml(character.name)}`;
    $("#back-to-character").href = `/characters/${character.id}`;
    $("#scene-subtitle").textContent = `${character.name} 的一段人生。选一个阶段，准备人设后就能进入对话。`;
    $("#analyze-button").classList.toggle("hidden", !periods.length);
    $("#add-scene-button").classList.toggle("hidden", !periods.length);
    renderEmpty(periods);
    renderList();
    renderDetail();
  }

  async function generateProfile(periodId) {
    if (state.busyPeriods.has(periodId)) return;
    const period = state.detail?.periods?.find(item => item.id === periodId);
    if (!period) return;
    state.busyPeriods.add(periodId);
    renderDetail();
    App.toast("正在根据资料生成场景人设，这可能需要几十秒。", "info");
    try {
      const result = await App.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.detail.character.novel_id)}/characters/${encodeURIComponent(characterId)}/periods/${periodId}/profile`, { method: "POST" });
      App.toast(result.profile_id ? "场景人设已生成。" : "人设生成完成。", "success");
      await load();
    } catch (error) {
      App.toast(error.message || "人设生成失败。", "error");
    } finally {
      state.busyPeriods.delete(periodId);
      renderDetail();
    }
  }

  async function analyze() {
    if (state.analyzing) return;
    state.analyzing = true;
    const button = $("#analyze-button");
    button.disabled = true;
    button.textContent = "正在分析…";
    $("#analysis-note").textContent = "正在阅读资料，寻找角色经历过的阶段…";
    try {
      const result = await App.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.detail.character.novel_id)}/characters/${encodeURIComponent(characterId)}/period-analysis`, {
        method: "POST",
        json: { period_hints: [] },
      });
      App.toast(`已分析 ${result.periods?.length || 0} 个场景。`, "success");
      if (result.periods?.length) openAnalysisModal(result.periods);
      await load();
    } catch (error) {
      $("#analysis-note").innerHTML = `<span class="error-text">${App.escapeHtml(error.message)}</span>`;
      App.toast(error.message || "分析失败。", "error");
    } finally {
      state.analyzing = false;
      button.disabled = false;
      button.textContent = "从原文整理场景";
    }
  }

  function openAnalysisModal(periods) {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head"><h3>保留这些场景</h3><button class="icon-btn" type="button" data-close>${App.icons.close}</button></div>
        <div class="modal-body">
          <p class="lead" style="margin-bottom:8px">资料里找到了 ${periods.length} 个阶段。保存后，每个阶段都会成为一个可以准备人设的场景。</p>
          <div class="analysis-period-list">
            ${periods.map((period, index) => `
              <div class="analysis-period-row">
                <span class="analysis-period-index">${String(index + 1).padStart(2, "0")}</span>
                <span><strong>${App.escapeHtml(period.name || "未命名场景")}</strong><span class="analysis-period-meta">${[period.chapter_start, period.chapter_end].filter(Boolean).join(" → ") || "章节未标注"}${period.rationale ? ` · ${App.escapeHtml(period.rationale)}` : ""}</span></span>
              </div>`).join("")}
          </div>
          <p class="error-text" id="analysis-error" style="margin-top:10px"></p>
        </div>
        <div class="modal-foot"><button class="btn" type="button" data-close>稍后处理</button><button class="btn btn-primary" type="button" id="save-analysis">保存这些场景</button></div>
      </div>`;
    document.body.append(backdrop);
    const close = () => backdrop.remove();
    backdrop.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", close));
    backdrop.addEventListener("click", event => { if (event.target === backdrop) close(); });
    backdrop.querySelector("#save-analysis").addEventListener("click", async () => {
      const button = backdrop.querySelector("#save-analysis");
      button.disabled = true;
      button.textContent = "保存中…";
      try {
        await App.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.detail.character.novel_id)}/characters/${encodeURIComponent(characterId)}/periods/confirm`, {
          method: "POST",
          json: { periods: periodPayload(periods) },
        });
        App.toast("场景已保存。", "success");
        close();
        await load();
      } catch (error) {
        backdrop.querySelector("#analysis-error").textContent = error.message || "保存失败。";
        button.disabled = false;
        button.textContent = "保存这些场景";
      }
    });
  }

  function openSceneModal(period = null) {
    const existing = Boolean(period);
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head"><h3>${existing ? "编辑场景" : "添加场景"}</h3><button class="icon-btn" type="button" data-close>${App.icons.close}</button></div>
        <div class="modal-body">
          <div class="field"><label class="field-label">场景名称</label><input class="input" id="scene-name" maxlength="255" value="${App.escapeHtml(period?.name || "")}" placeholder="例如：第一次相遇" ${existing ? "readonly" : ""}></div>
          ${existing ? `<p class="note-line" style="margin-top:6px">${App.icons?.info || ""}<span>场景名是保存键；已保存的场景不在这里改名。</span></p>` : ""}
          <div class="row" style="margin-top:12px;align-items:stretch">
            <div class="field" style="flex:1"><label class="field-label">起始章节</label><input class="input" id="scene-start" maxlength="255" value="${App.escapeHtml(period?.chapter_start || "")}" placeholder="可选"></div>
            <div class="field" style="flex:1"><label class="field-label">结束章节</label><input class="input" id="scene-end" maxlength="255" value="${App.escapeHtml(period?.chapter_end || "")}" placeholder="可选"></div>
          </div>
          <div class="field" style="margin-top:12px"><label class="field-label">关键词</label><input class="input" id="scene-keywords" value="${App.escapeHtml((period?.keywords || []).join("，"))}" placeholder="用逗号分隔，可选"></div>
          <div class="field" style="margin-top:12px"><label class="field-label">这个阶段发生了什么</label><textarea class="textarea" id="scene-rationale" placeholder="写一句角色在这个阶段的状态，可选">${App.escapeHtml(period?.rationale || "")}</textarea></div>
          <p class="error-text" id="scene-error" style="margin-top:10px"></p>
        </div>
        <div class="modal-foot"><button class="btn" type="button" data-close>取消</button><button class="btn btn-primary" type="button" id="save-scene">保存场景</button></div>
      </div>`;
    document.body.append(backdrop);
    const close = () => backdrop.remove();
    backdrop.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", close));
    backdrop.addEventListener("click", event => { if (event.target === backdrop) close(); });
    backdrop.querySelector("#save-scene").addEventListener("click", async () => {
      const name = backdrop.querySelector("#scene-name").value.trim();
      const errorNode = backdrop.querySelector("#scene-error");
      if (!name) { errorNode.textContent = "给这个场景一个名字。"; return; }
      const newPeriod = {
        name,
        chapter_start: backdrop.querySelector("#scene-start").value.trim() || null,
        chapter_end: backdrop.querySelector("#scene-end").value.trim() || null,
        keywords: backdrop.querySelector("#scene-keywords").value.split(/[，,\s]+/).map(item => item.trim()).filter(Boolean),
        rationale: backdrop.querySelector("#scene-rationale").value.trim(),
        confidence: period?.confidence || 0,
        evidence_ids: period?.evidence_ids || [],
      };
      const base = periodPayload(state.detail.periods || []);
      const targetIndex = base.findIndex(item => item.name === period?.name);
      if (existing && targetIndex >= 0) base.splice(targetIndex, 1, newPeriod);
      else base.push(newPeriod);
      const save = backdrop.querySelector("#save-scene");
      save.disabled = true;
      save.textContent = "保存中…";
      try {
        await App.api(`/api/v1/storyrole/novels/${encodeURIComponent(state.detail.character.novel_id)}/characters/${encodeURIComponent(characterId)}/periods/confirm`, {
          method: "POST",
          json: { periods: base },
        });
        App.toast("场景已保存。", "success");
        close();
        await load();
      } catch (error) {
        errorNode.textContent = error.message || "保存失败。";
        save.disabled = false;
        save.textContent = "保存场景";
      }
    });
  }

  async function load() {
    const detail = await App.api(`/api/app/characters/${encodeURIComponent(characterId)}`);
    state.detail = detail;
    if (state.selectedId && !(detail.periods || []).some(period => period.id === state.selectedId)) state.selectedId = null;
    if (!state.selectedId) state.selectedId = (detail.periods || [])[0]?.id || null;
    render();
    if (new URLSearchParams(location.search).get("created") === "1") {
      App.toast("角色已创建。下一步：准备一个场景人设。", "success");
    }
    App.pageTitle(`${detail.character.name} · 场景`);
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("characters");
    if (!characterId) { location.replace("/characters"); return; }
    $("#analyze-button").addEventListener("click", analyze);
    $("#add-scene-button").addEventListener("click", () => openSceneModal(null));
    try { await load(); }
    catch (error) {
      $("#scene-list").innerHTML = `<div class="empty-state"><h3>场景读不到</h3><p>${App.escapeHtml(error.message)}</p><a class="btn" href="/characters">返回角色</a></div>`;
      App.toast(error.message, "error");
    }
  }
  init();
})();
