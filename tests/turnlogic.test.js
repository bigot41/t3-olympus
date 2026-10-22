// Tests for turnlogic.js (shared cases in turn_cases.json).
const test = require("node:test");
const assert = require("node:assert");
const T = require("../turnlogic.js");
const CASES = require("./turn_cases.json");

for (const c of CASES.wrap_up) {
  test("wrap_up: " + c.name, () => {
    const card = T.normalizeWrapUp(c.input);
    delete card.advice;
    assert.deepStrictEqual(card, c.card);
    assert.strictEqual(T.showsBox(card), c.box);
  });
}
for (const c of CASES.plan) {
  test("plan: " + c.name, () => {
    assert.deepStrictEqual(T.applyPlan(c.steps, c.args), c.after);
  });
}

test("invisible characters drop a button, even at the edge", () => {
  const card = T.normalizeWrapUp({ recap: "r", ask: "a", actions: [{ label: "\uFEFFYes" }, { label: "Ok", message: "a\u200Bb" }, { label: "Fine" }] });
  assert.deepStrictEqual(card.actions.map((b) => b.label), ["Fine"]);
});
test("refused update_plan changes nothing", () => {
  const before = [{ content: "a", status: "pending" }];
  assert.strictEqual(T.applyPlan(before, { items: [{ content: "b", status: "pending" }] }), before);
  assert.strictEqual(T.applyPlan(before, { done: [5] }), before);
  assert.strictEqual(T.applyPlan(before, {}), before);
});

const PLAN = [{ content: "a", status: "in_progress" }, { content: "b", status: "pending" }];
let n = 0;
const msg = () => ({ id: "m" + ++n, type: "user_message", ordinal: n });
const tool = (name, input, status = "completed") => ({ id: "t" + ++n, type: "dynamic_tool", toolName: "mcp__olympus__" + name, input, status, ordinal: n });
const plan = (input, status) => tool("update_plan", input, status);
const wrap = (input, status) => tool("wrap_up", input, status);
const NEWPLAN = { scope: "first_task", items: PLAN };
const ASK = { recap: "Done.", ask: "Ship?", actions: [{ label: "Yes" }] };

test("empty items give empty view", () => {
  assert.deepStrictEqual(T.view([], null), { plan: null, box: null });
});
test("box after turn ends", () => {
  const v = T.view([msg(), plan(NEWPLAN), wrap(ASK)], { status: "completed" });
  assert.strictEqual(v.box.ask, "Ship?");
  assert.strictEqual(v.box.recap, "Done.");
  assert.deepStrictEqual(v.box.actions, [{ label: "Yes", message: "Yes" }]);
  assert.strictEqual(v.plan, null);
});
test("no box while running", () => {
  const v = T.view([msg(), plan(NEWPLAN), wrap(ASK)], { status: "running" });
  assert.strictEqual(v.box, null);
  assert.ok(v.plan.steps.every((s) => s.status === "completed"));
});
test("box cleared by user reply", () => {
  const v = T.view([msg(), plan(NEWPLAN), wrap(ASK), msg()], { status: "completed" });
  assert.strictEqual(v.box, null);
});
test("recap-only wrap_up draws no box", () => {
  assert.strictEqual(T.view([msg(), wrap({ recap: "Ok." })], { status: "completed" }).box, null);
});
test("old finished plan hidden", () => {
  const items = [msg(), plan(NEWPLAN), wrap(ASK), msg()];
  assert.strictEqual(T.view(items, { status: "running" }).plan, null);
});
test("old unfinished plan shown as old", () => {
  const v = T.view([msg(), plan(NEWPLAN), msg()], { status: "running" });
  assert.strictEqual(v.plan.old, true);
  assert.strictEqual(v.plan.live, true);
  assert.deepStrictEqual(v.plan.steps, PLAN);
});
test("current plan shown live", () => {
  const v = T.view([msg(), plan(NEWPLAN)], { status: "waiting" });
  assert.deepStrictEqual([v.plan.old, v.plan.live], [false, true]);
});
test("interrupted turn keeps list", () => {
  const v = T.view([msg(), plan(NEWPLAN), plan({ advance: true })], { status: "completed" });
  assert.strictEqual(v.plan.live, false);
  assert.strictEqual(v.plan.steps[1].status, "in_progress");
  assert.strictEqual(v.box, null);
});
test("failed calls ignored", () => {
  const v = T.view([msg(), plan(NEWPLAN), plan({ advance: true }, "failed"), plan({ done: [2] }, "error"), wrap(ASK, "failed")], { status: "completed" });
  assert.deepStrictEqual(v.plan.steps, PLAN);
  assert.strictEqual(v.box, null);
});
test("refused calls do not touch the list", () => {
  const v = T.view([msg(), plan(NEWPLAN), msg(), plan({ done: [9] })], { status: "running" });
  assert.strictEqual(v.plan.old, true);
  assert.deepStrictEqual(v.plan.steps, PLAN);
});
test("wrap_up completes the list, a later plan replaces it", () => {
  const items = [msg(), plan(NEWPLAN), wrap({ recap: "Ok." }), msg(), plan({ scope: "new_task", items: [{ content: "c", status: "pending" }] })];
  const v = T.view(items, { status: "running" });
  assert.deepStrictEqual(v.plan.steps, [{ content: "c", status: "pending" }]);
});
test("views are per thread", () => {
  const a = T.view([msg(), plan(NEWPLAN)], { status: "running" });
  const b = T.view([msg(), plan({ advance: true })], { status: "running" });
  assert.strictEqual(b.plan, null);
  assert.deepStrictEqual(a.plan.steps, PLAN);
});
test("exposed as a global", () => {
  assert.strictEqual(globalThis.OlympusTurn, T);
});
