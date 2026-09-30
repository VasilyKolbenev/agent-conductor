"use strict";
// The console of the project (spec 5.1 and 4.4.8): the name of the person at this page, the
// project queue as the server read it, the lines that say a project is in `view`, and, in a desk
// a hub frames, the "Continue after" block of spec 5.8. It draws what the boot module hands it
// and reads nothing: a press is a call to a handler, and no handler here writes to the wire.
// The queue is the read `desk-queue-model.js` already judged (`null` while nobody has read it),
// so a queue that was not read is not drawn as an empty one.
//
// The name is the actor of everything a later write of this page will record in a person's
// name (spec 5.2). It is asked for once and held in the boot module's state, in the page's
// memory: never in storage, in the address or in a request. The boot module owns the rule that
// says what a name may be; the form only asks it and shows the answer, in place, so the words
// typed are never lost to a refusal. The words typed and not yet saved are the boot module's
// too (`view.draft`): every redraw rebuilds the form, and it is drawn from them.
//
// A row of the queue is up to three runs of words -- what the record is, why, and since when --
// each a message of its own; the separators between them are punctuation and belong to no
// language. Times are said by `desk-time.js`, the reasons are the words of `desk-status-copy.js`.
import {element} from "./command-view.js";
import {MESSAGES, localize} from "./studio-i18n.js";
import {instantText} from "./desk-time.js";
import {releaseOffer, skipOffer} from "./desk-queue-model.js";

//: What each state of a queue record says of itself, and the tone that asks for a person.
const LEADS = Object.freeze({preauthorized: "desk.pult.entry_start",
  confirmation_required: "desk.pult.entry_confirm", blocked: "desk.pult.entry_blocked"});
//: What the slot says while a run holds it, or while nobody can.
const SLOTS = Object.freeze({busy: "desk.pult.slot_busy", stuck: "desk.pult.slot_stuck"});

// -- the name of the person -------------------------------------------------------------

function actorRow(view, handlers) {
  const named = view.actor !== null;
  const change = element("button", {type: "button", className: "desk-pult__change",
    "data-focus-key": "pult:actor-change",
    text: localize(view, named ? "desk.pult.actor_change" : "desk.pult.actor_set")});
  change.addEventListener("click", () => handlers.editActor());
  return element("p", {className: "desk-pult__actor"}, [
    element("span", {className: "desk-pult__who", text: named
      ? localize(view, "desk.pult.actor", {name: view.actor})
      : localize(view, "desk.pult.actor_none")}),
    document.createTextNode(" · "), change]);
}

//: The form that asks for the name. A refused name is said in place and the typed words stay
//: where they are; the refusal is the boot module's to remember (`view.refused`), so a redraw
//: says it again until a keystroke or a cancel ends it. The field is drawn from the words typed and not saved (`view.draft`, which
//: every keystroke hands to the boot module), else from the name that stands, else empty: a
//: field the person emptied stays empty, and a redraw that rebuilds the form never takes the
//: words back, whether the field had the keyboard or not.
function actorForm(view, handlers) {
  const input = element("input", {type: "text", name: "actor", maxlength: "128",
    autocomplete: "off", spellcheck: "false", "data-focus-key": "pult:actor-name",
    "aria-describedby": "deskActorHint"});
  input.value = view.draft ?? view.actor ?? "";
  const hint = element("p", {className: "desk-pult__hint", id: "deskActorHint", role: "alert",
    hidden: view.refused === true ? null : "", text: localize(view, "desk.pult.actor_hint")});
  const cancel = element("button", {type: "button", "data-focus-key": "pult:actor-cancel",
    text: localize(view, "desk.pult.actor_cancel")});
  const form = element("form", {className: "desk-pult__form", novalidate: ""}, [
    element("label", {className: "desk-pult__label"},
      [element("span", {text: localize(view, "desk.pult.actor_label")}), input]),
    hint,
    element("div", {className: "desk-pult__buttons"}, [
      element("button", {"data-focus-key": "pult:actor-save",
        text: localize(view, "desk.pult.actor_save")}), cancel])]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const accepted = handlers.setActor(input.value.trim());
    hint.hidden = accepted;
    if (!accepted) input.focus();
  });
  input.addEventListener("input", () => {
    hint.hidden = true;
    handlers.typeActor(input.value);
  });
  cancel.addEventListener("click", () => handlers.cancelActor());
  return form;
}

// -- the project queue ------------------------------------------------------------------

