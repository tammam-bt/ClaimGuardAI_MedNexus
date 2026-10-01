"use strict";
// ClaimGuard interface: the shell (sidebar and topbar, identical on every
// page) and the start-up. Pages are drawn into .content only.

const Shell = (function () {
  const navLinks = new Map();
  const title = h("h1");
  const subtitle = h("p");
  const content = h("main", { class: "content", id: "content", tabindex: "-1" });
  const userBlock = h("div", { class: "sidebar__user" });
  let current = null;
  let firstRender = true;

  function openCount() {
    const events = decisions();
    return CLAIMS.filter((c) => Core.outcome(c, events) !== "ready").length;
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
      nav, userBlock);
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
    const role = h("div", { class: "sidebar__user-role", text: State.role === "admin" ? "Admin" : "Reviewer" });
    fill(userBlock, name
      ? [h("span", { class: "avatar", "aria-hidden": "true", text: name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase() }),
        h("div", {}, h("span", { class: "sidebar__user-name", text: name }), role)]
      : h("div", {}, h("a", { class: "sidebar__user-link", href: href("settings", null, { focus: "name" }), text: "Set your name" }), role));
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
