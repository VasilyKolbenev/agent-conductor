"use strict";
// The pieces every step of the wizard is drawn from: a button with a focus key, a choice drawn as
// a button that says whether it is on, a control whose door a later slice opens, a text field the
// model holds the words of, and the two formats of an instant and of a duration.
//
// They write text nodes and elements only (no markup is ever parsed) and reach nothing but the
// view's element helper and the `ctx` a pass is handed (`ctx.t` says a message, `ctx.wizard` is the
// model's slice). They moved here out of `desk-wizard.js` when steps 5 and 6 would have passed its
// line cap, so that a second drawing module can be built on the same controls.
//
// Every control that takes a key or a click carries a `data-focus` key, so the focus net under
// the host's render pass can hand the caret back to the control that replaced it; text fields
// carry `data-focus-value="state"` because the model, not the DOM, holds what was typed.
import {element} from "./command-view.js";

//: A button with a focus key. A `blocked` reason (already words) disables it and is written on
//: screen beside it, so nothing is a silent no-op.
export function action(key, label, onClick, blocked = null) {
  const node = element("button", {type: "button", "data-focus": key, text: label,
    disabled: blocked === null ? null : "", "aria-disabled": blocked === null ? null : "true"});
  if (blocked === null) node.addEventListener("click", onClick);
  if (blocked === null) return node;
  return element("span", {className: "desk-wizard__blocked", "data-blocked": key},
    [node, element("small", {className: "desk-wizard__why", text: blocked})]);
}

//: A choice drawn as a button that says whether it is on (`role` radio or switch), never as an
//: `<input type=radio|checkbox>`: the focus net puts the caret back with `setSelectionRange`,
//: which such an input refuses, so a keyed one would break the redraw that follows its press.
export function choice(key, label, role, on, onClick) {
  const node = element("button", {type: "button", role, "data-focus": key, text: label,
    "aria-checked": on ? "true" : "false"});
  node.addEventListener("click", onClick);
  return node;
}

//: A control whose door a later slice opens: drawn disabled, with the reason on screen. Git
//: waits for activation in view, and for a later slice otherwise.
export function later(ctx, id, key, label) {
  const reason = id === "connect_git" && ctx.wizard.mode.view ? "connect_git_view" : id;
  return action(key, label, () => {}, ctx.t(`wizard.later.${reason}`));
}

//: A text field the model holds the words of: each input goes to the model as it is typed.
export function textField(ctx, spec) {
  const control = element(spec.multi ? "textarea" : "input", {"data-focus": spec.key,
    "data-focus-value": "state", name: spec.name, autocomplete: "off", spellcheck: "false",
    type: spec.multi ? null : "text", rows: spec.multi ? "5" : null,
    disabled: spec.locked ? "" : null});
  control.value = spec.value;
  control.addEventListener("input", () => spec.onValue(control.value));
  return element("label", {className: "desk-wizard__field", "data-field": spec.name},
    [element("span", {text: spec.label}), control, ...(spec.extra ?? [])]);
}

//: A UTC instant as the desk writes it until the shared time module arrives: date, minutes, zone.
export function instantText(iso) {
  return typeof iso === "string" ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC` : "";
}

//: A duration the server counted, said in hours and minutes. Only the format is drawn here.
export function timeText(ctx, seconds) {
  const total = Math.round(seconds / 60), hours = Math.floor(total / 60), minutes = total % 60;
  if (hours > 0 && minutes > 0) {
    return ctx.t("wizard.time.hm", {hours: String(hours), minutes: String(minutes)});
  }
  if (hours > 0) return ctx.t("wizard.time.h", {hours: String(hours)});
  if (minutes > 0) return ctx.t("wizard.time.m", {minutes: String(minutes)});
  return ctx.t("wizard.time.s", {seconds: String(seconds)});
}
