// "Session" section in the thread details tray (Ctrl+Shift+B), like Claude desktop's side panel:
// how full the chat's context window is, and the connectors (MCP servers) Claude has there.
// helper.py's /session reads T3's own context figure and runs claude mcp list in the chat's folder.
(() => {
  const HELPER = "http://127.0.0.1:47833";
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const style = document.createElement("style");
  style.textContent = `
#olympus-session { color: color-mix(in srgb, var(--foreground, CanvasText) 80%, transparent); }
#olympus-session .head { font-size: 11px; opacity: .65; margin: 6px 8px 4px; }
#olympus-session .bar { height: 4px; margin: 4px 8px 2px; border-radius: 2px; overflow: hidden;
  background: color-mix(in srgb, currentColor 15%, transparent); }
#olympus-session .bar > div { height: 100%; background: var(--primary, Highlight); }
#olympus-session .line { font-size: 12px; margin: 2px 8px; display: flex; align-items: center; gap: 6px; }
#olympus-session .dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }`;
  document.head.append(style);

  const threadId = () => {
    const parts = location.hash.replace(/^#\/?/, "").split(/[?#]/)[0].split("/");
    if (parts.length !== 2 || ["draft", "settings", "pull-requests", "new"].includes(parts[0])) return null;
    return decodeURIComponent(parts[1]);
  };
  const short = (n) => n >= 1e6 ? +(n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(n);

  let data = null, dataFor = null, fetchedAt = 0, loading = false;
  const load = async (thread) => {
    loading = true;
    try {
      data = await (await fetch(HELPER + "/session?thread=" + encodeURIComponent(thread))).json();
    } catch { data = { error: true }; }
    dataFor = thread; fetchedAt = Date.now(); loading = false;
    draw();
  };

  const html = () => {
    if (!data || dataFor !== threadId()) return `<div class="head">Session</div><div class="line">Loading…</div>`;
    if (data.error) return `<div class="head">Session</div><div class="line">The T3 Olympus helper isn't running.</div>`;
    const { usedTokens: used, maxTokens: max } = data.context || {};
    const ctx = used == null ? `<div class="line">No messages yet.</div>` :
      (max ? `<div class="bar"><div style="width:${Math.min(100, used / max * 100)}%"></div></div>` : "") +
      `<div class="line">${short(used)}${max ? ` of ${short(max)} tokens · ${Math.round(used / max * 100)}%` : " tokens"}</div>`;
    const list = data.connectors.length ? data.connectors.map((c) =>
      `<div class="line" title="${esc(c.status)}"><span class="dot" style="background:${c.ok ? "#3fb950" : "#f85149"}"></span>${esc(c.name)}${c.ok ? "" : ` <span style="opacity:.6">· ${esc(c.status)}</span>`}</div>`).join("")
      : `<div class="line">None</div>`;
    return `<div class="head">Context</div>${ctx}<div class="head">Connectors</div>${list}`;
  };

  let drawn = "";
  const draw = () => {
    const card = document.querySelector("[data-thread-details-card]");
    const workspace = card && card.querySelector('section[aria-label="Workspace"]');
    let mine = document.getElementById("olympus-session");
    const thread = threadId();
    if (!workspace || !thread) { if (mine) mine.remove(); return; }
    const after = document.getElementById("olympus-actions") || workspace;
    if (!mine) {
      mine = document.createElement("section");
      mine.id = "olympus-session";
      mine.setAttribute("aria-label", "Session");
      mine.className = "px-2 pt-1 pb-2.5 border-t border-border/65";
      drawn = "";
    }
    if (mine.previousElementSibling !== after) after.after(mine);
    const h = html();
    if (h !== drawn) { mine.innerHTML = h; drawn = h; }
    // refresh when the chat changes, and every 20s while the tray is open
    if (!loading && (dataFor !== thread || Date.now() - fetchedAt > 20000)) load(thread);
  };

  let queued = false;
  new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; draw(); }); }
  }).observe(document.documentElement, { subtree: true, childList: true });
  setInterval(draw, 5000);
})();
