const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }) })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript(({ token, user }) => { localStorage.setItem("access_token", token); localStorage.setItem("storyrole_user", JSON.stringify(user)); }, { token: login.access_token, user: login.user });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto(`${BASE}/chats/new?character=80`, { waitUntil: "networkidle" });
  console.log("before", await page.locator("#character-select").inputValue(), await page.locator("#scene-select").inputValue());
  await page.fill("#first-message", "你好，最近怎么样？");
  await page.click("#first-send");
  try {
    await page.waitForURL(/\/chats\/\d+$/, { timeout: 90000 });
    console.log("thread", page.url());
  } catch (_) {
    console.log("no redirect, error:", await page.locator("#new-chat-error").innerText());
  }
  console.log("errors", errors);
  await browser.close();
})();
