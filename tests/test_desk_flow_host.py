"""The flow host stops its pending work when the desk removes its panel."""
from __future__ import annotations

from tests.desk_wizard_node import run_js

DOM = """
const body = {};
globalThis.document = {body, activeElement: body, addEventListener() {}, createElement(tag) {
  return {tag, children: [], append(...nodes) {this.children.push(...nodes)},
    setAttribute() {}, addEventListener() {},
    replaceChildren(...nodes) {this.children = nodes}, querySelectorAll() {return []}};
}};
"""


def test_an_on_state_dispose_does_not_redraw_or_send_the_new_flow_write():
    out = run_js(DOM + """
      const mount = document.createElement("div");
      let writes = 0, host;
      const door = {readJson: () => new Promise(() => {}),
        submit: () => {writes += 1; return Promise.resolve({status: "accepted"})}};
      host = flowHost.createFlowHost({mount, door, locale: () => "en", nonce: "a".repeat(32),
        onForeign: () => {}, onState: (schema) => {
          if (schema.write.workflowId !== null) host.dispose();
        }});
      host.open();
      host.dispatch({type: "new", from: "starter", id: "desk-standard"});
      console.log(JSON.stringify({writes, children: mount.children.length,
        workflow: host.state().write.workflowId}));
    """, modules={"flowHost": "desk-flow-host.js"})
    assert out == {"writes": 0, "children": 0, "workflow": "cycle-aaaaaaaa"}


def test_a_project_mismatch_invalidates_pending_asks_before_notifying_the_desk():
    out = run_js(DOM + """
      const mount = document.createElement("div");
      let writes = 0, seen = 0, host;
      const door = {readJson: () => Promise.reject(new Error("project_mismatch")),
        submit: () => {writes += 1; return Promise.resolve({status: "accepted"})}};
      host = flowHost.createFlowHost({mount, door, locale: () => "en", nonce: "a".repeat(32),
        onForeign: () => {
          seen += 1;
          host.dispatch({type: "new", from: "starter", id: "desk-standard"});
        }});
      host.open();
      await new Promise((resolve) => setTimeout(resolve, 0));
      console.log(JSON.stringify({seen, writes, workflow: host.state().write.workflowId}));
    """, modules={"flowHost": "desk-flow-host.js"})
    assert out == {"seen": 1, "writes": 0, "workflow": None}


def test_a_suspended_host_holds_asks_and_answers_keeps_the_draft_and_stays_disposed():
    out = run_js(DOM + """
      const mount = document.createElement("div");
      let reads = 0, writes = 0, releaseWrite, releaseRead, host, pauseNewAsk = true;
      const door = {
        readJson: (path) => {
          reads += 1;
          return new Promise((resolve) => { if (path.endsWith("/flow")) releaseRead = resolve; });
        },
        submit: () => {
          writes += 1;
          return new Promise((resolve) => { releaseWrite = resolve; });
        },
      };
      host = flowHost.createFlowHost({mount, door, locale: () => "en", nonce: "a".repeat(32),
        onForeign: () => { throw new Error("unexpected foreign project"); },
        onState: (schema) => {
          if (pauseNewAsk && schema.write.inflight !== null) {
            pauseNewAsk = false;
            host.suspend();
          }
        }});
      host.open();
      host.dispatch({type: "new", from: "starter", id: "desk-standard"});
      const heldAsk = {reads, writes};
      host.resume();
      host.dispatch({type: "quick-open"});
      host.dispatch({type: "quick-title", value: "Unfinished title"});
      const before = host.state(), drawn = mount.children;
      host.suspend();
      releaseWrite({status: "unknown"});
      await Promise.resolve();
      host.refresh();
      const hidden = {reads, writes, unchanged: host.state() === before,
        undrawn: mount.children === drawn};
      host.resume();
      const resumed = {reads, writes, draft: host.state().quick.title,
        settling: host.state().write.reading?.purpose};
      host.suspend();
      const ending = host.state();
      releaseRead({});
      await Promise.resolve();
      host.dispose();
      host.resume();
      host.refresh();
      host.open();
      host.dispatch({type: "new", from: "starter", id: "desk-standard"});
      console.log(JSON.stringify({heldAsk, hidden, resumed,
        ended: {reads, writes, unchanged: host.state() === ending,
          children: mount.children.length}}));
    """, modules={"flowHost": "desk-flow-host.js"})
    assert out == {
        "heldAsk": {"reads": 1, "writes": 0},
        "hidden": {"reads": 1, "writes": 1, "unchanged": True, "undrawn": True},
        "resumed": {"reads": 2, "writes": 1, "draft": "Unfinished title", "settling": "settle"},
        "ended": {"reads": 2, "writes": 1, "unchanged": True, "children": 0},
    }
