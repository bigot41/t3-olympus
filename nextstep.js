// Next-step card above the composer, like Claude desktop's: when Claude ends a turn with the
// wrap_up tool (wrapup_mcp.py), helper.py's /wrapup returns that call and this draws its recap,
// question and buttons. A button types its message into the composer and sends it.
(() => {
  const HELPER = "http://127.0.0.1:47833";
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const style = document.createElement("style");
  style.textContent = `
#olympus-next { position: relative; z-index: 1; /* above the composer's frosted backdrop */ margin: 0 auto 8px; padding: 10px 14px; font-size: 13px; line-height: 1.5; border-radius: 8px;
  background: var(--card, Canvas); color: var(--foreground, CanvasText);
  border: 1px dotted color-mix(in srgb, var(--primary, currentColor) 70%, transparent); }
#olympus-next .ask { margin-top: 6px; font-weight: 600; }
#olympus-next .row { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
#olympus-next button { padding: 3px 10px; border-radius: 6px; cursor: pointer; font: inherit; color: inherit;
  background: transparent; border: 1px solid color-mix(in srgb, currentColor 30%, transparent); }
#olympus-next button.primary { background: var(--primary, Highlight); color: var(--primary-foreground, HighlightText); border-color: transparent; }
#olympus-next [data-close] { float: right; border: 0; padding: 0 2px; opacity: .6; }`;
  document.head.append(style);

  const threadId = () => {
    const parts = location.hash.replace(/^#\/?/, "").split(/[?#]/)[0].split("/");
    if (parts.length !== 2 || ["draft", "settings", "pull-requests", "new"].includes(parts[0])) return null;
    return decodeURIComponent(parts[1]);
  };

  // Put text in T3's message box and send it, the way typing and pressing Enter would.
  const send = (text) => {
    const host = document.querySelector('[data-slot="composer-host"]');
    const box = host && host.querySelector('[contenteditable="true"], textarea');
    if (!box) return;
    box.focus();
    if (box.tagName === "TEXTAREA") {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(box, text);
      box.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      document.execCommand("selectAll");
      document.execCommand("insertText", false, text);
    }
    setTimeout(() => box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true })), 50);
  };

  let shown = null;  // id of the wrap_up call on screen
  const dismissed = new Set();
  const draw = (card) => {
    const host = document.querySelector('[data-slot="composer-host"]');
    let el = document.getElementById("olympus-next");
    if (!card.id || dismissed.has(card.id) || !host) { if (el) el.remove(); shown = null; return; }
    if (el && shown === card.id && el.nextElementSibling === host) return;
    if (el) el.remove();
    el = document.createElement("div");
    el.id = "olympus-next";
    el.style.width = host.offsetWidth ? host.offsetWidth + "px" : "";
    const actions = (card.ask && card.actions) || [];
    el.innerHTML = `<button data-close title="Hide">×</button><div>${esc(card.recap || "")}</div>` +
      (card.ask ? `<div class="ask">${esc(card.ask)}</div>` : "") +
      (actions.length ? `<div class="row">${actions.map((a, i) =>
        `<button data-i="${i}" class="${i ? "" : "primary"}">${esc(a.label)}</button>`).join("")}</div>` : "");
    el.querySelector("[data-close]").onclick = () => { dismissed.add(card.id); el.remove(); };
    el.querySelectorAll("[data-i]").forEach((b) => b.onclick = () => {
      const a = actions[+b.dataset.i];
      dismissed.add(card.id);
      el.remove();
      send(a.message || a.label);
    });
    host.before(el);
    shown = card.id;
  };

  const poll = async () => {
    const thread = threadId();
    if (document.hidden) return;  // check again when T3 is back in front
    if (!thread) return draw({});
    try {
      draw(await (await fetch(HELPER + "/wrapup?thread=" + encodeURIComponent(thread))).json());
    } catch { /* helper not running: no card */ }
  };
  setInterval(poll, 2000);
  window.addEventListener("hashchange", poll);
  document.addEventListener("visibilitychange", poll);
})();
