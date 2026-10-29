// End-to-end check of the review loop against the local server
// (claimguard.ui.serve), in headless Chrome over the DevTools protocol.
//
//   node tests/serve_e2e.mjs <chrome> <server address with its token>
//
// A reviewer decides two findings, saves them to the audit log and sees
// "In the audit log"; a refused save keeps its draft; a correction is
// rechecked as a new version. Prints one JSON object with what it observed;
// tests/test_ui_serve_e2e.py checks it. Nothing here asserts.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [chromePath, address] = process.argv.slice(2);
const origin = new URL(address).origin;
const out = { errors: [], offOrigin: [] };

const profile = mkdtempSync(join(tmpdir(), "cg-serve-e2e-"));
const chrome = spawn(chromePath, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1440,1000", "about:blank"]);
const finish = (extra) => {
  process.stdout.write(JSON.stringify({ ...out, ...extra }));
  chrome.kill();
  setTimeout(() => { try { rmSync(profile, { recursive: true, force: true }); } catch (_) { /* still held */ } process.exit(0); }, 500);
};

let ws;
try {
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = "";
    const timer = setTimeout(() => reject(new Error("no DevTools address within 60 s")), 60000);
    chrome.once("error", (e) => { clearTimeout(timer); reject(e); });
    chrome.stderr.on("data", (d) => {
      buf += d;
      const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(timer); resolve(m[1]); }
    });
  });
  ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", () => reject(new Error("could not connect to DevTools")), { once: true });
  });
} catch (e) {
  finish({ failure: `Chrome did not start: ${e.message}` });
}

let nextId = 0;
const pending = new Map();
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  } else if (msg.method === "Runtime.exceptionThrown") {
    out.errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
  } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
    out.errors.push(msg.params.args.map((a) => a.value ?? a.description).join(" "));
  } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
    // A refused save answers 4xx on purpose; the page shows it. Anything else is an error.
    if (!/status of 4\d\d/.test(msg.params.entry.text)) out.errors.push(msg.params.entry.text);
  } else if (msg.method === "Network.requestWillBeSent") {
    const url = msg.params.request.url;
    if (!url.startsWith(origin) && !/^(data|blob|about):/.test(url)) out.offOrigin.push(url);
  }
});
let sessionId;
function send(method, params = {}) {
  const id = ++nextId;
  ws.send(JSON.stringify({ id, method, params, sessionId }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function js(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Waits for an expression to be true, through reloads (the context changes).
async function until(expression, label, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { if (await js(expression)) return; } catch (_) { /* reloading */ }
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${label}`);
}
const ready = "document.readyState === 'complete' && typeof Server !== 'undefined' && !!document.querySelector('.content')";
const click = (scope, text) => `(() => { const b = [...${scope}.querySelectorAll('button')].find((x) => x.textContent.trim().startsWith(${JSON.stringify(text)}));
  if (!b) throw new Error('no button ' + ${JSON.stringify(text)}); b.click(); return true; })()`;

try {
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await send("Target.attachToTarget", { targetId, flatten: true }));
  for (const d of ["Runtime", "Log", "Network", "Page"]) await send(`${d}.enable`);

  // The printed address: the token moves to a cookie and leaves the address bar.
  await send("Page.navigate", { url: address });
  await until(ready, "the served page");
  out.addressAfterRedirect = await js("location.href");
  out.live = await js("Server.live");
  out.policy = await js("document.querySelector('meta[http-equiv=Content-Security-Policy]').content");

  // Decide two findings by the page's own controls.
  // The name is set as Settings sets it, then read on the next load.
  await js("localStorage.setItem('claimguard.reviewer', JSON.stringify('Reviewer 01')); location.hash = '#/claims/CG-785C09BD9CC8?finding=R003'; true");
  await send("Page.reload");
  await until(`${ready} && !!document.querySelector('article[id^=finding-]')`, "the claim");
  for (let i = 0; i < 2; i++) {
    await js(click("document.querySelector('article[id^=finding-]')", "Confirm issue"));
    await js(`(() => { const t = document.querySelector('article[id^=finding-] textarea'); t.value = 'Seen in the source record.';
      t.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
    await js(click("document.querySelector('article[id^=finding-]')", "Save draft"));
  }
  out.draftsBefore = await js("State.drafts.length");
  out.saveLabel = await js("[...document.querySelectorAll('button')].map((b) => b.textContent.trim()).find((t) => t.startsWith('Save to the audit log')) || null");

  // Save them to the audit log: the page reloads and says so.
  await js(`window.__old = true; ${click("document", "Save to the audit log")}`);
  await until(`${ready} && !window.__old && Server.notice !== null`, "the reload after saving");
  out.saved = await js(`({ notice: Server.notice.title, text: Server.notice.text, drafts: State.drafts.length,
    inLog: [...document.querySelectorAll('.callout__title')].some((e) => e.textContent === 'In the audit log') })`);

  // A refused save keeps the draft and lists the problem.
  await js(`(() => { const d = Object.assign({}, RECORDED[RECORDED.length - 1], { rule_id: 'R001', created_at: new Date().toISOString() });
    State.drafts = [d]; State.save(); location.hash = '#/queue'; return true; })()`);
  await until(`[...document.querySelectorAll('button')].some((b) => b.textContent.trim().startsWith('Save to the audit log'))`, "the queue banner");
  await js(click("document", "Save to the audit log"));
  await until("!!document.querySelector('.callout.tone-fail[role=alert]')", "the refusal");
  out.refused = await js(`({ title: document.querySelector('.callout.tone-fail[role=alert] .callout__title').textContent,
    problems: [...document.querySelectorAll('.callout.tone-fail[role=alert] li')].map((e) => e.textContent), drafts: State.drafts.length,
    stored: JSON.parse(localStorage.getItem('claimguard.drafts.' + RUN_ID)).length })`);
  await js("State.drafts = []; State.save(); true");

  // A correction, rechecked by the server as version 2.
  await js("location.hash = '#/claims/CG-B39790AC3604'; true");
  await until("!!document.getElementById('fix-field')", "the correction builder");
  out.correctionButton = await js("[...document.querySelectorAll('button')].map((b) => b.textContent.trim()).find((t) => t.startsWith('Recheck')) || null");
  await js(`(() => { document.getElementById('fix-field').value = '/lines/0/authorization_id';
    document.getElementById('fix-value').value = 'AUTH-CG-B39790AC3604-1'; return true; })()`);
  await js(click("document", "Add change"));
  await js(`(() => { const t = document.getElementById('fix-reason'); t.value = 'Authorization added from the source record.';
    t.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  await js(`window.__old = true; ${click("document", "Recheck as a new version")}`);
  await until(`${ready} && !window.__old && Server.notice !== null`, "the reload after the correction");
  out.corrected = await js(`({ notice: Server.notice.title, text: Server.notice.text,
    deciding: [...document.querySelectorAll('.callout__title')].map((e) => e.textContent).find((t) => t.startsWith('Deciding on version')) || null })`);
  finish();
} catch (e) {
  finish({ failure: e.message });
}
