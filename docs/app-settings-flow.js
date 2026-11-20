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
  await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const before = await page.locator("#runtime-guard").isChecked();
  await page.locator(".switch").click();
  await page.click("#save-settings");
  await page.waitForTimeout(800);
  const status = await page.locator("#settings-status").innerText().catch(() => "");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const after = await page.locator("#runtime-guard").isChecked();
  await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "settings-after-save.png"), fullPage: true });
  console.log(JSON.stringify({ before, after, status, errors }, null, 2));
  await browser.close();
})();