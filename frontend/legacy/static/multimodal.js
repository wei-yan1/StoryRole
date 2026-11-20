const token = localStorage.getItem("access_token");
if (!token) location.href = "/";

const $ = (selector) => document.querySelector(selector);
const state = { visionMode: "ocr", asrText: "", translateText: "" };

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

function bytes(value) {
  const number = Number(value || 0);
  if (!number) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(number) / Math.log(1024)), 3);
  return `${(number / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

async function api(path, options = {}) {
  const currentToken = localStorage.getItem("access_token");
  if (!currentToken) {
    location.href = "/";
    return new Promise(() => {});
  }
  const response = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${currentToken}`,
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    location.href = "/";
    return new Promise(() => {});
  }
  if (!response.ok) throw Error(data.detail || `请求失败 (${response.status})`);
  return data;
}

async function copyText(text, button) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
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
    setTimeout(() => { button.textContent = original; }, 1400);
  }
}

function readFile(input, callback) {
  const file = input.files?.[0];
  if (!file) return null;
  callback(file);
  return file;
}

/* ---------------- model ribbon ---------------- */

async function loadModels() {
  const labels = {
    image: "出图",
    omni: "读图",
    ocr: "OCR",
    asr: "转写",
    tts: "合成",
    translate: "翻译",
  };
  try {
    const data = await api("/api/v1/media/models");
    const chips = Object.entries(labels).map(([role, label]) => {
      const model = data.models?.[role] || "-";
      const verified = data.verified?.[role] !== false;
      return `<span class="model-chip" title="${verified ? "已实测" : "未实测"}">${label} <strong>${escapeHtml(model)}</strong></span>`;
    }).join("");
    $("#model-chips").innerHTML = chips;
    setStatus("#model-status", "接口在线", false, true);
  } catch (error) {
    setStatus("#model-status", error.message, true);
  }
}

/* ---------------- image generation ---------------- */

$("#image-generate").addEventListener("click", async () => {
  const prompt = $("#image-prompt").value.trim();
  if (!prompt) return setStatus("#image-status", "先写一句画面描述。", true);
  setButtonBusy($("#image-generate"), true, "生成中…");
  setStatus("#image-status", "正在调用图片模型，通常需要十几秒…");
  $("#image-result").classList.add("hidden");
  try {
    const result = await api("/api/v1/media/images/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, size: $("#image-size").value }),
    });
    const preview = $("#image-preview");
    preview.src = result.url;
    $("#image-download").href = result.url;
    $("#image-meta").textContent = `${result.model} · ${result.size} · ${bytes(result.bytes)}`;
    $("#image-result").classList.remove("hidden");
    setStatus("#image-status", "图片已生成，保存在项目媒体目录。", false, true);
  } catch (error) {
    setStatus("#image-status", error.message, true);
  } finally {
    setButtonBusy($("#image-generate"), false, "生成图片");
  }
});

/* ---------------- OCR / image describe ---------------- */

document.querySelectorAll("[data-vision-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.visionMode = button.dataset.visionMode;
    document.querySelectorAll("[data-vision-mode]").forEach((item) => {
      item.classList.toggle("is-current", item === button);
    });
    const label = state.visionMode === "ocr" ? "开始识别" : "描述图片";
    $("#vision-submit span").textContent = label;
    setStatus("#vision-status", "");
    $("#vision-result").classList.add("hidden");
  });
});

$("#vision-file").addEventListener("change", () => {
  readFile($("#vision-file"), (file) => {
    $("#vision-file-label").textContent = `${file.name} · ${bytes(file.size)}`;
    const preview = $("#vision-preview");
    const image = $("#vision-preview-img");
    if (image.dataset.url) URL.revokeObjectURL(image.dataset.url);
    const url = URL.createObjectURL(file);
    image.dataset.url = url;
    image.src = url;
    preview.classList.remove("hidden");
  });
});

