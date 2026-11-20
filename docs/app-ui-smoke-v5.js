const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots-v6");
const USERNAME = "ui_flow_29166046";
const PASSWORD = "smoke-pass-1234";
const VIEWPORTS = [
  [1440, 980, "1440"],
  [768, 900, "768"],
  [390, 844, "390"],
];
const PAGES = [
  ["/", "shelf", "书架"],
  ["/novels/三体-三部曲", "novel", "小说详情"],
  ["/novels/new", "novel-new", "新增小说"],
  ["/usage", "usage", "用量"],
  ["/settings", "settings", "设置"],
  ["/chats", "chats", "对话列表"],
  ["/chats/72", "chat-thread", "对话详情"],
  ["/chats/new?character=81", "chat-new", "新对话"],
  ["/characters", "characters", "角色"],
  ["/characters/81", "character", "角色详情"],
  ["/characters/81/scenes", "scenes", "场景"],
  ["/characters/new", "character-new", "新建角色"],
  ["/tools", "tools", "工具"],
  ["/tools/image", "tool-image", "图片工具"],
  ["/tools/ocr", "tool-ocr", "OCR 工具"],
  ["/tools/voice", "tool-voice", "语音工具"],
  ["/tools/translate", "tool-translate", "翻译工具"],
];

const errors = [];
const report = [];
fs.mkdirSync(SHOT_DIR, { recursive: true });

async function api(pathname, options = {}) {
  const response = await fetch(`${BASE}${pathname}`, options);
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

  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  });

  for (const [width, height, suffix] of VIEWPORTS) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.on("console", message => {
      if (message.type() === "error") errors.push(`[${suffix}] [console] ${page.url()} :: ${message.text()}`);
    });
    page.on("pageerror", error => errors.push(`[${suffix}] [pageerror] ${page.url()} :: ${error.message}`));
    await page.addInitScript(({ token, user }) => {
      localStorage.setItem("access_token", token);
      localStorage.setItem("storyrole_user", JSON.stringify(user));
    }, { token: login.access_token, user: login.user });

    for (const [url, key, label] of PAGES) {
      const response = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(500);
      const status = response ? response.status() : 0;
      const text = await page.locator("body").innerText().catch(() => "");
      const checks = await page.evaluate(() => ({
        bookCards: document.querySelectorAll(".book-card").length,
        castCards: document.querySelectorAll(".cast-card").length,
        stageCards: document.querySelectorAll(".stage-card").length,
        modelRows: document.querySelectorAll(".model-row").length,
        importCard: Boolean(document.querySelector(".import-card")),
        overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
      }));
      const shot = path.join(SHOT_DIR, `${key}-${suffix}.png`);
      await page.screenshot({ path: shot, fullPage: true });
      report.push({ page: url, label, viewport: suffix, status, chars: text.length, ...checks, shot, sample: text.slice(0, 90).replace(/\s+/g, " ") });
    }
    await context.close();
  }

  await browser.close();
  fs.writeFileSync(
    path.join("D:", "AgentCode", "two", "docs", "app-ui-report-v6.json"),
    JSON.stringify({ generatedAt: new Date().toISOString(), errors, report }, null, 2),
    "utf8",
  );
  console.log(JSON.stringify({ errors, report }, null, 2));
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
