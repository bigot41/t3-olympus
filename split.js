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
/* The pane sits outside T3's own layout, fixed at the window's right edge, and the chat area gets a
   margin of its width. T3 re-rendering never touches it (moving a frame in the page reloads it), and
   it slides in and out with transform alone, so the graphics card animates it without laying the
   page out again per frame. The chat inside fades in once T3 has drawn it. */
#olympus-split { position: fixed; top: 0; right: 0; bottom: 0; width: var(--olympus-split-px, 45vw); z-index: 30; display: flex;
  background: var(--background, Canvas); overflow: hidden; contain: layout paint style;
  border-left: 1px dotted color-mix(in srgb, var(--foreground, currentColor) 35%, transparent);
  transition: transform .4s cubic-bezier(.16, 1, .3, 1), opacity .4s cubic-bezier(.16, 1, .3, 1); }
#olympus-split.off { transform: translate3d(100%, 0, 0); opacity: .3; pointer-events: none;
  transition-duration: .28s; transition-timing-function: cubic-bezier(.7, 0, .84, 0); }
#olympus-split.opening { transition: none; }
:root[data-olympus-split] main[data-slot="sidebar-inset"] { margin-right: var(--olympus-split-px) !important; }
#olympus-split iframe { flex: 1; border: 0; width: 100%; height: 100%; background: var(--background, Canvas);
  opacity: 0; transition: opacity .3s ease-out; }
