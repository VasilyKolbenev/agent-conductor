"use strict";
// What a press on the console's queue block MEANS (spec 4.4.8): a step up or down, the withdrawal
// of an entry, and freeing the slot of a holder that stopped. It is the console's hands, between
// the buttons `desk-pult.js` draws and the queue door `desk-queue.js` writes through, and it names
// no route and no wire word of its own: it is handed the door and the boot module's state, and it
// does nothing the door cannot.
//
// Every press follows one rule. A write is never believed for being answered: a queue the answer
// carries is the queue the server holds after it, and it is what the console is drawn from; an
// answer that is lost, refused or unreadable is settled by reading again -- the queue, and for a
// control the holder it was written to -- and what the person is told is what that read shows. A
// write that landed but whose answer was lost says nothing; a refusal says its catalogue words; a
// change the read does not show says that it could not be confirmed. While one write is out no
// other press is taken, so the queue the desk holds is always the one the next press acts on.
//
// Its small state is `pult` in the boot module's state: the notice under the block (null, or what
// the last write left: a refusal with its code, or an unconfirmed change), what is in flight, and
// the dialog that is open (null, or `{kind, run_id, nonce}`: the nonce makes the ids of what the
// dialog writes, so a press that is repeated is the same write and not a second one).
import {controlBody, controlRecorded, holdsOrder, holdsRun, orderBody, releaseOffer,
  withdrawBody} from "./desk-queue-model.js";

export const NO_PULT = Object.freeze({notice: null, busy: null, dialog: null});

const refused = (code) => Object.freeze({kind: "refused", code});
const UNCONFIRMED = Object.freeze({kind: "unconfirmed"});
//: What stands in for an answer when nothing was sent: what landed is not known.
const UNSENT = Object.freeze({status: "unknown", code: null});

//: The hands of the console. `door` is the queue door; `host` gives the boot module's state
//: (`state()`), takes a change of it (`move(patch)`, which a terminal desk ignores) and makes a
//: nonce (`nonce()`).
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

  // -- freeing the slot of a holder that stopped -------------------------------------------

  //: Open the dialog, for the holder the queue names, when the console offers it.
  function openRelease() {
    const {queue, mode, actor} = host.state();
    const offer = releaseOffer(queue, {mode, actor});
    if (offer === null || !offer.named || held().busy !== null) return;
    show({notice: null, dialog: Object.freeze({kind: "release", run_id: offer.run_id,
      nonce: host.nonce()})});
  }

  const closeDialog = () => show({dialog: null});

  //: What a control that was not cleanly answered leaves: the queue is read again (it says whether
  //: the slot is free), and a control whose answer was lost is settled by the holder's own read.
  async function settleControl(answer, runId, body) {
    land(await door.read());
    if (answer.status === "saved") return null;
    if (answer.status === "refused") return refused(answer.code);
    const holder = await door.automation(runId);
    return body !== null && controlRecorded(holder, body.control_id) ? null : UNCONFIRMED;
  }

  //: The person's choice in the dialog: `pause` or `revoke`, written to the holder's grant as the
  //: desk reads it NOW, in the name of the person at the page.
  async function release(action) {
    const {foreign, actor, queue, mode} = host.state();
    const dialog = held().dialog;
    if (foreign || actor === null || held().busy !== null || dialog?.kind !== "release") return;
    if (releaseOffer(queue, {mode, actor})?.run_id !== dialog.run_id) {
      show({dialog: null});                  // the slot is no longer this run's to free
      return;
    }
    show({busy: "slot", notice: null});
    const holder = await door.automation(dialog.run_id);
    const controlId = `control-${dialog.nonce}-${action}`;
    const body = controlBody(holder, {action, actor, controlId});
    const answer = body === null ? UNSENT : await door.control(dialog.run_id, body);
    show({busy: null, dialog: null, notice: await settleControl(answer, dialog.run_id, body)});
  }

  return Object.freeze({order, withdraw, openRelease, closeDialog, release});
}
