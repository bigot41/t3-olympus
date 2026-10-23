// Desktop pets (pets.pyw): tell the helper which chat you're looking at, so a pet's "done" badge
// clears once you've seen it, and open the chat a pet was clicked for. The helper holds each
// request open for up to 2 s and answers as soon as a pet is clicked, so the jump is immediate.
(() => {
  if (window !== window.top) return;  // a split-view pane is T3 in a frame: only the main window reports
  const open = (thread) => {
    if (olympus.threadId() === thread) return true;
    const row = document.querySelector(`[data-testid="thread-row-${CSS.escape(thread)}"]`);
    if (row) { row.click(); return true; }
    // the row may be hidden in a folded project: go by address, with the environment from the
    // open chat or any sidebar row that carries it ("env:thread")
    const here = location.hash.replace(/^#\/?/, "").split("/");
    const other = [...document.querySelectorAll("li[data-thread-item]")].map((r) => r.dataset.threadItem)
      .find((k) => k.includes(":"));
    const env = olympus.threadId() ? here[0] : other ? other.split(":")[0] : "";
    if (!env) return false;
    location.hash = `#/${env}/${encodeURIComponent(thread)}`;
    return true;
  };
  // a profile with no chats yet: a new chat in it, through T3's project chooser
  const fresh = (profile) => {
    if (!olympus.pickProject || !document.querySelector('button[aria-label="New thread"]')) return false;
    olympus.pickProject(profile);
    return true;
  };
  // T3 may still be drawing its sidebar just after it opens, so keep trying for a few seconds
  const go = async ({ thread, profile }) => {
    for (const end = Date.now() + 8000; Date.now() < end;) {
      if (thread ? open(thread) : fresh(profile)) return;
      await new Promise((r) => setTimeout(r, 150));
    }
    if (thread && profile) fresh(profile);
  };
  const loop = async () => {
    for (;;) {
      try {
        const q = `thread=${encodeURIComponent(olympus.threadId() || "")}&focus=${document.hasFocus() ? 1 : 0}`;
        const res = await (await fetch(`${olympus.HELPER}/pets/poll?${q}`)).json();
        if (res.open || res.profile) go({ thread: res.open, profile: res.profile });
      } catch {
        await new Promise((r) => setTimeout(r, 3000));  // helper not running yet
      }
    }
  };
  loop();

  // Ctrl+Alt+P turns the desktop pets off or on; the helper remembers it until you press it again
  addEventListener("keydown", async (e) => {
    if (!e.ctrlKey || !e.altKey || e.shiftKey || e.code !== "KeyP") return;
    e.preventDefault();
    try {
      const { on } = await olympus.post("/pets/toggle", {});
      olympus.toast(on ? "Desktop pets on." : "Desktop pets off. Press Ctrl+Alt+P to bring them back.");
    } catch (err) {
      olympus.toast(err instanceof TypeError ? "The T3 Olympus helper isn't running." : olympus.esc(err.message));
    }
  }, true);
})();
