// Measure the review page for the UI baseline (plan item P1) and its later
// comparison (P8): render time, screenshots at four widths, sideways
// overflow, and a keyboard walk of every page. Headless Chrome, driven over
// the DevTools protocol with Node's built-in WebSocket (Node 22+).
//
//   node scripts/ui_baseline.mjs <chrome> <page.html> <out-folder> [runs]
//
// Writes <out-folder>/baseline.json and <out-folder>/screens/*.png. Nothing
// here asserts: the numbers are read by a person and compared by hand.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [chromePath, pagePath, outDir, runsArg] = process.argv.slice(2);
const RUNS = Number(runsArg || 5);
const WIDTHS = [375, 768, 1280, 1440];
const CLAIM = "CG-785C09BD9CC8";  // a claim with findings, also used by the e2e test
const ROUTES = ["dashboard", "queue", "claims", `claims/${CLAIM}`, "audit", "rules", "rules/R013", "evaluation", "settings", "components"];
const MAX_SHOT_HEIGHT = 6000;  // the claims list is very tall; the top is enough to judge it
mkdirSync(join(outDir, "screens"), { recursive: true });

const profile = mkdtempSync(join(tmpdir(), "cg-baseline-"));
const chrome = spawn(chromePath, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1440,900", "about:blank"]);
const wsUrl = await new Promise((resolve, reject) => {
  let buf = "";
  const timer = setTimeout(() => reject(new Error("no DevTools address within 60 s")), 60000);
  chrome.stderr.on("data", (d) => {
    buf += d;
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) { clearTimeout(timer); resolve(m[1]); }
  });
});
const ws = new WebSocket(wsUrl);
await new Promise((resolve) => ws.addEventListener("open", resolve, { once: true }));

