// Switches T3 to the profile's god when you open a thread in that project, and adds the
// Continue elsewhere / Send to cloud buttons. The god map is filled in from gods.json by patch.py.
(() => {
  const GODS = /*GODS*/ {};
  const THEME = "t3code:theme";
  const HALVES = "t3code:theme-halves:v1";
  let lastProject = null;
  let expected = null;  // the theme this script last set, so a different one is your own pick
  let queued = false;

  const apply = () => {
    queued = false;
    const crumb = document.querySelector('[data-slot="workspace-breadcrumb-text"]');
    const project = crumb && crumb.textContent.trim();
    if (!project || project === lastProject) return;
    lastProject = project;
    const god = GODS[project];
    const id = expected = god ? "pantheon-" + god : null;
    if (!id) return;
    if (localStorage.getItem(THEME) === id && !localStorage.getItem(HALVES)) return;
    // the same steps T3 takes when you pick a whole theme, then T3 re-reads it
    localStorage.removeItem(HALVES);
    localStorage.setItem(THEME, id);
    window.dispatchEvent(new StorageEvent("storage", { key: THEME }));
  };

  // helper.py does the work; config.json's buttons_show_in picks the projects ("all" or names).
  const HELPER = "http://127.0.0.1:47833";
  let showIn = "all";
  fetch(HELPER + "/config").then(r => r.json()).then(c => { showIn = c.show_in || "all"; }).catch(() => {});
  const NOT_RUNNING = "The T3 Olympus helper isn't running. Close T3 and open it from the T3 Olympus shortcut.";
  const post = async (path, body) => {
    const r = await fetch(HELPER + path, { method: "POST", headers: { "Content-Type": "application/json" },
                                           body: JSON.stringify(body) });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error);
    return res;
  };
  const failed = e => toast(e instanceof TypeError ? NOT_RUNNING : esc(e.message), true);

  // Picking a god by hand (Ctrl+Alt+A) makes it the open profile's god: saved to gods.json.
  // Waits a moment so previewing themes in the picker, then cancelling, saves nothing.
  let saveTimer;
  const picked = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const id = document.documentElement.dataset.themeId || "";
      const project = lastProject;
      if (!project || !id.startsWith("pantheon-") || id === expected) return;
      const god = id.slice("pantheon-".length);
      try {
        await post("/gods", { project, god });
        GODS[project] = god;
        expected = id;
        toast(`${esc(god[0].toUpperCase() + god.slice(1))} is now ${esc(project)}'s god.`);
      } catch (e) { failed(e); }
    }, 1500);
  };
  new MutationObserver(picked).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme-id"] });

  const threadId = () => {
    const parts = location.hash.replace(/^#\/?/, "").split(/[?#]/)[0].split("/");
    if (parts.length !== 2 || ["draft", "settings", "pull-requests", "new"].includes(parts[0])) return null;
    return decodeURIComponent(parts[1]);
  };

  const toast = (html, keep) => {
    let t = document.getElementById("olympus-toast");
    if (!t) { t = document.createElement("div"); t.id = "olympus-toast"; document.body.append(t); }
    t.innerHTML = html + '<button data-close>×</button>';
    t.querySelector("[data-close]").onclick = () => t.remove();
    clearTimeout(t.timer);
    if (!keep) t.timer = setTimeout(() => t.remove(), 6000);
  };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  const call = async (path, label) => {
    const thread = threadId();
    if (!thread) return;
    toast(label + "…", true);
    try { return await post(path, { thread }); } catch (e) { failed(e); }
  };

  const continueElsewhere = async () => {
    const res = await call("/continue", "Starting Remote Control");
    if (!res) return;
    const link = res.url ? `<a href="${esc(res.url)}" target="_blank">${esc(res.url)}</a>`
                         : "Open Remote Control in Claude desktop or the Claude phone app.";
    toast(`<b>${esc(res.title)}</b> is running in the background with Remote Control.<br>${link}<br>` +
          `${esc(res.note)} Keep typing there, not in this T3 chat. Stop it with <code>claude stop ${esc(res.id)}</code>.`, true);
  };
  const sendToCloud = async () => {
    const res = await call("/cloud", "Opening a terminal");
    if (res) toast("A terminal is writing the handoff note, then it starts the cloud session.");
  };

  // Lucide icons, the set T3 uses
  const svg = d => `<svg class="lucide size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  const ICON = {
    phone: svg('<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>'),
    cloud: svg('<path d="M12 13v8"/><path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="m8 17 4-4 4 4"/>'),
  };

  // The buttons live in the thread details tray (Ctrl+Shift+B), as a section under Workspace.
  // They copy the look of T3's own tray buttons, so they match every theme.
  const buttons = () => {
    const card = document.querySelector("[data-thread-details-card]");
    const workspace = card && card.querySelector('section[aria-label="Workspace"]');
    const mine = document.getElementById("olympus-actions");
    const show = workspace && threadId() && (showIn === "all" || (Array.isArray(showIn) && showIn.includes(lastProject)));
    if (show && mine && mine.previousElementSibling === workspace) return;
    if (mine) mine.remove();
    if (!show) return;
    const tpl = workspace.querySelector('button[aria-label="Add project script"]') || workspace.querySelector("button");
    const section = document.createElement("section");
    section.id = "olympus-actions";
    section.setAttribute("aria-label", "Hand off");
    section.className = "px-2 pt-2 pb-2.5 border-t border-border/65";
    const list = document.createElement("div");
    list.className = "flex flex-col";
    for (const [icon, label, tip, onclick] of [
      [ICON.phone, "Continue elsewhere", "Keep this same chat going in the background with Remote Control", continueElsewhere],
      [ICON.cloud, "Send to cloud", "Write a handoff note and start a cloud session from it", sendToCloud],
    ]) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = tpl ? tpl.className : "";
      b.title = tip;
      b.innerHTML = icon + `<span>${label}</span>`;
      b.onclick = onclick;
      list.append(b);
    }
    section.append(list);
    workspace.after(section);
  };

  const tick = () => { apply(); buttons(); };
  tick();
  new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(tick); }
  }).observe(document.documentElement, { subtree: true, childList: true, characterData: true });
})();
