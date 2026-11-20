const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3");
const USERNAME = "ui_flow_29166046";
const PASSWORD = "smoke-pass-1234";
const pages = [
  ["/chats", "chats", "对话列表"],
  ["/chats/new", "chat-new", "新对话"],
  ["/characters", "characters", "角色库"],
  ["/characters/81", "character", "角色详情"],
  ["/characters/81/scenes", "scenes", "场景管理"],
  ["/characters/new", "character-new", "新建角色"],
  ["/library", "library", "资料库"],
  ["/tools", "tools", "工具"],
  ["/tools/image", "tool-image", "生成图片"],
  ["/tools/ocr", "tool-ocr", "读图与 OCR"],
  ["/tools/voice", "tool-voice", "语音"],
  ["/tools/translate", "tool-translate", "翻译"],
  ["/usage", "usage", "用量"],
  ["/settings", "settings", "设置"],
];
const errors = [];
const report = [];
fs.mkdirSync(SHOT_DIR, { recursive: true });

async function api(pathname, options = {}) {
  const response = await fetch(`${BASE}${pathname}`, {
    method: options.method || "GET",
    headers: options.headers || {},
    body: options.body,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`${pathname}: ${JSON.stringify(data)}`);
  return data;
}

async function main() {
  const login = await api("/api/app/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  const conversations = await api("/api/app/conversations", {
    headers: { Authorization: `Bearer ${login.access_token}` },
  });
  if (conversations.items?.[0]?.id) {
    pages.push([`/chats/${conversations.items[0].id}`, "chat-thread", "对话详情"]);
  }
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on("console", message => {
    if (message.type() === "error") errors.push(`[console] ${page.url()} :: ${message.text()}`);
  });
  page.on("pageerror", error => errors.push(`[pageerror] ${page.url()} :: ${error.message}`));

  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });

  for (const [url, key, label] of pages) {
    const response = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(420);
    const status = response ? response.status() : 0;
    const text = await page.locator("body").innerText().catch(() => "");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    const shot = path.join(SHOT_DIR, `${key}-1440.png`);
    await page.screenshot({ path: shot, fullPage: true });
    report.push({ page: url, label, status, chars: text.length, overflow, shot, sample: text.slice(0, 80).replace(/\s+/g, " ") });
  }

  const invalid = await page.goto(`${BASE}/chats/999999`, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  const invalidText = await page.locator("body").innerText();
  report.push({ page: "/chats/999999", label: "无效对话兜底", status: invalid ? invalid.status() : 0, fallback: invalidText.includes("打不开") || invalidText.includes("不存在"), shot: path.join(SHOT_DIR, "chat-invalid.png") });
  await page.screenshot({ path: path.join(SHOT_DIR, "chat-invalid.png"), fullPage: true });

  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
    for (const [url, key] of pages) {
      const response = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(220);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
      const shot = path.join(SHOT_DIR, `${key}-${width}.png`);
      await page.screenshot({ path: shot, fullPage: true });
      report.push({ page: `${url} @${width}`, status: response ? response.status() : 0, overflow, shot });
    }
  }

  const loginContext = await browser.newContext({ viewport: { width: 1440, height: 980 } });
  const loginPage = await loginContext.newPage();
  loginPage.on("console", message => { if (message.type() === "error") errors.push(`[login console] ${message.text()}`); });
  loginPage.on("pageerror", error => errors.push(`[login pageerror] ${error.message}`));
  await loginPage.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await loginPage.waitForTimeout(250);
  await loginPage.screenshot({ path: path.join(SHOT_DIR, "login-1440.png"), fullPage: true });
  report.push({ page: "/login", label: "登录页", status: 200, overflow: await loginPage.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2) });
  await loginContext.close();

  fs.writeFileSync(path.join("D:", "AgentCode", "two", "docs", "app-ui-report.json"), JSON.stringify({ username: USERNAME, report, errors }, null, 2), "utf8");
  await browser.close();
  console.log(JSON.stringify({ pages: pages.length, checks: report.length, errors }, null, 2));
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});