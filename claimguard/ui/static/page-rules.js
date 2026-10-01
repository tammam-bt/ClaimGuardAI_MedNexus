"use strict";
// Rules: the 15 rules of the fictional rulebook (rules/rules.json), read-only.
// A rule is fixed and versioned (fictional-rulebook/R003@1.0.0): changing one
// means a new rulebook version, never a setting in this page.

const RulesPage = (function () {
  // The policy fields each rule reads, from the rule code in claimguard/rules/.
  const POLICY_FIELDS = {
    R005: ["allowed_providers"],
    R008: ["auth_required_services"],
    R009: ["auth_required_services"],
    R010: ["required_documents"],
    R013: ["max_unit_price", "max_quantity_per_line"],
    R014: ["submission_window_days"],
    R015: ["currency"],
  };

  function statusCountsFor(ruleId) {
    return Core.statusCounts(CLAIMS.map((c) => c.results.find((r) => r.rule_id === ruleId)).filter(Boolean));
  }
  function metricsFor(ruleId) {
    return DATA.evaluation ? DATA.evaluation.by_rule[ruleId] || null : null;
  }

  function policyValue(v) {
    if (Array.isArray(v)) return h("span", { class: "mono small", text: v.join(", ") });
    if (v && typeof v === "object") {
      return h("div", { class: "stack", style: { gap: "2px" } },
        Object.entries(v).map(([k, x]) => h("span", { class: "mono small", text: `${k}: ${x}` })));
    }
    return h("span", { class: "mono small", text: String(v) });
  }

  function policyCard(ruleId) {
    const fields = POLICY_FIELDS[ruleId];
    if (!fields) {
      return card({ title: "Policy values used", body: h("p", { class: "muted small", text: "This rule reads no policy value." }) });
    }
    const policies = Object.values(DATA.policies);
    return card({ title: "Policy values used", meta: "rules/policies.json", flush: true, body: table({
      caption: "Policy values this rule reads", rows: fields,
      columns: [
        { key: "field", label: "Field", render: (k) => h("span", { class: "mono", text: k }) },
        ...policies.map((p) => ({ key: p.policy_id, label: `${p.policy_id} ${p.version}`, render: (k) => policyValue(p[k]) })),
      ] }) });
  }

  function performanceCard(ruleId) {
    const m = metricsFor(ruleId);
    if (!m) {
      return card({ title: "Performance", body: emptyState({ icon: "bar-chart", title: "No expected results given",
        text: "Pass --gold to claimguard.ui to score this run against the expected results." }) });
    }
    return card({ title: "Performance", meta: "Official scorer", body: h("div", { class: "stack" },
      kv([
        ["Status accuracy", Core.percent(m.status_accuracy)],
        ["Issue precision", Core.percent(m.issue_precision)],
        ["Issue recall", Core.percent(m.issue_recall)],
        ["Issue F1", Core.percent(m.issue_f1)],
        ["False-alarm rate", Core.percent(m.false_alarm_rate)],
        ["TP · FP · FN · TN", `${m.tp} · ${m.fp} · ${m.fn} · ${m.tn}`],
        ["False / missed abstentions", `${m.false_abstentions} · ${m.missed_abstentions}`],
      ])) });
  }

  function matrixCard(ruleId) {
    if (!DATA.evaluation) return null;
    return card({ title: "Expected against predicted", meta: `${ruleId} on ${Core.plural(CLAIMS.length, "claim")}`,
      body: confusionMatrix(DATA.evaluation.confusion_by_rule[ruleId], `${ruleId}: expected against predicted`) });
  }

  function list() {
    const sev = Core.count(DATA.rules, (r) => r.severity);
    const implemented = DATA.rules.filter((r) => r.implemented).length;
    const known = DATA.rules.filter((r) => r.implemented !== null && r.implemented !== undefined).length;
    const rows = DATA.rules.map((r) => ({ rule: r, counts: statusCountsFor(r.rule_id), m: metricsFor(r.rule_id) }));
    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "list-checks", tone: "info", label: "Rules", value: Core.number(DATA.rules.length), caption: "Fixed fictional rulebook" }),
        statCard({ icon: "cpu", tone: "pass", label: "Implemented", value: known ? `${implemented} / ${DATA.rules.length}` : "—",
          caption: known ? "From the run manifest" : "No run manifest" }),
        statCard({ icon: Core.ROUTE.ESCALATE.icon, tone: "fail", label: "High severity", value: Core.number(sev.high || 0), caption: "A failure escalates the claim" }),
        statCard({ icon: Core.ROUTE.REVIEW.icon, tone: "unknown", label: "Medium severity", value: Core.number(sev.medium || 0),
          caption: "A failure sends the claim to review" }),
      ]),
      card({ title: "All rules", meta: "Every rule is deterministic: no model and no probability", flush: true, body: table({
        caption: "The 15 rules", rows, onRowClick: (x) => go("rules", x.rule.rule_id),
        columns: [
          { key: "id", label: "Rule", sort: (x) => x.rule.rule_id, render: (x) => h("span", {},
            h("span", { class: "mono", text: x.rule.rule_id }), ` ${x.rule.title}`) },
          { key: "severity", label: "Severity", sort: (x) => x.rule.severity, render: (x) => severityBadge(x.rule.severity) },
          { key: "method", label: "Method", render: () => methodBadge() },
          { key: "state", label: "In this run", render: (x) => (x.rule.implemented === false
            ? statusBadge("NOT_IMPLEMENTED") : x.rule.implemented ? badge("Implemented", { tone: "pass", icon: "cpu" }) : h("span", { class: "muted", text: "—" })) },
          { key: "fail", label: "Failed", num: true, sort: (x) => x.counts.FAIL, render: (x) => Core.number(x.counts.FAIL) },
          { key: "unable", label: "Unable", num: true, sort: (x) => x.counts.UNABLE_TO_ASSESS, render: (x) => Core.number(x.counts.UNABLE_TO_ASSESS) },
          { key: "na", label: "N/A", num: true, sort: (x) => x.counts.NOT_APPLICABLE, render: (x) => Core.number(x.counts.NOT_APPLICABLE) },
          { key: "acc", label: "Status accuracy", num: true, sort: (x) => (x.m ? x.m.status_accuracy : -1),
            render: (x) => (x.m ? Core.percent(x.m.status_accuracy) : "—") },
          { key: "version", label: "Version", render: (x) => h("span", { class: "mono small", text: x.rule.version }) },
        ] }) }));
  }

  function detail(ruleId, route) {
    const rule = RULE_BY_ID.get(ruleId);
    if (!rule) {
      return card({ body: emptyState({ icon: "search", title: `No rule ${ruleId}`, text: "The rulebook has R001 to R015.",
        action: linkButton({ href: href("rules"), label: "All rules", icon: "chevron-left" }) }) });
    }
    const counts = statusCountsFor(ruleId);
    const concerned = CLAIMS.filter((c) => c.results.some((r) => r.rule_id === ruleId && (r.status === "FAIL" || r.status === "UNABLE_TO_ASSESS")));
    const i = DATA.rules.findIndex((r) => r.rule_id === ruleId);
    const prev = DATA.rules[i - 1], next = DATA.rules[i + 1];
    return h("div", { class: "stack" },
      h("div", { class: "row row--between" },
        linkButton({ href: href("rules"), label: "All rules", icon: "chevron-left", variant: "ghost" }),
        h("div", { class: "row" },
          prev ? linkButton({ href: href("rules", prev.rule_id), label: prev.rule_id, icon: "chevron-left" }) : null,
          next ? linkButton({ href: href("rules", next.rule_id), label: next.rule_id, icon: "chevron-right" }) : null)),
      h("div", { class: "claim-head" },
        h("div", { class: "claim-head__title" }, h("h2", { text: rule.rule_id }), h("span", { class: "card__title", text: rule.title })),
        h("div", { class: "row" }, severityBadge(rule.severity), methodBadge(),
          rule.implemented === false ? statusBadge("NOT_IMPLEMENTED") : null,
          badge(rule.source, { tone: "neutral" }))),
      h("div", { class: "grid grid--main-side" },
        h("div", { class: "stack" },
          card({ title: "Rule logic", meta: "Quoted from the rulebook", body: h("div", { class: "stack" },
            h("p", { class: "logic", text: rule.logic }),
            h("div", { class: "finding__section" }, h("span", { class: "label", text: "Corrective action" }), h("p", { text: rule.corrective_action }))) }),
          policyCard(ruleId)),
        h("div", { class: "stack" },
          card({ title: "This run", meta: `${Core.number(CLAIMS.length)} claims`, body: bars(Core.STATUS_ORDER.map((s) => ({
            label: Core.STATUS[s].label, value: counts[s],
            tone: { fail: "fail", unknown: "unknown", pass: "pass", neutral: "neutral" }[Core.STATUS[s].tone] }))) }),
          performanceCard(ruleId))),
      matrixCard(ruleId),
      card({ title: "Claims with a finding on this rule", meta: Core.plural(concerned.length, "claim"), flush: !!concerned.length,
        body: concerned.length
          ? ClaimViews.list({ pageKey: "rules", pageId: ruleId, base: concerned, params: route.params, hide: ["rule", "show"], bare: true })
          : emptyState({ icon: "check-check", title: "No finding in this run", text: "Every claim passed this check or it did not apply." }) }));
  }

  return { list, detail };
})();

registerPage({
  key: "rules",
  label: "Rules",
  icon: "list-checks",
  subtitle: "The 15 fixed rules of the fictional rulebook. Read-only.",
  render: (route) => (route.id ? RulesPage.detail(route.id, route) : RulesPage.list()),
});