let nextId = 0;
const pending = new Map();
const errors = [];
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  } else if (msg.method === "Runtime.exceptionThrown") {
    errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
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
await page("Performance.enable");
// Chrome's counters add up over a tab's life, so each load is the difference.
const counters = async () => Object.fromEntries((await page("Performance.getMetrics")).metrics.map((x) => [x.name, x.value]));

async function evaluate(expression) {
  const r = await page("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`${expression.slice(0, 80)}: ${r.exceptionDetails.exception?.description}`);
  return r.result.value;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(expression, ms = 30000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await evaluate(`!!(${expression})`).catch(() => false)) return;
    await sleep(50);
  }
  throw new Error(`timed out waiting for ${expression}`);
}
const fileUrl = pathToFileURL(pagePath).href;
async function open(hash) {
  await page("Page.navigate", { url: "about:blank" });
  await sleep(100);
  await page("Page.navigate", { url: fileUrl + hash });
  await waitFor("document.readyState === 'complete' && document.querySelector('.content') && document.querySelector('.content').children.length");
}
// Route change inside the loaded page: the shell's hashchange listener was
// added first, so ours runs after it has drawn the page.
async function goTo(route) {
  return evaluate(`new Promise((resolve, reject) => {
    if (location.hash === ${JSON.stringify("#/" + route)}) { resolve({ drawn: 0, painted: 0 }); return; }
    setTimeout(() => reject(new Error('no hashchange')), 30000);
    const t0 = performance.now();
    addEventListener('hashchange', () => {
      const drawn = performance.now() - t0;
      requestAnimationFrame(() => setTimeout(() => resolve({ drawn, painted: performance.now() - t0 }), 0));
    }, { once: true });
    location.hash = ${JSON.stringify("#/" + route)};
  })`);
}
// Leave the route first, so that going to it redraws it.
const away = (route) => goTo(route === "settings" ? "components" : "settings");
const median = (xs) => { const s = xs.slice().sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
const round = (x) => Math.round(x * 10) / 10;

const out = { page: pagePath, bytes: statSync(pagePath).size, runs: RUNS, chrome: (await send("Browser.getVersion")).product, errors };

// ---- cold load: navigation start to first paint, scripts done, load
// The page draws itself in one inline script at the end of <body>, so the
// first frame after DOMContentLoaded is the first frame with content. Chrome
// records no first-contentful-paint for a headless target, so this is timed
// by a script DevTools adds to the page (the page's own CSP does not apply).
const cold = { firstFrame: [], domContentLoaded: [], load: [], scriptMs: [], layoutMs: [] };
await page("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await page("Page.addScriptToEvaluateOnNewDocument", { source:
  "addEventListener('DOMContentLoaded', () => requestAnimationFrame(() => setTimeout(() => { window.__cgPainted = performance.now(); }, 0)));" });
for (let i = 0; i < RUNS; i++) {
  await page("Page.navigate", { url: "about:blank" });
  await sleep(200);
  const before = await counters();
  await open("#/dashboard");
  await waitFor("window.__cgPainted");
  const t = await evaluate(`(() => {
    const n = performance.getEntriesByType('navigation')[0];
    return { painted: window.__cgPainted, dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd };
  })()`);
  const m = await counters();
  cold.firstFrame.push(t.painted); cold.domContentLoaded.push(t.dcl); cold.load.push(t.load);
  cold.scriptMs.push((m.ScriptDuration - before.ScriptDuration) * 1000);
  cold.layoutMs.push((m.LayoutDuration - before.LayoutDuration) * 1000);
}
out.cold = Object.fromEntries(Object.entries(cold).map(([k, xs]) => [k, { median: round(median(xs)), all: xs.map(round) }]));

// ---- each route, drawn inside the loaded page
out.routes = {};
for (const route of ROUTES) {
  const drawn = [], painted = [];
  for (let i = 0; i < RUNS; i++) {
    await away(route);
    const r = await goTo(route);
    drawn.push(r.drawn); painted.push(r.painted);
  }
  out.routes[route] = { drawnMedian: round(median(drawn)), paintedMedian: round(median(painted)),
    domNodes: await evaluate("document.getElementsByTagName('*').length") };
}

// ---- screenshots and sideways overflow at each width
out.overflow = {};
for (const width of WIDTHS) {
  await page("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 768 });
  out.overflow[width] = {};
  for (const route of ROUTES) {
    await away(route);
    await goTo(route);
    await sleep(150);
    const size = await evaluate(`({ w: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
      h: document.documentElement.scrollHeight,
      wide: [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1
        && !e.closest('.table-wrap, [class*=scroll]')).slice(0, 5).map((e) => e.tagName.toLowerCase() + '.' + String(e.className).split(' ')[0]) })`);
    out.overflow[width][route] = { sideways: size.w - size.cw, height: size.h, wide: size.wide };
    const height = Math.min(size.h, MAX_SHOT_HEIGHT);
    const shot = await page("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: Math.max(width, size.w), height, scale: 1 } });
    writeFileSync(join(outDir, "screens", `${route.replace(/\//g, "_")}@${width}.png`), Buffer.from(shot.data, "base64"));
  }
}

// ---- keyboard walk at 1440: Tab from the top, record each stop
await page("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
const STOP = `(() => {
  const e = document.activeElement;
  if (!e || e === document.body) return null;
  const r = e.getBoundingClientRect();
  const s = getComputedStyle(e);
  const name = (e.getAttribute('aria-label') || e.labels?.[0]?.textContent || e.textContent || e.getAttribute('title') || e.value || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
  const ring = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
    || (e.parentElement && e.parentElement.matches(':focus-within') && getComputedStyle(e.parentElement).outlineStyle !== 'none');
  return { tag: e.tagName.toLowerCase(), role: e.getAttribute('role'), cls: String(e.className).split(' ')[0], name,
    region: e.closest('aside') ? 'sidebar' : e.closest('header') ? 'topbar' : e.closest('main') ? 'main' : 'other',
    visible: r.width > 0 && r.height > 0, ring, top: Math.round(r.top + scrollY) };
})()`;
const LANDMARKS = `(() => {
  const count = (sel) => document.querySelectorAll(sel).length;
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((x) => Number(x.tagName[1]));
  const skips = headings.filter((lv, i) => i > 0 && lv > headings[i - 1] + 1).length;
  const unnamed = [...document.querySelectorAll('button, a[href], [role=tab], [role=button]')]
    .filter((el) => !(el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim()).length;
  const unlabelled = [...document.querySelectorAll('input, select, textarea')]
    .filter((el) => !(el.getAttribute('aria-label') || el.closest('label') || (el.id && document.querySelector('label[for="' + el.id + '"]')))).length;
  const clickableNotFocusable = [...document.querySelectorAll('[onclick], tr[class*=click], .clickable, [data-href]')]
    .filter((el) => el.tabIndex < 0).length;
  const tables = [...document.querySelectorAll('table')];
  return { banner: count('header, [role=banner]'), nav: count('nav, [role=navigation]'), main: count('main, [role=main]'),
    complementary: count('aside, [role=complementary]'), h1: count('h1'), headings: headings.join(''), headingSkips: skips,
    unnamedControls: unnamed, unlabelledFields: unlabelled, clickableNotFocusable,
    tablesWithoutCaption: tables.filter((t) => !t.querySelector('caption') && !t.getAttribute('aria-label') && !t.getAttribute('aria-labelledby')).length,
    liveRegions: count('[aria-live], [role=status], [role=alert]') };
})()`;
out.keyboard = {};
for (const route of ROUTES) {
  await open("#/" + route);
  const stops = [];
  for (let i = 0; i < 120; i++) {
    await page("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await page("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    const s = await evaluate(STOP);
    if (!s) break;
    if (stops.length && stops[0].name === s.name && stops[0].cls === s.cls && i > 3) break;  // wrapped round
    stops.push(s);
  }
  // DOM order versus visual order inside main: a stop placed higher on the page than the previous one
  const main = stops.filter((s) => s.region === "main");
  const backwards = main.filter((s, i) => i > 0 && s.top < main[i - 1].top - 4).length;
  out.keyboard[route] = { stops: stops.length, firstMain: stops.findIndex((s) => s.region === "main") + 1, backwards,
    firstDecision: stops.findIndex((s) => s.name === "Confirm issue") + 1,
    focusableRows: await evaluate("document.querySelectorAll('tr[tabindex]').length"),
    noRing: stops.filter((s) => !s.ring).map((s) => `${s.tag}.${s.cls} "${s.name}"`),
    hidden: stops.filter((s) => !s.visible).map((s) => `${s.tag}.${s.cls} "${s.name}"`),
    landmarks: await evaluate(LANDMARKS), first: stops.slice(0, 70).map((s) => `${s.region}: ${s.tag}${s.role ? "[" + s.role + "]" : ""} "${s.name}"`) };
}

writeFileSync(join(outDir, "baseline.json"), JSON.stringify(out, null, 2));
process.stdout.write(JSON.stringify({ bytes: out.bytes, cold: Object.fromEntries(Object.entries(out.cold).map(([k, v]) => [k, v.median])), errors }, null, 2) + "\n");
ws.close();
chrome.kill();
await sleep(300);
try { rmSync(profile, { recursive: true, force: true }); } catch (_) { /* Chrome may still hold files */ }
