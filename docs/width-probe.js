const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }) })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await page.addInitScript(({ token, user }) => { localStorage.setItem("access_token", token); localStorage.setItem("storyrole_user", JSON.stringify(user)); }, { token: login.access_token, user: login.user });
  await page.goto(`${BASE}/characters`, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  console.log(await page.evaluate(() => {
    const names = ["body", ".shell", ".sidebar", ".side-nav", ".main", ".page", ".character-grid", ".character-card"];
    const out = {};
    for (const sel of names) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      out[sel] = { left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width), scrollWidth: el.scrollWidth, minWidth: getComputedStyle(el).minWidth, display: getComputedStyle(el).display, overflowX: getComputedStyle(el).overflowX };
    }
    return { vw: innerWidth, doc: document.documentElement.scrollWidth, body: document.body.scrollWidth, out };
  }));
  await browser.close();
})();