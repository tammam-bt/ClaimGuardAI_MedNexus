"use strict";
// Components: every shared component in every state, drawn from real data.
// Not in the navigation (open #/components). It is the reference that keeps
// the pages consistent: a page may only use what appears here.

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

      card({ title: "Icons", meta: `${iconNames.length} icons, one per concept`, body:
        h("div", { class: "grid grid--4" }, iconNames.map((n) => h("span", { class: "row small" }, icon(n), h("span", { class: "mono", text: n })))) }),

      card({ title: "Badges", body: h("div", { class: "stack" },
        specimen("Result status", h("div", { class: "row" }, Core.STATUS_ORDER.map((s) => statusBadge(s)))),
        specimen("Result status, short (tables)", h("div", { class: "row" }, Core.STATUS_ORDER.map((s) => statusBadge(s, { short: true })))),
        specimen("Route", h("div", { class: "row" }, Core.ROUTE_ORDER.map(routeBadge))),
        specimen("Severity", h("div", { class: "row" }, ["high", "medium"].map(severityBadge))),
        specimen("Life-cycle outcome", h("div", { class: "row" }, Core.OUTCOME_ORDER.map(outcomeBadge))),
        specimen("Explanation source", h("div", { class: "row" }, Object.keys(Core.SOURCE).map(sourceBadge))),
        specimen("Method", h("div", { class: "row" }, methodBadge()))) }),

      card({ title: "Buttons", body: h("div", { class: "stack" },
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

      card({ title: "Callouts", body: h("div", { class: "stack" },
        callout({ tone: "info", icon: "info", title: "Information", text: "Neutral context for the reviewer." }),
        callout({ tone: "unknown", icon: "shield-alert", title: "Flagged for injection", text: "Instruction-like text was found; this claim's text never reaches the model." }),
        callout({ tone: "fail", icon: "alert-triangle", title: "Audit chain invalid", text: "A broken link was found." })) }),

      sample ? card({ title: "Life cycle", meta: sample.claim.claim_id, body:
        lifecycleStrip(Core.lifecycle(sample, decisions()), { label: `Life cycle of ${sample.claim.claim_id}` }) }) : null,

      sample ? card({ title: "Check grid", meta: sample.claim.claim_id, body: checkGrid(sample.results) }) : null,

      fail ? card({ title: "Evidence table", meta: `${fail.rule_id} on ${fail.claim_id}`, body: evidenceTable(fail.evidence, sample.claim) }) : null,

      card({ title: "Bars", body: bars(Core.ROUTE_ORDER.map((r) => ({
        label: Core.ROUTE[r].label, value: CLAIMS.filter((c) => c.route.route === r).length, tone: Core.ROUTE[r].tone }))) }),

      card({ title: "Table, filter bar and side panel", flush: true, body: h("div", {},
        h("div", { class: "card__body" }, filterBar([{ label: "Route", value: "", options: [["", "All routes"], ...Core.ROUTE_ORDER.map((r) => [r, Core.ROUTE[r].label])], onChange: () => {} }], "5 of 5 claims")),
        table({ caption: "Sample claims", rows: CLAIMS.slice(0, 5),
          columns: [
            { key: "id", label: "Claim", sort: (c) => c.claim.claim_id, render: (c) => h("span", { class: "mono", text: c.claim.claim_id }) },
            { key: "route", label: "Route", sort: (c) => Core.ROUTE_ORDER.indexOf(c.route.route), render: (c) => routeBadge(c.route.route) },
            { key: "amount", label: "Total", num: true, sort: (c) => c.claim.total_amount || 0, render: (c) => Core.money(c.claim.total_amount, c.claim.currency) },
          ],
          onRowClick: (c) => openPanel(c.claim.claim_id, kv([["Route", routeBadge(c.route.route)], ["Submitted", Core.date(c.claim.submission_date)]])) })) }),

      card({ title: "Tabs", body: tabs("components", [
        { key: "a", label: "First", count: 2, render: () => h("p", { text: "First tab content." }) },
        { key: "b", label: "Second", render: () => h("p", { text: "Second tab content." }) }]) }),

      card({ title: "Key / value", body: kv([["Run", DATA.run ? h("span", { class: "mono", text: DATA.run.run_id }) : null], ["Generated from", DATA.sources.results]]) }),

      card({ title: "Empty state", body: emptyState({ icon: "search", title: "Nothing matches", text: "Change or clear the filters." }) }));
  },
});
