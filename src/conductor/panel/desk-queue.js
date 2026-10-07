"use strict";
// The door of the project's task queue (spec 4.4.5, 4.4.6 and 4.4.8): its one read, the two writes
// that change the order of what waits (`order` and `withdraw`), and what it takes to free the slot
// of a holder that stopped: a read of the holder and the control that pauses or revokes it. The
// boot module is held to write nothing at all, so these live here, where they can be read whole;
// this module keeps no state, no timer and no storage, and it opens no door of its own: it reaches
// the wire only through the transport `door` it is handed, with the session token and the project
// claim that door adds, and names one target of the mutation door per write.
//
// A read answers what its model vouches for, or `null`: a route that is not there, a refusal, an
// answer that never came and a body of another shape are all "nothing to draw", and the console
// then draws nothing rather than an empty queue.
//
// A write answers what a caller must know to say something true: the queue the server now holds
// (`saved` -- a queue write answers with the read as it stands after it; a `saved` whose body the
// model cannot vouch for carries no queue, and the caller reads again), the code it refused with
// (`refused`), or that the desk cannot tell what landed (`unknown`: the answer never came). The
// control's answer is the control it recorded and says nothing of the queue. A refusal
// `project_mismatch` from any call tells the boot module, which ends the desk.
import {path} from "./desk-transport.js";
import {confirmPreview, projectHolder, projectQueue} from "./desk-queue-model.js";

const MISMATCH = "project_mismatch";

//: What a write answered, cut to the three things a caller may rely on. `judge` reads the body of
//: an answer that is a queue; a write whose answer is not one judges nothing.
function outcome(answer, ended, judge) {
  if (answer.code === MISMATCH) ended();
  if (answer.status === "accepted") {
    return Object.freeze({status: "saved", queue: judge === null ? null : judge(answer.payload)});
  }
  return Object.freeze({status: answer.status === "refused" ? "refused" : "unknown",
    code: answer.code ?? null});
}

//: The calls of the queue's door over the transport `door`; `ended` is called when the server
//: says it serves another project.
export function createQueueDoor(door, ended) {
  async function read(target, judge) {
    try {
      return judge(await door.readJson(target));
    } catch (error) {
      if (error instanceof Error && error.message === MISMATCH) ended();
      return null;
    }
  }
  const queue = () => read(path.queue(), projectQueue);
  const automation = (runId) => read(path.automation(runId),
    (body) => projectHolder(body, runId));
  async function order(body) {
    return outcome(await door.submit("queueOrder", null, body), ended, projectQueue);
  }
  async function withdraw(runId, body) {
    return outcome(await door.submit("queueWithdraw", runId, body), ended, projectQueue);
  }
  async function control(runId, body) {
    return outcome(await door.submit("automationControl", runId, body), ended, null);
  }
  async function enqueue(body) {
    return outcome(await door.submit("queue", null, body), ended, projectQueue);
  }
  async function preview(runId) {
    const answer = await door.submit("automationPreview", runId, {});
    if (answer.code === MISMATCH) ended();
    return Object.freeze({status: answer.status === "accepted" ? "saved" : answer.status,
      code: answer.code ?? null,
      preview: answer.status === "accepted" ? confirmPreview(answer.payload) : null});
  }
  return Object.freeze({read: queue, automation, order, withdraw, control, enqueue, preview});
}
