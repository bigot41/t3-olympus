// Switches T3 to the profile's god when you open a thread in that project, and adds the
// Continue elsewhere / Send to cloud buttons. The god map is filled in from gods.json by patch.py.
// Shared by all the T3 Olympus scripts (patch.py joins them into one file).
window.olympus = {
  HELPER: "http://127.0.0.1:47833",
  COMPOSER: '[data-slot="composer-host"]',
  esc: (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]),
  // the chat id in the address bar (null on a new chat or settings page)
  threadId: () => {
    const parts = location.hash.replace(/^#\/?/, "").split(/[?#]/)[0].split("/");
    if (parts.length !== 2 || ["draft", "settings", "pull-requests", "new"].includes(parts[0])) return null;
    return decodeURIComponent(parts[1]);
  },
  // a request to the helper; throws its error message, or a TypeError when it isn't running
  post: async (path, body, raw) => {
    const r = await fetch(olympus.HELPER + path, { method: "POST", body: raw ? body : JSON.stringify(body),
      headers: { "Content-Type": raw ? "application/octet-stream" : "application/json" } });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error);
    return res;
  },
  // T3's message box (the editable part), and filling it: replace or append, then optionally send
  box: () => document.querySelector(`${olympus.COMPOSER} [contenteditable="true"], ${olympus.COMPOSER} textarea`),
  fill: (text, { append = false, send = false } = {}) => {
    const box = olympus.box();
    if (!box) return;
    box.focus();
    if (append) {
      getSelection().selectAllChildren(box);
      getSelection().collapseToEnd();
      if (box.innerText.trim()) text = " " + text;
    } else document.execCommand("selectAll");
    document.execCommand("insertText", false, text);
    // Enter, as if typed: clicking T3's send button from a new chat sends it and then opens yet
    // another new chat instead of the one just started
    if (send) setTimeout(() => box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true })), 50);
  },
  // one page watcher for every script: fn runs at most once per frame after the page changes
  onDom: (fn) => {
    const o = window.olympus;
    if (!o.ticks) {
      o.ticks = [];
      let queued = false;
      new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; o.ticks.forEach((f) => { try { f(); } catch { /* keep the rest */ } }); });
      }).observe(document.documentElement, { subtree: true, childList: true, characterData: true });
    }
    o.ticks.push(fn);
  },
};

// One shared place above T3's message box for the Temporary label, the task list and box, and the
// dictation status, so they stack instead of each pushing the others out of the way.
// Usage: olympusAbove(element) puts it there; the CSS order keeps them in a fixed order.
let stackSized = null;  // the message box the stack's width follows
const stackWidth = new ResizeObserver(([e]) => {
  const stack = document.getElementById("olympus-stack");
  if (stack) stack.style.width = e.target.offsetWidth ? e.target.offsetWidth + "px" : "";
});
window.olympusAbove = (el) => {
  const host = document.querySelector(olympus.COMPOSER);
  if (!host) return false;
  let stack = document.getElementById("olympus-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.id = "olympus-stack";
    const style = document.createElement("style");
    style.textContent = `
#olympus-stack { position: relative; z-index: 1; /* above the composer's frosted backdrop */
  display: flex; flex-direction: column; gap: 6px; min-width: 0; box-sizing: border-box;
  /* inset from the rounded panel behind the composer, so nothing sits on its corner */
  margin: 0 auto 6px; padding: 10px 14px 0; }
#olympus-stack:empty { display: none; }`;
    document.head.append(style);
  }
  if (stack.nextElementSibling !== host) host.before(stack);
  if (stackSized !== host) {  // T3 re-created its message box: follow the new one
    if (stackSized) stackWidth.unobserve(stackSized);
    stackWidth.observe(host);
    stackSized = host;
  }
  if (el.parentElement !== stack) stack.append(el);
  return true;
};

