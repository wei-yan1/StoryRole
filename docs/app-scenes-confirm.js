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
  await page.goto(`${BASE}/characters/87/scenes`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  const out = { rowsBefore: await page.locator(".scene-row").count() };
  if (out.rowsBefore === 0) {
    await page.locator("#scene-empty-analyze").click();
    await page.waitForSelector("#save-analysis", { timeout: 120000 });
    out.suggested = await page.locator(".analysis-period-row").count();
    await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "scenes-analysis-modal.png"), fullPage: true });
    await page.click("#save-analysis");
    await page.waitForTimeout(1500);
  }
  out.rowsAfter = await page.locator(".scene-row").count();
  out.selected = await page.locator("#scene-detail-content").count();
  out.note = await page.locator("#analysis-note").innerText().catch(() => "");
  out.errors = errors;
  await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "scenes-after-confirm.png"), fullPage: true });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();