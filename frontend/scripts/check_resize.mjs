// M10 resize check (run by backend/scripts/verify_m10.py): drives headless Chrome over the DevTools protocol (real
// mouse events) on a builder page: drag the chat | preview border right ACROSS the preview iframe, far left (min
// width), far right (max), reload (stored width kept), double-click (reset). Prints one JSON state per step.
// Usage: node frontend/scripts/check_resize.mjs http://localhost:3001/c/<thread_id>
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const CH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const URL = process.argv[2];
const chrome = spawn(CH, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9333", "--window-size=1440,900", `--user-data-dir=${process.env.TMPDIR ?? "/tmp"}/builder-resize-check`, "about:blank"]);
let targets;
for (let i = 0; i < 40 && !targets; i++) {
  await new Promise((r) => setTimeout(r, 250));
  try { targets = await (await fetch("http://127.0.0.1:9333/json")).json(); } catch {}
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true })).result.value;
const shot = async (name) => writeFileSync(`${process.env.TMPDIR ?? "/tmp/"}resize-${name}.png`, Buffer.from((await send("Page.captureScreenshot")).data, "base64"));
const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons: type === "mouseReleased" ? 0 : 1, clickCount: 1, ...extra });
const state = () => evalJs(`JSON.stringify({chat: document.querySelector('[aria-label=Conversation]').getBoundingClientRect().width, preview: document.querySelector('[aria-label="Preview and documents"]').getBoundingClientRect().width, stored: localStorage.getItem('builder:chatWidth')})`);
const handle = () => evalJs(`(()=>{const r=document.querySelector('[role=separator]').getBoundingClientRect();return [r.x+r.width/2, r.y+r.height/2]})()`);

await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: URL }); await sleep(5000);
await evalJs("localStorage.removeItem('builder:chatWidth')"); await send("Page.reload"); await sleep(5000);
console.log("default", await state());
let [x, y] = await handle();
await mouse("mousePressed", x, y);
for (let i = 1; i <= 20; i++) await mouse("mouseMoved", x + i * 20, y);   // +400 px, deep into the iframe area
await mouse("mouseReleased", x + 400, y); await sleep(300);
console.log("dragged_+400", await state()); await shot("wide");
[x, y] = await handle();
await mouse("mousePressed", x, y);
for (let i = 1; i <= 30; i++) await mouse("mouseMoved", x - i * 30, y);   // far left: clamps at the minimum
await mouse("mouseReleased", x - 900, y); await sleep(300);
console.log("dragged_-900", await state()); await shot("narrow");
[x, y] = await handle();
await mouse("mousePressed", x, y); for (let i = 1; i <= 20; i++) await mouse("mouseMoved", x + i * 100, y); await mouse("mouseReleased", x + 2000, y); await sleep(300);
console.log("dragged_+2000", await state());
await send("Page.reload"); await sleep(5000);
console.log("after_reload", await state());
[x, y] = await handle();
await mouse("mousePressed", x, y); await mouse("mouseReleased", x, y);
await mouse("mousePressed", x, y, { clickCount: 2 }); await mouse("mouseReleased", x, y, { clickCount: 2 }); await sleep(300);
console.log("double-click", await state());
ws.close(); chrome.kill();
