"use strict";
// Evaluation: this run scored against the expected results by the official
// scorer (src/evaluate.py's score(), wrapped by claimguard.evaluation.confusion).
// Nothing here is computed in the page: every number is the scorer's.

const EvaluationPage = (function () {
  const pct = (x) => Core.percent(x);

  function missing() {
    return card({ body: emptyState({ icon: "bar-chart", title: "Not scored",
      text: "Expected results weren't loaded, so this run isn't scored." }) });
  }

  function perRuleTable(ev) {
    const rows = DATA.rules.map((r) => ({ rule: r, m: ev.by_rule[r.rule_id] })).filter((x) => x.m);
    const n = (k) => ({ key: k, label: { tp: "TP", fp: "FP", fn: "FN", tn: "TN" }[k], num: true, sort: (x) => x.m[k], render: (x) => Core.number(x.m[k]) });
    const anyNotImplemented = rows.some((x) => x.m.not_implemented > 0);
    return table({ caption: "Metrics per rule", rows, onRowClick: (x) => go("rules", x.rule.rule_id),
      columns: [
        { key: "rule", label: "Rule", sort: (x) => x.rule.rule_id, render: (x) => h("span", {},
          h("span", { class: "mono", text: x.rule.rule_id }), ` ${x.rule.title}`) },
        { key: "acc", label: "Status accuracy", num: true, sort: (x) => x.m.status_accuracy, render: (x) => pct(x.m.status_accuracy) },
        { key: "p", label: "Precision", num: true, sort: (x) => x.m.issue_precision ?? -1, render: (x) => pct(x.m.issue_precision) },
        { key: "r", label: "Recall", num: true, sort: (x) => x.m.issue_recall ?? -1, render: (x) => pct(x.m.issue_recall) },
        { key: "f1", label: "F1", num: true, sort: (x) => x.m.issue_f1 ?? -1, render: (x) => pct(x.m.issue_f1) },
        n("tp"), n("fp"), n("fn"), n("tn"),
        { key: "abst", label: "False / missed abst.", num: true, sort: (x) => x.m.false_abstentions + x.m.missed_abstentions,
          render: (x) => `${x.m.false_abstentions} / ${x.m.missed_abstentions}` },
        anyNotImplemented ? { key: "ni", label: "Not impl.", num: true, sort: (x) => x.m.not_implemented, render: (x) => Core.number(x.m.not_implemented) } : null,
      ].filter(Boolean) });
  }

  function mismatchCard(ev) {
    const rows = ev.mismatches;
    return card({ title: "Disagreements with the expected results", meta: Core.plural(rows.length, "pair"), flush: rows.length > 0,
      body: rows.length
        ? table({ caption: "Claim-rule pairs whose status differs from the expected one", rows,
          onRowClick: (x) => go("claims", x.claim_id),
          columns: [
            { key: "claim", label: "Claim", sort: (x) => x.claim_id, render: (x) => h("span", { class: "mono", text: x.claim_id }) },
            { key: "rule", label: "Rule", sort: (x) => x.rule_id, render: (x) => h("span", {}, h("span", { class: "mono", text: x.rule_id }), ` ${ruleName(x.rule_id)}`) },
            { key: "expected", label: "Expected", render: (x) => statusBadge(x.expected) },
            { key: "predicted", label: "Predicted", render: (x) => statusBadge(x.predicted) },
          ] })
        : emptyState({ icon: "check-check", title: "No disagreement",
          text: `Every one of the ${Core.number(ev.overall.count)} claim-rule pairs has the expected status.` }) });
  }

  function aiCard() {
    const ai = DATA.run && DATA.run.ai ? DATA.run.ai.summary : null;
    if (!ai) {
      return card({ title: "AI explanations", body: emptyState({ icon: "sparkles", title: "Not run",
        text: "This run has no explanations." }) });
    }
    const fallbacks = Object.entries(ai.failures || {});
    return card({ title: "AI explanations", meta: "Not scored here", body: h("div", { class: "stack" },
      h("p", { class: "small", text: explainerLine() }),
      kv([
        ["Findings", Core.number(ai.findings)],
        ["By source", Object.entries(ai.by_source).map(([k, v]) => {
          const kind = k === "provider" && ai.provider === "mock" ? "mock" : k;
          return `${(Core.SOURCE[kind] || { label: k }).label}: ${Core.number(v)}`;
        }).join(" · ")],
        ["Fallbacks", fallbacks.length ? fallbacks.map(([k, v]) => `${k}: ${v}`).join(" · ") : "None"],
      ]),
      callout({ tone: "info", icon: "info", title: "Explanation quality is scored by people",
        text: "The scorer checks statuses and evidence only. Explanations are scored by hand, on the 25 exercise cases." })) });
  }

  function render() {
    const ev = DATA.evaluation;
    if (!ev) return missing();
    const o = ev.overall;
    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "check-check", tone: "pass", label: "Status accuracy", value: pct(o.status_accuracy),
          caption: `${Core.number(o.count)} claim-rule pairs` }),
        statCard({ icon: Core.STATUS.FAIL.icon, tone: "fail", label: "Issue F1", value: pct(o.issue_f1),
          caption: `Precision ${pct(o.issue_precision)} · recall ${pct(o.issue_recall)}` }),
        statCard({ icon: "alert-triangle", tone: "unknown", label: "False-alarm rate", value: pct(o.false_alarm_rate),
          caption: `${Core.number(o.fp)} false FAIL among ${Core.number(o.fp + o.tn)} non-FAIL pairs` }),
        statCard({ icon: "file-check", tone: "info", label: "Claims fully correct",
          value: `${Core.number(ev.claims_with_all_statuses_correct)} / ${Core.number(CLAIMS.length)}`, caption: "All 15 statuses as expected" }),
      ]),
      callout({ tone: "info", icon: "info", title: "What this measures",
        text: `${ev.note} Expected results: ${DATA.sources.gold}. High accuracy on this synthetic set is not evidence of production readiness.` }),
      card({ title: "Expected against predicted", meta: `All rules · ${Core.number(o.count)} pairs`, body: confusionMatrix(ev.confusion) }),
      card({ title: "Per rule", meta: "Click a rule to open it", flush: true, body: perRuleTable(ev) }),
      h("div", { class: "grid grid--main-side" },
        h("div", { class: "stack" }, mismatchCard(ev)),
        h("div", { class: "stack" }, aiCard())));
  }

  return { render };
})();

registerPage({
  key: "evaluation",
  label: "Evaluation",
  icon: "bar-chart",
  subtitle: "This run scored against the expected results by the official scorer.",
  render: () => EvaluationPage.render(),
});
