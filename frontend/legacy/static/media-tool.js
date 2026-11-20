(() => {
  const page = document.body.dataset.media || "";
  const state = { visionMode: "ocr" };
  const $ = selector => document.querySelector(selector);

  function setStatus(selector, text, error = false, success = false) {
    const node = $(selector);
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("error", error);
    node.classList.toggle("success", success);
  }

  function setButtonBusy(button, busy, label) {
    if (!button) return;
    button.disabled = busy;
    const span = button.querySelector("span");
    if (span && label) span.textContent = label;
  }

  async function copyText(text, button) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    if (button) {
      const original = button.textContent;
      button.textContent = "已复制";
      window.setTimeout(() => { button.textContent = original; }, 1400);
    }
  }

  async function loadModels() {
    const labels = { image: "出图", omni: "读图", ocr: "OCR", asr: "转写", tts: "合成", translate: "翻译" };
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

  function bindImage() {
    $("#image-generate").addEventListener("click", async () => {
      const prompt = $("#image-prompt").value.trim();
      if (!prompt) return setStatus("#image-status", "先写一句画面描述。", true);
      setButtonBusy($("#image-generate"), true, "生成中…");
      setStatus("#image-status", "正在调用图片模型，通常需要十几秒…");
      $("#image-result").classList.add("hidden");
      try {
        const result = await Studio.api("/api/v1/media/images/generate", {
          method: "POST",
          json: { prompt, size: $("#image-size").value }
        });
        $("#image-preview").src = result.url;
        $("#image-download").href = result.url;
        $("#image-meta").textContent = `${result.model || "图片模型"} · ${result.size || ""} · ${Studio.formatBytes(result.bytes || 0)}`;
        $("#image-result").classList.remove("hidden");
        setStatus("#image-status", "图片已生成，保存在项目媒体目录。", false, true);
      } catch (error) {
        setStatus("#image-status", error.message, true);
      } finally {
        setButtonBusy($("#image-generate"), false, "生成图片");
      }
    });
  }

  function bindRead() {
    document.querySelectorAll("[data-vision-mode]").forEach(button => {
      button.addEventListener("click", () => {
        state.visionMode = button.dataset.visionMode;
        document.querySelectorAll("[data-vision-mode]").forEach(item => item.classList.toggle("is-current", item === button));
        $("#vision-submit span").textContent = state.visionMode === "ocr" ? "开始识别" : "描述图片";
        setStatus("#vision-status", "");
        $("#vision-result").classList.add("hidden");
      });
    });
    $("#vision-file").addEventListener("change", () => {
      const file = $("#vision-file").files?.[0];
      if (!file) return;
      $("#vision-file-label").textContent = `${file.name} · ${Studio.formatBytes(file.size)}`;
      const image = $("#vision-preview-img");
      if (image.dataset.url) URL.revokeObjectURL(image.dataset.url);
      const url = URL.createObjectURL(file);
      image.dataset.url = url;
      image.src = url;
      $("#vision-preview").classList.remove("hidden");
    });
    $("#vision-submit").addEventListener("click", async () => {
      const file = $("#vision-file").files?.[0];
      if (!file) return setStatus("#vision-status", "先选择一张图片。", true);
      const form = new FormData();
      form.append("file", file);
      const prompt = $("#vision-prompt").value.trim();
      if (prompt) form.append("prompt", prompt);
      const endpoint = state.visionMode === "ocr" ? "/api/v1/media/ocr" : "/api/v1/media/images/describe";
      setButtonBusy($("#vision-submit"), true, state.visionMode === "ocr" ? "识别中…" : "分析中…");
      setStatus("#vision-status", state.visionMode === "ocr" ? "正在提取图片文字…" : "正在理解画面…");
      $("#vision-result").classList.add("hidden");
      try {
        const result = await Studio.api(endpoint, { method: "POST", body: form });
        $("#vision-text").textContent = result.text || "";
        $("#vision-meta").textContent = `${result.model || "视觉模型"} · ${state.visionMode === "ocr" ? "OCR" : "图片描述"}`;
        $("#vision-copy").disabled = false;
        $("#vision-result").classList.remove("hidden");
        setStatus("#vision-status", "识别完成。", false, true);
      } catch (error) {
        setStatus("#vision-status", error.message, true);
      } finally {
        setButtonBusy($("#vision-submit"), false, state.visionMode === "ocr" ? "开始识别" : "描述图片");
      }
    });
    $("#vision-copy").addEventListener("click", () => copyText($("#vision-text").textContent, $("#vision-copy")));
  }

  function bindVoice() {
    $("#tts-send").addEventListener("click", async () => {
      const text = $("#tts-text").value.trim();
      if (!text) return setStatus("#tts-status", "先写要朗读的文本。", true);
      setButtonBusy($("#tts-send"), true, "合成中…");
      setStatus("#tts-status", "正在生成语音…");
      $("#tts-result").classList.add("hidden");
      try {
        const result = await Studio.api("/api/v1/media/audio/speech", {
          method: "POST",
          json: { text, voice: $("#tts-voice").value }
        });
        $("#tts-audio").src = result.url;
        $("#tts-audio").load();
        $("#tts-download").href = result.url;
        $("#tts-meta").textContent = `${result.model || "语音模型"} · ${result.voice || $("#tts-voice").value} · ${Studio.formatBytes(result.bytes || 0)}`;
        $("#tts-result").classList.remove("hidden");
        setStatus("#tts-status", "语音已生成，点播放试听。", false, true);
      } catch (error) {
        setStatus("#tts-status", error.message, true);
      } finally {
        setButtonBusy($("#tts-send"), false, "合成语音");
      }
    });
    $("#asr-file").addEventListener("change", () => {
      const file = $("#asr-file").files?.[0];
      if (!file) return;
      $("#asr-file-label").textContent = `${file.name} · ${Studio.formatBytes(file.size)}`;
      setStatus("#asr-status", "");
    });
    $("#asr-send").addEventListener("click", async () => {
      const file = $("#asr-file").files?.[0];
      if (!file) return setStatus("#asr-status", "先选择一段音频。", true);
      const form = new FormData();
      form.append("file", file);
      form.append("language", $("#asr-language").value);
      setButtonBusy($("#asr-send"), true, "转写中…");
      setStatus("#asr-status", "正在上传并转写音频…");
      $("#asr-result").classList.add("hidden");
      try {
        const result = await Studio.api("/api/v1/media/audio/transcribe", { method: "POST", body: form });
        $("#asr-text").textContent = result.text || "";
        $("#asr-meta").textContent = `${result.model || "语音模型"} · ${result.format || "audio"}`;
        $("#asr-result").classList.remove("hidden");
        setStatus("#asr-status", "转写完成。", false, true);
      } catch (error) {
        setStatus("#asr-status", error.message, true);
      } finally {
        setButtonBusy($("#asr-send"), false, "转写音频");
      }
    });
  }

  function bindTranslate() {
    $("#translate-send").addEventListener("click", async () => {
      const text = $("#translate-text").value.trim();
      if (!text) return setStatus("#translate-status", "先写要翻译的文本。", true);
      setButtonBusy($("#translate-send"), true, "翻译中…");
      setStatus("#translate-status", "正在翻译…");
      try {
        const result = await Studio.api("/api/v1/media/translate", {
          method: "POST",
          json: {
            text,
            source_lang: $("#translate-source").value,
            target_lang: $("#translate-target").value
          }
        });
        $("#translate-output").textContent = result.text || "";
        $("#translate-meta").textContent = `${result.model || "翻译模型"} · ${result.source_lang || $("#translate-source").value} → ${result.target_lang || $("#translate-target").value}`;
        $("#translate-copy").disabled = false;
        setStatus("#translate-status", "翻译完成。", false, true);
      } catch (error) {
        setStatus("#translate-status", error.message, true);
      } finally {
        setButtonBusy($("#translate-send"), false, "翻译");
      }
    });
    $("#translate-copy").addEventListener("click", () => copyText($("#translate-output").textContent, $("#translate-copy")));
  }

  loadModels();
  if (page === "image") bindImage();
  if (page === "read") bindRead();
  if (page === "voice") bindVoice();
  if (page === "translate") bindTranslate();
})();
