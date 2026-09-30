"use strict";
// The door of the project's task queue (spec 4.4.5 and 4.4.6): the one read of it. The boot module
// is held to write nothing at all, so the queue's reads and, in later slices, its writes live
// here, where they can be read whole; nothing in this module keeps state, a timer or a storage,
// and it opens no door of its own: it reaches the wire only through the transport `door` it is
// handed, with the session token and the project claim that door adds.
//
// A read answers the queue as `desk-queue-model.js` vouches for it, or `null`: a route that is
// not there, a refusal, an answer that never came and a body of another shape are all "no queue
// to draw", and the console then draws none rather than an empty one. A refusal
// `project_mismatch` tells the boot module, which ends the desk.
import {path} from "./desk-transport.js";
import {projectQueue} from "./desk-queue-model.js";

const MISMATCH = "project_mismatch";

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
  return Object.freeze({read});
}
