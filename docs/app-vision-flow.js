const { chromium } = require("playwright");
const path = require("path");
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
  await page.goto(`${BASE}/tools/ocr`, { waitUntil: "networkidle" });
  await page.locator('[data-mode="vision"]').click();
  await page.setInputFiles("#vision-file", path.join("D:", "AgentCode", "two", "docs", "assets", "ocr-sample.png"));
  await page.click("#vision-submit");
  let output = {};
  for (let index = 0; index < 45; index += 1) {
    await page.waitForTimeout(2000);
    const state = await page.evaluate(() => ({
      status: document.querySelector("#vision-status")?.textContent || "",
      text: document.querySelector("#vision-text")?.textContent || "",
      meta: document.querySelector("#vision-meta")?.textContent || "",
    }));
    if (state.status.includes("完成") || state.status.includes("失败")) { output = { seconds: index * 2, ...state }; break; }
  }
  output.errors = errors;
  console.log(JSON.stringify({ ...output, text: output.text?.slice(0, 180) }, null, 2));
  await browser.close();
})();