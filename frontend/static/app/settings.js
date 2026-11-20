(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  const ROLE_GROUPS = [
    { title: "对话与检索", roles: ["chat", "reasoning", "guard", "rerank", "embedding"] },
    { title: "多模态工具", roles: ["image", "ocr", "omni", "asr", "tts", "translate"] },
  ];
  const ROLE_LABELS = {
    chat: "角色对话",
    reasoning: "深度推理",
    guard: "一致性检查",
    rerank: "场景重排",
    embedding: "检索向量",
    image: "图片生成",
    ocr: "文字识别",
    omni: "图片理解",
    asr: "语音转写",
    tts: "语音合成",
    translate: "翻译",
  };

  function setStatus(text, type = "") {
    const node = $("#settings-status");
    node.textContent = text || "";
    node.className = type === "error" ? "error-text" : type === "success" ? "success-text" : "note-line";
  }

  function setTestResult(text, type = "") {
    const node = $("#model-test-result");
    node.textContent = text || "";
    node.className = `model-test-result ${type === "error" ? "is-error" : type === "success" ? "is-success" : ""}`;
  }

  function renderRuntimeModels(models) {
    const root = $("#runtime-models");
    if (!models) { root.innerHTML = `<p class="field-hint">当前账号没有可读取的运行模型。</p>`; return; }
    root.innerHTML = ROLE_GROUPS.map(group => `
      <div class="model-group">
        <div class="model-group-title">${group.title}</div>
        ${group.roles.filter(role => models[role]).map(role => {
          const item = models[role];
          return `<div class="model-row">
            <span class="model-role">${ROLE_LABELS[role] || role}</span>
            <span class="model-id">${App.escapeHtml(item.model)}</span>
            <span class="model-state ${item.verified ? "is-verified" : ""}">${item.verified ? "已验证" : "未验证"}</span>
          </div>`;
        }).join("")}
      </div>`).join("");
  }

  function fillCustom(values) {
    $("#model-label").value = values["models.custom.label"] || "";
    $("#model-type").value = values["models.custom.type"] || "chat";
    $("#model-source").value = values["models.custom.source"] || "openai-compatible";
    $("#model-base-url").value = values["models.custom.base_url"] || "";
    $("#model-name").value = values["models.custom.model"] || "";
    if (values["models.custom.key"] === "••••••••") {
      $("#model-api-key").value = "";
      $("#model-api-key").placeholder = "已保存，测试时请重新输入";
    }
    if (values["models.custom.active"]) {
      setTestResult("已保存一条自定义连接。", "success");
    }
  }

  function modelPayload() {
    return {
      type: $("#model-type").value,
      source: $("#model-source").value,
      base_url: $("#model-base-url").value.trim(),
      model: $("#model-name").value.trim(),
      api_key: $("#model-api-key").value.trim(),
    };
  }

  async function init() {
    const user = await App.syncUser();
    App.mountSidebar("settings");
    App.pageTitle("设置");
    const name = user?.display_name || user?.username || "我的账号";
    $("#account-avatar").innerHTML = App.avatar(name, "avatar-sm");
    $("#account-name").textContent = name;
    $("#account-meta").textContent = `@${user?.username || "account"}`;
    $("#logout-button").addEventListener("click", App.logout);

    let settings = { values: {} };
    try {
      settings = await App.api("/api/app/settings");
      const values = settings.values || {};
      const secretState = settings.secret_state || {};
      renderRuntimeModels(settings.runtime_models);
      fillCustom(values);
      $("#runtime-guard").checked = values["runtime.guard_enabled"] !== false;
      $("#decision-backend").textContent = values["runtime.decision_backend"] || "laya";
      $("#keys-dashscope").value = "";
      $("#keys-dashscope").placeholder = values["keys.dashscope"]
        ? "已保存（不显示）"
        : secretState["keys.dashscope"] ? "已由服务端环境变量提供（不显示）" : "未设置";
      $("#keys-tavily").value = "";
      $("#keys-tavily").placeholder = values["keys.tavily"]
        ? "已保存（不显示）"
        : secretState["keys.tavily"] ? "已由服务端环境变量提供（不显示）" : "未设置";
    } catch (error) {
      setStatus(error.message || "设置读取失败", "error");
    }

    $("#test-model").addEventListener("click", async () => {
      const payload = modelPayload();
      if (!payload.api_key && $("#model-source").value !== "ollama") {
        setTestResult("测试已保存的连接时，请重新输入 API Key。", "error");
        return;
      }
      const button = $("#test-model");
      button.disabled = true;
      button.textContent = "连接中…";
      setTestResult("正在请求模型接口…");
      try {
        const result = await App.api("/api/app/models/test", { method: "POST", json: payload });
        setTestResult(result.message, result.ok ? "success" : "error");
        if (result.ok) App.toast("模型连接可用。", "success");
      } catch (error) {
        setTestResult(error.message || "连接失败", "error");
      } finally {
        button.disabled = false;
        button.textContent = "测试连接";
      }
    });

    $("#save-model").addEventListener("click", async () => {
      const payload = modelPayload();
      if (!payload.base_url || !payload.model) {
        setTestResult("先填写接口地址和模型 ID。", "error");
        return;
      }
      const button = $("#save-model");
      button.disabled = true;
      button.textContent = "保存中…";
      try {
        const values = {
          "models.custom.label": $("#model-label").value.trim(),
          "models.custom.type": payload.type,
          "models.custom.source": payload.source,
          "models.custom.base_url": payload.base_url,
          "models.custom.model": payload.model,
          "models.custom.active": true,
        };
        if (payload.api_key) values["models.custom.key"] = payload.api_key;
        await App.api("/api/app/settings", { method: "PUT", json: { values } });
        setTestResult("连接已保存到当前账号。", "success");
        App.toast("模型连接已保存。", "success");
      } catch (error) {
        setTestResult(error.message || "保存失败", "error");
      } finally {
        button.disabled = false;
        button.textContent = "保存连接";
      }
    });

    $("#save-settings").addEventListener("click", async () => {
      const button = $("#save-settings");
      button.disabled = true;
      button.textContent = "保存中…";
      const values = { "runtime.guard_enabled": $("#runtime-guard").checked };
      const dashscope = $("#keys-dashscope").value.trim();
      const tavily = $("#keys-tavily").value.trim();
      if (dashscope) values["keys.dashscope"] = dashscope;
      if (tavily) values["keys.tavily"] = tavily;
      try {
        await App.api("/api/app/settings", { method: "PUT", json: { values } });
        setStatus("设置已保存。", "success");
        App.toast("设置已保存。", "success");
      } catch (error) {
        setStatus(error.message || "保存失败", "error");
      } finally {
        button.disabled = false;
        button.textContent = "保存设置";
      }
    });
  }

  init();
})();