#olympus-split.ready iframe { opacity: 1; }
#olympus-split-guide { position: fixed; top: 0; bottom: 0; left: 0; width: 2px; z-index: 31; pointer-events: none;
  background: var(--primary, Highlight); will-change: transform; }
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
@media (prefers-reduced-motion: reduce) { #olympus-split, #olympus-split.off, #olympus-split iframe { transition: none; } }
#olympus-split .resize { position: absolute; left: 0; top: 0; bottom: 0; width: 8px; cursor: col-resize; z-index: 5; }
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

  const WIDTH = "olympus:split-w";
  const MIN = 320;
  // the pane's width in px, kept between the chat area's minimum and the window
  const setWidth = (px) => {
    const w = Math.round(Math.max(MIN, Math.min(px, innerWidth - 360)));
    document.documentElement.style.setProperty("--olympus-split-px", w + "px");
    return w;
  };

  const open = (route) => {
    const m = main();
    if (!m) return;
    let pane = document.getElementById("olympus-split");
    if (!pane || pane.classList.contains("off")) {
      pane?.remove();  // it was closing
      let saved = 0;
      try { saved = +localStorage.getItem(WIDTH) || 0; } catch { /* default */ }
      setWidth(saved || m.getBoundingClientRect().width * 0.45);
      pane = document.createElement("div");
      pane.id = "olympus-split";
      pane.className = "off opening";
      pane.innerHTML = `<div class="resize" title="Drag to resize"></div><button class="close" title="Close split view">×</button>` +
        `<iframe></iframe><div class="loading"><i></i><span>Opening chat…</span></div>`;
      pane.querySelector(".close").onclick = close;
      pane.querySelector(".resize").onpointerdown = resize;
      // each time T3 loads in the frame (a reload too), wait for its chat again
      pane.querySelector("iframe").addEventListener("load", (e) => watch(pane, e.target));
      document.body.append(pane);
      document.documentElement.setAttribute("data-olympus-split", "");
      pane.getBoundingClientRect();  // start off-screen, then slide in
      pane.classList.remove("opening", "off");
    }
    const frame = pane.querySelector("iframe");
    if (frame.dataset.route !== route) { frame.dataset.route = route; frame.src = base() + "#/" + route; watch(pane, frame); }
    try { sessionStorage.setItem(KEY, route); } catch { /* not kept */ }
  };
  // Show the chat once T3 has drawn it inside the frame: its message box, not just the empty chat
  // area T3 draws first. If it hasn't after 10 s, say what the frame shows, with a Reload button.
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
      if (doc?.querySelector(`main[data-slot="sidebar-inset"] ${olympus.COMPOSER}`)) {
        clearInterval(pane.watching);
        pane.classList.add("ready");
        return;
      }
      if (Date.now() - started < 10000) return;
      clearInterval(pane.watching);
      const errors = (frame.contentWindow?.olympusFrameErrors || []).slice(-3);
      const shown = doc?.querySelector('main[data-slot="sidebar-inset"]')?.innerText.trim().slice(0, 120);
      why = why || [`address ${doc?.location?.href || frame.src}`, `page ${doc?.readyState || "not loaded"}`,
                    `${doc?.body?.childElementCount ?? 0} elements`, shown ? `shows "${shown}"` : "chat area empty", ...errors].join(" · ");
      note.className = "loading failed";
      note.innerHTML = `<span>This chat didn't open in the split pane.</span><code>${olympus.esc(why)}</code><button>Reload pane</button>`;
      note.querySelector("button").onclick = () => { frame.src = "about:blank"; setTimeout(() => { frame.src = base() + "#/" + frame.dataset.route; }, 50); };
    }, 200);
  };
  const close = () => {
    const pane = document.getElementById("olympus-split");
    if (!pane || pane.classList.contains("off")) return;
    clearInterval(pane.watching);
    try { sessionStorage.removeItem(KEY); } catch { /* nothing kept */ }
    const done = () => {
      if (!pane.isConnected) return;
      pane.remove();
      if (!document.getElementById("olympus-split")) document.documentElement.removeAttribute("data-olympus-split");
    };
    pane.classList.add("off");  // slides out, then the chat area takes the room back
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return done();
    pane.addEventListener("transitionend", (e) => { if (e.target === pane && e.propertyName === "transform") done(); });
    setTimeout(done, 450);  // in case the transition never runs
  };
  // The divider: while you drag, only a thin line follows the pointer (moved by transform, so it
  // keeps up); the two chats are laid out again once, when you let go.
  const resize = (e) => {
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    const guide = Object.assign(document.createElement("div"), { id: "olympus-split-guide" });
    const left = main()?.getBoundingClientRect().left || 0;
    const clamp = (x) => Math.max(left + 360, Math.min(x, innerWidth - MIN));
    let x = clamp(e.clientX), queued = false;
    const apply = () => { queued = false; guide.style.transform = `translate3d(${x - 1}px, 0, 0)`; };
    apply();
    document.body.append(guide);
    const move = (ev) => { x = clamp(ev.clientX); if (!queued) { queued = true; requestAnimationFrame(apply); } };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      guide.remove();
      const w = setWidth(innerWidth - x);
      try { localStorage.setItem(WIDTH, w); } catch { /* not kept */ }
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  };
  // a smaller window: keep room for the main chat
  addEventListener("resize", () => {
    if (!document.getElementById("olympus-split")) return;
    const w = parseFloat(document.documentElement.style.getPropertyValue("--olympus-split-px"));
    if (w > innerWidth - 360) setWidth(w);
  });

  // Dragging a sidebar chat: past a few pixels it becomes a drag (T3 tracks the pointer itself;
  // it starts no browser drag for these rows). With no split, dropping it on the chat area opens
  // it beside the current chat. With a split open, the side under the pointer is outlined
  // ("Replace this chat") and dropping swaps that side's chat; two chats is the most. Over a
  // message box the outline hugs the box ("Add to message") and dropping adds the chat to it as a
  // chip (T3 does that itself for some rows; chipAt fills in for the rest). A plain click still opens the chat.
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
  // the chat as a chip in the message box under (x, y), unless T3 already put it there
  const chipAt = (x, y, route, title) => {
    const c = main()?.querySelector(olympus.COMPOSER);
    const pc = paneComposer();
    const host = c && within(c.getBoundingClientRect(), x, y) ? c : pc && within(pc.box, x, y) ? pc.host : null;
    const editor = host?.querySelector(".ProseMirror")?.editor;
    if (!editor) return;
    const id = "thread_" + decodeURIComponent(route.split("/").pop());
    setTimeout(() => {
      if (JSON.stringify(editor.getJSON()).includes(`"contextId":"${id}"`)) return;
      editor.chain().focus("end").insertContent([
        { type: "composer-context-reference",
          attrs: { kind: "thread", contextId: id, label: title, source: `[${title}](t3-context://v1/thread/${id})` } },
        { type: "text", text: " " }]).run();
    }, 120);
  };
  // A sidebar row's chat as a route ("env/thread") and its title. Chat rows carry "env:thread";
  // rows under a project carry only "true", with the id in their button's test id, so the
  // environment comes from the open chat or another row.
  const rowChat = (row) => {
    const key = row.dataset.threadItem || "";
    const cut = key.indexOf(":");
    let env = cut > 0 ? key.slice(0, cut) : "", thread = cut > 0 ? key.slice(cut + 1) : "";
    if (!thread) {
      thread = (row.querySelector('[data-testid^="thread-row-"]')?.dataset.testid || "").slice("thread-row-".length);
      const here = location.hash.replace(/^#\/?/, "").split("/");
      const other = [...document.querySelectorAll("li[data-thread-item]")].map((r) => r.dataset.threadItem).find((k) => k.includes(":"));
      env = olympus.threadId() ? here[0] : other ? other.split(":")[0] : "";
    }
    if (!env || !thread) return null;
    const button = row.querySelector('[role="button"]');
    const title = (button?.getAttribute("aria-label") || button?.innerText.split("\n")[0] || "Chat").split(",")[0].trim();
    return { route: `${env}/${encodeURIComponent(thread)}`, title };
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
    const chat = row && rowChat(row);
    if (!chat) return;
    drag = { x: e.clientX, y: e.clientY, at: { x: e.clientX, y: e.clientY }, zone: null, ...chat };
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
    chipAt(e.clientX, e.clientY, d.route, d.title);
    d.target?.drop(d.route);
    // the drag ends with a click on whatever is underneath; don't let it open the chat here too
    const eat = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
    addEventListener("click", eat, { capture: true, once: true });
    setTimeout(() => removeEventListener("click", eat, true), 300);
  }, true);

  // bring the pane back after a reload
  try { const route = sessionStorage.getItem(KEY); if (route) setTimeout(() => open(route), 1500); } catch { /* none */ }
})();
