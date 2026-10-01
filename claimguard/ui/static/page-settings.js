"use strict";
// Settings: the only things a viewer sets here (their name, the role to view
// as, their unsent drafts), then how review works, read-only. Configuration
// is changed where it lives (rules/*.json, the environment before
// claimguard.run), never in this page, which cannot change the backend.

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
      h("label", { class: "field", for: "settings-name" }, "Your name", input),
      kv([["Viewing as", State.role === "admin" ? "Admin" : "Reviewer (change it in the top bar)"],
        ["Drafts", Core.plural(State.drafts.length, "decision") + " saved in this browser, not yet in the audit log"]]),
      confirmHolder,
      h("p", { class: "muted small", text: "Your name is recorded with each decision." })) });
  }

  function aiCard() {
    return card({ title: "AI explanations", body: h("p", { class: "small", text: explainerLine() }) });
  }

  function rbacCard() {
    const actions = Array.from(new Set([...DATA.rbac.reviewer, ...DATA.rbac.admin]));
    const order = ["view_claim", "view_findings", ...Core.ACTION_ORDER, "export_decisions", "view_run_events",
      "run_pipeline", "append_audit", "verify_audit", "change_ai_settings"];
    const rank = (a) => { const i = order.indexOf(a); return i < 0 ? order.length : i; };
    actions.sort((a, b) => rank(a) - rank(b));
    const cell = (role, a) => (DATA.rbac[role].includes(a)
      ? badge("Allowed", { tone: "pass" }) : h("span", { class: "muted small", text: "Not allowed" }));
    return card({ title: "Roles and permissions", flush: true, body: h("div", {},
      table({ caption: "What each role may do", rows: actions, columns: [
        { key: "action", label: "Action", render: (a) => (Core.ACTION[a] || {}).label || ACTION_LABELS[a] || Core.humanize(a) },
        { key: "reviewer", label: "Reviewer", render: (a) => cell("reviewer", a) },
        { key: "admin", label: "Admin", render: (a) => cell("admin", a) },
      ] }),
      h("p", { class: "card__body muted small", text: "Permissions are checked when decisions are added to the audit log." })) });
  }

  function securityCard() {
    return card({ title: "Security", body: kv([
      ["API key", "Never part of this page or the run's files"],
      ["Claim text", "Shown as text only; it is never run or interpreted as HTML"],
      ["Network", "None: this page loads nothing and sends nothing"],
      ["Audit log", "Tamper-evident (hash chain and anchored head), not immutable"],
    ]) });
  }

  function render(route) {
    // "Set your name" in the sidebar opens this page with the field focused,
    // once the page is in the document.
    if (route && route.params.focus === "name") {
      queueMicrotask(() => { const el = document.getElementById("settings-name"); if (el) el.focus(); });
    }
    return h("div", { class: "stack" },
      h("div", { class: "grid grid--2" },
        h("div", { class: "stack" }, youCard(), securityCard()),
        h("div", { class: "stack" }, card({ title: "Routing", body: routingRules() }), aiCard())),
      rbacCard());
  }

  return { render };
})();

registerPage({
  key: "settings",
  label: "Settings",
  icon: "sliders",
  subtitle: "Your name and drafts, how claims are routed, and what each role may do.",
  render: (route) => SettingsPage.render(route),
});
