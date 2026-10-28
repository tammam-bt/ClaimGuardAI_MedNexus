"use strict";
// Components: every shared component in every state, drawn from real data.
// Not in the navigation (open #/components). It is the reference that keeps
// the pages consistent: a page may only use what appears here.

// The type scale, in the sans and the monospace stacks. System fonts differ
// by OS (Segoe UI and Consolas on Windows, San Francisco and SF Mono on
// Apple), so this is the card to compare across machines.
function typeScale() {
  const sizes = [["xs", "12"], ["sm", "14 · body"], ["base", "16"], ["lg", "18"], ["xl", "20"], ["2xl", "24"], ["3xl", "30"], ["4xl", "36"]];
  return card({ level: 3, title: "Type", meta: "System fonts: the face differs by OS, the scale does not", body: h("div", { class: "stack" },
    h("div", {}, sizes.map(([k, px]) => h("div", { class: "type-row" },
      h("span", { class: "mono small muted", text: `--text-${k} (${px})` }),
      h("span", { class: `t-${k}` }, "Coverage active on service date ", h("span", { class: "num", text: "1,520.00 · 0O 1lI" }))))),
    h("div", { class: "row" }, ["regular", "medium", "semibold", "bold"].map((w) => h("span", { class: `w-${w}`, text: `--weight-${w}` }))),
    h("p", { class: "muted small", text: "Theme: Settings › You › Theme (same as the system, light or dark)." })) });
}

// The signature components of the redesign, each in every state. A state
// this run's data cannot show is drawn from an example, labelled as such.
function signature(sample, fail, specimen) {
  if (!sample || !fail) return [];
  const pick = (pred) => CLAIMS.find(pred);
  const clear = pick((c) => c.route.route === "CLEAR");
  const unable = pick((c) => c.results.some((r) => r.status === "UNABLE_TO_ASSESS"));
  const legend = Core.STATUS_ORDER.map((st) => h("span", {},
    h("span", { "aria-hidden": "true" }, fingerprint([{ rule_id: Core.STATUS[st].short, status: st }], { size: "sm" })), Core.STATUS[st].label));
  const row = (c) => c ? h("div", { class: "row" }, h("span", { class: "mono small", text: c.claim.claim_id }), routeBadge(c.route.route),
    fingerprint(c.results, { size: "sm" }), fingerprint(c.results)) : null;

  const everyEvidence = CLAIMS.flatMap((c) => c.results.flatMap((r) => r.evidence.map((e) => ({ e, claim: c.claim }))));
  const missing = everyEvidence.find((x) => x.e.value === null || x.e.value === "");
  const structured = everyEvidence.find((x) => x.e.value !== null && typeof x.e.value === "object");
  const noop = () => {};

  const panel = (state) => decisionPanel(Object.assign({ id: `spec-${state.key}`, action: null, reason: "", reviewer: "Example reviewer",
    allowed: can, onAction: noop, onReason: noop, onName: noop, onSave: noop, onDiscard: noop }, state));
  const example = Core.decisionEvent(sample, fail, "confirm_issue", "Example reviewer", "Example reason: the end date is before the service date.", new Date().toISOString());

  const logged = DATA.audit ? DATA.audit.events.filter((r) => canSeeEvent(r.event)).slice(0, 2) : [];
  // A reviewer sees no run event; then the logged state is an example too.
  const items = [
    ...(logged.length
      ? logged.map((r) => ({ kind: "logged", badge: eventBadge(r.event), meta: `#${r.sequence} · ${Core.datetime(r.recorded_at)}`, text: eventSummary(r.event) }))
      : [{ kind: "logged", badge: eventBadge(example), meta: "Example", text: eventSummary(Object.assign({}, example, { action: "request_information" })) }]),
    { kind: "draft", badge: eventBadge(example), meta: "Example", text: eventSummary(example) },
  ];

  return [
    card({ level: 3, title: "Check fingerprint", meta: "15 cells, one per rule; shape and color", body: h("div", { class: "stack" },
      specimen("Legend", h("div", { class: "fp-legend" }, legend)),
      specimen("Escalate, review and clear claims (small for rows, medium for the claim header)",
        h("div", { class: "stack" }, row(sample), row(unable), row(clear)))) }),

    card({ level: 3, title: "Evidence chips", meta: `${fail.rule_id} on ${fail.claim_id}`, body: h("div", { class: "stack" },
      specimen("Cited fields; the second pressed (shown in the claim)", h("div", { class: "chips" },
        fail.evidence.map((e, i) => evidenceChip(e, sample.claim, { onShow: noop, active: i === 1 })))),
      specimen("A value missing in the source, and a structured value", h("div", { class: "chips" },
        missing ? evidenceChip(missing.e, missing.claim, { onShow: noop }) : null,
        structured ? evidenceChip(structured.e, structured.claim, { onShow: noop }) : null)),
      specimen("Not interactive", h("div", { class: "chips" }, evidenceChip(fail.evidence[0], sample.claim)))) }),

    specimen("Finding in three layers (selected)", findingBlock({ result: fail, selected: true,
      claimLayer: h("div", { class: "chips" }, fail.evidence.map((e) => evidenceChip(e, sample.claim, { onShow: noop }))),
      explanationLayer: h("div", { class: "stack" }, h("div", { class: "row row--tight" }, sourceBadge("mock")), h("p", { text: fail.explanation })),
      decisionLayer: panel({ key: "layer" }) })),

    card({ level: 3, title: "Decision panel", meta: "Every state; examples, nothing is saved", body: h("div", { class: "grid grid--2" },
      specimen("No name yet: the field comes before Save", panel({ key: "noname", reviewer: "", action: "confirm_issue", reason: "Example reason." })),
      specimen("Action chosen, no reason", panel({ key: "noreason", action: "dismiss_with_reason" })),
      specimen("Ready to save", panel({ key: "ready", action: "request_information", reason: "Example: the coverage letter is missing." })),
      specimen("Dismiss asks once more before saving", panel({ key: "confirm", action: "dismiss_with_reason", reason: "Example: coverage was extended.", confirming: true })),
      specimen("Draft saved", panel({ key: "draft", draft: example, action: "confirm_issue", reason: example.reason })),
      specimen("Save failed: the reason is kept", panel({ key: "error", action: "confirm_issue", reason: "Example reason kept after a failure.",
        error: "This browser refused to store the draft." })),
      specimen("The check did not run: Dismiss is unavailable", panel({ key: "ni", notImplemented: true }))) }),

    card({ level: 3, title: "Timeline", meta: "Logged events against drafts", body: timeline(items, { label: "Example history" }) }),

    card({ level: 3, title: "Drawer", meta: "The side panel that opens a check or an audit event", body: h("div", { class: "row" },
      button({ label: "Open the drawer", icon: "chevron-left", onClick: () => openPanel(sample.claim.claim_id, h("div", { class: "stack" },
        fingerprint(sample.results), kv([["Route", routeBadge(sample.route.route)], ["Submitted", Core.date(sample.claim.submission_date)],
          ["Total", h("span", { class: "num", text: Core.money(sample.claim.total_amount, sample.claim.currency) })]]))) }),
      h("span", { class: "muted small", text: "Escape or Close returns focus here." })) }),
  ];
}

