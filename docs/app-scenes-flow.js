const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
const CHARACTER = process.argv[2] || "87";
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
  await page.goto(`${BASE}/characters/${CHARACTER}/scenes`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const start = await page.locator(".scene-row").count();
  await page.locator("#scene-empty-analyze").click();
  let result = { character: CHARACTER, start };
  for (let index = 0; index < 90; index += 1) {
    await page.waitForTimeout(2000);
    const state = await page.evaluate(() => ({
      rows: document.querySelectorAll(".scene-row").length,
      note: document.querySelector("#analysis-note")?.textContent || "",
      button: document.querySelector("#analyze-button")?.textContent || "",
    }));
    if (state.rows || state.button.includes("分析时间线")) {
      result = { ...result, ...state, seconds: index * 2 };
      break;
    }
  }
  await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "scenes-after-analyze.png"), fullPage: true });
  result.errors = errors;
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})();