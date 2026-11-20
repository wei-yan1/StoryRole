const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
const NAME = process.argv[2] || "云天明";
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
  await page.goto(`${BASE}/characters/new`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.fill("#character-name", NAME);
  await page.click("#create-character");
  let result = { name: NAME };
  for (let index = 0; index < 60; index += 1) {
    await page.waitForTimeout(2000);
    const state = await page.evaluate(() => ({
      url: location.href,
      error: document.querySelector("#create-error")?.textContent || "",
      button: document.querySelector("#create-character")?.textContent || "",
    }));
    if (state.url.includes("/scenes") || state.error || !state.button.includes("查找")) {
      result = { ...result, ...state };
      break;
    }
  }
  await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "character-new-result.png"), fullPage: true });
  result.errors = errors;
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})();