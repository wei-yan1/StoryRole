const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots");
const USERNAME = "ui_flow_26888107";
const PASSWORD = "smoke-pass-1234";
const NOVEL = "builtin_three_body_v1";
const CHARACTER = "31";
const PERIOD = "25";

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 980 } });
  const page = await context.newPage();
  const errors = [];
  page.on("console", message => {
    if (message.type() === "error") errors.push(`[console] ${message.text()}`);
  });
  page.on("pageerror", error => errors.push(`[pageerror] ${error.message}`));

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.evaluate(async ({ username, password }) => {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "login failed");
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("current_user", JSON.stringify(data.user || {}));
  }, { username: USERNAME, password: PASSWORD });

  await page.goto(`${BASE}/chat?novel=${NOVEL}&character=${CHARACTER}&period=${PERIOD}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  const ready = await page.locator("#send-button").isEnabled().catch(() => false);
  await page.screenshot({ path: path.join(SHOT_DIR, "flow-chat-ready.png"), fullPage: true });

  let answer = "";
  let status = "";
  let overflowState = null;
  if (ready) {
    const initialAnswers = await page.locator(".message-row.assistant").count();
    await page.fill("#chat-input", "你好，罗辑。换一个问题：你今天过得怎么样？");
    await page.click("#send-button");
    try {
      await page.waitForFunction(initialCount => {
        const status = document.querySelector("#chat-status")?.textContent || "";
        const rows = document.querySelectorAll(".message-row.assistant");
        const last = rows[rows.length - 1];
        const answered = rows.length > initialCount && (last?.querySelector(".message-bubble")?.textContent || "").length > 12;
        const stillWriting = status.includes("处理中") || status.includes("正在回答");
        return answered && !stillWriting;
      }, initialAnswers, { timeout: 90000 });
    } catch (_) {}
    await page.waitForTimeout(400);
    answer = await page.locator(".message-row.assistant .message-bubble").last().innerText().catch(() => "");
    status = await page.locator("#chat-status").innerText().catch(() => "");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    overflowState = overflow;
    if (overflow) errors.push("chat page has horizontal overflow");
    await page.screenshot({ path: path.join(SHOT_DIR, "flow-chat-answer.png"), fullPage: true });
  }

  const report = { ready, answerLength: answer.length, answer: answer.slice(0, 200), status, overflow: overflowState, errors };
  fs.writeFileSync(path.join("D:", "AgentCode", "two", "docs", "chat-ui-report.json"), JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
