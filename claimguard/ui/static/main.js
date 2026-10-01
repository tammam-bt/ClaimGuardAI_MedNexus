"use strict";
// ClaimGuard interface: the shell (sidebar and topbar, identical on every
// page) and the start-up. Pages are drawn into .content only.

const Shell = (function () {
  const navLinks = new Map();
  const title = h("h1");
  const subtitle = h("p");
  const content = h("main", { class: "content", id: "content", tabindex: "-1" });
  const userName = h("span", { class: "sidebar__user-name" });
  const userRole = h("span", { class: "sidebar__user-role" });
  const avatar = h("span", { class: "avatar", "aria-hidden": "true" });
  let current = null;
  let firstRender = true;

  function openCount() {
    const events = decisions();
    return CLAIMS.filter((c) => Core.outcome(c, events) !== "ready").length;
  }

  function runCard() {
    if (!DATA.run) return h("div", { class: "sidebar__run" }, h("strong", { text: "No run manifest" }));
    const r = DATA.run;
    return h("div", { class: "sidebar__run" },
      h("div", {}, "Run ", h("strong", { class: "mono", text: Core.shortHash(r.run_id) })),
      h("div", {}, `${Core.number(r.input.accepted)} claims · ${r.input.adapter}`),
      h("div", {}, `Engine ${r.engine.version} · prompt ${r.prompt_version || "—"}`));
  }

  function sidebar() {
    const nav = h("nav", { class: "nav", "aria-label": "Main" });
    for (const page of PAGES.filter((p) => p.nav !== false)) {
      const count = page.key === "queue" ? h("span", { class: "nav__count", "aria-label": "open claims" }) : null;
      const link = h("a", { class: "nav__item", href: href(page.key) },
        icon(page.icon), h("span", { class: "nav__label", text: page.label }), count);
      navLinks.set(page.key, { link, count });
      nav.appendChild(link);
    }
    return h("aside", { class: "sidebar" },
      h("div", { class: "brand" }, icon("logo"),
        h("div", {}, h("div", { class: "brand__name", text: "ClaimGuard AI" }),
          h("div", { class: "brand__tag", text: "Claim pre-validation" }))),
      nav, runCard(),
      h("div", { class: "sidebar__user" }, avatar, h("div", {}, userName, h("div", {}, userRole))));
  }

  function topbarSearch() {
    const input = h("input", { type: "search", placeholder: "Claim ID or rule ID", "aria-label": "Search a claim or a rule" });
    const form = h("form", { class: "search", role: "search", onSubmit: (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      const upper = q.toUpperCase();
      if (CLAIM_BY_ID.has(upper)) go("claims", upper);
      else if (RULE_BY_ID.has(upper)) go("rules", upper);
      else go("claims", null, { q });
      input.value = "";
    } }, icon("search", { size: "sm" }), input);
    return form;
  }

  function roleSwitch() {
    return h("label", { class: "row small muted" }, "View as",
      h("select", { class: "select", "aria-label": "Role", onChange: (e) => { State.role = e.target.value; State.save(); render(); } },
        [["reviewer", "Reviewer"], ["admin", "Admin"]].map(([v, l]) => h("option", { value: v, selected: State.role === v ? true : null, text: l }))));
  }

  function refreshUser() {
    const name = State.reviewer.trim();
    userName.textContent = name || "Name not set";
    userRole.textContent = State.role === "admin" ? "Admin" : "Reviewer";
    avatar.textContent = name ? name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase() : "?";
    const q = navLinks.get("queue");
    if (q && q.count) q.count.textContent = Core.number(openCount());
  }

  function build() {
    const app = document.getElementById("app");
    app.className = "app";
    const skip = h("a", { class: "skip-link", href: "#content", text: "Skip to content",
      onClick: (e) => { e.preventDefault(); content.focus(); } });
    document.body.insertBefore(skip, app);
    app.replaceChildren(sidebar(),
      h("div", { class: "main" },
        h("header", { class: "topbar" }, h("div", { class: "topbar__title" }, title, subtitle), topbarSearch(), roleSwitch()),
        content));
    refreshUser();
    State.onChange(refreshUser);
    window.addEventListener("hashchange", render);
  }

  function render() {
    closePanel();
    const route = parseRoute();
    const page = PAGES.find((p) => p.key === route.key) || PAGES.find((p) => p.key === "dashboard");
    if (current !== page.key) window.scrollTo(0, 0);
    current = page.key;
    for (const [key, { link }] of navLinks) link.setAttribute("aria-current", key === page.key ? "page" : "false");
    title.textContent = page.label;
    subtitle.textContent = page.subtitle;
    document.title = `${page.label} | ClaimGuard AI`;
    let body;
    try {
      body = page.render(route);
    } catch (err) {
      console.error(err);
      body = emptyState({ icon: "alert-triangle", title: "This page could not be drawn", text: String(err && err.message || err) });
    }
    content.replaceChildren(body);
    // After a navigation (not on first load), move focus to the new content
    // so keyboard and screen-reader users land on it.
    if (!firstRender && document.activeElement && !content.contains(document.activeElement)) content.focus({ preventScroll: true });
    firstRender = false;
  }

  return { build, render, refreshUser };
})();

Shell.build();
Shell.render();
