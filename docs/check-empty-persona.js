const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }),
  })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });
  await page.route("**/api/app/characters/80", async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.character.name = "三体";
    data.source.name = "three_body";
    data.profile = null;
    data.periods = (data.periods || []).map(period => ({ ...period, profile_ready: false, profile_version: null }));
    await route.fulfill({ response, json: data });
  });
  await page.goto(`${BASE}/characters/80`, { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join("D:\\AgentCode\\two\\docs\\ui-shots-v5", "empty-persona-1440.png"), fullPage: true });
  console.log(await page.locator(".character-hero-meta").innerText());
  await browser.close();
})();