//: The task a run belongs to, by the desk's own lists; the run's own id when they do not say.
function holderName(view, runId) {
  const run = view.runs.list.find((row) => row.run_id === runId);
  const task = run === undefined ? undefined
    : view.tasks.list.find((row) => row.task_id === run.task_id);
  return task !== undefined && !task.unreadable && task.title ? task.title : runId;
}

//: The reason a slot gives for being stopped or unavailable, in the desk's words; a reason the
//: desk has no words for is left unsaid, never shown as the machine's word.
function whyText(view, reason) {
  const key = `desk_pult.why_${reason}`;
  return reason !== null && Object.hasOwn(MESSAGES, key) ? localize(view, key) : null;
}

//: The first row: a project in `view` cannot start anything, so it says so; otherwise the state of
//: the slot, and for a holder that stopped or a slot nobody can use, why.
function firstRow(view) {
  if (view.mode === "view") return localize(view, "desk.pult.inactive");
  const {state, run_id: runId, reason_code: reason} = view.queue.slot;
  if (state === "free") return localize(view, "desk.pult.slot_free");
  const line = Object.hasOwn(SLOTS, state)
    ? localize(view, SLOTS[state], {task: holderName(view, runId)})
    : localize(view, "desk.pult.slot_unavailable");
  const why = state === "busy" ? null : whyText(view, reason);
  return why === null ? line : `${line}: ${why}`;
}

//: "since when" for a record: a wait for a person is dated by the server's `state_since` (none:
//: noticed, and the console has no instant to say it at); a blocked record by its enqueue time.
function tail(view, entry) {
  if (entry.state === "confirmation_required") {
    const at = entry.state_since === null ? null : instantText(view.locale, entry.state_since);
    return at !== null && at.known
      ? localize(view, "desk_status.since_waiting", {time: at.short})
      : localize(view, "desk_status.since_observed_unknown");
  }
  const queued = entry.state === "blocked" ? instantText(view.locale, entry.enqueued_at) : null;
  return queued !== null && queued.known
    ? localize(view, "desk.pult.entry_queued", {time: queued.short}) : null;
}

//: One control of an entry. A press is a call to the boot module's handler; while a write is out
//: (`view.pult.busy`) no control of the block can be pressed, and a step the entry cannot take
//: (up at the head, down at the tail) is not offered. Such a control says it is unavailable
//: (`aria-disabled`) and does nothing, and is NOT `disabled`: a control that is disabled cannot
//: hold the keyboard, and the press that put the write out must not lose its place in the redraw.
function control(view, {key, glyph, words, off, press}) {
  const button = element("button", {type: "button", "data-focus-key": key,
    "aria-label": localize(view, words), text: glyph ?? localize(view, words)});
  if (off || view.pult?.busy) {
    button.setAttribute("aria-disabled", "true");
    button.classList.add("desk-queue__off");
  } else button.addEventListener("click", press);
  return button;
}

//: The controls of an entry: a step up, a step down, and "Remove from the queue".
function actions(view, handlers, entry) {
  const last = view.queue.entries.length;
  const id = entry.run_id;
  const buttons = [
    control(view, {key: `queue:up:${id}`, glyph: "↑", words: "desk_pult.up",
      off: entry.position === 1, press: () => handlers.orderEntry(id, -1)}),
    control(view, {key: `queue:down:${id}`, glyph: "↓", words: "desk_pult.down",
      off: entry.position === last, press: () => handlers.orderEntry(id, 1)}),
    control(view, {key: `queue:withdraw:${id}`, glyph: null, words: "desk_pult.withdraw",
      off: false, press: () => handlers.withdrawEntry(id)})];
  if (entry.state === "confirmation_required") {
    buttons.push(control(view, {key: `queue:confirm:${id}`, glyph: null,
      words: "desk_pult.confirm", off: view.actor === null,
      press: () => handlers.openConfirm(id)}));
  }
  return element("div", {className: "desk-queue__acts"}, buttons);
}

function entryRow(view, handlers, entry) {
  const title = entry.title === "" ? entry.run_id : entry.title;
  const said = [localize(view, LEADS[entry.state], {position: String(entry.position), title})];
  if (entry.state !== "preauthorized" && entry.reason_code !== null) {
    said.push(": ", localize(view, `desk_status.entry_${entry.reason_code}`));
  }
  const since = tail(view, entry);
  if (since !== null) said.push(" · ", since);
  const nameHint = entry.state === "confirmation_required" && view.actor === null
    ? [element("span", {className: "desk-queue__hint",
      text: localize(view, "desk_pult.confirm_need_name")})] : [];
  const dialog = view.pult?.dialog;
  const card = dialog?.kind === "confirm" && dialog.run_id === entry.run_id
    ? [confirmDialog(view, handlers, entry, dialog)] : [];
  return element("li", {className: "desk-queue__entry", "data-run-id": entry.run_id,
    "data-queue-state": entry.state,
    "data-tone": entry.state === "confirmation_required" ? "amber" : null},
  [...said.map((part) => element("span", {text: part})), actions(view, handlers, entry),
    ...nameHint, ...card]);
}

