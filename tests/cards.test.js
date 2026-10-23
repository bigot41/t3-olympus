const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function fixture(data = { chats: 1 }, post = () => Promise.resolve({ ok: true,
  json: () => ({ ok: true, card: { ...data, does: "Fresh AI summary." } }) })) {
  const timers = new Map();
  let counter = 0;
  const listeners = {};
  const requests = [];
  let rendered;
  const rows = new Map();
  const element = (tag) => {
    const classes = new Set();
    return {
      tag, children: [], listeners: {}, style: {}, innerHTML: "", textContent: "",
      classList: { add(...names) { names.forEach((name) => classes.add(name)); },
        remove(...names) { names.forEach((name) => classes.delete(name)); },
        contains(name) { return classes.has(name); } },
      offsetHeight: 100, isConnected: false,
      append(...children) { this.children.push(...children); },
      contains(target) { return target === this || this.children.some((child) => child.contains(target)); },
      setAttribute(name, value) { this[name] = value; },
      addEventListener(name, callback) { this.listeners[name] = callback; },
      focus() { context.document.activeElement = this; listeners.focusin({ type: "focusin", target: this }); },
      remove() { this.isConnected = false; },
    };
  };
  const context = {
    olympus: { esc: String }, innerHeight: 800,
    document: {
      createElement: element, head: { append() {} },
      body: { append(card) { card.isConnected = true; rendered = card; } },
      activeElement: null,
      addEventListener(name, callback) { listeners[name] = callback; },
    },
    setTimeout(callback, delay) { timers.set(++counter, { callback, delay }); return counter; },
    clearTimeout(timer) { timers.delete(timer); },
    requestAnimationFrame(callback) { callback(); },
    fetch(url, options) {
      requests.push({ url, options });
      if (options) {
        assert.equal(url, "http://127.0.0.1:47833/card/refresh");
        return post(options);
      }
      assert.match(url, /^http:\/\/127\.0\.0\.1:47833\/card\?name=/);
      return Promise.resolve({ ok: true, json: () => data });
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../cards.js"), "utf8"), context);
  const rowFor = (name) => {
    if (!rows.has(name)) {
      const row = { querySelector: () => ({ textContent: name }),
        getBoundingClientRect: () => ({ right: 200, top: 100 }),
        closest: () => row, focus() { context.document.activeElement = row; } };
      rows.set(name, row);
    }
    return rows.get(name);
  };
  const flush = (delay) => {
    for (const [id, timer] of [...timers]) {
      if (timer.delay === delay) { timers.delete(id); timer.callback(); }
    }
  };
  return {
    enter(name = "General") { listeners.mouseover({ target: rowFor(name) }); },
    leave() { listeners.mouseover({ target: { closest: () => null } }); },
    cardEnter() { listeners.mouseover({ target: rendered.children[1] }); },
    focusRow(name = "General") {
      const row = rowFor(name);
      context.document.activeElement = row;
      listeners.focusin({ type: "focusin", target: row });
      flush(0);
    },
    tab(name = "General") {
      let prevented = false;
      listeners.keydown({ key: "Tab", target: rowFor(name), preventDefault() { prevented = true; } });
      return prevented;
    },
    escape() { listeners.keydown({ key: "Escape" }); },
    focused() { return context.document.activeElement; },
    card() { return rendered; },
    button() { return rendered.children[1]; },
    click() { return rendered.children[1].listeners.click(); },
    dwell() { flush(1750); },
    flush,
    count() { return requests.length; },
    requests,
    html() { return rendered.children.map((child) => child.innerHTML + child.textContent).join(""); },
    async settle() {
      await new Promise(setImmediate);
      flush(900);
    },
  };
}

test("passing over a profile does not request a card", () => {
  const page = fixture();
  page.enter();
  assert.equal(page.count(), 0);
  page.leave();
  page.dwell();
  assert.equal(page.count(), 0);
});

test("a sustained hover requests once", () => {
  const page = fixture();
  page.enter();
  page.dwell();
  assert.equal(page.count(), 1);
  page.enter();
  page.dwell();
  assert.equal(page.count(), 1);
});

test("the local description and cached AI summary are both visible", async () => {
  const page = fixture({ description: "Local profile description.", does: "Old AI description.",
    topics: [], projects: ["Example folder"], chats: 2, recent: ["Recent chat"] });
  page.enter();
  page.dwell();
  await page.settle();
  assert.match(page.html(), /Local profile description\./);
  assert.match(page.html(), /AI summary.*Old AI description/);
  assert.doesNotMatch(page.html(), /Main work/);
  assert.match(page.html(), /Example folder/);
  assert.match(page.html(), /Latest of 2 chats/);
  assert.match(page.html(), /Recent chat/);
});

test("legacy cards still display cached summaries and topics", async () => {
  const page = fixture({ does: "Cached summary.", topics: ["Testing"], chats: 1 });
  page.enter();
  page.dwell();
  await page.settle();
  assert.match(page.html(), /Cached summary\./);
  assert.match(page.html(), /Main work/);
  assert.match(page.html(), /Testing/);
});

test("crossing the gap onto the card keeps its native refresh button usable", async () => {
  const page = fixture();
  page.enter();
  page.dwell();
  await page.settle();
  page.leave();
  page.cardEnter();
  page.flush(250);
  assert.equal(page.card().classList.contains("on"), true);
  assert.equal(page.button().tag, "button");
  assert.equal(page.button().type, "button");
  assert.match(page.html(), /Refresh AI summaryUses Haiku/);
  await page.click();
  const request = page.requests[1];
  assert.equal(request.options.method, "POST");
  assert.deepEqual(JSON.parse(request.options.body), { name: "General" });
  assert.match(page.html(), /Fresh AI summary/);
});

test("keyboard focus opens the card, Tab reaches the button and Escape dismisses", async () => {
  const page = fixture();
  page.focusRow();
  await page.settle();
  assert.equal(page.tab(), true);
  assert.equal(page.focused(), page.button());
  page.leave();
  page.flush(250);
  assert.equal(page.card().classList.contains("on"), true);
  page.escape();
  assert.equal(page.card().classList.contains("on"), false);
  assert.equal(page.card().inert, true);
});

test("refresh disables in flight and never issues duplicate requests", async () => {
  let finish;
  const page = fixture({ chats: 1 }, () => new Promise((resolve) => { finish = resolve; }));
  page.enter();
  page.dwell();
  await page.settle();
  const first = page.click();
  assert.equal(page.button().disabled, true);
  await page.click();
  assert.equal(page.count(), 2);
  finish({ ok: true, json: () => ({ ok: true, card: { chats: 1, does: "New summary." } }) });
  await first;
  assert.equal(page.button().disabled, false);
  assert.match(page.html(), /New summary/);
});

test("failed refresh preserves cached text and shows only a safe generic error", async () => {
  const data = { description: "Local description.", does: "Cached summary.", chats: 1 };
  const page = fixture(data, () => Promise.resolve({ ok: false,
    json: () => ({ error: "private details <script>" }) }));
  page.enter();
  page.dwell();
  await page.settle();
  await page.click();
  assert.equal(page.count(), 2);
  assert.equal(page.button().disabled, false);
  assert.match(page.html(), /Local description/);
  assert.match(page.html(), /Cached summary/);
  assert.match(page.html(), /Couldn't refresh AI summary/);
  assert.doesNotMatch(page.html(), /private|<script>/);
});

test("a late refresh never replaces the newly hovered profile", async () => {
  let finish;
  const page = fixture({ chats: 1 }, () => new Promise((resolve) => { finish = resolve; }));
  page.enter();
  page.dwell();
  await page.settle();
  const first = page.click();
  page.enter("Dev");
  page.dwell();
  await page.settle();
  finish({ ok: true, json: () => ({ ok: true, card: { chats: 1, does: "General only." } }) });
  await first;
  assert.match(page.html(), /<b>Dev<\/b>/);
  assert.doesNotMatch(page.html(), /General only/);
  page.enter();
  page.dwell();
  assert.match(page.html(), /General only/);
});
