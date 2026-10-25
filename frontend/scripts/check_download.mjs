// M10 "Download code" check (run by backend/scripts/verify_m10.py), real clicks in headless Chrome over the DevTools
// protocol on a builder page:
//  1. folder mode: the native folder picker cannot be automated, so window.showDirectoryPicker is replaced by the
//     browser's Origin Private File System root, which is the same FileSystemDirectoryHandle API. Click the button,
//     then list every file written (path + size) under the project subfolder;
//  2. zip mode: without showDirectoryPicker (Safari / Firefox), the click downloads <folder>.zip into a temp folder.
// Prints "folder <json>" and "zip <json>".
// Usage: node frontend/scripts/check_download.mjs http://localhost:3001/c/<thread_id>
import { spawn } from "node:child_process";
import { mkdtempSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const URL = process.argv[2];
const profile = mkdtempSync(join(tmpdir(), "builder-download-check-"));
const downloads = mkdtempSync(join(tmpdir(), "builder-downloads-"));
const chrome = spawn(CH, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9334", "--window-size=1440,900", `--user-data-dir=${profile}`, "about:blank"]);
let targets;
for (let i = 0; i < 40 && !targets; i++) {
  await new Promise((r) => setTimeout(r, 250));
  try { targets = await (await fetch("http://127.0.0.1:9334/json")).json(); } catch {}
}
const pageTarget = targets.find((t) => t.type === "page");
const browserWs = new WebSocket((await (await fetch("http://127.0.0.1:9334/json/version")).json()).webSocketDebuggerUrl);
const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
await Promise.all([new Promise((r) => (ws.onopen = r)), new Promise((r) => (browserWs.onopen = r))]);
let id = 0;
const pending = new Map();
for (const sock of [ws, browserWs]) sock.onmessage = (m) => { const d = JSON.parse(m.data); if (pending.has(d.id)) { pending.get(d.id)(d.result ?? d.error); pending.delete(d.id); } };
const send = (method, params = {}, sock = ws) => new Promise((r) => { pending.set(++id, r); sock.send(JSON.stringify({ id, method, params })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result.value;
const click = async () => {
  const [x, y] = await evalJs(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Download code'));const r=b.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()`);
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 });
};

await send("Page.enable");
await send("Runtime.enable");
await send("Page.navigate", { url: URL });
await sleep(6000);

// 1. folder mode, into the private file system
await evalJs(`window.showDirectoryPicker = async () => navigator.storage.getDirectory(); true`);
await click();
let status = "";
for (let i = 0; i < 40 && !status.includes("Saved"); i++) { await sleep(250); status = await evalJs(`document.querySelector('[role=status]')?.textContent ?? ''`); }
const tree = await evalJs(`(async () => {
  const root = await navigator.storage.getDirectory(); const out = [];
  async function walk(dir, prefix) { for await (const [name, h] of dir.entries()) {
    if (h.kind === 'directory') await walk(h, prefix + name + '/'); else out.push([prefix + name, (await h.getFile()).size]); } }
  await walk(root, ''); return out; })()`);
console.log("folder " + JSON.stringify({ status, files: tree }));

// 2. zip mode (no folder picker)
await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads }, browserWs);
await evalJs(`delete window.showDirectoryPicker; window.showDirectoryPicker = undefined; true`);
await click();
let zips = [];
for (let i = 0; i < 40 && zips.length === 0; i++) { await sleep(250); zips = readdirSync(downloads).filter((f) => f.endsWith(".zip")); }
console.log("zip " + JSON.stringify({ files: zips.map((f) => ({ name: f, path: join(downloads, f), size: statSync(join(downloads, f)).size })) }));
ws.close();
browserWs.close();
chrome.kill();
