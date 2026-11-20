(() => {
  if (!App.requireAuth()) return;
  const $ = App.qs;
  function setStatus(text, error = false) {
    const node = $("#settings-status");
    node.textContent = text || "";
    node.className = error ? "error-text" : "success-text";
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
    try {
      const settings = await App.api("/api/app/settings");
      const values = settings.values || {};
      $("#models-chat").value = values["models.chat"] || "deepseek-v4.1-flash-1017";
      $("#models-router").value = values["models.router"] || "deepseek-v4.1-flash-1017";
      $("#models-rerank").textContent = values["models.rerank"] || "qwen3.7-text-rerank";
      $("#runtime-guard").checked = values["runtime.guard_enabled"] !== false;
      $("#keys-dashscope").value = values["keys.dashscope"] && values["keys.dashscope"] !== "••••••••" ? "" : "••••••••";
      $("#keys-tavily").value = values["keys.tavily"] && values["keys.tavily"] !== "••••••••" ? "" : "••••••••";
      $("#decision-backend").textContent = values["runtime.decision_backend"] || "laya";
      $("#models-chat").dataset.current = values["models.chat"] || "";
    } catch (error) {
      setStatus(error.message || "设置读取失败", true);
    }
    $("#save-settings").addEventListener("click", async () => {
      const button = $("#save-settings");
      button.disabled = true;
      button.textContent = "保存中…";
      const values = { "runtime.guard_enabled": $("#runtime-guard").checked };
      const dashscope = $("#keys-dashscope").value.trim();
      const tavily = $("#keys-tavily").value.trim();
      if (dashscope && dashscope !== "••••••••") values["keys.dashscope"] = dashscope;
      if (tavily && tavily !== "••••••••") values["keys.tavily"] = tavily;
      try {
        await App.api("/api/app/settings", { method: "PUT", json: { values } });
        setStatus("设置已保存。");
        App.toast("设置已保存。", "success");
      } catch (error) {
        setStatus(error.message || "保存失败", true);
        App.toast(error.message || "保存失败", "error");
      } finally {
        button.disabled = false;
        button.textContent = "保存设置";
      }
    });
  }
  init();
})();