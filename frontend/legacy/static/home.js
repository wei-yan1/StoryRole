(() => {
  const state = { library: [], context: Studio.getContext() };
  const stageLabels = { uploaded: "已收录", parsing: "解析章节", embedding: "生成向量", vector_indexing: "建立语义索引", keyword_indexing: "整理关键词", ready: "档案就绪", failed: "失败", cancelled: "已取消" };
  const $ = selector => document.querySelector(selector);

  function hrefFor(path, options = {}) {
    const params = new URLSearchParams();
    if (options.novel) params.set("novel", options.novel);
    if (options.character) params.set("character", options.character);
    if (options.period) params.set("period", options.period);
    return params.toString() ? `${path}?${params.toString()}` : path;
  }

  function renderContext() {
    const root = $("#home-context");
    if (!root) return;
    const novel = state.library.find(item => String(item.novel_id) === String(state.context.novelId)) || null;
    const character = state.context.characterName || (state.context.characterId ? `角色 ${state.context.characterId}` : "");
    const period = state.context.periodName || (state.context.periodId ? `时期 ${state.context.periodId}` : "");
    const items = [
      ["小说", novel?.novel_name || state.context.novelName || "尚未选择", state.context.novelId ? "已载入" : "从小说档案开始"],
      ["角色", character || "尚未建立", state.context.characterId ? "档案已建立" : "需要先选小说"],
      ["时期", period || "尚未辨认", state.context.periodId ? "对话已解锁" : "需要先建立角色"]
    ];
    root.innerHTML = items.map(([label, value, note]) => `
      <div class="home-context-item"><small>${Studio.escapeHtml(label)}</small><strong title="${Studio.escapeHtml(value)}">${Studio.escapeHtml(value)}</strong><small>${Studio.escapeHtml(note)}</small></div>
    `).join("");
  }

  function renderSteps() {
    const root = $("#home-steps");
    if (!root) return;
    const hasNovel = Boolean(state.library.length);
    const hasCharacter = Boolean(state.context.characterId);
    const hasPeriod = Boolean(state.context.periodId);
    const currentNovel = state.context.novelId || state.library[0]?.novel_id || "";
    const steps = [
      {
        no: "01", title: "收录原文", desc: hasNovel ? `已有 ${state.library.length} 本小说档案，可直接继续。` : "导入 TXT / Markdown，建立章节与语义索引。",
        status: hasNovel ? "档案已收录" : "从零开始", href: "/novels", done: hasNovel
      },
      {
        no: "02", title: "建立人物", desc: hasCharacter ? `当前角色：${state.context.characterName || "已建立"}` : "从原文里找出一个人物，生成他的女娲档案。",
        status: hasCharacter ? "角色已就绪" : "选择人物", href: hrefFor("/characters", { novel: currentNovel }), done: hasCharacter
      },
      {
        no: "03", title: "辨认时期", desc: hasPeriod ? `当前时期：${state.context.periodName || "已选择"}` : "让角色回到具体的人生阶段，再生成该时期的画像。",
        status: hasPeriod ? "时期已就绪" : "分析时间线", href: hrefFor("/periods", { novel: state.context.novelId, character: state.context.characterId }), done: hasPeriod
      },
      {
        no: "04", title: "开始交谈", desc: hasPeriod ? "画像已准备好，进入对话纸面。" : "完成时期画像后，才能进入角色对话。",
        status: hasPeriod ? "可以开始" : "等待解锁", href: hrefFor("/chat", { novel: state.context.novelId, character: state.context.characterId, period: state.context.periodId }), done: hasPeriod
      }
    ];
    let nextMarked = false;
    root.innerHTML = steps.map(step => {
      const isNext = !step.done && !nextMarked;
      if (isNext) nextMarked = true;
      return `<a class="step-card ${step.done ? "is-done" : ""} ${isNext ? "is-next" : ""}" href="${step.href}">
        <div class="step-no">${step.no} / ${step.done ? "DONE" : isNext ? "NEXT" : "WAIT"}</div>
        <h3>${Studio.escapeHtml(step.title)}</h3>
        <p>${Studio.escapeHtml(step.desc)}</p>
        <div class="step-link"><span>${Studio.escapeHtml(step.status)}</span><span aria-hidden="true">→</span></div>
      </a>`;
    }).join("");
  }

  function renderLibrary() {
    const root = $("#recent-novels");
    if (!root) return;
    if (!state.library.length) {
      root.innerHTML = `<div class="empty-state"><strong>还没有小说档案。</strong><p>从 TXT 或 Markdown 开始，建立第一本可以检索、可以交谈的小说。</p><a class="btn btn-ghost btn-sm" href="/novels">去收录原文</a></div>`;
      return;
    }
    root.innerHTML = state.library.slice(0, 4).map((item, index) => `
      <a class="novel-mini" href="${hrefFor("/characters", { novel: item.novel_id })}" data-novel="${Studio.escapeHtml(item.novel_id)}">
        <span class="novel-mini-mark">${String(index + 1).padStart(2, "0")}</span>
        <span class="novel-mini-copy"><strong>${Studio.escapeHtml(item.novel_name || "未命名小说")}</strong><small>${Studio.escapeHtml(stageLabels[item.stage] || item.stage || "档案")} · ${Studio.formatNumber(item.chunk_count || 0)} 段</small></span>
        <span aria-hidden="true">↗</span>
      </a>
    `).join("");
    root.querySelectorAll("[data-novel]").forEach(node => {
      node.addEventListener("click", () => {
        const item = state.library.find(entry => String(entry.novel_id) === node.dataset.novel);
        if (item) Studio.saveContext({ novelId: item.novel_id, novelName: item.novel_name });
      });
    });
  }

  function renderFocus() {
    const panel = $("#focus-panel");
    if (!panel) return;
    const novel = state.library.find(item => String(item.novel_id) === String(state.context.novelId));
    const novelLabel = novel?.novel_name || state.context.novelName || "未选择";
    $("#focus-novel").textContent = `当前小说 · ${novelLabel}`;
    $("#focus-role").textContent = state.context.characterName ? `当前角色 · ${state.context.characterName}` : "当前角色 · 未建立";

    let title = "先把第一本小说收进来。";
    let copy = "档案室需要一段原文。导入之后，系统会为它建立章节与语义索引，人物和时期才有落脚之处。";
    let href = "/novels";
    let action = "前往小说档案 →";
    if (state.library.length && !state.context.novelId) {
      title = "书架里有档案，选一本继续。";
      copy = "你已经收录了小说。挑一本作为当前档案，再为人物的出现建立身份。";
      href = "/novels";
      action = "选择小说 →";
    } else if (state.context.novelId && !state.context.characterId) {
      title = "读者已经就位，角色还没到场。";
      copy = "从当前小说里选一个人物，系统会为它建立女娲身份档案，并把它接到时期时间线上。";
      href = hrefFor("/characters", { novel: state.context.novelId });
      action = "建立人物 →";
    } else if (state.context.characterId && !state.context.periodId) {
      title = "让角色回到他自己的年代。";
      copy = "时期决定角色能看见什么、记得什么。先辨认他处在哪一段人生，再生成这一阶段的画像。";
      href = hrefFor("/periods", { novel: state.context.novelId, character: state.context.characterId });
      action = "辨认时期 →";
    } else if (state.context.characterId && state.context.periodId) {
      title = "纸页已经翻开，继续聊下去。";
      copy = "当前角色和时期都已就绪。直接进入对话，让他用自己的语气回答你。";
      href = hrefFor("/chat", { novel: state.context.novelId, character: state.context.characterId, period: state.context.periodId });
      action = "进入对话 →";
    }
    const kicker = panel.querySelector(".section-kicker");
    const heading = panel.querySelector("h2");
    const paragraph = panel.querySelector("p");
    const link = panel.querySelector("a");
    if (kicker) kicker.textContent = "下一步 / NEXT";
    heading.textContent = title;
    paragraph.textContent = copy;
    link.href = href;
    link.innerHTML = `${action} <span aria-hidden="true">→</span>`;
  }

  async function load() {
    try {
      state.library = await Studio.api("/api/v1/novels/library");
      const chosen = state.library.find(item => String(item.novel_id) === String(state.context.novelId));
      if (chosen && chosen.novel_name && chosen.novel_name !== state.context.novelName) {
        Studio.saveContext({ novelId: chosen.novel_id, novelName: chosen.novel_name });
        state.context = Studio.getContext();
      }
      $("#home-foot").textContent = `${state.library.length} 本小说档案 · LOCAL WORKSPACE`;
      renderContext();
      renderSteps();
      renderLibrary();
      renderFocus();
    } catch (error) {
      Studio.toast(error.message, "error");
      $("#recent-novels").innerHTML = `<div class="empty-state"><strong>书架暂时读取失败。</strong><p>${Studio.escapeHtml(error.message)}</p><a class="btn btn-ghost btn-sm" href="/novels">打开小说档案</a></div>`;
    }
  }

  document.addEventListener("studio:contextchange", event => {
    state.context = event.detail || {};
    renderContext();
    renderSteps();
    renderFocus();
  });

  load();
})();
