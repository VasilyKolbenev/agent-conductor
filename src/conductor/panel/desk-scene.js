"use strict";
// The scene: the Trace and the Orbit for the newest run of the task a person chose (spec
// 5.1). It does not draw them itself: the Studio's participant deck is the drawing of one
// frozen run read, with both lenses, the participants, the human gates and the bounded
// returns, and it is reused here rather than copied. This module hands it the run the
// boot module read and says its own sentence when there is nothing to hand.
//
// Nothing is written and nothing is read here. The deck opens no door and asks the host
// for none: its one handler, the button that would open the decisions, stays off until a
// decisions panel exists to open. The word of the live connection is the boot module's to
// say, and goes to the deck as it is: the deck's own rule turns a gate into an attention it
// cannot confirm when that word is `closed`.
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {participantDeck, participantSelection, releaseParticipants,
  restoreParticipantScroll} from "./studio-participants.js";

//: Why a chosen task has no run to show, each with the sentence that says it.
const ABSENT = Object.freeze({none: "desk.scene.no_run", unknown: "desk.scene.unknown_run",
  unreadable: "desk.scene.task_unreadable"});

function note(view, key) {
  return element("p", {className: "desk-scene__note", text: localize(view, key)});
}

//: The task and the run the deck below it draws, so a person is never left to guess.
function subject(view) {
  const task = view.task?.title || localize(view, "desk.rail.unreadable");
  return element("p", {className: "desk-scene__subject", text: localize(view,
    "desk.scene.subject", {task, run: view.run.detail.run.run_id})});
}

//: What stands in the scene when no run is drawn: the reason a chosen task has none, or the
//: invitation to choose one -- made only when the rail has tasks to choose from. A read that
//: was refused or failed draws nothing here, because the top bar says it in the one sentence
//: a person reads.
function nothingToShow(view) {
  if (view.run.absent !== null) return [note(view, ABSENT[view.run.absent])];
  const invite = view.taskId === null && view.listed && view.tasks.list.length > 0;
  return invite ? [note(view, "desk.scene.choose")] : [];
}

//: The terminal state of a desk open for another project (spec 4.5.1): the sentence that
//: says so, and the one way out, a button that reloads the page. Nothing else is drawn.
function foreignPlate(view, handlers) {
  const reload = element("button", {type: "button", className: "desk-scene__reload",
    "data-focus-key": "scene:reload", text: localize(view, "desk.reload")});
  reload.addEventListener("click", () => handlers.reload());
  return [note(view, "desk.foreign"), reload];
}

//: A redraw of the same run keeps the lens, the selection and the scroll a person left it
//: in: the deck reads them off the mount before it is replaced and is handed them back.
export function mountScene(mount, view, handlers) {
  const previous = participantSelection(mount);
  releaseParticipants(mount);
  if (view.foreign) {
    mount.replaceChildren(...foreignPlate(view, handlers));
    return;
  }
  const {phase, detail} = view.run;
  if (phase === "loading") mount.replaceChildren(note(view, "phase.loading"));
  else if (detail !== null) {
    mount.replaceChildren(subject(view),
      participantDeck(detail, previous, {locale: view.locale, connection: view.connection},
        handlers));
  } else mount.replaceChildren(...nothingToShow(view));
  restoreParticipantScroll(mount, previous);
}
