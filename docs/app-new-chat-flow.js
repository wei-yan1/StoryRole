const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }),
  })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 980 } })).newPage();
  const errors = [];
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });
  await page.goto(`${BASE}/chats/new?character=87&period=103`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.fill("#first-message", "你好，第一次见面，想听听你怎么看自己现在的生活。");
  await page.click("#first-send");
  await page.waitForFunction(() => location.pathname.startsWith("/chats/") && location.pathname !== "/chats/new", null, { timeout: 120000 }).catch(() => {});
  const out = { url: page.url(), errors };
  if (page.url().includes("/chats/")) {
    await page.waitForTimeout(500);
    out.messages = await page.locator(".message").count();
    out.header = await page.locator(".chat-header").innerText().catch(() => "");
    await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "chat-new-result.png"), fullPage: true });
  } else {
    out.error = await page.locator("#new-chat-error").innerText().catch(() => "");
  }
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();