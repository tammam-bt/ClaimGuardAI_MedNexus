"use strict";
// ClaimGuard interface: pure logic, no DOM. Loaded first in the page, and by
// tests/test_ui_core.py in Node, so every rule here is checked against the
// Python backend it mirrors.

const Core = (function () {
  // ---------------------------------------------------------------- vocabulary
  // One entry per concept. Every page reads labels, icons and tones from here,
  // so a status looks the same everywhere.
  const STATUS = {
    PASS: { label: "Pass", short: "Pass", icon: "check-circle", tone: "pass",
      help: "This check passed on the supplied data. It is not payer approval." },
    FAIL: { label: "Fail", short: "Fail", icon: "x-circle", tone: "fail",
      help: "The supplied data proves a violation of this rule." },
    UNABLE_TO_ASSESS: { label: "Unable to assess", short: "Unable", icon: "help-circle", tone: "unknown",
      help: "Information needed to decide is missing or unusable." },
    NOT_APPLICABLE: { label: "Not applicable", short: "N/A", icon: "minus-circle", tone: "neutral",
      help: "The rule does not govern any part of this claim." },
    NOT_IMPLEMENTED: { label: "Not implemented", short: "Not impl.", icon: "circle-dashed", tone: "neutral",
      help: "No implementation ran for this rule. It is never shown as a pass." },
  };
  const STATUS_ORDER = ["FAIL", "UNABLE_TO_ASSESS", "NOT_IMPLEMENTED", "PASS", "NOT_APPLICABLE"];

  const ROUTE = {
    ESCALATE: { label: "Escalate", icon: "arrow-up-circle", tone: "escalate",
      help: "A high-severity check failed or could not be assessed, or a check did not run. A senior reviewer decides." },
    REVIEW: { label: "Review", icon: "eye", tone: "review",
      help: "Only medium- or low-severity checks failed or could not be assessed." },
    CLEAR: { label: "Clear", icon: "check-check", tone: "clear",
      help: "No check failed or was left unassessed." },
  };
  const ROUTE_ORDER = ["ESCALATE", "REVIEW", "CLEAR"];

  const SEVERITY = { high: { label: "High" }, medium: { label: "Medium" }, low: { label: "Low" } };

  // The four review actions of schemas/review_event.schema.json.
  const ACTION = {
    confirm_issue: { label: "Confirm issue", icon: "flag",
      help: "The finding is right; the claim needs a correction." },
    dismiss_with_reason: { label: "Dismiss with reason", icon: "ban",
      help: "The finding does not hold for this claim. The reason is kept in the audit log." },
    request_information: { label: "Request information", icon: "message-question",
      help: "More source information is needed before deciding." },
    mark_corrected_for_recheck: { label: "Corrected, recheck", icon: "refresh",
      help: "The source was corrected; the claim must be checked again as a new version." },
  };
  const ACTION_ORDER = ["confirm_issue", "dismiss_with_reason", "request_information", "mark_corrected_for_recheck"];
  const APPROVAL = "dismiss_with_reason"; // claimguard/review/routing.py

  // Explanation record sources (claimguard/ai/watchdog.py, explainer.py).
  const SOURCE = {
    provider: { label: "AI explanation", icon: "sparkles", tone: "info" },
    mock: { label: "Template text (mock, no model)", icon: "scroll", tone: "neutral" },
    fallback: { label: "Rule explanation (fallback)", icon: "cpu", tone: "unknown" },
    skipped_flagged: { label: "Withheld from the model", icon: "shield-alert", tone: "neutral" },
  };

  // Where a claim is in its life cycle once routed.
  const OUTCOME = {
    ready: { label: "Ready for submission", icon: "send", tone: "clear",
      help: "No open finding. A passed pre-check is not payer approval." },
    to_review: { label: "To review", icon: "user", tone: "review", help: "No finding has a decision yet." },
    in_review: { label: "In review", icon: "user", tone: "review", help: "Some findings have a decision." },
    waiting_information: { label: "Waiting for information", icon: "message-question", tone: "unknown",
      help: "A reviewer asked for more source information." },
    correction_needed: { label: "Correction needed", icon: "flag", tone: "fail",
      help: "A reviewer confirmed an issue; the source must be corrected." },
    awaiting_recheck: { label: "Awaiting recheck", icon: "refresh", tone: "unknown",
      help: "The source was corrected; the claim must run again as a new version." },
    rechecked: { label: "Rechecked as a new version", icon: "refresh", tone: "info",
      help: "A corrected version was checked again by all 15 rules; its results are shown with the claim." },
  };
  const OUTCOME_ORDER = ["to_review", "in_review", "waiting_information", "correction_needed", "awaiting_recheck", "rechecked", "ready"];

  // Injection pre-filter families (claimguard/guards/injection.py).
  const FAMILY = {
    override: "Tries to override the instructions",
    role_marker: "Fake role marker (e.g. SYSTEM:)",
    role_play: "Tries to change the assistant's role",
    secret_request: "Asks for secrets or the prompt",
    decision_forcing: "Tries to force a decision",
    output_tampering: "Tries to change the output",
    tool_or_exfiltration: "Asks to call a tool or send data",
    false_authority: "Claims a false authority",
  };

  // Audit chain event types (claimguard/audit/chain.py). Each reuses the icon
  // of its concept: a flag looks like a flag, a decision like a person.
  const EVENT = {
    run_started: { label: "Run started", icon: "layers", tone: "info" },
    run_finished: { label: "Run finished", icon: "layers", tone: "info" },
    ingestion_error: { label: "Rejected at ingestion", icon: "file-x", tone: "fail" },
    injection_flag: { label: "Flagged for injection", icon: "shield-alert", tone: "unknown" },
    model_failure: { label: "Model failure (fallback)", icon: "alert-triangle", tone: "unknown" },
    review_decision: { label: "Review decision", icon: "user", tone: "pass" },
    version_created: { label: "New claim version", icon: "refresh", tone: "info" },
  };

  const STAGES = [
    { key: "received", label: "Received", icon: "arrow-down-line" },
    { key: "ingested", label: "Ingested", icon: "file-check" },
    { key: "checked", label: "Checked", icon: "list-checks" },
    { key: "screened", label: "Screened", icon: "shield" },
    { key: "explained", label: "Explained", icon: "sparkles" },
    { key: "routed", label: "Routed", icon: "split" },
    { key: "review", label: "In review", icon: "user" },
    { key: "outcome", label: "Outcome", icon: "send" },
  ];

  // ------------------------------------------------------------------ helpers
  const blank = (v) => v === null || v === undefined || String(v).trim() === "";
  const count = (items, key) => items.reduce((acc, x) => { const k = key(x); acc[k] = (acc[k] || 0) + 1; return acc; }, {});
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;

  // ---------------------------------------------------------------- decisions
  // Mirrors claimguard.review.routing.outstanding(): per finding, the latest
  // decision with a non-blank actor and reason whose original_status equals
  // the finding's current status counts; a finding is settled only by
  // dismiss_with_reason; NOT_IMPLEMENTED can never be dismissed.
  function outstanding(routing, events) {
    const latest = new Map();
    for (const e of events) {
      if (e.claim_id !== routing.claim_id) continue;
      if (blank(e.actor) || blank(e.reason)) continue;
      latest.set(`${e.rule_id}\u0000${e.original_status}`, e.action);
    }
    const pending = [];
    for (const reason of routing.reasons) {
      const action = latest.get(`${reason.rule_id}\u0000${reason.status}`);
      let why;
      if (reason.status === "NOT_IMPLEMENTED") why = "check not implemented; cannot be dismissed";
      else if (action === undefined) why = "no review decision recorded";
      else if (action !== APPROVAL) why = `latest decision is ${action}`;
      else continue;
      pending.push(Object.assign({}, reason, { why }));
    }
    return pending;
  }

  // The latest valid decision per finding, for display. Same validity as
  // outstanding(), plus: a decision taken on another version of the claim
  // (another input_hash) does not count.
  function latestDecisions(entry, events) {
    const latest = {};
    for (const e of events) {
      if (e.claim_id !== entry.route.claim_id || e.input_hash !== entry.input_hash) continue;
      if (blank(e.actor) || blank(e.reason)) continue;
      latest[`${e.rule_id}\u0000${e.original_status}`] = e;
    }
    const out = {};
    for (const reason of entry.route.reasons) {
      const e = latest[`${reason.rule_id}\u0000${reason.status}`];
      if (e) out[reason.rule_id] = e;
    }
    return out;
  }

  function outcome(entry, events) {
    const reasons = entry.route.reasons;
    if (reasons.length === 0) return "ready";
    // A corrected version replaces this one: its own results decide next.
    if (entry.versions && entry.versions.length) return "rechecked";
    const valid = events.filter((e) => e.input_hash === entry.input_hash);
    const actions = Object.values(latestDecisions(entry, valid)).map((e) => e.action);
    if (actions.includes("mark_corrected_for_recheck")) return "awaiting_recheck";
    if (actions.includes("request_information")) return "waiting_information";
    if (actions.includes("confirm_issue")) return "correction_needed";
    if (outstanding(entry.route, valid).length === 0) return "ready";
    return actions.length ? "in_review" : "to_review";
  }

  // The findings a reviewer decides on: the results the route names, in rule
  // order, each with its result row.
  function findings(entry) {
    const byRule = new Map(entry.results.map((r) => [r.rule_id, r]));
    return entry.route.reasons.map((reason) => ({ reason, result: byRule.get(reason.rule_id) }));
  }

  // A review_decision event as claimguard/audit/chain.py records it.
  function decisionEvent(entry, result, action, actor, reason, createdAt) {
    return {
      event: "review_decision",
      claim_id: entry.route.claim_id,
      rule_id: result.rule_id,
      action,
      actor: String(actor).trim(),
      reason: String(reason).trim(),
      created_at: createdAt,
      original_status: result.status,
      input_hash: entry.input_hash,
    };
  }

  // ------------------------------------------------------------- life cycle
  function statusCounts(results) {
    const c = count(results, (r) => r.status);
    return STATUS_ORDER.reduce((acc, s) => { acc[s] = c[s] || 0; return acc; }, {});
  }

  function lifecycle(entry, events) {
    const c = statusCounts(entry.results);
    const p = entry.provenance;
    const flagged = !!entry.flag;
    const toExplain = entry.results.filter((r) => r.status === "FAIL" || r.status === "UNABLE_TO_ASSESS").length;
    const ex = entry.explanations;
    const reasons = entry.route.reasons;
    const decided = Object.keys(latestDecisions(entry, events)).length;
    const result = outcome(entry, events);

    let explained;
    if (ex === null || ex === undefined) explained = { state: "skipped", summary: "AI explanation not run" };
    else if (toExplain === 0) explained = { state: "skipped", summary: "nothing to explain" };
    else if (flagged) explained = { state: "skipped", summary: "withheld from the model (flagged)" };
    else {
      const bySource = count(ex, (e) => e.source);
      const fallbacks = bySource.fallback || 0;
      const mock = ex.some((e) => e.provider === "mock");
      explained = {
        state: fallbacks ? "warn" : "done",
        summary: `${plural(ex.length, "finding")} ${mock ? "by template (mock)" : "explained"}` + (fallbacks ? `, ${fallbacks} by fallback` : ""),
      };
    }

    const stages = {
      received: { state: p ? "done" : "warn",
        summary: p ? `${p.adapter} · line ${p.line_number}` : "provenance not recorded" },
      ingested: { state: "done", summary: "accepted" },
      checked: { state: c.FAIL ? "fail" : (c.UNABLE_TO_ASSESS || c.NOT_IMPLEMENTED ? "warn" : "done"),
        summary: `${c.PASS} passed · ${c.FAIL} failed · ${c.UNABLE_TO_ASSESS} unable` },
      screened: { state: flagged ? "warn" : "done",
        summary: flagged ? `flagged: ${plural(entry.flag.hits.length, "hit")}` : "no instruction-like text" },
      explained,
      routed: { state: "done", summary: ROUTE[entry.route.route].label },
      review: reasons.length === 0
        ? { state: "skipped", summary: "not needed" }
        : { state: decided === reasons.length ? "done" : "current", summary: `${decided} / ${reasons.length} decided` },
      outcome: { state: result === "ready" ? "done" : "current", summary: OUTCOME[result].label, outcome: result },
    };
    return STAGES.map((s) => Object.assign({}, s, stages[s.key]));
  }

  // Run-level funnel: how many claims reached each point.
  function funnel(data, events) {
    const claims = data.claims;
    const outcomes = count(claims, (c) => outcome(c, events));
    return {
      received: (data.run && data.run.input) ? data.run.input.records : claims.length + data.rejected.length,
      rejected: data.rejected.length,
      accepted: claims.length,
      checked: claims.length,
      flagged: claims.filter((c) => c.flag).length,
      routes: count(claims, (c) => c.route.route),
      outcomes: OUTCOME_ORDER.reduce((acc, k) => { acc[k] = outcomes[k] || 0; return acc; }, {}),
    };
  }

  // The same eight stages for the whole run: how many records reached each.
  function runStages(data, events) {
    const f = funnel(data, events);
    const run = data.run;
    const claims = data.claims;
    const results = claims.reduce((n, c) => n + c.results.length, 0);
    const ruleErrors = run ? run.rule_errors.length : 0;
    const ai = run && run.ai ? run.ai.summary : null;
    const routed = claims.filter((c) => c.route.reasons.length);
    const total = routed.reduce((n, c) => n + c.route.reasons.length, 0);
    const decided = routed.reduce((n, c) => n + Object.keys(latestDecisions(c, events)).length, 0);
    const ready = f.outcomes.ready;
    let explained = { state: "skipped", summary: "AI explanation not run" };
    if (ai) {
      const failures = Object.values(ai.failures || {}).reduce((a, b) => a + b, 0);
      // The mock is not a model: say so rather than "explained".
      const written = ai.provider === "mock" ? "by template (mock)" : "explained";
      explained = {
        state: failures ? "warn" : "done",
        summary: `${number(ai.by_source.provider || 0)} ${written} · ${number(ai.by_source.skipped_flagged || 0)} withheld · ` +
          plural(failures, "fallback"),
      };
    }
    const stages = {
      received: { state: "done", summary: plural(f.received, "record") },
      ingested: { state: f.rejected ? "warn" : "done", summary: `${number(f.accepted)} accepted · ${number(f.rejected)} rejected` },
      checked: { state: ruleErrors ? "fail" : "done", summary: `${number(results)} results · ${plural(ruleErrors, "rule error")}` },
      screened: { state: f.flagged ? "warn" : "done", summary: `${number(f.flagged)} flagged for injection` },
      explained,
      routed: { state: "done",
        summary: `${number(f.routes.ESCALATE || 0)} escalate · ${number(f.routes.REVIEW || 0)} review · ${number(f.routes.CLEAR || 0)} clear` },
      review: total
        ? { state: decided === total ? "done" : "current", summary: `${number(decided)} / ${number(total)} findings decided` }
        : { state: "skipped", summary: "nothing to review" },
      outcome: { state: ready === claims.length ? "done" : "current",
        summary: `${number(ready)} ready · ${number(claims.length - ready)} open` },
    };
    return STAGES.map((s) => Object.assign({}, s, stages[s.key]));
  }

  // ------------------------------------------------------------- formatting
  const NUMBER = new Intl.NumberFormat("en-GB");
  const MONEY = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function number(n) { return n === null || n === undefined ? "—" : NUMBER.format(n); }
  function money(n, currency) {
    if (n === null || n === undefined || typeof n !== "number" || !isFinite(n)) return "—";
    return `${MONEY.format(n)}${currency ? " " + currency : ""}`;
  }
  // One date format everywhere: 24 Apr 2026. ISO dates are read as written,
  // never through the local time zone.
  function date(iso) {
    if (typeof iso !== "string") return "—";
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return iso;
    return `${m[3]} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
  }
  function datetime(iso) {
    if (typeof iso !== "string") return "—";
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(iso);
    return m ? `${date(iso)}, ${m[4]}:${m[5]}:${m[6]} UTC` : iso;
  }
  function percent(x, digits) {
    return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits === undefined ? 1 : digits)}%`;
  }
  function shortHash(h) { return typeof h === "string" ? h.slice(0, 12) : "—"; }

  return {
    STATUS, STATUS_ORDER, ROUTE, ROUTE_ORDER, SEVERITY, ACTION, ACTION_ORDER, SOURCE, OUTCOME, OUTCOME_ORDER, STAGES,
    FAMILY, EVENT, outstanding, latestDecisions, outcome, statusCounts, lifecycle, funnel, runStages, findings, decisionEvent,
    number, money, date, datetime, percent, shortHash, plural, count,
  };
})();

if (typeof module !== "undefined") module.exports = Core;
