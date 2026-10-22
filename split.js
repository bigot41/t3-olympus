// Split view, like Claude desktop's: drag a chat from the sidebar onto the chat area and it opens
// beside the current one. With a split open, dropping a chat on either side replaces that side. The second pane is T3 itself in a frame (patch.py lets frames use the
// desktop bridge), so it's a full chat with its own composer. Drag the divider to resize; × closes.
(() => {
  // T3 keeps its toolbar a fixed distance from the window's right edge, leaving room for the
  // window's own minimize / maximize / close buttons. A pane sits at that edge but can't know
  // about those buttons, so it takes their width from the main window.
  const CONTROLS = "[data-workspace-titlebar-controls]";
  const HEADER = `header:has(> ${CONTROLS})`;
  if (window !== top) {  // inside a pane: no sidebar, no nested splits, room for the window buttons
    const css = document.createElement("style");
    css.textContent = `
[data-slot="sidebar"], [data-slot="sidebar-gap"], [data-slot="sidebar-container"] { display: none !important; }
${CONTROLS} { right: calc(var(--olympus-window-buttons, 0px) + 12px) !important; }
${HEADER} { padding-right: calc(var(--olympus-window-buttons, 0px) + 20px) !important; }`;
    document.head.append(css);
    const measure = () => {
      const o = top.navigator.windowControlsOverlay;
      const r = o && o.visible ? o.getTitlebarAreaRect() : null;
      const width = r ? Math.max(0, top.innerWidth - (r.x + r.width)) : 0;
      document.documentElement.style.setProperty("--olympus-window-buttons", width + "px");
      // T3 sizes its top bar from the window's title bar height, which only the main window
      // knows; without it a pane's bar is 52px instead of 40px and sits out of line
      if (r) document.documentElement.style.setProperty("--workspace-topbar-height", r.height + "px");
    };
    measure();
    top.navigator.windowControlsOverlay?.addEventListener("geometrychange", measure);
    top.addEventListener("resize", measure);
    return;
  }
  const KEY = "olympus:split";
  const style = document.createElement("style");
  style.textContent = `
#olympus-split { position: relative; flex: 0 0 var(--olympus-split-w, 45%); min-width: 320px; display: flex;
  border-left: 1px dotted color-mix(in srgb, var(--foreground, currentColor) 35%, transparent); }
#olympus-split iframe { flex: 1; border: 0; width: 100%; height: 100svh; background: var(--background, Canvas);
  opacity: 0; transform: translate3d(18px, 0, 0) scale(.985); transform-origin: left center;
  transition: opacity .35s ease-out, transform .55s cubic-bezier(.2, .9, .25, 1.05); }
/* the pane slides open from the divider; the chat fades in once T3 has drawn it inside */
#olympus-split { overflow: hidden; animation: olympus-split-in .5s cubic-bezier(.22, 1, .36, 1); }
#olympus-split.ready iframe { opacity: 1; transform: none; }
#olympus-split.closing { animation: olympus-split-out .32s cubic-bezier(.4, 0, .9, .6) forwards; pointer-events: none; }
@keyframes olympus-split-in { from { flex-basis: 0; min-width: 0; opacity: .4; } }
@keyframes olympus-split-out { to { flex-basis: 0; min-width: 0; opacity: 0; } }
#olympus-split .loading { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 10px; padding: 24px; text-align: center; font-size: 13px; pointer-events: none;
  color: color-mix(in srgb, var(--foreground, CanvasText) 70%, transparent); transition: opacity .3s; }
#olympus-split.ready .loading { opacity: 0; }
#olympus-split .loading i { width: 18px; height: 18px; border-radius: 50%; animation: olympus-spin .8s linear infinite;
  border: 2px solid color-mix(in srgb, var(--primary, Highlight) 30%, transparent); border-top-color: var(--primary, Highlight); }
#olympus-split .loading.failed { pointer-events: auto; }
#olympus-split .loading.failed i { display: none; }
#olympus-split .loading code { max-width: 100%; overflow-wrap: anywhere; font-size: 11px; opacity: .8; }
#olympus-split .loading button { padding: 4px 12px; border-radius: 6px; cursor: pointer; font: inherit; border: 0;
  background: var(--primary, Highlight); color: var(--primary-foreground, HighlightText); }
@keyframes olympus-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { #olympus-split, #olympus-split iframe { animation: none; transition: none; } }
#olympus-split .resize { position: absolute; left: -4px; top: 0; bottom: 0; width: 8px; cursor: col-resize; z-index: 5; }
#olympus-split .close { position: absolute; top: 52px; right: 12px; z-index: 5; width: 24px; height: 24px; border: 0;
  border-radius: 6px; cursor: pointer; font-size: 16px; line-height: 1; color: var(--foreground, CanvasText);
  background: color-mix(in srgb, var(--foreground, currentColor) 10%, transparent); }
/* with a split open, the main chat's toolbar belongs at the main chat's edge, not the window's */
:root[data-olympus-split] ${CONTROLS} { right: calc(var(--olympus-split-px) + 12px) !important; }
:root[data-olympus-split] ${HEADER} { padding-right: 20px !important; }
#olympus-drop.box { border-radius: 26px; align-items: flex-start; justify-content: flex-end; padding: 6px 14px; font-size: 12px;
  background: color-mix(in srgb, var(--primary, Highlight) 6%, transparent); }
#olympus-drop { position: fixed; z-index: 9998; pointer-events: none; border-radius: 10px;
  border: 2px dashed var(--primary, Highlight); background: color-mix(in srgb, var(--primary, Highlight) 12%, transparent);
  display: flex; align-items: center; justify-content: center; font-size: 14px; color: var(--foreground, CanvasText); }
:root[data-olympus-dragging], :root[data-olympus-dragging] * { user-select: none !important; cursor: grabbing !important; }
:root[data-olympus-dragging] #olympus-split iframe { pointer-events: none; }`;
  document.head.append(style);

  const main = () => document.querySelector('main[data-slot="sidebar-inset"]');
  const base = () => location.origin + location.pathname;

  const open = (route) => {
    const m = main();
    if (!m) return;
    let pane = document.getElementById("olympus-split");
    if (!pane) {
      pane = document.createElement("div");
      pane.id = "olympus-split";
      pane.innerHTML = `<div class="resize" title="Drag to resize"></div><button class="close" title="Close split view">×</button>` +
        `<iframe></iframe><div class="loading"><i></i><span>Opening chat…</span></div>`;
      pane.querySelector(".close").onclick = close;
      pane.querySelector(".resize").onpointerdown = resize;
    }
    pane.classList.remove("closing");
    if (pane.previousElementSibling !== m) m.after(pane);
    document.documentElement.setAttribute("data-olympus-split", "");
    if (!pane.sized) {
      pane.sized = new ResizeObserver(() => document.documentElement.style.setProperty(
        "--olympus-split-px", pane.getBoundingClientRect().width + "px"));
      pane.sized.observe(pane);
    }
    const frame = pane.querySelector("iframe");
    if (frame.dataset.route !== route) { frame.dataset.route = route; frame.src = base() + "#/" + route; watch(pane, frame); }
    try { sessionStorage.setItem(KEY, route); } catch { /* not kept */ }
  };
  // Show the chat once T3 has drawn it inside the frame. If it hasn't after 10 s, say what the
  // frame reports instead of leaving the pane blank, with a Reload button.
  const watch = (pane, frame) => {
    clearInterval(pane.watching);
    pane.classList.remove("ready");
    const note = pane.querySelector(".loading");
    note.className = "loading";
    note.innerHTML = "<i></i><span>Opening chat…</span>";
    const started = Date.now();
    pane.watching = setInterval(() => {
      let doc = null, why = "";
      try { doc = frame.contentDocument; } catch (e) { why = "the frame can't be read: " + e.message; }
      if (doc?.querySelector('main[data-slot="sidebar-inset"]')) {
        clearInterval(pane.watching);
        pane.classList.add("ready");
        return;
      }
      if (Date.now() - started < 10000) return;
      clearInterval(pane.watching);
      const errors = (frame.contentWindow?.olympusFrameErrors || []).slice(-3);
      why = why || [`address ${doc?.location?.href || frame.src}`, `page ${doc?.readyState || "not loaded"}`,
                    `${doc?.body?.childElementCount ?? 0} elements`, ...errors].join(" · ");
      note.className = "loading failed";
      note.innerHTML = `<span>This chat didn't open in the split pane.</span><code>${olympus.esc(why)}</code><button>Reload pane</button>`;
      note.querySelector("button").onclick = () => { frame.src = "about:blank"; setTimeout(() => { frame.src = base() + "#/" + frame.dataset.route; watch(pane, frame); }, 50); };
    }, 200);
  };
  const close = () => {
    const pane = document.getElementById("olympus-split");
    if (!pane || pane.classList.contains("closing")) return;
    clearInterval(pane.watching);
    try { sessionStorage.removeItem(KEY); } catch { /* nothing kept */ }
    const done = () => {
      if (!pane.classList.contains("closing") && !matchMedia("(prefers-reduced-motion: reduce)").matches) return;  // reopened meanwhile
      pane.sized?.disconnect();
      pane.remove();
      document.documentElement.removeAttribute("data-olympus-split");
    };
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return done();
    pane.classList.add("closing");  // slides shut, then goes
    pane.addEventListener("animationend", (e) => { if (e.target === pane) done(); });
    setTimeout(done, 500);  // in case the animation never runs
  };
  const resize = (e) => {
    e.preventDefault();
    const pane = document.getElementById("olympus-split");
    const right = pane.getBoundingClientRect().right;
    document.documentElement.setAttribute("data-olympus-dragging", "");
    const move = (ev) => pane.style.setProperty("--olympus-split-w", Math.max(320, right - ev.clientX) + "px");
    const up = () => { document.documentElement.removeAttribute("data-olympus-dragging");
                       removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  };

  // Dragging a sidebar chat: past a few pixels it becomes a drag (T3 tracks the pointer itself;
  // it starts no browser drag for these rows). With no split, dropping it on the chat area opens
  // it beside the current chat. With a split open, the side under the pointer is outlined
  // ("Replace this chat") and dropping swaps that side's chat; two chats is the most. Over a
  // message box the outline hugs the box ("Add to message"): T3 adds the chat to the main box as a
  // chip itself, and chipInPane does the same for the pane's box. A plain click still opens the chat.
  const zones = () => {
    const m = main()?.getBoundingClientRect();
    if (!m) return [];
    const pane = document.getElementById("olympus-split");
    if (!pane) return [{ hit: m, box: { left: m.left + m.width / 2, top: m.top, width: m.width / 2, height: m.height },
                         label: "Open in split view", drop: open }];
    const p = pane.getBoundingClientRect();
    return [{ hit: m, box: m, label: "Replace this chat", drop: (route) => { location.hash = "#/" + route; } },
            { hit: p, box: p, label: "Replace this chat", drop: open }];
  };
  const within = (r, x, y) => x > r.left && x < r.left + r.width && y > r.top && y < r.top + r.height;
  // the pane's message box, with its box in this window's coordinates
  const paneComposer = () => {
    const frame = document.querySelector("#olympus-split iframe");
    const host = frame?.contentDocument?.querySelector(olympus.COMPOSER);
    if (!host) return null;
    const f = frame.getBoundingClientRect(), r = host.getBoundingClientRect();
    return { host, box: { left: f.left + r.left, top: f.top + r.top, width: r.width, height: r.height } };
  };
  // the message box at (x, y), in the main chat or the pane
  const composerAt = (x, y) => {
    const c = main()?.querySelector(olympus.COMPOSER)?.getBoundingClientRect();
    if (c && within(c, x, y)) return c;
    const pc = paneComposer();
    return pc && within(pc.box, x, y) ? pc.box : null;
  };
  const targetAt = (x, y) => {
    const box = composerAt(x, y);
    if (box) return { box, label: "Add to message", composer: true, drop: () => {} };
    return zones().find((z) => within(z.hit, x, y)) || null;
  };
  const chipInPane = (x, y, route, title) => {
    const pc = paneComposer();
    const editor = pc && within(pc.box, x, y) && pc.host.querySelector(".ProseMirror")?.editor;
    if (!editor) return;
    const id = "thread_" + decodeURIComponent(route.split("/").pop());
    editor.chain().focus("end").insertContent([
      { type: "composer-context-reference",
        attrs: { kind: "thread", contextId: id, label: title, source: `[${title}](t3-context://v1/thread/${id})` } },
      { type: "text", text: " " }]).run();
  };

  let drag = null, frameQueued = false;
  const show = (z) => {
    if (z) {
      const inset = z.composer ? -4 : 8;  // a message box gets a ring just outside it
      Object.assign(drag.zone.style, { left: z.box.left + inset + "px", top: z.box.top + inset + "px",
                                       width: z.box.width - 2 * inset + "px", height: z.box.height - 2 * inset + "px" });
      drag.zone.classList.toggle("box", !!z.composer);
      if (drag.zone.textContent !== z.label) drag.zone.textContent = z.label;
      if (!drag.zone.isConnected) document.body.append(drag.zone);
    } else drag.zone.remove();
    drag.target = z;
  };
  const update = () => {
    frameQueued = false;
    if (drag?.zone) show(targetAt(drag.at.x, drag.at.y));
  };

  addEventListener("pointerdown", (e) => {
    const row = e.button === 0 && e.target.closest("li[data-thread-item]");
    if (!row) return;
    const [env, thread] = row.dataset.threadItem.split(":");
    drag = { x: e.clientX, y: e.clientY, at: { x: e.clientX, y: e.clientY }, zone: null,
             route: `${env}/${encodeURIComponent(thread)}`,
             title: (row.firstElementChild?.getAttribute("aria-label") || "Chat").split(",")[0] };
  }, true);
  addEventListener("pointermove", (e) => {
    if (!drag) return;
    drag.at = { x: e.clientX, y: e.clientY };
    if (!drag.zone) {
      if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 12) return;
      drag.zone = Object.assign(document.createElement("div"), { id: "olympus-drop" });
      // the pane stops taking the pointer, and nothing gets text-selected, while dragging
      document.documentElement.setAttribute("data-olympus-dragging", "");
      getSelection()?.removeAllRanges();
    }
    e.preventDefault();
    if (!frameQueued) { frameQueued = true; requestAnimationFrame(update); }
  }, true);
  addEventListener("pointerup", (e) => {
    const d = drag;
    drag = null;
    if (!d?.zone) return;  // a click, not a drag
    document.documentElement.removeAttribute("data-olympus-dragging");
    d.zone.remove();
    chipInPane(e.clientX, e.clientY, d.route, d.title);
    d.target?.drop(d.route);
    // the drag ends with a click on whatever is underneath; don't let it open the chat here too
    const eat = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
    addEventListener("click", eat, { capture: true, once: true });
    setTimeout(() => removeEventListener("click", eat, true), 300);
  }, true);

  // keep the pane next to the chat area (T3 re-renders it) and bring it back after a reload
  olympus.onDom(() => {
    const pane = document.getElementById("olympus-split");
    const m = pane && main();
    if (m && pane.previousElementSibling !== m) m.after(pane);
  });
  try { const route = sessionStorage.getItem(KEY); if (route) setTimeout(() => open(route), 1500); } catch { /* none */ }
})();
