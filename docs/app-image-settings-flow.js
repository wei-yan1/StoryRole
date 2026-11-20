const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
const SHOTS = path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3");
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
  const out = {};

  await page.goto(`${BASE}/tools/image`, { waitUntil: "networkidle" });
  await page.fill("#image-prompt", "清晨的街角咖啡馆，窗边有一杯冒热气的咖啡，胶片质感，暖色调");
  await page.click("#image-generate");
  for (let index = 0; index < 90; index += 1) {
    const state = await page.evaluate(() => ({
      status: document.querySelector("#image-status")?.textContent || "",
      src: document.querySelector("#image-preview")?.getAttribute("src") || "",
    }));
    if (state.status.includes("已生成") || state.status.includes("失败") || state.status.includes("错误")) {
      out.image = { seconds: index * 2, ...state };
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  await page.screenshot({ path: path.join(SHOTS, "tool-image-result.png"), fullPage: true });

  await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const guard = page.locator("#runtime-guard");
  const before = await guard.isChecked();
  await page.locator('label.switch:has(#runtime-guard)').click();
  await page.click("#save-settings");
  await page.waitForFunction(() => document.querySelector("#settings-status")?.textContent.includes("已保存"), null, { timeout: 30000 }).catch(() => {});
  out.settingsStatus = await page.locator("#settings-status").innerText().catch(() => "");
  await page.reload({ waitUntil: "networkidle" });
  out.settings = { before, after: await page.locator("#runtime-guard").isChecked() };
  await page.screenshot({ path: path.join(SHOTS, "settings-after-save.png"), fullPage: true });
  out.errors = errors;
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();