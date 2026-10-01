"use strict";
// Settings: how this run was configured, read-only, and the only things a
// viewer sets here: their name, the role to view as, and their unsent drafts.
// Configuration is changed where it lives (rules/*.json, the environment
// before claimguard.run), never in this page, which cannot change the backend.

const SettingsPage = (function () {
  const ACTION_LABELS = {
    view_claim: "View claims", view_findings: "View findings", export_decisions: "Download decisions",
    run_pipeline: "Run the pipeline", append_audit: "Append to the audit log", verify_audit: "Verify the audit log",
    view_run_events: "See run events (runs, rejections, flags, model failures)", change_ai_settings: "Change AI settings",
  };

  function youCard() {
    const input = h("input", { id: "settings-name", class: "input", autocomplete: "name", placeholder: "e.g. Reviewer 01",
      onInput: (e) => { State.reviewer = e.target.value; State.save(); } });
    input.value = State.reviewer;
    const confirmHolder = h("div", { class: "row" });
    function drawDrafts() {
      fill(confirmHolder,
        button({ label: `Download decisions (${State.drafts.length})`, variant: "primary", icon: "download",
          disabled: State.drafts.length === 0, onClick: downloadDecisions }),
        button({ label: "Discard all drafts", variant: "danger", icon: "ban", disabled: State.drafts.length === 0,
          onClick: () => fill(confirmHolder,
            h("span", { class: "small", text: `Discard ${Core.plural(State.drafts.length, "draft")} not yet in the audit log?` }),
            button({ label: "Yes, discard them", variant: "danger", onClick: () => { State.drafts = []; State.save(); drawDrafts(); } }),
            button({ label: "Keep them", variant: "ghost", onClick: drawDrafts })) }));
    }
    drawDrafts();
    return card({ title: "You", meta: "Kept in this browser only", body: h("div", { class: "stack" },
      h("label", { class: "field", for: "settings-name" }, "Your name, recorded with each decision", input),
      kv([["Viewing as", State.role === "admin" ? "Admin" : "Reviewer (change it in the top bar)"],
        ["Drafts", Core.plural(State.drafts.length, "decision") + " saved in this browser, not yet in the audit log"]]),
      confirmHolder,
      h("p", { class: "muted small", text: "Names and roles are self-declared: there is no login (doc 10). The role only changes what this page shows; the permission that counts is checked when decisions are appended to the audit log." })) });
  }

  function runCard() {
    const r = DATA.run;
    const s = DATA.sources;
    const path = (p) => (p ? h("span", { class: "mono small", text: p }) : h("span", { class: "muted", text: "not given" }));
    return card({ title: "Run and versions", body: kv([
      ["Run", r ? h("span", { class: "mono small", text: r.run_id }) : "No run manifest"],
      ["Engine", r ? `${r.engine.name} ${r.engine.version} · Python ${r.python}` : DATA.engine_version],
      ["Starter pack", r ? h("span", { class: "mono small", text: `SHA256SUMS ${Core.shortHash(r.pack.sha256sums)}`, title: r.pack.sha256sums }) : null],
      ["Input", r ? `${r.input.adapter} ${r.input.adapter_version} · ${Core.shortHash(r.input.source_sha256)}` : null],
      ["Rules", `${DATA.rules.length} rules · ${Array.from(new Set(DATA.rules.map((x) => x.version))).join(", ")}`],
      ["Policies", Object.values(DATA.policies).map((p) => `${p.policy_id} ${p.version}`).join(" · ")],
      ["Routing policy", DATA.routing.policy_version],
      ["Prompt", r ? r.prompt_version : null],
      ["Manifest / page data", `${r ? r.manifest_version : "—"} / ${DATA.bundle_version}`],
      ["Results", path(s.results)], ["Claims", path(s.claims)], ["Manifest", path(s.manifest)],
      ["Explanations", path(s.explanations)], ["Audit log", path(s.audit_log)], ["Expected results", path(s.gold)],
      ["Corrections", path(s.corrections)],
    ]) });
  }

  function aiCard() {
    const ai = DATA.run && DATA.run.ai ? DATA.run.ai.summary : null;
    return card({ title: "AI explanations", body: h("div", { class: "stack" },
      kv([
        ["Provider", ai ? (ai.provider === "mock" ? "mock (no model is wired yet)" : ai.provider) : "Not run"],
        ["Model", ai ? value(ai.model) : null],
        ["Why", ai ? ai.provider_reason : null],
        ["Timeout", ai ? `${ai.timeout_s} s, then the rule's own explanation` : null],
        ["Explained", "FAIL and UNABLE_TO_ASSESS results only"],
        ["Withheld", "Every claim flagged by the injection pre-filter"],
        ["The model sees", "One finding and its rule. Never the claim, its ID, notes or document text."],
        ["Checked by", "The watchdog: timeout, provider error, invalid JSON, citations, rule ID, review flag, wording"],
      ]),
      callout({ tone: "info", icon: "info", title: "Set before the run, not here",
        text: "ANTHROPIC_API_KEY, CLAIMGUARD_MODEL and CLAIMGUARD_AI_TIMEOUT_S are read from the environment by python -m claimguard.run (see .env.example). The key is never written to the run's files, so it is never part of this page." })) });
  }

  function rbacCard() {
    const actions = Array.from(new Set([...DATA.rbac.reviewer, ...DATA.rbac.admin]));
    const order = ["view_claim", "view_findings", ...Core.ACTION_ORDER, "export_decisions", "view_run_events",
      "run_pipeline", "append_audit", "verify_audit", "change_ai_settings"];
    const rank = (a) => { const i = order.indexOf(a); return i < 0 ? order.length : i; };
    actions.sort((a, b) => rank(a) - rank(b));
    const cell = (role, a) => (DATA.rbac[role].includes(a)
      ? badge("Allowed", { tone: "pass" }) : h("span", { class: "muted small", text: "Not allowed" }));
    return card({ title: "Roles and permissions", meta: "claimguard.guards.rbac", flush: true, body: h("div", {},
      table({ caption: "What each role may do", rows: actions, columns: [
        { key: "action", label: "Action", render: (a) => h("span", {}, (Core.ACTION[a] || {}).label || ACTION_LABELS[a] || a,
          h("span", { class: "mono muted small", text: `  ${a}` })) },
        { key: "reviewer", label: "Reviewer", render: (a) => cell("reviewer", a) },
        { key: "admin", label: "Admin", render: (a) => cell("admin", a) },
      ] }),
      h("p", { class: "card__body muted small", text: "Enforced when decisions are appended (python -m claimguard.ui.decisions). In this page the role only changes what is shown: there is no login." })) });
  }

  function securityCard() {
    return card({ title: "Security", body: kv([
      ["API key", "Never part of this page or the run's files"],
      ["Claim text", "Shown as text only; it is never run or interpreted as HTML"],
      ["Network", "None: this page loads nothing and sends nothing"],
      [".env", "Git-ignored. Other names such as .env.local are not: use .env only"],
      ["Audit log", "Tamper-evident (hash chain and anchored head), not immutable"],
    ]) });
  }

  function render() {
    const ai = DATA.run && DATA.run.ai ? DATA.run.ai.summary : null;
    return h("div", { class: "stack" },
      statRow([
        statCard({ icon: "list-checks", tone: "info", label: "Rulebook", value: `${DATA.rules.length} rules`,
          caption: `Version ${Array.from(new Set(DATA.rules.map((x) => x.version))).join(", ")}`, href: href("rules") }),
        statCard({ icon: "split", tone: "info", label: "Routing policy", value: DATA.routing.policy_version, caption: "claimguard.review.routing" }),
        statCard({ icon: "sparkles", tone: ai && ai.provider !== "mock" ? "info" : "neutral", label: "Explanations",
          value: ai ? ai.provider : "Not run", caption: ai ? `Prompt ${ai.prompt_version}` : "Run with --explain" }),
        statCard({ icon: "user", tone: "pass", label: "Viewing as", value: State.role === "admin" ? "Admin" : "Reviewer",
          caption: State.reviewer.trim() || "Name not set" }),
      ]),
      h("div", { class: "grid grid--2" },
        h("div", { class: "stack" }, youCard(), aiCard(), securityCard()),
        h("div", { class: "stack" }, runCard(), card({ title: "Routing", meta: `Policy ${DATA.routing.policy_version}`, body: routingRules() }))),
      rbacCard(),
      h("p", { class: "muted small" }, "Every component of this interface, in every state: ",
        h("a", { href: href("components"), text: "component reference" }), "."));
  }

  return { render };
})();

registerPage({
  key: "settings",
  label: "Settings",
  icon: "sliders",
  subtitle: "How this run was configured. Read-only, except your name and drafts.",
  render: () => SettingsPage.render(),
});
