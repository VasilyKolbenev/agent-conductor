"use strict";
// The door of the project's task queue (spec 4.4.5 and 4.4.6): its one read, and the two writes
// that change the order of what waits (`order` and `withdraw`). The boot module is held to write
// nothing at all, so the queue's reads and writes live here, where they can be read whole; this
// module keeps no state, no timer and no storage, and it opens no door of its own: it reaches the
// wire only through the transport `door` it is handed, with the session token and the project
// claim that door adds, and names one target of the mutation door per write.
//
// A read answers the queue as `desk-queue-model.js` vouches for it, or `null`: a route that is
// not there, a refusal, an answer that never came and a body of another shape are all "no queue
// to draw", and the console then draws none rather than an empty one.
//
// A write answers what a caller must know to say something true: the queue the server now holds
// (`saved` -- every queue write answers with the read as it stands after it; a `saved` whose body
// the model cannot vouch for carries no queue, and the caller reads again), the code it refused
// with (`refused`), or that the desk cannot tell what landed (`unknown`: the answer never came).
// A refusal `project_mismatch` from any call tells the boot module, which ends the desk.
import {path} from "./desk-transport.js";
import {projectQueue} from "./desk-queue-model.js";

const MISMATCH = "project_mismatch";

//: What a write answered, cut to the three things a caller may rely on.
function outcome(answer, ended) {
  if (answer.code === MISMATCH) ended();
  if (answer.status === "accepted") {
    return Object.freeze({status: "saved", queue: projectQueue(answer.payload)});
  }
  return Object.freeze({status: answer.status === "refused" ? "refused" : "unknown",
    code: answer.code ?? null});
}

//: The calls of the queue's door over the transport `door`; `ended` is called when the server
//: says it serves another project.
export function createQueueDoor(door, ended) {
  async function read() {
    try {
      return projectQueue(await door.readJson(path.queue()));
    } catch (error) {
      if (error instanceof Error && error.message === MISMATCH) ended();
      return null;
    }
  }
  async function order(body) {
    return outcome(await door.submit("queueOrder", null, body), ended);
  }
  async function withdraw(runId, body) {
    return outcome(await door.submit("queueWithdraw", runId, body), ended);
  }
  return Object.freeze({read, order, withdraw});
}
