// The task list and next-step box above the composer, like Claude desktop's. olympus-hook.js
// re-fires T3's own thread events ("olympus:thread"); this keeps each chat's turn items and run
// status, asks OlympusTurn.view (turnlogic.js) what to show, and draws it. Nothing polls: a chat
// T3 opened before sends no history over its socket, so its past calls come once from the helper.
(() => {
  const { HELPER, esc, threadId } = olympus;
  const style = document.createElement("style");
  style.textContent = `
#olympus-turn { order: 1; padding: 10px 14px; font-size: 13px; line-height: 1.5; border-radius: 8px;
  background: var(--card, Canvas); color: var(--foreground, CanvasText);
  border: 1px dotted color-mix(in srgb, var(--primary, currentColor) 70%, transparent); }
#olympus-turn .old { font-size: 11px; opacity: .65; margin-bottom: 4px; }
#olympus-turn ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
#olympus-turn li { display: flex; gap: 8px; align-items: flex-start; }
#olympus-turn li.completed, #olympus-turn li.pending { color: color-mix(in srgb, var(--foreground, CanvasText) 55%, transparent); }
#olympus-turn li .i { flex: none; width: 14px; height: 14px; margin-top: 3px; display: inline-flex; align-items: center; justify-content: center; }
#olympus-turn li.completed .i { border-radius: 50%; background: var(--primary, Highlight); color: var(--primary-foreground, HighlightText); font-size: 9px; }
#olympus-turn li.pending .i { border-radius: 50%; border: 1.5px solid currentColor; box-sizing: border-box; }
#olympus-turn li.in_progress .i.spin { border-radius: 50%; border: 2px solid color-mix(in srgb, var(--primary, Highlight) 30%, transparent);
  border-top-color: var(--primary, Highlight); box-sizing: border-box; animation: olympus-spin .8s linear infinite; }
#olympus-turn li.in_progress .i.dots::before { content: "…"; font-weight: 700; color: var(--primary, Highlight); }
@keyframes olympus-spin { to { transform: rotate(360deg); } }
#olympus-turn .ask { font-weight: 600; }
#olympus-turn .recap { color: color-mix(in srgb, var(--foreground, CanvasText) 75%, transparent); }
#olympus-turn .ask + .recap { margin-top: 2px; }
#olympus-turn .row { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
#olympus-turn button { padding: 3px 10px; border-radius: 6px; cursor: pointer; font: inherit; color: inherit;
  background: transparent; border: 1px solid color-mix(in srgb, currentColor 30%, transparent); }
#olympus-turn button.primary { background: var(--primary, Highlight); color: var(--primary-foreground, HighlightText); border-color: transparent; }
#olympus-turn [data-close] { float: right; border: 0; padding: 0 2px; opacity: .6; }`;
  document.head.append(style);

  // per chat: its turn items (by id, ordered by T3's ordinal) and the latest run
  const chats = new Map();
  const chat = (id) => { if (!chats.has(id)) chats.set(id, { items: new Map(), run: null, asked: false }); return chats.get(id); };
  const ordered = (c) => [...c.items.values()].sort((a, b) => (a.ordinal ?? 0) - (b.ordinal ?? 0));
  const dismissed = new Set();  // box ids closed with ×

  addEventListener("olympus:thread", (e) => {
    const { threadId: id, kind, payload } = e.detail || {};
    if (!id || !payload) return;
    const c = chat(id);
    if (kind === "item" && payload.id) c.items.set(payload.id, payload);
    else if (kind === "run") c.run = payload;
    if (id === threadId()) queue();
  });

  // a chat with nothing from the socket yet: its olympus calls and your messages, once, from the helper
  const load = async (id) => {
    const c = chat(id);
    if (c.asked) return;
    c.asked = true;
    try {
      const r = await (await fetch(HELPER + "/turn?thread=" + encodeURIComponent(id))).json();
      (r.items || []).forEach((it, i) => { if (it.id && !c.items.has(it.id)) c.items.set(it.id, { ordinal: i - 1e6, ...it }); });
      if (id === threadId()) queue();
    } catch { c.asked = false; }  // helper not running: try again next time the chat opens
  };

  // put text in T3's message box; send it unless only filling (Ctrl+click)
  const reply = (text, send) => {
    const host = document.querySelector('[data-slot="composer-host"]');
    const box = host?.querySelector('[contenteditable="true"], textarea');
    if (!box) return;
    box.focus();
    document.execCommand("selectAll");
    document.execCommand("insertText", false, text);
    if (!send) return;
    setTimeout(() => {
      const submit = host.querySelector('button[aria-label="Submit message"], button[type="submit"]');
      if (submit && !submit.disabled) submit.click();
      else box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
    }, 50);
  };

  let current = null;  // what's drawn, so nothing is rebuilt when it hasn't changed
  const draw = () => {
    const id = threadId();
    let el = document.getElementById("olympus-turn");
    const v = id ? OlympusTurn.view(ordered(chat(id)), chat(id).run) : { plan: null, box: null };
    if (id && !chat(id).items.size) load(id);
    const box = v.box && !dismissed.has(v.box.id) ? v.box : null;
    const key = JSON.stringify([id, box, box ? null : v.plan]);
    if (!box && !v.plan) { el?.remove(); current = null; return; }
    if (el && key === current) { olympusAbove(el); return; }
    current = key;
    if (!el) { el = document.createElement("div"); el.id = "olympus-turn"; }
    el.dataset.box = box ? "1" : "";
    if (box) {
      const line = box.ask ? `<div class="ask">${esc(box.ask)}</div>`
        : box.blocked ? `<div class="ask">Claude is waiting on you. Pick a reply or type your own.</div>` : "";
      el.innerHTML = (box.blocked ? "" : `<button data-close title="Dismiss">×</button>`) + line +
        `<div class="recap">${esc(box.recap)}</div>` +
        (box.actions.length ? `<div class="row">${box.actions.map((a, i) =>
          `<button data-i="${i}" class="${i ? "" : "primary"}" title="Ctrl+click to only fill the message box">${esc(a.label)}</button>`).join("")}</div>` : "");
      el.querySelector("[data-close]")?.addEventListener("click", () => { dismissed.add(box.id); draw(); });
      el.querySelectorAll("[data-i]").forEach((b) => b.addEventListener("click", (e) => {
        reply(box.actions[+b.dataset.i].message, !(e.ctrlKey || e.metaKey));
      }));
    } else {
      const icon = (s) => s.status === "completed" ? `<span class="i">✓</span>`
        : s.status === "in_progress" ? `<span class="i ${v.plan.live ? "spin" : "dots"}"></span>` : `<span class="i"></span>`;
      el.innerHTML = (v.plan.old ? `<div class="old">Plan from before your last message</div>` : "") +
        `<ol>${v.plan.steps.map((s) => `<li class="${s.status}">${icon(s)}<span>${esc(s.content)}</span></li>`).join("")}</ol>`;
    }
    olympusAbove(el);
  };

  let queued = false;
  const queue = () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; draw(); }); } };
  addEventListener("hashchange", queue);
  new MutationObserver(queue).observe(document.documentElement, { childList: true, subtree: true });

  // Ctrl+Enter in an empty message box presses the box's first button
  addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
    const host = e.target.closest?.('[data-slot="composer-host"]');
    const first = document.querySelector("#olympus-turn[data-box='1'] [data-i='0']");
    if (!host || !first || (host.querySelector('[contenteditable="true"], textarea')?.innerText || "").trim()) return;
    e.preventDefault();
    e.stopPropagation();
    first.click();
  }, true);
})();
