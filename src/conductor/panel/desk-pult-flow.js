"use strict";
// What a press on the console's queue block MEANS (spec 4.4.8): a step up or down, and the
// withdrawal of an entry. It is the console's hands, between the buttons `desk-pult.js` draws and
// the queue door `desk-queue.js` writes through, and it names no route and no wire word of its
// own: it is handed the door and the boot module's state, and it does nothing the door cannot.
//
// Every press follows one rule. A write is never believed for being answered: the queue the
// answer carries is the queue the server holds after it, and it is what the console is drawn from;
// an answer that is lost, refused or unreadable is settled by reading the queue again, and what
// the person is told is what that read shows. A write that landed but whose answer was lost says
// nothing; a refusal says its catalogue words; a change the read does not show says that it could
// not be confirmed. While one write is out no other press is taken, so the queue the desk holds is
// always the one the next press acts on.
//
// Its small state is `pult` in the boot module's state: the notice under the block (null, or what
// the last write left: a refusal with its code, or an unconfirmed change) and what is in flight.
import {holdsOrder, holdsRun, orderBody, withdrawBody} from "./desk-queue-model.js";

export const NO_PULT = Object.freeze({notice: null, busy: null});

const refused = (code) => Object.freeze({kind: "refused", code});
const UNCONFIRMED = Object.freeze({kind: "unconfirmed"});

//: The hands of the console. `door` is the queue door; `host` gives the boot module's state
//: (`state()`) and takes a change of it (`move(patch)`, which a terminal desk ignores).
export function createPultFlow({door, host}) {
  const held = () => host.state().pult;
  const show = (changes) => host.move({pult: Object.freeze({...held(), ...changes})});
  const land = (queue) => {
    if (queue !== null) host.move({queue});
  };

  //: A write that was not cleanly answered: read the queue again and say what that read shows.
  async function settle(answer, landed) {
    const fresh = await door.read();
    land(fresh);
    if (answer.status === "refused") return refused(answer.code);
    return fresh !== null && landed(fresh) ? null : UNCONFIRMED;
  }

  //: One press: lock the block while the write is out, draw from the answer, settle what is not
  //: clean. `landed` asks a queue whether what was written has come to stand.
  async function perform(lock, send, landed) {
    const state = host.state();
    if (state.foreign || state.queue === null || held().busy !== null) return;
    show({busy: lock, notice: null});
    const answer = await send();
    const clean = answer.status === "saved" && answer.queue !== null;
    if (clean) land(answer.queue);
    show({busy: null, notice: clean ? null : await settle(answer, landed)});
  }

  function order(runId, step) {
    const body = orderBody(host.state().queue, runId, step);
    if (body === null) return Promise.resolve();
    return perform(runId, () => door.order(body), (queue) => holdsOrder(queue, body.run_ids));
  }

  function withdraw(runId) {
    return perform(runId, () => door.withdraw(runId, withdrawBody()),
      (queue) => !holdsRun(queue, runId));
  }

  return Object.freeze({order, withdraw});
}
