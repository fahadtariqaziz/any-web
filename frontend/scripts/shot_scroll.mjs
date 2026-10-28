// Screenshot a page at several scroll positions of its scrolling panel (2026-10-29, landing page check):
//   node frontend/scripts/shot_scroll.mjs <url> <out-prefix> <screens> [scrollSelector]
// Writes <out-prefix>-1.png ... (1440x900 each) and prints the page's text length.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const CH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [URL, OUT, N, SEL = ".scroll-thin"] = process.argv.slice(2);
const chrome = spawn(CH, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9335", "--window-size=1440,900", `--user-data-dir=${process.env.TMPDIR ?? "/tmp"}/builder-shot2`, "about:blank"]);
let targets;
for (let i = 0; i < 40 && !targets; i++) {
  await new Promise((r) => setTimeout(r, 250));
  try { targets = await (await fetch("http://127.0.0.1:9335/json")).json(); } catch {}
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
for (let i = 0; i < Number(N); i++) {
  await evalJs(`(document.querySelector(${JSON.stringify(SEL)}) ?? document.scrollingElement).scrollTop = ${i} * 820`);
  await sleep(1400);
  writeFileSync(`${OUT}-${i + 1}.png`, Buffer.from((await send("Page.captureScreenshot")).data, "base64"));
}
console.log("text length", await evalJs("document.body.innerText.length"));
chrome.kill();
process.exit(0);
