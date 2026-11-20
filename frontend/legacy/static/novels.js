(() => {
  const state = { library: [], files: [], importId: null, polling: false, filter: "", busy: false };
  const stageLabels = { uploaded: "已收录", parsing: "解析章节", embedding: "生成向量", vector_indexing: "建立语义索引", keyword_indexing: "整理关键词", ready: "档案就绪", failed: "失败", cancelled: "已取消" };
  const $ = selector => document.querySelector(selector);

  function renderFiles() {
    const label = $("#file-label");
    const pills = $("#selected-files");
    if (!label || !pills) return;
    label.textContent = state.files.length ? `${state.files.length} 个文件已加入` : "把文本拖到这里，或点击选择";
    pills.innerHTML = state.files.map((file, index) => `<span class="file-pill"><b>${Studio.escapeHtml(file.name)}</b>${Studio.formatBytes(file.size)}<button type="button" data-remove="${index}" aria-label="移除 ${Studio.escapeHtml(file.name)}">×</button></span>`).join("");
    pills.querySelectorAll("[data-remove]").forEach(button => {
      button.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        state.files.splice(Number(button.dataset.remove), 1);
        renderFiles();
      });
    });
    if (!$("#novel-name").value && state.files[0]) $("#novel-name").value = state.files[0].name.replace(/\.[^.]+$/, "");
  }

  function addFiles(fileList) {
    const incoming = [...fileList].filter(file => /\.(txt|md|markdown)$/i.test(file.name));
    if (!incoming.length) {
      setStatus("只接受 TXT 或 Markdown 文件。", true);
      return;
    }
    state.files = incoming;
    renderFiles();
    setStatus(`已加入 ${incoming.length} 个文件，准备建立索引。`);
  }

  function setStatus(text, error = false, success = false) {
    const node = $("#import-status");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("error", error);
    node.classList.toggle("success", success);
  }

  function setBusy(value, label) {
    state.busy = value;
    const button = $("#import-button");
    if (button) {
      button.disabled = value;
      button.textContent = label || (value ? "正在建立档案…" : "建立文本索引");
    }
    $("#cancel-import")?.classList.toggle("hidden", !value && !state.polling);
    $("#cancel-import")?.toggleAttribute("disabled", !value);
  }

  function showProgress(job) {
    $("#import-progress")?.classList.remove("hidden");
    $("#progress-stage").textContent = stageLabels[job.stage] || job.stage || "准备任务";
    $("#progress-count").textContent = `${job.processed_files || 0} / ${job.total_files || 0} 个文件`;
    const percent = job.total_files ? Math.round(((job.processed_files || 0) / job.total_files) * 100) : (job.status === "completed" ? 100 : 8);
    $("#progress-fill").style.width = `${Math.max(3, Math.min(100, percent))}%`;
    $("#import-metrics").textContent = `${Studio.formatNumber(job.chunk_count || 0)} 个文本片段 / ${Studio.formatBytes(job.total_bytes || 0)}`;
  }

  function renderLibrary() {
    const root = $("#novel-library");
    if (!root) return;
    const context = Studio.getContext();
    const query = state.filter.trim().toLowerCase();
    const items = state.library.filter(item => !query || String(item.novel_name || "").toLowerCase().includes(query));
    $("#library-count").textContent = `${state.library.length} 本`;
    const active = state.library.find(item => String(item.novel_id) === String(context.novelId));
    $("#library-active").textContent = active ? active.novel_name : "未选择";
    $("#library-active").classList.toggle("tag-forest", Boolean(active));
    if (!items.length) {
      root.innerHTML = `<div class="empty-state"><strong>${state.library.length ? "没有匹配的档案。" : "书架还是空的。"}</strong><p>${state.library.length ? "换一个关键词，或者从左侧投递新的原文。" : "把第一部小说导入进来，角色和时期才有原文可依。"}</p></div>`;
      return;
    }
    root.innerHTML = items.map((item, index) => `
      <article class="library-row ${String(item.novel_id) === String(context.novelId) ? "active" : ""}" data-id="${Studio.escapeHtml(item.novel_id)}">
        <span class="library-index">${String(index + 1).padStart(2, "0")}</span>
        <div class="library-copy">
          <strong title="${Studio.escapeHtml(item.novel_name)}">${Studio.escapeHtml(item.novel_name || "未命名小说")}</strong>
          <small><span>${Studio.escapeHtml(stageLabels[item.stage] || item.stage || "档案")}</span><span>${Studio.formatNumber(item.chunk_count || 0)} 段</span><span>${Studio.formatDate(item.updated_at || item.created_at)}</span></small>
        </div>
        <div class="library-action">
          <a class="row-enter" data-open href="/characters?novel=${encodeURIComponent(item.novel_id)}" title="用这本小说建立人物" aria-label="用这本小说建立人物">↗</a>
          <button class="row-icon" type="button" data-rename title="重命名档案" aria-label="重命名档案">✎</button>
          <button class="row-icon danger" type="button" data-delete title="删除档案" aria-label="删除档案">×</button>
        </div>
      </article>
    `).join("");
    root.querySelectorAll(".library-row").forEach(row => {
      const item = state.library.find(entry => String(entry.novel_id) === row.dataset.id);
      row.addEventListener("click", event => {
        if (event.target.closest("button, a")) return;
        chooseNovel(item);
      });
      row.querySelector("[data-open]").addEventListener("click", event => {
        event.stopPropagation();
        Studio.saveContext({ novelId: item.novel_id, novelName: item.novel_name });
      });
      row.querySelector("[data-rename]").addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        renameNovel(item);
      });
      row.querySelector("[data-delete]").addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        deleteNovel(item);
      });
    });
  }

  function chooseNovel(item) {
    if (!item) return;
    Studio.saveContext({ novelId: item.novel_id, novelName: item.novel_name });
    renderLibrary();
    const next = $("#import-next");
    if (next) {
      next.classList.remove("hidden");
      next.innerHTML = `<a class="btn btn-accent btn-sm" href="/characters?novel=${encodeURIComponent(item.novel_id)}">继续建立人物 <span aria-hidden="true">→</span></a>`;
    }
    Studio.toast(`当前小说：${item.novel_name}`, "success");
  }

  async function loadLibrary(preferredId) {
    try {
      state.library = await Studio.api("/api/v1/novels/library");
      const context = Studio.getContext();
      const preferred = state.library.find(item => String(item.novel_id) === String(preferredId || context.novelId));
      if (preferred && String(preferred.novel_id) !== String(context.novelId)) {
        Studio.saveContext({ novelId: preferred.novel_id, novelName: preferred.novel_name });
      } else if (!context.novelId && state.library.length) {
        Studio.saveContext({ novelId: state.library[0].novel_id, novelName: state.library[0].novel_name });
      }
      renderLibrary();
      return preferred || state.library[0] || null;
    } catch (error) {
      Studio.toast(error.message, "error");
      $("#novel-library").innerHTML = `<div class="empty-state"><strong>档案库读取失败。</strong><p>${Studio.escapeHtml(error.message)}</p></div>`;
      return null;
    }
  }

  async function renameNovel(item) {
    const name = await Studio.prompt({
      title: "重命名档案",
      description: "名称只影响档案的显示，不会改动原文内容。",
      label: "档案名称",
      value: item.novel_name,
      confirmText: "保存名称"
    });
    if (!name || name === item.novel_name) return;
    try {
      const result = await Studio.api(`/api/v1/novels/${encodeURIComponent(item.novel_id)}`, { method: "PATCH", json: { novel_name: name } });
      item.novel_name = result.novel_name;
      const context = Studio.getContext();
      if (String(context.novelId) === String(item.novel_id)) Studio.saveContext({ novelId: item.novel_id, novelName: result.novel_name });
      await loadLibrary(item.novel_id);
      Studio.toast("档案名称已更新。", "success");
    } catch (error) {
      Studio.toast(error.message, "error");
    }
  }

  async function deleteNovel(item) {
    const ok = await Studio.confirm({
      title: "删除这本小说？",
      description: "删除后，这本小说的人物、时期和画像也会一并移除。",
      message: `“${item.novel_name}”将从档案库中删除，这个操作不能撤销。`,
      confirmText: "删除档案",
      danger: true
    });
    if (!ok) return;
    try {
      await Studio.api(`/api/v1/novels/${encodeURIComponent(item.novel_id)}`, { method: "DELETE" });
      const context = Studio.getContext();
      if (String(context.novelId) === String(item.novel_id)) {
        Studio.clearContext();
      }
      await loadLibrary();
      Studio.toast("小说档案已删除。", "success");
    } catch (error) {
      Studio.toast(error.message, "error");
    }
  }

  async function finishImport(id) {
    state.polling = false;
    state.importId = null;
    localStorage.removeItem("storyrole_active_import");
    $("#cancel-import")?.classList.add("hidden");
    $("#retry-import")?.classList.add("hidden");
    setBusy(false);
    setStatus("文本与检索索引已就绪。可以建立人物了。", false, true);
    const item = await loadLibrary(id);
    if (item) chooseNovel(item);
    const next = $("#import-next");
    if (next) next.classList.remove("hidden");
    Studio.toast("小说档案已建立。", "success");
  }

  async function pollImport(id) {
    if (state.polling) return;
    state.polling = true;
    state.importId = id;
    localStorage.setItem("storyrole_active_import", id);
    $("#cancel-import")?.classList.remove("hidden");
    $("#retry-import")?.classList.add("hidden");
    setStatus("正在建立索引…");
    try {
      for (let attempt = 0; attempt < 300; attempt += 1) {
        const job = await Studio.api(`/api/v1/novels/imports/${encodeURIComponent(id)}`);
        showProgress(job);
        if (job.status === "completed" && job.stage === "ready") {
          await finishImport(id);
          return;
        }
        if (["failed", "cancelled"].includes(job.status)) {
          state.polling = false;
          $("#cancel-import")?.classList.add("hidden");
          $("#retry-import")?.classList.remove("hidden");
          setStatus(job.error || (job.status === "cancelled" ? "导入任务已取消。" : "导入未完成，请重试。"), true);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
      state.polling = false;
      $("#cancel-import")?.classList.add("hidden");
      setStatus("导入仍在运行，刷新页面可以继续查看。", true);
    } catch (error) {
      state.polling = false;
      $("#cancel-import")?.classList.add("hidden");
      $("#retry-import")?.classList.remove("hidden");
      setStatus(error.message, true);
    }
  }

  async function startImport() {
    if (state.busy || state.polling) return;
    if (!state.files.length) {
      setStatus("先选择 TXT 或 Markdown 文件。", true);
      return;
    }
    setBusy(true, "正在建立档案…");
    setStatus("正在准备导入…");
    $("#import-progress")?.classList.remove("hidden");
    $("#progress-stage").textContent = "准备任务";
    $("#progress-count").textContent = "0 / 0 个文件";
    $("#progress-fill").style.width = "8%";
    $("#import-metrics").textContent = "";
    $("#import-next")?.classList.add("hidden");
    $("#retry-import")?.classList.add("hidden");
    $("#cancel-import")?.classList.remove("hidden");
    const form = new FormData();
    state.files.forEach(file => form.append("files", file));
    form.append("novel_name", $("#novel-name").value.trim() || state.files[0].name);
    try {
      const accepted = await Studio.api("/api/v1/novels/imports", { method: "POST", body: form });
      setStatus("文本已接收，正在建立索引…");
      await loadLibrary(accepted.import_id);
      await pollImport(accepted.import_id);
    } catch (error) {
      setBusy(false);
      setStatus(error.message, true);
    }
  }

  async function cancelImport() {
    if (!state.importId) return;
    try {
      await Studio.api(`/api/v1/novels/imports/${encodeURIComponent(state.importId)}/cancel`, { method: "POST" });
      state.polling = false;
      $("#cancel-import")?.classList.add("hidden");
      $("#retry-import")?.classList.remove("hidden");
      setBusy(false);
      setStatus("导入任务已取消，可以重试。", true);
    } catch (error) {
      Studio.toast(error.message, "error");
    }
  }

  async function retryImport() {
    if (!state.importId) return;
    try {
      setStatus("正在重新排队…");
      await Studio.api(`/api/v1/novels/imports/${encodeURIComponent(state.importId)}/retry`, { method: "POST" });
      $("#retry-import")?.classList.add("hidden");
      await pollImport(state.importId);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function restoreThreeBody() {
    const button = $("#restore-three-body");
    button.disabled = true;
    try {
      const result = await Studio.api("/api/v1/storyrole/bundled/three-body/activate", { method: "POST" });
      const id = result.novel?.novel_id;
      await loadLibrary(id);
      if (id) {
        const item = state.library.find(entry => String(entry.novel_id) === String(id));
        if (item) chooseNovel(item);
      }
      Studio.toast("内置三体档案已恢复。", "success");
    } catch (error) {
      Studio.toast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  function bind() {
    $("#novel-files").addEventListener("change", event => addFiles(event.target.files));
    const zone = $("#drop-zone");
    ["dragenter", "dragover"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add("drag-active"); }));
    ["dragleave", "drop"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove("drag-active"); }));
    zone.addEventListener("drop", event => addFiles(event.dataTransfer.files));
    $("#import-button").addEventListener("click", startImport);
    $("#cancel-import").addEventListener("click", cancelImport);
    $("#retry-import").addEventListener("click", retryImport);
    $("#restore-three-body").addEventListener("click", restoreThreeBody);
    $("#library-search").addEventListener("input", event => { state.filter = event.target.value; renderLibrary(); });
    document.addEventListener("studio:contextchange", renderLibrary);
  }

  async function init() {
    bind();
    await loadLibrary();
    const active = localStorage.getItem("storyrole_active_import");
    if (active) pollImport(active);
  }

  init();
})();
