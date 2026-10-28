"use strict";
// Claims page: every checked claim (#/claims) and one claim (#/claims/<id>).
// ClaimViews.list is shared with the Review Queue, which shows the same table
// with a preset filter.

const ClaimViews = (function () {
  const SEARCH_INDEX = new WeakMap();
  // The list a claim was last opened from, in the order it was shown: a
  // claim's Previous / Next, its way back, and its "next open claim" follow
  // it. Until a list is drawn, every claim, most urgent first.
  let lastOrder = null;
  let lastList = { key: "queue", id: null, href: href("queue") };

  function searchText(entry) {
    if (!SEARCH_INDEX.has(entry)) {
      const c = entry.claim;
      SEARCH_INDEX.set(entry, [c.claim_id, c.invoice_number, c.patient_id, c.member_id, c.provider_id, c.policy_id]
        .filter(Boolean).join(" ").toLowerCase());
    }
    return SEARCH_INDEX.get(entry);
  }
  function countOf(entry, status) { return entry.results.filter((r) => r.status === status).length; }
  // Most urgent route first, then first in, first out (oldest submission).
  function byUrgency(a, b) {
    return (Core.ROUTE_ORDER.indexOf(a.route.route) - Core.ROUTE_ORDER.indexOf(b.route.route))
      || String(a.claim.submission_date).localeCompare(String(b.claim.submission_date));
  }
  function decidedOf(entry, events) {
    return [Object.keys(Core.latestDecisions(entry, events)).length, Core.current(entry).route.reasons.length];
  }
  // A claim with a finding nobody has decided yet (a draft counts).
  function undecided(entry, events) { const [d, t] = decidedOf(entry, events); return d < t; }
  lastOrder = CLAIMS.slice().sort(byUrgency).map((c) => c.claim.claim_id);

  function matches(entry, f, events) {
    if (f.q && !searchText(entry).includes(f.q.toLowerCase())) return false;
    if (f.route && entry.route.route !== f.route) return false;
    if (f.stage && Core.outcome(entry, events) !== f.stage) return false;
    if (f.show === "open" && Core.outcome(entry, events) === "ready") return false;
    if (f.flag === "flagged" && !entry.flag) return false;
    if (f.flag === "clean" && entry.flag) return false;
    if (f.rule) {
      const r = entry.results.find((x) => x.rule_id === f.rule);
      if (!r || (r.status !== "FAIL" && r.status !== "UNABLE_TO_ASSESS")) return false;
    }
    return true;
  }

  // The claim's 15 checks as a fingerprint (its current version, as on the
  // claim's own header), then its findings in words.
  function findingsCell(entry) {
    const fail = countOf(entry, "FAIL"), unable = countOf(entry, "UNABLE_TO_ASSESS"), ni = countOf(entry, "NOT_IMPLEMENTED");
    const words = [fail ? `${fail} failed` : null, unable ? `${unable} unable` : null, ni ? `${ni} not impl.` : null].filter(Boolean);
    return h("span", { class: "row row--tight" }, fingerprint(Core.current(entry).results, { size: "sm" }),
      h("span", { class: "muted small", text: words.length ? words.join(" · ") : "None" }));
  }

  // The claim table with its filters. opts: { pageKey, pageId, base (claims
  // to list), params (from the URL), hide: [filter names to leave out],
  // defaultShow, onOrder(entries) to hear each new order }. The filters and
  // the sort live in the address, so a reload, a link or Back keeps them.
  function list(opts) {
    const f = Object.assign({ q: "", route: "", stage: "", flag: "", rule: "", sort: "", show: opts.defaultShow || "" }, opts.params);
    const hide = new Set(opts.hide || []);
    const base = opts.base.slice().sort(byUrgency);
    const holder = h("div");
    const count = h("span", { class: "filters__count", role: "status" });
    const remember = () => {
      const at = href(opts.pageKey, opts.pageId || null, f);
      history.replaceState(null, "", at);
      lastList = { key: opts.pageKey, id: opts.pageId || null, href: at };
    };

    function draw() {
      const events = decisions();
      const rows = base.filter((e) => matches(e, f, events));
      count.textContent = `${Core.number(rows.length)} of ${Core.plural(base.length, "claim")}`;
      remember();
      fill(holder, table({
        caption: "Claims", rows, pageSize: 50,
        sort: f.sort ? { key: f.sort.replace(/^-/, ""), dir: f.sort.startsWith("-") ? -1 : 1 } : null,
        onOrder: (all, sort) => {
          lastOrder = all.map((e) => e.claim.claim_id);
          const s = sort ? `${sort.dir < 0 ? "-" : ""}${sort.key}` : "";
          if (s !== f.sort) { f.sort = s; remember(); }
          if (opts.onOrder) opts.onOrder(all);
        },
        empty: emptyState({ icon: "search", title: "No claim matches", text: "Change or clear the filters." }),
        rowHref: (e) => href("claims", e.claim.claim_id),
        columns: [
          { key: "claim", label: "Claim", sort: (e) => e.claim.claim_id, render: (e) => h("div", {},
            h("div", { class: "mono", text: e.claim.claim_id }), h("div", { class: "muted small", text: e.claim.patient_id })) },
          { key: "route", label: "Route", sort: (e) => Core.ROUTE_ORDER.indexOf(e.route.route), render: (e) => routeBadge(e.route.route) },
          { key: "stage", label: "Stage", sort: (e) => Core.OUTCOME_ORDER.indexOf(Core.outcome(e, events)),
            render: (e) => outcomeBadge(Core.outcome(e, events)) },
          { key: "findings", label: "Findings", sort: (e) => -(countOf(e, "FAIL") * 100 + countOf(e, "UNABLE_TO_ASSESS")), render: findingsCell },
          { key: "decided", label: "Decided", num: true, sort: (e) => { const [d, t] = decidedOf(e, events); return t ? d / t : 2; },
            render: (e) => { const [d, t] = decidedOf(e, events); return t ? `${d} / ${t}` : h("span", { class: "muted small", text: "—" }); } },
          { key: "flag", label: "Injection", sort: (e) => (e.flag ? 0 : 1),
            render: (e) => (e.flag ? badge("Flagged", { tone: "unknown", icon: "shield-alert" }) : h("span", { class: "muted small", text: "—" })) },
          { key: "provider", label: "Provider", sort: (e) => e.claim.provider_id, render: (e) => h("span", { class: "mono", text: e.claim.provider_id }) },
          { key: "total", label: "Total", num: true, sort: (e) => (typeof e.claim.total_amount === "number" ? e.claim.total_amount : -1),
            render: (e) => Core.money(e.claim.total_amount, e.claim.currency) },
          { key: "submitted", label: "Submitted", sort: (e) => e.claim.submission_date, render: (e) => Core.date(e.claim.submission_date) },
        ],
      }));
    }

    const set = (key) => (v) => { f[key] = v; draw(); };
    const filters = [
      !hide.has("show") && { label: "Show", value: f.show, onChange: set("show"),
        options: [["open", "Open claims only"], ["all", "All claims"]] },
      !hide.has("route") && { label: "Route", value: f.route, onChange: set("route"),
        options: [["", "All routes"], ...Core.ROUTE_ORDER.map((r) => [r, Core.ROUTE[r].label])] },
      !hide.has("stage") && { label: "Stage", value: f.stage, onChange: set("stage"),
        options: [["", "All stages"], ...Core.OUTCOME_ORDER.map((k) => [k, Core.OUTCOME[k].label])] },
      { label: "Injection", value: f.flag, onChange: set("flag"),
        options: [["", "All claims"], ["flagged", "Flagged"], ["clean", "Not flagged"]] },
      !hide.has("rule") && { label: "Failing or unassessed rule", value: f.rule, onChange: set("rule"),
        options: [["", "Any rule"], ...DATA.rules.map((r) => [r.rule_id, `${r.rule_id} · ${r.title}`])] },
    ].filter(Boolean);

    const search = searchField({ placeholder: "Claim, invoice, patient, member, provider…", label: "Search claims",
      value: f.q, onInput: set("q") });
    draw();
    const content = h("div", {}, h("div", { class: "card__body" }, filterBar(filters, null, [search, count])), holder);
    // bare: for a list placed inside another card.
    return opts.bare ? content : card({ flush: true, body: content });
  }

  function neighbours(id) {
    const i = lastOrder.indexOf(id);
    return i < 0 ? [null, null] : [lastOrder[i - 1] || null, lastOrder[i + 1] || null];
  }

  // The next claim in that list with a finding left to decide, after id
  // and then from the top; null when there is none.
  function nextOpen(id) {
    const events = decisions();
    const i = lastOrder.indexOf(id);
    const order = i < 0 ? lastOrder : lastOrder.slice(i + 1).concat(lastOrder.slice(0, i));
    return order.find((x) => x !== id && undecided(CLAIM_BY_ID.get(x), events)) || null;
  }

  // The way back to that list, with its filters: { href, label }.
  function back() {
    const page = PAGES.find((p) => p.key === lastList.key);
    return { href: lastList.href, label: lastList.id || (lastList.key === "claims" ? "All claims" : page ? page.label : "All claims") };
  }

  return { list, neighbours, nextOpen, back, undecided, countOf, decidedOf };
})();