function confirmDialog(view, handlers, entry, dialog) {
  const terms = dialog.preview;
  const lines = terms === null ? [] : [
    ["desk_pult.confirm_actions", {count: String(terms.max_actions)}],
    ["desk_pult.confirm_time", {seconds: String(terms.max_total_task_seconds)}],
    ["desk_pult.confirm_window", {seconds: String(terms.duration_seconds)}]]
    .map(([key, args]) => element("p", {text: localize(view, key, args)}));
  return element("div", {className: "desk-queue__dialog", role: "group",
    "data-pult-dialog": "confirm"}, [
    element("p", {className: "desk-queue__dialog-head", text: localize(view,
      "desk_pult.confirm")}),
    element("p", {text: localize(view, "desk_pult.confirm_text", {task: entry.title})}),
    ...lines,
    control(view, {key: `queue:confirm:accept:${entry.run_id}`, glyph: null,
      words: "desk_pult.confirm_press", off: terms === null,
      press: () => handlers.confirm()}),
    control(view, {key: `queue:confirm:cancel:${entry.run_id}`, glyph: null,
      words: "desk_pult.cancel", off: false, press: () => handlers.closeDialog()})]);
}

function entryList(view, handlers) {
  const {entries} = view.queue;
  return entries.length === 0
    ? element("p", {className: "desk-queue__none", text: localize(view, "desk.pult.queue_empty")})
    : element("ul", {className: "desk-queue__list"},
      entries.map((entry) => entryRow(view, handlers, entry)));
}

//: What the last write left under the block: a refusal in the words of its code, or that a change
//: could not be confirmed. Nothing is drawn when the last write left nothing to say.
function noticeLine(view) {
  const notice = view.pult?.notice ?? null;
  if (notice === null) return [];
  let key = "desk_pult.unconfirmed";
  let text = null;
  if (notice.kind === "refused") {
    const code = `error.${notice.code}`;
    key = Object.hasOwn(MESSAGES, code) ? code : "error.store_error";
  } else if (notice.kind === "partial") {
    const code = `error.${notice.code}`;
    const reason = localize(view, Object.hasOwn(MESSAGES, code) ? code : "error.store_error");
    text = localize(view, "desk_pult.skip_partial", {
      task: holderName(view, notice.run_id), reason});
  }
  return [element("p", {className: "desk-queue__notice", role: "status",
    "data-pult-notice": "", text: text ?? localize(view, key)})];
}

//: One choice of a dialog: the button, and what it does said under it.
function choice(view, {key, words, note, press}) {
  return element("div", {className: "desk-queue__choice"}, [
    control(view, {key, glyph: null, words, off: false, press}),
    element("p", {className: "desk-queue__note", text: localize(view, note)})]);
}

//: The dialog of freeing the slot: two choices, equal, none of them taken for the person. A run
//: that needs a correction the desk cannot make says so before the choices.
function releaseDialog(view, handlers, offer) {
  const feedback = offer.reason === "feedback_required"
    ? [element("p", {className: "desk-queue__note", text: localize(view, "desk_pult.release_feedback")})]
    : [];
  return element("div", {className: "desk-queue__dialog", role: "group",
    "aria-labelledby": "deskReleaseHead", "data-pult-dialog": "release"}, [
    element("p", {className: "desk-queue__dialog-head", id: "deskReleaseHead",
      text: localize(view, "desk_pult.release")}),
    element("p", {text: localize(view, "desk_pult.release_text",
      {task: holderName(view, offer.run_id)})}),
    ...feedback,
    choice(view, {key: "queue:release:pause", words: "desk_pult.release_pause",
      note: "desk_pult.release_pause_note", press: () => handlers.release("pause")}),
    choice(view, {key: "queue:release:revoke", words: "desk_pult.release_revoke",
      note: "desk_pult.release_revoke_note", press: () => handlers.release("revoke")}),
    element("div", {className: "desk-queue__acts"}, [control(view, {key: "queue:release:cancel",
      glyph: null, words: "desk_pult.cancel", off: false, press: () => handlers.closeDialog()})])]);
}

