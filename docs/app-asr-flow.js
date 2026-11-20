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
  await page.goto(`${BASE}/tools/voice`, { waitUntil: "networkidle" });
  await page.locator('[data-mode="asr"]').click();
  await page.setInputFiles("#asr-file", path.join("D:", "AgentCode", "two", "data", "generated", "audio", "36e6825623914bf9afdd1cf43f7ce653.wav"));
  await page.click("#asr-send");
  let output = {};
  for (let index = 0; index < 45; index += 1) {
    await page.waitForTimeout(2000);
    const state = await page.evaluate(() => ({
      status: document.querySelector("#asr-status")?.textContent || "",
      text: document.querySelector("#asr-text")?.textContent || "",
      meta: document.querySelector("#asr-meta")?.textContent || "",
    }));
    if (state.status.includes("完成") || state.status.includes("失败")) { output = { seconds: index * 2, ...state }; break; }
  }
  output.errors = errors;
  console.log(JSON.stringify(output, null, 2));
  await browser.close();
})();