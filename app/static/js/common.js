(() => {
  const toggle = document.querySelector(".cs-nav-toggle");
  const nav = document.querySelector(".cs-primary-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  const trigger = document.querySelector("#member-menu-trigger");
  const menu = document.querySelector("#member-menu");
  if (trigger && menu) {
    trigger.addEventListener("click", () => {
      const open = menu.hidden;
      menu.hidden = !open;
      trigger.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", event => {
      if (!menu.hidden && !event.target.closest(".cs-member")) {
        menu.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
      }
    });
  }

  window.csToast = (message, kind = "success") => {
    const toast = document.querySelector("#global-toast");
    if (!toast) return;
    toast.textContent = message;
    toast.dataset.kind = kind;
    toast.hidden = false;
    clearTimeout(window.__csToastTimer);
    window.__csToastTimer = setTimeout(() => { toast.hidden = true; }, 3500);
  };

  if (document.body.dataset.role === "OWNER") {
    fetch("/api/alerts", { headers: { Accept: "application/json" } })
      .then(response => response.ok ? response.json() : [])
      .then(rows => {
        const count = rows.filter(row => !row.resolved).length;
        const badge = document.querySelector("#nav-alert-count");
        if (badge && count) {
          badge.textContent = count > 99 ? "99+" : String(count);
          badge.hidden = false;
        }
      })
      .catch(() => {});
  }
})();