function skipDialog(view, handlers, offer) {
  const dialog = view.pult.dialog;
  const when = dialog.expires_at === null ? null : instantText(view.locale, dialog.expires_at);
  const windowLine = when === null || !when.known ? [] : [element("p", {text: localize(view,
    "desk_pult.skip_window", {time: when.short})})];
  return element("div", {className: "desk-queue__dialog", role: "group",
    "aria-labelledby": "deskSkipHead", "data-pult-dialog": "skip"}, [
    element("p", {className: "desk-queue__dialog-head", id: "deskSkipHead",
      text: localize(view, "desk_pult.skip")}),
    element("p", {text: localize(view, "desk_pult.skip_text",
      {task: holderName(view, offer.run_id)})}),
    ...windowLine,
    control(view, {key: "queue:skip:confirm", glyph: null, words: "desk_pult.skip_confirm",
      off: when === null, press: () => handlers.skip()}),
    control(view, {key: "queue:skip:cancel", glyph: null, words: "desk_pult.cancel",
      off: false, press: () => handlers.closeDialog()})]);
}

//: What the console offers for a holder that stopped: "Free the slot" once a name is given (or the
//: sentence that says a name is needed), and the dialog it opens.
function slotActions(view, handlers) {
  const dialog = view.pult?.dialog ?? null;
  if (dialog?.kind === "skip" && view.queue.slot.run_id !== dialog.run_id) {
    return [skipDialog(view, handlers, {run_id: dialog.run_id})];
  }
  const offer = releaseOffer(view.queue, view) ?? skipOffer(view.queue, view);
  if (offer === null) return [];
  const skip = skipOffer(view.queue, view) !== null;
  if (!offer.named) {
    return [element("p", {className: "desk-queue__hint", "data-pult-slot-hint": "",
      text: localize(view, skip ? "desk_pult.skip_need_name" : "desk_pult.release_need_name")})];
  }
  const kind = skip ? "skip" : "release";
  const open = dialog !== null && dialog.kind === kind && dialog.run_id === offer.run_id;
  const button = control(view, {key: `queue:${kind}`, glyph: null, words: `desk_pult.${kind}`,
    off: false, press: () => skip ? handlers.openSkip() : handlers.openRelease()});
  button.setAttribute("aria-expanded", String(open));
  return [element("div", {className: "desk-queue__acts"}, [button]),
    ...(open ? [skip ? skipDialog(view, handlers, offer) : releaseDialog(view, handlers, offer)]
      : [])];
}

//: The block is drawn when the queue was read, and in `view` even when it was not: the mode is
//: the server's word, and it says the project cannot start what the queue holds.
function queueBlock(view, handlers) {
  if (view.queue === null && view.mode !== "view") return [];
  const kids = [
    element("h3", {className: "desk-queue__head", text: localize(view, "desk.pult.queue")}),
    element("p", {className: "desk-queue__now", text: firstRow(view)})];
  if (view.queue !== null) {
    kids.push(...slotActions(view, handlers), entryList(view, handlers), ...noticeLine(view));
  }
  if (view.mode === "view") {
    kids.push(element("p", {className: "desk-pult__flag", text: localize(view, "desk.pult.flag")}));
  }
  return [element("section", {className: "desk-queue"}, kids)];
}

// -- the "continue after" block ---------------------------------------------------------

//: A checkbox that says its words and, on a change, hands the boot module what changed. It
//: redraws nothing: the control already shows it, and the boot module keeps it in its state.
function check(view, handlers, {key, label, on, change}) {
  const box = element("input", {type: "checkbox", "data-focus-key": key});
  box.checked = on;
  box.addEventListener("change", () => {
    handlers.draftFlag(change(box.checked));
    view.hint.hidden = true;
  });
  return element("label", {className: "desk-flag__check"}, [box,
    element("span", {"data-flag-title": "", text: label})]);
}

//: A run the flag may continue has a mark; a run whose grant expired has none, and says why.
function runRow(view, handlers, row) {
  if (row.expired) {
    return element("li", {"data-run-id": row.run_id, "data-expired": ""}, [
      element("span", {"data-flag-title": "", text: row.title}),
      element("span", {className: "desk-flag__note", "data-flag-note": "",
        text: localize(view, "desk.flag.expired")})]);
  }
  return element("li", {"data-run-id": row.run_id}, [check(view, handlers, {
    key: `flag:run:${row.run_id}`, label: row.title, on: view.flag.form.marked.includes(row.run_id),
    change: (on) => ({run: row.run_id, on})})]);
}

