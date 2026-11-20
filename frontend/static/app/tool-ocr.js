(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  const state = { mode: "ocr", file: null, objectUrl: "" };
  function setStatus(text, error = false) {
    const node = $("#vision-status");
    node.textContent = text || "";
    node.className = error ? "error-text" : "note-line";
  }
  function setMode(mode) {
    state.mode = mode;
    App.qsa("[data-mode]").forEach(button => button.classList.toggle("is-current", button.dataset.mode === mode));
    $("#vision-submit").textContent = mode === "ocr" ? "开始识别" : "描述图片";
    $("#vision-title").textContent = mode === "ocr" ? "上传一张图片" : "上传一张图片";
    $("#vision-lead").textContent = mode === "ocr" ? "OCR 适合截图和文档；会尽量保留原文的换行与段落。" : "描述模式会概括画面内容、主体、风格和可见细节。";
    setStatus("");
  }
  async function init() {
    await App.syncUser();
    App.mountSidebar("tools");
    App.pageTitle("读图与 OCR");
    $("#back-link").innerHTML = `${App.icons.back} 返回工具`;
    App.qsa("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
    $("#vision-file").addEventListener("change", event => {
      const file = event.target.files?.[0];
      if (!file) return;
      state.file = file;
      $("#vision-file-label").textContent = `${file.name} · ${App.formatBytes(file.size)}`;
      if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = URL.createObjectURL(file);
      $("#vision-preview").src = state.objectUrl;
      $("#vision-preview").classList.remove("hidden");
      setStatus("");
    });
    $("#vision-submit").addEventListener("click", async () => {
      if (!state.file) { setStatus("先选择一张图片。", true); return; }
      const button = $("#vision-submit");
      button.disabled = true;
      button.textContent = state.mode === "ocr" ? "正在识别…" : "正在描述…";
      setStatus(state.mode === "ocr" ? "正在提取图片文字…" : "正在理解画面…");
      const form = new FormData();
      form.append("file", state.file, state.file.name);
      const prompt = $("#vision-prompt").value.trim();
      if (prompt) form.append("prompt", prompt);
      try {
        const result = await App.api(state.mode === "ocr" ? "/api/app/tools/ocr" : "/api/app/tools/vision", { method: "POST", body: form });
        $("#vision-text").textContent = result.text || "没有识别到文字。";
        $("#vision-meta").textContent = `${result.model || "视觉模型"} · ${state.mode === "ocr" ? "OCR" : "图片描述"} · ${App.formatNumber((result.text || "").length)} 字`;
        $("#vision-copy").classList.remove("hidden");
        setStatus("识别完成。");
      } catch (error) {
        setStatus(error.message || "识别失败，请重试。", true);
        App.toast(error.message || "识别失败", "error");
      } finally {
        button.disabled = false;
        button.textContent = state.mode === "ocr" ? "开始识别" : "描述图片";
      }
    });
    $("#vision-copy").addEventListener("click", () => App.copyText($("#vision-text").textContent));
    setMode("ocr");
  }
  init();
})();