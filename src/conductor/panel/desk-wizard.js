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
import {BUILT_STEPS, LIMITS, agentInstructionsRow, availableKinds, canAdvance,
  closeNeedsWarning, documentPicker, gitReading, materialsEstimate, nextStep, stepStates,
  taskFields} from "./desk-wizard-model.js";

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

//: A choice drawn as a button that says whether it is on (`role` radio or switch), never as an
//: `<input type=radio|checkbox>`: the focus net puts the caret back with `setSelectionRange`,
//: which such an input refuses, so a keyed one would break the redraw that follows its press.
function choice(key, label, role, on, onClick) {
  const node = element("button", {type: "button", role, "data-focus": key, text: label,
    "aria-checked": on ? "true" : "false"});
  node.addEventListener("click", onClick);
  return node;
}

//: A control whose door a later slice opens: drawn disabled, with the reason on screen. Git
//: waits for activation in view, and for a later slice otherwise.
function later(ctx, id, key, label) {
  const reason = id === "connect_git" && ctx.wizard.mode.view ? "connect_git_view" : id;
  return action(key, label, () => {}, ctx.t(`wizard.later.${reason}`));
}

//: A text field the model holds the words of: each input goes to the model as it is typed.
function textField(ctx, spec) {
  const control = element(spec.multi ? "textarea" : "input", {"data-focus": spec.key,
    "data-focus-value": "state", name: spec.name, autocomplete: "off", spellcheck: "false",
    type: spec.multi ? null : "text", rows: spec.multi ? "5" : null,
    disabled: spec.locked ? "" : null});
  control.value = spec.value;
  control.addEventListener("input", () => spec.onValue(control.value));
  return element("label", {className: "desk-wizard__field", "data-field": spec.name},
    [element("span", {text: spec.label}), control, ...(spec.extra ?? [])]);
}

// -- the frame ---------------------------------------------------------------------------

//: Closing with cards that no server holds asks first; with none it just leaves.
function head(ctx) {
  const close = () => (closeNeedsWarning(ctx.wizard) ? ctx.send({type: "close-request"})
    : ctx.leave());
  return element("header", {className: "desk-wizard__head"}, [
    element("h2", {text: ctx.t("wizard.title")}), action("wizard:close", ctx.t("wizard.close"), close)]);
}

