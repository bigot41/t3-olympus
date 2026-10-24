const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { background, send } = require("../background.js");

function socket() {
  const listeners = new Map();
  return {
    readyState: 1, requests: [],
    addEventListener(name, callback) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(callback);
    },
    removeEventListener(name, callback) { listeners.get(name)?.delete(callback); },
    send(data) { this.requests.push(JSON.parse(data)); },
    emit(name, event) { for (const callback of [...listeners.get(name) || []]) callback(event); },
    reply(request, success = true) {
      this.emit("message", { data: JSON.stringify({ _tag: "Exit", requestId: String(request.id),
        exit: { _tag: success ? "Success" : "Failure", value: { sequence: 1 } } }) });
    },
    listenerCount() { return [...listeners.values()].reduce((total, values) => total + values.size, 0); },
  };
}

test("Background keeps the same children and lineage, enabling completion delivery only", async () => {
  const connection = socket();
  const promise = background("parent", [{ id: "child-one" }, { id: "child-two" }], connection);
  assert.equal(connection.requests.length, 2);
  for (const request of connection.requests) {
    assert.equal(request.tag, "orchestration.dispatchCommand");
    assert.equal(request.payload.type, "delegated_task.wake-policy");
    assert.equal(request.payload.parentThreadId, "parent");
    assert.equal(request.payload.completionWake, "always");
    connection.reply(request);
  }
  assert.deepEqual(connection.requests.map((request) => request.payload.taskId), ["child-one", "child-two"]);
  await promise;
  assert.equal(connection.listenerCount(), 0);
});

test("does not report success before the matching server acknowledgement", async () => {
  const connection = socket();
  let resolved = false;
  const promise = send(connection, { type: "test" }).then(() => { resolved = true; });
  connection.emit("message", { data: "garbage" });
  connection.emit("message", { data: JSON.stringify([null, { _tag: "Exit", requestId: -1, exit: { _tag: "Success" } }]) });
  await Promise.resolve();
  assert.equal(resolved, false);
  connection.reply(connection.requests[0]);
  await promise;
  assert.equal(resolved, true);
});

test("server rejection is shown without stopping or restarting agents", async () => {
  const connection = socket();
  const promise = background("parent", [{ id: "child" }], connection);
  connection.reply(connection.requests[0], false);
  await assert.rejects(promise, /Couldn't background/);
  assert.equal(connection.requests.length, 1);
  assert.equal(connection.listenerCount(), 0);
});

test("connection loss releases listeners and does not retry uncertain commands", async () => {
  const connection = socket();
  const promise = send(connection, { type: "test" });
  connection.emit("close", {});
  await assert.rejects(promise, /disconnected/);
  assert.equal(connection.requests.length, 1);
  assert.equal(connection.listenerCount(), 0);
});

test("disconnected T3 rejects the action before sending", async () => {
  await assert.rejects(background("parent", [{ id: "child" }], null), /not connected/);
});

test("unacknowledged requests time out without claiming success", async () => {
  const connection = socket();
  await assert.rejects(send(connection, { type: "test" }, 5), /hasn't confirmed/);
  assert.equal(connection.requests.length, 1);
  assert.equal(connection.listenerCount(), 0);
});

function uiFixture(initialTasks = [{ id: "child" }]) {
  const elements = new Map(), notices = [], state = { thread: "parent", tasks: initialTasks };
  const connection = socket();
  let tick;
  const element = () => ({
    children: [], listeners: {}, disabled: false,
    append(child) { this.children.push(child); },
    addEventListener(name, callback) { this.listeners[name] = callback; },
    querySelector() { return this.children[0]; },
    remove() { elements.delete(this.id); },
  });
  const context = {
    window: { olympusT3Socket: connection }, crypto: globalThis.crypto, TextDecoder,
    setTimeout, clearTimeout, setInterval() {},
    document: {
      createElement: element, head: { append() {} },
      getElementById: (id) => elements.get(id),
      querySelector: () => ({}),
    },
    olympus: {
      COMPOSER: "composer", HELPER: "helper", threadId: () => state.thread,
      onDom(callback) { tick = callback; }, esc: String, toast: (text) => notices.push(text),
      fill() { throw new Error("Must not change the user's composer"); },
    },
    olympusAbove(row) { elements.set(row.id, row); },
    fetch: async () => ({ ok: true, json: async () => ({ tasks: state.tasks }) }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../background.js"), "utf8"), context);
  return {
    connection, notices, state, tick: () => tick(),
    button: () => elements.get("olympus-background")?.children[0],
    flush: () => new Promise((resolve) => setImmediate(resolve)),
  };
}

test("UI shows one small background button only when there is a waiting delegation", async () => {
  const app = uiFixture();
  await app.flush();
  assert.equal(app.button().textContent, "↗ Continue in background");
  app.state.thread = null;
  app.tick();
  assert.equal(app.button(), undefined);
  const empty = uiFixture([]);
  await empty.flush();
  assert.equal(empty.button(), undefined);
});

test("UI blocks duplicate clicks and only confirms after server success", async () => {
  const app = uiFixture();
  await app.flush();
  const click = app.button().listeners.click;
  const pending = click();
  assert.equal(app.button().disabled, true);
  await click();
  assert.equal(app.connection.requests.length, 1);
  assert.deepEqual(app.notices, []);
  app.state.tasks = [];
  app.connection.reply(app.connection.requests[0]);
  await pending;
  await app.flush();
  assert.equal(app.button(), undefined);
  assert.equal(app.notices.length, 1);
  assert.match(app.notices[0], /continuing in the background/);
});

test("UI reports rejection rather than claiming that the parent is free", async () => {
  const app = uiFixture();
  await app.flush();
  const pending = app.button().listeners.click();
  app.connection.reply(app.connection.requests[0], false);
  await pending;
  await app.flush();
  assert.equal(app.button().disabled, false);
  assert.equal(app.notices.length, 1);
  assert.match(app.notices[0], /Couldn't background/);
});
