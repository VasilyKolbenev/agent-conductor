import assert from "node:assert/strict";
import {test} from "node:test";
import {createRunWriteHost} from "../src/conductor/panel/desk-run-write-host.js";

const read = (runId = "run-one", taskId = "task-one") => ({
  run: {run_id: runId}, config: {task: {id: taskId}},
});
const desk = (detail, taskId = "task-one") => ({taskId,
  run: {phase: "ready", detail}});
const tick = () => new Promise((done) => setTimeout(done, 0));
const gateRead = (runId, taskId) => ({...read(runId, taskId), records: [],
  graph: {definition: {nodes: [{node_id: "gate-node", gate_id: "gate-one",
    title: "Gate"}]}, runtime: {nodes: [{node_id: "gate-node", decision: "idle"}]},
  schedule: {run_state: "running", nodes: [{node_id: "gate-node", state: "runnable",
    answerable: "first", opens: [], blocked_by: [], closed_by: []}]}}});

test("the Studio write lock survives acceptance until this run is reread", async () => {
  const calls = [], refreshes = [];
  const now = {taskId: "task-one", runId: "run-one", mode: "active",
    foreign: false, connection: "open", ready: true};
  const host = createRunWriteHost({door: {submit: async (...args) => {
    calls.push(args); return {status: "accepted"};
  }}, binding: () => now, refreshRun: (id) => refreshes.push(id),
  onChange: () => {}, onForeign: () => assert.fail("foreign")});
  const first = read();
  host.sync(desk(first));
  host.handlers.chooseStep("node-one");
  host.handlers.editStep({proposedBy: "owner", rationale: "reason"});
  host.handlers.proposeStep({runId: "run-one", nodeId: "node-one",
    generation: host.state().runs.step.generation, body: {proposal_id: "proposal-one"}});
  await tick();
  assert.deepEqual(calls, [["proposals", "run-one", {proposal_id: "proposal-one"}]]);
  assert.deepEqual(refreshes, ["run-one"]);
  assert.equal(host.state().runs.writes["run-one/node-one"], "answered");
  host.sync(desk(first));
  assert.equal(host.state().runs.writes["run-one/node-one"], "answered");
  host.sync(desk(read()));
  assert.equal(host.state().runs.writes["run-one/node-one"], undefined);
  host.dispose();
});

test("view cannot write and an accepted late answer cannot refresh a new task", async () => {
  const calls = [], refreshes = [];
  let complete;
  const now = {taskId: "task-one", runId: "run-one", mode: "view",
    foreign: false, connection: "open", ready: true};
  const host = createRunWriteHost({door: {submit: (...args) => {
    calls.push(args); return new Promise((done) => { complete = done; });
  }}, binding: () => now, refreshRun: (id) => refreshes.push(id),
  onChange: () => {}, onForeign: () => assert.fail("foreign")});
  host.sync(desk(read()));
  host.handlers.publishDocument({runId: "run-one", generation: 0,
    body: {artifact_id: "artifact-one"}});
  await tick();
  assert.equal(calls.length, 0);
  now.mode = "active";
  host.handlers.publishDocument({runId: "run-one", generation: 0,
    body: {artifact_id: "artifact-one"}});
  await tick();
  assert.equal(calls.length, 1);
  now.taskId = "task-two"; now.runId = "run-two";
  host.sync(desk(read("run-two", "task-two"), "task-two"));
  complete({status: "accepted"});
  await tick();
  assert.deepEqual(refreshes, []);
  assert.equal(host.state().runs.selectedId, "run-two");
  host.dispose();
});

