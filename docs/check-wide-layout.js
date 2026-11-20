const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ui_flow_29166046", password: "smoke-pass-1234" }) })).json();
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const ctx = await browser.newContext({ viewport: { width: 2550, height: 1275 } });
  const page = await ctx.newPage();
  await page.addInitScript(({ token, user }) => { localStorage.setItem("access_token", token); localStorage.setItem("storyrole_user", JSON.stringify(user)); }, { token: login.access_token, user: login.user });
  for (const url of ["/characters", "/chats", "/characters/80"]) {
    await page.goto(BASE + url, { waitUntil: "networkidle" });
    console.log(url, await page.evaluate(() => {
      const el = document.querySelector(".page");
      const grid = document.querySelector(".character-grid");
      const card = document.querySelector(".character-card");
      return {
        viewport: innerWidth,
        pageMax: getComputedStyle(el).maxWidth,
        pageWidth: el.getBoundingClientRect().width,
        pageLeft: el.getBoundingClientRect().left,
        gridCols: grid ? getComputedStyle(grid).gridTemplateColumns : null,
        cardWidth: card ? card.getBoundingClientRect().width : null,
        matches: matchMedia("(min-width: 2000px)").matches,
      };
    }));
  }
  await browser.close();
})();
