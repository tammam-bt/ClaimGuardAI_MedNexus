"use strict";
// ClaimGuard interface: shared components, the shell and the router.
//
// Rules every page follows:
//   - build elements with h(); text always goes in as a text node, never as
//     HTML, because claim text is untrusted (doc 10: "The UI escapes source
//     text"). No HTML string is ever parsed into the page.
//   - use the components below; a page never styles an element itself.
//   - name icons, statuses, routes and actions only through Core's tables,
//     so a concept looks the same on every page.

// -------------------------------------------------------------------- data
const DATA = JSON.parse(document.getElementById("claimguard-data").textContent);
const RUN_ID = DATA.run ? DATA.run.run_id : "no-manifest";
const CLAIMS = DATA.claims;
const CLAIM_BY_ID = new Map(CLAIMS.map((c) => [c.claim.claim_id, c]));
const RULE_BY_ID = new Map(DATA.rules.map((r) => [r.rule_id, r]));

// ---------------------------------------------------------------- storage
// Per-viewer conveniences only (role, name, unsent decisions). It can be
// empty or unavailable; the app works without it.
const Store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(`claimguard.${key}`); return v === null ? fallback : JSON.parse(v); }
    catch (e) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`claimguard.${key}`, JSON.stringify(value)); } catch (e) { /* unavailable */ }
  },
};

const State = {
  role: Store.get("role", "reviewer") === "admin" ? "admin" : "reviewer",
  reviewer: String(Store.get("reviewer", "") || ""),
  drafts: (() => { const d = Store.get(`drafts.${RUN_ID}`, []); return Array.isArray(d) ? d : []; })(),
  listeners: [],
  save() {
    Store.set("role", this.role);
    Store.set("reviewer", this.reviewer);
    Store.set(`drafts.${RUN_ID}`, this.drafts);
    this.listeners.forEach((fn) => fn());
  },
  onChange(fn) { this.listeners.push(fn); },
};

// Review decisions already in the audit chain, then this viewer's drafts.
const RECORDED = DATA.audit
  ? DATA.audit.events.map((row) => row.event).filter((e) => e && e.event === "review_decision")
  : [];
function decisions() { return RECORDED.concat(State.drafts); }
function can(action) { return (DATA.rbac[State.role] || []).includes(action); }

// --------------------------------------------------------------- elements
function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "style") Object.assign(el.style, value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}
// Replace an element's children; empty values (null, false) are skipped,
// never written out as text.
function fill(el, ...children) { el.replaceChildren(); return append(el, children); }
function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}
const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, String(v));
  for (const c of children.flat(Infinity)) if (c) el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

// ------------------------------------------------------------------- icons
// The only way to draw an icon. A name missing from icons.svg is a bug: it
// is reported once in the console and drawn as nothing.
const MISSING_ICONS = new Set();
function icon(name, opts) {
  const o = opts || {};
  if (!document.getElementById(`i-${name}`) && !MISSING_ICONS.has(name)) {
    MISSING_ICONS.add(name);
    console.error(`icon "${name}" is not in icons.svg`);
  }
  const el = svg("svg", { class: `icon${o.size ? " icon--" + o.size : ""}`, "aria-hidden": o.label ? null : "true",
    role: o.label ? "img" : null, "aria-label": o.label || null, focusable: "false" },
  svg("use", { href: `#i-${name}` }));
  return el;
}

