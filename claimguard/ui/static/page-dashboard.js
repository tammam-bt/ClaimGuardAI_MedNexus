"use strict";
// Dashboard: the run as a command center. The run's eight-stage life cycle is
// its spine; every number opens the list it counts, and every card names the
// file it comes from: the run manifest, the results (and the routes computed
// from them), the audit log, or the drafts in this browser. Nothing here is
// a trend, a turnaround or a workload: one run has no data for them.

const Dashboard = (function () {
  // Where a number comes from, in the words each card uses.
  const FROM = {
    manifest: "run manifest",
    results: "results",
    routes: "results, routed by the fixed rules",
    review: "results, audit log and drafts in this browser",
    audit: "audit log",
    browser: "this browser",
  };

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
    // A rule opens the claims it failed or could not assess.
    return table({ caption: "Rules most often failing or unassessed", rows,
      empty: emptyState({ icon: "check-check", title: "No rule failed", text: "Every check passed or did not apply, so no claim needs a review.",
        action: linkButton({ href: href("claims"), label: "See every claim", icon: "arrow-right" }) }),
      rowHref: (x) => href("claims", null, { rule: x.rule.rule_id }),
      columns: [
        { key: "rule", label: "Rule", render: (x) => h("span", {}, h("span", { class: "mono", text: x.rule.rule_id }), ` ${x.rule.title}`) },
        { key: "severity", label: "Severity", render: (x) => severityBadge(x.rule.severity) },
        { key: "fail", label: "Failed", num: true, sort: (x) => x.fail, render: (x) => Core.number(x.fail) },
        { key: "unable", label: "Unable", num: true, sort: (x) => x.unable, render: (x) => Core.number(x.unable) },
      ] });
  }

  // Where the review stands: each claim's state, each a link to its list.
  function progressCard(f) {
    const routed = CLAIMS.filter((c) => c.route.reasons.length).length;
    const body = routed
      ? bars(Core.OUTCOME_ORDER.filter((k) => k !== "rechecked" || f.outcomes[k]).map((k) => ({
        label: Core.OUTCOME[k].label, value: f.outcomes[k], tone: Core.OUTCOME[k].tone, href: href("claims", null, { stage: k }) })))
      : emptyState({ icon: "check-check", title: "Nothing to review", text: "Every claim passed its checks or had nothing to decide.",
        action: linkButton({ href: href("claims", null, { stage: "ready" }), label: "See the ready claims", icon: "arrow-right" }) });
    return card({ title: "Where the review stands", meta: `Source: ${FROM.review}`, body });
  }

  function auditCard() {
    if (!DATA.audit) {
      return card({ title: "Audit log", meta: `Source: ${FROM.audit}`, body: emptyState({ icon: "history", title: "No audit log",
        text: "This page was built without the run's audit log, so it cannot show what was recorded. Ask an administrator for a page built with it." }) });
    }
    // A reviewer does not see run events: the card then shows the chain's
    // status and the way to the log, nothing that reads as missing.
    const latest = DATA.audit.events.filter((row) => canSeeEvent(row.event)).slice(-5).reverse();
    return card({ title: "Audit log", meta: `Source: ${FROM.audit}`,
      body: h("div", { class: "stack" },
        h("div", { class: "row row--between" }, DATA.audit.valid
          ? badge(`Chain valid · ${Core.plural(Core.number(DATA.audit.count), "event")}`, { tone: "pass", icon: "lock" })
          : badge("Chain INVALID", { tone: "fail", icon: "alert-triangle" }),
        linkButton({ href: href("audit"), label: "Open audit log", icon: "arrow-right", variant: "ghost" })),
        latest.map((row) => {
          const e = row.event || {};
          return h("div", { class: "small" },
            h("div", { class: "row" }, eventBadge(e),
              e.claim_id ? h("a", { class: "mono", href: href("claims", e.claim_id), text: e.claim_id }) : null),
            h("div", { class: "muted", text: `#${row.sequence} · ${Core.datetime(row.recorded_at)}` }));
        })) });
  }

  // Decisions saved here and not yet in the audit log.
  function draftsCard() {
    const n = State.drafts.length;
    const claims = new Set(State.drafts.map((d) => d.claim_id)).size;
    return card({ title: "Your drafts", meta: `Source: ${FROM.browser}`, body: n
      ? h("div", { class: "stack" },
        h("p", { class: "small", text: `${Core.plural(n, "decision")} on ${Core.plural(claims, "claim")}, not in the audit log until an administrator appends them.` }),
        h("div", { class: "row" }, button({ label: `Download decisions (${n})`, icon: "download", onClick: downloadDecisions })))
      : emptyState({ icon: "user", title: "No draft in this browser", text: "Decisions you save on a claim wait here until they are downloaded.",
        action: linkButton({ href: href("queue"), label: "Open the Review Queue", icon: "arrow-right" }) }) });
  }

  function rejectedCard() {
    const rows = DATA.rejected;
    return card({ title: "Rejected at ingestion", meta: `${rows.length ? `${Core.plural(rows.length, "record")} · ` : ""}Source: ${FROM.manifest}`,
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

  function scrollTo(id) {
    const el = document.getElementById(id);
    if (el) { el.setAttribute("tabindex", "-1"); el.scrollIntoView({ behavior: scrollBehavior(), block: "start" }); el.focus({ preventScroll: true }); }
  }

  function render(route) {
    const events = decisions();
    const f = Core.funnel(DATA, events);
    const routed = CLAIMS.filter((c) => c.route.reasons.length).length;
    const open = CLAIMS.length - f.outcomes.ready;
    // Each stage of the life cycle opens what it counts.
    const toPage = { received: ["dashboard", "sec-rejected"], ingested: ["dashboard", "sec-rejected"], checked: ["claims"],
      screened: ["claims", null, { flag: "flagged" }], explained: ["queue"], routed: ["claims"], review: ["queue"],
      outcome: ["claims", null, { stage: "ready" }] };
    // "Rejected at ingestion" links here with ?focus=rejected.
    if (route && route.params.focus === "rejected") queueMicrotask(() => scrollTo("sec-rejected"));

    return h("div", { class: "stack stagger" },
      statRow([
        statCard({ icon: "inbox", tone: "unknown", label: "Routed for review", value: Core.number(routed),
          caption: `${Core.number(open)} still open`, source: FROM.routes, href: href("queue") }),
        statCard({ icon: Core.OUTCOME.ready.icon, tone: "pass", label: "Ready for submission", value: Core.number(f.outcomes.ready),
          caption: "Pre-check passed or settled; not payer approval", source: FROM.review, href: href("claims", null, { stage: "ready" }) }),
        statCard({ icon: "shield-alert", tone: "unknown", label: "Flagged for injection", value: Core.number(f.flagged),
          caption: "All 15 rules still ran; text withheld from the model", source: FROM.manifest, href: href("claims", null, { flag: "flagged" }) }),
        statCard({ icon: "file-x", tone: f.rejected ? "fail" : "neutral", label: "Rejected at ingestion", value: Core.number(f.rejected),
          caption: `Of ${Core.plural(Core.number(f.received), "record")} received`, source: FROM.manifest, href: href("dashboard", null, { focus: "rejected" }) }),
      ]),
      card({ title: "Life cycle of this run", meta: "Source: run manifest, results, audit log and this browser", body: lifecycleStrip(Core.runStages(DATA, events), {
        label: "Life cycle of this run",
        onPick: (s) => {
          const [key, anchor, params] = toPage[s.key];
          if (key === "dashboard") scrollTo(anchor);
          else go(key, null, params);
        },
      }) }),
      h("div", { class: "grid grid--main-side" },
        h("div", { class: "stack" },
          progressCard(f),
          card({ title: "Routes", meta: `Source: ${FROM.routes}`, body: bars(Core.ROUTE_ORDER.map((r) => ({
            label: Core.ROUTE[r].label, value: f.routes[r] || 0, tone: Core.ROUTE[r].tone, href: href("claims", null, { route: r }) }))) }),
          card({ title: "Rules most often failing or unassessed", meta: `Source: ${FROM.results}`, flush: true, body: ruleTable() })),
        h("div", { class: "stack" }, draftsCard(), auditCard())),
      Object.assign(rejectedCard(), { id: "sec-rejected" }));
  }

  return { render };
})();

registerPage({
  key: "dashboard",
  label: "Dashboard",
  icon: "layout-dashboard",
  subtitle: "Where the review stands, and where each number comes from.",
  render: (route) => Dashboard.render(route),
});
