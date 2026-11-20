const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }) })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await (await browser.newContext({ viewport: { width: 768, height: 1024 } })).newPage();
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });
  for (const url of ["/chats", "/chats/new", "/characters", "/characters/81", "/characters/81/scenes", "/library", "/tools", "/settings", "/chats/72"]) {
    await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(250);
    const result = await page.evaluate(() => {
      const vw = window.innerWidth;
      const offenders = [];
      for (const node of document.querySelectorAll("body *")) {
        const rect = node.getBoundingClientRect();
        if (rect.right > vw + 1 && rect.width > 2) {
          const style = getComputedStyle(node);
          offenders.push({ tag: node.tagName, cls: node.className, right: Math.round(rect.right), width: Math.round(rect.width), text: (node.textContent || "").trim().slice(0, 24), overflowX: style.overflowX });
        }
      }
      return { vw, scrollWidth: document.documentElement.scrollWidth, offenders: offenders.slice(0, 12) };
    });
    console.log(url, JSON.stringify(result));
  }
  await browser.close();
})();