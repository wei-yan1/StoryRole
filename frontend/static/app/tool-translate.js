(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  function setStatus(text, error = false) {
    const node = $("#translate-status");
    node.textContent = text || "";
    node.className = error ? "error-text" : "note-line";
  }
  async function init() {
    await App.syncUser();
    App.mountSidebar("tools");
    App.pageTitle("翻译");
    $("#back-link").innerHTML = `${App.icons.back} 返回工具`;
    $("#translate-send").addEventListener("click", async () => {
      const text = $("#translate-text").value.trim();
      if (!text) { setStatus("先输入要翻译的文本。", true); return; }
      const button = $("#translate-send");
      button.disabled = true;
      button.textContent = "翻译中…";
      setStatus("正在翻译…");
      try {
        const result = await App.api("/api/app/tools/translate", {
          method: "POST",
          json: {
            text,
            source_lang: $("#translate-source").value,
            target_lang: $("#translate-target").value,
          },
        });
        $("#translate-result").textContent = result.translation || result.text || "";
        $("#translate-meta").textContent = `${result.model || "翻译模型"} · ${$("#translate-source").value} → ${$("#translate-target").value}`;
        $("#translate-copy").classList.remove("hidden");
        setStatus("翻译完成。");
      } catch (error) {
        setStatus(error.message || "翻译失败。", true);
      } finally {
        button.disabled = false;
        button.textContent = "开始翻译";
      }
    });
    $("#translate-copy").addEventListener("click", () => App.copyText($("#translate-result").textContent));
  }
  init();
})();