$("#vision-submit").addEventListener("click", async () => {
  const file = $("#vision-file").files?.[0];
  if (!file) return setStatus("#vision-status", "先选择一张图片。", true);
  const form = new FormData();
  form.append("file", file);
  const prompt = $("#vision-prompt").value.trim();
  if (prompt) form.append("prompt", prompt);
  const endpoint = state.visionMode === "ocr" ? "/api/v1/media/ocr" : "/api/v1/media/images/describe";
  setButtonBusy($("#vision-submit"), true, "识别中…");
  setStatus("#vision-status", state.visionMode === "ocr" ? "正在提取图片文字…" : "正在理解画面…");
  $("#vision-result").classList.add("hidden");
  try {
    const result = await api(endpoint, { method: "POST", body: form });
    $("#vision-text").textContent = result.text;
    $("#vision-meta").textContent = `${result.model} · ${state.visionMode === "ocr" ? "OCR" : "图片描述"}`;
    $("#vision-copy").disabled = false;
    $("#vision-result").classList.remove("hidden");
    setStatus("#vision-status", "识别完成。", false, true);
  } catch (error) {
    setStatus("#vision-status", error.message, true);
  } finally {
    setButtonBusy($("#vision-submit"), false, state.visionMode === "ocr" ? "开始识别" : "描述图片");
  }
});

$("#vision-copy").addEventListener("click", () => {
  copyText($("#vision-text").textContent, $("#vision-copy"));
});

/* ---------------- TTS ---------------- */

$("#tts-send").addEventListener("click", async () => {
  const text = $("#tts-text").value.trim();
  if (!text) return setStatus("#tts-status", "先写要朗读的文本。", true);
  setButtonBusy($("#tts-send"), true, "合成中…");
  setStatus("#tts-status", "正在生成语音…");
  $("#tts-result").classList.add("hidden");
  try {
    const result = await api("/api/v1/media/audio/speech", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: $("#tts-voice").value }),
    });
    const audio = $("#tts-audio");
    audio.src = result.url;
    audio.load();
    $("#tts-download").href = result.url;
    $("#tts-meta").textContent = `${result.model} · ${result.voice} · ${bytes(result.bytes)}`;
    $("#tts-result").classList.remove("hidden");
    setStatus("#tts-status", "语音已生成，点播放试听。", false, true);
  } catch (error) {
    setStatus("#tts-status", error.message, true);
  } finally {
    setButtonBusy($("#tts-send"), false, "合成语音");
  }
});

/* ---------------- ASR ---------------- */

$("#asr-file").addEventListener("change", () => {
  readFile($("#asr-file"), (file) => {
    $("#asr-file-label").textContent = `${file.name} · ${bytes(file.size)}`;
    setStatus("#asr-status", "");
  });
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
    const result = await api("/api/v1/media/audio/transcribe", { method: "POST", body: form });
    state.asrText = result.text;
    $("#asr-text").textContent = result.text;
    $("#asr-meta").textContent = `${result.model} · ${result.format || "audio"}`;
    $("#asr-result").classList.remove("hidden");
    setStatus("#asr-status", "转写完成。", false, true);
  } catch (error) {
    setStatus("#asr-status", error.message, true);
  } finally {
    setButtonBusy($("#asr-send"), false, "转写音频");
  }
});

$("#asr-to-translate").addEventListener("click", () => {
  if (!state.asrText) return;
  $("#translate-text").value = state.asrText;
  $("#translate-text").focus();
  setStatus("#translate-status", "已把转写结果填入原文。", false, true);
});

/* ---------------- translation ---------------- */

$("#translate-send").addEventListener("click", async () => {
  const text = $("#translate-text").value.trim();
  if (!text) return setStatus("#translate-status", "先写要翻译的文本。", true);
  setButtonBusy($("#translate-send"), true, "翻译中…");
  setStatus("#translate-status", "正在翻译…");
  try {
    const result = await api("/api/v1/media/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        source_lang: $("#translate-source").value,
        target_lang: $("#translate-target").value,
      }),
    });
    state.translateText = result.text;
    const output = $("#translate-output");
    output.textContent = result.text;
    output.classList.remove("is-empty");
    $("#translate-meta").textContent = `${result.model} · ${result.source_lang} → ${result.target_lang}`;
    $("#translate-copy").disabled = false;
    setStatus("#translate-status", "翻译完成。", false, true);
  } catch (error) {
    setStatus("#translate-status", error.message, true);
  } finally {
    setButtonBusy($("#translate-send"), false, "翻译");
  }
});

$("#translate-copy").addEventListener("click", () => {
  copyText(state.translateText, $("#translate-copy"));
});

/* ---------------- shell ---------------- */

$("#logout").addEventListener("click", () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("current_user");
  location.href = "/";
});

loadModels();
