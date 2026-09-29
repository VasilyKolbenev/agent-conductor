"use strict";
// The new-task wizard, drawn: `mountWizard(mount, state, handlers)` and nothing else exported.
//
// It writes text nodes only (no markup is ever parsed), one `replaceChildren` per pass, and reads
// nothing but the state it is given: `state.wizard` is the model's slice and `state.locale` the
// language. It touches no wire, no storage and no clock. Every edit goes out as one event of the
// model's closed table through `handlers.onWizard`, and leaving goes through
// `handlers.onWizardClose`; what the wizard wants from a server is the model's business (an ask it
// returns), and the host that owns the doors performs it. A control whose door a later slice opens
// is drawn disabled with its reason on screen, never as a button that does nothing.
//
// Every control that takes a key or a click carries a `data-focus` key, so the focus net under
// the host's render pass can hand the caret back to the control that replaced it; text fields
// carry `data-focus-value="state"` because the model, not the DOM, holds what was typed.
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {BUILT_STEPS, canAdvance, nextStep, stepStates, taskFields}
  from "./desk-wizard-model.js";

function modeOf(wizard) {
  if (wizard.mode.starterId !== null) return "starter";
  return wizard.mode.view ? "view" : "normal";
}

//: What one pass carries: the model's slice, the words in the reader's language, and the two ways
//: out. `lang` is the language a document the wizard writes is composed in.
function context(state, handlers) {
  return {wizard: state.wizard, lang: state.locale === "ru" ? "ru" : "en",
    t: (key, params) => localize(state, key, params),
    send: (event) => handlers.onWizard(event), leave: () => handlers.onWizardClose()};
}

//: A button with a focus key. A `blocked` reason (already words) disables it and is written on
//: screen beside it, so nothing is a silent no-op.
function action(key, label, onClick, blocked = null) {
  const node = element("button", {type: "button", "data-focus": key, text: label,
    disabled: blocked === null ? null : "", "aria-disabled": blocked === null ? null : "true"});
  if (blocked === null) node.addEventListener("click", onClick);
  if (blocked === null) return node;
  return element("span", {className: "desk-wizard__blocked", "data-blocked": key},
    [node, element("small", {className: "desk-wizard__why", text: blocked})]);
}

// -- the frame ---------------------------------------------------------------------------

function head(ctx) {
  return element("header", {className: "desk-wizard__head"}, [
    element("h2", {text: ctx.t("wizard.title")}),
    action("wizard:close", ctx.t("wizard.close"), () => ctx.leave())]);
}

function stepRow(ctx, row, at) {
  const label = `${at + 1}. ${ctx.t(`wizard.step.${row.step}`)}`;
  const built = BUILT_STEPS.includes(row.step);
  const openable = built && ["current", "done", "ready"].includes(row.status);
  const note = row.status === "later" ? ctx.t("wizard.step_later")
    : ctx.t(`wizard.step_${row.status === "blocked" ? "blocked" : row.status === "current"
      ? "now" : row.status}`);
  const why = row.status === "blocked" && row.reason !== null
    ? ctx.t(`wizard.reason.${row.reason}`) : null;
  const control = openable
    ? action(`wizard:step:${row.step}`, label, () => ctx.send({type: "goto", step: row.step}))
    : element("span", {className: "desk-wizard__step-name", text: label, title: why});
  return element("li", {"data-wizard-step": row.step, "data-status": row.status,
    "aria-current": row.status === "current" ? "step" : null},
  [control, element("small", {className: "desk-wizard__step-note", text: note})]);
}

function stepper(ctx) {
  return element("ol", {className: "desk-wizard__steps", "aria-label": ctx.t("wizard.steps_label")},
    stepStates(ctx.wizard).map((row, at) => stepRow(ctx, row, at)));
}

//: Back is always there past the first step. Next is enabled only while the step is complete, and
//: says why when it is not; the last built step offers "prepare" as a control that waits.
function foot(ctx) {
  const wizard = ctx.wizard, gate = canAdvance(wizard), following = nextStep(wizard);
  const why = gate.ok ? "" : ctx.t(`wizard.reason.${gate.reason}`);
  const back = wizard.step === BUILT_STEPS[0] ? []
    : [action("wizard:back", ctx.t("wizard.back"), () => ctx.send({type: "back"}))];
  const primary = following === null
    ? action("wizard:prepare", ctx.t("wizard.prepare"), () => {}, ctx.t("wizard.later.prepare"))
    : action("wizard:next", ctx.t("wizard.next"), () => ctx.send({type: "next"}),
      gate.ok ? null : why);
  return element("footer", {className: "desk-wizard__foot"}, [
    ...back, primary, element("p", {className: "desk-wizard__reason", "data-wizard-reason": "",
      "aria-live": "polite", text: following === null ? "" : why})]);
}

// -- step 1: the task --------------------------------------------------------------------

function taskField(ctx, field) {
  const wizard = ctx.wizard, multi = field !== "title";
  const control = element(multi ? "textarea" : "input", {"data-focus": `wizard:${field}`,
    "data-focus-value": "state", name: field, autocomplete: "off", spellcheck: "false",
    type: multi ? null : "text", rows: multi ? "5" : null,
    disabled: field === "title" && wizard.task.written ? "" : null});
  control.value = wizard.task[field];
  control.addEventListener("input", () => ctx.send({type: `edit-${field}`, value: control.value}));
  const locked = field === "title" && wizard.task.written
    ? [element("small", {text: ctx.t("wizard.task.title_locked")})] : [];
  return element("label", {className: "desk-wizard__field", "data-field": field},
    [element("span", {text: ctx.t(`wizard.task.${field}`)}), control, ...locked]);
}

function taskBody(ctx) {
  return taskFields(ctx.wizard).map((field) => taskField(ctx, field));
}

// -- the pass ----------------------------------------------------------------------------

//: One body for each step the renderer draws so far.
const BODIES = {task: taskBody};

export function mountWizard(mount, state, handlers) {
  if (typeof handlers?.onWizard !== "function" || typeof handlers.onWizardClose !== "function") {
    throw new Error("the wizard is mounted without its handlers");
  }
  const ctx = context(state, handlers), wizard = ctx.wizard;
  const draw = Object.hasOwn(BODIES, wizard.step) ? BODIES[wizard.step] : () => [];
  mount.replaceChildren(element("section", {className: "desk-wizard", "data-wizard": "",
    "data-step": wizard.step, "data-mode": modeOf(wizard)}, [
    head(ctx), stepper(ctx),
    element("div", {className: "desk-wizard__body", "data-body": wizard.step}, draw(ctx)),
    foot(ctx)]));
}
