// Temporary chats (temporary.py does the files): a button next to New thread starts a chat in the
// hidden "Temporary" project through T3's own project chooser. The chat is labelled while open,
// hidden from the sidebar and the chooser, and deleted with T3's own delete command when you explicitly
// leave it. Chats left behind by a crash or by closing T3 are deleted the next time T3 opens.
(() => {
  const { HELPER } = olympus;
  const TITLE = "Temporary";
  // like olympus.post, but an error reply is returned rather than thrown: purge is retried until T3 has deleted
  const post = (path, body) => olympus.post(path, body).catch((e) => (e instanceof TypeError ? Promise.reject(e) : { error: e.message }));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  const style = document.createElement("style");
  style.textContent = `
/* saved temporary chats and unsent temporary drafts alike */
[data-slot="sidebar-inner"] li:has(> [aria-label$=", ${TITLE}"]) { display: none !important; }
[data-olympus-hidden] { display: none !important; }
:root[data-olympus-temporary] [data-slot="composer-host"] { border: 2px dashed var(--primary, currentColor) !important; }
#olympus-temp-label { order: 0; align-self: flex-start; display: inline-flex; align-items: center; gap: 6px;
  max-width: 100%; padding: 3px 10px 3px 8px; border-radius: 999px; font-size: 12px; line-height: 18px; white-space: nowrap;
  color: color-mix(in srgb, var(--foreground, CanvasText) 85%, transparent);
  background: color-mix(in srgb, var(--primary, Highlight) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary, Highlight) 45%, transparent); }
#olympus-temp-label svg { flex: none; width: 14px; height: 14px; color: var(--primary, Highlight); }
#olympus-temp-label b { font-weight: 600; color: var(--foreground, CanvasText); }
#olympus-temp-label span { overflow: hidden; text-overflow: ellipsis; }
#olympus-temp-button { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 24px; /* narrow: the row is full */
  border-radius: 6px; background: none; border: 0; color: inherit; cursor: pointer; opacity: .8; }
#olympus-temp-button:hover { opacity: 1; background: color-mix(in srgb, currentColor 10%, transparent); }
/* the extra button costs the Search box its last letters; its right padding gives them back */
[data-slot="sidebar-inner"] div:has(> span > input[placeholder="Search"]) { padding-right: 2px !important; }
#olympus-temp-button[aria-pressed="true"] { opacity: 1; color: var(--primary, Highlight);
  background: color-mix(in srgb, var(--primary, Highlight) 18%, transparent); }
/* while the button picks a project, T3's chooser stays invisible */
:root[data-olympus-picking] [role="dialog"]:has([role="option"]),
:root[data-olympus-picking] [data-slot$="backdrop"] { opacity: 0 !important; }`;
  document.head.append(style);

  // Lucide "message-square-dashed"
  const ICON = `<svg class="lucide size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 17H7l-4 4v-7"/><path d="M14 17h1"/><path d="M14 3h1"/><path d="M19 3a2 2 0 0 1 2 2"/><path d="M21 14v1a2 2 0 0 1-2 2"/><path d="M21 9v1"/><path d="M3 9v1"/><path d="M5 3a2 2 0 0 0-2 2"/><path d="M9 3h1"/></svg>`;

  // T3 has no "delete thread" the page can call, so send its own command on its own connection,
  // the same message its Delete menu item sends. olympus-hook.js records that connection.
  const deleteThread = async (thread) => {
    const t3 = () => window.olympusT3Socket;
    for (let i = 0; i < 40 && (!t3() || t3().readyState !== 1); i++) await wait(250);
    if (!t3()) throw new Error("not connected to T3");
    t3().send(JSON.stringify({ _tag: "Request", id: 2e9 + Math.floor(Math.random() * 1e8),
      tag: "orchestration.dispatchCommand", headers: [],
      payload: { type: "thread.delete", commandId: crypto.randomUUID(), threadId: thread } }));
  };

  const removing = new Set();
  const remove = async (thread) => {
    if (removing.has(thread)) return;
    removing.add(thread);
    try {
      // the helper checks T3's database that this is a temporary chat, and notes its files;
      // anything else is never deleted
      if (!(await post("/temporary/leaving", { thread })).ok) return;
      await deleteThread(thread);
      for (let i = 0; i < 20; i++) {  // then removes them once T3 has deleted the chat
        await wait(500);
        const r = await post("/temporary/purge", { thread });
        if (r.ok) return;
      }
    } catch { /* helper not running: the next launch clears it */ } finally { removing.delete(thread); }
  };

  const project = () => (document.querySelector('[data-slot="workspace-breadcrumb-text"]') || {}).textContent?.trim();

  // T3's New thread button opens its project chooser. The button picks an entry there: Temporary to
  // start a temporary chat, or (from inside one) the project you were last in, to go back. The
  // chooser is hidden while this happens, and the entry is picked on the next frame it appears.
  // an entry's lines, read from its text pieces: no layout, and works on an entry hidden by this script
  const lines = (o) => [...o.querySelectorAll("*")].filter((e) => !e.children.length).map((e) => e.textContent.trim());
  const isOption = (title) => (o) => lines(o).includes(title);
  const isTemporaryOption = isOption(TITLE);
  const LAST = "olympus:last-project";
  // the next frame, or 50 ms if T3 is in the background (frames pause there)
  const frame = () => new Promise((r) => { requestAnimationFrame(r); setTimeout(r, 50); });
  let picking = false;
  // the first entry match accepts, else (when given) the first one fallback accepts
  const choose = async (match, fallback) => {
    const fresh = document.querySelector('button[aria-label="New thread"]');
    if (!fresh || picking) return;
    picking = true;
    document.documentElement.setAttribute("data-olympus-picking", "");
    let selected = false;
    try {
      fresh.click();
      for (const end = performance.now() + 2000; performance.now() < end;) {
        await frame();
        const options = [...document.querySelectorAll('[role="option"]')];
        const option = options.find(match) || (fallback && options.find(fallback));
        if (option) { option.removeAttribute("data-olympus-hidden"); option.click(); selected = true; break; }
      }
    } finally {
      picking = false;
      document.documentElement.removeAttribute("data-olympus-picking");
    }
    olympus.box()?.focus();
    return selected;
  };
  // shared with olympus.js's New profile button ("Start a chat in it")
  olympus.pickProject = (title) => choose(isOption(title));
  const start = () => {
    fetch(HELPER + "/temporary").catch(() => {});  // makes sure the project exists; no need to wait
    return choose(isTemporaryOption).then(() => project() === TITLE || wait(300).then(() => choose(isTemporaryOption)));  // T3 still starting: once more
  };
  const leave = async () => {
    let last = null;
    try { last = localStorage.getItem(LAST); } catch { /* none */ }
    const match = (o) => !isTemporaryOption(o) && last && lines(o).includes(last);
    // no remembered project: the first real one in the list (it shows its folder path)
    leaving = true;
    try {
      const selected = await choose(match, (o) => !isTemporaryOption(o) && lines(o).some((l) => /[\\/]/.test(l)));
      if (selected) {
        exiting = true;
        const thread = current;
        current = null;
        route = null;
        remember();
        if (thread) remove(thread);
      }
    } finally { leaving = false; }
    tick();
  };

  // Navigation to Usage/settings is not an exit. Keep this window's temporary
  // route so T3's default landing page cannot silently switch back to Projects.
  const ACTIVE = window === top ? "olympus:temporary" : "olympus:temporary-pane";
  let current = null;
  let route = null;
  let leaving = false;
  let exiting = false;
  try {
    const active = JSON.parse(sessionStorage.getItem(ACTIVE) || "null");
    if (active && typeof active.route === "string" && /^#\/[^/]+\/[^/]+$/.test(active.route)) {
      current = active.thread || null;
      route = active.route;
    }
  } catch { /* storage unavailable */ }
  const remember = () => {
    try {
      if (route) sessionStorage.setItem(ACTIVE, JSON.stringify({ thread: current, route }));
      else sessionStorage.removeItem(ACTIVE);
    } catch { /* storage unavailable */ }
  };
  let saved = null;  // the last project written to localStorage
  const tick = () => {
    const here = { thread: olympus.threadId() };
    const name = project();
    // The chooser click can precede React's breadcrumb/route update. Do not
    // recapture the old temporary thread while an explicit exit is settling.
    if (exiting) {
      if (!name || name === TITLE) return;
      exiting = false;
    }
    const host = document.querySelector(olympus.COMPOSER);
    const auxiliary = /^#\/?(?:settings|usage|pull-requests)(?:[/?#]|$)/.test(location.hash);
    if (route && !leaving && !picking && !auxiliary && host && location.hash !== route) {
      // A draft becoming a saved temporary thread is the same conversation.
      const ownThread = name === TITLE && here.thread && document.querySelector(
        `li[data-thread-item$=":${CSS.escape(here.thread)}"] > [aria-label$=", ${TITLE}"]`);
      if (!ownThread) { location.hash = route; return; }
    }
    const temporary = Boolean(route) || name === TITLE;
    document.documentElement.toggleAttribute("data-olympus-temporary", temporary);
    // remember the last real project, to go back to from a temporary chat
    if (name && !temporary && name !== "No project" && name !== saved) {
      saved = name;
      try { localStorage.setItem(LAST, name); } catch { /* not kept */ }
    }
    // Only learn routes confirmed by T3's project/sidebar, never a settings route.
    if (!leaving && !picking && name === TITLE && !auxiliary &&
        ((!here.thread && /^#\/?draft\//.test(location.hash)) ||
         (here.thread && document.querySelector(
           `li[data-thread-item$=":${CSS.escape(here.thread)}"] > [aria-label$=", ${TITLE}"]`)))) {
      current = here.thread;
      route = location.hash;
      remember();
    }

    // the label above the composer
    let label = document.getElementById("olympus-temp-label");
    if (temporary && host) {
      if (!label) {
        label = document.createElement("div");
        label.id = "olympus-temp-label";
        label.title = "Not saved to your chat history. Deleted when you click Leave temporary chat.";
        label.innerHTML = `${ICON}<span><b>Temporary chat</b> · not saved, kept until you exit</span>`;
      }
      olympusAbove(label);
    } else if (label) label.remove();

    // keep Temporary out of the project picker, except while this script picks it
    if (!picking) document.querySelectorAll('[role="option"]').forEach((o) =>
      o.toggleAttribute("data-olympus-hidden", isTemporaryOption(o)));

    // the button, next to T3's own New thread button
    const fresh = document.querySelector('button[aria-label="New thread"]');
    if (fresh && !document.getElementById("olympus-temp-button")) {
      const b = document.createElement("button");
      b.id = "olympus-temp-button";
      b.type = "button";
      b.innerHTML = ICON;
      b.onclick = (e) => { e.stopPropagation(); (route || project() === TITLE ? leave : start)(); };
      fresh.after(b);
    }
    // the same button takes you back out of a temporary chat
    const b = document.getElementById("olympus-temp-button");
    if (b && b.getAttribute("aria-pressed") !== String(temporary)) {
      b.setAttribute("aria-pressed", String(temporary));
      b.title = temporary ? "Leave temporary chat: back to a normal new chat" : "Temporary chat: not saved, deleted when you leave it";
      b.setAttribute("aria-label", temporary ? "Leave temporary chat" : "Temporary chat");
    }
  };

  olympus.onDom(tick);
  window.addEventListener("hashchange", tick);

  // chats left behind when T3 was closed or crashed while one was open (main window only)
  if (window === top) setTimeout(async () => {
    try {
      const { threads } = await (await fetch(HELPER + "/temporary")).json();
      // chats on screen are kept: the main chat and the split pane's (split.js keeps its route)
      let pane = null;
      try { pane = sessionStorage.getItem("olympus:split"); } catch { /* none */ }
      const open = new Set([current, olympus.threadId(), pane && decodeURIComponent(pane.split("/").pop())]);
      for (const t of threads) if (!open.has(t)) remove(t);
    } catch { /* helper not running */ }
  }, 3000);
})();
