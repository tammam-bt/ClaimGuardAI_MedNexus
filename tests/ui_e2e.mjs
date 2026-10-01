// End-to-end check of the review interface in headless Chrome, driven over
// the DevTools protocol with Node's built-in WebSocket (Node 22+).
//
//   node tests/ui_e2e.mjs <chrome> <page.html> <hostile-page.html>
//
// Prints one JSON object with what it observed; tests/test_ui_e2e.py checks
// it. Nothing here asserts: the Python test does.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [chromePath, pagePath, hostilePath] = process.argv.slice(2);
const profile = mkdtempSync(join(tmpdir(), "cg-e2e-"));
const chrome = spawn(chromePath, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1440,1000", "about:blank"]);

const wsUrl = await new Promise((resolve, reject) => {
  let buf = "";
  const timer = setTimeout(() => reject(new Error("Chrome did not start")), 20000);
  chrome.stderr.on("data", (d) => {
    buf += d;
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) { clearTimeout(timer); resolve(m[1]); }
  });
});

const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let nextId = 0;
const pending = new Map();
const errors = [];
const network = [];
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  } else if (msg.method === "Runtime.exceptionThrown") {
    errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
  } else if (msg.method === "Network.requestWillBeSent") {
    const url = msg.params.request.url;
    if (!/^(file|data|blob|about):/.test(url)) network.push(url);
  } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
    errors.push(msg.params.args.map((a) => a.value ?? a.description).join(" "));
  }
});
function send(method, params = {}, sessionId) {
  const id = ++nextId;
  ws.send(JSON.stringify({ id, method, params, sessionId }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
const page = (method, params) => send(method, params, sessionId);
await page("Runtime.enable");
await page("Page.enable");
await page("Network.enable");

// Accessibility problems on the current page, as short descriptions.
const A11Y = `(() => {
  const problems = [];
  const name = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim();
  for (const el of document.querySelectorAll('button, a[href], [role=tab]')) if (!name(el)) problems.push('unnamed ' + el.tagName + ' ' + el.className);
  for (const el of document.querySelectorAll('input, select, textarea')) {
    const labelled = el.getAttribute('aria-label') || el.closest('label') || (el.id && document.querySelector('label[for="' + el.id + '"]'));
    if (!labelled) problems.push('unlabelled ' + el.tagName + ' ' + (el.id || el.className));
  }
  for (const el of document.querySelectorAll('[tabindex]')) if (Number(el.getAttribute('tabindex')) > 0) problems.push('positive tabindex');
  const ids = [...document.querySelectorAll('[id]')].map(e => e.id).filter(id => !id.startsWith('i-'));
  const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
  if (dup.length) problems.push('duplicate ids ' + [...new Set(dup)].join(','));
  if (!document.documentElement.lang) problems.push('no lang');
  if (document.querySelectorAll('h1').length !== 1) problems.push(document.querySelectorAll('h1').length + ' h1');
  return problems;
})()`;

async function evaluate(expression) {
  const r = await page("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`${expression.slice(0, 80)}: ${r.exceptionDetails.exception?.description}`);
  return r.result.value;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(expression, ms = 15000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(`!!(${expression})`).catch(() => false)) return true;
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${expression}`);
}
// Always a real load: through about:blank, because navigating to the same
// file with another #hash only changes the hash and reloads nothing.
async function open(file, hash) {
  await page("Page.navigate", { url: "about:blank" });
  await sleep(100);
  await page("Page.navigate", { url: pathToFileURL(file).href + hash });
  await waitFor("document.querySelector('.content') && document.querySelector('.content').children.length");
}
async function goTo(hash) {
  await evaluate(`location.hash = ${JSON.stringify(hash)}`);
  await sleep(150);
  await waitFor("document.querySelector('.content').children.length");
}
const text = (sel) => evaluate(`(document.querySelector(${JSON.stringify(sel)}) || {}).textContent || null`);

const out = { errors, network };
try {
  // ---- every page draws
  await open(pagePath, "#/dashboard");
  out.pages = {};
  for (const key of ["dashboard", "queue", "claims", "audit", "rules", "evaluation", "settings", "components"]) {
    await goTo(`#/${key}`);
    out.pages[key] = {
      a11y: await evaluate(A11Y),
      title: await text(".topbar h1"),
      current: await evaluate("(document.querySelector('.nav__item[aria-current=page] .nav__label') || {}).textContent || null"),
      crashed: await evaluate("document.querySelector('.content').textContent.includes('could not be drawn')"),
    };
  }
  out.sidebarSame = await evaluate("document.querySelectorAll('.nav__item').length");

  // ---- keyboard: the skip link is the first stop and lands on the content
  await open(pagePath, "#/dashboard");  // a real reload: Tab starts from the top
  await page("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
  await page("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
  out.keyboard = { firstStop: await evaluate("document.activeElement.textContent") };
  await evaluate("document.activeElement.click()");
  out.keyboard.afterSkip = await evaluate("document.activeElement.id");

  // ---- 1280 px: no page scrolls sideways
  await page("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  out.narrow = {};
  for (const key of ["dashboard", "queue", "claims", "claims/CG-785C09BD9CC8", "audit", "rules", "rules/R013", "evaluation", "settings"]) {
    await goTo(`#/${key}`);
    out.narrow[key] = await evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth");
  }
  await page("Emulation.clearDeviceMetricsOverride");
  await goTo("#/dashboard");
  out.dashboard = { lifecycle: await text(".lifecycle"), stats: await text(".grid--4"), rejected: await text("#sec-rejected"),
    page: await text(".content"), sidebar: await text(".sidebar") };

  // ---- audit: the role decides which events show
  await goTo("#/audit");
  out.audit = { reviewer: { count: await text(".filters__count"), page: await text(".content") } };
  await evaluate(`(() => { const s = document.querySelector('.topbar select'); s.value = 'admin'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  await sleep(200);
  out.audit.admin = { count: await text(".filters__count"), types: await evaluate("[...document.querySelectorAll('.table tbody tr')].map(r => r.children[2].textContent)") };
  await evaluate(`(() => { const s = document.querySelector('.topbar select'); s.value = 'reviewer'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  await sleep(200);

  // ---- evaluation
  await goTo("#/evaluation");
  out.evaluation = { stats: await text(".grid--4"), page: await text(".content") };

  // ---- rules
  await goTo("#/rules");
  out.rules = { rows: await evaluate("[...document.querySelectorAll('.table tbody tr')].map(r => r.children[0].textContent)") };
  await goTo("#/rules/R013");
  out.rules.r013 = {
    page: await text(".content"),
    filters: await evaluate("[...document.querySelectorAll('.filters .field')].map(f => f.firstChild.textContent)"),
    diagonal: await evaluate("[...document.querySelectorAll('.matrix td.tone-pass')].map(td => td.textContent)"),
    offDiagonal: await evaluate("document.querySelectorAll('.matrix td.tone-fail').length"),
  };

  // ---- the queue before any decision
  await goTo("#/queue");
  out.queueBefore = {
    count: await text(".filters__count"),
    firstRoutes: await evaluate("[...document.querySelectorAll('.table tbody tr')].slice(0, 3).map(r => r.children[1].textContent)"),
  };
  await evaluate("document.querySelector('.table tbody tr').click()");
  await sleep(200);
  out.queueRowOpens = await evaluate("location.hash");

  // ---- the decision flow on a claim with two findings
  const cid = "CG-785C09BD9CC8";
  await goTo(`#/claims/${cid}`);
  out.queueCountBefore = await text(".nav__count");
  out.headBefore = await text(".claim-head__title");
  out.claimPage = await text(".content");
  out.sidebarUserBefore = await text(".sidebar__user");
  out.saveDisabledWithoutName = await evaluate("[...document.querySelectorAll('#finding-R003 button')].find(b => b.textContent.includes('Save')).disabled");

  const decide = async (rule, actionLabel, reason) => {
    await evaluate(`(() => {
      const f = document.querySelector('#finding-${rule}');
      [...f.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(actionLabel)}).click();
    })()`);
    await evaluate(`(() => {
      const t = document.querySelector('#reason-${rule}');
      t.value = ${JSON.stringify(reason)};
      t.dispatchEvent(new Event('input', { bubbles: true }));
      [...document.querySelectorAll('#finding-${rule} button')].find(b => b.textContent.includes('Save') || b.textContent.includes('Replace')).click();
    })()`);
  };

  await evaluate(`(() => { const i = document.querySelector('#reviewer-name'); i.value = 'Reviewer 01'; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await decide("R003", "Dismiss with reason", "Coverage extension confirmed by the payer.");
  out.afterOne = { head: await text(".claim-head__title"), lifecycle: await text(".lifecycle"), count: await text(".nav__count") };
  await decide("R004", "Dismiss with reason", "Member record corrected upstream.");
  out.afterTwo = { head: await text(".claim-head__title"), count: await text(".nav__count") };
  out.drafts = await evaluate(`JSON.parse(localStorage.getItem('claimguard.drafts.' + JSON.parse(document.getElementById('claimguard-data').textContent).run.run_id))`);
  out.reviewerShown = await text(".sidebar__user-name");
  await goTo("#/queue");
  out.queueAfter = { count: await text(".filters__count"), drafts: await text(".grid--4 .card:nth-child(4) .stat__value") };
  await goTo("#/queue?show=all");
  out.queueAll = await text(".filters__count");
  await goTo(`#/claims/${cid}`);

  // Replacing a decision keeps one draft per finding.
  await decide("R004", "Request information", "Need the member card.");
  out.afterReplace = { head: await text(".claim-head__title"), drafts: await evaluate(`JSON.parse(localStorage.getItem('claimguard.drafts.' + JSON.parse(document.getElementById('claimguard-data').textContent).run.run_id)).length`) };

  // ---- settings: the name is the same everywhere; drafts can be discarded
  await goTo("#/settings");
  out.settings = {
    name: await evaluate("document.querySelector('#settings-name').value"),
    stats: await text(".grid--4"),
    rbacRows: await evaluate("[...document.querySelectorAll('.table tbody tr')].map(r => [...r.children].map(c => c.textContent))"),
    page: await text(".content"),
  };
  await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent.includes('Discard all drafts')).click()");
  await sleep(100);
  out.settings.confirmShown = await evaluate("!!([...document.querySelectorAll('button')].find(b => b.textContent.includes('Yes, discard them')))");
  await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent.includes('Keep them')).click()");
  await sleep(100);
  out.settings.keptDrafts = await evaluate(`JSON.parse(localStorage.getItem('claimguard.drafts.' + JSON.parse(document.getElementById('claimguard-data').textContent).run.run_id)).length`);
  await goTo(`#/claims/${cid}`);

  // The stage survives a reload (drafts are kept in this browser).
  await open(pagePath, `#/claims/${cid}`);
  out.afterReload = await text(".claim-head__title");
  out.reloadedFresh = await evaluate("performance.getEntriesByType('navigation')[0].type");

  // A flagged claim shows the flag and keeps its text inert.
  await goTo("#/claims/CG-116C84D4774D");
  out.flagged = { callout: await text("#sec-flag"), explanation: await text("#sec-findings") };

  // List filters reach the URL.
  await goTo("#/claims?route=REVIEW");
  out.filtered = { count: await text(".filters__count"), hash: await evaluate("location.hash") };

  // ---- hostile claim text never runs
  await open(hostilePath, "#/claims");
  const hostileId = await evaluate("JSON.parse(document.getElementById('claimguard-data').textContent).claims[0].claim.claim_id");
  await goTo(`#/claims/${hostileId}`);
  await evaluate("document.querySelectorAll('details').forEach(d => d.open = true)");
  await sleep(300);
  out.hostile = {
    pwned: await evaluate("window.__pwned === 1"),
    injectedImages: await evaluate("document.querySelectorAll('.content img').length"),
    shownAsText: await evaluate("document.querySelector('.content').textContent.includes('window.__pwned=1')"),
  };
  await goTo("#/evaluation");
  out.hostile.mismatchRows = await evaluate("[...document.querySelectorAll('.card')].find(c => c.textContent.includes('Disagreements')).querySelectorAll('tbody tr').length");
} catch (e) {
  out.failure = String(e && e.stack || e);
} finally {
  process.stdout.write(JSON.stringify(out));
  ws.close();
  chrome.kill();
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) { /* Chrome may still hold files */ }
  process.exit(0);
}
