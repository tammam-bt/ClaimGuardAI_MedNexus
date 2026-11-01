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

  function ruleRows() {
    const byRule = new Map(DATA.rules.map((r) => [r.rule_id, { rule: r, fail: 0, unable: 0 }]));
    for (const c of CLAIMS) {
      for (const r of c.results) {
        const row = byRule.get(r.rule_id);
        if (r.status === "FAIL") row.fail += 1;
        else if (r.status === "UNABLE_TO_ASSESS") row.unable += 1;
      }
    }
    return Array.from(byRule.values()).filter((x) => x.fail || x.unable)
      .sort((a, b) => (b.fail + b.unable) - (a.fail + a.unable));
  }

  function ruleTable(rows) {
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

  function routeCard(f) {
    const total = CLAIMS.length;
    const radius = 68;
    const routed = (f.routes.ESCALATE || 0) + (f.routes.REVIEW || 0);
    const value = h("strong", { class: "dashboard-route__value", id: "dashboard-route-value", text: Core.number(routed) });
    const label = h("span", { class: "dashboard-route__label", id: "dashboard-route-label", text: "Routed for review" });
    const chart = svg("svg", { class: "dashboard-donut", viewBox: "0 0 180 180", "aria-label": "Claims by route" },
      svg("circle", { class: "dashboard-donut__track", cx: 90, cy: 90, r: radius }));
    const items = Core.ROUTE_ORDER.map((key) => ({
      key,
      route: Core.ROUTE[key],
      value: f.routes[key] || 0,
    }));
    const legendLinks = [];
    let offset = 0;
    const segments = items.map((item) => {
      const start = total ? -90 + offset / total * 360 : -90;
      const sweep = total ? item.value / total * 360 : 0;
      const gap = items.filter((route) => route.value > 0).length > 1 ? Math.min(1.5, sweep / 2) : 0;
      const startAngle = start + gap / 2;
      const endAngle = start + sweep - gap / 2;
      const point = (angle) => {
        const radians = angle * Math.PI / 180;
        return { x: 90 + radius * Math.cos(radians), y: 90 + radius * Math.sin(radians) };
      };
      const first = point(startAngle);
      const last = point(endAngle);
      const full = item.value === total && total > 0;
      const middle = point(startAngle + 180);
      const d = !item.value ? "" : full
        ? `M${first.x},${first.y} A${radius},${radius} 0 1 1 ${middle.x},${middle.y} A${radius},${radius} 0 1 1 ${first.x},${first.y}`
        : `M${first.x},${first.y} A${radius},${radius} 0 ${sweep > 180 ? 1 : 0} 1 ${last.x},${last.y}`;
      const link = svg("a", {
        class: `dashboard-donut__link dashboard-donut__link--${item.key.toLowerCase()}`,
        href: href("claims", null, { route: item.key }),
        tabindex: -1, // the legend beside it holds the same links for the keyboard
        "aria-label": `${item.route.label}: ${Core.number(item.value)} claims`,
      }, svg("path", {
        class: "dashboard-donut__segment",
        d,
        pathLength: 1,
        "stroke-dasharray": "0 1",
      }), svg("title", {}, `${item.route.label}: ${Core.number(item.value)} of ${Core.number(total)} claims`));
      link.addEventListener("mouseenter", () => showRoute(item));
      link.addEventListener("focus", () => showRoute(item));
      link.addEventListener("mouseleave", resetRoute);
      link.addEventListener("blur", resetRoute);
      link.firstChild.dataset.dash = "1 0";
      offset += item.value;
      return link;
    });
    chart.append(...segments);
    requestAnimationFrame(() => chart.querySelectorAll(".dashboard-donut__segment").forEach((segment) => {
      segment.setAttribute("stroke-dasharray", segment.dataset.dash);
    }));

    function showRoute(item) {
      value.textContent = Core.number(item.value);
      label.textContent = `${item.route.label} · ${total ? (100 * item.value / total).toFixed(1) : "0.0"}%`;
      chart.classList.add("is-active");
      chart.querySelectorAll(".dashboard-donut__link").forEach((link) => {
        link.classList.toggle("is-active", link.getAttribute("aria-label").startsWith(`${item.route.label}:`));
      });
      legendLinks.forEach((link) => link.classList.toggle("is-active", link.dataset.route === item.key));
    }
    function resetRoute() {
      value.textContent = Core.number(routed);
      label.textContent = "Routed for review";
      chart.classList.remove("is-active");
      chart.querySelectorAll(".dashboard-donut__link").forEach((link) => link.classList.remove("is-active"));
      legendLinks.forEach((link) => link.classList.remove("is-active"));
    }

    const legend = h("div", { class: "dashboard-route__legend" }, items.map((item) => {
      const percent = total ? (100 * item.value / total).toFixed(1) : "0.0";
      const link = h("a", {
        class: "dashboard-route__item",
        "data-route": item.key,
        href: href("claims", null, { route: item.key }),
        onMouseenter: () => showRoute(item),
        onMouseleave: resetRoute,
        onFocus: () => showRoute(item),
        onBlur: resetRoute,
      },
      h("span", { class: `dashboard-route__dot dashboard-route__dot--${item.key.toLowerCase()}` }),
      h("span", { class: "dashboard-route__name" }, item.route.label, h("span", { class: "muted" }, `${percent}%`)),
      h("strong", { class: "dashboard-route__count" }, Core.number(item.value)));
      legendLinks.push(link);
      return link;
    }));
    return card({ title: "Routing outcomes", meta: `Source: ${FROM.routes}`,
      body: h("div", { class: "dashboard-route" },
        h("div", { class: "dashboard-route__chart" }, chart,
          h("div", { class: "dashboard-route__center", "aria-live": "polite" }, value, label)),
        legend) });
  }

  // Grouped bars: failed and unable-to-assess results for every rule that has
  // any, in rule order. Rules are categories, so nothing joins one to the next.
  function ruleProfile(rows) {
    if (!rows.length) return emptyState({ icon: "check-check", title: "No rule failed",
      text: "Every check passed or did not apply, so no claim needs a review." });
    const ordered = [...rows].sort((a, b) => a.rule.rule_id.localeCompare(b.rule.rule_id));
    const max = Math.max(1, ...ordered.map((row) => Math.max(row.fail, row.unable)));
    return h("div", { class: "dashboard-rules" }, ordered.map((row) => h("a", {
      class: "dashboard-rule",
      href: href("claims", null, { rule: row.rule.rule_id }),
      title: `${row.rule.rule_id} ${row.rule.title}`,
      "aria-label": `${row.rule.rule_id}, ${row.rule.title}: ${Core.number(row.fail)} failed, ${Core.number(row.unable)} unable to assess; view claims`,
    },
    h("span", { class: "mono", text: row.rule.rule_id }),
    h("span", { class: "dashboard-rule__bars" }, [["fail", "escalate"], ["unable", "review"]].map(([key, tone]) => [
      h("span", { class: "bar__track" }, h("span", { class: `bar__fill fill-${tone}`, style: { width: `${100 * row[key] / max}%` } })),
      h("span", { class: "bar__value", text: Core.number(row[key]) }),
    ])))));
  }

  function profileCard(rows) {
    return card({ title: "Rule outcomes profile", meta: `Source: ${FROM.results}`,
      body: rows.length ? h("div", {},
        ruleProfile(rows),
        h("div", { class: "dashboard-profile__legend" },
          h("span", {}, h("i", { class: "dashboard-profile__key dashboard-profile__key--fail" }), "Failed"),
          h("span", {}, h("i", { class: "dashboard-profile__key dashboard-profile__key--unable" }), "Unable to assess")))
        : ruleProfile(rows),
    });
  }

  // Where the review stands: one vertical bar per claim state, each a link to
  // its list. A bar's height is its percent of all claims.
  function progressCard(f) {
    const total = CLAIMS.length;
    const routed = CLAIMS.filter((c) => c.route.reasons.length).length;
    const keys = Core.OUTCOME_ORDER.filter((k) => k !== "rechecked" || f.outcomes[k]);
    const body = routed
      ? h("div", { class: "dashboard-volume" }, keys.map((k) => {
        const outcome = Core.OUTCOME[k];
        const count = f.outcomes[k];
        const percent = total ? (100 * count / total).toFixed(1) : "0.0";
        return h("a", {
          class: "dashboard-volume__item",
          href: href("claims", null, { stage: k }),
          title: `${outcome.label}: ${Core.number(count)} of ${Core.number(total)} claims`,
          "aria-label": `${outcome.label}: ${Core.number(count)} claims, ${percent}%; view claims`,
        },
        h("strong", { class: "dashboard-volume__count" }, Core.number(count)),
        h("span", { class: "dashboard-volume__track" },
          h("span", { class: `dashboard-volume__fill fill-${outcome.tone}${count ? "" : " is-zero"}`,
            style: { height: `${percent}%` } })),
        h("span", { class: "dashboard-volume__label" }, outcome.label),
        h("span", { class: "dashboard-volume__percent" }, `${percent}%`));
      }))
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
        h("p", { class: "small", text: `${Core.plural(n, "decision")} on ${Core.plural(claims, "claim")}. ${draftsWait()}` }),
        draftActions())
      : emptyState({ icon: "user", title: "No draft in this browser", text: `Decisions you save on a claim wait here until they are ${Server.live ? "saved to the audit log" : "downloaded"}.`,
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
    const rows = ruleRows();
    const routed = CLAIMS.filter((c) => c.route.reasons.length).length;
    const open = CLAIMS.length - f.outcomes.ready;
    // Each stage of the life cycle opens what it counts.
    const toPage = { received: ["dashboard", "sec-rejected"], ingested: ["dashboard", "sec-rejected"], checked: ["claims"],
      screened: ["claims", null, { flag: "flagged" }], explained: ["queue"], routed: ["claims"], review: ["queue"],
      outcome: ["claims", null, { stage: "ready" }] };
    // "Rejected at ingestion" links here with ?focus=rejected.
    if (route && route.params.focus === "rejected") queueMicrotask(() => scrollTo("sec-rejected"));

    return h("div", { class: "stack stagger dashboard" },
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
          h("div", { class: "grid grid--2 dashboard__overview" }, routeCard(f), progressCard(f)),
          profileCard(rows),
          card({ title: "Rules most often failing or unassessed", meta: `Source: ${FROM.results}`, flush: true, body: ruleTable(rows.slice(0, 8)) })),
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
