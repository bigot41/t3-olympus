// Mark up: open the file the files pane is showing (a render, or a DXF the helper drew)
// as a page in the browser pane, so its existing pen can mark it. The file is not changed.
(() => {
  if (window !== window.top) return;
  const EXTS = /\.(png|jpe?g|webp|gif|avif|svg|ico|dxf)$/i;

  const style = document.createElement("style");
  style.textContent = `#olympus-picture { margin-left: 8px; padding: 2px 8px; border-radius: 6px; border: 1px solid color-mix(in srgb, currentColor 25%, transparent);
    background: none; color: inherit; font: inherit; font-size: 12px; cursor: pointer; }
    #olympus-picture:hover { background: color-mix(in srgb, currentColor 10%, transparent); }
    #olympus-picture:disabled { opacity: .5; cursor: default; }`;
  document.head.append(style);

  const filePath = () => {
    const nodes = [...document.querySelectorAll("[data-file-crumb]")];
    const current = document.querySelector("[data-current-file-crumb]");
    if (current && !nodes.includes(current)) nodes.push(current);
    const texts = nodes.map((c) => c.textContent.trim()).filter(Boolean);
    const project = document.querySelector("[data-slot=workspace-breadcrumb-text]")?.textContent?.trim();
    if (project && texts[0] === project) texts.shift();
    return texts.join("/");
  };

  const frames = (data) => {
    const parsed = JSON.parse(typeof data === "string" ? data : new TextDecoder().decode(data));
    return Array.isArray(parsed) ? parsed : [parsed];
  };

  const waitExit = (sock, id) => new Promise((resolve, reject) => {
    const timer = setTimeout(() => { sock.removeEventListener("message", on); reject(new Error("The browser pane didn't answer.")); }, 8000);
    const on = (e) => {
      let list;
      try { list = frames(e.data); } catch { return; }
      for (const m of list) {
        if (!m || String(m.requestId) !== String(id) || m._tag !== "Exit") continue;
        clearTimeout(timer);
        sock.removeEventListener("message", on);
        if (m.exit && m.exit._tag === "Failure") reject(new Error("The browser pane refused this page."));
        else resolve();
      }
    };
    sock.addEventListener("message", on);
  });

  // The address bar is React state. Setting the DOM value is not enough; Enter reads that state.
  const typeUrl = (url) => new Promise((resolve) => {
    const input = document.querySelector("[data-preview-url-input]");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, url);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    requestAnimationFrame(() => requestAnimationFrame(() => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true }));
      resolve();
    }));
  });

  // Ctrl+Shift+J is preview.toggle: it shows the tab preview.open just created.
  // A control labelled Browser is the add-surface action and would open a blank tab instead.
  const showBrowser = () => {
    if (document.querySelector("[data-preview-url-input]")) return;
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "j", code: "KeyJ", ctrlKey: true, shiftKey: true, bubbles: true, cancelable: true }));
  };

  const open = async (url) => {
    if (document.querySelector("[data-preview-url-input]")) return typeUrl(url);
    const sock = window.olympusT3Socket;
    if (!sock || sock.readyState !== 1) throw new Error("Not connected to T3 yet.");
    const id = 2e9 + Math.floor(Math.random() * 1e8);
    const pending = waitExit(sock, id);
    sock.send(JSON.stringify({ _tag: "Request", id, tag: "preview.open", headers: [],
      payload: { threadId: olympus.threadId(), url } }));
    await pending;
    showBrowser();
    await new Promise((r) => requestAnimationFrame(r));
    if (!document.querySelector("[data-preview-url-input]"))
      throw new Error("Opened. If you still see the file, press Ctrl+Shift+J.");
  };

  const mark = async (button, path) => {
    button.disabled = true;
    const title = "Open this in the browser pane and mark it up";
    try {
      const thread = olympus.threadId();
      if (!thread) throw new Error("Open a chat in this project first.");
      const { url } = await olympus.post("/picture", { thread, path });
      await open(url);
      button.title = title;
    } catch (e) {
      button.title = e instanceof TypeError ? "The helper isn't running." : (e.message || "Couldn't open this.");
    } finally {
      button.disabled = false;
    }
  };

  olympus.onDom(() => {
    const path = filePath();
    const host = document.querySelector("[data-surface-subheader]");
    const existing = document.getElementById("olympus-picture");
    if (!host || !EXTS.test(path)) {
      existing?.remove();
      return;
    }
    if (existing && existing.dataset.path === path && existing.parentElement === host) return;
    existing?.remove();
    const button = document.createElement("button");
    button.id = "olympus-picture";
    button.type = "button";
    button.dataset.path = path;
    button.textContent = "Mark up";
    button.title = "Open this in the browser pane and mark it up";
    button.addEventListener("click", () => mark(button, button.dataset.path));
    host.append(button);
  });
})();
