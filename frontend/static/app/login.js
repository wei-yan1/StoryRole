(() => {
  if (App.isLoggedIn()) {
    location.replace(App.nextUrl());
    return;
  }
  const state = { mode: "login", busy: false };
  const $ = App.qs;
  const form = $("#auth-form");
  const username = $("#auth-username");
  const password = $("#auth-password");
  const errorNode = $("#auth-error");
  const submit = $("#auth-submit");

  function setMode(mode) {
    state.mode = mode;
    App.qsa("[data-auth-tab]").forEach(button => button.classList.toggle("is-current", button.dataset.authTab === mode));
    $("#auth-title").textContent = mode === "login" ? "欢迎回来" : "创建你的空间";
    $("#auth-lead").textContent = mode === "login" ? "登录后继续你的对话。" : "一个账号，保存所有角色与对话。";
    submit.textContent = mode === "login" ? "登录" : "创建账号";
    password.autocomplete = mode === "login" ? "current-password" : "new-password";
    password.placeholder = mode === "login" ? "输入密码" : "至少 8 位密码";
    errorNode.textContent = "";
  }

  App.qsa("[data-auth-tab]").forEach(button => {
    button.addEventListener("click", () => setMode(button.dataset.authTab));
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (state.busy) return;
    const name = username.value.trim();
    const secret = password.value;
    if (name.length < 2) { errorNode.textContent = "账号至少需要 2 个字符。"; return; }
    if (secret.length < 8) { errorNode.textContent = "密码至少需要 8 个字符。"; return; }
    state.busy = true;
    submit.disabled = true;
    submit.textContent = state.mode === "login" ? "正在登录…" : "正在创建…";
    errorNode.textContent = "";
    try {
      const result = await App.api(`/api/app/auth/${state.mode}`, {
        method: "POST",
        json: { username: name, password: secret },
      });
      localStorage.setItem("access_token", result.access_token);
      App.saveUser(result.user);
      location.href = App.nextUrl();
    } catch (error) {
      errorNode.textContent = error.message || "登录失败，请重试。";
      state.busy = false;
      submit.disabled = false;
      submit.textContent = state.mode === "login" ? "登录" : "创建账号";
    }
  });

  setMode("login");
})();