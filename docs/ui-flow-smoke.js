const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8765";
const SHOT_DIR = path.join("D:", "AgentCode", "two", "docs", "ui-shots");
const USERNAME = `ui_flow_${Date.now().toString().slice(-8)}`;
const PASSWORD = "smoke-pass-1234";
const report = [];
const errors = [];

function mark(name, ok, detail) {
  report.push({ name, ok, detail });
}

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 980 } });
  const page = await context.newPage();
  const capture = async (name, fullPage = true) => {
    if (fullPage) {
      await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }));
      await page.waitForTimeout(300);
    }
    await page.screenshot({ path: path.join(SHOT_DIR, name), fullPage });
  };
  page.on("console", message => {
    if (message.type() === "error") errors.push(`[console] ${page.url()} :: ${message.text()}`);
  });
  page.on("pageerror", error => errors.push(`[pageerror] ${page.url()} :: ${error.message}`));

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.click("#switch-mode");
  await page.fill("#username", USERNAME);
  await page.fill("#password", PASSWORD);
  await page.fill("#password-confirm", PASSWORD);
  await Promise.all([page.waitForURL("**/storyrole", { timeout: 20000 }), page.click("#submit-button")]);
  mark("register/login", page.url().includes("/storyrole"), page.url());

  await page.goto(`${BASE}/novels`, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  await page.click("#restore-three-body");
  await page.waitForSelector(".library-row", { timeout: 20000 }).catch(() => null);
  await page.waitForTimeout(300);
  const rowCount = await page.locator(".library-row").count();
  if (rowCount) {
    await page.locator(".library-row").first().click();
    await page.waitForTimeout(300);
  }
  mark("restore bundled novel", rowCount > 0, `${rowCount} library rows`);
  await page.screenshot({ path: path.join(SHOT_DIR, "flow-novels.png"), fullPage: true });

  await page.goto(`${BASE}/characters`, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  const novelValue = await page.locator("#novel-select").inputValue().catch(() => "");
  if (novelValue) {
    await page.fill("#character-name", "罗辑");
    await page.click("#setup-button");
    await page.waitForTimeout(9000);
    const status = await page.locator("#character-status").innerText().catch(() => "");
    const hasDossier = await page.locator(".dossier-cover").count();
    mark("setup character", hasDossier > 0 || /已建立|恢复/.test(status), `${status} | dossier=${hasDossier}`);
  } else {
    mark("setup character", false, "no novel context");
  }
  await page.screenshot({ path: path.join(SHOT_DIR, "flow-characters.png"), fullPage: true });

  await page.goto(`${BASE}/periods`, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  const hasCharacter = await page.locator("#period-layout").isVisible().catch(() => false);
  if (hasCharacter) {
    const existingPeriods = await page.evaluate(async () => {
      const context = window.Studio.getContext();
      return await window.Studio.api(`/api/v1/storyrole/novels/${encodeURIComponent(context.novelId)}/characters/${context.characterId}/periods`);
    });
    await page.click("#add-period");
    await page.fill("#period-name", "测试时期");
    await page.fill("#period-start", "第 1 章");
    await page.fill("#period-end", "第 36 章");
    await page.fill("#period-keywords", "测试、时期");
    await page.fill("#period-rationale", "前端流程回归使用的临时时期。");
    await page.screenshot({ path: path.join(SHOT_DIR, "flow-periods-editor.png"), fullPage: true });

    await page.route("**/api/v1/storyrole/**/periods/confirm", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ periods: [...existingPeriods, { id: "smoke-period-1", name: "测试时期", status: "confirmed", chapter_start: "第 1 章", chapter_end: "第 36 章", keywords: ["测试", "时期"], rationale: "前端流程回归使用的临时时期。", confidence: 0.8 }] })
    }));
    await page.route(/\/periods\/[^/]+\/profile$/, route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ trace_summary: { duration_ms: 1234, total_tokens: 1000, usage_complete: true }, trace_steps: [{ step_name: "period_profile" }], trace_agents: [{ agent_id: "nuwa-profiler" }] })
    }));
    await page.click("#confirm-periods");
    await page.waitForTimeout(700);
    const periodStatus = await page.locator("#period-status").innerText().catch(() => "");
    const periodRows = await page.locator(".period-row").count();
    mark("period save + profile UI", periodRows > 0 && /已处理|画像/.test(periodStatus), `${periodStatus} | rows=${periodRows}`);
    const chatLink = await page.locator("#chat-next").isVisible().catch(() => false);
    if (await page.locator("#open-trace").isVisible().catch(() => false)) {
      await page.click("#open-trace");
      await page.waitForTimeout(300);
      const drawerOpen = await page.locator("#trace-drawer.is-open").count();
      await page.screenshot({ path: path.join(SHOT_DIR, "flow-periods-trace.png"), fullPage: false });
      await page.click("#close-trace");
      mark("trace drawer", drawerOpen > 0, `open=${drawerOpen}`);
    }
    mark("chat CTA", chatLink, `visible=${chatLink}`);
  } else {
    mark("period page context", false, "period layout hidden");
  }
  await page.screenshot({ path: path.join(SHOT_DIR, "flow-periods.png"), fullPage: true });

  await page.goto(`${BASE}/chat`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const chatVisible = await page.locator(".chat-shell, .chat-layout, #chat-log").count();
  mark("chat page", chatVisible > 0, `chat shells=${chatVisible}`);
  await page.screenshot({ path: path.join(SHOT_DIR, "flow-chat.png"), fullPage: true });

  await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  await page.click("#save-settings-top");
  await page.waitForTimeout(600);
  const saveStatus = await page.locator("#status").innerText().catch(() => "");
  mark("settings save", /已保存/.test(saveStatus), saveStatus);
  await page.screenshot({ path: path.join(SHOT_DIR, "flow-settings.png"), fullPage: true });

  await page.goto(`${BASE}/media/translate`, { waitUntil: "networkidle" });
  await page.fill("#translate-text", "你好，很高兴见到你。");
  await page.click("#translate-send");
  await page.waitForTimeout(1800);
  const translated = await page.locator("#translate-output").innerText().catch(() => "");
  mark("translate UI", translated.length > 4 && !translated.includes("译文会出现在这里"), translated.slice(0, 80));
  await capture("flow-translate.png");

  await page.goto(`${BASE}/media/read`, { waitUntil: "networkidle" });
  await page.setInputFiles("#vision-file", path.join("D:", "AgentCode", "two", "docs", "assets", "ocr-sample.png"));
  await page.click("#vision-submit");
  await page.waitForTimeout(6500);
  const visionVisible = await page.locator("#vision-result").isVisible().catch(() => false);
  const visionText = await page.locator("#vision-text").innerText().catch(() => "");
  mark("OCR UI", visionVisible && visionText.length > 4, `visible=${visionVisible} chars=${visionText.length}`);
  await capture("flow-read.png");

  await page.goto(`${BASE}/media/voice`, { waitUntil: "networkidle" });
  await page.fill("#tts-text", "你好，这是 StoryRole 的语音测试。");
  await page.click("#tts-send");
  await page.waitForTimeout(2200);
  const ttsVisible = await page.locator("#tts-result").isVisible().catch(() => false);
  const ttsSrc = await page.locator("#tts-audio").getAttribute("src").catch(() => "");
  mark("TTS UI", ttsVisible && Boolean(ttsSrc), `visible=${ttsVisible} src=${ttsSrc ? "set" : "empty"}`);
  await capture("flow-voice.png");

  await page.setInputFiles("#asr-file", path.join("D:", "AgentCode", "two", "data", "generated", "audio", "1189e658ee7842128d33ca65b5059f12.wav"));
  await page.click("#asr-send");
  await page.waitForTimeout(4000);
  const asrVisible = await page.locator("#asr-result").isVisible().catch(() => false);
  const asrText = await page.locator("#asr-text").innerText().catch(() => "");
  mark("ASR UI", asrVisible && asrText.length > 2, `visible=${asrVisible} text=${asrText.slice(0, 60)}`);
  await capture("flow-voice-asr.png");

  await page.route("**/api/v1/media/images/generate", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ model: "stub-image", size: "1024x1024", url: "/static/assets/luoji.jpg", bytes: 12345 })
  }));
  await page.goto(`${BASE}/media/image`, { waitUntil: "networkidle" });
  await page.fill("#image-prompt", "黄昏的雪原与射电望远镜，电影感。");
  await page.click("#image-generate");
  await page.waitForTimeout(600);
  const imageVisible = await page.locator("#image-result").isVisible().catch(() => false);
  const imageSrc = await page.locator("#image-preview").getAttribute("src").catch(() => "");
  mark("image UI (mocked response)", imageVisible && Boolean(imageSrc), `visible=${imageVisible} src=${imageSrc ? "set" : "empty"}`);
  await capture("flow-image.png");

  fs.writeFileSync(path.join("D:", "AgentCode", "two", "docs", "ui-flow-report.json"), JSON.stringify({ username: USERNAME, report, errors }, null, 2), "utf8");
  console.log(JSON.stringify({ username: USERNAME, report, errors }, null, 2));
  await browser.close();
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
