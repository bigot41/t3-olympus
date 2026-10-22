// A small × on chat chips in the message box (the chip a chat becomes when you drop it there):
// hover a chip and click × to remove it, along with the space after it. Backspace and Delete
// already remove chips, through T3's own editor.
(() => {
  const CHIP = ".node-composer-context-reference";
  const style = document.createElement("style");
  style.textContent = `
#olympus-chip-x { position: fixed; z-index: 50; width: 16px; height: 16px; padding: 0; border: 0; border-radius: 50%;
  display: none; align-items: center; justify-content: center; cursor: pointer; font-size: 12px; line-height: 1;
  color: var(--background, Canvas); background: var(--foreground, CanvasText); box-shadow: 0 1px 4px rgb(0 0 0 / .3); }
#olympus-chip-x.on { display: inline-flex; }`;
  document.head.append(style);

  const x = Object.assign(document.createElement("button"), { id: "olympus-chip-x", type: "button", textContent: "×",
                                                             title: "Remove" });
  x.setAttribute("aria-label", "Remove from message");
  let chip = null, hideTimer;
  const hide = () => { x.classList.remove("on"); chip = null; };

  document.addEventListener("mouseover", (e) => {
    const c = e.target.closest?.(CHIP);
    if (e.target === x) { clearTimeout(hideTimer); return; }
    if (!c || !c.closest(".ProseMirror")?.editor) { clearTimeout(hideTimer); hideTimer = setTimeout(hide, 150); return; }
    clearTimeout(hideTimer);
    chip = c;
    const r = c.getBoundingClientRect();
    x.style.left = r.right - 8 + "px";
    x.style.top = r.top - 6 + "px";
    if (!x.isConnected) document.body.append(x);
    x.classList.add("on");
  }, true);

  // mousedown, so the editor keeps focus and its selection
  x.addEventListener("mousedown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const editor = chip?.closest(".ProseMirror")?.editor;
    if (!editor) return hide();
    const { state, view } = editor;
    let pos = view.posAtDOM(chip, 0);
    if (state.doc.nodeAt(pos)?.type.name !== "composer-context-reference") pos -= 1;
    const node = state.doc.nodeAt(pos);
    if (node?.type.name === "composer-context-reference") {
      let end = pos + node.nodeSize;
      if (state.doc.textBetween(end, Math.min(end + 1, state.doc.content.size)) === " ") end += 1;
      view.dispatch(state.tr.delete(pos, end));
      view.focus();
    }
    hide();
  });
})();
