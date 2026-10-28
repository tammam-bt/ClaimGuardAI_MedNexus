// End-to-end check of the review interface in headless Chrome, driven over
// the DevTools protocol with Node's built-in WebSocket (Node 22+).
//
//   node tests/ui_e2e.mjs <chrome> <page.html> <hostile-page.html>
//
// Prints one JSON object with what it observed; tests/test_ui_e2e.py checks
// it. Nothing here asserts: the Python test does.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [chromePath, pagePath, hostilePath] = process.argv.slice(2);

// Start Chrome and connect to it. A busy CI runner can be slow to start a
// browser, so this waits up to a minute and tries twice. If Chrome still does
// not start, the result says so instead of being empty.
async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "cg-e2e-"));
  const chrome = spawn(chromePath, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1440,1000", "about:blank"]);
  try {
    const wsUrl = await new Promise((resolve, reject) => {
      let buf = "";
      const timer = setTimeout(() => reject(new Error("no DevTools address within 60 s")), 60000);
      chrome.once("error", (e) => { clearTimeout(timer); reject(e); });
      chrome.once("exit", (code) => { clearTimeout(timer); reject(new Error(`Chrome exited with code ${code}`)); });
      chrome.stderr.on("data", (d) => {
        buf += d;
        const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
        if (m) { clearTimeout(timer); resolve(m[1]); }
      });
    });
    const ws = new WebSocket(wsUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve, { once: true });
      ws.addEventListener("error", () => reject(new Error("could not connect to DevTools")), { once: true });
    });
    return { chrome, ws, profile };
  } catch (e) {
    chrome.kill();
    try { rmSync(profile, { recursive: true, force: true }); } catch (_) { /* Chrome may still hold files */ }
    throw e;
  }
}

let chrome, ws, profile;
for (let attempt = 1; !ws; attempt++) {
  try {
    ({ chrome, ws, profile } = await launch());
  } catch (e) {
    if (attempt === 2) {
      process.stdout.write(JSON.stringify({ failure: `Chrome did not start: ${e.message}` }));
      process.exit(0);
    }
  }
}

