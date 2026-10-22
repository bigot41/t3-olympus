// A Compact button in the message box: compacts the chat's conversation now, whenever you like,
// on top of Claude Code's automatic compaction. T3 already treats a "/compact" message as its
// compact command, so the button sends just that. Shown on saved chats only (a new one has nothing to compact).
(() => {
  // Lucide "fold-vertical"
  const ICON = `<svg class="lucide size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22v-6"/><path d="M12 8V2"/><path d="M4 12H2"/><path d="M10 12H8"/><path d="M16 12h-2"/><path d="M22 12h-2"/><path d="m15 19-3-3-3 3"/><path d="m15 5-3 3-3-3"/></svg>`;
  const button = () => {
    const attach = document.querySelector(`${olympus.COMPOSER} button[aria-label="Attach files"]`);
    const mine = document.getElementById("olympus-compact");
    if (!attach || !olympus.threadId()) { mine?.remove(); return; }
    if (mine) return;
    const b = document.createElement("button");
    b.id = "olympus-compact";
    b.className = attach.className;  // T3's own composer button look, in every theme
    b.type = "button";
    b.title = "Compact this conversation now";
    b.setAttribute("aria-label", "Compact conversation");
    b.innerHTML = ICON;
    b.onclick = (e) => { e.preventDefault(); olympus.fill("/compact", { send: true }); };
    attach.before(b);
  };
  olympus.onDom(button);
})();
