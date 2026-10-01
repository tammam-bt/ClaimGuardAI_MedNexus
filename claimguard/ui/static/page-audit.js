"use strict";
// Audit Logs: the run's hash-chained audit log (claimguard.audit.chain), as
// verified when this page was built. Tamper-evident, not immutable (doc 10).

const AuditPage = (function () {
  const COMMANDS = [
    "# Add the decisions downloaded from this page to the chain (checked first; one bad decision writes nothing):",
    "python -m claimguard.ui.decisions --decisions review_decisions_<run>.jsonl --log outputs/audit.jsonl \\",
    "    --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl",
    "",
    "# Correct a claim: version 2 is checked again by all 15 rules and recorded in the chain:",
    "python -m claimguard.review.correct --claims data/development/claims.jsonl --claim-id <CLAIM> \\",
    "    --changes fix.json --actor \"<name>\" --reason \"<why>\" --log outputs/audit.jsonl --output outputs/corrections",
    "",
    "# Then rebuild this page with --audit-log outputs/audit.jsonl --corrections outputs/corrections",
  ].join("\n");

  function eventPanel(row) {
    const e = row.event;
    openPanel(`Event #${row.sequence}`, h("div", { class: "stack" },
      h("div", { class: "row" }, eventBadge(e)),
      h("p", { text: eventSummary(e) }),
      kv([
        ["Sequence", Core.number(row.sequence)],
        ["Recorded", Core.datetime(row.recorded_at)],
        ["Hash", h("span", { class: "mono small", text: row.hash })],
        ["Previous hash", h("span", { class: "mono small", text: row.previous_hash })],
        e.claim_id ? ["Claim", h("a", { href: href("claims", e.claim_id), class: "mono", text: e.claim_id })] : null,
        e.run_id ? ["Run", h("span", { class: "mono small", text: e.run_id })] : null,
      ]),
      h("span", { class: "label", text: "Recorded fields (as written in the chain)" }),
      h("pre", { class: "untrusted", text: JSON.stringify(e, null, 2) })));
  }

  function render(route) {
    const audit = DATA.audit;
    if (!audit) {
      return card({ body: emptyState({ icon: "history", title: "No audit log given",
        text: "Run python -m claimguard.run with --audit-log outputs/audit.jsonl, then build this page with the same --audit-log." }) });
    }
    const rows = audit.events;
    const types = Core.count(rows, (r) => r.event.event);
    const visible = rows.filter((r) => canSeeEvent(r.event));
    const f = Object.assign({ type: "", claim: "" }, route.params);
    const holder = h("div");
    const count = h("span", { class: "filters__count", role: "status" });

    function draw() {
      const q = f.claim.trim().toLowerCase();
      const shown = visible.filter((r) => (!f.type || r.event.event === f.type)
        && (!q || String(r.event.claim_id || "").toLowerCase().includes(q))).slice().reverse();
      count.textContent = `${Core.number(shown.length)} of ${Core.plural(visible.length, "event")}`;
      history.replaceState(null, "", href("audit", null, f));
      fill(holder, table({ caption: "Audit events, latest first", rows: shown, onRowClick: eventPanel,
        empty: emptyState({ icon: "search", title: "No event matches", text: "Change or clear the filters." }),
        columns: [
          { key: "seq", label: "#", num: true, sort: (r) => r.sequence, render: (r) => Core.number(r.sequence) },
          { key: "time", label: "Recorded", sort: (r) => r.recorded_at, render: (r) => Core.datetime(r.recorded_at) },
          { key: "type", label: "Event", sort: (r) => r.event.event, render: (r) => eventBadge(r.event) },
          { key: "claim", label: "Claim", render: (r) => (r.event.claim_id
            ? h("a", { href: href("claims", r.event.claim_id), class: "mono", text: r.event.claim_id, onClick: (ev) => ev.stopPropagation() })
            : h("span", { class: "muted", text: "—" })) },
          { key: "summary", label: "What was recorded", render: (r) => h("span", { class: "small", text: eventSummary(r.event) }) },
          { key: "hash", label: "Hash", render: (r) => h("span", { class: "mono small", text: Core.shortHash(r.hash), title: r.hash }) },
        ] }));
    }

    const typeOptions = [["", "All event types"], ...Object.keys(Core.EVENT)
      .filter((t) => types[t] && (can("view_run_events") || !RUN_EVENT_TYPES.includes(t)))
      .map((t) => [t, `${Core.EVENT[t].label} (${types[t]})`])];
    const filters = filterBar([{ label: "Event type", value: f.type, options: typeOptions, onChange: (v) => { f.type = v; draw(); } }], null,
      [searchField({ placeholder: "Claim ID", label: "Filter by claim", value: f.claim, onInput: (v) => { f.claim = v; draw(); } }), count]);
    draw();

    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "history", tone: "info", label: "Events in the chain", value: Core.number(audit.count),
          caption: audit.anchored ? "Head anchored beside the log" : "No anchor file" }),
        audit.valid
          ? statCard({ icon: "lock", tone: "pass", label: "Integrity", value: "Valid", caption: `Head ${Core.shortHash(audit.head)}` })
          : statCard({ icon: "alert-triangle", tone: "fail", label: "Integrity", value: "INVALID", caption: "See the reason below" }),
        statCard({ icon: "user", tone: "pass", label: "Review decisions", value: Core.number(types.review_decision || 0), caption: "Appended to the chain" }),
        statCard({ icon: "refresh", tone: "info", label: "New claim versions", value: Core.number(types.version_created || 0), caption: "Corrections rechecked" }),
      ]),
      audit.valid
        ? callout({ tone: "pass", icon: "lock", title: "Chain verified when this page was built",
          text: `Every event links to the one before it by SHA-256, and ${audit.anchored ? "the anchored head matches, so no event was removed or rewritten" : "there is no anchor file, so removing events from the end would not be detected"}. Tamper-evident, not immutable: whoever controls both the log and its anchor can rewrite both (doc 10).` })
        : callout({ tone: "fail", icon: "alert-triangle", title: "Chain INVALID", role: "alert",
          text: `${audit.error}. Do not trust these events until the log is restored from a trusted copy.` }),
      can("view_run_events") ? null : callout({ tone: "neutral", icon: "user",
        title: `${Core.plural(rows.length - visible.length, "run event")} hidden for your role`,
        text: "Runs, rejections, injection flags and model failures need the view_run_events permission, which admins have. Switch “View as” to Admin to see them. This is a demonstration without login, not a security control (doc 10)." }),
      card({ title: "Events", meta: h("span", { class: "mono small", text: audit.log }), flush: true,
        body: h("div", {}, h("div", { class: "card__body" }, filters), holder) }),
      card({ title: "Adding decisions and corrections", body: h("pre", { class: "untrusted", text: COMMANDS }) }));
  }

  return { render, eventPanel };
})();

registerPage({
  key: "audit",
  label: "Audit Logs",
  icon: "history",
  subtitle: "The hash-chained record of every run event and decision.",
  render: (route) => AuditPage.render(route),
});
