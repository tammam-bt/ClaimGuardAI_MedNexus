"use strict";
// Review Queue, a reviewer's home page: the claims routed to review or
// escalation, open ones first, most urgent route first, then oldest
// submission first. The next claim to decide comes first; the table is the
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
      + (outcomes.correction_needed || 0) + (outcomes.awaiting_recheck || 0) + (outcomes.rechecked || 0);

    // The first claim of the list below, as filtered and sorted, that still
    // has a finding to decide.
    const nextHolder = h("div");
    function drawNext(rows) {
      const entry = rows.find((e) => ClaimViews.undecided(e, events));
      if (!entry) {
        fill(nextHolder, callout({ tone: "pass", icon: "check-check", title: "Nothing left to decide in this list",
          text: "Every claim shown below has a decision on each finding. Clear the filters to see the rest of the queue." }));
        return;
      }
      const id = entry.claim.claim_id;
      const [decided, total] = ClaimViews.decidedOf(entry, events);
      fill(nextHolder, card({ title: "Next to decide", meta: "The first claim in the list below with a finding left to decide",
        body: h("div", { class: "next-claim" },
          h("span", { class: "mono next-claim__id", text: id }), routeBadge(entry.route.route),
          fingerprint(Core.current(entry).results, { size: "sm" }),
          h("span", { class: "muted small", text: `${decided} of ${Core.plural(total, "finding")} decided` }),
          linkButton({ href: href("claims", id), label: "Open claim", icon: "arrow-right", variant: "primary" })) }));
    }

    return h("div", { class: "stack" },
      draftsBanner(),
      statRow([
        statCard({ icon: "inbox", tone: "info", label: "Open claims", value: Core.number(open.length),
          caption: "Routed claims not yet ready for submission", href: href("queue") }),
        statCard({ icon: Core.ROUTE.ESCALATE.icon, tone: "fail", label: "Escalate, open", value: Core.number(openByRoute.ESCALATE || 0),
          caption: "A senior reviewer decides", href: href("queue", null, { route: "ESCALATE", show: "open" }) }),
        statCard({ icon: Core.ROUTE.REVIEW.icon, tone: "unknown", label: "Review, open", value: Core.number(openByRoute.REVIEW || 0),
          caption: "Medium- or low-severity findings only", href: href("queue", null, { route: "REVIEW", show: "open" }) }),
        statCard({ icon: Core.OUTCOME.to_review.icon, tone: "neutral", label: "Not started", value: Core.number(outcomes.to_review || 0),
          caption: `${Core.number(inProgress)} in progress`, href: href("queue", null, { stage: "to_review", show: "open" }) }),
      ]),
      nextHolder,
      ClaimViews.list({ pageKey: "queue", base: routed, params: route.params, defaultShow: "open", onOrder: drawNext }),
      card({ body: h("details", { class: "disclosure" }, h("summary", { text: "How claims reach this queue" }), routingRules()) }));
  },
});
