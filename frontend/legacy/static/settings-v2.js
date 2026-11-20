(() => {
  const $ = selector => document.querySelector(selector);
  const labels = { embedding: "向量与索引", indexing: "索引策略", models: "模型", runtime: "运行策略", keys: "服务密钥" };
  const notes = {
    embedding: "导入与检索时使用的向量模型和缓存策略。",
    indexing: "文本切分、索引构建与重建行为。",
    models: "对话、分析、画像与多模态工具使用的模型路由。",
    runtime: "超时、重试与运行环境的行为。",
    keys: "外部服务的访问密钥；已保存的密钥不会回显。"
  };
  let snapshot = null;

  function groupLabel(group) {
    return labels[group] || group;
  }

  async function load() {
    const loading = $("#settings-loading");
    const status = $("#status");
    try {
      status.textContent = "正在读取设置…";
      status.className = "save-status";
      snapshot = await Studio.api("/api/v1/settings");
      loading?.classList.add("hidden");
      render();
      $("#save-settings-top").disabled = false;
      status.textContent = "设置已读取。修改后保存会立即生效。";
    } catch (error) {
      loading?.classList.add("hidden");
      status.textContent = error.message;
      status.className = "save-status error";
    }
  }

  function field(key, definition, value) {
    const wrap = document.createElement("div");
    wrap.className = "settings-field";
    const label = document.createElement("div");
    label.className = "settings-field-label";
    const title = document.createElement("strong");
    title.textContent = definition.label || key;
    const help = document.createElement("small");
    help.textContent = definition.secret ? "已保存的密钥不会显示；留空表示保持不变。" : definition.help || definition.description || "";
    label.append(title, help);
    let control;
    if (definition.type === "select") {
      control = document.createElement("select");
      control.className = "select";
      (definition.options || []).forEach(option => {
        const item = document.createElement("option");
        item.value = option;
        item.textContent = option;
        control.append(item);
      });
      control.value = value ?? "";
    } else if (definition.type === "boolean") {
      const switchWrap = document.createElement("label");
      switchWrap.className = "switch-label";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = key;
      checkbox.checked = Boolean(value);
      const switchFace = document.createElement("span");
      switchFace.className = "switch";
      switchFace.append(checkbox);
      const copy = document.createElement("span");
      copy.textContent = value ? "开启" : "关闭";
      checkbox.addEventListener("change", () => { copy.textContent = checkbox.checked ? "开启" : "关闭"; });
      switchWrap.append(switchFace, copy);
      control = switchWrap;
    } else {
      control = document.createElement("input");
      control.className = "input";
      control.type = definition.type === "secret" ? "password" : definition.type === "number" ? "number" : "text";
      control.value = value ?? "";
      if (definition.type === "number") {
        if (definition.min != null) control.min = definition.min;
        if (definition.max != null) control.max = definition.max;
      }
      if (definition.type === "secret") control.placeholder = "留空保持不变";
    }
    if (definition.type !== "boolean") control.name = key;
    if (definition.type !== "boolean") control.setAttribute("aria-label", definition.label || key);
    wrap.append(label, control);
    return wrap;
  }

  function render() {
    const nav = $("#settings-nav");
    const root = $("#settings-groups");
    if (!snapshot) return;
    const groups = (() => {
      const preferred = ["embedding", "indexing", "models", "runtime", "keys"];
      const available = snapshot.groups || [];
      return preferred.filter(group => available.includes(group)).concat(available.filter(group => !preferred.includes(group)));
    })();
    nav.innerHTML = groups.map((group, index) => `<a href="#settings-${index}" data-group-link="${Studio.escapeHtml(group)}">${Studio.escapeHtml(groupLabel(group))}</a>`).join("");
    root.innerHTML = "";
    groups.forEach((group, index) => {
      const definitions = Object.entries(snapshot.definitions || {}).filter(([, definition]) => definition.group === group);
      if (!definitions.length) return;
      const section = document.createElement("section");
      section.className = "settings-group";
      section.id = `settings-${index}`;
      section.dataset.group = group;
      const head = document.createElement("div");
      head.className = "settings-group-head";
      const h2 = document.createElement("h2");
      h2.textContent = groupLabel(group);
      const p = document.createElement("p");
      p.textContent = notes[group] || "这一组配置会影响工作区的运行行为。";
      head.append(h2, p);
      const fields = document.createElement("div");
      fields.className = "settings-fields";
      definitions.forEach(([key, definition]) => fields.append(field(key, definition, snapshot.values?.[key])));
      section.append(head, fields);
      root.append(section);
    });
    if (!root.children.length) {
      root.innerHTML = `<div class="settings-empty">后端没有返回可编辑的设置项。</div>`;
    }
    nav.querySelectorAll("[data-group-link]").forEach(link => {
      link.addEventListener("click", event => {
        event.preventDefault();
        const group = link.dataset.groupLink;
        const target = [...root.querySelectorAll(".settings-group")].find(section => section.dataset.group === group);
        nav.querySelectorAll("a").forEach(item => item.classList.toggle("active", item === link));
        target?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  async function save(event) {
    event.preventDefault();
    if (!snapshot) return;
    const button = $("#save-settings");
    const topButton = $("#save-settings-top");
    const status = $("#status");
    const values = {};
    for (const element of event.target.querySelectorAll("[name]")) {
      const definition = snapshot.definitions?.[element.name];
      if (!definition) continue;
      if (definition.type === "boolean") values[element.name] = element.type === "checkbox" ? element.checked : element.checked;
      else if (definition.type === "number") values[element.name] = element.value === "" ? null : Number(element.value);
      else values[element.name] = element.value;
    }
    button.disabled = true;
    if (topButton) topButton.disabled = true;
    status.textContent = "正在保存…";
    status.className = "save-status";
    try {
      await Studio.api("/api/v1/settings", { method: "PUT", json: { values } });
      status.textContent = "已保存。新的设置会在下一次请求时生效。";
      status.className = "save-status success";
      Studio.toast("设置已保存。", "success");
    } catch (error) {
      status.textContent = error.message;
      status.className = "save-status error";
    } finally {
      button.disabled = false;
      if (topButton) topButton.disabled = false;
    }
  }

  load();
  $("#settings-form").addEventListener("submit", save);
  $("#reload-settings").addEventListener("click", load);
})();
