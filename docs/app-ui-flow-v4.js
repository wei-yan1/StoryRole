const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots-v4");
const USERNAME = "ui_flow_29166046";
const PASSWORD = "smoke-pass-1234";
const errors = [];
const steps = [];
fs.mkdirSync(SHOT_DIR, { recursive: true });

async function api(pathname, options = {}) {
  const response = await fetch(`${BASE}${pathname}`, options);
  const data = await response.json();
  if (!response.ok) throw new Error(`${pathname}: ${JSON.stringify(data)}`);
  return data;
}

async function main() {
  const login = await api("/api/app/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on("console", message => {
    if (message.type() === "error") errors.push(`[console] ${page.url()} :: ${message.text()}`);
  });
  page.on("pageerror", error => errors.push(`[pageerror] ${page.url()} :: ${error.message}`));
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("storyrole_user", JSON.stringify(user));
  }, { token: login.access_token, user: login.user });

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  const bookHref = await page.locator(".book-card:not(.book-add)").first().getAttribute("href");
  steps.push({ step: "shelf loaded", href: bookHref, url: page.url() });
  await page.locator(".book-card:not(.book-add)").first().click();
  await page.waitForURL(/\/novels\//, { timeout: 10000 });
  await page.waitForTimeout(500);
  steps.push({ step: "book opens novel", url: page.url(), title: await page.locator("h1").first().innerText() });
  if ((await page.locator(".cast-card").count()) < 5) throw new Error("novel character cards missing");
  if (!(await page.locator(".novel-recent").count())) throw new Error("novel recent conversations missing");

  await page.locator(".cast-card").first().locator(".cast-summary").click();
  await page.waitForURL(/\/characters\//, { timeout: 10000 });
  await page.waitForTimeout(500);
  steps.push({ step: "character card opens character", url: page.url(), title: await page.locator("h1").first().innerText() });

  await page.goto(`${BASE}/usage`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  await page.locator("#usage-range").selectOption("7");
  await page.waitForTimeout(700);
  steps.push({ step: "usage range changes", cards: await page.locator(".stage-card").count(), url: page.url() });
  if (!(await page.locator(".stage-card").count())) throw new Error("usage stage cards missing after range change");

  await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  steps.push({ step: "settings loaded", modelRows: await page.locator(".model-row").count(), url: page.url() });
  if ((await page.locator(".model-row").count()) < 11) throw new Error("runtime models missing");

  await page.screenshot({ path: path.join(SHOT_DIR, "flow-settings.png"), fullPage: true });
  await browser.close();
  fs.writeFileSync(path.join("D:", "AgentCode", "two", "docs", "app-ui-flow-report-v4.json"), JSON.stringify({ generatedAt: new Date().toISOString(), errors, steps }, null, 2), "utf8");
  console.log(JSON.stringify({ errors, steps }, null, 2));
}
main().catch(error => { console.error(error); process.exit(1); });
