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
  await page.waitForTimeout(500);
  const button = page.locator("[data-profile]").first();
  const label = await button.innerText().catch(() => "");
  await button.click();
  let out = { label };
  for (let index = 0; index < 60; index += 1) {
    await page.waitForTimeout(2000);
    const ready = await page.locator(".scene-row-state").first().innerText().catch(() => "");
    if (ready.includes("人设可用") || ready.includes("等待准备人设") && index > 3) {
      out = { ...out, ready, seconds: index * 2 };
      break;
    }
  }
  await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "scenes-after-profile.png"), fullPage: true });
  out.errors = errors;
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();