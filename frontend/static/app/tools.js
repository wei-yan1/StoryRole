(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  async function init() {
    await App.syncUser();
    App.mountSidebar("tools");
    App.pageTitle("工具");
    App.qsa("[data-icon]").forEach(node => { node.innerHTML = App.icons[node.dataset.icon] || ""; });
    try {
      const data = await App.api("/api/app/tools/models");
      const labels = { image: "出图", image_fast: "快速出图", ocr: "OCR", omni: "读图", asr: "转写", tts: "语音合成", translate: "翻译" };
      $("#model-chips").innerHTML = Object.entries(labels).map(([role, label]) => {
        const id = data.models?.[role];
        if (!id) return "";
        const verified = data.verified?.[role] !== false;
        return `<span class="pill ${verified ? "pill-mint pill-dot" : ""}" title="${verified ? "已配置并验证" : "配置已读取"}"><span class="faint">${label}</span> <span class="mono" style="font-size:9px">${App.escapeHtml(id)}</span></span>`;
      }).join("");
      $("#model-status").textContent = "服务在线";
    } catch (error) {
      $("#model-status").textContent = "模型状态未知";
      $("#model-chips").innerHTML = `<span class="error-text">${App.escapeHtml(error.message)}</span>`;
    }
  }
  init();
})();