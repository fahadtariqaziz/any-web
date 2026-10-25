// Screenshot one builder tab (M11): node frontend/scripts/shot_tab.mjs <url> <tab label> <out.png> [scrollSelector]
// Opens the page in headless Chrome (DevTools protocol), clicks the tab, scrolls the work pane to the bottom if
// asked, and writes a 1440x900 screenshot. Prints the work pane's text so checks can grep it.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const CH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [URL, TAB, OUT, SCROLL] = process.argv.slice(2);
const chrome = spawn(CH, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9334", "--window-size=1440,900", `--user-data-dir=${process.env.TMPDIR ?? "/tmp"}/builder-shot`, "about:blank"]);
let targets;
for (let i = 0; i < 40 && !targets; i++) {
  await new Promise((r) => setTimeout(r, 250));
  try { targets = await (await fetch("http://127.0.0.1:9334/json")).json(); } catch {}
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
await send("Page.navigate", { url: URL }); await sleep(6000);
await evalJs(`[...document.querySelectorAll('[role=tab]')].find(b => b.textContent.trim() === ${JSON.stringify(TAB)})?.click()`);
await sleep(2500);
if (SCROLL) await evalJs(`document.querySelectorAll(${JSON.stringify(SCROLL)}).forEach(e => e.scrollTop = e.scrollHeight)`);
await sleep(500);
writeFileSync(OUT, Buffer.from((await send("Page.captureScreenshot")).data, "base64"));
console.log(await evalJs(`document.querySelector('[aria-label="Preview and documents"]')?.innerText ?? ""`));
chrome.kill();
process.exit(0);
