(() => {
  const TOKEN_KEY = "access_token";
  const USER_KEY = "storyrole_user";

  const icons = {
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 8.7 8.7 0 0 1-3.8-.9L3 21l1.9-5.4A8.5 8.5 0 1 1 21 11.5Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/></svg>',
    people: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></svg>',
    tools: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m14.7 6.3 1.9-1.9a4.5 4.5 0 1 1 6.3 6.3l-1.9 1.9"/><path d="m9.3 17.7-1.9 1.9a4.5 4.5 0 1 1-6.3-6.3l1.9-1.9"/><path d="m14 7 7 7"/><path d="m3 10 7 7"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3v18h18"/><path d="m7 15 4-5 3 3 5-7"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1.5-1V3a2 2 0 0 1 4 0v.1A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M19 12H5"/><path d="m11 18-6-6 6-6"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3.4 20.4 21 12 3.4 3.6l.1 6.6L15 12 3.5 13.8l-.1 6.6Z"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z"/><path d="m19 16 .9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9L19 16Z"/></svg>',
    image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>',
    scan: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/><path d="M7 8h4M7 16h7"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 19v3"/><path d="M8 22h8"/></svg>',
    translate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 5h8M8 3v2c0 4-2.5 7-5 8"/><path d="M6 10c0 3 3 6 6 7"/><path d="m14 21 4-10 4 10"/><path d="M15.5 17h5"/></svg>',
    upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    more: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m6 6 12 12M18 6 6 18"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m5 12 4 4L19 6"/></svg>',
  };

  function readUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch (_) { return null; }
  }
  function saveUser(user) {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  }
  function token() { return localStorage.getItem(TOKEN_KEY) || ""; }
  function isLoggedIn() { return Boolean(token()); }
  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    saveUser(null);
    location.href = "/login";
  }
  function requireAuth() {
    if (!isLoggedIn()) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.replace(`/login?next=${next}`);
      return false;
    }
    return true;
  }
  function nextUrl() {
    const next = new URLSearchParams(location.search).get("next");
    if (!next) return "/chats";
    try {
      const decoded = decodeURIComponent(next);
      return decoded.startsWith("/") && !decoded.startsWith("//") ? decoded : "/chats";
    } catch (_) { return "/chats"; }
  }

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (token()) headers.Authorization = `Bearer ${token()}`;
    let body = options.body;
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.json);
    }
    const response = await fetch(path, { method: options.method || "GET", headers, body, signal: options.signal });
    if (response.status === 401) {
      logout();
      throw new Error("登录已过期，请重新登录");
    }
    const text = await response.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (_) { data = text; }
    }
    if (!response.ok) {
      const detail = data && typeof data === "object" ? data.detail : data;
      if (Array.isArray(detail)) throw new Error(detail.map(item => item.msg || JSON.stringify(item)).join("；"));
      throw new Error(detail || `请求失败（${response.status}）`);
    }
    return data;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  }
  function hash(text) {
    let result = 0;
    for (let index = 0; index < String(text).length; index += 1) result = (result * 31 + String(text).charCodeAt(index)) >>> 0;
    return result;
  }
  function avatarStyle(name) {
    const value = hash(name || "?");
    const hue = value % 360;
    const second = (hue + 38 + (value % 40)) % 360;
    return `background: linear-gradient(145deg, hsl(${hue} 45% 42%), hsl(${second} 52% 30%))`;
  }
  function initials(name) {
    const value = String(name || "?").trim();
    if (!value) return "?";
    const parts = value.split(/\s+/).filter(Boolean);
    if (parts.length > 1 && /^[\x00-\x7F]+$/.test(value)) return (parts[0][0] + parts[1][0]).toUpperCase();
    return value.slice(0, 2);
  }
  function avatar(name, size = "", extra = "") {
    return `<span class="avatar ${size} ${extra}" style="${avatarStyle(name)}" aria-hidden="true">${escapeHtml(initials(name))}</span>`;
  }
  function formatNumber(value) {
    return Number(value || 0).toLocaleString("zh-CN");
  }
  function formatBytes(bytes) {
    const n = Number(bytes || 0);
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }
  function formatRelative(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    const diff = Date.now() - date.getTime();
    if (Number.isNaN(diff)) return "";
    if (diff < 60 * 1000) return "刚刚";
    if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`;
    if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)} 小时前`;
    if (diff < 7 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / 86400000)} 天前`;
    return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  }
  function formatDate(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  }
  function formatDateTime(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function formatCost(value) {
    if (value === null || value === undefined) return "—";
    const n = Number(value);
    if (!n) return "¥0.00";
    if (n < 0.01) return `¥${n.toFixed(4)}`;
    return `¥${n.toFixed(2)}`;
  }
  function toast(message, type = "info") {
    let wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      document.body.append(wrap);
    }
    const node = document.createElement("div");
    node.className = `toast${type === "error" ? " is-error" : type === "success" ? " is-success" : ""}`;
    node.textContent = message;
    wrap.append(node);
    window.setTimeout(() => node.remove(), 3600);
  }
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); toast("已复制", "success"); }
    catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      toast("已复制", "success");
    }
  }
  function pageTitle(title) { document.title = `${title} · StoryRole`; }

  const navItems = [
    { key: "chats", href: "/chats", label: "对话", icon: "chat" },
    { key: "characters", href: "/characters", label: "角色", icon: "people" },
    { key: "library", href: "/library", label: "资料", icon: "library" },
    { key: "tools", href: "/tools", label: "工具", icon: "tools" },
    { key: "usage", href: "/usage", label: "用量", icon: "chart" },
    { key: "settings", href: "/settings", label: "设置", icon: "settings" },
  ];

  function mountSidebar(active) {
    const user = readUser() || {};
    const mount = document.getElementById("sidebar");
    if (!mount) return;
    const name = user.display_name || user.username || "我的账号";
    mount.innerHTML = `
      <a class="brand" href="/chats" aria-label="StoryRole 首页">
        <span class="brand-mark">${icons.spark}</span>
        <span><span class="brand-name">StoryRole</span><span class="brand-sub">character chat</span></span>
      </a>
      <nav class="side-nav" aria-label="主导航">
        ${navItems.map(item => `<a href="${item.href}" class="${item.key === active ? "is-current" : ""}">${icons[item.icon]}<span>${item.label}</span></a>`).join("")}
      </nav>
      <div class="side-bottom">
        <a class="side-account" href="/settings" title="账户设置">
          ${avatar(name, "avatar-sm")}
          <span class="side-account-copy">
            <span class="side-account-name">${escapeHtml(name)}</span>
            <span class="side-account-meta">@${escapeHtml(user.username || "account")}</span>
          </span>
        </a>
        <button class="side-signout" type="button" title="退出登录" aria-label="退出登录" id="app-signout">${icons.logout}</button>
      </div>
    `;
    document.getElementById("app-signout")?.addEventListener("click", logout);
  }

  async function syncUser() {
    const cached = readUser();
    if (cached) return cached;
    try {
      const user = await api("/api/app/auth/me");
      saveUser(user);
      return user;
    } catch (_) { return null; }
  }

  function debounce(fn, wait = 250) {
    let timer = 0;
    return (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn(...args), wait);
    };
  }

  function qs(selector, root = document) { return root.querySelector(selector); }
  function qsa(selector, root = document) { return Array.from(root.querySelectorAll(selector)); }

  async function streamChat({ characterId, novelId, message, periodId, threadName, mode, webMode, onProgress, onToken, onReset }) {
    const headers = {
      Authorization: `Bearer ${token()}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    const response = await fetch(`/api/app/characters/${encodeURIComponent(characterId)}/messages`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        period_id: Number(periodId),
        thread_name: threadName || "主对话",
        mode: mode || "quick",
        web_mode: webMode === "on" ? "on" : "off",
        debug: false,
        retry: false,
      }),
    });
    if (response.status === 401) { logout(); throw new Error("登录已过期"); }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg || "").join("；") : data.detail;
      throw new Error(detail || "对话请求失败");
    }
    if (!response.body) throw new Error("当前浏览器不支持流式响应");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let complete = null;
    let streamError = null;
    const handle = block => {
      if (!block.trim()) return;
      const eventName = block.match(/^event:\s*(.+)$/m)?.[1] || "message";
      const data = block.split(/\r?\n/).filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n");
      let payload = {};
      try { payload = JSON.parse(data); } catch (_) { return; }
      if (eventName === "progress") onProgress?.(payload);
      else if (eventName === "heartbeat") return;
      else if (eventName === "reset") onReset?.();
      else if (eventName === "token") onToken?.(payload.text || "");
      else if (eventName === "complete") complete = payload;
      else if (eventName === "error") streamError = new Error(payload.message || "对话失败");
    };
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || "";
      blocks.forEach(handle);
      if (done) break;
    }
    if (buffer.trim()) handle(buffer);
    if (streamError) throw streamError;
    if (!complete) throw new Error("流式响应提前结束");
    return complete;
  }

  window.App = {
    icons, token, isLoggedIn, logout, requireAuth, nextUrl, readUser, saveUser, syncUser,
    api, escapeHtml, avatar, avatarStyle, initials, formatNumber, formatBytes, formatRelative,
    formatDate, formatDateTime, formatCost, toast, copyText, pageTitle, mountSidebar,
    debounce, qs, qsa, streamChat,
  };
})();