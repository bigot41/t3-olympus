// Tests for parseFrame in olympus-hook.js.
const test = require("node:test");
const assert = require("node:assert");
const { parseFrame } = require("../olympus-hook.js");

const subs = new Map([["5", "t1"]]);
const chunk = (id, ...values) => ({ _tag: "Chunk", requestId: id, values });
const ev = (event) => ({ kind: "event", sequence: 1, event });

test("turn item for a known request", () => {
  const item = { type: "dynamic_tool", toolName: "mcp__olympus__wrap_up" };
  const out = parseFrame(JSON.stringify(chunk("5", ev({ type: "turn-item.updated", payload: item }))), subs);
  assert.deepStrictEqual(out, [{ threadId: "t1", kind: "item", payload: item }]);
});

test("unknown request id without a thread gives nothing", () => {
  const f = JSON.stringify(chunk("9", ev({ type: "turn-item.updated", payload: {} })));
  assert.deepStrictEqual(parseFrame(f, subs), []);
});

test("another subscription's event that names its thread is passed on", () => {
  // a brand-new chat's first run updates come on T3's wider subscription, not the chat's own
  const run = { status: "running", ordinal: 1, threadId: "t2" };
  const out = parseFrame(JSON.stringify(chunk("9", ev({ type: "run.updated", payload: run }))), subs);
  assert.deepStrictEqual(out, [{ threadId: "t2", kind: "run", payload: run }]);
});

test("run.updated gives a run", () => {
  const run = { status: "running", ordinal: 7, threadId: "t1" };
  const out = parseFrame(JSON.stringify(chunk("5", ev({ type: "run.updated", payload: run }))), subs);
  assert.deepStrictEqual(out, [{ threadId: "t1", kind: "run", payload: run }]);
});

test("snapshot gives its projection", () => {
  const projection = { turnItems: [] };
  const out = parseFrame(JSON.stringify(chunk("5", { kind: "snapshot", projection })), subs);
  assert.deepStrictEqual(out, [{ threadId: "t1", kind: "snapshot", payload: projection }]);
});

test("array of two messages", () => {
  const a = chunk("5", ev({ type: "turn-item.updated", payload: { id: 1 } }));
  const b = chunk("5", ev({ type: "run.updated", payload: { status: "x" } }));
  const out = parseFrame(JSON.stringify([a, b, { _tag: "Pong" }]), subs);
  assert.deepStrictEqual(out.map((o) => o.kind), ["item", "run"]);
});

test("ArrayBuffer frame", () => {
  const bytes = new TextEncoder().encode(JSON.stringify(chunk("5", ev({ type: "turn-item.updated", payload: { id: 2 } }))));
  const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  assert.strictEqual(parseFrame(buf, subs)[0].payload.id, 2);
});

test("invalid JSON gives nothing", () => {
  assert.deepStrictEqual(parseFrame("{nope", subs), []);
});