// ------------------------------------------------------------------ badges
function badge(text, opts) {
  const o = opts || {};
  return h("span", { class: `badge ${o.tone ? "tone-" + o.tone : ""} ${o.extra || ""}`.trim(), title: o.title },
    o.icon ? icon(o.icon) : null, text);
}
function statusBadge(status, opts) {
  const s = Core.STATUS[status];
  if (!s) return badge(String(status), { tone: "neutral" });
  return badge((opts && opts.short) ? s.short : s.label, { tone: s.tone, icon: s.icon, title: `${status}: ${s.help}` });
}
function routeBadge(route) {
  const r = Core.ROUTE[route];
  return badge(r.label, { tone: r.tone, icon: r.icon, extra: "badge--route", title: r.help });
}
// "High" in a Severity column; { long: true } adds the noun where no label
// says it is a severity (a finding's head).
function severityBadge(severity, opts) {
  const s = Core.SEVERITY[severity] || { label: String(severity) };
  return badge(opts && opts.long ? `${s.label} severity` : s.label,
    { extra: `badge--severity${severity === "high" ? " is-high" : ""}`, title: `${s.label} severity` });
}
function outcomeBadge(outcome) {
  const o = Core.OUTCOME[outcome];
  return badge(o.label, { tone: o.tone, icon: o.icon, title: o.help });
}
function sourceBadge(source) {
  const s = Core.SOURCE[source] || { label: String(source), icon: "info", tone: "neutral" };
  return badge(s.label, { tone: s.tone, icon: s.icon });
}
function methodBadge() { return badge("Deterministic", { tone: "neutral", icon: "cpu", title: "A fixed rule: no probability, no model." }); }

// ----------------------------------------------------------------- buttons
function button(opts) {
  const o = opts || {};
  const b = h("button", {
    type: "button",
    class: `btn btn--${o.variant || "secondary"}${o.iconOnly ? " btn--icon" : ""}`,
    onClick: o.onClick, title: o.title || (o.iconOnly ? o.label : null),
    "aria-label": o.iconOnly ? o.label : null,
    "aria-pressed": o.pressed === undefined ? null : String(!!o.pressed),
    disabled: o.disabled ? true : null,
  }, o.icon ? icon(o.icon) : null, o.iconOnly ? null : o.label);
  return b;
}
function linkButton(opts) {
  return h("a", { class: `btn btn--${opts.variant || "secondary"}`, href: opts.href },
    opts.icon ? icon(opts.icon) : null, opts.label);
}

// ------------------------------------------------------------------- cards
function card(opts) {
  const o = opts || {};
  return h("section", { class: "card", "aria-label": o.title || null },
    o.title ? h("div", { class: "card__head" },
      h("h3", { class: "card__title", text: o.title }),
      o.meta ? h("span", { class: "card__meta" }, o.meta) : null,
      o.actions || null) : null,
    h("div", { class: `card__body${o.flush ? " card__body--flush" : ""}` }, o.body));
}

// Stat card: icon, label, value, and where the number comes from. Always the
// same anatomy; no sparkline, because one run has no history to draw.
function statCard(opts) {
  const o = opts || {};
  const inner = [
    h("span", { class: `stat__icon tone-${o.tone || "info"}` }, icon(o.icon, { size: "lg" })),
    h("span", { class: "stat__body" },
      h("span", { class: "stat__label", text: o.label }),
      h("span", { class: "stat__value", text: o.value }),
      o.caption ? h("span", { class: "stat__caption", text: o.caption }) : null),
  ];
  return o.href ? h("a", { class: "card stat", href: o.href }, inner) : h("div", { class: "card stat" }, inner);
}
function statRow(cards) { return h("div", { class: "grid grid--4" }, cards); }

function pageHead(opts) {
  return h("div", { class: "page-head" },
    h("div", { class: "page-head__text" }, h("h2", { text: opts.title }), opts.text ? h("p", { text: opts.text }) : null),
    opts.actions ? h("div", { class: "row" }, opts.actions) : null);
}

function emptyState(opts) {
  return h("div", { class: "empty" }, icon(opts.icon || "info"),
    h("p", { class: "empty__title", text: opts.title }),
    opts.text ? h("p", { text: opts.text }) : null, opts.action || null);
}

function callout(opts) {
  return h("div", { class: `callout tone-${opts.tone || "info"}`, role: opts.role || null },
    icon(opts.icon || "info"),
    h("div", {}, opts.title ? h("p", { class: "callout__title", text: opts.title }) : null,
      opts.text ? h("p", {}, opts.text) : null, opts.body || null));
}

function kv(pairs) {
  return h("dl", { class: "kv" }, pairs.filter(Boolean).map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v === null || v === undefined ? "—" : v)]));
}

