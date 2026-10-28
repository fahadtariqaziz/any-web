// Tap through the clarification questions by clicking option chips (2026-10-29 check):
//   node frontend/scripts/click_flow.mjs <project url> <out-prefix>
// Clicks the first option of each question, screenshots after each click, prints the chat column's text.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const CH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [URL, OUT] = process.argv.slice(2);
const chrome = spawn(CH, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9336", "--window-size=1440,900", `--user-data-dir=${process.env.TMPDIR ?? "/tmp"}/builder-shot3`, "about:blank"]);
let targets;
for (let i = 0; i < 40 && !targets; i++) {
  await new Promise((r) => setTimeout(r, 250));
  try { targets = await (await fetch("http://127.0.0.1:9336/json")).json(); } catch {}
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true })).result.value;
await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: URL }); await sleep(5000);
for (let step = 1; step <= 3; step++) {
  const clicked = await evalJs(`(() => { const b = document.querySelector('[aria-label="Answer options"] button'); if (!b) return null; const t = b.textContent; b.click(); return t; })()`);
  console.log(`step ${step}: clicked ${clicked}`);
  await sleep(step === 2 ? 7000 : 1500);
  writeFileSync(`${OUT}-${step}.png`, Buffer.from((await send("Page.captureScreenshot")).data, "base64"));
  if (!clicked) break;
}
console.log("--- chat text ---");
console.log(await evalJs(`document.querySelector('[aria-label="Conversation"]')?.innerText ?? ""`));
chrome.kill();
process.exit(0);