(() => {
  const GODS = /*GODS*/ {};
  const { HELPER, esc, threadId, post } = olympus;
  const THEME = "t3code:theme";
  const HALVES = "t3code:theme-halves:v1";
  let lastProject = null;
  let expected = null;  // the theme this script last set, so a different one is your own pick

  const apply = () => {
    if (window !== top) return;  // a split-view pane follows the main window's theme
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
  let showIn = "all";
  fetch(HELPER + "/config").then(r => r.json()).then(c => { showIn = c.show_in || "all"; }).catch(() => {});
  const NOT_RUNNING = "The T3 Olympus helper isn't running. Close T3 and open it from the T3 Olympus shortcut.";
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

  // The window's minimize / maximize / close buttons are drawn by T3's desktop shell, light on a
  // dark app and dark on a light one. With the appearance set to System, T3 tells the shell to
  // follow Windows, so a dark god theme on light Windows got dark buttons you can't see. After
  // each theme change, tell the shell whether the god's theme is light or dark (patch.py fills in
  // each theme's mode from its file).
  const MODES = /*MODES*/ {};
  let shellMode = null;
  const syncButtons = () => {
    if (window !== top || typeof window.desktopBridge?.setTheme !== "function") return;
    // only the god themes, whose light and dark versions are the same: pinning the shell to dark
    // or light changes nothing else there. Any other theme gets T3's own setting back, so System
    // keeps following Windows.
    if (!(document.documentElement.dataset.themeId || "").startsWith("pantheon-")) {
      if (shellMode) {
        shellMode = null;
        let own = "system";
        try { own = localStorage.getItem("t3code:theme-appearance-mode") || own; } catch { /* default */ }
        Promise.resolve(window.desktopBridge.setTheme(own)).catch(() => {});
      }
      return;
    }
    const mode = MODES[document.documentElement.dataset.themeId.slice("pantheon-".length)];
    if (!mode || mode === shellMode) return;
    shellMode = mode;
    Promise.resolve(window.desktopBridge.setTheme(mode)).catch(() => { shellMode = null; });
  };
  let buttonsTimer;
  new MutationObserver(() => { clearTimeout(buttonsTimer); buttonsTimer = setTimeout(syncButtons, 400); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme-id", "class"] });
  setTimeout(syncButtons, 1500);


  const toast = (html, keep) => {
    let t = document.getElementById("olympus-toast");
    if (!t) { t = document.createElement("div"); t.id = "olympus-toast"; document.body.append(t); }
    t.innerHTML = html + '<button data-close>×</button>';
    t.querySelector("[data-close]").onclick = () => t.remove();
    clearTimeout(t.timer);
    if (!keep) t.timer = setTimeout(() => t.remove(), 6000);
  };

  const call = async (path, label, allow) => {
    const thread = threadId();
    if (!thread) return;
    toast(label + "…", true);
    try { return await post(path, { thread, allow }); } catch (e) { failed(e); }
  };

  const continueElsewhere = async (allow) => {
    const res = await call("/continue", "Starting Remote Control", allow === true);
    if (!res) return;
    if (res.trust) {  // Claude Code wants this folder trusted first: ask here, not in a terminal
      toast(`<b>Allow Remote Control in this folder?</b><br><code>${esc(res.trust)}</code><br>` +
            "Sessions started from your phone or claude.ai can read, edit and run files here, and this " +
            "folder's settings (hooks, MCP servers, permissions) apply to them. Only allow it for a folder you trust." +
            '<div class="olympus-ask"><button data-allow>Allow</button><button data-deny>Not now</button></div>', true);
      const t = document.getElementById("olympus-toast");
      t.querySelector("[data-allow]").onclick = () => continueElsewhere(true);
      t.querySelector("[data-deny]").onclick = () => t.remove();
      return;
    }
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

  // The god map: the copy baked in by patch.py, then the helper's gods.json, so a profile made
  // with the New profile button gets its god straight away.
  const loadGods = (map) => {
    Object.keys(GODS).forEach((k) => delete GODS[k]);
    Object.assign(GODS, map);
    lastProject = null;  // apply again
    tick();
  };
  fetch(HELPER + "/gods").then((r) => r.json()).then(loadGods).catch(() => {});

  // New profile: a button above the sidebar's bottom row opens a small dialog; the helper makes it.
  const PLUS = svg('<path d="M5 12h14"/><path d="M12 5v14"/>');
  const dialogStyle = document.createElement("style");
  dialogStyle.textContent = `
#olympus-new-profile { position: fixed; inset: 0; z-index: 9998; display: flex; align-items: center; justify-content: center;
  background: rgb(0 0 0 / .35); }
#olympus-new-profile form { width: 340px; padding: 16px 18px; border-radius: 10px; display: flex; flex-direction: column; gap: 10px;
  font-size: 13px; background: var(--popover, Canvas); color: var(--foreground, CanvasText);
  border: 1px dotted color-mix(in srgb, var(--primary, currentColor) 70%, transparent); box-shadow: 0 8px 24px rgb(0 0 0 / .35); }
#olympus-new-profile label { display: flex; flex-direction: column; gap: 4px; }
#olympus-new-profile label.check { flex-direction: row; align-items: center; gap: 8px; }
#olympus-new-profile input:not([type]), #olympus-new-profile input[name], #olympus-new-profile select {
  font: inherit; color: inherit; padding: 5px 8px; border-radius: 6px; background: var(--background, Canvas);
  border: 1px solid color-mix(in srgb, currentColor 25%, transparent); }
#olympus-new-profile input[type=checkbox] { width: auto; }
#olympus-new-profile .row { display: flex; justify-content: flex-end; gap: 6px; }
#olympus-new-profile button { padding: 4px 12px; border-radius: 6px; cursor: pointer; font: inherit; color: inherit;
  background: transparent; border: 1px solid color-mix(in srgb, currentColor 30%, transparent); }
#olympus-profile-button { display: flex; align-items: center; gap: 8px; margin: 2px var(--sidebar-content-inset, 8px) 0;
  padding: 6px 8px; border-radius: 8px; border: 1px dashed color-mix(in srgb, var(--primary, currentColor) 55%, transparent);
  background: transparent; color: var(--sidebar-foreground, inherit); font: inherit; font-size: 13px; cursor: pointer; text-align: left; }
#olympus-profile-button:hover { background: color-mix(in srgb, var(--primary, Highlight) 12%, transparent); }
#olympus-new-profile button.primary { background: var(--primary, Highlight); color: var(--primary-foreground, HighlightText); border-color: transparent; }`;
  document.head.append(dialogStyle);
  const profileDialog = async () => {
    if (document.getElementById("olympus-new-profile")) return;
    let themes = [];
    try { themes = await (await fetch(HELPER + "/gods/themes")).json(); } catch { return failed(new TypeError()); }
    const d = document.createElement("div");
    d.id = "olympus-new-profile";
    d.innerHTML = `<form><b>New profile</b>
      <label>Name <input name="name" required pattern="[A-Za-z0-9][A-Za-z0-9-]*" placeholder="gamedev" autocomplete="off"></label>
      <label>God <select name="god"><option value="">Pick later (Ctrl+Alt+A)</option>${themes.map((g) =>
        `<option value="${esc(g)}">${esc(g === "mars" ? "Ares (mars)" : g[0].toUpperCase() + g.slice(1))}</option>`).join("")}</select></label>
      <label>What it works on <input name="about" placeholder="Unity games and level design" autocomplete="off"></label>
      <label class="check"><input type="checkbox" name="agent"> Let other chats hand work to it</label>
      <div class="row"><button type="button" data-cancel>Cancel</button><button type="submit" class="primary">Create</button></div></form>`;
    const close = () => d.remove();
    d.querySelector("[data-cancel]").onclick = close;
    d.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    d.querySelector("form").onsubmit = async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      const create = e.target.querySelector("button[type=submit]");
      create.disabled = true;
      create.textContent = "Creating…";  // registering its tools with Claude Code takes a few seconds
      try {
        const res = await post("/profile", { name: f.get("name"), god: f.get("god"), about: f.get("about"), agent: f.get("agent") === "on" });
        close();
        loadGods(res.gods);
        // the sidebar lists chats, so an empty profile isn't there yet; T3's project chooser has it
        toast(res.messages.map(esc).join("<br>") + (res.added ? '<br><button data-start>Start a chat in it</button>' : ""), true);
        document.querySelector("#olympus-toast [data-start]")?.addEventListener("click", () => {
          document.getElementById("olympus-toast")?.remove();
          olympus.pickProject(res.title);  // temporary.js: T3's chooser, picked out of sight
        });
      } catch (err) {
        create.disabled = false;
        create.textContent = "Create";
        failed(err);
      }
    };
    document.body.append(d);
    d.querySelector("input[name=name]").focus();
  };
  // its own labelled row just above the sidebar's bottom row (Settings, Usage), so it's easy to find;
  // a "+" icon among those got missed
  const profileButton = () => {
    const footers = document.querySelectorAll('[data-slot="sidebar-inner"] [data-slot="sidebar-footer"]');
    const footer = footers[footers.length - 1];
    const mine = document.getElementById("olympus-profile-button");
    if (!footer || (mine && mine.nextElementSibling === footer)) return;
    mine?.remove();
    const b = document.createElement("button");
    b.id = "olympus-profile-button";
    b.type = "button";
    b.title = "Make a new profile (agent) with its own folder and god";
    b.innerHTML = PLUS + "<span>New profile</span>";
    b.onclick = (e) => { e.stopPropagation(); profileDialog(); };
    footer.before(b);
  };

  const tick = () => { apply(); buttons(); profileButton(); };
  tick();
  olympus.onDom(tick);
  addEventListener("hashchange", tick);
})();
