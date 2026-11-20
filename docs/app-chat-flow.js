const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3");
const USERNAME = "ui_flow_29166046";
const PASSWORD = "smoke-pass-1234";

(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  })).json();
  const conversations = await (await fetch(`${BASE}/api/app/conversations`, {
    headers: { Authorization: `Bearer ${login.access_token}` },
  })).json();
  const thread = conversations.items?.[0];
  if (!thread) throw new Error("没有可用的测试会话");
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 980 } })).newPage();
  const errors = [];
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });
  await page.goto(`${BASE}/chats/${thread.id}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const before = await page.locator(".message").count();
  await page.fill("#chat-input", "如果重新选择一次，你会怎么做？");
  await page.click("#send-button");
  await page.waitForFunction(() => {
    const status = document.querySelector("#chat-error");
    return status && (status.textContent.includes("已就绪") || status.textContent.includes("失败"));
  }, { timeout: 120000 });
  await page.waitForTimeout(800);
  const after = await page.locator(".message").count();
  const status = await page.locator("#chat-error").innerText().catch(() => "");
  const detail = await (await fetch(`${BASE}/api/app/conversations/${thread.id}`, {
    headers: { Authorization: `Bearer ${login.access_token}` },
  })).json();
  await page.screenshot({ path: path.join(SHOT_DIR, "chat-thread-after-send.png"), fullPage: true });
  console.log(JSON.stringify({ thread: thread.id, before, after, apiMessages: detail.messages?.length, status, errors }, null, 2));
  await browser.close();
})();