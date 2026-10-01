"use strict";
// Claims page: every checked claim (#/claims) and one claim (#/claims/<id>).
// ClaimViews.list is shared with the Review Queue, which shows the same table
// with a preset filter.

const ClaimViews = (function () {
  const SEARCH_INDEX = new WeakMap();
  let lastOrder = CLAIMS.map((c) => c.claim.claim_id);

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
    return [Object.keys(Core.latestDecisions(entry, events)).length, entry.route.reasons.length];
  }

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

  function findingsCell(entry) {
    const fail = countOf(entry, "FAIL"), unable = countOf(entry, "UNABLE_TO_ASSESS"), ni = countOf(entry, "NOT_IMPLEMENTED");
    if (!fail && !unable && !ni) return h("span", { class: "muted small", text: "None" });
    return h("span", { class: "row" },
      fail ? badge(`${fail} failed`, { tone: "fail", icon: Core.STATUS.FAIL.icon }) : null,
      unable ? badge(`${unable} unable`, { tone: "unknown", icon: Core.STATUS.UNABLE_TO_ASSESS.icon }) : null,
      ni ? badge(`${ni} not impl.`, { tone: "neutral", icon: Core.STATUS.NOT_IMPLEMENTED.icon }) : null);
  }

  // The claim table with its filters. opts: { pageKey, base (claims to list),
  // params (from the URL), hide: [filter names to leave out] }
  function list(opts) {
    const f = Object.assign({ q: "", route: "", stage: "", flag: "", rule: "", show: opts.defaultShow || "" }, opts.params);
    const hide = new Set(opts.hide || []);
    const base = opts.base.slice().sort(byUrgency);
    const holder = h("div");
    const count = h("span", { class: "filters__count", role: "status" });

    function draw() {
      const events = decisions();
      const rows = base.filter((e) => matches(e, f, events));
      lastOrder = rows.map((e) => e.claim.claim_id);
      count.textContent = `${Core.number(rows.length)} of ${Core.plural(base.length, "claim")}`;
      history.replaceState(null, "", href(opts.pageKey, opts.pageId || null, f));
      fill(holder, table({
        caption: "Claims", rows,
        empty: emptyState({ icon: "search", title: "No claim matches", text: "Change or clear the filters." }),
        onRowClick: (e) => go("claims", e.claim.claim_id),
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

  return { list, neighbours, countOf };
})();


// ------------------------------------------------------------------ detail
const ClaimDetail = (function () {
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
  function explanationLabel(x) {
    const s = Core.SOURCE[x.kind] || Core.SOURCE.mock;
    const why = x.kind === "fallback" && x.record && x.record.failure ? `The AI answer was rejected (${x.record.failure.reason}).`
      : x.kind === "skipped_flagged" ? "This claim was flagged for injection, so its findings were never sent to the model." : null;
    return badge(s.label, { tone: s.tone, icon: s.icon, title: why });
  }

  // One finding: what the engine found, why, and the reviewer's decision.
  function findingCard(entry, finding, onDecided, nameWatchers) {
    const r = finding.result;
    const rule = RULE_BY_ID.get(r.rule_id);
    const s = Core.STATUS[r.status];
    const box = h("article", { class: `finding is-${s.tone}`, id: `finding-${r.rule_id}`, "aria-label": `${r.rule_id} ${rule.title}` });
    const draft0 = draftFor(entry, r.rule_id);
    const pending = { action: draft0 ? draft0.action : null, reason: draft0 ? draft0.reason : "" };
    let saveButton = null;

    function canSave() {
      return !!pending.action && pending.reason.trim() !== "" && State.reviewer.trim() !== "" && can(pending.action);
    }
    function updateSave() { if (saveButton) saveButton.disabled = !canSave(); }
    nameWatchers.push(updateSave);

    function decisionArea() {
      const draft = draftFor(entry, r.rule_id);
      const recorded = recordedFor(entry, r.rule_id);
      const area = h("div", { class: "decision" }, h("span", { class: "label", text: "Your decision" }));
      if (recorded) {
        area.appendChild(callout({ tone: "info", icon: "history", title: "In the audit log",
          text: `${Core.ACTION[recorded.action].label} by ${recorded.actor}, ${Core.datetime(recorded.created_at)}: ${recorded.reason}` }));
      }
      if (draft) {
        area.appendChild(callout({ tone: "pass", icon: Core.ACTION[draft.action].icon, title: "Saved in this browser, not yet in the audit log",
          text: `${Core.ACTION[draft.action].label} by ${draft.actor}: ${draft.reason}`,
          body: h("div", { class: "row", style: { marginTop: "8px" } },
            button({ label: "Discard this draft", variant: "ghost", icon: "ban",
              onClick: () => { discardDraft(entry, r.rule_id); pending.action = null; pending.reason = ""; onDecided(); draw(); } })) }));
      }
      const notImplemented = r.status === "NOT_IMPLEMENTED";
      if (notImplemented) {
        area.appendChild(callout({ tone: "neutral", icon: "circle-dashed", title: "This check did not run",
          text: "It cannot be dismissed (routing policy): only an implementation can settle it." }));
      }
      area.appendChild(h("div", { class: "row", role: "group", "aria-label": "Review action" },
        Core.ACTION_ORDER.map((a) => button({
          label: Core.ACTION[a].label, icon: Core.ACTION[a].icon, title: Core.ACTION[a].help,
          pressed: pending.action === a,
          disabled: !can(a) || (notImplemented && a === "dismiss_with_reason"),
          onClick: () => { pending.action = pending.action === a ? null : a; draw(); },
        }))));
      if (pending.action) area.appendChild(h("p", { class: "muted small", text: Core.ACTION[pending.action].help }));
      const reasonId = `reason-${r.rule_id}`;
      const textarea = h("textarea", { id: reasonId, class: "textarea", rows: "3",
        placeholder: "Why? Recorded with your name in the audit log.",
        onInput: (e) => { pending.reason = e.target.value; updateSave(); } });
      textarea.value = pending.reason;
      area.appendChild(h("label", { class: "field", for: reasonId }, "Reason (required for every decision)", textarea));
      saveButton = button({ label: draft ? "Replace the saved decision" : "Save decision", variant: "primary",
        onClick: () => {
          if (!canSave()) return;
          saveDraft(Core.decisionEvent(entry, r, pending.action, State.reviewer, pending.reason, new Date().toISOString()));
          onDecided();
          draw();
        } });
      saveButton.disabled = !canSave();
      area.appendChild(h("div", { class: "row" }, saveButton,
        State.reviewer.trim() ? null : h("span", { class: "muted small", text: "Enter your name in “Your decisions” first." })));
      return area;
    }

    function draw() {
      const ex = explanationOf(entry, r);
      box.replaceChildren(
        h("div", { class: "finding__head" },
          h("span", { class: "mono", text: r.rule_id }), h("span", { class: "finding__title", text: rule.title }),
          statusBadge(r.status), severityBadge(r.severity, { long: true }),
          r.affected_line_ids.length ? badge(`Line ${r.affected_line_ids.join(", ")}`, { tone: "neutral" }) : null),
        h("div", { class: "finding__body" },
          h("div", { class: "finding__section" },
            h("div", { class: "row row--tight" }, h("span", { class: "label", text: "What the engine found" }), ex.own ? explanationLabel(ex) : null),
            h("p", { text: r.explanation })),
          ex.own ? null : h("div", { class: "finding__section" },
            h("div", { class: "row row--tight" }, h("span", { class: "label", text: "Explanation for the reviewer" }), explanationLabel(ex)),
            h("div", { class: "explanation stack" }, h("p", { text: ex.record.explanation }),
              h("p", { class: "muted small", text: "Written by an AI model and checked before it is shown. It cannot change the result." }))),
          h("div", { class: "finding__section" }, h("span", { class: "label", text: "Evidence the engine cited" }), evidenceTable(r.evidence, entry.claim)),
          r.corrective_action ? h("div", { class: "finding__section" }, h("span", { class: "label", text: "Corrective action" }), h("p", { text: r.corrective_action })) : null,
          h("details", { class: "disclosure" }, h("summary", { text: "Rule logic (rulebook)" }),
            h("p", { class: "small", text: rule.logic })),
          decisionArea()));
    }
    draw();
    return box;
  }

  function routeCallout(entry) {
    const route = entry.route;
    if (!route.reasons.length) {
      return callout({ tone: "pass", icon: Core.ROUTE.CLEAR.icon, title: "Clear: nothing to decide",
        text: "Every check passed or did not apply. A passed pre-check is not payer approval." });
    }
    return callout({ tone: route.route === "ESCALATE" ? "fail" : "unknown", icon: Core.ROUTE[route.route].icon,
      title: `Why ${Core.ROUTE[route.route].label.toLowerCase()}`,
      text: Core.ROUTE[route.route].help,
      body: h("div", { class: "row", style: { marginTop: "8px" } }, route.reasons.map((x) =>
        h("a", { href: `#finding-${x.rule_id}`, class: "badge tone-neutral", style: { textDecoration: "none" },
          onClick: (ev) => { ev.preventDefault(); scrollToId(`finding-${x.rule_id}`); } },
        `${x.rule_id} · ${Core.STATUS[x.status].label} · ${x.severity}`))) });
  }

  function flagCallout(entry) {
    if (!entry.flag) return null;
    return callout({ tone: "unknown", icon: "shield-alert", title: "Flagged by the injection pre-filter",
      text: "Instruction-like text was found in this claim. All 15 rules still ran on it, and its findings were not sent to the model. The text is shown below as data only.",
      body: h("ul", { class: "small", style: { margin: "8px 0 0", paddingLeft: "18px" } }, entry.flag.hits.map((hit) =>
        h("li", {}, hit.path === "(joined)" ? "Text across several fields" : Core.fieldLabel(hit.path, entry.claim),
          ` · ${Core.FAMILY[hit.family] || hit.family} · found in: ${hit.layer}`))) });
  }

  function scrollToId(id) {
    const el = document.getElementById(id);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); el.focus && el.setAttribute("tabindex", "-1"); }
  }

  function resultPanel(entry, r) {
    const rule = RULE_BY_ID.get(r.rule_id);
    openPanel(`${r.rule_id} · ${rule.title}`, h("div", { class: "stack" },
      h("div", { class: "row" }, statusBadge(r.status), severityBadge(r.severity, { long: true })),
      h("p", { text: r.explanation }),
      h("span", { class: "label", text: "Evidence the engine cited" }), evidenceTable(r.evidence, entry.claim),
      h("span", { class: "label", text: "Rule logic (rulebook)" }), h("p", { class: "small", text: rule.logic })));
  }

  function linesTable(c) {
    return table({ caption: "Service lines", rows: c.lines, columns: [
      { key: "line_id", label: "Line", render: (l) => h("span", { class: "mono", text: l.line_id }) },
      { key: "service_code", label: "Service", render: (l) => h("span", { class: "mono" }, value(l.service_code)) },
      { key: "service_date", label: "Date", render: (l) => (l.service_date ? Core.date(l.service_date) : value(null)) },
      { key: "modifier", label: "Modifier", render: (l) => value(l.modifier) },
      { key: "quantity", label: "Qty", num: true, render: (l) => value(l.quantity) },
      { key: "unit_price", label: "Unit price", num: true, render: (l) => (typeof l.unit_price === "number" ? Core.money(l.unit_price) : value(l.unit_price)) },
      { key: "net_amount", label: "Net", num: true, render: (l) => (typeof l.net_amount === "number" ? Core.money(l.net_amount) : value(l.net_amount)) },
      { key: "authorization_id", label: "Authorization", render: (l) => h("span", { class: "mono" }, value(l.authorization_id)) },
    ] });
  }

  function authorizationsBlock(c) {
    if (!c.authorizations.length) return h("p", { class: "muted small", text: "No authorization supplied (an empty inventory, not an unknown)." });
    return table({ caption: "Authorizations", rows: c.authorizations, columns: [
      { key: "authorization_id", label: "Authorization", render: (a) => h("span", { class: "mono", text: a.authorization_id }) },
      { key: "status", label: "Status", render: (a) => value(a.status) },
      { key: "service_code", label: "Service", render: (a) => h("span", { class: "mono" }, value(a.service_code)) },
      { key: "patient_id", label: "Patient", render: (a) => h("span", { class: "mono" }, value(a.patient_id)) },
      { key: "valid", label: "Valid", render: (a) => `${a.valid_from ? Core.date(a.valid_from) : "—"} – ${a.valid_to ? Core.date(a.valid_to) : "—"}` },
      { key: "max_quantity", label: "Max qty", num: true, render: (a) => value(a.max_quantity) },
    ] });
  }

  function attachmentsBlock(entry) {
    const c = entry.claim;
    if (!c.attachments.length) return h("p", { class: "muted small", text: "No document supplied (an empty inventory, not an unknown)." });
    return h("div", { class: "stack" }, c.attachments.map((a, i) => {
      const flaggedHere = entry.flag && entry.flag.hits.some((hit) => hit.path.startsWith(`/attachments/${i}/`));
      return h("div", { class: "stack" },
        kv([["Document", h("span", { class: "mono", text: a.attachment_id })], ["Type", a.type], ["Status", a.document_status],
          ["Patient", h("span", { class: "mono", text: a.patient_id })], ["Service", h("span", { class: "mono", text: a.service_code })],
          ["Service date", Core.date(a.service_date)]]),
        h("details", { class: "disclosure", open: flaggedHere ? null : true },
          h("summary", { text: flaggedHere ? "Show the flagged text (untrusted, shown as data)" : "Document text (untrusted, shown as data)" }),
          h("pre", { class: "untrusted", text: a.text })));
    }));
  }

  function partiesCard(c) {
    const policyKnown = Object.prototype.hasOwnProperty.call(DATA.policies, c.policy_id);
    return card({ title: "Claim parties", body: kv([
      ["Patient", h("span", { class: "mono" }, value(c.patient_id))],
      ["Member", h("span", { class: "mono" }, value(c.member_id))],
      ["Provider", h("span", { class: "mono" }, value(c.provider_id))],
      ["Payer", h("span", { class: "mono" }, value(c.payer_id))],
      ["Policy", h("span", { class: "row" }, h("span", { class: "mono", text: c.policy_id }),
        policyKnown ? null : badge("No matching policy supplied", { tone: "unknown", icon: "help-circle" }))],
      ["Invoice", h("span", { class: "mono" }, value(c.invoice_number))],
      ["Diagnosis", h("span", { class: "mono" }, value(c.diagnosis_code))],
    ]) });
  }

  function coverageCard(c) {
    const cv = c.coverage;
    return card({ title: "Coverage", body: kv([
      ["Coverage", h("span", { class: "mono", text: cv.coverage_id })],
      ["Status field", value(cv.status)],
      ["Beneficiary", h("span", { class: "mono" }, value(cv.beneficiary_patient_id))],
      ["Member", h("span", { class: "mono" }, value(cv.member_id))],
      ["Period", `${cv.start_date ? Core.date(cv.start_date) : "—"} – ${cv.end_date ? Core.date(cv.end_date) : "—"}`],
    ]) });
  }

  // Corrected versions of this claim (python -m claimguard.review.correct).
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

  // This claim's audit events your role may see, then decisions not yet sent.
  function historyCard(entry) {
    const id = entry.route.claim_id;
    const rows = DATA.audit ? DATA.audit.events.filter((r) => r.event.claim_id === id && canSeeEvent(r.event)) : [];
    const drafts = State.drafts.filter((d) => d.claim_id === id);
    const items = [
      ...rows.map((r) => h("button", { type: "button", class: "stage", style: { width: "100%" }, onClick: () => AuditPage.eventPanel(r) },
        h("span", { class: "row" }, eventBadge(r.event), h("span", { class: "muted small", text: `#${r.sequence} · ${Core.datetime(r.recorded_at)}` })),
        h("span", { class: "small", text: eventSummary(r.event) }))),
      ...drafts.map((d) => h("div", { class: "stage is-skipped" },
        h("span", { class: "row" }, badge("Draft in this browser", { tone: "neutral", icon: "user" })),
        h("span", { class: "small", text: eventSummary(d) }))),
    ];
    return card({ title: "History", meta: DATA.audit ? "From the audit log" : null, body: items.length
      ? h("div", { class: "stack" }, items)
      : h("p", { class: "muted small", text: DATA.audit ? "No event your role can see for this claim yet." : "No audit log was loaded for this run." }) });
  }

  function progressCard(entry) {
    const events = decisions();
    const total = entry.route.reasons.length;
    const decided = Object.keys(Core.latestDecisions(entry, events)).length;
    const mine = State.drafts.filter((d) => d.claim_id === entry.route.claim_id && d.input_hash === entry.input_hash).length;
    return card({ title: "Review progress", body: h("div", { class: "stack" },
      h("div", { class: "row" }, outcomeBadge(Core.outcome(entry, events))),
      total ? bars([{ label: "Findings decided", value: decided, total, tone: "primary", display: `${decided} / ${total}` }])
        : h("p", { class: "muted small", text: "Nothing to decide on this claim." }),
      h("p", { class: "small", text: `${Core.plural(mine, "draft")} on this claim · ${Core.plural(State.drafts.length, "draft")} in all.` }),
      button({ label: `Download decisions (${State.drafts.length})`, variant: "primary", icon: "download",
        disabled: State.drafts.length === 0, onClick: downloadDecisions }),
      h("p", { class: "muted small", text: "Decisions are kept in this browser until you download them." })) });
  }

  function nameCard(nameWatchers) {
    const input = h("input", { id: "reviewer-name", class: "input", value: State.reviewer, autocomplete: "name",
      placeholder: "e.g. Reviewer 01",
      onInput: (e) => { State.reviewer = e.target.value; State.save(); nameWatchers.forEach((fn) => fn()); } });
    input.value = State.reviewer;
    return card({ title: "Your decisions", body: h("div", { class: "stack" },
      h("label", { class: "field", for: "reviewer-name" }, "Your name", input),
      h("p", { class: "muted small", text: `Role: ${State.role === "admin" ? "Admin" : "Reviewer"}. Your name is recorded with each decision.` })) });
  }

  function render(id) {
    const entry = CLAIM_BY_ID.get(id);
    if (!entry) {
      return card({ body: emptyState({ icon: "search", title: `No claim ${id} in this run`,
        text: "It may have been rejected at ingestion, or belong to another run.", action: linkButton({ href: href("claims"), label: "All claims", icon: "chevron-left" }) }) });
    }
    const c = entry.claim;
    const [prev, next] = ClaimViews.neighbours(id);
    const headBadges = h("span", { class: "row" });
    const lifecycleHolder = h("div");
    const progressHolder = h("div");
    const nameWatchers = [];

    function refresh() {
      const events = decisions();
      fill(headBadges, routeBadge(entry.route.route), outcomeBadge(Core.outcome(entry, events)),
        entry.flag ? badge("Flagged for injection", { tone: "unknown", icon: "shield-alert" }) : null);
      fill(lifecycleHolder, lifecycleStrip(Core.lifecycle(entry, events), {
        label: `Life cycle of ${id}`,
        onPick: (s) => scrollToId({ received: "sec-received", ingested: "sec-received", checked: "sec-checks",
          screened: entry.flag ? "sec-flag" : "sec-checks", explained: "sec-findings", routed: "sec-route",
          review: "sec-findings", outcome: "sec-findings" }[s.key]),
      }));
      fill(progressHolder, progressCard(entry));
      Shell.refreshUser();
    }
    refresh();

    const counts = Core.statusCounts(entry.results);
    const finds = Core.findings(entry);

    return h("div", { class: "stack" },
      h("div", { class: "row row--between" },
        linkButton({ href: href("claims"), label: "All claims", icon: "chevron-left", variant: "ghost" }),
        h("div", { class: "row" },
          prev ? linkButton({ href: href("claims", prev), label: "Previous", icon: "chevron-left" }) : null,
          next ? linkButton({ href: href("claims", next), label: "Next", icon: "chevron-right" }) : null)),
      h("div", { class: "claim-head" },
        h("div", { class: "claim-head__title" }, h("h2", { text: c.claim_id }), headBadges),
        h("dl", { class: "facts" },
          [["Total", Core.money(c.total_amount, c.currency)], ["Submitted", Core.date(c.submission_date)],
            ["Policy", c.policy_id], ["Provider", c.provider_id], ["Lines", Core.number(c.lines.length)]]
            .map(([k, v]) => h("div", {}, h("dt", { text: k }), h("dd", { text: v }))))),
      card({ title: "Life cycle", body: lifecycleHolder }),
      versionsCard(entry),
      entry.flag ? section("sec-flag", flagCallout(entry)) : null,
      h("div", { class: "grid grid--main-side" },
        h("div", { class: "stack" },
          section("sec-route", routeCallout(entry)),
          section("sec-checks", card({ title: "All 15 checks",
            meta: `${counts.PASS} passed · ${counts.FAIL} failed · ${counts.UNABLE_TO_ASSESS} unable · ${counts.NOT_APPLICABLE} n/a` +
              (counts.NOT_IMPLEMENTED ? ` · ${counts.NOT_IMPLEMENTED} not implemented` : ""),
            body: checkGrid(entry.results, { onPick: (r) => (finds.some((f) => f.result.rule_id === r.rule_id)
              ? scrollToId(`finding-${r.rule_id}`) : resultPanel(entry, r)) }) })),
          section("sec-findings", h("section", { class: "stack", "aria-label": "Findings to decide" },
            h("h3", { class: "card__title", text: finds.length ? `Findings to decide (${finds.length})` : "Findings to decide" }),
            finds.length ? finds.map((f) => findingCard(entry, f, refresh, nameWatchers))
              : card({ body: emptyState({ icon: "check-check", title: "No finding", text: "Nothing on this claim needs a decision." }) }))),
          card({ title: "Service lines", flush: true, body: linesTable(c) }),
          card({ title: "Authorizations", flush: !!c.authorizations.length, body: authorizationsBlock(c) }),
          card({ title: "Documents", body: attachmentsBlock(entry) }),
          historyCard(entry),
          section("sec-received", card({ title: "Claim as received", body: h("details", { class: "disclosure" },
            h("summary", { text: "Show the JSON envelope (untrusted text shown as data)" }),
            h("pre", { class: "untrusted", text: JSON.stringify(c, null, 2) })) }))),
        h("div", { class: "sticky-side" }, nameCard(nameWatchers), progressHolder, partiesCard(c), coverageCard(c))));
  }

  return { render };
})();


registerPage({
  key: "claims",
  label: "Claims",
  icon: "file-text",
  subtitle: "Every checked claim, its 15 checks, evidence and decisions.",
  render(route) {
    if (route.id) return ClaimDetail.render(route.id);
    const routes = Core.count(CLAIMS, (c) => c.route.route);
    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "file-check", tone: "info", label: "Claims checked", value: Core.number(CLAIMS.length),
          caption: DATA.rejected.length ? `${DATA.rejected.length} rejected at ingestion` : "None rejected at ingestion", href: href("claims") }),
        ...Core.ROUTE_ORDER.map((r) => statCard({ icon: Core.ROUTE[r].icon, tone: Core.ROUTE[r].tone === "escalate" ? "fail" : Core.ROUTE[r].tone === "review" ? "unknown" : "pass",
          label: Core.ROUTE[r].label, value: Core.number(routes[r] || 0), caption: "Route computed from the results", href: href("claims", null, { route: r }) })),
      ]),
      ClaimViews.list({ pageKey: "claims", base: CLAIMS, params: route.params, hide: ["show"] }));
  },
});
