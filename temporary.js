// Temporary chats (temporary.py does the files): a button next to New thread starts a chat in the
// hidden "Temporary" project (through T3's own project chooser); the chat is labelled while open, hidden from the sidebar and project
// picker, and deleted with T3's own delete command when you leave it. Chats left behind by a crash
// or by closing T3 are deleted the next time T3 opens.
(() => {
  const HELPER = "http://127.0.0.1:47833";
  const TITLE = "Temporary";
  const post = (path, body) => fetch(HELPER + path, { method: "POST", headers: { "Content-Type": "application/json" },
                                                      body: JSON.stringify(body) }).then((r) => r.json());
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  const style = document.createElement("style");
  style.textContent = `
li[data-thread-item]:has(> [aria-label$=", ${TITLE}"]) { display: none !important; }
[data-olympus-hidden] { display: none !important; }
:root[data-olympus-temporary] [data-slot="composer-host"] { border-style: dashed !important;
  border-color: color-mix(in srgb, var(--primary, currentColor) 80%, transparent) !important; }
#olympus-temp-label { position: relative; z-index: 1; display: flex; align-items: center; gap: 6px; margin: 0 auto 6px; font-size: 12px;
  color: color-mix(in srgb, var(--foreground, CanvasText) 80%, transparent); }
#olympus-temp-label b { color: var(--primary, Highlight); font-weight: 600; }
#olympus-temp-button { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
  border-radius: 6px; background: none; border: 0; color: inherit; cursor: pointer; opacity: .8; }
#olympus-temp-button:hover { opacity: 1; background: color-mix(in srgb, currentColor 10%, transparent); }`;
  document.head.append(style);

  // Lucide "message-square-dashed"
  const ICON = `<svg class="lucide size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 17H7l-4 4v-7"/><path d="M14 17h1"/><path d="M14 3h1"/><path d="M19 3a2 2 0 0 1 2 2"/><path d="M21 14v1a2 2 0 0 1-2 2"/><path d="M21 9v1"/><path d="M3 9v1"/><path d="M5 3a2 2 0 0 0-2 2"/><path d="M9 3h1"/></svg>`;

  // T3 has no "delete thread" the page can call, so send its own command on its own connection,
  // the same message its Delete menu item sends. The connection is the one the page last used.
  let socket = null;
  const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (data) {
    if (typeof data === "string" && data.includes('"orchestration.')) socket = this;
    return send.call(this, data);
  };
  const deleteThread = async (thread) => {
    for (let i = 0; i < 40 && (!socket || socket.readyState !== 1); i++) await wait(250);
    if (!socket) throw new Error("not connected to T3");
    send.call(socket, JSON.stringify({ _tag: "Request", id: 2e9 + Math.floor(Math.random() * 1e8),
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

  const route = () => {
    const parts = location.hash.replace(/^#\/?/, "").split(/[?#]/)[0].split("/");
    return { draft: parts[0] === "draft", thread: parts.length === 2 && parts[0] !== "draft" ? decodeURIComponent(parts[1]) : null };
  };
  const project = () => (document.querySelector('[data-slot="workspace-breadcrumb-text"]') || {}).textContent?.trim();

  // Start one: T3's New thread button opens its project chooser; pick Temporary there.
  const isTemporaryOption = (o) => o.innerText.split(/\n/).some((l) => l.trim() === TITLE);
  let picking = false;
  const start = async () => {
    try { await fetch(HELPER + "/temporary"); } catch { /* the project usually exists already */ }
    const fresh = document.querySelector('button[aria-label="New thread"]');
    if (!fresh) return;
    picking = true;
    fresh.click();
    for (let i = 0; i < 30; i++) {
      await wait(100);
      const option = [...document.querySelectorAll('[role="option"]')].find(isTemporaryOption);
      if (option) { option.removeAttribute("data-olympus-hidden"); option.click(); break; }
    }
    picking = false;
    for (let i = 0; i < 20 && project() !== TITLE; i++) await wait(100);
    document.querySelector('[data-slot="composer-host"] [contenteditable="true"]')?.focus();
  };

  let current = null;  // the temporary chat on screen, deleted when you leave it
  const tick = () => {
    const here = route();
    const temporary = project() === TITLE;
    document.documentElement.toggleAttribute("data-olympus-temporary", temporary);
    if (current && here.thread !== current) { remove(current); current = null; }
    // only a chat T3's own sidebar lists under Temporary (the project name can change a moment
    // before the address does, so the name alone could point at the chat you just left)
    if (temporary && here.thread && document.querySelector(
      `li[data-thread-item$=":${CSS.escape(here.thread)}"] > [aria-label$=", ${TITLE}"]`)) current = here.thread;

    // the label above the composer
    const host = document.querySelector('[data-slot="composer-host"]');
    let label = document.getElementById("olympus-temp-label");
    if (temporary && host) {
      if (!label) {
        label = document.createElement("div");
        label.id = "olympus-temp-label";
        label.innerHTML = `${ICON}<span><b>Temporary chat</b> · not saved to your history, deleted when you leave it</span>`;
      }
      if (label.nextElementSibling !== host && label.nextElementSibling?.id !== "olympus-next") host.before(label);
      label.style.width = host.offsetWidth ? host.offsetWidth + "px" : "";
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
      b.title = "Temporary chat: not saved, deleted when you leave it";
      b.setAttribute("aria-label", "Temporary chat");
      b.innerHTML = ICON;
      b.onclick = (e) => { e.stopPropagation(); start(); };
      fresh.after(b);
    }
  };

  let queued = false;
  new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; tick(); }); }
  }).observe(document.documentElement, { subtree: true, childList: true, characterData: true });
  window.addEventListener("hashchange", tick);

  // chats left behind when T3 was closed or crashed while one was open (main window only)
  if (window === top) setTimeout(async () => {
    try {
      const { threads } = await (await fetch(HELPER + "/temporary")).json();
      for (const t of threads) if (t !== route().thread) remove(t);
    } catch { /* helper not running */ }
  }, 3000);
})();
