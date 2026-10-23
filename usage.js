// Antigravity usage presentation for Olympus. Google can report shared third-party
// limits without reporting any Gemini quota; keep a visible display bar in that case.
(() => {
  const HIDDEN = "data-olympus-shared-quota";
  const FALLBACK = "data-olympus-antigravity-fallback";
  const CARD = "md:grid-cols-[11rem_minmax(0,1fr)]";
  const GRIDS = [
    "grid-cols-[minmax(0,9rem)_minmax(3rem,1fr)_auto]",
    "grid-cols-[11rem_minmax(0,1fr)_7rem]",
  ];
  const SHARED = /^Claude\s*&\s*GPT\s*\(shared\)/i;
  const GEMINI = /^Gemini(?=\s*(?:[\u00b7\u2022]|$))/;
  const style = document.createElement("style");
  style.id = "olympus-usage-style";
  style.textContent = `
    [${HIDDEN}] { display: none !important; }
    [${FALLBACK}] { display: grid; grid-column: 1 / -1; grid-template-columns: minmax(9rem, 11rem) minmax(0, 1fr);
      align-items: center; gap: 12px 24px; padding: 16px; border: 1px solid var(--border, #493d29); border-radius: 8px; }
    [${FALLBACK}] .olympus-usage-name { font-size: 14px; font-weight: 500; }
    [${FALLBACK}] .olympus-usage-value { margin-top: 4px; font-size: 30px; font-weight: 600; line-height: 1.2; }
    [${FALLBACK}] .olympus-usage-note { margin-top: 4px; font-size: 11px; color: var(--muted-foreground, #a3947e); }
    [${FALLBACK}] .olympus-usage-track { height: 28px; border-radius: 6px; opacity: 0.55;
      background: repeating-linear-gradient(135deg, transparent 0 6px, color-mix(in srgb, var(--background, #000) 25%, transparent) 6px 12px),
        color-mix(in srgb, var(--primary, #8c7bd1) 45%, var(--muted, #292326)); }
    [${FALLBACK}][data-compact] { padding: 8px 0; border: 0; grid-template-columns: minmax(0, 9rem) minmax(3rem, 1fr); gap: 12px; }
    [${FALLBACK}][data-compact] .olympus-usage-value { font-size: 18px; }
    [${FALLBACK}][data-compact] .olympus-usage-track { height: 12px; }
    @media (max-width: 500px) { [${FALLBACK}] { grid-template-columns: 1fr; } }
  `;
  document.head.append(style);

  const fallback = (host, show, compact = false) => {
    let bar = Array.from(host.children).find((child) => child.hasAttribute(FALLBACK));
    if (!show) { bar?.remove(); return; }
    if (bar) { bar.toggleAttribute("data-compact", compact); return; }
    bar = document.createElement("div");
    bar.setAttribute(FALLBACK, "");
    bar.toggleAttribute("data-compact", compact);
    bar.title = "Google does not report a Gemini quota here. This full bar is a display placeholder, not an unlimited allowance.";
    bar.innerHTML = `<div><div class="olympus-usage-name">Antigravity</div>
      <div class="olympus-usage-value">100%</div><div class="olympus-usage-note">Usage not reported</div></div>
      <div class="olympus-usage-track" role="img" aria-label="Antigravity: usage not reported; full display bar"></div>`;
    host.append(bar);
  };

  const updateRow = (label, cells) => {
    if (!label) return;
    const text = label.textContent.trim();
    cells.forEach((cell) => cell.toggleAttribute(HIDDEN, SHARED.test(text)));
    if (!GEMINI.test(text)) return;
    const walker = document.createTreeWalker(label, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const renamed = node.nodeValue.replace(/^\s*Gemini(?=\s*(?:[\u00b7\u2022]|$))/, (match) =>
        match.replace("Gemini", "Antigravity"));
      if (renamed !== node.nodeValue) node.nodeValue = renamed;
    }
  };

  const tick = () => {
    for (const grid of document.querySelectorAll("div.grid")) {
      if (grid.hasAttribute(FALLBACK)) continue;
      if (grid.classList.contains(CARD)) {
        updateRow(grid.firstElementChild?.firstElementChild, [grid]);
      } else if (GRIDS.some((name) => grid.classList.contains(name))) {
        const cells = Array.from(grid.children).filter((cell) => !cell.hasAttribute(FALLBACK));
        if (cells.length % 3) continue;
        for (let i = 0; i < cells.length; i += 3) {
          const row = cells.slice(i, i + 3);
          updateRow(row[0].querySelector("span.truncate"), row);
          for (const cell of row) {
            const bars = [...(cell.hasAttribute("aria-label") ? [cell] : []), ...cell.querySelectorAll("[aria-label]")];
            for (const bar of bars) {
              const label = bar.getAttribute("aria-label");
              const renamed = label.replace(/^Gemini(?=\s*(?:[\u00b7\u2022]|:|$))/, "Antigravity");
              if (renamed !== label) bar.setAttribute("aria-label", renamed);
            }
          }
        }
        const sharedOnly = cells.length > 0 && cells.every((cell) => cell.hasAttribute(HIDDEN));
        fallback(grid, sharedOnly, true);
      }
    }
    // The full Usage page has one section per provider. Never leave Antigravity blank.
    for (const heading of document.querySelectorAll("section > h2")) {
      if (heading.textContent.trim() !== "Antigravity") continue;
      const section = heading.parentElement;
      const reported = Array.from(section.querySelectorAll("div.grid")).some((card) =>
        card.classList.contains(CARD) && !card.hasAttribute(HIDDEN));
      fallback(section, !reported);
    }
  };
  olympus.onDom(tick);
  tick();
})();
