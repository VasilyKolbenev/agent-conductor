"use strict";
// The door of the continue-after flag (spec 4.3.4 and 5.8): the one read of it and the one write
// of it, and nothing else. The boot module is held to write nothing at all, so the one write that
// is a person's decision to change what happens to a project at its next activation lives here,
// where it can be read whole: it names ONE target of the transport, `autoContinue`, and reaches
// the wire through the transport's mutation door like every write, with the session token and
// the project claim it adds. It holds no state, no timer and no storage, and it opens no door of
// its own.
//
// A read answers a record this desk can vouch for, or `null`: a body of another shape, a route
// that is not there and a refusal are all "no flag to draw". A write answers what a caller must
// know to say something true: the record the server now holds (`saved`), the code it refused with
// (`refused`), or that the desk cannot tell what landed (`unknown`); an answer that was accepted
// but is not a record is `saved` with no flag, and the caller reads the flag again. A refusal
// `project_mismatch` from either door tells the boot module, which ends the desk.
import {path} from "./desk-transport.js";
import {projectFlag} from "./desk-flag-model.js";

const MISMATCH = "project_mismatch";

//: The two calls of the flag's door over the transport `door`; `ended` is called when the server
//: says it serves another project.
export function createFlagDoor(door, ended) {
  async function read() {
    try {
      return projectFlag(await door.readJson(path.autoContinue()));
    } catch (error) {
      if (error instanceof Error && error.message === MISMATCH) ended();
      return null;
    }
  }
  async function save(body) {
    const answer = await door.submit("autoContinue", null, body);
    if (answer.code === MISMATCH) ended();
    if (answer.status === "accepted") {
      return Object.freeze({status: "saved", flag: projectFlag(answer.payload)});
    }
    return Object.freeze({status: answer.status === "refused" ? "refused" : "unknown",
      code: answer.code ?? null});
  }
  return Object.freeze({read, save});
}
