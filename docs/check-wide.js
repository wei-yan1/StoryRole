const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:8765";
(async () => {
  const login = await (await fetch(`${BASE}/api/app/auth/login`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({username:"ui_flow_29166046",password:"smoke-pass-1234"})})).json();
  const browser = await chromium.launch({headless:true, executablePath:"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"});
  const ctx = await browser.newContext({viewport:{width:2550,height:1275}, deviceScaleFactor:1});
  const page = await ctx.newPage();
  await page.addInitScript(({token,user}) => { localStorage.setItem("access_token",token); localStorage.setItem("storyrole_user",JSON.stringify(user)); }, {token:login.access_token,user:login.user});
  for (const [url, name] of [["/chats","wide-chats"],["/characters","wide-characters"],["/characters/80","wide-character"]]) {
    await page.goto(BASE+url, {waitUntil:"networkidle"});
    await page.waitForTimeout(300);
    await page.screenshot({path:path.join("D:\\AgentCode\\two\\docs\\ui-shots-v4", name+".png"), fullPage:true});
  }
  await browser.close();
})();
