"use strict";
// Settings: the only things a viewer sets here (their name, the theme, the
// role to view as, their unsent drafts), then how review works, read-only. Configuration
// is changed where it lives (rules/*.json, the environment before
// claimguard.run), never in this page, which cannot change the backend.

const SettingsPage = (function () {
  const ACTION_LABELS = {
    view_claim: "View claims", view_findings: "View findings", export_decisions: "Download decisions",
    run_pipeline: "Run the pipeline", append_audit: "Append to the audit log", verify_audit: "Verify the audit log",
    view_run_events: "See run events (runs, rejections, flags, model failures, who ran each append)", change_ai_settings: "Change AI settings",
  };

  function youCard() {
    // Signed in on the local server, the name is the server's and cannot be typed.
    const input = h("input", { id: "settings-name", class: "input", autocomplete: "name", placeholder: "e.g. Reviewer 01",
      readonly: Server.user ? true : null, onInput: (e) => { State.reviewer = e.target.value; State.save(); } });
    input.value = State.reviewer;
    const theme = h("select", { id: "settings-theme", class: "select", onChange: (e) => { State.theme = e.target.value; State.save(); } },
      THEMES.map(([v, l]) => h("option", { value: v, selected: State.theme === v ? true : null, text: l })));
    const confirmHolder = h("div", { class: "row" });
    function drawDrafts() {
      fill(confirmHolder,
        draftActions(),
        button({ label: "Discard all drafts", variant: "danger", icon: "ban", disabled: State.drafts.length === 0,
          onClick: () => fill(confirmHolder,
            h("span", { class: "small", text: `Discard ${Core.plural(State.drafts.length, "draft")} not yet in the audit log?` }),
            button({ label: "Yes, discard them", variant: "danger", onClick: () => { State.drafts = []; State.save(); drawDrafts(); } }),
            button({ label: "Keep them", variant: "ghost", onClick: drawDrafts })) }));
    }
    drawDrafts();
    return card({ title: "You", meta: "Kept in this browser only", body: h("div", { class: "stack" },
      h("label", { class: "field", for: "settings-name" }, "Your name", input),
      h("label", { class: "field", for: "settings-theme" }, "Theme", theme),
      kv([["Viewing as", (State.role === "admin" ? "Admin" : "Reviewer") + (Server.user ? " (signed in)" : State.role === "admin" ? "" : " (demo switch in the top bar)")],
        ["Drafts", Core.plural(State.drafts.length, "decision") + " saved in this browser, not yet in the audit log"]]),
      confirmHolder,
      h("p", { class: "muted small", text: "Your name is recorded with each decision." })) });
  }

  // The safeguards hold whichever provider runs (claimguard/ai/minimize.py,
  // watchdog.py), so they are listed even with the mock.
  function aiCard() {
    return card({ title: "AI explanations", body: h("div", { class: "stack" },
      h("p", { class: "small", text: explainerLine() }),
      h("p", { class: "small", text: "The model sees one finding and its rule, never the claim: no claim number, notes or " +
        "document text, and patient and member numbers replaced by placeholders such as [patient-1]." }),
      h("p", { class: "small", text: "An answer is rejected, and the rule's own explanation shown instead, when:" }),
      h("ul", { class: "small", style: { margin: "0", paddingLeft: "18px" } },
        Object.values(Core.FAILURE).map((label) => h("li", { text: label }))),
      h("p", { class: "muted small", text: "A rejected answer is never shown or stored." })) });
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
      ["Network", Server.token ? "Only the local server that sent this page, on this machine (127.0.0.1)"
        : "None: this page loads nothing and sends nothing"],
      ["Audit log", "Tamper-evident (hash chain and anchored head), not immutable"],
    ]) });
  }

  // The local server (python -m claimguard.ui.serve), only on a page it sent:
  // what it reports, and sign-in when it asks for one (B4).
  function serverCard() {
    if (!Server.token) return null;
    if (!Server.live) {
      return card({ title: "Local server", body: callout({ tone: "unknown", icon: "alert-triangle", title: "The local server does not answer",
        text: "Drafts stay in this browser and can be downloaded. Once the server runs again, reload this page." }) });
    }
    const s = Server.status;
    const signin = s.signin;
    return card({ title: "Local server", meta: "This machine only (127.0.0.1)", body: h("div", { class: "stack" },
      kv([["Audit log", s.audit.valid ? `${Core.plural(s.audit.count, "event")}, verified; head ${Core.shortHash(s.audit.head)}` : `Invalid: ${s.audit.error}`],
        ["Corrections", s.corrections ? "Rechecked by the server as new versions" : "Downloaded as a file: the server has no corrections folder"],
        ["Sign-in", !signin ? "Not used: names are self-declared, as on the offline page"
          : signin.user ? `${signin.user} (${signin.role === "admin" ? "Admin" : "Reviewer"})` : "Required to save"]]),
      signin && !signin.user ? signInForm() : null,
      signin && signin.user ? h("div", { class: "row" }, button({ label: "Sign out", icon: "lock", onClick: async () => {
        await Server.call("POST", "/api/signout", {});
        location.reload();
      } })) : null,
      signin ? h("p", { class: "muted small", text: "Sign-in proves who saved only if reviewers cannot use the account that runs the server." }) : null) });
  }
  function signInForm() {
    const name = h("input", { id: "signin-name", class: "input", autocomplete: "username" });
    const password = h("input", { id: "signin-password", class: "input", type: "password", autocomplete: "current-password" });
    const problem = h("div");
    return h("form", { class: "stack", "aria-label": "Sign in", onSubmit: async (e) => {
      e.preventDefault();
      fill(problem);
      const r = await Server.call("POST", "/api/signin", { name: name.value, password: password.value });
      password.value = "";
      if (r.ok) { location.reload(); return; }
      fill(problem, callout({ tone: "fail", icon: "alert-triangle", role: "alert", title: String(r.data.error || "Not signed in.") }));
    } },
    h("label", { class: "field", for: "signin-name" }, "Name", name),
    h("label", { class: "field", for: "signin-password" }, "Password", password),
    problem,
    h("div", { class: "row" }, h("button", { type: "submit", class: "btn btn--primary" }, icon("lock"), "Sign in")));
  }

  function render(route) {
    // "Set your name" in the sidebar opens this page with the field focused,
    // once the page is in the document.
    if (route && route.params.focus === "name") {
      queueMicrotask(() => { const el = document.getElementById("settings-name"); if (el) el.focus(); });
    }
    return h("div", { class: "stack" },
      h("div", { class: "grid grid--2" },
        h("div", { class: "stack" }, serverCard(), youCard(), securityCard()),
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
