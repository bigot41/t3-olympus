// Dictation, like Claude Code's /voice: the microphone button in the composer records you, the
// words appear as you speak, and the text lands in the message box when you stop (click again or
// press Esc). It uses Claude Code's own speech-to-text service through helper.py (voice.py).
(() => {
  const { HELPER, esc } = olympus;
  const style = document.createElement("style");
  style.textContent = `
#olympus-mic.on { border-radius: 50%; color: var(--primary-foreground, HighlightText); background: var(--primary, Highlight);
  animation: olympus-pulse 1.4s ease-in-out infinite; }
@keyframes olympus-pulse { 50% { box-shadow: 0 0 0 6px color-mix(in srgb, var(--primary, Highlight) 25%, transparent); } }
#olympus-voice { order: 2; font-size: 13px; line-height: 1.45;
  color: color-mix(in srgb, var(--foreground, CanvasText) 85%, transparent); }
#olympus-voice b { color: var(--primary, Highlight); font-weight: 600; }`;
  document.head.append(style);

  const MIC = `<svg class="lucide size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19v3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><rect x="9" y="2" width="6" height="13" rx="3"/></svg>`;
  const call = async (path, body) => {
    const r = await fetch(HELPER + path, { method: "POST", body, headers: { "Content-Type": "application/octet-stream" } });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error);
    return res;
  };

  let rec = null;  // { stream, ctx, node, queue, text }
  const status = (html) => {
    const host = document.querySelector('[data-slot="composer-host"]');
    let el = document.getElementById("olympus-voice");
    if (html === null || !host) { el?.remove(); return; }
    if (!el) { el = document.createElement("div"); el.id = "olympus-voice"; }
    olympusAbove(el);
    el.innerHTML = html;
  };

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      // record straight away and hold the audio until the speech service is connected,
      // so the first words aren't lost while it connects
      const ctx = new AudioContext({ sampleRate: 16000 });
      const node = ctx.createScriptProcessor(1024, 1, 1);
      rec = { stream, ctx, node, queue: Promise.resolve(), pending: [], text: "", ready: false };
      node.onaudioprocess = (e) => {
        const f = e.inputBuffer.getChannelData(0), pcm = new Int16Array(f.length);
        for (let i = 0; i < f.length; i++) pcm[i] = Math.max(-1, Math.min(1, f[i])) * 0x7fff;
        rec.pending.push(pcm);
      };
      ctx.createMediaStreamSource(stream).connect(node);
      node.connect(ctx.destination);
      document.getElementById("olympus-mic")?.classList.add("on");
      status("<b>Listening…</b> click the microphone or press Esc to stop");
      const r = rec;
      await call("/voice/start");
      if (rec !== r) return;  // stopped while connecting
      r.ready = true;
      r.timer = setInterval(flush, 100);
    } catch (e) {
      stopAudio();
      status(`<b>Dictation didn't start:</b> ${esc(e instanceof TypeError ? "the T3 Olympus helper isn't running" : e.message)}`);
      setTimeout(() => status(null), 6000);
    }
  };
  // send the audio recorded since last time, in order
  const flush = () => {
    if (!rec || !rec.ready || !rec.pending.length) return;
    const parts = rec.pending.splice(0), all = new Int16Array(parts.reduce((n, p) => n + p.length, 0));
    let o = 0;
    for (const p of parts) { all.set(p, o); o += p.length; }
    const r = rec;
    r.queue = r.queue.then(() => call("/voice/audio", all.buffer)).then((res) => {
      r.text = res.text;
      if (rec === r) status(`<b>Listening…</b> ${esc(res.text) || "click the microphone or press Esc to stop"}`);
    }).catch((e) => { if (rec === r) { status(`<b>Dictation stopped:</b> ${esc(e.message)}`); stopAudio(); } });
  };
  const stopAudio = () => {
    if (!rec) return null;
    const r = rec;
    rec = null;
    clearInterval(r.timer);
    r.stream?.getTracks().forEach((t) => t.stop());
    r.node?.disconnect();
    r.ctx?.close();
    document.getElementById("olympus-mic")?.classList.remove("on");
    return r;
  };
  const stop = async () => {
    const r = rec;
    if (!r) return;
    flush();
    stopAudio();
    status("<b>Finishing…</b>");
    try {
      await r.queue;
      const { text } = await call("/voice/stop");
      status(null);
      if (!text) return;
      const box = document.querySelector('[data-slot="composer-host"] [contenteditable="true"]');
      if (!box) return;
      box.focus();
      const sel = getSelection();
      sel.selectAllChildren(box);
      sel.collapseToEnd();
      const before = box.innerText.trim();
      document.execCommand("insertText", false, (before ? " " : "") + text);
    } catch (e) {
      status(`<b>Dictation failed:</b> ${esc(e.message)}`);
      setTimeout(() => status(null), 6000);
    }
  };

  const button = () => {
    const attach = document.querySelector('[data-slot="composer-host"] button[aria-label="Attach files"]');
    if (!attach || document.getElementById("olympus-mic")) return;
    const b = document.createElement("button");
    b.id = "olympus-mic";
    b.className = attach.className;  // T3's own composer button look, in every theme
    b.type = "button";
    b.title = "Dictate (Claude's speech-to-text)";
    b.setAttribute("aria-label", "Dictate");
    b.innerHTML = MIC;
    if (rec) b.classList.add("on");
    b.onclick = (e) => { e.preventDefault(); rec ? stop() : start(); };
    attach.before(b);
  };
  addEventListener("keydown", (e) => { if (rec && e.key === "Escape") { e.preventDefault(); stop(); } }, true);
  let queued = false;
  new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; button(); }); }
  }).observe(document.documentElement, { subtree: true, childList: true });
})();
