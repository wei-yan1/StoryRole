(() => {
  if (!App.requireAuth()) return;
  const state = { files: [], busy: false };
  const $ = App.qs;

  function renderFiles() {
    const root = $("#file-list");
    if (!state.files.length) { root.innerHTML = ""; return; }
    root.innerHTML = state.files.map(file => `<span class="file-row">${App.icons.file}<span class="spacer">${App.escapeHtml(file.name)}</span><span class="faint">${App.formatBytes(file.size)}</span></span>`).join("");
  }

  function setFiles(files) {
    state.files = Array.from(files || []).filter(file => /\.(txt|md|markdown)$/i.test(file.name));
    renderFiles();
    if (state.files.length && !$("#source-name").value.trim()) {
      $("#source-name").value = state.files[0].name.replace(/\.(txt|md|markdown)$/i, "");
    }
    if (files && files.length && !state.files.length) {
      $("#upload-error").textContent = "只支持 TXT、Markdown 文本文件。";
    }
  }

  async function upload() {
    if (state.busy) return;
    const errorNode = $("#upload-error");
    errorNode.textContent = "";
    if (!state.files.length) { errorNode.textContent = "先选择要导入的小说文件。"; return; }
    const name = $("#source-name").value.trim() || state.files[0].name.replace(/\.(txt|md|markdown)$/i, "");
    if (!name) { errorNode.textContent = "请填写小说名称。"; $("#source-name").focus(); return; }
    state.busy = true;
    const button = $("#upload-button");
    button.disabled = true;
    button.textContent = "正在上传…";
    try {
      const form = new FormData();
      form.append("novel_name", name);
      state.files.forEach(file => form.append("files", file, file.name));
      const result = await App.api("/api/app/sources/import", { method: "POST", body: form });
      App.toast(`「${result.novel_name || name}」已放上书架。`, "success");
      button.textContent = "正在打开小说…";
      let target = result.import_id ? `/novels/${encodeURIComponent(result.import_id)}` : "/";
      if (result.import_id) {
        try {
          const detail = await App.api(`/api/app/novels/${encodeURIComponent(result.import_id)}`);
          if (detail?.novel?.slug) target = `/novels/${encodeURIComponent(detail.novel.slug)}`;
        } catch {
          // The job may still be queued; the id route remains valid.
        }
      }
      window.setTimeout(() => { location.href = target; }, 700);
    } catch (error) {
      errorNode.textContent = error.message || "上传失败，请重试。";
      state.busy = false;
      button.disabled = false;
      button.textContent = "导入到书架";
    }
  }

  async function init() {
    await App.syncUser();
    App.mountSidebar("shelf");
    App.pageTitle("新增小说");
    $("#source-files").addEventListener("change", event => setFiles(event.target.files));
    $("#upload-button").addEventListener("click", upload);
    $("#source-name").addEventListener("keydown", event => {
      if (event.key === "Enter") { event.preventDefault(); $("#source-files").click(); }
    });
    const drop = $("#drop-area");
    ["dragenter", "dragover"].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.add("is-dragging"); }));
    ["dragleave", "dragend"].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.remove("is-dragging"); }));
    drop.addEventListener("drop", event => {
      event.preventDefault();
      drop.classList.remove("is-dragging");
      setFiles(event.dataTransfer.files);
    });
  }

  init();
})();
