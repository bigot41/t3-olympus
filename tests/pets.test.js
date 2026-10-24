const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "pets.js"), "utf8");

function setup() {
  const listeners = {}, requests = [], messages = [];
  const window = {};
  window.top = window;
  vm.runInNewContext(source, {
    window,
    document: { hasFocus: () => true },
    fetch: () => new Promise(() => {}),
    addEventListener: (name, handler) => { listeners[name] = handler; },
    olympus: {
      HELPER: "http://localhost", threadId: () => "thread", onDom: () => {}, esc: (text) => text,
      post: async (route) => { requests.push(route); return { on: true }; },
      toast: (message) => messages.push(message),
    },
  });
  const key = async (extra = {}) => {
    const event = { ctrlKey: true, altKey: true, code: "KeyP", preventDefault() {}, ...extra };
    await listeners.keydown(event);
  };
  return { key, requests, messages };
}

test("Ctrl+Alt+P retains the visibility toggle", async () => {
  const app = setup();
  await app.key();
  assert.deepEqual(app.requests, ["/pets/toggle"]);
  assert.deepEqual(app.messages, ["Desktop pets on."]);
});

test("Ctrl+Alt+Shift+P opens settings without toggling pets", async () => {
  const app = setup();
  await app.key({ shiftKey: true });
  assert.deepEqual(app.requests, ["/pets/settings"]);
});

test("key repeats and unrelated shortcuts are ignored", async () => {
  const app = setup();
  await app.key({ repeat: true });
  await app.key({ altKey: false });
  await app.key({ code: "KeyQ" });
  assert.deepEqual(app.requests, []);
});
