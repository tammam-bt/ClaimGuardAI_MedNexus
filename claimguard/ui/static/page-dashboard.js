"use strict";
// Dashboard: the run at a glance. Every number comes from the run's files:
// the manifest, the results, the routes computed from them, the audit log,
// and the decisions saved in this browser.

const Dashboard = (function () {
  function ruleTable() {
    const byRule = new Map(DATA.rules.map((r) => [r.rule_id, { rule: r, fail: 0, unable: 0 }]));
    for (const c of CLAIMS) {
      for (const r of c.results) {
        const row = byRule.get(r.rule_id);
        if (r.status === "FAIL") row.fail += 1;
        else if (r.status === "UNABLE_TO_ASSESS") row.unable += 1;
      }
    }
    const rows = Array.from(byRule.values()).filter((x) => x.fail || x.unable)
      .sort((a, b) => (b.fail + b.unable) - (a.fail + a.unable)).slice(0, 8);
    return table({ caption: "Rules most often failing or unassessed", rows,
      empty: emptyState({ icon: "check-check", title: "No rule failed", text: "Every check passed or did not apply." }),
      onRowClick: (x) => go("rules", x.rule.rule_id),
      columns: [
        { key: "rule", label: "Rule", render: (x) => h("span", {}, h("span", { class: "mono", text: x.rule.rule_id }), ` ${x.rule.title}`) },
        { key: "severity", label: "Severity", render: (x) => severityBadge(x.rule.severity) },
        { key: "fail", label: "Failed", num: true, sort: (x) => x.fail, render: (x) => Core.number(x.fail) },
        { key: "unable", label: "Unable", num: true, sort: (x) => x.unable, render: (x) => Core.number(x.unable) },
      ] });
  }

  function eventsCard() {
    if (!DATA.audit) {
      return card({ title: "Latest audit events", body: emptyState({ icon: "history", title: "No audit log",
        text: "No audit log was loaded for this run." }) });
    }
    // A reviewer does not see run events: the card then shows the chain's
    // status and the way to the log, nothing that reads as missing.
    const latest = DATA.audit.events.filter((row) => canSeeEvent(row.event)).slice(-5).reverse();
    return card({ title: "Latest audit events",
      actions: linkButton({ href: href("audit"), label: "Open audit log", icon: "arrow-right", variant: "ghost" }),
      body: h("div", { class: "stack" },
        h("div", { class: "row" }, DATA.audit.valid
          ? badge(`Chain valid · ${Core.plural(Core.number(DATA.audit.count), "event")}`, { tone: "pass", icon: "lock" })
          : badge("Chain INVALID", { tone: "fail", icon: "alert-triangle" })),
        latest.map((row) => {
          const e = row.event || {};
          const t = Core.EVENT[e.event] || { label: String(e.event), icon: "info", tone: "neutral" };
          return h("div", { class: "small" },
            h("div", { class: "row" }, badge(t.label, { tone: t.tone, icon: t.icon }), e.claim_id ? h("span", { class: "mono", text: e.claim_id }) : null),
            h("div", { class: "muted", text: `#${row.sequence} · ${Core.datetime(row.recorded_at)}` }));
        })) });
  }

  function rejectedCard() {
    const rows = DATA.rejected;
    return card({ title: "Rejected at ingestion", meta: rows.length ? Core.plural(rows.length, "record") : null,
      flush: rows.length > 0,
      body: rows.length
        ? table({ caption: "Records rejected at ingestion", rows, columns: [
          { key: "line", label: "Line", num: true, sort: (e) => e.provenance.line_number, render: (e) => Core.number(e.provenance.line_number) },
          { key: "stage", label: "Stage", sort: (e) => e.stage, render: (e) => badge(e.stage, { tone: "fail" }) },
          { key: "reason", label: "Reason", render: (e) => e.reason },
          { key: "claim", label: "Claim", render: (e) => h("span", { class: "mono" }, value(e.claim_id)) },
          { key: "source", label: "Source", render: (e) => h("span", { class: "mono small", text: e.provenance.source }) },
        ] })
        : emptyState({ icon: "file-check", title: "No record was rejected",
          text: "Every record passed the ingestion contract. A rejected record is reported here, never dropped silently." }) });
  }

  function render() {
    const events = decisions();
    const f = Core.funnel(DATA, events);
    const counts = Core.statusCounts(CLAIMS.flatMap((c) => c.results));
    const routed = CLAIMS.filter((c) => c.route.reasons.length).length;
    const open = CLAIMS.length - f.outcomes.ready;
    const toPage = { received: ["dashboard", "sec-rejected"], ingested: ["dashboard", "sec-rejected"], checked: ["claims"],
      screened: ["claims", null, { flag: "flagged" }], explained: ["queue"], routed: ["claims"], review: ["queue"],
      outcome: ["claims", null, { stage: "ready" }] };

    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "arrow-down-line", tone: "info", label: "Records received", value: Core.number(f.received),
          caption: f.rejected ? `${Core.plural(f.rejected, "record")} rejected at ingestion` : "None rejected at ingestion" }),
        statCard({ icon: "inbox", tone: "unknown", label: "Routed for review", value: Core.number(routed),
          caption: `${Core.number(open)} still open`, href: href("queue") }),
        statCard({ icon: Core.OUTCOME.ready.icon, tone: "pass", label: "Ready for submission", value: Core.number(f.outcomes.ready),
          caption: "Pre-check passed or settled; not payer approval", href: href("claims", null, { stage: "ready" }) }),
        statCard({ icon: "shield-alert", tone: "unknown", label: "Flagged for injection", value: Core.number(f.flagged),
          caption: "All 15 rules still ran; text withheld from the model", href: href("claims", null, { flag: "flagged" }) }),
      ]),
      card({ title: "Life cycle of this run", body: lifecycleStrip(Core.runStages(DATA, events), {
        label: "Life cycle of this run",
        onPick: (s) => {
          const [key, anchor, params] = toPage[s.key];
          if (key === "dashboard") { const el = document.getElementById(anchor); if (el) el.scrollIntoView({ behavior: "smooth" }); }
          else go(key, null, params);
        },
      }) }),
      h("div", { class: "grid grid--main-side" },
        h("div", { class: "stack" },
          card({ title: "Routes", body: bars(Core.ROUTE_ORDER.map((r) => ({
            label: Core.ROUTE[r].label, value: f.routes[r] || 0, tone: Core.ROUTE[r].tone, href: href("claims", null, { route: r }) }))) }),
          card({ title: "Results", meta: `${Core.number(CLAIMS.length * 15)} checks`, body: bars(statusBars(counts)) }),
          card({ title: "Rules most often failing or unassessed", flush: true, body: ruleTable() })),
        h("div", { class: "stack" }, eventsCard())),
      Object.assign(rejectedCard(), { id: "sec-rejected" }));
  }

  return { render };
})();

registerPage({
  key: "dashboard",
  label: "Dashboard",
  icon: "layout-dashboard",
  subtitle: "The run at a glance: life cycle, routes and results.",
  render: () => Dashboard.render(),
});
