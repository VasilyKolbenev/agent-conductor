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
import {confirmBody, controlBody, controlRecorded, holdsOrder, holdsRun, orderBody,
  releaseOffer, resumeBody, skipOffer, skipProgress, skipStep, withdrawBody} from "./desk-queue-model.js";

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
  async function openRelease() {
    const {queue, mode, actor} = host.state();
    const offer = releaseOffer(queue, {mode, actor});
    if (offer === null || !offer.named || held().busy !== null || held().dialog !== null) return;
    const nonce = host.nonce();
    show({busy: "release-read", notice: null});
    const [fresh, snapshot] = await Promise.all([door.read(), door.automation(offer.run_id)]);
    if (host.state().foreign) return;
    land(fresh);
    if (snapshot === null || host.state().actor !== actor || host.state().mode !== mode
        || releaseOffer(fresh, {mode, actor})?.run_id !== offer.run_id) {
      show({busy: null, notice: UNCONFIRMED});
      return;
    }
    show({busy: null, dialog: Object.freeze({kind: "release", run_id: offer.run_id,
      nonce, snapshot})});
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
    const before = dialog.snapshot;
    const [freshQueue, holder] = await Promise.all([door.read(), door.automation(dialog.run_id)]);
    if (host.state().foreign) return;
    land(freshQueue);
    const same = before !== null && holder !== null
      && releaseOffer(freshQueue, {mode, actor})?.run_id === dialog.run_id
      && before.state === holder.state && before.reason_code === holder.reason_code
      && before.last_control_id === holder.last_control_id
      && before.grant?.authorization_id === holder.grant?.authorization_id
      && before.grant?.authorization_digest === holder.grant?.authorization_digest;
    if (!same) {
      show({busy: null, dialog: null, notice: UNCONFIRMED});
      return;
    }
    const controlId = `control-${dialog.nonce}-${action}`;
    const body = controlBody(holder, {action, actor, controlId});
    const answer = body === null ? UNSENT : await door.control(dialog.run_id, body);
    show({busy: null, dialog: null, notice: await settleControl(answer, dialog.run_id, body)});
  }

  //: A skip holds one nonce across retries. The dialog is kept when a lost queue answer cannot
  //: be settled; the next press reads the holder and queue before deciding which step remains.
  function openSkip() {
    const {queue, mode, actor} = host.state();
    const offer = skipOffer(queue, {mode, actor});
    if (offer === null || !offer.named || held().busy !== null || held().dialog !== null) return;
    const nonce = host.nonce();
    show({notice: null, dialog: Object.freeze({kind: "skip", run_id: offer.run_id,
      nonce, expires_at: null})});
    void door.automation(offer.run_id).then((holder) => {
      if (host.state().foreign || held().dialog?.nonce !== nonce) return;
      show({dialog: Object.freeze({...held().dialog, expires_at: holder?.expires_at ?? null})});
    });
  }

  async function skip() {
    const {foreign, actor, queue, mode} = host.state();
    const dialog = held().dialog;
    if (foreign || actor === null || held().busy !== null || dialog?.kind !== "skip") return;
    show({busy: "skip", notice: null});
    const pauseId = `control-${dialog.nonce}-pause`;
    const resumeId = `control-${dialog.nonce}-resume`;
    let holder = await door.automation(dialog.run_id);
    let fresh = await door.read();
    if (host.state().foreign) return;
    land(fresh);
    let step = skipStep(skipProgress({holder, queue: fresh, runId: dialog.run_id, pauseId}));
    if (step === "pause") {
      if (skipOffer(fresh, {mode, actor})?.run_id !== dialog.run_id) {
        show({busy: null, dialog: null});
        return;
      }
      const body = controlBody(holder, {action: "pause", actor, controlId: pauseId});
      const answer = body === null ? UNSENT : await door.control(dialog.run_id, body);
      holder = await door.automation(dialog.run_id);
      fresh = await door.read();
      if (host.state().foreign) return;
      land(fresh);
      const recorded = controlRecorded(holder, pauseId);
      if (!recorded) {
        show({busy: null, dialog: answer.status === "refused" ? null : dialog,
          notice: answer.status === "refused" ? refused(answer.code) : UNCONFIRMED});
        return;
      }
      step = "queue";
    }
    if (step === "queue") {
      const body = resumeBody(holder, {actor, controlId: resumeId,
        expectedControlId: pauseId});
      const answer = body === null ? UNSENT : await door.enqueue(body);
      fresh = await door.read();
      if (host.state().foreign) return;
      land(fresh);
      const queued = skipProgress({holder, queue: fresh, runId: dialog.run_id, pauseId}).queued;
      if (!queued) {
        const note = answer.status === "refused"
          ? Object.freeze({kind: "partial", code: answer.code, run_id: dialog.run_id})
          : UNCONFIRMED;
        show({busy: null, dialog: answer.status === "refused" ? null : dialog, notice: note});
        return;
      }
    }
    show({busy: null, dialog: null, notice: null});
  }

  //: A changed entry asks for a new human confirmation. The preview is read from the server
  //: after opening, and the dialog holds exactly those terms until the person confirms them.
  async function openConfirm(runId) {
    const {queue, actor, foreign} = host.state();
    const entry = queue?.entries.find((row) => row.run_id === runId);
    if (foreign || actor === null || held().busy !== null || held().dialog !== null
        || entry?.state !== "confirmation_required") return;
    const nonce = host.nonce();
    show({busy: "preview", notice: null,
      dialog: Object.freeze({kind: "confirm", run_id: runId, nonce, preview: null,
        resume: entry.kind === "resume" && entry.reason_code !== "grant_expired"})});
    if (held().dialog.resume) {
      show({busy: null});
      return;
    }
    const answer = await door.preview(runId);
    if (host.state().foreign || held().dialog?.nonce !== nonce) return;
    if (answer.status !== "saved" || answer.preview === null) {
      show({busy: null, dialog: null, notice: answer.status === "refused"
        ? refused(answer.code) : UNCONFIRMED});
      return;
    }
    show({busy: null, dialog: Object.freeze({...held().dialog, preview: answer.preview})});
  }

  async function confirm() {
    const {foreign, actor} = host.state();
    const dialog = held().dialog;
    if (foreign || actor === null || held().busy !== null || dialog?.kind !== "confirm"
        || (!dialog.resume && dialog.preview === null)) return;
    const entry = host.state().queue?.entries.find((row) => row.run_id === dialog.run_id);
    if (entry?.state !== "confirmation_required") {
      show({dialog: null});
      return;
    }
    show({busy: "confirm", notice: null});
    const holder = await door.automation(dialog.run_id);
    const body = confirmBody(entry, dialog.preview, holder,
      {actor, authorizationId: `auth-${dialog.nonce}`});
    const answer = body === null ? UNSENT : await door.enqueue(body);
    const fresh = await door.read();
    if (host.state().foreign) return;
    land(fresh);
    const current = fresh?.entries.find((row) => row.run_id === dialog.run_id);
    const expectedDigest = body?.start?.preview_digest ?? body?.resume?.authorization_digest;
    const confirmed = current?.state === "preauthorized"
      && current.preauthorization?.digest === expectedDigest
      && current.preauthorization.authorized_by === actor;
    const readBack = current === undefined && fresh !== null
      ? await door.automation(dialog.run_id) : null;
    const started = body !== null && (body.start !== undefined
      ? readBack?.grant?.authorization_id === body.start.authorization_id
      : readBack?.last_control_id === body.resume.control_id);
    if (host.state().foreign) return;
    if (answer.status === "refused") {
      show({busy: null, dialog: null, notice: refused(answer.code)});
    } else if (fresh !== null && (confirmed || started)) {
      show({busy: null, dialog: null, notice: null});
    } else {
      show({busy: null, dialog: fresh !== null && current === undefined ? null : dialog,
        notice: UNCONFIRMED});
    }
  }

  return Object.freeze({order, withdraw, openRelease, closeDialog, release, openSkip, skip,
    openConfirm, confirm});
}
