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
import {WIZARD_COPY} from "./desk-wizard-copy.js";
import {BUILT_STEPS, LIMITS, RETRYABLE, agentInstructionsRow, assignmentView, availableKinds,
  canAdvance, closeNeedsWarning, cycleCards, cycleFacts, documentPicker, gitReading,
  instructionFields, materialsEstimate, nextStep, preselection, rosterStatus, stepStates,
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
  const openable = built && ["current", "done", "ready", "attention"].includes(row.status);
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

//: The reason a gate gives, said with its step when it is not the one the owner stands on: an
//: earlier step can fail again after it was left, and "this is not complete" must not sound
//: like it is about the screen in front of them.
function gateWords(ctx, gate) {
  const words = ctx.t(`wizard.reason.${gate.reason}`);
  return gate.step === ctx.wizard.step ? words : ctx.t("wizard.reason.earlier",
    {step: ctx.t(`wizard.step.${gate.step}`), reason: words});
}

//: Back is always there past the first step. Next is enabled only while this step and every step
//: before it are complete, and says why when they are not; the last built step offers "prepare"
//: as a control that waits.
function foot(ctx) {
  const wizard = ctx.wizard, gate = canAdvance(wizard), following = nextStep(wizard);
  const why = gate.ok ? "" : gateWords(ctx, gate);
  const back = wizard.step === BUILT_STEPS[0] ? []
    : [action("wizard:back", ctx.t("wizard.back"), () => ctx.send({type: "back"}))];
  const primary = following === null
    ? action("wizard:prepare", ctx.t("wizard.prepare"), () => {}, ctx.t("wizard.later.prepare"))
    : action("wizard:next", ctx.t("wizard.next"), () => ctx.send({type: "next"}),
      gate.ok ? null : why);
  return element("footer", {className: "desk-wizard__foot"}, [
    ...back, primary, element("p", {className: "desk-wizard__reason", "data-wizard-reason": "",
      "aria-live": "polite", text: why})]);
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

// -- step 3: the cycle -------------------------------------------------------------------

const CYCLE_NAMES = Object.freeze({"desk-standard": "standard", "desk-short": "short",
  "desk-starter-docs": "starter_docs"});

//: A UTC instant as the desk writes it until the shared time module arrives: date, minutes, zone.
function instantText(iso) {
  return typeof iso === "string" ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC` : "";
}

//: A duration the server counted, said in hours and minutes. Only the format is drawn here.
function timeText(ctx, seconds) {
  const total = Math.round(seconds / 60), hours = Math.floor(total / 60), minutes = total % 60;
  if (hours > 0 && minutes > 0) {
    return ctx.t("wizard.time.hm", {hours: String(hours), minutes: String(minutes)});
  }
  if (hours > 0) return ctx.t("wizard.time.h", {hours: String(hours)});
  if (minutes > 0) return ctx.t("wizard.time.m", {minutes: String(minutes)});
  return ctx.t("wizard.time.s", {seconds: String(seconds)});
}

//: Where the preselected card came from, said only while the choice is still the preselection. A
//: last run whose cycle is not offered chose nothing, and that is said while nothing is chosen.
function sourceLine(ctx) {
  const cycle = ctx.wizard.cycle, source = preselection(ctx.wizard.reads).source;
  const shown = cycle.chosenBy === "preselection"
    || (cycle.choice === null && source.kind === "last_run_uncarded");
  if (!shown) return [];
  const at = instantText(source.at);
  let text = null;
  if (source.kind === "pinned") {
    text = ctx.t("wizard.cycle.source_pinned", {by: source.by ?? "—", at});
  } else if (source.kind === "last_run") {
    text = source.taskTitle === null ? ctx.t("wizard.cycle.source_last_run_untitled", {at})
      : ctx.t("wizard.cycle.source_last_run", {task: source.taskTitle, at});
  } else if (source.kind === "last_run_uncarded") {
    text = ctx.t("wizard.cycle.source_last_run_other", {workflow: source.workflowId, at});
  }
  return text === null ? [] : [element("p", {"data-cycle-source": source.kind, text})];
}

//: A pinned cycle that could not be read is said to be unread, never to be absent.
function unreadNote(ctx) {
  if (ctx.wizard.mode.starterId !== null || !preselection(ctx.wizard.reads).pinnedUnread) return [];
  return [element("p", {"data-cycle-unread": "", text: ctx.t("wizard.cycle.pinned_unread")})];
}

function cardName(ctx, card) {
  return card.kind === "starter" ? ctx.t(`wizard.cycle.name_${CYCLE_NAMES[card.id]}`)
    : card.title ?? card.id;
}

function cycleCard(ctx, card) {
  const chosen = ctx.wizard.cycle.choice?.workflowId === card.workflowId;
  const small = (text) => element("small", {text});
  const notes = [];
  if (card.pinned) notes.push(small(ctx.t("wizard.cycle.pinned")));
  if (card.kind === "starter" && !card.published) notes.push(small(ctx.t("wizard.cycle.unpublished")));
  if (card.published) notes.push(small(ctx.t("wizard.cycle.revision", {number: String(card.revision)})));
  const pick = action(`wizard:cycle:choose:${card.id}`,
    ctx.t(chosen ? "wizard.cycle.chosen" : "wizard.cycle.choose"),
    () => ctx.send({type: "cycle-choose", id: card.id}));
  pick.setAttribute("aria-pressed", chosen ? "true" : "false");
  const pin = card.canPin ? [later(ctx, "make_project_cycle", `wizard:cycle:pin:${card.id}`,
    ctx.t("wizard.cycle.make_project"))] : [];
  return element("li", {className: "desk-wizard__card", "data-card-id": card.id,
    "data-chosen": chosen ? "true" : "false", "data-pinned": card.pinned ? "true" : "false",
    "data-locked": card.locked ? "true" : null},
  [element("h4", {text: cardName(ctx, card)}), ...notes, ...(card.locked ? [] : [pick, ...pin])]);
}

function cardItems(ctx) {
  return cycleCards(ctx.wizard).map((card) => (card.kind === "build"
    ? element("li", {className: "desk-wizard__card", "data-card-id": "build"},
      [later(ctx, "build_own", "wizard:cycle:build", ctx.t("wizard.cycle.build"))])
    : cycleCard(ctx, card)));
}

//: What the server said about the cycle chosen, or that its answer is not in yet. A lost answer
//: and a moved draft come with "try again", which needs no card and so works when the card is
//: locked and on the roles step.
function flowStatus(ctx, facts) {
  if (ctx.wizard.cycle.choice === null) return [];
  const key = {conflict: "changed", changed_elsewhere: "changed", refused: "refused",
    unknown: "unknown"}[facts.status] ?? (facts.revisions === null ? "pending" : null);
  if (key === null) return [];
  const retry = RETRYABLE.includes(facts.status) ? [action("wizard:cycle:retry",
    ctx.t("wizard.flow.retry"), () => ctx.send({type: "cycle-retry"}))] : [];
  return [element("p", {"data-flow-status": facts.status, text: ctx.t(`wizard.flow.${key}`)}),
    ...retry];
}

//: The conditions exactly as the server counted them; nothing is added or worked out here.
function budgetView(ctx, facts) {
  const budget = facts.budget;
  if (budget === null) return [];
  const {clean, worst, limits} = budget, line = (name, text) => element("p", {[name]: "", text});
  return [element("section", {className: "desk-wizard__budget", "data-budget": ""}, [
    element("h3", {text: ctx.t("wizard.budget.heading")}),
    line("data-budget-clean", ctx.t("wizard.budget.clean", {actions: String(clean.actions),
      time: timeText(ctx, clean.seconds)})),
    line("data-budget-worst", ctx.t("wizard.budget.worst", {actions: String(worst.actions),
      time: timeText(ctx, worst.seconds)})),
    line("data-budget-limit", ctx.t("wizard.budget.limit",
      {actions: String(limits.max_actions)}))])];
}

function addressText(ctx, at) {
  if (at && typeof at.step_id === "string") return ctx.t("wizard.diag.at_step", {step: at.step_id});
  if (at && Array.isArray(at.link)) {
    return ctx.t("wizard.diag.at_link", {from: String(at.link[0]), to: String(at.link[1])});
  }
  return "";
}

function diagnosticRow(ctx, row) {
  const key = `wizard.diag.${row.code}`, where = addressText(ctx, row.at);
  const text = Object.hasOwn(WIZARD_COPY, key) ? ctx.t(key)
    : ctx.t("wizard.diag.unknown", {code: String(row.code)});
  return element("li", {"data-diag": row.code, "data-severity": row.severity}, [
    element("strong", {text: ctx.t(row.severity === "error" ? "wizard.diag.error"
      : "wizard.diag.warning")}), element("span", {text: ` ${text}`}),
    ...(where === "" ? [] : [element("small", {text: ` ${where}`})])]);
}

function diagnosticsView(ctx, facts) {
  if (facts.revisions === null) return [];
  if (facts.diagnostics.length === 0) {
    return [element("p", {"data-diag-none": "", text: ctx.t("wizard.diag.none")})];
  }
  return [element("section", {className: "desk-wizard__diagnostics"}, [
    element("h3", {text: ctx.t("wizard.diag.heading")}),
    element("ul", {}, facts.diagnostics.map((row) => diagnosticRow(ctx, row)))])];
}

function cycleBody(ctx) {
  const facts = cycleFacts(ctx.wizard);
  const locked = ctx.wizard.mode.starterId === null ? []
    : [element("p", {text: ctx.t("wizard.cycle.locked")})];
  return [element("h3", {text: ctx.t("wizard.cycle.heading")}), ...locked, ...sourceLine(ctx),
    ...unreadNote(ctx), element("ul", {className: "desk-wizard__cards"}, cardItems(ctx)),
    ...flowStatus(ctx, facts), ...budgetView(ctx, facts), ...diagnosticsView(ctx, facts)];
}

// -- step 4: roles and instructions ------------------------------------------------------

function roleName(ctx, row) {
  return row.kind === "custom"
    ? ctx.t("wizard.role.custom", {name: row.role_id.replace(/^role-/, "")})
    : ctx.t(`wizard.role.${row.kind}`);
}

//: What is left of a harness's limit, or that it is not known and why. Never a remainder that
//: was not read.
function quotaText(ctx, quota) {
  if (!quota.known) return `${ctx.t("wizard.quota.unknown")} · ${ctx.t(`wizard.quota.${quota.reason}`)}`;
  return quota.kind === "balance" ? ctx.t("wizard.quota.balance")
    : ctx.t("wizard.quota.remaining", {value: String(quota.remaining)});
}

function rolePicker(ctx, row) {
  const pick = element("select", {"data-focus": `wizard:role:${row.role_id}`, name: row.role_id,
    "aria-label": roleName(ctx, row)});
  if (row.provider === null) {
    pick.append(element("option", {value: "", text: ctx.t("wizard.role.unassigned"),
      disabled: ""}));
  }
  for (const offer of row.offers) {
    pick.append(element("option", {value: offer.id,
      text: `${offer.name} · ${quotaText(ctx, offer.quota)}`}));
  }
  pick.value = row.provider ?? "";
  pick.addEventListener("change", () => ctx.send({type: "role-assign", role_id: row.role_id,
    provider_id: pick.value}));
  return pick;
}

function roleRow(ctx, row) {
  const by = row.by === null ? ctx.t("wizard.role.unassigned") : ctx.t(`wizard.role.by_${row.by}`);
  const notes = row.notes.map((code) => element("small", {"data-note": code,
    text: ctx.t(`wizard.note.${code}`)}));
  const clear = row.by === "owner" ? [action(`wizard:role:${row.role_id}:clear`,
    ctx.t("wizard.role.clear"), () => ctx.send({type: "role-assign", role_id: row.role_id,
      provider_id: null}))] : [];
  return element("li", {className: "desk-wizard__role", "data-role": row.role_id,
    "data-by": row.by ?? "none", "data-subject": `role:${row.role_id}`}, [
    element("span", {text: roleName(ctx, row)}), rolePicker(ctx, row),
    element("small", {text: by}), ...notes, ...clear]);
}

function fieldLabel(ctx, field) {
  if (field.kind === "doer") return ctx.t("wizard.instr.field_doer");
  if (field.kind === "tester") return ctx.t("wizard.instr.field_tester");
  return ctx.t("wizard.instr.field_custom", {step: field.title ?? field.step_id});
}

//: The "as step X" chooser, offered only where the model says it may be.
function likePicker(ctx, field) {
  if (field.likeChoices.length === 0 && field.source !== "like") return [];
  const pick = element("select", {"data-focus": `wizard:instr:${field.step_id}:like`,
    "aria-label": ctx.t("wizard.instr.like")}, [
    element("option", {value: "", text: ctx.t("wizard.instr.like_none")}),
    ...field.likeChoices.map((id) => element("option", {value: id, text: id}))]);
  pick.value = field.like ?? "";
  pick.addEventListener("change", () => ctx.send({type: "instruction-like",
    step_id: field.step_id, like: pick.value === "" ? null : pick.value}));
  return [element("label", {}, [element("span", {text: ctx.t("wizard.instr.like")}), pick])];
}

function instructionBody(ctx, field) {
  const label = fieldLabel(ctx, field);
  if (field.source === "own") {
    return [textField(ctx, {key: `wizard:instr:${field.step_id}:text`,
      name: `instruction-${field.step_id}`, multi: true, label, value: field.text,
      onValue: (text) => ctx.send({type: "instruction-edit", step_id: field.step_id, text}),
      extra: [element("small", {text: ctx.t("wizard.instr.required")})]})];
  }
  if (field.source === "like") {
    return [element("p", {text: label}),
      element("p", {"data-like-of": field.like, text: ctx.t("wizard.instr.like_of",
        {step: field.like})}), element("small", {text: ctx.t("wizard.instr.like_cost")})];
  }
  return [element("p", {text: label}), element("p", {"data-instruction-text": "",
    text: field.text}), element("small", {text: ctx.t("wizard.instr.from_task")}),
  action(`wizard:instr:${field.step_id}:apart`, ctx.t("wizard.instr.write_apart"),
    () => ctx.send({type: "instruction-own", step_id: field.step_id, lang: ctx.lang}))];
}

function instructionView(ctx, field) {
  const argv = field.argv === null ? [] : [element("p", {"data-argv": "",
    "data-fits": String(field.argv.fits), text: ctx.t("wizard.instr.argv",
      {chars: String(field.argv.chars), limit: String(LIMITS.argvChars)})})];
  return element("div", {className: "desk-wizard__instruction", "data-instruction": field.step_id,
    "data-subject": `instruction:${field.step_id}`},
  [...instructionBody(ctx, field), ...likePicker(ctx, field), ...argv]);
}

function rolesBody(ctx) {
  const heading = element("h3", {text: ctx.t("wizard.roles.heading")});
  const roster = rosterStatus(ctx.wizard);
  if (roster !== "ready") {
    return [heading, element("p", {[`data-providers-${roster}`]: "",
      text: ctx.t(`wizard.providers.${roster}`)})];
  }
  const facts = cycleFacts(ctx.wizard), fields = instructionFields(ctx.wizard, ctx.lang);
  const none = fields.length === 0
    ? [element("p", {"data-instructions-none": "", text: ctx.t("wizard.instr.none")})] : [];
  return [heading, element("ul", {className: "desk-wizard__roles"},
    assignmentView(ctx.wizard).map((row) => roleRow(ctx, row))),
  element("h3", {text: ctx.t("wizard.roles.instructions")}), ...none,
  ...fields.map((field) => instructionView(ctx, field)),
  ...flowStatus(ctx, facts), ...diagnosticsView(ctx, facts)];
}

// -- the pass ----------------------------------------------------------------------------

//: One body for each built step.
const BODIES = {task: taskBody, materials: materialsBody, cycle: cycleBody, roles: rolesBody};

export function mountWizard(mount, state, handlers) {
  if (typeof handlers?.onWizard !== "function" || typeof handlers.onWizardClose !== "function") {
    throw new Error("the wizard is mounted without its handlers");
  }
  const ctx = context(state, handlers), wizard = ctx.wizard;
  const draw = Object.hasOwn(BODIES, wizard.step) ? BODIES[wizard.step] : () => [];
  mount.replaceChildren(element("section", {className: "desk-wizard", "data-wizard": "",
    "data-wizard-current": wizard.step, "data-mode": modeOf(wizard)}, [
    head(ctx), stepper(ctx),
    element("div", {className: "desk-wizard__body", "data-body": wizard.step}, draw(ctx)),
    foot(ctx), ...closing(ctx)]));
}