test("a late gate answer cannot erase a changed draft or another run's draft", async () => {
  const calls = [], refreshes = [];
  let complete;
  const now = {taskId: "task-one", runId: "run-one", mode: "active",
    foreign: false, connection: "open", ready: true};
  const host = createRunWriteHost({door: {submit: (...args) => {
    calls.push(args); return new Promise((done) => { complete = done; });
  }}, binding: () => now, refreshRun: (id) => refreshes.push(id),
  onChange: () => {}, onForeign: () => assert.fail("foreign")});
  const first = {...desk(gateRead("run-one", "task-one")), actor: "owner"};
  host.sync(first);
  host.handlers.editDecision({reason: "first wording"});
  host.handlers.submitDecision(host.state().decisions.list[0]);
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "decisions");
  assert.equal(host.decisionPending(), true);
  host.handlers.submitDecision(host.state().decisions.list[0]);
  await tick();
  assert.equal(calls.length, 1);
  host.handlers.editDecision({reason: "changed while pending"});
  complete({status: "accepted"});
  await tick();
  assert.equal(host.decisionPending(), false);
  assert.equal(host.state().decisions.draft.reason, "changed while pending");
  assert.deepEqual(refreshes, ["run-one"]);

  let finishOld;
  const secondHost = createRunWriteHost({door: {submit: () => new Promise((done) => {
    finishOld = done;
  })}, binding: () => now, refreshRun: (id) => refreshes.push(id),
  onChange: () => {}, onForeign: () => assert.fail("foreign")});
  secondHost.sync(first);
  secondHost.handlers.editDecision({reason: "old run words"});
  secondHost.handlers.submitDecision(secondHost.state().decisions.list[0]);
  await tick();
  now.taskId = "task-two"; now.runId = "run-two";
  secondHost.sync({...desk(gateRead("run-two", "task-two"), "task-two"), actor: "owner"});
  assert.deepEqual(secondHost.state().decisions.list.map((row) => row.run_id), ["run-two"]);
  assert.equal(secondHost.state().decisions.draft.key, "run-two/gate-one");
  secondHost.handlers.editDecision({reason: "new run words"});
  finishOld({status: "accepted"});
  await tick();
  assert.equal(secondHost.state().decisions.draft.reason, "new run words");
  assert.deepEqual(refreshes, ["run-one"]);
  now.taskId = "task-one"; now.runId = "run-one";
  secondHost.sync(first);
  assert.equal(secondHost.state().decisions.draft.reason, "old run words");
  secondHost.sync({taskId: "task-one", run: {phase: "loading", detail: null}, actor: "owner"});
  assert.deepEqual(secondHost.state().decisions.list, []);
  assert.equal(secondHost.state().decisions.draft.key, null);
  host.dispose(); secondHost.dispose();
});

test("a settled gate yields the Pult draft to the next answerable gate", () => {
  const now = {taskId: "task-one", runId: "run-one", mode: "active",
    foreign: false, connection: "open", ready: true};
  const host = createRunWriteHost({door: {submit: () => assert.fail("unexpected write")},
    binding: () => now, refreshRun: () => {}, onChange: () => {},
    onForeign: () => assert.fail("foreign")});
  const first = gateRead("run-one", "task-one");
  host.sync({...desk(first), actor: "owner"});
  host.handlers.editDecision({reason: "gate A words"});
  const next = {...first, graph: {...first.graph,
    definition: {nodes: [first.graph.definition.nodes[0],
      {node_id: "next-node", gate_id: "gate-two", title: "Gate B"}]},
    runtime: {nodes: [{node_id: "gate-node", decision: "approved"},
      {node_id: "next-node", decision: "idle"}]},
    schedule: {run_state: "running", nodes: [
      {node_id: "gate-node", state: "settled", answerable: "none"},
      {node_id: "next-node", state: "runnable", answerable: "first",
        opens: [], blocked_by: [], closed_by: []}]}}};
  host.sync({...desk(next), actor: "owner"});
  assert.equal(host.state().decisions.draft.key, "run-one/gate-two");
  assert.equal(host.state().decisions.draft.reason, "");
  assert.equal(host.state().decisions.draft.actor, "owner");
  host.handlers.selectDecision("run-one/gate-one");
  assert.equal(host.historyKey(), "run-one/gate-one");
  assert.equal(host.state().decisions.draft.key, "run-one/gate-two");
  host.dispose();
});
