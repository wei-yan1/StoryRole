const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
const pages = [
  ["/chats", "simplify-chats"],
  ["/characters", "simplify-characters"],
  ["/characters/80", "simplify-character"],
  ["/characters/87", "simplify-character-87"],
  ["/characters/80/scenes", "simplify-scenes"],
  ["/chats/72", "simplify-chat-thread"],
  ["/chats/new?character=81", "simplify-chat-new"],
  ["/novels/三体-三部曲", "simplify-novel"],
];
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }),
  })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const errors = [];
  for (const width of [2550, 1440]) {
    const ctx = await browser.newContext({ viewport: { width, height: width === 2550 ? 1275 : 900 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    page.on("console", msg => { if (msg.type() === "error") errors.push({ width, url: page.url(), console: msg.text() }); });
    page.on("pageerror", err => errors.push({ width, url: page.url(), pageerror: err.message }));
    await page.addInitScript(({ token, user }) => {
      localStorage.setItem("access_token", token);
      localStorage.setItem("storyrole_user", JSON.stringify(user));
    }, { token: login.access_token, user: login.user });
    for (const [url, name] of pages) {
      await page.goto(BASE + url, { waitUntil: "networkidle" });
      await page.waitForTimeout(250);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      if (overflow) errors.push({ width, url, overflow: true });
      await page.screenshot({ path: path.join("D:\\AgentCode\\two\\docs\\ui-shots-v5", `${name}-${width}.png`), fullPage: true });
    }
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify({ errors }, null, 2));
})();
