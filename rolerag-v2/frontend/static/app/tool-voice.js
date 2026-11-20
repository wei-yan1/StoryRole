(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  const state = { file: null };
  function setStatus(id, text, error = false) {
    const node = $(id);
    node.textContent = text || "";
    node.className = error ? "error-text" : "note-line";
  }
  function setMode(mode) {
    App.qsa("[data-mode]").forEach(button => button.classList.toggle("is-current", button.dataset.mode === mode));
    $("#tts-panel").classList.toggle("hidden", mode !== "tts");
    $("#asr-panel").classList.toggle("hidden", mode !== "asr");
  }
  async function init() {
    await App.syncUser();
    App.mountSidebar("tools");
    App.pageTitle("语音");
    $("#back-link").innerHTML = `${App.icons.back} 返回工具`;
    App.qsa("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
    $("#tts-send").addEventListener("click", async () => {
      const text = $("#tts-text").value.trim();
      if (!text) { setStatus("#tts-status", "先写要朗读的文本。", true); return; }
      const button = $("#tts-send");
      button.disabled = true;
      button.textContent = "合成中…";
      setStatus("#tts-status", "正在生成语音…");
      try {
        const result = await App.api("/api/app/tools/speech", { method: "POST", json: { text, voice: $("#tts-voice").value } });
        $("#tts-result").classList.remove("hidden");
        $("#tts-audio").src = result.url;
        $("#tts-audio").load();
        $("#tts-download").href = result.url;
        $("#tts-meta").textContent = `${result.model || "语音模型"} · ${result.voice || $("#tts-voice").value} · ${App.formatBytes(result.bytes || 0)}`;
        setStatus("#tts-status", "语音已生成，点播放试听。");
      } catch (error) {
        setStatus("#tts-status", error.message || "合成失败。", true);
      } finally {
        button.disabled = false;
        button.textContent = "生成语音";
      }
    });
    $("#asr-file").addEventListener("change", event => {
      const file = event.target.files?.[0];
      if (!file) return;
      state.file = file;
      $("#asr-file-label").textContent = `${file.name} · ${App.formatBytes(file.size)}`;
      setStatus("#asr-status", "");
    });
    $("#asr-send").addEventListener("click", async () => {
      if (!state.file) { setStatus("#asr-status", "先选择一段音频。", true); return; }
      const button = $("#asr-send");
      button.disabled = true;
      button.textContent = "转写中…";
      setStatus("#asr-status", "正在上传并转写音频…");
      const form = new FormData();
      form.append("file", state.file, state.file.name);
      form.append("language", $("#asr-language").value);
      try {
        const result = await App.api("/api/app/tools/transcribe", { method: "POST", body: form });
        $("#asr-result").classList.remove("hidden");
        $("#asr-text").textContent = result.text || "";
        $("#asr-meta").textContent = `${result.model || "语音模型"} · ${result.format || "audio"} · ${App.formatNumber((result.text || "").length)} 字`;
        setStatus("#asr-status", "转写完成。");
      } catch (error) {
        setStatus("#asr-status", error.message || "转写失败。", true);
      } finally {
        button.disabled = false;
        button.textContent = "转写音频";
      }
    });
    $("#asr-copy").addEventListener("click", () => App.copyText($("#asr-text").textContent));
    setMode("tts");
  }
  init();
})();