function stepRow(ctx, row, at) {
  const label = `${at + 1}. ${ctx.t(`wizard.step.${row.step}`)}`;
  const built = BUILT_STEPS.includes(row.step);
  const openable = built && ["current", "done", "ready"].includes(row.status);
  const note = row.status === "later" ? ctx.t("wizard.step_later")
    : ctx.t(`wizard.step_${row.status === "current" ? "now" : row.status}`);
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

//: The warning shown while the owner has asked to close with materials that are not saved.
function closing(ctx) {
  if (ctx.wizard.closing !== "confirm") return [];
  return [element("div", {className: "desk-wizard__dialog", role: "alertdialog",
    "aria-modal": "true", "data-close-dialog": ""}, [
    element("p", {text: ctx.t("wizard.close.warning")}),
    action("wizard:close:keep", ctx.t("wizard.close.keep"), () => ctx.send({type: "close-cancel"})),
    action("wizard:close:discard", ctx.t("wizard.close.discard"), () => ctx.leave())])];
}

// -- step 1: the task --------------------------------------------------------------------

function taskField(ctx, field) {
  const locked = field === "title" && ctx.wizard.task.written;
  return textField(ctx, {key: `wizard:${field}`, name: field, multi: field !== "title", locked,
    label: ctx.t(`wizard.task.${field}`), value: ctx.wizard.task[field],
    onValue: (value) => ctx.send({type: `edit-${field}`, value}),
    extra: locked ? [element("small", {text: ctx.t("wizard.task.title_locked")})] : []});
}

function taskBody(ctx) {
  return taskFields(ctx.wizard).map((field) => taskField(ctx, field));
}

// -- step 2: where the code comes from ---------------------------------------------------

const COMMANDS = Object.freeze({
  safe_directory: ["git config --global --add safe.directory \"$(pwd)\"",
    "git config --global --add safe.directory (Get-Location).Path"],
  pin_git: ["conduct tools pin git --path …"]});

function gitSentence(ctx, git) {
  const found = git.params;
  const params = git.state === "repo" ? {ref: found.ref ?? "HEAD", commit: found.commit}
    : git.state === "unsupported" ? {names: found.names.join(", ")} : {};
  return ctx.t(`wizard.git.${git.sentence}`, params);
}

function commandBlock(ctx, command) {
  const lead = ctx.t(command === "safe_directory" ? "wizard.git.command_safe"
    : "wizard.git.command_pin");
  return element("div", {"data-git-command": command},
    [element("p", {text: lead}), ...COMMANDS[command].map((line) => element("code", {text: line}))]);
}

function exitButton(ctx, id) {
  const key = `wizard:git:${id}`, label = ctx.t(`wizard.exit.${id}`);
  const node = id === "reread" ? action(key, label, () => ctx.send({type: "reread", name: "git"}))
    : later(ctx, id, key, label);
  return element("span", {"data-git-exit": id}, [node]);
}

function gitPanel(ctx) {
  const git = gitReading(ctx.wizard), dirty = git.params.dirty;
  const parts = [element("h3", {text: ctx.t("wizard.git.heading")}),
    element("p", {className: "desk-wizard__git-sentence", text: gitSentence(ctx, git)})];
  if (git.state === "repo" && typeof dirty === "number" && dirty > 0) {
    parts.push(element("p", {"data-git-dirty": "",
      text: ctx.t("wizard.git.dirty", {count: String(dirty)})}));
  }
  if (git.command !== null) parts.push(commandBlock(ctx, git.command));
  if (git.exits.length > 0) {
    parts.push(element("div", {className: "desk-wizard__exits"},
      git.exits.map((id) => exitButton(ctx, id))));
  }
  return element("section", {className: "desk-wizard__git", "data-git-state": git.state}, parts);
}

//: The project-instructions row, only when files were found (spec 6.2.1).
function instructionsRow(ctx) {
  const row = agentInstructionsRow(ctx.wizard);
  if (row === null) return [];
  const flip = () => ctx.send({type: "include-instructions", value: !row.include});
  return [element("div", {className: "desk-wizard__instructions", "data-instructions": ""}, [
    element("p", {text: ctx.t("wizard.instr.row", {count: String(row.found)})}),
    choice("wizard:include-instructions", ctx.t("wizard.instr.switch"), "switch", row.include,
      flip),
    element("details", {}, [element("summary", {"data-focus": "wizard:instructions-info",
      text: "ⓘ"}), element("p", {text: ctx.t("wizard.instr.info")})])])];
}

// -- step 2: the materials ---------------------------------------------------------------

function addBar(ctx) {
  const buttons = availableKinds(ctx.wizard).map((kind) => action(`wizard:add:${kind}`,
    ctx.t(`wizard.add.${kind}`), () => ctx.send({type: "material-add", kind})));
  buttons.push(later(ctx, "from_starter_docs", "wizard:add:starter_docs",
    ctx.t("wizard.add.starter_docs")));
  return element("div", {className: "desk-wizard__add", role: "group",
    "aria-label": ctx.t("wizard.add.label")}, buttons);
}

function pickerRows(ctx, picker) {
  if (picker.documents.length === 0) return [element("p", {text: ctx.t("wizard.picker.empty")})];
  const rows = picker.documents.map((doc) => element("li", {"data-picker-doc": doc.doc_id}, [
    element("code", {text: doc.path}),
    doc.added ? element("small", {text: ctx.t("wizard.picker.added")})
      : action(`wizard:picker:take:${doc.doc_id}`, ctx.t("wizard.picker.take"),
        () => ctx.send({type: "material-add", kind: "project_doc", docId: doc.doc_id}))]));
  const note = picker.truncated ? [element("p", {text: ctx.t("wizard.picker.truncated")})] : [];
  return [element("ul", {}, rows), ...note];
}

function pickerPanel(ctx) {
  const picker = documentPicker(ctx.wizard);
  if (!picker.open) return [];
  const parts = [element("h3", {text: ctx.t("wizard.picker.heading")})];
  if (picker.status === "reading") parts.push(element("p", {text: ctx.t("wizard.picker.reading")}));
  if (picker.status === "failed") {
    parts.push(element("p", {"data-picker-failed": "", text: ctx.t("wizard.picker.failed")}),
      action("wizard:picker:reread", ctx.t("wizard.exit.reread"),
        () => ctx.send({type: "reread", name: "documents"})));
  }
  if (picker.status === "ready") parts.push(...pickerRows(ctx, picker));
  parts.push(action("wizard:picker:close", ctx.t("wizard.picker.close"),
    () => ctx.send({type: "picker-close"})));
  return [element("section", {className: "desk-wizard__picker", "data-picker": picker.status},
    parts)];
}

function editCard(ctx, card, field, label, multi) {
  return textField(ctx, {key: `wizard:card:${card.key}:${field}`, name: field, multi, label,
    value: card[field], onValue: (value) => ctx.send({type: "material-edit", key: card.key,
      field, value})});
}

function textCardParts(ctx, card) {
  const scheme = card.kind === "scheme";
  return [editCard(ctx, card, "title", ctx.t("wizard.card.title"), false),
    editCard(ctx, card, "content", ctx.t(scheme ? "wizard.card.content_scheme"
      : "wizard.card.content"), true)];
}

function modeRadios(ctx, card) {
  const radios = ["link", "copy"].map((mode) => choice(`wizard:card:${card.key}:mode:${mode}`,
    ctx.t(`wizard.card.mode_${mode}`), "radio", card.mode === mode,
    () => ctx.send({type: "material-mode", key: card.key, mode})));
  return element("div", {role: "radiogroup", "aria-label": ctx.t("wizard.card.mode")}, radios);
}

//: A project document: its path as text, link or copy, and the copy's own text once read.
function docCardParts(ctx, card, estimate) {
  const parts = [element("code", {text: card.path}), modeRadios(ctx, card)];
  if (card.mode === "copy" && card.fetched) {
    parts.push(editCard(ctx, card, "content", ctx.t("wizard.card.content"), true));
  }
  if (card.mode === "copy" && !card.fetched) {
    parts.push(element("p", {text: ctx.t("wizard.card.reading")}));
  }
  if (card.blocked !== null) {
    parts.push(element("p", {"data-blocked-reason": card.blocked,
      text: ctx.t(`wizard.refusal.${card.blocked}`)}));
  }
  if (estimate.overBytes && estimate.linkable.includes(card.key)) {
    parts.push(action(`wizard:card:${card.key}:to-link`, ctx.t("wizard.materials.to_link"),
      () => ctx.send({type: "material-mode", key: card.key, mode: "link"})));
  }
  return parts;
}

function cardView(ctx, card, estimate) {
  const mark = card.source === "starter_docs"
    ? [element("small", {text: ctx.t("wizard.card.from_starter")})] : [];
  const parts = card.kind === "project_doc" ? docCardParts(ctx, card, estimate)
    : textCardParts(ctx, card);
  return element("li", {className: "desk-wizard__card", "data-card": card.key,
    "data-kind": card.kind, "data-subject": `material:${card.key}`}, [
    element("h4", {text: ctx.t(`wizard.card.kind.${card.kind}`)}), ...mark, ...parts,
    action(`wizard:card:${card.key}:remove`, ctx.t("wizard.card.remove"),
      () => ctx.send({type: "material-remove", key: card.key}))]);
}

//: The last refusal, the approximate size, and the hint to make a document a link.
function tally(ctx, estimate) {
  const refusal = ctx.wizard.materials.refusal, out = [];
  if (refusal !== null) {
    out.push(element("p", {role: "alert", "data-refusal": refusal,
      text: ctx.t(`wizard.refusal.${refusal}`)}));
  }
  out.push(element("p", {"data-materials-counter": "", text: ctx.t("wizard.materials.counter",
    {count: String(estimate.count), limit: String(LIMITS.materials),
      kib: (estimate.bytes / 1024).toFixed(1)})}));
  if (estimate.hint === "make_link") {
    out.push(element("p", {"data-hint": "make_link", text: ctx.t("wizard.materials.make_link")}));
  }
  return out;
}

function materialsBody(ctx) {
  const items = ctx.wizard.materials.items, estimate = materialsEstimate(ctx.wizard);
  const cards = items.length === 0
    ? [element("p", {"data-materials-none": "", text: ctx.t("wizard.materials.none")})]
    : [element("ul", {className: "desk-wizard__cards"},
      items.map((card) => cardView(ctx, card, estimate)))];
  return [gitPanel(ctx), ...instructionsRow(ctx),
    element("h3", {text: ctx.t("wizard.materials.heading")}), addBar(ctx), ...pickerPanel(ctx),
    ...cards, ...tally(ctx, estimate)];
}

// -- the pass ----------------------------------------------------------------------------

//: One body for each step the renderer draws so far.
const BODIES = {task: taskBody, materials: materialsBody};

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
    foot(ctx), ...closing(ctx)]));
}