function runList(view, handlers) {
  const {rows} = view.flag;
  if (rows.length === 0) {
    return element("p", {className: "desk-flag__note",
      text: localize(view, "desk.flag.runs_none")});
  }
  return element("fieldset", {className: "desk-flag__runs"}, [
    element("legend", {text: localize(view, "desk.flag.runs")}),
    element("ul", {}, rows.map((row) => runRow(view, handlers, row)))]);
}

//: The one line that says what the flag is: it stands since a time, or an activation spent it.
function lineOfFlag(view) {
  const {line} = view.flag;
  if (line.kind === "none") return [];
  const words = localize(view, line.kind === "standing" ? "desk.flag.standing"
    : "desk.flag.consumed", {time: instantText(view.locale, line.at).short, actor: line.actor});
  return [element("p", {className: "desk-flag__line", "data-flag-line": "", text: words})];
}

//: A run the consumed flag listed that changed after it, said once: the flag was not applied to
//: it (spec 5.8). A run the flag continued or one that waits says nothing, and a run whose
//: automation was not read is never said to have changed.
function verdictLines(view) {
  const changed = view.flag.verdicts.filter((row) => row.verdict === "changed");
  if (changed.length === 0) return [];
  return [element("ul", {className: "desk-flag__verdicts"}, changed.map((row) =>
    element("li", {"data-verdict-run": row.run_id, "data-flag-verdict": row.verdict}, [
      element("span", {"data-flag-title": "", text: holderName(view, row.run_id)}),
      element("span", {className: "desk-flag__note", "data-flag-note": "",
        text: localize(view, "desk.flag.changed")})])))];
}

//: A refusal, or an unconfirmed save, said in place: the catalogue's words for the code.
function hintText(view) {
  const {refused} = view.flag;
  if (refused === null) return "";
  if (refused === "unknown") return localize(view, "desk.flag.unknown");
  const key = `error.${refused}`;
  return localize(view, Object.hasOwn(MESSAGES, key) ? key : "error.store_error");
}

function flagButtons(view, handlers) {
  const blocked = view.actor === null || view.flag.saving;
  const save = element("button", {type: "button", "data-focus-key": "flag:save",
    text: localize(view, "desk.flag.save")});
  const clear = element("button", {type: "button", "data-focus-key": "flag:clear",
    text: localize(view, "desk.flag.clear")});
  for (const button of [save, clear]) if (blocked) button.setAttribute("disabled", "");
  save.addEventListener("click", () => handlers.saveFlag());
  clear.addEventListener("click", () => handlers.clearFlag());
  return element("div", {className: "desk-pult__buttons"}, [save, clear]);
}

//: The block, closed until a person (or the address) opens it. Only a desk a hub frames has one,
//: and only once the flag has been read as a record the desk can vouch for.
function flagBlock(view, handlers) {
  const {flag = null} = view;
  if (flag === null) return [];
  const hint = element("p", {className: "desk-pult__hint", role: "alert", "data-flag-hint": "",
    text: view.actor === null ? localize(view, "desk.flag.need_name") : hintText(view)});
  hint.hidden = view.actor !== null && flag.refused === null;
  const shown = {...view, hint};
  const details = element("details", {className: "desk-flag", open: flag.open ? "" : null}, [
    element("summary", {className: "desk-flag__head", "data-focus-key": "flag:summary",
      text: localize(view, "desk.flag.head")}),
    check(shown, handlers, {key: "flag:enabled", label: localize(view, "desk.flag.switch"),
      on: flag.form.enabled, change: (enabled) => ({enabled})}),
    runList(shown, handlers),
    check(shown, handlers, {key: "flag:queue", label: localize(view, "desk.flag.queue"),
      on: flag.form.queue, change: (queue) => ({queue})}),
    element("p", {className: "desk-flag__note", text: localize(view, "desk.flag.queue_note")}),
    ...lineOfFlag(view), ...verdictLines(view), hint, flagButtons(view, handlers),
    element("details", {className: "desk-flag__info"}, [
      element("summary", {"data-focus-key": "flag:info", "aria-label": localize(view,
        "desk.flag.info"), text: "ⓘ"}),
      element("p", {className: "desk-flag__note", text: localize(view, "desk.flag.help")})])]);
  details.addEventListener("toggle", () => handlers.openFlag(details.open));
  return [details];
}

//: A desk open for another project draws nothing here: it holds no name and shows no queue.
export function mountPult(mount, view, handlers) {
  if (view.foreign) {
    mount.replaceChildren();
    return;
  }
  mount.replaceChildren(
    element("h2", {className: "desk-pult__head", text: localize(view, "desk.pult.label")}),
    view.editing ? actorForm(view, handlers) : actorRow(view, handlers),
    ...queueBlock(view, handlers), ...flagBlock(view, handlers));
}
