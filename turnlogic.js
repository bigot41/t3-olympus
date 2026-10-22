// What the task list and the next-step box show for a thread, worked out from its turn items.
// Same rules as wrapup_mcp.py (tests/turn_cases.json holds the shared cases). Pure: no state, no DOM.
(function () {
  const MAX_STEPS = 12, MAX_STEP_CHARS = 160, MAX_RECAP = 1200;
  const MAX_BUTTONS = 2, MAX_LABEL_CHARS = 24, MAX_LABEL_WORDS = 4, MAX_MESSAGE = 300;
  const STATUSES = ["pending", "in_progress", "completed"];
  const SCOPES = ["first_task", "continuation", "new_task"];
  const HIDDEN = /[\u200B-\u200F\u2028-\u202E\u2060-\u2064\uFEFF]/;
  const EDGE = /^[^\S\uFEFF]+|[^\S\uFEFF]+$/g; // like Python's strip: U+FEFF stays, so it is caught as invisible

  const text = (v) => (typeof v === "string" ? v.replace(EDGE, "") : "");
  const cut = (s, n) => { const a = Array.from(s); return a.length > n ? a.slice(0, n).join("") : s; };
  const len = (s) => Array.from(s).length;
  const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const truthy = (v) => Array.isArray(v) ? v.length > 0 : isObj(v) ? Object.keys(v).length > 0 : !!v;
  const isTrue = (v) => v === true || v === 1 || v === "true";

  function button(raw) {
    if (!isObj(raw)) return null;
    const label = text(raw.label);
    const message = text(raw.message) || label;
    if (!label || len(label) > MAX_LABEL_CHARS || label.split(/\s+/).filter(Boolean).length > MAX_LABEL_WORDS) return null;
    if ([label, message].some((t) => "/!".includes(t[0]) || HIDDEN.test(t))) return null;
    return { label, message: cut(message, MAX_MESSAGE) };
  }

  function normalizeWrapUp(input) {
    const args = isObj(input) ? input : {};
    const recap = cut(text(args.recap) || text(args.outcome) || text(args.next_recap), MAX_RECAP);
    const ask = text(args.ask) || text(args.next_ask) || text(args.next_brief);
    let raw = args.actions == null ? args.next_actions : args.actions;
    raw = Array.isArray(raw) ? raw : [];
    const blocked = isTrue(args.blocked) || truthy(args.needs_user);
    return { recap: recap || null, ask: ask || null, blocked, actions: raw.map(button).filter(Boolean).slice(0, MAX_BUTTONS) };
  }

  const showsBox = (card) => !!(card.blocked || (card.ask && card.actions.length));

  function parseSteps(items) {
    const steps = [];
    for (const it of Array.isArray(items) ? items : []) {
      if (isObj(it) && text(it.content) && STATUSES.includes(it.status)) steps.push({ content: cut(text(it.content), MAX_STEP_CHARS), status: it.status });
    }
    return steps.slice(0, MAX_STEPS);
  }

  // Returns the new steps, or the same steps object when the call is refused.
  function applyPlan(steps, input) {
    const args = isObj(input) ? input : {};
    const hasUpdate = ["advance", "done", "start"].some((k) => {
      const v = args[k];
      return !(v == null || v === false || v === 0 || v === "false" || (Array.isArray(v) && !v.length));
    });
    if (args.items != null) {
      if (!SCOPES.includes(args.scope)) return steps;
      return parseSteps(args.items).length ? parseSteps(args.items) : steps;
    }
    if (!hasUpdate || !steps || !steps.length) return steps;
    const n = steps.length, start = args.start;
    let done = truthy(args.done) ? args.done : [];
    done = Array.isArray(done) ? done : [done];
    const nums = done.concat(start == null ? [] : [start]);
    if (nums.some((x) => !Number.isInteger(x) || x < 1 || x > n)) return steps;
    const out = steps.map((s) => ({ ...s }));
    for (const x of done) out[x - 1].status = "completed";
    if (start != null) out[start - 1].status = "in_progress";
    if (isTrue(args.advance)) {
      const cur = out.findIndex((s) => s.status === "in_progress");
      if (cur >= 0) out[cur].status = "completed";
      let nxt = cur >= 0 ? out.findIndex((s, i) => i > cur && s.status === "pending") : -1;
      if (nxt < 0) nxt = out.findIndex((s) => s.status === "pending");
      if (nxt >= 0) out[nxt].status = "in_progress";
    }
    return out;
  }

  const FAILED = ["failed", "error"];
  const LIVE = ["running", "waiting"];

  function view(items, run) {
    let steps = null, lastPlan = -1, lastUser = -1, wrapAt = -1, wrapCard = null, wrapId = null;
    (Array.isArray(items) ? items : []).forEach((it, i) => {
      if (!it) return;
      if (it.type === "user_message") { lastUser = i; return; }
      if (it.type !== "dynamic_tool" || FAILED.includes(it.status) || typeof it.toolName !== "string") return;
      if (it.toolName.endsWith("__update_plan")) {
        const next = applyPlan(steps, it.input);
        if (next !== steps) { steps = next; lastPlan = i; }
      } else if (it.toolName.endsWith("__wrap_up")) {
        const card = normalizeWrapUp(it.input);
        if (!card.recap) return; // the server refuses a wrap_up without a recap
        if (steps) steps = steps.map((s) => ({ ...s, status: "completed" }));
        wrapAt = i; wrapCard = card; wrapId = it.id;
      }
    });
    const live = !!run && LIVE.includes(run.status);
    const box = !live && wrapCard && wrapAt > lastUser && showsBox(wrapCard)
      ? { id: wrapId, recap: wrapCard.recap, ask: wrapCard.ask, blocked: wrapCard.blocked, actions: wrapCard.actions } : null;
    let planView = null;
    if (steps) {
      const old = lastPlan < lastUser;
      const unfinished = steps.some((s) => s.status !== "completed");
      if (live ? (!old || unfinished) : (!box && unfinished)) planView = { steps, old, live };
    }
    return { plan: planView, box };
  }

  const api = { normalizeWrapUp, showsBox, applyPlan, view };
  globalThis.OlympusTurn = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