registerPage({
  key: "components",
  label: "Components",
  icon: "sliders",
  nav: false,
  subtitle: "Every shared component, in every state. The pages use only these.",
  render() {
    const sample = CLAIMS.find((c) => c.route.route === "ESCALATE" && c.results.some((r) => r.status === "FAIL"))
      || CLAIMS[0];
    const fail = sample ? sample.results.find((r) => r.status === "FAIL") || sample.results[0] : null;

    const specimen = (label, ...nodes) => h("div", { class: "specimen" }, h("span", { class: "specimen__label", text: label }), ...nodes);
    const iconNames = Array.from(document.querySelectorAll("svg symbol[id^='i-']")).map((s) => s.id.slice(2));

    return h("div", { class: "stack" },
      pageHead({ title: "Component reference", text: "Built from this run's data. Open with #/components." }),

      card({ level: 3, title: "Icons", meta: `${iconNames.length} icons, one per concept`, body:
        h("div", { class: "grid grid--4" }, iconNames.map((n) => h("span", { class: "row small" }, icon(n), h("span", { class: "mono", text: n })))) }),

      card({ level: 3, title: "Badges", body: h("div", { class: "stack" },
        specimen("Result status", h("div", { class: "row" }, Core.STATUS_ORDER.map((s) => statusBadge(s)))),
        specimen("Result status, short (tables)", h("div", { class: "row" }, Core.STATUS_ORDER.map((s) => statusBadge(s, { short: true })))),
        specimen("Route", h("div", { class: "row" }, Core.ROUTE_ORDER.map(routeBadge))),
        specimen("Severity", h("div", { class: "row" }, ["high", "medium"].map(severityBadge))),
        specimen("Life-cycle outcome", h("div", { class: "row" }, Core.OUTCOME_ORDER.map(outcomeBadge))),
        specimen("Explanation source", h("div", { class: "row" }, Object.keys(Core.SOURCE).map(sourceBadge))),
        specimen("Method", h("div", { class: "row" }, methodBadge()))) }),

      card({ level: 3, title: "Buttons", body: h("div", { class: "stack" },
        specimen("Variants", h("div", { class: "row" },
          button({ label: "Primary", variant: "primary", icon: "download" }),
          button({ label: "Secondary" }), button({ label: "Danger", variant: "danger" }),
          button({ label: "Ghost", variant: "ghost" }), button({ label: "Disabled", disabled: true }),
          button({ label: "Close", icon: "x", iconOnly: true, variant: "ghost" }))),
        specimen("Review actions (one pressed)", h("div", { class: "row" },
          Core.ACTION_ORDER.map((a, i) => button({ label: Core.ACTION[a].label, icon: Core.ACTION[a].icon, pressed: i === 1, title: Core.ACTION[a].help }))))) }),

      specimen("Stat cards", statRow([
        statCard({ icon: "file-check", tone: "info", label: "Claims checked", value: Core.number(CLAIMS.length), caption: "From the run manifest" }),
        statCard({ icon: "arrow-up-circle", tone: "fail", label: "Escalated", value: Core.number(CLAIMS.filter((c) => c.route.route === "ESCALATE").length), caption: "Computed from the results" }),
        statCard({ icon: "shield-alert", tone: "unknown", label: "Flagged for injection", value: Core.number(CLAIMS.filter((c) => c.flag).length), caption: "Injection pre-filter" }),
        statCard({ icon: "check-check", tone: "pass", label: "Clear", value: Core.number(CLAIMS.filter((c) => c.route.route === "CLEAR").length), caption: "No finding" }),
      ])),

      card({ level: 3, title: "Callouts", body: h("div", { class: "stack" },
        callout({ tone: "info", icon: "info", title: "Information", text: "Neutral context for the reviewer." }),
        callout({ tone: "unknown", icon: "shield-alert", title: "Flagged for injection", text: "Instruction-like text was found; this claim's text never reaches the model." }),
        callout({ tone: "fail", icon: "alert-triangle", title: "Audit chain invalid", text: "A broken link was found." })) }),

      sample ? card({ level: 3, title: "Life cycle", meta: sample.claim.claim_id, body:
        lifecycleStrip(Core.lifecycle(sample, decisions()), { label: `Life cycle of ${sample.claim.claim_id}` }) }) : null,

      sample ? card({ level: 3, title: "Check grid", meta: sample.claim.claim_id, body: checkGrid(sample.results) }) : null,

      typeScale(),
      ...signature(sample, fail, specimen),

      fail ? card({ level: 3, title: "Evidence table", meta: `${fail.rule_id} on ${fail.claim_id}`, body: evidenceTable(fail.evidence, sample.claim) }) : null,

      card({ level: 3, title: "Bars", body: bars(Core.ROUTE_ORDER.map((r) => ({
        label: Core.ROUTE[r].label, value: CLAIMS.filter((c) => c.route.route === r).length, tone: Core.ROUTE[r].tone }))) }),

      card({ level: 3, title: "Table, filter bar and side panel", flush: true, body: h("div", {},
        h("div", { class: "card__body" }, filterBar([{ label: "Route", value: "", options: [["", "All routes"], ...Core.ROUTE_ORDER.map((r) => [r, Core.ROUTE[r].label])], onChange: () => {} }], "5 of 5 claims")),
        table({ caption: "Sample claims", rows: CLAIMS.slice(0, 5),
          columns: [
            { key: "id", label: "Claim", sort: (c) => c.claim.claim_id, render: (c) => h("span", { class: "mono", text: c.claim.claim_id }) },
            { key: "route", label: "Route", sort: (c) => Core.ROUTE_ORDER.indexOf(c.route.route), render: (c) => routeBadge(c.route.route) },
            { key: "amount", label: "Total", num: true, sort: (c) => c.claim.total_amount || 0, render: (c) => Core.money(c.claim.total_amount, c.claim.currency) },
          ],
          onRowClick: (c) => openPanel(c.claim.claim_id, kv([["Route", routeBadge(c.route.route)], ["Submitted", Core.date(c.claim.submission_date)]])) })) }),

      card({ level: 3, title: "Tabs", body: tabs("components", [
        { key: "a", label: "First", count: 2, render: () => h("p", { text: "First tab content." }) },
        { key: "b", label: "Second", render: () => h("p", { text: "Second tab content." }) }]) }),

      card({ level: 3, title: "Key / value", body: kv([["Run", DATA.run ? h("span", { class: "mono", text: DATA.run.run_id }) : null], ["Generated from", DATA.sources.results]]) }),

      card({ level: 3, title: "Empty state", body: emptyState({ icon: "search", title: "Nothing matches", text: "Change or clear the filters." }) }));
  },
});
