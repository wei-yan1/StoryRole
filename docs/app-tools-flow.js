const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3");
const OCR_SAMPLE = path.join("D:", "AgentCode", "two", "docs", "assets", "ocr-sample.png");

(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }),
  })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 980 } })).newPage();
  const errors = [];
  page.on("console", message => { if (message.type() === "error") errors.push(`[console] ${page.url()} :: ${message.text()}`); });
  page.on("pageerror", error => errors.push(`[pageerror] ${page.url()} :: ${error.message}`));
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });
  const out = {};

  await page.goto(`${BASE}/tools/translate`, { waitUntil: "networkidle" });
  await page.fill("#translate-text", "罗辑坐在窗前，外面下着细雨。");
  await page.selectOption("#translate-source", "Chinese");
  await page.selectOption("#translate-target", "English");
  await page.click("#translate-send");
  await page.waitForFunction(() => document.querySelector("#translate-status")?.textContent.includes("完成"), null, { timeout: 120000 });
  out.translate = (await page.locator("#translate-result").innerText()).slice(0, 300);
  await page.screenshot({ path: path.join(SHOT_DIR, "tool-translate-result.png"), fullPage: true });

  await page.goto(`${BASE}/tools/ocr`, { waitUntil: "networkidle" });
  await page.setInputFiles("#vision-file", OCR_SAMPLE);
  await page.click("#vision-submit");
  await page.waitForFunction(() => document.querySelector("#vision-status")?.textContent.includes("完成"), null, { timeout: 120000 });
  out.ocr = (await page.locator("#vision-text").innerText()).slice(0, 300);
  await page.screenshot({ path: path.join(SHOT_DIR, "tool-ocr-result.png"), fullPage: true });

  await page.goto(`${BASE}/tools/voice`, { waitUntil: "networkidle" });
  await page.fill("#tts-text", "你好，我是罗辑。今天窗外下着细雨，很适合安静地聊一会儿。");
  await page.click("#tts-send");
  await page.waitForFunction(() => document.querySelector("#tts-audio")?.getAttribute("src"), null, { timeout: 120000 });
  out.tts = await page.locator("#tts-audio").getAttribute("src");
  await page.screenshot({ path: path.join(SHOT_DIR, "tool-voice-result.png"), fullPage: true });

  await page.goto(`${BASE}/tools/image`, { waitUntil: "networkidle" });
  await page.fill("#image-prompt", "清晨的街角咖啡馆，窗边有一杯冒热气的咖啡，胶片质感，暖色调");
  await page.click("#image-generate");
  await page.waitForFunction(() => document.querySelector("#image-preview")?.getAttribute("src"), null, { timeout: 180000 });
  out.image = await page.locator("#image-preview").getAttribute("src");
  await page.screenshot({ path: path.join(SHOT_DIR, "tool-image-result.png"), fullPage: true });

  await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
  const before = await page.locator("#runtime-guard").isChecked();
  await page.locator('label.switch:has(#runtime-guard)').click();
  await page.click("#save-settings");
  await page.waitForFunction(() => document.querySelector("#settings-status")?.textContent.includes("已保存"), null, { timeout: 30000 });
  await page.reload({ waitUntil: "networkidle" });
  const after = await page.locator("#runtime-guard").isChecked();
  out.settings = { before, after, status: await page.locator("#settings-status").innerText().catch(() => "") };
  await page.screenshot({ path: path.join(SHOT_DIR, "settings-after-save.png"), fullPage: true });

  out.errors = errors;
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();