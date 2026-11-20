(() => {
  if (!App.requireAuth()) return;
  const state = { sources: [], files: [], busy: false, timer: 0 };
  const $ = App.qs;
  const statusLabels = {
    ready: "已就绪", processing: "解析中", failed: "解析失败", uploaded: "已上传", queued: "排队中",
  };

  function renderFiles() {
    const root = $("#file-list");
    if (!state.files.length) { root.innerHTML = ""; return; }
    root.innerHTML = state.files.map(file => `<span class="file-row">${App.icons.file}<span class="spacer">${App.escapeHtml(file.name)}</span><span class="faint">${App.formatBytes(file.size)}</span></span>`).join("");
  }

  function renderSources() {
    const root = $("#source-list");
    $("#source-count").textContent = `${state.sources.length} 份资料`;
    if (!state.sources.length) {
      root.innerHTML = `<div class="empty-state"><span class="empty-icon">${App.icons?.library || ""}</span><h3>还没有资料</h3><p>导入一份文本，系统会从里面整理角色、场景和人设。没有资料也可以先浏览界面，但角色需要资料才能建立。</p></div>`;
      return;
    }
    root.innerHTML = state.sources.map(source => {
      const label = statusLabels[source.status] || source.stage || source.status || "未知";
      const ready = source.status === "ready";
      return `
        <div class="source-row">
          <span class="source-icon">${App.icons.file}</span>
          <div class="source-copy">
            <div class="source-name">${App.escapeHtml(source.name)} <span class="pill ${ready ? "pill-mint pill-dot" : ""}">${App.escapeHtml(label)}</span>${source.source_kind === "bundled" ? `<span class="pill">内置</span>` : ""}</div>
            <div class="source-meta">${source.character_count || 0} 位角色 · ${source.chunk_count ? `${App.formatNumber(source.chunk_count)} 个片段` : (ready ? "全文已入库" : "等待解析")} · 更新于 ${App.escapeHtml(App.formatRelative(source.updated_at))}</div>
          </div>
          <div class="source-actions">
            <a class="btn btn-sm" href="/characters?source=${encodeURIComponent(source.novel_id)}">查看角色</a>
            <button class="icon-btn" type="button" data-rename="${App.escapeHtml(source.novel_id)}" title="重命名">${App.icons.more}</button>
            <button class="icon-btn" type="button" data-delete="${App.escapeHtml(source.novel_id)}" title="删除资料" style="color:var(--danger)">${App.icons.close}</button>
          </div>
        </div>`;
    }).join("");
    App.qsa("[data-rename]").forEach(button => button.addEventListener("click", () => renameSource(button.dataset.rename)));
    App.qsa("[data-delete]").forEach(button => button.addEventListener("click", () => deleteSource(button.dataset.delete)));
  }

  async function loadSources() {
    window.clearTimeout(state.timer);
    try {
      const data = await App.api("/api/app/sources");
      state.sources = data.items || [];
      renderSources();
      if (state.sources.some(source => ["processing", "queued", "uploaded"].includes(source.status))) {
        state.timer = window.setTimeout(loadSources, 4000);
      }
    } catch (error) {
      $("#source-list").innerHTML = `<div class="empty-state"><h3>读取资料失败</h3><p>${App.escapeHtml(error.message)}</p><button class="btn" onclick="location.reload()">重新加载</button></div>`;
      App.toast(error.message, "error");
    }
  }

  async function renameSource(id) {
    const source = state.sources.find(item => String(item.novel_id) === String(id));
    if (!source) return;
    const name = window.prompt("新的资料名称", source.name);
    if (!name || !name.trim() || name.trim() === source.name) return;
    try {
      await App.api(`/api/app/sources/${encodeURIComponent(id)}`, { method: "PATCH", json: { novel_name: name.trim() } });
      App.toast("资料名称已更新。", "success");
      await loadSources();
    } catch (error) { App.toast(error.message, "error"); }
  }

  async function deleteSource(id) {
    const source = state.sources.find(item => String(item.novel_id) === String(id));
    if (!source) return;
    if (!window.confirm(`删除资料「${source.name}」？相关的角色和对话将无法继续使用。`)) return;
    try {
      await App.api(`/api/app/sources/${encodeURIComponent(id)}`, { method: "DELETE" });
      App.toast("资料已删除。", "success");
      await loadSources();
    } catch (error) { App.toast(error.message, "error"); }
  }

  function setFiles(files) {
    state.files = Array.from(files || []);
    renderFiles();
    if (state.files.length && !$("#source-name").value.trim()) {
      const first = state.files[0].name.replace(/\.(txt|md|markdown)$/i, "");
      $("#source-name").value = first;
    }
  }

  async function upload() {
    if (state.busy) return;
    const errorNode = $("#upload-error");
    errorNode.textContent = "";
    if (!state.files.length) { errorNode.textContent = "先选择要导入的文件。"; return; }
    const name = $("#source-name").value.trim() || state.files[0].name.replace(/\.(txt|md|markdown)$/i, "");
    state.busy = true;
    const button = $("#upload-button");
    button.disabled = true;
    button.textContent = "正在上传…";
    try {
      const form = new FormData();
      form.append("novel_name", name);
      state.files.forEach(file => form.append("files", file, file.name));
      const result = await App.api("/api/app/sources/import", { method: "POST", body: form });
      App.toast(`已收到「${result.novel_name || name}」，正在后台解析。`, "success");
      state.files = [];
      renderFiles();
      $("#source-files").value = "";
      $("#source-file-top").value = "";
      await loadSources();
    } catch (error) {
      errorNode.textContent = error.message || "上传失败，请重试。";
    } finally {
      state.busy = false;
      button.disabled = false;
      button.textContent = "开始导入";
    }
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("library");
    App.pageTitle("资料");
    $("#source-files").addEventListener("change", event => setFiles(event.target.files));
    $("#source-file-top").addEventListener("change", event => setFiles(event.target.files));
    $("#upload-button").addEventListener("click", upload);
    const drop = $("#drop-area");
    ["dragenter", "dragover"].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.style.borderColor = "var(--accent)"; }));
    ["dragleave", "drop"].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.style.borderColor = ""; }));
    drop.addEventListener("drop", event => setFiles(event.dataTransfer.files));
    await loadSources();
  }

  init();
})();