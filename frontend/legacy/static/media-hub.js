(() => {
  const $ = selector => document.querySelector(selector);
  const labels = { image: "出图", omni: "读图", ocr: "OCR", asr: "转写", tts: "合成", translate: "翻译" };
  async function loadModels() {
    try {
      const data = await Studio.api("/api/v1/media/models");
      const chips = Object.entries(labels).map(([role, label]) => {
        const model = data.models?.[role] || "—";
        const verified = data.verified?.[role] !== false;
        return `<span class="model-chip" title="${verified ? "已实测" : "未实测"}">${label} <strong>${Studio.escapeHtml(model)}</strong></span>`;
      }).join("");
      $("#model-chips").innerHTML = chips;
      $("#model-status").textContent = "接口在线";
      $("#model-status").classList.add("tag-forest");
    } catch (error) {
      $("#model-status").textContent = "接口异常";
      $("#model-status").classList.add("tag-accent");
      Studio.toast(error.message, "error");
    }
  }
  loadModels();
})();
