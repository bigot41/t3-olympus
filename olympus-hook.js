// Wraps T3's WebSocket (path /ws) and re-fires thread events on window as "olympus:thread"
// with detail {threadId, kind: "item" | "run" | "snapshot", payload}. Inlined into index.html
// by patch.py before T3's own script, so it runs first.
(() => {
  const parseFrame = (data, subs) => {
    try {
      const text = typeof data === "string" ? data : new TextDecoder().decode(data);
      const parsed = JSON.parse(text);
      const out = [];
      for (const m of Array.isArray(parsed) ? parsed : [parsed]) {
        const threadId = m && m._tag === "Chunk" && subs.get(String(m.requestId));
        if (!threadId) continue;
        for (const v of m.values || []) {
          if (v.kind === "snapshot") out.push({ threadId, kind: "snapshot", payload: v.projection });
          else if (v.kind === "event" && v.event) {
            const e = v.event;
            if (e.type === "turn-item.updated") out.push({ threadId, kind: "item", payload: e.payload });
            else if (e.type === "run.updated") out.push({ threadId, kind: "run", payload: e.payload ?? e });
          }
        }
      }
      return out;
    } catch { return []; }
  };

  if (typeof module !== "undefined") module.exports = { parseFrame };
  if (typeof window === "undefined" || !window.WebSocket) return;

  const Native = window.WebSocket;
  const subs = new Map();  // request id -> thread id, from orchestration.subscribeThread
  const noteSend = (data) => {
    try {
      const text = typeof data === "string" ? data : new TextDecoder().decode(data);
      const parsed = JSON.parse(text);
      for (const m of Array.isArray(parsed) ? parsed : [parsed])
        if (m && m._tag === "Request" && m.tag === "orchestration.subscribeThread") subs.set(String(m.id), m.payload.threadId);
    } catch { /* not ours to handle */ }
  };

  class Hooked extends Native {
    constructor(url, protocols) {
      super(url, protocols);
      try {
        if (!new URL(url, location.href).pathname.endsWith("/ws")) return;
        const send = this.send.bind(this);
        this.send = (data) => {
          noteSend(data);
          // the socket T3 sends its orchestration commands on, for temporary.js's delete
          if (typeof data === "string" && data.includes('"orchestration.')) window.olympusT3Socket = this;
          return send(data);
        };
        this.addEventListener("message", (e) => {
          for (const detail of parseFrame(e.data, subs)) {
            try { window.dispatchEvent(new CustomEvent("olympus:thread", { detail })); } catch { /* keep T3 running */ }
          }
        });
      } catch { /* keep T3 running */ }
    }
  }
  window.WebSocket = Hooked;
})();
