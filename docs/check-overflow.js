const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }) })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const ctx = await browser.newContext({ viewport: { width: 768, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript(({ token, user }) => { localStorage.setItem("access_token", token); localStorage.setItem("storyrole_user", JSON.stringify(user)); }, { token: login.access_token, user: login.user });
  await page.goto(`${BASE}/characters/81`, { waitUntil: "networkidle" });
  console.log(await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    offenders: Array.from(document.querySelectorAll("body *")).filter(el => {
      const r = el.getBoundingClientRect();
      return r.right > document.documentElement.clientWidth + 2 || r.left < -2;
    }).slice(0, 20).map(el => ({ tag: el.tagName, cls: el.className, left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right, text: (el.textContent || "").trim().slice(0, 30) })),
  })));
  await browser.close();
})();
