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
  await page.goto(`${BASE}/tools/voice`, { waitUntil: "networkidle" });
  await page.fill("#tts-text", "你好，我是罗辑。今天窗外下着细雨，很适合安静地聊一会儿。");
  await page.click("#tts-send");
  for (let index = 0; index < 60; index += 1) {
    const state = await page.evaluate(() => ({
      status: document.querySelector("#tts-status")?.textContent || "",
      src: document.querySelector("#tts-audio")?.getAttribute("src") || "",
      error: document.querySelector("#tts-status")?.className || "",
    }));
    if (state.status.includes("完成") || state.status.includes("失败") || state.status.includes("错误") || state.src) {
      console.log(JSON.stringify({ seconds: index * 2, ...state, errors }, null, 2));
      await page.screenshot({ path: path.join("D:", "AgentCode", "two", "docs", "ui-shots-v3", "tool-voice-result.png"), fullPage: true });
      await browser.close();
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  console.log(JSON.stringify({ timeout: true, status: await page.locator("#tts-status").innerText().catch(() => ""), errors }, null, 2));
  await browser.close();
})();