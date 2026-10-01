"use strict";
// Review Queue: the claims routed to review or escalation, open ones first,
// most urgent route first, then oldest submission first. The table is the
// Claims page's, with a preset filter.

registerPage({
  key: "queue",
  label: "Review Queue",
  icon: "inbox",
  subtitle: "Claims routed to review or escalation, most urgent first.",
  render(route) {
    const routed = CLAIMS.filter((c) => c.route.route !== "CLEAR");
    const events = decisions();
    const outcomes = Core.count(routed, (c) => Core.outcome(c, events));
    const open = routed.filter((c) => Core.outcome(c, events) !== "ready");
    const openByRoute = Core.count(open, (c) => c.route.route);
    const inProgress = (outcomes.in_review || 0) + (outcomes.waiting_information || 0)
      + (outcomes.correction_needed || 0) + (outcomes.awaiting_recheck || 0);

    const rules = h("details", { class: "disclosure" },
      h("summary", { text: "How claims reach this queue" }), routingRules());

    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "inbox", tone: "info", label: "Open claims", value: Core.number(open.length),
          caption: `${Core.number(outcomes.to_review || 0)} not started · ${Core.number(inProgress)} in progress`, href: href("queue") }),
        statCard({ icon: Core.ROUTE.ESCALATE.icon, tone: "fail", label: "Escalate, open", value: Core.number(openByRoute.ESCALATE || 0),
          caption: "A senior reviewer decides", href: href("queue", null, { route: "ESCALATE", show: "open" }) }),
        statCard({ icon: Core.ROUTE.REVIEW.icon, tone: "unknown", label: "Review, open", value: Core.number(openByRoute.REVIEW || 0),
          caption: "Medium- or low-severity findings only", href: href("queue", null, { route: "REVIEW", show: "open" }) }),
        statCard({ icon: "download", tone: "pass", label: "Decisions to download", value: Core.number(State.drafts.length),
          caption: "Saved in this browser only" }),
      ]),
      card({ title: "Decisions", meta: "Download to add them to the audit log",
        actions: button({ label: `Download decisions (${State.drafts.length})`, variant: "primary", icon: "download",
          disabled: State.drafts.length === 0, onClick: downloadDecisions }),
        body: rules }),
      ClaimViews.list({ pageKey: "queue", base: routed, params: route.params, defaultShow: "open" }));
  },
});