let nextId = 0;
const pending = new Map();
const errors = [];
const network = [];
const downloaded = [];  // guids of completed downloads
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
  } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
    errors.push(msg.params.entry.text);  // includes every Content-Security-Policy refusal
  } else if (msg.method === "Browser.downloadProgress" && msg.params.state === "completed") {
    downloaded.push(msg.params.guid);
  }
});
function send(method, params = {}, sessionId) {
  const id = ++nextId;
  ws.send(JSON.stringify({ id, method, params, sessionId }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

let sessionId;  // set at the start of the run below, inside its try
const page = (method, params) => send(method, params, sessionId);

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

// Real key presses and typing, for the keyboard-only flow.
const KEYS = { Tab: ["Tab", 9], Enter: ["Enter", 13, "\r"], " ": ["Space", 32, " "], j: ["KeyJ", 74, "j"], k: ["KeyK", 75, "k"],
  End: ["End", 35] };
async function press(key, modifiers = 0) {
  const [code, vk, chars] = KEYS[key];
  await page("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: vk, modifiers, text: chars });
  await page("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: vk, modifiers });
  await sleep(60);
}
const typeText = (t) => page("Input.insertText", { text: t });
// Tab until the focused element matches; returns the number of presses.
async function tabUntil(expression, max = 80) {
  for (let n = 1; n <= max; n++) {
    await press("Tab");
    if (await evaluate(`(() => { const el = document.activeElement; return !!(${expression}); })()`)) return n;
  }
  throw new Error(`Tab never reached ${expression}`);
}
const focused = () => evaluate("(document.activeElement.id || document.activeElement.textContent || '').trim()");
const selectedRule = () => evaluate("(document.querySelector('.ws-list [aria-selected=true]') || {}).dataset?.rule || null");

const out = { errors, network };
try {
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await send("Target.attachToTarget", { targetId, flatten: true }));
  await page("Runtime.enable");
  await page("Page.enable");
  await page("Network.enable");
  await page("Log.enable");

  // ---- every page draws
  await open(pagePath, "#/dashboard");
  out.pages = {};
  for (const key of ["dashboard", "queue", "claims", "claims/CG-785C09BD9CC8", "audit", "rules", "evaluation", "settings", "components"]) {
    await goTo(`#/${key}`);
    out.pages[key] = {
      a11y: await evaluate(A11Y),
      title: await text(".topbar h1"),
      current: await evaluate("(document.querySelector('.nav__item[aria-current=page] .nav__label') || {}).textContent || null"),
      crashed: await evaluate("document.querySelector('.content').textContent.includes('could not be drawn')"),
    };
  }
  // The nav is the same on every page; a reviewer's is shorter, the rest under "More".
  const NAV = "[...document.querySelectorAll('.nav > a.nav__item')].map(a => a.querySelector('.nav__label').textContent)";
  const MORE = "[...document.querySelectorAll('.nav__more a.nav__item')].map(a => a.querySelector('.nav__label').textContent)";
  out.sidebarSame = { reviewer: { main: await evaluate(NAV), more: await evaluate(MORE) } };
  await goTo("#/audit");
  out.sidebarSame.moreOpenOnItsPage = await evaluate("document.querySelector('.nav__more').open");

  // An address without a page opens the reviewer's home: the Review Queue.
  await page("Page.navigate", { url: "about:blank" });
  await sleep(100);
  await page("Page.navigate", { url: pathToFileURL(pagePath).href });
  await waitFor("document.querySelector('.content') && document.querySelector('.content').children.length");
  out.home = { title: await text(".topbar h1"), current: await evaluate("document.querySelector('.nav__item[aria-current=page] .nav__label').textContent") };

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
  out.sidebarSame.admin = await evaluate(NAV);
  out.sidebarSame.adminMore = await evaluate("document.querySelectorAll('.nav__more').length");
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
  out.queueRows = {
    drawn: await evaluate("document.querySelectorAll('.table tbody tr').length"),
    fingerprints: await evaluate("document.querySelectorAll('.table tbody tr .fingerprint').length"),
    foot: await text(".table-foot"),
    stops: await evaluate("document.querySelectorAll('.table tbody [tabindex=\"0\"]').length"),
    next: await text(".next-claim"),
  };
  // Keyboard: the table is one stop; j / k move, Tab leaves, Enter opens.
  await evaluate("document.getElementById('content').focus()");
  out.queueKb = { tabsToTable: await tabUntil("el.classList.contains('row-link')") };
  out.queueKb.first = await evaluate("document.activeElement.textContent.slice(0, 15)");
  await press("j");
  await press("j");
  out.queueKb.afterJJ = await evaluate("[...document.querySelectorAll('.row-link')].indexOf(document.activeElement)");
  await press("k");
  out.queueKb.afterK = await evaluate("[...document.querySelectorAll('.row-link')].indexOf(document.activeElement)");
  await press("End");
  out.queueKb.afterEnd = await evaluate("[...document.querySelectorAll('.row-link')].indexOf(document.activeElement)");
  await press("Tab");
  out.queueKb.afterTab = await evaluate("document.activeElement.classList.contains('row-link') ? 'row' : document.activeElement.textContent.trim()");
  await evaluate("[...document.querySelectorAll('.table-foot button')].find(b => b.textContent.startsWith('Show')).click()");
  await sleep(100);
  out.queueKb.afterMore = { drawn: await evaluate("document.querySelectorAll('.table tbody tr').length"),
    focused: await evaluate("[...document.querySelectorAll('.row-link')].indexOf(document.activeElement)") };
  await evaluate("document.querySelector('.row-link').focus()");
  await press("Enter");
  await sleep(200);
  out.queueKb.enterOpens = await evaluate("location.hash");
  await goTo("#/queue");
  await evaluate("document.querySelector('.table tbody tr').click()");
  await sleep(200);
  out.queueRowOpens = await evaluate("location.hash");
  out.backLink = await evaluate("(() => { const a = document.querySelector('.claim-head__title a'); return { text: a.textContent, href: a.getAttribute('href') }; })()");

  // ---- the decision flow on a claim with two findings
  const cid = "CG-785C09BD9CC8";
  await goTo(`#/claims/${cid}`);
  out.queueCountBefore = await text(".nav__count");
  out.headBefore = await text(".claim-head__title");
  out.claimPage = await text(".content");
  out.sidebarUserBefore = await text(".sidebar__user");
  out.saveDisabledWithoutName = await evaluate("[...document.querySelectorAll('#finding-R003 button')].find(b => b.textContent.includes('Save')).disabled");

  // Keyboard only, from the top of the content (where the skip link lands):
  // Tab to the findings list, j/k to move, Enter to open, Tab to an action,
  // Space to press it, type the reason, Tab to Save, Enter; Dismiss asks once
  // more, with the focus on "Yes, dismiss".
  out.kb = {};
  await evaluate("document.getElementById('content').focus()");
  out.kb.tabsToList = await tabUntil("el.getAttribute('role') === 'option'");
  out.kb.firstOption = await evaluate("document.activeElement.dataset.rule");
  await press("j");
  out.kb.afterJ = { selected: await selectedRule(), focused: await focused() };
  await press("k");
  out.kb.afterK = await selectedRule();
  const decide = async (rule, actionLabel, reason, name) => {
    for (let n = 0; n < 20 && (await selectedRule()) !== rule; n++) await press("j");
    await evaluate(`document.getElementById('opt-${rule}').focus()`);
    await press("Enter");
    const opened = await focused();
    const toAction = await tabUntil(`el.textContent.trim() === ${JSON.stringify(actionLabel)}`);
    await press(" ");
    await tabUntil(`el.id === 'reason-${rule}'`);
    await typeText(reason);
    if (name) { await tabUntil(`el.id === 'name-${rule}'`); await typeText(name); }
    await tabUntil("el.textContent.includes('Save draft') || el.textContent.includes('Replace the draft')");
    await press("Enter");
    const confirm = await focused();
    if (actionLabel === "Dismiss with reason") await press("Enter");
    await sleep(150);
    return { opened, toAction, confirm, nowSelected: await selectedRule(), nowFocused: await focused() };
  };

  out.kb.first = await decide("R003", "Dismiss with reason", "Coverage extension confirmed by the payer.", "Reviewer 01");
  out.afterOne = { head: await text(".claim-head__title"), lifecycle: await text(".lifecycle"), count: await text(".nav__count") };
  out.kb.second = await decide("R004", "Dismiss with reason", "Member record corrected upstream.");
  out.afterTwo = { head: await text(".claim-head__title"), count: await text(".nav__count"), next: await text("#next-claim") };
  out.drafts = await evaluate(`JSON.parse(localStorage.getItem('claimguard.drafts.' + JSON.parse(document.getElementById('claimguard-data').textContent).run.run_id))`);
  out.reviewerShown = await text(".sidebar__user-name");
  await goTo("#/queue");
  out.queueAfter = { count: await text(".filters__count"), drafts: await text(".content .callout__title") };
  await goTo("#/queue?show=all");
  out.queueAll = await text(".filters__count");
  await goTo(`#/claims/${cid}`);

  // Replacing a decision keeps one draft per finding.
  out.kb.replace = await decide("R004", "Request information", "Need the member card.");
  out.afterReplace = { head: await text(".claim-head__title"), drafts: await evaluate(`JSON.parse(localStorage.getItem('claimguard.drafts.' + JSON.parse(document.getElementById('claimguard-data').textContent).run.run_id)).length`) };

  // ---- the decisions download is a real file, under the page's Content-Security-Policy
  const downloadDir = join(profile, "downloads");
  await send("Browser.setDownloadBehavior", { behavior: "allowAndName", downloadPath: downloadDir, eventsEnabled: true });
  await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent.startsWith('Download decisions')).click()");
  for (let waited = 0; !downloaded.length && waited < 10000; waited += 100) await sleep(100);
  out.download = downloaded.length
    ? { completed: true, lines: readFileSync(join(downloadDir, downloaded[0]), "utf-8").split(/\r?\n/)
      .filter(Boolean).map((l) => JSON.parse(l)) }
    : { completed: false };

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
  // The sort reaches the URL too, and a link with it opens sorted.
  await evaluate("document.querySelector('th[data-key=total] button').click()");
  await sleep(100);
  out.filtered.sortedHash = await evaluate("location.hash");
  await goTo("#/claims?route=REVIEW&sort=-total");
  out.filtered.linkSort = await evaluate("document.querySelector('th[data-key=total]').getAttribute('aria-sort')");

  // ---- a browser that will not store the draft: the page says so and the
  // reason is not lost
  const other = await evaluate(`JSON.parse(document.getElementById('claimguard-data').textContent).claims
    .find((c) => c.route.reasons.length && !c.flag && c.claim.claim_id !== ${JSON.stringify(cid)}).claim.claim_id`);
  await goTo(`#/claims/${other}`);
  await evaluate("Storage.prototype.__setItem = Storage.prototype.setItem; Storage.prototype.setItem = function () { throw new DOMException('full', 'QuotaExceededError'); }");
  const failRule = await selectedRule();
  await evaluate(`(() => {
    const f = document.getElementById('finding-${failRule}');
    [...f.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Request information').click();
    const t = document.getElementById('reason-${failRule}');
    t.value = 'Kept although storage failed.';
    t.dispatchEvent(new Event('input', { bubbles: true }));
    [...f.querySelectorAll('button')].find((b) => b.textContent.includes('Save draft')).click();
  })()`);
  await sleep(150);
  out.storageFailure = {
    alert: await evaluate(`(document.querySelector('#finding-${failRule} [role=alert]') || {}).textContent || null`),
    kept: await evaluate(`document.querySelector('#finding-${failRule}').textContent.includes('Kept although storage failed.')`),
  };
  await evaluate("Storage.prototype.setItem = Storage.prototype.__setItem");

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
