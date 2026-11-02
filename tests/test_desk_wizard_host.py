"""The live wizard host fences an opening that its address has since abandoned."""
from __future__ import annotations

from tests.desk_node import run_js


def test_removed_wizard_address_and_reentrant_close_send_no_late_asks():
    answer = run_js("""
const {getEventListeners} = await import("node:events");
globalThis.window = new EventTarget();
globalThis.history = {state: null};
const mount = {replaceChildren() {}, querySelector() { return null; }};
const trigger = {addEventListener() {}, removeEventListener() {}};
const context = {actor: () => "owner", mode: () => "view", tasks: () => [],
  foreign: () => false, applied: () => true};
const open = {steps: [{key: "new"}, {key: "starter"}]};
const keys = {new: "task", prepare: null, starter: "desk-starter-docs"};
const gone = {new: null, prepare: null, starter: null};
let release, reads = [], host;
const held = {readJson(url) {
  reads.push(url);
  return new Promise((resolve) => { release = resolve; });
}, submit() { throw Error("unexpected write"); }};
host = h.createWizardHost({mount, trigger, door: held, locale: () => "en",
  nonce: () => "12345678", onForeign() {}, onState() {}, onHash() {}, onExit() {}});
host.bind(context);
const opening = host.navigate(open, keys);
await host.navigate({steps: [], reset: []}, gone);
release({starters: [{starter_id: "desk-starter-docs"}]});
await opening;
const fenced = host.state() === null && reads.length === 1;
let second, secondReads = [];
const eager = {readJson(url) {
  secondReads.push(url);
  if (url === "/command/workflows") return Promise.resolve({starters: []});
  throw Error("ask escaped closed host");
}, submit() { throw Error("write escaped closed host"); }};
second = h.createWizardHost({mount, trigger, door: eager, locale: () => "en",
  nonce: () => "12345678", onForeign() {}, onState() {},
  onHash() { second.close(); }, onExit() {}});
second.bind(context);
await second.navigate(open, keys);
const callback = second.state() === null && secondReads.length === 1;
const listeners = () => getEventListeners(window, "beforeunload").length;
const active = listeners();
host.dispose();
const oneLeft = listeners();
second.dispose();
console.log(JSON.stringify({fenced, callback, listeners: [active, oneLeft, listeners()]}));
""", {"h": "desk-wizard-host.js"})
    assert answer == {"fenced": True, "callback": True, "listeners": [2, 1, 0]}
