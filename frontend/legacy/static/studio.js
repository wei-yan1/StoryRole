(() => {
  const token = localStorage.getItem("access_token");
  if (!token) {
    location.replace("/");
    return;
  }

  const page = document.body.dataset.page || "home";
  const navItems = [
    { group: "工作区", label: "总览", href: "/storyrole", match: ["home"], icon: "compass" },
    { group: "工作区", label: "小说档案", href: "/novels", match: ["novels"], icon: "book" },
    { group: "工作区", label: "角色档案", href: "/characters", match: ["characters"], icon: "person" },
    { group: "工作区", label: "时期画像", href: "/periods", match: ["periods"], icon: "timeline" },
    { group: "工作区", label: "角色对话", href: "/chat", match: ["chat"], icon: "message" },
    { group: "工具", label: "多模态", href: "/media", match: ["media", "media-image", "media-read", "media-voice", "media-translate"], icon: "aperture" },
    { group: "工具", label: "调用监控", href: "/models", match: ["models"], icon: "pulse" },
    { group: "工具", label: "设置", href: "/settings", match: ["settings"], icon: "sliders" }
  ];
  const icons = {
    compass: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="8.5"/><path d="m15.7 8.3-2.2 5.2-5.2 2.2 2.2-5.2 5.2-2.2Z"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4.5 5.5h6a3 3 0 0 1 3 3v10a2 2 0 0 0-2-2h-7v-11Z"/><path d="M19.5 5.5h-3a3 3 0 0 0-3 3v10a2 2 0 0 1 2-2h4v-11Z"/></svg>',
    person: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="8" r="3.2"/><path d="M5.5 19c.7-3.1 3.1-5 6.5-5s5.8 1.9 6.5 5"/></svg>',
    timeline: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 4v16M5 8h5M5 14h5M5 20h5"/><circle cx="10" cy="8" r="1.4"/><circle cx="10" cy="14" r="1.4"/><circle cx="10" cy="20" r="1.4"/><path d="M14 8h5M14 14h4M14 20h5"/></svg>',
    message: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4.5 5.5h15v10h-8l-4 3v-3h-3v-10Z"/><path d="M8 9h8M8 12h5"/></svg>',
    aperture: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v8.5M20.5 12h-8.5M12 20.5v-8.5M3.5 12h8.5M5.9 5.9l6 6M18.1 5.9l-6 6M18.1 18.1l-6-6M5.9 18.1l6-6"/></svg>',
    pulse: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 12h4l2-5 4 10 2-5h6"/><path d="M4 19h16"/></svg>',
    sliders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 7h7M15 7h5M4 12h3M11 12h9M4 17h10M18 17h2"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="16" cy="17" r="2"/></svg>'
  };
  const contextKey = "storyrole_context";
  const legacyNovelKey = "storyrole_last_import";
  let context = readContext();

  function readContext() {
    try {
      const parsed = JSON.parse(localStorage.getItem(contextKey) || "{}");
      if (parsed && typeof parsed === "object") return parsed;
    } catch (_) {}
    const legacy = localStorage.getItem(legacyNovelKey);
    return legacy ? { novelId: legacy, novelName: "" } : {};
  }

  function getContext() {
    return { ...context };
  }

  function saveContext(patch = {}) {
    const next = { ...context };
    if (Object.prototype.hasOwnProperty.call(patch, "novelId") && String(patch.novelId || "") !== String(next.novelId || "")) {
      next.characterId = null;
      next.characterName = "";
      next.periodId = null;
      next.periodName = "";
    }
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === undefined || value === "") next[key] = null;
      else next[key] = value;
    }
    if (next.novelId) {
      localStorage.setItem(legacyNovelKey, String(next.novelId));
    } else {
      localStorage.removeItem(legacyNovelKey);
    }
    context = next;
    localStorage.setItem(contextKey, JSON.stringify(next));
    renderRail();
    document.dispatchEvent(new CustomEvent("studio:contextchange", { detail: getContext() }));
    return getContext();
  }

  function clearContext() {
    context = {};
    localStorage.removeItem(contextKey);
    localStorage.removeItem(legacyNovelKey);
    renderRail();
    document.dispatchEvent(new CustomEvent("studio:contextchange", { detail: {} }));
  }

  function currentUser() {
    try {
      const user = JSON.parse(localStorage.getItem("current_user") || "{}");
      if (user && typeof user === "object") return user;
    } catch (_) {}
    return {};
  }

  function userName() {
    const user = currentUser();
    return user.display_name || user.nickname || user.username || user.email || "档案管理员";
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    location.replace("/");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "0";
    return number.toLocaleString("zh-CN");
  }

  function formatDuration(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    const ms = Number(value);
    if (ms < 1000) return `${Math.round(ms)} ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
    return `${(ms / 60000).toFixed(1)} min`;
  }

  function formatBytes(value) {
    const bytes = Number(value) || 0;
    if (bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  function formatDate(value, withTime = false) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    const options = withTime
      ? { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }
      : { year: "numeric", month: "numeric", day: "numeric" };
    return new Intl.DateTimeFormat("zh-CN", options).format(date);
  }

  function queryParams() {
    return new URLSearchParams(location.search);
  }

  function hydrateContextFromQuery() {
    const params = queryParams();
    const patch = {};
    if (params.has("novel")) patch.novelId = params.get("novel");
    if (params.has("character")) patch.characterId = params.get("character");
    if (params.has("period")) patch.periodId = params.get("period");
    if (Object.keys(patch).length) saveContext(patch);
  }

  function api(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    headers.Authorization = `Bearer ${token}`;
    const fetchOptions = { ...options, headers };
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      fetchOptions.body = JSON.stringify(options.json);
      delete fetchOptions.json;
    }
    return fetch(url, fetchOptions).then(async response => {
      if (response.status === 401) {
        logout();
        throw new Error("登录状态已过期，请重新登录。");
      }
      if (response.status === 204) return null;
      const type = response.headers.get("content-type") || "";
      const data = type.includes("application/json")
        ? await response.json().catch(() => null)
        : await response.text().catch(() => "");
      if (!response.ok) {
        const detail = data && typeof data === "object" ? (data.detail || data.message) : "";
        throw new Error(typeof detail === "string" ? detail : "请求失败");
      }
      return data;
    });
  }

  function toast(message, type = "info", timeout = 3200) {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      document.body.append(stack);
    }
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.textContent = message;
    stack.append(node);
    window.setTimeout(() => {
      node.style.opacity = "0";
      node.style.transform = "translateY(5px)";
      window.setTimeout(() => node.remove(), 220);
    }, timeout);
  }

  function modalShell(title, description, bodyHtml, footerHtml) {
    const modal = document.createElement("div");
    modal.className = "modal";
    modal.innerHTML = `
      <div class="modal-backdrop" data-close></div>
      <div class="modal-card" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="modal-head">
          <div><h2>${escapeHtml(title)}</h2>${description ? `<p>${escapeHtml(description)}</p>` : ""}</div>
          <button class="modal-close" type="button" data-close aria-label="关闭">×</button>
        </div>
        <div class="modal-body">${bodyHtml}${footerHtml || ""}</div>
      </div>`;
    document.body.append(modal);
    const close = () => modal.remove();
    modal.querySelectorAll("[data-close]").forEach(node => node.addEventListener("click", close));
    document.addEventListener("keydown", function onKey(event) {
      if (event.key === "Escape") { close(); document.removeEventListener("keydown", onKey); }
    });
    modal.querySelectorAll("input, textarea, button").forEach(node => {
      if (node.dataset.autofocus !== undefined) node.focus();
    });
    return { modal, close };
  }

  function confirmDialog(options = {}) {
    return new Promise(resolve => {
      const { modal, close } = modalShell(
        options.title || "确认操作",
        options.description || "",
        `<p class="inline-note">${escapeHtml(options.message || "这个操作会立即生效。")}</p>`,
        `<div class="action-row" style="justify-content:flex-end;margin-top:22px">
          <button class="btn btn-ghost" type="button" data-cancel>取消</button>
          <button class="btn ${options.danger ? "btn-danger" : "btn-primary"}" type="button" data-confirm>${escapeHtml(options.confirmText || "确认")}</button>
        </div>`
      );
      const finish = value => { close(); resolve(value); };
      modal.querySelector("[data-cancel]").addEventListener("click", () => finish(false));
      modal.querySelector("[data-confirm]").addEventListener("click", () => finish(true));
    });
  }

  function promptDialog(options = {}) {
    return new Promise(resolve => {
      const { modal, close } = modalShell(
        options.title || "编辑",
        options.description || "",
        `<label class="field"><span>${escapeHtml(options.label || "内容")}</span><input class="input" data-input value="${escapeHtml(options.value || "")}" autocomplete="off" data-autofocus></label>`,
        `<div class="action-row" style="justify-content:flex-end;margin-top:22px">
          <button class="btn btn-ghost" type="button" data-cancel>取消</button>
          <button class="btn btn-primary" type="button" data-confirm>${escapeHtml(options.confirmText || "保存")}</button>
        </div>`
      );
      const input = modal.querySelector("[data-input]");
      const finish = value => { close(); resolve(value); };
      modal.querySelector("[data-cancel]").addEventListener("click", () => finish(null));
      modal.querySelector("[data-confirm]").addEventListener("click", () => finish(input.value.trim()));
      input.addEventListener("keydown", event => {
        if (event.key === "Enter") { event.preventDefault(); finish(input.value.trim()); }
      });
    });
  }

  function renderRail() {
    const rail = document.getElementById("rail");
    if (!rail) return;
    const user = userName();
    const active = navItems.find(item => item.match.includes(page));
    const novelName = context.novelName || (context.novelId ? `小说 ${context.novelId}` : "尚未选择小说");
    const characterName = context.characterName || (context.characterId ? `角色 ${context.characterId}` : "尚未建立角色");
    const periodName = context.periodName || (context.periodId ? `时期 ${context.periodId}` : "尚未辨认时期");
    const groups = [...new Set(navItems.map(item => item.group))];
    rail.innerHTML = `
      <div class="brand">
        <span class="brand-seal">叙</span>
        <div class="brand-copy"><strong>STORYROLE</strong><small>小说角色档案室</small></div>
      </div>
      <div class="rail-context">
        <span class="rail-label">当前档案 / CURRENT DOSSIER</span>
        <strong title="${escapeHtml(novelName)}">${escapeHtml(novelName)}</strong>
        <div class="context-meta"><span>${escapeHtml(characterName)}</span><span>${escapeHtml(periodName)}</span></div>
        <button class="context-action" type="button" data-switch-context>切换档案 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
      </div>
      <nav class="rail-nav" aria-label="主导航">
        ${groups.map(group => `<div class="nav-group"><div class="nav-group-label">${escapeHtml(group)}</div>${navItems.filter(item => item.group === group).map(item => `
          <a class="nav-link ${active === item ? "active" : ""}" href="${item.href}" ${active === item ? 'aria-current="page"' : ""}>
            ${icons[item.icon] || ""}<span>${escapeHtml(item.label)}</span>
          </a>`).join("")}</div>`).join("")}
      </nav>
      <div class="rail-foot">
        <div class="rail-status"><i></i><span>LOCAL / MaaS ROUTE</span></div>
        <div class="rail-user">
          <span class="user-avatar">${escapeHtml(String(user).slice(0, 1))}</span>
          <span class="user-copy" title="${escapeHtml(user)}">${escapeHtml(user)}</span>
          <button class="rail-logout" type="button" data-logout>退出</button>
        </div>
      </div>`;
    rail.querySelector("[data-logout]").addEventListener("click", logout);
    rail.querySelector("[data-switch-context]").addEventListener("click", () => {
      if (context.novelId) location.href = `/characters?novel=${encodeURIComponent(context.novelId)}`;
      else location.href = "/novels";
    });
  }

  function setup() {
    hydrateContextFromQuery();
    renderRail();
  }

  window.Studio = {
    api,
    toast,
    escapeHtml,
    formatNumber,
    formatDuration,
    formatBytes,
    formatDate,
    queryParams,
    currentUser,
    userName,
    logout,
    getContext,
    saveContext,
    clearContext,
    confirm: confirmDialog,
    prompt: promptDialog,
    icon: name => icons[name] || ""
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
