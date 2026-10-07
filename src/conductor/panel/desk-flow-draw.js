"use strict";
// The pieces every part of the «Схема» is drawn from: the context a pass is handed, a button with a
// focus key, the names of steps and road words in the reader's language, and the text control whose
// words the model holds until they are committed.
//
// They write text nodes and elements only (no markup is ever parsed) and reach nothing but the view's
// element helper and the catalogue. Every control that takes a key or a click carries a `data-focus`
// key, so the focus net under the host's render pass can hand the caret back to the control that
// replaced it; text fields carry `data-focus-value="state"` because the model, not the DOM, holds what
// was typed.
//
// Leaving a field commits it, and that is the one thing a redraw makes hard: a pass replaces the field
// that has focus, and the browser then tells the old field it lost focus while it is still in the
// page. So a leave is a leave only if the field is still in the page a moment later; and a press of
// the pointer that took focus away is let finish first, because a redraw between its press and its
// release would swallow the click it was making.
import {element} from "./command-view.js";
import {MESSAGES, localize} from "./studio-i18n.js";
import {flowView} from "./desk-flow-model.js";
import {kindOfRole} from "./desk-flow-shape.js";

/** What one pass carries: the model's facts, the words in the reader's language, the one way out. */
export function context(state, handlers) {
  return {state, view: flowView(state.schema),
    t: (key, params) => localize(state, key, params),
    send: (event) => handlers.onFlow(event)};
}

/** A message that may not exist (a word the server added): its own text stands in for it. */
export function knownText(ctx, key, fallback, params) {
  return Object.hasOwn(MESSAGES, key) ? ctx.t(key, params) : String(fallback);
}

/** A button with a focus key; a blocked reason (already words) disables it and is written beside it. */
export function action(key, label, onClick, blocked = null) {
  const node = element("button", {type: "button", "data-focus": key, text: label,
    disabled: blocked === null ? null : "", "aria-disabled": blocked === null ? null : "true"});
  if (blocked === null) node.addEventListener("click", onClick);
  if (blocked === null) return node;
  return element("span", {className: "desk-flow__blocked", "data-blocked": key},
    [node, element("small", {className: "desk-flow__why", text: blocked})]);
}

/** What a step is called: its own title, else the name of its kind (a custom role by its name). */
export function stepName(ctx, step) {
  if (typeof step.title === "string" && step.title !== "") return step.title;
  if (step.type === "human") return ctx.t("schema.kind.decision");
  if (step.type === "route") return ctx.t("schema.kind.route");
  if (step.type === "loop") return ctx.t("schema.kind.loop");
  const kind = kindOfRole(step.role_id);
  if (kind !== null) return ctx.t(`wizard.role.${kind}`);
  return ctx.t("wizard.role.custom", {name: String(step.role_id).replace(/^role-/, "")});
}

/** The name of a step told by its id, with the id beside it when the names would be alike. */
export function stepLabel(ctx, id) {
  const step = ctx.view.flow?.steps.find((one) => one.step_id === id);
  return step === undefined ? id : `${stepName(ctx, step)} (${id})`;
}

/** The word of a road, in the reader's language (a word the catalogue lacks stands as it is). */
export function whenWord(ctx, word) {
  return knownText(ctx, `schema.when.${word}`, word);
}

// -- leaving a field ---------------------------------------------------------------------

let pointerDown = false;
let pending = null;
let watching = false;

//: The commit a press took a field's focus for, run once the press has done its work.
function flushPending() {
  const run = pending;
  pending = null;
  if (run !== null) run();
}

function watchPointer() {
  if (watching) return;
  watching = true;
  document.addEventListener("pointerdown", () => {
    flushPending();
    pointerDown = true;
  }, true);
  document.addEventListener("pointerup", () => { pointerDown = false; }, true);
  document.addEventListener("pointercancel", () => { pointerDown = false; }, true);
  //: After the pressed control's own handlers (this is the bubbling phase), or at the next gesture.
  document.addEventListener("click", flushPending);
  document.addEventListener("keydown", flushPending, true);
}

/** Run `commit` when the person leaves `control`; never because a redraw replaced it. */
export function commitOnLeave(control, commit) {
  watchPointer();
  control.addEventListener("blur", () => Promise.resolve().then(() => {
    if (!control.isConnected) return;
    if (!pointerDown) {
      commit();
      return;
    }
    flushPending();
    pending = commit;
  }));
}

/**
 * A text control whose words the model holds: each input goes to `onInput`, leaving it (or Enter, in
 * a single line) goes to `onCommit`. `spec`: `{key, name, multi, rows, value, onInput, onCommit}`.
 */
export function textControl(spec) {
  const control = element(spec.multi ? "textarea" : "input", {"data-focus": spec.key,
    "data-focus-value": "state", name: spec.name, autocomplete: "off", spellcheck: "false",
    type: spec.multi ? null : "text", rows: spec.multi ? String(spec.rows ?? 3) : null});
  control.value = spec.value;
  control.addEventListener("input", () => spec.onInput(control.value));
  commitOnLeave(control, () => spec.onCommit(control.value));
  if (!spec.multi) {
    control.addEventListener("keydown", (event) => {
      if (event.key === "Enter") spec.onCommit(control.value);
    });
  }
  return control;
}
