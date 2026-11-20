(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  function setStatus(text, error = false) {
    const node = $("#image-status");
    node.textContent = text || "";
    node.className = error ? "error-text" : "note-line";
  }
  async function init() {
    await App.syncUser();
    App.mountSidebar("tools");
    App.pageTitle("生成图片");
    $("#back-link").innerHTML = `${App.icons.back} 返回工具`;
    $("#image-generate").addEventListener("click", async () => {
      const prompt = $("#image-prompt").value.trim();
      if (!prompt) { setStatus("先写一句画面描述。", true); return; }
      const button = $("#image-generate");
      button.disabled = true;
      button.textContent = "正在生成…";
      setStatus("正在调用图片模型，通常需要十几秒…");
      try {
        const result = await App.api("/api/app/tools/image", { method: "POST", json: { prompt, size: $("#image-size").value } });
        $("#image-empty").classList.add("hidden");
        $("#image-result").classList.remove("hidden");
        $("#image-preview").src = result.url;
        $("#image-download").href = result.url;
        $("#image-meta").textContent = `${result.model || "图片模型"} · ${result.size || ""} · ${App.formatBytes(result.bytes || 0)}`;
        setStatus("图片已生成。");
        App.toast("图片已生成。", "success");
      } catch (error) {
        setStatus(error.message || "生成失败，请重试。", true);
        App.toast(error.message || "生成失败", "error");
      } finally {
        button.disabled = false;
        button.textContent = "生成图片";
      }
    });
  }
  init();
})();