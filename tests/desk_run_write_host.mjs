import assert from "node:assert/strict";
import {test} from "node:test";
import {createRunWriteHost} from "../src/conductor/panel/desk-run-write-host.js";

const read = (runId = "run-one", taskId = "task-one") => ({
  run: {run_id: runId}, config: {task: {id: taskId}},
});
const desk = (detail, taskId = "task-one") => ({taskId,
  run: {phase: "ready", detail}});
const tick = () => new Promise((done) => setTimeout(done, 0));

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
