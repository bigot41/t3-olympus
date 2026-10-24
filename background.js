(() => {
  const send = (socket, command, timeout = 10000) => new Promise((resolve, reject) => {
    if (!socket || socket.readyState !== 1) { reject(new Error("T3 is not connected. Try again.")); return; }
    const id = 2e9 + Math.floor(Math.random() * 1e8);
    let timer;
    const cleanup = () => {
      clearTimeout(timer);
      socket.removeEventListener("message", reply);
      socket.removeEventListener("close", closed);
    };
    const closed = () => { cleanup(); reject(new Error("T3 disconnected. Check the agents before retrying.")); };
    const reply = (event) => {
      let messages;
      try {
        const parsed = JSON.parse(typeof event.data === "string" ? event.data : new TextDecoder().decode(event.data));
        messages = Array.isArray(parsed) ? parsed : [parsed];
      } catch { return; }
      for (const message of messages) {
        if (!message || message._tag !== "Exit" || String(message.requestId) !== String(id)) continue;
        cleanup();
        if (message.exit?._tag === "Success") resolve();
        else reject(new Error("Couldn't background this agent. It may have finished; refresh and try again."));
      }
    };
    socket.addEventListener("message", reply);
    socket.addEventListener("close", closed);
    timer = setTimeout(() => {
      cleanup();
      reject(new Error("T3 hasn't confirmed the background request. Check the agents before retrying."));
    }, timeout);
    try {
      socket.send(JSON.stringify({ _tag: "Request", id, tag: "orchestration.dispatchCommand", headers: [], payload: command }));
    } catch (error) { cleanup(); reject(error); }
  });
  const background = async (thread, tasks, socket) => {
    await Promise.all(tasks.map((task) => send(socket, {
      type: "delegated_task.wake-policy", commandId: crypto.randomUUID(),
      parentThreadId: thread, taskId: task.id, completionWake: "always",
    })));
  };
  if (typeof module !== "undefined") module.exports = { send, background };
  if (typeof window === "undefined") return;

  const style = document.createElement("style");
  style.textContent = `
#olympus-background { order: 2; display: flex; justify-content: flex-end; }
#olympus-background button { display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  padding: 4px 9px; border-radius: 6px; font: inherit; font-size: 12px; color: var(--foreground, CanvasText);
  background: var(--muted, Canvas); border: 1px solid var(--border, GrayText); }
#olympus-background button:hover { background: var(--accent, ButtonFace); }
#olympus-background button:focus-visible { outline: 2px solid var(--ring, Highlight); outline-offset: 2px; }
#olympus-background button:disabled { opacity: .6; cursor: wait; }`;
  document.head.append(style);
  let current = null, tasks = [], loading = false, busy = false;
  const draw = () => {
    let row = document.getElementById("olympus-background");
    if (olympus.threadId() !== current || !tasks.length) { row?.remove(); return; }
    if (!row) {
      row = document.createElement("div");
      row.id = "olympus-background";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "↗ Continue in background";
      button.title = "Let delegated agents keep working and ask the main agent to finish its reply. Nothing is stopped.";
      button.addEventListener("click", async () => {
        if (busy) return;
        const thread = current, pending = tasks.slice();
        busy = true;
        draw();
        try {
          await background(thread, pending, window.olympusT3Socket);
          if (current === thread) tasks = [];
          olympus.toast("Agents are continuing in the background. The main agent can now wrap up its reply.");
        } catch (error) { olympus.toast(olympus.esc(error.message)); }
        finally { busy = false; draw(); load(); }
      });
      row.append(button);
    }
    row.querySelector("button").disabled = busy;
    olympusAbove(row);
  };
  const load = async () => {
    const thread = olympus.threadId();
    if (thread !== current) { current = thread; tasks = []; draw(); }
    if (!thread || loading || !document.querySelector(olympus.COMPOSER)) return;
    if (!document.querySelector(`${olympus.COMPOSER} button[aria-label="Stop generation"]`)) {
      tasks = [];
      draw();
      return;
    }
    loading = true;
    try {
      const response = await fetch(olympus.HELPER + "/background?thread=" + encodeURIComponent(thread));
      if (!response.ok) throw new Error("Background status unavailable");
      const data = await response.json();
      if (current === thread && olympus.threadId() === thread) tasks = data.tasks || [];
    } catch { if (current === thread) tasks = []; }
    finally { loading = false; draw(); }
  };
  olympus.onDom(() => { if (olympus.threadId() !== current) load(); else draw(); });
  setInterval(load, 2000);
  load();
})();