function bars(items) {
  const max = Math.max(1, ...items.map((i) => i.total || i.value));
  return h("div", { class: "bars" }, items.map((i) => h(i.href ? "a" : "div", { class: "bar", href: i.href || null, style: i.href ? { color: "inherit", textDecoration: "none" } : null },
    h("span", {}, i.label),
    h("span", { class: "bar__track", role: "img", "aria-label": `${i.label}: ${i.value}` },
      h("span", { class: `bar__fill fill-${i.tone}`, style: { width: `${(100 * i.value) / max}%` } })),
    h("span", { class: "bar__value", text: i.display || Core.number(i.value) }))));
}

// Result statuses as bars. "Not implemented" appears only when a check did
// not run: a row of zeros there is noise.
function statusBars(counts) {
  return Core.STATUS_ORDER.filter((s) => s !== "NOT_IMPLEMENTED" || counts[s] > 0).map((s) => ({
    label: Core.STATUS[s].label, value: counts[s],
    tone: { fail: "fail", unknown: "unknown", pass: "pass", neutral: "neutral" }[Core.STATUS[s].tone] }));
}

// ------------------------------------------------------------------- table
// columns: [{ key, label, num, sort: row => value, render: row => node }]
function table(opts) {
  const o = opts;
  let sortKey = o.sort ? o.sort.key : null;
  let sortDir = o.sort ? o.sort.dir : 1;
  const tbody = h("tbody");
  const wrap = h("div", { class: "table-wrap" });

  function rows() {
    const col = o.columns.find((c) => c.key === sortKey);
    if (!col || !col.sort) return o.rows;
    return o.rows.slice().sort((a, b) => {
      const x = col.sort(a), y = col.sort(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
  }
  function draw() {
    tbody.replaceChildren(...rows().map((row) => {
      const tr = h("tr", {
        class: o.onRowClick ? "is-clickable" : null,
        "aria-selected": o.selected && o.selected(row) ? "true" : null,
        tabindex: o.onRowClick ? "0" : null,
        onClick: o.onRowClick ? () => o.onRowClick(row) : null,
        onKeydown: o.onRowClick ? (e) => { if (e.key === "Enter") o.onRowClick(row); } : null,
      }, o.columns.map((c) => h("td", { class: c.num ? "num" : null }, c.render ? c.render(row) : row[c.key])));
      return tr;
    }));
    head.querySelectorAll("th").forEach((th) => {
      th.setAttribute("aria-sort", th.dataset.key === sortKey ? (sortDir === 1 ? "ascending" : "descending") : "none");
    });
  }
  const head = h("thead", {}, h("tr", {}, o.columns.map((c) => h("th", { class: c.num ? "num" : null, "data-key": c.key, scope: "col" },
    c.sort ? h("button", { type: "button", onClick: () => { sortDir = sortKey === c.key ? -sortDir : 1; sortKey = c.key; draw(); } },
      c.label, icon("sort", { size: "sm" })) : c.label))));
  if (!o.rows.length) return o.empty || emptyState({ icon: "search", title: "Nothing to show", text: "No row matches." });
  wrap.appendChild(h("table", { class: "table" }, h("caption", { class: "sr-only", text: o.caption || "" }), head, tbody));
  draw();
  return wrap;
}

// --------------------------------------------------------------- filters
// filters: [{ label, value, options: [[value, label]], onChange }]
function filterBar(filters, countText, extra) {
  return h("div", { class: "filters" },
    filters.map((f) => h("label", { class: "field" }, f.label,
      h("select", { class: "select", onChange: (e) => f.onChange(e.target.value) },
        f.options.map(([v, l]) => h("option", { value: v, selected: v === f.value ? true : null, text: l }))))),
    extra || null,
    countText ? h("span", { class: "filters__count", role: "status", text: countText }) : null);
}
function searchField(opts) {
  const input = h("input", { type: "search", placeholder: opts.placeholder, value: opts.value || "", "aria-label": opts.label,
    onInput: (e) => opts.onInput(e.target.value) });
  return h("label", { class: "search" }, icon("search", { size: "sm" }), input);
}

// ------------------------------------------------------------------ tabs
// tabs: [{ key, label, count, render }]; the active tab is kept per name.
function tabs(name, list, initial) {
  const panel = h("div", { role: "tabpanel" });
  let active = list.some((t) => t.key === initial) ? initial : list[0].key;
  const bar = h("div", { class: "tabs", role: "tablist" });
  function draw() {
    bar.replaceChildren(...list.map((t) => h("button", {
      type: "button", class: "tab", role: "tab", "aria-selected": String(t.key === active),
      onClick: () => { active = t.key; draw(); },
    }, t.label, t.count !== undefined ? h("span", { class: "tab__count", text: Core.number(t.count) }) : null)));
    panel.replaceChildren(list.find((t) => t.key === active).render());
  }
  draw();
  return h("div", { class: "stack" }, bar, panel);
}

// ----------------------------------------------------------- side panel
let panelState = null;
function openPanel(title, body) {
  closePanel();
  const opener = document.activeElement;
  const close = button({ label: "Close", icon: "x", iconOnly: true, variant: "ghost", onClick: closePanel });
  const backdrop = h("div", { class: "panel-backdrop", onClick: closePanel });
  const panel = h("aside", { class: "panel", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "panel__head" }, h("h2", { class: "panel__title", text: title }), close),
    h("div", { class: "panel__body" }, body));
  document.body.append(backdrop, panel);
  panelState = { backdrop, panel, opener };
  close.focus();
}
function closePanel() {
  if (!panelState) return;
  panelState.backdrop.remove();
  panelState.panel.remove();
  if (panelState.opener && panelState.opener.focus) panelState.opener.focus();
  panelState = null;
}
document.addEventListener("keydown", (e) => {
  if (!panelState) return;
  if (e.key === "Escape") { closePanel(); return; }
  if (e.key !== "Tab") return;
  // Keep focus inside the open panel (it is a modal dialog).
  const focusable = Array.from(panelState.panel.querySelectorAll(
    "a[href], button:not([disabled]), input, select, textarea, summary, [tabindex]:not([tabindex='-1'])"));
  if (!focusable.length) return;
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

// ------------------------------------------------------- domain components
function ruleName(ruleId) { const r = RULE_BY_ID.get(ruleId); return r ? r.title : ruleId; }

// The 15 checks of one claim, in rule order.
function checkGrid(results, opts) {
  const o = opts || {};
  return h("ul", { class: "checks", "aria-label": "All 15 checks" }, results.map((r) => {
    const s = Core.STATUS[r.status];
    const inner = [h("span", { class: "check__top" }, icon(s.icon, { size: "sm" }), h("span", { class: "check__id", text: r.rule_id })),
      h("span", { class: "check__name", text: ruleName(r.rule_id) })];
    const cls = `check tone-${s.tone}`;
    const title = `${r.rule_id} ${ruleName(r.rule_id)}: ${s.label}`;
    return h("li", {}, o.onPick
      ? h("button", { type: "button", class: cls, title, onClick: () => o.onPick(r), style: { width: "100%", cursor: "pointer", font: "inherit", textAlign: "left" } }, inner)
      : h("span", { class: cls, title }, inner));
  }));
}

// Evidence as the engine cited it: the field, named for a reviewer (the
// claim names lines and documents by their own IDs), and its value as plain
// text. A list or an object is source text: it stays boxed as data.
function evidenceTable(evidence, claim) {
  return h("table", { class: "evidence" },
    h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Field" }), h("th", { scope: "col", text: "Value" }))),
    h("tbody", {}, evidence.map((e) => h("tr", {}, h("td", { text: Core.fieldLabel(e.path, claim) }),
      h("td", {}, e.value !== null && typeof e.value === "object"
        ? h("pre", { class: "untrusted", text: Core.plain(e.value) })
        : value(e.value))))));
}

// The life cycle of one claim (Core.lifecycle) or of the run (same look).
function lifecycleStrip(stages, opts) {
  const o = opts || {};
  return h("ol", { class: "lifecycle", "aria-label": o.label || "Life cycle" }, stages.map((s, i) => {
    // The stage's own icon, except a failed or warning stage, which shows the
    // FAIL or warning icon (the same concepts as everywhere else).
    const glyph = s.state === "fail" ? "x-circle" : s.state === "warn" ? "alert-triangle" : s.icon;
    const inner = [
      h("span", { class: "stage__top" }, h("span", { class: "stage__dot" }, icon(glyph)),
        `${i + 1}. ${s.label}`),
      h("span", { class: "stage__summary", text: s.summary }),
    ];
    const cls = `stage is-${s.state}`;
    return h("li", {}, o.onPick
      ? h("button", { type: "button", class: cls, style: { width: "100%" }, onClick: () => o.onPick(s) }, inner)
      : h("div", { class: cls }, inner));
  }));
}

// ------------------------------------------------------ confusion matrix
// Expected status (rows) against predicted status (columns), as
// claimguard.evaluation.confusion reports it. A table, so it reads cell by
// cell with a screen reader; agreement is green, disagreement red.
const EXPECTED = ["PASS", "FAIL", "UNABLE_TO_ASSESS", "NOT_APPLICABLE"];
const PREDICTED = EXPECTED.concat(["NOT_IMPLEMENTED"]);
function confusionMatrix(cells, caption) {
  const at = new Map(cells.map((c) => [`${c.expected}|${c.predicted}`, c.count]));
  // "Not implemented" is a column only when some check did not run.
  const predicted = PREDICTED.filter((p) => p !== "NOT_IMPLEMENTED" || cells.some((c) => c.predicted === p && c.count > 0));
  return h("div", { class: "table-wrap" }, h("table", { class: "table matrix" },
    h("caption", { class: "sr-only", text: caption || "Expected status against predicted status" }),
    h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Expected ↓ · Predicted →" }),
      predicted.map((p) => h("th", { scope: "col", class: "num", text: Core.STATUS[p].short })))),
    h("tbody", {}, EXPECTED.map((e) => h("tr", {}, h("th", { scope: "row", text: Core.STATUS[e].label }),
      predicted.map((p) => {
        const n = at.get(`${e}|${p}`) || 0;
        const tone = n === 0 ? "" : e === p ? "tone-pass" : "tone-fail";
        return h("td", { class: `num ${tone}`, title: `Expected ${e}, predicted ${p}: ${n}`, text: Core.number(n) });
      }))))));
}

// ---------------------------------------------------------- routing rules
// How claims are routed and settled (claimguard.review.routing), written once
// for every page that explains it.
function routingRules() {
  return h("div", { class: "stack small" },
    h("div", { class: "row" }, routeBadge("ESCALATE"), h("span", { text: Core.ROUTE.ESCALATE.help })),
    h("div", { class: "row" }, routeBadge("REVIEW"), h("span", { text: Core.ROUTE.REVIEW.help })),
    h("div", { class: "row" }, routeBadge("CLEAR"), h("span", { text: `${Core.ROUTE.CLEAR.help} Clear claims need no review.` })),
    h("p", { class: "muted", text: "A finding is settled only by “Dismiss with reason”. “Confirm issue” means the claim needs a correction, “Request information” waits for the source, and “Corrected, recheck” sends the claim back through the rules as a new version. A decision taken on another version of the claim, or on a status that has since changed, does not count. A check that did not run can never be dismissed." }),
    h("p", { class: "muted", text: "Routes follow these fixed rules, applied to this run's results. Nothing here is a score or a probability." }));
}

// ---------------------------------------------------------- explanations
// How findings are explained in this run, in one plain line (Settings and
// Evaluation). Only a real model is called AI; the mock is not one.
function explainerLine() {
  const ai = DATA.run && DATA.run.ai ? DATA.run.ai.summary : null;
  if (!ai) return "This run has no explanations.";
  if (ai.provider === "mock") return "AI explainer not enabled. Findings use the rule's own explanation.";
  return `AI explanations are written by ${ai.provider}${ai.model ? ` (${ai.model})` : ""} and checked before they are shown. They never change a result.`;
}

// ----------------------------------------------------------- audit events
// Run events (runs, rejections, flags, model failures) need the
// view_run_events permission (claimguard.guards.rbac): admins only. Review
// decisions and new versions are visible to every role.
const RUN_EVENT_TYPES = ["run_started", "run_finished", "ingestion_error", "injection_flag", "model_failure"];
function canSeeEvent(e) { return !RUN_EVENT_TYPES.includes(e.event) || can("view_run_events"); }
function eventBadge(e) {
  const t = Core.EVENT[e.event] || { label: String(e.event), icon: "info", tone: "neutral" };
  return badge(t.label, { tone: t.tone, icon: t.icon });
}
// One line saying what an event recorded. Text from the event, shown as text.
function eventSummary(e) {
  switch (e.event) {
    case "run_started":
      return `Input ${Core.shortHash(e.input_sha256)} · engine ${e.engine_version} · ${Object.keys(e.rule_versions || {}).length} rule versions`;
    case "run_finished":
      return `${Core.number(e.results)} results · ${Core.number(e.accepted)} accepted · ${Core.number(e.rejected)} rejected · ` +
        `${Core.plural(e.injection_flags, "flag")} · ${Core.plural(e.rule_errors, "rule error")}`;
    case "ingestion_error": return `${e.stage}: ${e.reason}`;
    case "injection_flag":
      return `${Core.plural(e.hits.length, "hit")}: ${Array.from(new Set(e.hits.map((x) => Core.FAMILY[x.family] || x.family))).join("; ")}`;
    case "model_failure": return `${e.rule_id} · ${e.reason}${e.detail ? ": " + e.detail : ""}`;
    case "review_decision":
      return `${e.rule_id} · ${(Core.ACTION[e.action] || { label: e.action }).label} by ${e.actor}: ${e.reason}`;
    case "version_created":
      return `v${e.version} by ${e.actor}: ${Core.plural((e.changes || []).length, "change")} · ${e.reason}`;
    default: return "";
  }
}

// ------------------------------------------------------------ decisions
// A decision made here is a draft in this browser until it is downloaded and
// appended to the audit log. The latest one per finding (and per version of
// the claim) replaces any earlier draft.
function sameFinding(e, claimId, ruleId, inputHash) {
  return e.claim_id === claimId && e.rule_id === ruleId && e.input_hash === inputHash;
}
function draftFor(entry, ruleId) {
  return State.drafts.find((d) => sameFinding(d, entry.route.claim_id, ruleId, entry.input_hash)) || null;
}
function recordedFor(entry, ruleId) {
  const mine = RECORDED.filter((e) => sameFinding(e, entry.route.claim_id, ruleId, entry.input_hash));
  return mine.length ? mine[mine.length - 1] : null;
}
function saveDraft(event) {
  State.drafts = State.drafts.filter((d) => !sameFinding(d, event.claim_id, event.rule_id, event.input_hash)).concat([event]);
  State.save();
}
function discardDraft(entry, ruleId) {
  State.drafts = State.drafts.filter((d) => !sameFinding(d, entry.route.claim_id, ruleId, entry.input_hash));
  State.save();
}
function downloadDecisions() {
  download(`review_decisions_${RUN_ID.slice(0, 8)}.jsonl`, State.drafts.map((d) => JSON.stringify(d)).join("\n") + "\n");
}

// A source value as plain text (Core.plain). A missing value is a dash, with
// a tooltip saying the source has none.
function value(v) {
  if (v === null || v === undefined || v === "") return h("span", { class: "muted", text: "—", title: "No value in the source" });
  return Core.plain(v);
}

// ------------------------------------------------------------- download
function download(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
  const a = h("a", { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------- router
// Pages register themselves; the shell draws the same sidebar and topbar
// for every one of them.
const PAGES = [];
function registerPage(page) { PAGES.push(page); }

function parseRoute() {
  const raw = (location.hash || "#/dashboard").replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  const parts = path.split("/").map(decodeURIComponent);
  const params = {};
  new URLSearchParams(query || "").forEach((v, k) => { params[k] = v; });
  return { key: parts[0] || "dashboard", id: parts[1] || null, params };
}
function href(key, id, params) {
  const q = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined)).toString() : "";
  return `#/${key}${id ? "/" + encodeURIComponent(id) : ""}${q ? "?" + q : ""}`;
}
function go(key, id, params) { location.hash = href(key, id, params); }
