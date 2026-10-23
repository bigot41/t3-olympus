// Hover card over a profile name in T3's sidebar: what the profile works on, its main
// work, folders and latest chats. Each hover asks helper.py for that profile's
// local card, rebuilt then (cards_build.py); hovering never requests an AI summary.
(() => {
  const { esc } = olympus;
  const seen = {};  // last card per profile, shown while the fresh one loads
  const loaded = {};  // whether this hover's fresh card has arrived
  const refreshing = new Set();
  const errors = {};
  const versions = {};
  let hovered = null;
  let currentRow = null;
  let focusSource = null;
  const list = (items) => "<ul>" + (items || []).map((i) => `<li>${esc(i)}</li>`).join("") + "</ul>";

  const style = document.createElement("style");
  style.textContent = `
.olympus-card { position: fixed; z-index: 100; width: 300px; padding: 12px 14px; pointer-events: none;
  background: var(--popover, Canvas); color: var(--foreground, CanvasText); font-size: 12px; line-height: 1.45;
  border: 1px dotted color-mix(in srgb, var(--primary, currentColor) 70%, transparent); border-radius: 8px;
  box-shadow: 0 8px 24px rgb(0 0 0 / 35%);
  /* Only opacity and transform move, so the graphics card animates it without redrawing.
     Hidden until .on, then it springs in from the sidebar, slightly past its spot and back. */
  opacity: 0; transform: translate3d(-10px, 0, 0) scale(.97); transform-origin: left center;
  will-change: transform, opacity;
  transition: opacity .18s ease-in, transform .18s ease-in; }
.olympus-card.on { opacity: 1; pointer-events: auto; transform: translate3d(0, 0, 0) scale(1);
  transition: opacity .35s ease-out, transform .6s cubic-bezier(.34, 1.45, .55, 1); }
/* the glow is its own layer that only fades, once, as the card arrives */
.olympus-card::before { content: ""; position: absolute; inset: -1px; border-radius: inherit; opacity: 0; pointer-events: none;
  box-shadow: 0 0 26px 1px color-mix(in srgb, var(--primary, currentColor) 40%, transparent); }
.olympus-card.enter::before { animation: olympus-glow 1.3s ease-out; }
@keyframes olympus-glow { 30% { opacity: 1; } }
/* sections settle in top to bottom, on entrance only */
.olympus-card.enter > * { animation: olympus-rise .45s cubic-bezier(.2, .8, .3, 1) both; }
.olympus-card.enter > :nth-child(n+3) { animation-delay: .06s; }
.olympus-card.enter > :nth-child(n+5) { animation-delay: .12s; }
.olympus-card.enter > :nth-child(n+7) { animation-delay: .18s; }
@keyframes olympus-rise { from { opacity: 0; transform: translate3d(0, 4px, 0); } }
.olympus-card b { font-size: 14px; }
.olympus-card i { float: right; opacity: .6; font-size: 11px; }
.olympus-card p { margin: 4px 0 6px; opacity: .85; }
.olympus-card h6 { margin: 8px 0 2px; font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--primary, currentColor); }
.olympus-card ul { margin: 0; padding: 0; list-style: none; }
.olympus-card button { margin-top: 10px; cursor: pointer; }
.olympus-card button:focus-visible { outline: 2px solid var(--primary, currentColor); outline-offset: 3px; }
.olympus-card small { display: block; margin-top: 4px; }
.olympus-card li { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.olympus-card li::before { content: "· "; opacity: .6; }`;
  document.head.append(style);

  const card = document.createElement("div");
  card.className = "olympus-card";
  const content = document.createElement("div");
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.textContent = "Refresh AI summary";
  const caption = document.createElement("small");
  caption.textContent = "Uses Haiku";
  const status = document.createElement("small");
  status.setAttribute("role", "status");
  card.append(content, refresh, caption, status);
  const show = (name, c, loading) => {
    content.innerHTML = `<b>${esc(name)}</b>${loading ? "<i>reading...</i>" : ""}` + (c ?
      `<p>${esc(c.description || "")}</p>` + (c.does ? `<h6>AI summary</h6><p>${esc(c.does)}</p>` : "") +
      (c.topics?.length ? `<h6>Main work</h6>${list(c.topics)}` : "") +
      `<h6>Folders</h6>${list(c.projects)}<h6>Latest of ${c.chats} chats</h6>${list(c.recent)}` :
      (loading ? "" : "<p>The T3 Olympus helper isn't running. Open T3 from the T3 Olympus shortcut.</p>"));
    refresh.disabled = refreshing.has(name);
    status.textContent = refreshing.has(name) ? "Refreshing AI summary..." : errors[name] || "";
  };

  refresh.addEventListener("click", async () => {
    const name = hovered;
    if (!name || refreshing.has(name)) return;
    refreshing.add(name);
    versions[name] = (versions[name] || 0) + 1;
    delete errors[name];
    show(name, seen[name], false);
    try {
      const response = await fetch("http://127.0.0.1:47833/card/refresh", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok || !result.card || typeof result.card.does !== "string") throw new Error();
      seen[name] = result.card;
    } catch {
      errors[name] = "Couldn't refresh AI summary. Try again later.";
    } finally {
      refreshing.delete(name);
      if (hovered === name && card.isConnected) { show(name, seen[name], false); place(currentRow); }
    }
  });

  // The card waits until you have rested on a profile for 1.75 seconds, then fades in.
  const DELAY = 1750;
  let timer = null;
  let leaveTimer = null;
  let entering = false;
  let pending = null;  // a fresh card that arrived mid-entrance, swapped in once it settles
  const place = (row) => {
    const r = row.getBoundingClientRect();
    card.style.left = r.right + 12 + "px";
    card.style.top = Math.max(8, Math.min(r.top - 8, innerHeight - card.offsetHeight - 8)) + "px";
  };
  const hide = () => {
    clearTimeout(timer);
    clearTimeout(leaveTimer);
    hovered = null;
    pending = null;
    card.classList.remove("on", "enter");
    card.inert = true;
    clearTimeout(card.gone);
    card.gone = setTimeout(() => { if (!hovered) card.remove(); }, 250);
  };

  const follow = (e) => {
    clearTimeout(leaveTimer);
    if (card.contains(e.target)) return;
    const row = e.target.closest && e.target.closest('[class*="group/project-header"]');
    const name = row && row.querySelector(".truncate")?.textContent.trim();
    if (!name) {
      if (!card.isConnected) clearTimeout(timer);
      if (hovered) leaveTimer = setTimeout(() => {
        if (!card.contains(document.activeElement)) hide();
      }, 250);
      return;
    }
    if (e.type === "focusin") focusSource = e.target;
    if (name === hovered) return;
    hide();
    hovered = name;
    currentRow = row;
    timer = setTimeout(() => {
      clearTimeout(card.gone);
      card.classList.remove("on", "enter");
      show(name, seen[name], !loaded[name]);
      document.body.append(card);
      card.inert = false;
      place(row);
      entering = true;
      requestAnimationFrame(() => requestAnimationFrame(() => card.classList.add("on", "enter")));
      setTimeout(() => {
        entering = false;
        if (hovered !== name) return;
        card.classList.remove("enter");
        if (pending) { pending(); pending = null; }
      }, 900);
      loaded[name] = false;
      const version = versions[name] || 0;
      fetch("http://127.0.0.1:47833/card?name=" + encodeURIComponent(name)).then((res) => res.json())
      .then((c) => { if (c && c.chats !== undefined && version === (versions[name] || 0)) seen[name] = c; })
      .catch(() => {})
      .finally(() => {
        loaded[name] = true;
        if (hovered !== name || !card.isConnected) return;
        // swap the contents in place, without replaying the entrance
        const swap = () => { show(name, seen[name], false); place(row); };
        if (entering) pending = swap; else swap();
      });
    }, e.type === "focusin" ? 0 : DELAY);
  };
  document.addEventListener("mouseover", follow);
  document.addEventListener("focusin", follow);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && hovered) {
      if (card.contains(document.activeElement)) focusSource?.focus();
      hide();
    } else if (e.key === "Tab" && !e.shiftKey && card.isConnected &&
               e.target.closest?.('[class*="group/project-header"]') === currentRow && !refresh.disabled) {
      e.preventDefault();
      refresh.focus();
    }
  });
  card.addEventListener("focusout", (e) => {
    if (!card.contains(e.relatedTarget)) leaveTimer = setTimeout(hide, 250);
  });
})();