// ------------------------------------------------------------------ detail
// One claim as a review workspace. A header (ID, route, outcome, total,
// dates, the check fingerprint), then three panes on wide screens: the
// findings, the finding being decided (in three layers), and the claim's
// data, where "show in claim" highlights each field a finding cites (the
// evidence thread). The rest of the claim follows below: life cycle, all 15
// checks, history and the envelope as received.
const ClaimDetail = (function () {
  const SEVERITY_RANK = { high: 0, medium: 1, low: 2 };
  const STATUS_RANK = { FAIL: 0, NOT_IMPLEMENTED: 1, UNABLE_TO_ASSESS: 2 };
  const DECISION_STATE = { open: "Undecided", draft: "Draft", logged: "In the audit log" };
  // j/k move between findings wherever the open workspace has the page; one
  // listener for the page's life, pointed at the workspace on screen.
  let keyHandler = null;
  document.addEventListener("keydown", (e) => { if (keyHandler) keyHandler(e); });

  function section(id, node) { node.id = id; return node; }

  // Where a finding's explanation came from. The mock is not a model: its
  // text is the rule's own explanation, and it is labelled as such. Only a
  // genuine model answer that says something else is shown a second time.
  function explanationOf(entry, result) {
    const ex = (entry.explanations || []).find((e) => e.rule_id === result.rule_id) || null;
    const kind = !ex ? "mock" : ex.source === "provider" && ex.provider === "mock" ? "mock" : ex.source;
    const own = !ex || kind !== "provider" || String(ex.explanation || "").trim() === "" ||
      String(ex.explanation).trim() === String(result.explanation || "").trim();
    return { kind, record: ex, own };
  }

  // Layer 2: the rule's text or the AI's, labelled; a rejected AI answer
  // and a withheld claim say why in plain words, not in a tooltip.
  function explanationLayer(entry, r) {
    const x = explanationOf(entry, r);
    const s = Core.SOURCE[x.kind] || Core.SOURCE.mock;
    const why = x.kind === "fallback" && x.record && x.record.failure
      ? `The AI answer was rejected: ${(Core.FAILURE[x.record.failure.reason] || x.record.failure.reason).toLowerCase()}. The rule's own explanation is shown instead.`
      : x.kind === "skipped_flagged" ? "This claim was flagged for injection, so its findings were never sent to the model." : null;
    const rule = RULE_BY_ID.get(r.rule_id);
    return h("div", { class: "stack stack--tight" },
      x.own
        ? [h("div", { class: "row row--tight" }, badge(s.label, { tone: s.tone, icon: s.icon })), h("p", { text: r.explanation })]
        : [h("p", { text: r.explanation }),
          h("div", { class: "explanation stack stack--tight" }, h("div", { class: "row row--tight" }, badge(s.label, { tone: s.tone, icon: s.icon })),
            h("p", { text: x.record.explanation }),
            h("p", { class: "muted small", text: "Written by an AI model and checked before it is shown. It cannot change the result." }))],
      why ? h("p", { class: "muted small", text: why }) : null,
      r.corrective_action ? h("p", { class: "small" }, h("span", { class: "label", text: "Corrective action: " }), r.corrective_action) : null,
      h("details", { class: "disclosure" }, h("summary", { text: "Rule logic (rulebook)" }), h("p", { class: "small", text: rule.logic })));
  }

  // Why a finding needs a human (routing triggers), in the challenge's words.
  const TRIGGER_LABEL = { low_confidence: "low confidence", high_severity: "high severity", issue: "proven issue" };

  function routeCallout(entry, onPick) {
    const route = entry.route;
    if (!route.reasons.length) {
      return callout({ tone: "pass", icon: Core.ROUTE.CLEAR.icon, title: "Clear: nothing to decide",
        text: "Every check passed or did not apply. A passed pre-check is not payer approval." });
    }
    return callout({ tone: route.route === "ESCALATE" ? "fail" : "unknown", icon: Core.ROUTE[route.route].icon,
      title: `Why ${Core.ROUTE[route.route].label.toLowerCase()}`,
      text: Core.ROUTE[route.route].help,
      body: h("div", { class: "row row--tight" }, route.reasons.map((x) =>
        h("a", { href: href("claims", route.claim_id, { finding: x.rule_id }), class: "badge tone-neutral",
          onClick: (ev) => { ev.preventDefault(); onPick(x.rule_id); } },
        `${x.rule_id} · ${Core.STATUS[x.status].label} · ` +
        ((x.triggers || []).map((t) => TRIGGER_LABEL[t] || t).join(", ") || x.severity)))) });
  }

  function flagCallout(entry) {
    if (!entry.flag) return null;
    return callout({ tone: "unknown", icon: "shield-alert", title: "Flagged by the injection pre-filter",
      text: "Instruction-like text was found in this claim. All 15 rules still ran on it, and its findings were not sent to the model. The text is shown below as data only.",
      body: h("ul", { class: "small plain-list" }, entry.flag.hits.map((hit) =>
        h("li", {}, hit.path === "(joined)" ? "Text across several fields" : Core.fieldLabel(hit.path, entry.claim),
          ` · ${Core.FAMILY[hit.family] || hit.family} · found in: ${hit.layer}`))) });
  }

  function scrollToId(id) {
    const el = document.getElementById(id);
    if (el) { el.setAttribute("tabindex", "-1"); el.scrollIntoView({ behavior: "smooth", block: "start" }); el.focus({ preventScroll: true }); }
  }

  function resultPanel(entry, r) {
    const rule = RULE_BY_ID.get(r.rule_id);
    openPanel(`${r.rule_id} · ${rule.title}`, h("div", { class: "stack" },
      h("div", { class: "row" }, statusBadge(r.status), severityBadge(r.severity, { long: true })),
      h("p", { text: r.explanation }),
      h("span", { class: "label", text: "Evidence the engine cited" }), evidenceTable(r.evidence, entry.claim),
      h("span", { class: "label", text: "Rule logic (rulebook)" }), h("p", { class: "small", text: rule.logic })));
  }

  // ---------------------------------------------------------- claim pane
  // Every value carries its JSON pointer (data-path), the same pointer the
  // engine cites as evidence, so a finding can point at it.
  const mono = (v) => h("span", { class: "mono" }, value(v));
  const money = (v, cur) => (typeof v === "number" ? h("span", { class: "num", text: Core.money(v, cur) }) : value(v));
  const day = (v) => (v ? Core.date(v) : value(null));
  function fields(pairs) {
    return h("dl", { class: "kv" }, pairs.filter(Boolean).map(([k, path, v]) =>
      [h("dt", { text: k }), h("dd", { "data-path": path }, v)]));
  }
  function block(path, title, body) {
    return h("div", { class: "claim-block", "data-path": path }, h("p", { class: "label", text: title }), body);
  }
  function claimPane(entry) {
    const c = Core.current(entry).claim;
    const cv = c.coverage;
    const policyKnown = Object.prototype.hasOwnProperty.call(DATA.policies, c.policy_id);
    const lines = c.lines.map((l, i) => block(`/lines/${i}`, `Line ${l.line_id}`, fields([
      ["Service", `/lines/${i}/service_code`, mono(l.service_code)],
      ["Date", `/lines/${i}/service_date`, day(l.service_date)],
      l.modifier !== undefined ? ["Modifier", `/lines/${i}/modifier`, value(l.modifier)] : null,
      ["Quantity", `/lines/${i}/quantity`, h("span", { class: "num" }, value(l.quantity))],
      ["Unit price", `/lines/${i}/unit_price`, money(l.unit_price)],
      ["Net", `/lines/${i}/net_amount`, money(l.net_amount)],
      ["Authorization", `/lines/${i}/authorization_id`, mono(l.authorization_id)],
    ])));
    const auths = c.authorizations.map((a, i) => block(`/authorizations/${i}`, `Authorization ${a.authorization_id}`, fields([
      ["Status", `/authorizations/${i}/status`, value(a.status)],
      ["Service", `/authorizations/${i}/service_code`, mono(a.service_code)],
      ["Patient", `/authorizations/${i}/patient_id`, mono(a.patient_id)],
      ["Valid from", `/authorizations/${i}/valid_from`, day(a.valid_from)],
      ["Valid to", `/authorizations/${i}/valid_to`, day(a.valid_to)],
      ["Max quantity", `/authorizations/${i}/max_quantity`, h("span", { class: "num" }, value(a.max_quantity))],
    ])));
    return h("div", { class: "stack" },
      card({ title: "Claim", body: fields([
        ["Patient", "/patient_id", mono(c.patient_id)], ["Member", "/member_id", mono(c.member_id)],
        ["Provider", "/provider_id", mono(c.provider_id)], ["Payer", "/payer_id", mono(c.payer_id)],
        ["Policy", "/policy_id", h("span", { class: "row row--tight" }, mono(c.policy_id),
          policyKnown ? null : badge("No matching policy supplied", { tone: "unknown", icon: "help-circle" }))],
        ["Invoice", "/invoice_number", mono(c.invoice_number)], ["Diagnosis", "/diagnosis_code", mono(c.diagnosis_code)],
        ["Submitted", "/submission_date", day(c.submission_date)],
        ["Total", "/total_amount", money(c.total_amount)], ["Currency", "/currency", mono(c.currency)],
      ]) }),
      card({ title: "Coverage", body: fields([
        ["Coverage", "/coverage/coverage_id", mono(cv.coverage_id)], ["Status", "/coverage/status", value(cv.status)],
        ["Beneficiary", "/coverage/beneficiary_patient_id", mono(cv.beneficiary_patient_id)], ["Member", "/coverage/member_id", mono(cv.member_id)],
        ["Start", "/coverage/start_date", day(cv.start_date)], ["End", "/coverage/end_date", day(cv.end_date)],
      ]) }),
      card({ title: `Service lines (${c.lines.length})`, body: h("div", { class: "stack", "data-path": "/lines" }, lines) }),
      card({ title: "Authorizations", body: h("div", { class: "stack", "data-path": "/authorizations" }, auths.length ? auths
        : h("p", { class: "muted small", text: "No authorization supplied (an empty inventory, not an unknown)." })) }),
      card({ title: "Documents", body: h("div", { "data-path": "/attachments" }, attachmentsBlock(entry)) }));
  }

  function attachmentsBlock(entry) {
    const c = Core.current(entry).claim;
    if (!c.attachments.length) return h("p", { class: "muted small", text: "No document supplied (an empty inventory, not an unknown)." });
    return h("div", { class: "stack" }, c.attachments.map((a, i) => {
      const flaggedHere = entry.flag && entry.flag.hits.some((hit) => hit.path.startsWith(`/attachments/${i}/`));
      return block(`/attachments/${i}`, `Document ${a.attachment_id}`, h("div", { class: "stack stack--tight" },
        fields([["Type", `/attachments/${i}/type`, value(a.type)], ["Status", `/attachments/${i}/document_status`, value(a.document_status)],
          ["Patient", `/attachments/${i}/patient_id`, mono(a.patient_id)], ["Service", `/attachments/${i}/service_code`, mono(a.service_code)],
          ["Service date", `/attachments/${i}/service_date`, day(a.service_date)]]),
        h("details", { class: "disclosure", open: flaggedHere ? null : true },
          h("summary", { text: flaggedHere ? "Show the flagged text (untrusted, shown as data)" : "Document text (untrusted, shown as data)" }),
          h("pre", { class: "untrusted", "data-path": `/attachments/${i}/text`, text: a.text }))));
    }));
  }

  // The claim fields a pointer names: the field itself, else everything
  // inside it (a whole line), else the nearest field holding it.
  function targets(pane, path) {
    const all = Array.from(pane.querySelectorAll("[data-path]"));
    let hit = all.filter((el) => el.dataset.path === path);
    if (!hit.length) hit = all.filter((el) => el.dataset.path.startsWith(`${path}/`));
    for (let p = path; !hit.length && p.lastIndexOf("/") > 0;) {
      p = p.slice(0, p.lastIndexOf("/"));
      hit = all.filter((el) => el.dataset.path === p);
    }
    return hit;
  }

  // ----------------------------------------------------------- workspace
  function workspace(entry, initialRule, onDecided) {
    const id = entry.route.claim_id;
    const finds = Core.findings(entry).slice().sort((a, b) =>
      ((SEVERITY_RANK[a.result.severity] ?? 3) - (SEVERITY_RANK[b.result.severity] ?? 3))
      || ((STATUS_RANK[a.result.status] ?? 3) - (STATUS_RANK[b.result.status] ?? 3))
      || a.result.rule_id.localeCompare(b.result.rule_id));
    const st = {
      selected: finds.some((f) => f.result.rule_id === initialRule) ? initialRule : (finds[0] ? finds[0].result.rule_id : null),
      f: { status: "", severity: "", decision: "", q: "" },
      pending: {}, errors: {}, active: null,
    };
    const stateOf = (rule) => (draftFor(entry, rule) ? "draft" : recordedFor(entry, rule) ? "logged" : "open");

    const pane = h("div", { class: "ws-pane ws-pane--claim", role: "region", "aria-label": "Claim data", tabindex: "-1" }, claimPane(entry));
    const findingHolder = h("div", { class: "ws-pane ws-pane--finding" });
    const listHolder = h("div");
    const count = h("span", { class: "filters__count", role: "status" });
    const progressHolder = h("div");
    const announce = h("p", { class: "sr-only", role: "status" });

    function visible() {
      const q = st.f.q.trim().toLowerCase();
      return finds.filter(({ result: r }) => (!st.f.status || r.status === st.f.status) && (!st.f.severity || r.severity === st.f.severity)
        && (!st.f.decision || stateOf(r.rule_id) === st.f.decision)
        && (!q || `${r.rule_id} ${ruleName(r.rule_id)}`.toLowerCase().includes(q)));
    }

    function drawProgress() {
      const decided = Object.keys(Core.latestDecisions(entry, decisions())).length;
      fill(progressHolder, bars([{ label: "Decided", value: decided, total: finds.length, tone: "primary", display: `${decided} / ${finds.length}` }]));
    }

    function drawList() {
      const vis = visible();
      const roving = vis.some((f) => f.result.rule_id === st.selected) ? st.selected : (vis[0] ? vis[0].result.rule_id : null);
      count.textContent = `${vis.length} of ${Core.plural(finds.length, "finding")}`;
      fill(listHolder, vis.length ? h("ul", { class: "ws-list", role: "listbox", "aria-label": "Findings" }, vis.map(({ result: r }) => {
        const d = stateOf(r.rule_id);
        const draft = d === "draft" ? draftFor(entry, r.rule_id) : null;
        return h("li", { role: "option", id: `opt-${r.rule_id}`, class: "ws-item", "data-rule": r.rule_id,
          "aria-selected": String(r.rule_id === st.selected), tabindex: r.rule_id === roving ? "0" : "-1",
          onClick: () => select(r.rule_id, true),
          onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(r.rule_id, false); openFinding(); } } },
          h("span", { class: "ws-item__top" }, h("span", { class: "mono", text: r.rule_id }), statusBadge(r.status, { short: true }), severityBadge(r.severity)),
          h("span", { class: "ws-item__title", text: ruleName(r.rule_id) }),
          h("span", { class: `ws-item__state is-${d}`, text: draft ? `Draft: ${Core.ACTION[draft.action].label}` : DECISION_STATE[d] }));
      })) : emptyState({ icon: "search", title: "No finding matches", text: "Change or clear the filters." }));
    }

    // Layer 1 marks every field the finding cites; a pressed chip marks one
    // strongly and brings it into view in the claim pane.
    function markEvidence(r) {
      pane.querySelectorAll(".is-cited, .is-thread").forEach((el) => el.classList.remove("is-cited", "is-thread"));
      if (!r) return;
      for (const e of r.evidence) targets(pane, e.path).forEach((el) => el.classList.add("is-cited"));
      if (st.active) {
        const hit = targets(pane, st.active);
        hit.forEach((el) => el.classList.add("is-thread"));
        if (hit[0]) hit[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }

    // Every finding decided: the next claim of the list that still has one
    // to decide is a link away (focused right after the last save).
    function nextClaim() {
      if (!finds.length || ClaimViews.undecided(entry, decisions())) return null;
      const nextId = ClaimViews.nextOpen(id);
      const link = nextId ? linkButton({ href: href("claims", nextId), label: `Next open claim: ${nextId}`, icon: "arrow-right", variant: "primary" }) : null;
      if (link) link.id = "next-claim";
      return callout({ tone: "pass", icon: "check-check", title: "Every finding on this claim is decided",
        text: nextId ? "The next claim in your list with a finding left to decide:" : "No other claim in your list has a finding left to decide.",
        body: link ? h("div", { class: "row" }, link) : null });
    }

    function drawFinding() {
      const f = finds.find((x) => x.result.rule_id === st.selected);
      if (!f) {
        fill(findingHolder, emptyState({ icon: "check-check", title: "No finding", text: "Nothing on this claim needs a decision." }));
        markEvidence(null);
        return;
      }
      const r = f.result;
      const draft = draftFor(entry, r.rule_id);
      const p = st.pending[r.rule_id] || (st.pending[r.rule_id] = { action: draft ? draft.action : null, reason: draft ? draft.reason : "" });
      const chips = h("div", { class: "chips" });
      const drawChips = () => fill(chips, r.evidence.map((e) => evidenceChip(e, entry.claim, { active: st.active === e.path,
        onShow: (ev) => {
          st.active = st.active === ev.path ? null : ev.path;
          chips.querySelectorAll(".chip").forEach((c, i) => c.setAttribute("aria-pressed", String(st.active === r.evidence[i].path)));
          markEvidence(r);
          if (st.active) announce.textContent = `${Core.fieldLabel(ev.path, Core.current(entry).claim)} highlighted in the claim data.`;
        } })));
      drawChips();
      const article = findingBlock({ result: r, claimLayer: chips, explanationLayer: explanationLayer(entry, r),
        decisionLayer: decisionPanel({ id: r.rule_id, action: p.action, reason: p.reason, reviewer: State.reviewer, allowed: can,
          notImplemented: r.status === "NOT_IMPLEMENTED", draft, recorded: recordedFor(entry, r.rule_id), error: st.errors[r.rule_id] || null,
          onAction: (a) => { p.action = a; }, onReason: (v) => { p.reason = v; },
          onName: (v) => { State.reviewer = v; State.save(); },
          onSave: (d) => save(r, d),
          onDiscard: () => { discardDraft(entry, r.rule_id); p.action = null; p.reason = ""; changed(r.rule_id, "Draft discarded.", false); } }) });
      article.id = `finding-${r.rule_id}`;
      article.setAttribute("tabindex", "-1");
      fill(findingHolder, nextClaim(), article);
      markEvidence(r);
    }

    function select(rule, focusItem) {
      if (rule === st.selected && findingHolder.firstChild) { if (focusItem) focusOption(rule); return; }
      st.selected = rule;
      st.active = null;
      history.replaceState(null, "", href("claims", id, { finding: rule }));
      drawList();
      drawFinding();
      if (focusItem) focusOption(rule);
    }
    function focusOption(rule) { const el = document.getElementById(`opt-${rule}`); if (el) el.focus(); }
    function openFinding() { const el = findingHolder.querySelector("article"); if (el) el.focus(); }

    // Saved: the next undecided finding opens, so a claim is decided in
    // one pass. A browser that would not store the draft keeps it on this
    // page and says so, with the reason still in the box.
    function save(r, d) {
      const ok = saveDraft(Core.decisionEvent(entry, r, d.action, State.reviewer, d.reason, new Date().toISOString()));
      st.errors[r.rule_id] = ok ? null
        : "This browser would not store the draft (storage is full or blocked). It is kept on this page until you reload: download your decisions before you leave.";
      changed(r.rule_id, ok ? `Draft saved for ${r.rule_id}.` : `Not stored: ${r.rule_id} is kept on this page only.`, ok);
    }
    function changed(rule, message, advance) {
      onDecided();
      drawProgress();
      const next = advance ? visible().find((f) => f.result.rule_id !== rule && stateOf(f.result.rule_id) === "open") : null;
      if (next) {
        st.selected = next.result.rule_id;
        st.active = null;
        history.replaceState(null, "", href("claims", id, { finding: st.selected }));
      }
      drawList();
      drawFinding();
      const onward = advance && !next ? document.getElementById("next-claim") : null;
      announce.textContent = next ? `${message} Next: ${st.selected} ${ruleName(st.selected)}.`
        : onward ? `${message} Every finding on this claim is decided. ${onward.textContent}.` : message;
      if (onward) onward.focus();
      else openFinding();
    }

    function move(step) {
      const vis = visible();
      if (!vis.length) return;
      const i = vis.findIndex((f) => f.result.rule_id === st.selected);
      const j = i < 0 ? 0 : Math.min(vis.length - 1, Math.max(0, i + step));
      select(vis[j].result.rule_id, true);
    }
    const root = h("div", { class: "workspace" });
    keyHandler = (e) => {
      if (!root.isConnected) { keyHandler = null; return; }
      if (e.altKey || e.ctrlKey || e.metaKey || panelState) return;
      const t = e.target instanceof Element ? e.target : null;
      if (t && t.closest("input, textarea, select, [contenteditable]")) return;
      const inList = !!(t && t.closest(".ws-list"));
      const step = e.key === "j" || (inList && e.key === "ArrowDown") ? 1 : e.key === "k" || (inList && e.key === "ArrowUp") ? -1 : 0;
      if (!step) return;
      e.preventDefault();
      move(step);
    };

    const set = (key) => (v) => { st.f[key] = v; drawList(); };
    const filters = filterBar([
      { label: "Status", value: "", onChange: set("status"), options: [["", "All"], ...["FAIL", "UNABLE_TO_ASSESS", "NOT_IMPLEMENTED"]
        .filter((s) => finds.some((f) => f.result.status === s)).map((s) => [s, Core.STATUS[s].label])] },
      { label: "Severity", value: "", onChange: set("severity"), options: [["", "All"], ...["high", "medium", "low"]
        .filter((s) => finds.some((f) => f.result.severity === s)).map((s) => [s, Core.SEVERITY[s].label])] },
      { label: "Decision", value: "", onChange: set("decision"), options: [["", "All"], ...Object.entries(DECISION_STATE)] },
    ]);
    const search = searchField({ placeholder: "Rule ID or name", label: "Search findings", value: "", onInput: set("q") });

    drawProgress();
    drawList();
    drawFinding();
    return fill(root,
      h("section", { class: "ws-pane ws-pane--list", "aria-label": "Findings to decide" },
        h("div", { class: "ws-list-head" },
          h("h3", { class: "card__title", text: `Findings to decide (${finds.length})` }), progressHolder,
          h("details", { class: "disclosure" }, h("summary", { text: "Filter and search" }), h("div", { class: "stack stack--tight" }, filters, search)),
          h("div", { class: "row row--between" }, count, h("span", { class: "muted small", text: "j / k to move · Enter to open" }))),
        listHolder),
      findingHolder, pane, announce);
  }

  // ------------------------------------------------- below the workspace
  function versionsCard(entry) {
    if (!entry.versions || !entry.versions.length) return null;
    return card({ title: "Corrected versions", meta: "The claim as received (v1) is never edited", body: h("div", { class: "stack" },
      entry.versions.map((v) => h("div", { class: "stack" },
        h("div", { class: "row" }, badge(`v${v.version}`, { tone: "info", icon: "refresh" }), routeBadge(v.route.route),
          h("span", { class: "small", text: `by ${v.actor}: ${v.reason}` })),
        h("div", { class: "row small" }, h("span", { class: "label", text: "What changed" }),
          v.changes.map((c) => h("span", { class: "badge tone-neutral",
            text: `${({ add: "Added", remove: "Removed", replace: "Changed", move: "Moved", copy: "Copied" })[c.op] || c.op}: ${Core.fieldLabel(c.path, entry.claim)}` }))),
        h("div", { class: "row small" }, h("span", { class: "label", text: "Status changes after recheck" }),
          v.status_changes.length ? v.status_changes.map((c) => h("span", { class: "row" },
            h("span", { class: "mono", text: c.rule_id }), statusBadge(c.before, { short: true }), "→", statusBadge(c.after, { short: true })))
            : h("span", { class: "muted", text: "None: the correction changed no status." })),
        h("span", { class: "label", text: `All 15 checks on v${v.version}` }),
        checkGrid(v.results)))) });
  }

  // This claim's audit events your role may see, then decisions not yet
  // sent, as one timeline: a draft never looks like a logged event.
  function historyCard(entry) {
    const id = entry.route.claim_id;
    const rows = DATA.audit ? DATA.audit.events.filter((r) => r.event.claim_id === id && canSeeEvent(r.event)) : [];
    const items = [
      ...rows.map((r) => ({ kind: "logged", badge: eventBadge(r.event), meta: `#${r.sequence} · ${Core.datetime(r.recorded_at)}`,
        text: eventSummary(r.event), onOpen: () => AuditPage.eventPanel(r) })),
      ...State.drafts.filter((d) => d.claim_id === id).map((d) => ({ kind: "draft", badge: eventBadge(d),
        meta: Core.datetime(d.created_at), text: eventSummary(d) })),
    ];
    return card({ title: "History", meta: DATA.audit ? "Audit log, then drafts in this browser" : null, body: items.length
      ? timeline(items, { label: `History of ${id}` })
      : h("p", { class: "muted small", text: DATA.audit ? "No event your role can see for this claim yet." : "No audit log was loaded for this run." }) });
  }

  function render(id, params) {
    const entry = CLAIM_BY_ID.get(id);
    if (!entry) {
      keyHandler = null;
      return card({ body: emptyState({ icon: "search", title: `No claim ${id} in this run`,
        text: "It may have been rejected at ingestion, or belong to another run.", action: linkButton({ href: href("claims"), label: "All claims", icon: "chevron-left" }) }) });
    }
    // Everything a reviewer decides on is the current version: the newest
    // corrected one, else the claim as received (Core.current).
    const cur = Core.current(entry);
    const c = cur.claim;
    const onVersion = cur.version > 1 ? ` on v${cur.version}` : "";
    const [prev, next] = ClaimViews.neighbours(id);
    const back = ClaimViews.back();
    const headBadges = h("span", { class: "row row--tight" });
    const lifecycleHolder = h("div");
    const bannerHolder = h("div");
    const historyHolder = h("div");
    let ws = null;

    function refresh() {
      const events = decisions();
      fill(headBadges, cur.version > 1 ? badge(`v${cur.version}`, { tone: "info", icon: "refresh" }) : null,
        routeBadge(cur.route.route), outcomeBadge(Core.outcome(entry, events)),
        entry.flag ? badge("Flagged for injection", { tone: "unknown", icon: "shield-alert" }) : null);
      fill(lifecycleHolder, lifecycleStrip(Core.lifecycle(entry, events), {
        label: `Life cycle of ${id}`,
        onPick: (s) => scrollToId({ received: "sec-received", ingested: "sec-received", checked: "sec-checks",
          screened: entry.flag ? "sec-flag" : "sec-checks", explained: "sec-findings", routed: "sec-route",
          review: "sec-findings", outcome: "sec-findings" }[s.key]),
      }));
      fill(bannerHolder, draftsBanner());
      fill(historyHolder, historyCard(entry));
      Shell.refreshUser();
    }
    refresh();
    ws = workspace(entry, params && params.finding, refresh);
    // A route reason or a check opens its finding in the workspace.
    const pick = (rule) => {
      const el = document.getElementById(`opt-${rule}`);
      if (!el) return;
      document.getElementById("sec-findings").scrollIntoView({ behavior: "smooth", block: "start" });
      el.click();
    };
    const counts = Core.statusCounts(cur.results);
    const finds = Core.findings(entry);

    return h("div", { class: "stack" },
      h("header", { class: "claim-head" },
        h("div", { class: "claim-head__title" },
          linkButton({ href: back.href, label: back.label, icon: "chevron-left", variant: "ghost" }),
          h("h2", { text: c.claim_id }), headBadges, fingerprint(cur.results),
          h("div", { class: "row row--tight claim-head__nav" },
            prev ? linkButton({ href: href("claims", prev), label: "Previous", icon: "chevron-left" }) : null,
            next ? linkButton({ href: href("claims", next), label: "Next", icon: "chevron-right" }) : null)),
        h("dl", { class: "facts" },
          [["Total", h("span", { class: "num", text: Core.money(c.total_amount, c.currency) })], ["Submitted", Core.date(c.submission_date)],
            ["Policy", c.policy_id], ["Provider", c.provider_id], ["Lines", Core.number(c.lines.length)]]
            .map(([k, v]) => h("div", {}, h("dt", { text: k }), h("dd", {}, v))))),
      bannerHolder,
      entry.flag ? section("sec-flag", flagCallout(entry)) : null,
      cur.version > 1 ? callout({ tone: "info", icon: "refresh", title: `Deciding on version ${cur.version}`,
        text: `This claim was corrected and rechecked. Its findings, checks and data are those of v${cur.version}; ` +
          "decisions on an earlier version no longer count. The claim as received (v1) is kept unchanged below." }) : null,
      finds.length ? section("sec-findings", ws) : section("sec-findings", routeCallout(cur, pick)),
      finds.length ? section("sec-route", routeCallout(cur, pick)) : null,
      card({ title: "Life cycle", body: lifecycleHolder }),
      section("sec-checks", card({ title: `All 15 checks${onVersion}`,
        meta: `${counts.PASS} passed · ${counts.FAIL} failed · ${counts.UNABLE_TO_ASSESS} unable · ${counts.NOT_APPLICABLE} n/a` +
          (counts.NOT_IMPLEMENTED ? ` · ${counts.NOT_IMPLEMENTED} not implemented` : ""),
        body: checkGrid(cur.results, { onPick: (r) => (finds.some((f) => f.result.rule_id === r.rule_id) ? pick(r.rule_id) : resultPanel(cur, r)) }) })),
      versionsCard(entry),
      historyHolder,
      section("sec-received", card({ title: "Claim as received", body: h("details", { class: "disclosure" },
        h("summary", { text: "Show the JSON envelope (untrusted text shown as data)" }),
        h("pre", { class: "untrusted", text: JSON.stringify(entry.claim, null, 2) })) })));
  }

  return { render };
})();


registerPage({
  key: "claims",
  label: "Claims",
  icon: "file-text",
  subtitle: "Every checked claim, its 15 checks, evidence and decisions.",
  render(route) {
    if (route.id) return ClaimDetail.render(route.id, route.params);
    const routes = Core.count(CLAIMS, (c) => c.route.route);
    return h("div", { class: "stack" },
      draftsBanner(),
      statRow([
        statCard({ icon: "file-check", tone: "info", label: "Claims checked", value: Core.number(CLAIMS.length),
          caption: DATA.rejected.length ? `${DATA.rejected.length} rejected at ingestion` : "None rejected at ingestion", href: href("claims") }),
        ...Core.ROUTE_ORDER.map((r) => statCard({ icon: Core.ROUTE[r].icon, tone: Core.ROUTE[r].tone === "escalate" ? "fail" : Core.ROUTE[r].tone === "review" ? "unknown" : "pass",
          label: Core.ROUTE[r].label, value: Core.number(routes[r] || 0), caption: "Route computed from the results", href: href("claims", null, { route: r }) })),
      ]),
      ClaimViews.list({ pageKey: "claims", base: CLAIMS, params: route.params, hide: ["show"] }));
  },
});
