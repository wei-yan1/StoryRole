const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots");
const USERNAME = `ui_smoke_${Date.now().toString().slice(-8)}`;
const PASSWORD = "smoke-pass-1234";
const pages = [
  ["/", "login", "登录"],
  ["/storyrole", "home", "总览工作台"],
  ["/novels", "novels", "小说档案"],
  ["/characters", "characters", "角色档案"],
  ["/periods", "periods", "时期画像"],
  ["/chat", "chat", "角色对话"],
  ["/media", "media", "多模态入口"],
  ["/media/image", "media-image", "图片生成"],
  ["/media/read", "media-read", "读图与 OCR"],
  ["/media/voice", "media-voice", "语音合成与转写"],
  ["/media/translate", "media-translate", "翻译"],
  ["/models", "models", "调用监控"],
  ["/settings", "settings", "设置"],
];
const errors = [];
const report = [];

fs.mkdirSync(SHOT_DIR, { recursive: true });

function safeName(value) {
  return value.replace(/[^a-z0-9-]/gi, "_");
}

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on("console", message => {
    if (message.type() === "error") errors.push(`[console] ${page.url()} :: ${message.text()}`);
  });
  page.on("pageerror", error => errors.push(`[pageerror] ${page.url()} :: ${error.message}`));

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(SHOT_DIR, "login-1440.png"), fullPage: true });

  // Exercise the real register -> login flow on the login page.
  await page.click("#switch-mode");
  await page.fill("#username", USERNAME);
  await page.fill("#password", PASSWORD);
  await page.fill("#password-confirm", PASSWORD);
  await Promise.all([
    page.waitForURL("**/storyrole", { timeout: 15000 }).catch(() => null),
    page.click("#submit-button")
  ]);
  report.push({ page: "/", status: page.url().includes("/storyrole") ? "register + redirect OK" : `register failed: ${await page.locator("#message").innerText().catch(() => "no message")}` });

  for (const [url, key, label] of pages.slice(1)) {
    await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);
    const text = await page.locator("body").innerText();
    const hasError = await page.locator(".error, #error").filter({ visible: true }).count().catch(() => 0);
    const visibleError = hasError ? (await page.locator(".error, #error").filter({ visible: true }).first().innerText().catch(() => "")) : "";
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    const shot = path.join(SHOT_DIR, `${key}-1440.png`);
    await page.screenshot({ path: shot, fullPage: true });
    report.push({ page: url, label, chars: text.length, overflow, errorBanner: visibleError, shot });
  }

  // Tablet pass: the 768 width is where navigation and two-column layouts usually break.
  await page.setViewportSize({ width: 768, height: 1024 });
  for (const [url, key] of pages.slice(1)) {
    await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    const shot = path.join(SHOT_DIR, `${key}-768.png`);
    await page.screenshot({ path: shot, fullPage: true });
    report.push({ page: `${url} (tablet)`, overflow, shot });
  }

  // Mobile pass across every page, not just the obvious ones.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [url, key, label] of pages.slice(1)) {
    await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    const shot = path.join(SHOT_DIR, `${key}-390.png`);
    await page.screenshot({ path: shot, fullPage: true });
    report.push({ page: `${url} (mobile)`, overflow, shot });
  }

  fs.writeFileSync(path.join("D:", "AgentCode", "two", "docs", "ui-smoke-report.json"), JSON.stringify({ username: USERNAME, report, errors }, null, 2), "utf8");
  console.log(JSON.stringify({ username: USERNAME, report, errors }, null, 2));
  await browser.close();
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
