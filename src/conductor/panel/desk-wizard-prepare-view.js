"use strict";
// Step 5, «Подготовка», drawn: the six links of the chain with where each stands, what may be
// pressed, what went wrong, and what a reloaded page found.
//
// It draws what `prepareFacts` says and nothing it works out itself: a link is done only when the
// model says so, a lost answer is said to be lost, and a button whose gate is closed is disabled
// with the reason on screen. Every press is one event of the model's closed table handed to the
// host through `ctx.send`; leaving to open a run goes through `ctx.leave`.
import {element} from "./command-view.js";
import {action, textField} from "./desk-wizard-draw.js";
import {prepareFacts} from "./desk-wizard-model.js";

//: The refusals that have a sentence of their own; any other is said by its code.
const SENTENCES = Object.freeze({record_conflict: "wizard.chain.conflict_run",
  draft_conflict: "wizard.flow.changed"});

function linkRow(ctx, row, at) {
  return element("li", {"data-link": row.link, "data-status": row.status}, [
    element("span", {text: `${at + 1}. ${ctx.t(`wizard.chain.link.${row.link}`)}`}),
    element("small", {text: ctx.t(`wizard.chain.status.${row.status}`)})]);
}

function refusalNote(ctx, refusal) {
  const code = refusal.reason === null ? refusal.code : `${refusal.code} · ${refusal.reason}`;
  const key = Object.hasOwn(SENTENCES, refusal.code) ? SENTENCES[refusal.code]
    : "wizard.chain.refused";
  return element("p", {"data-refusal-link": refusal.link, role: "alert",
    text: ctx.t(key, key === "wizard.chain.refused" ? {code} : {})});
}

//: The buttons a refusal offers: a clash of runs asks which run to keep, anything else may be tried
//: again. A read that failed is asked again by the owner and never on its own.
function refusalActions(ctx, facts) {
  if (facts.phase === "refused" && facts.refusal.code === "record_conflict") {
    return [action("wizard:prepare:adopt", ctx.t("wizard.chain.adopt"),
      () => ctx.send({type: "prepare-adopt"})),
    action("wizard:prepare:bump", ctx.t("wizard.chain.bump", {number: String(facts.following)}),
      () => ctx.send({type: "prepare-bump"}))];
  }
  const again = facts.phase === "refused" || (facts.phase === "unknown"
    && facts.readFailed !== null);
  return again ? [action("wizard:prepare:retry", ctx.t("wizard.chain.retry"),
    () => ctx.send({type: "prepare-retry"}))] : [];
}

function chainNote(ctx, facts) {
  if (facts.phase !== "unknown") return [];
  const failed = facts.readFailed;
  return [element("p", {"data-chain-note": "", text: failed === null
    ? ctx.t("wizard.chain.unknown") : ctx.t("wizard.chain.read_failed", {code: failed.code})})];
}

//: The button that begins the chain, or begins it again after edits made past a preview. On a
//: reloaded page it reads «Продолжить подготовку» and only where the read says there is more.
function startButton(ctx, facts) {
  const resumed = facts.resume !== null;
  const offered = resumed ? ["documents", "preview"].includes(facts.resume.kind)
    : !facts.pressed || (facts.phase === "review" && !facts.prepared);
  if (!offered || (resumed && facts.pressed)) return [];
  const words = facts.gate.ok ? null : ctx.t(`wizard.reason.${facts.gate.reason}`);
  return [action("wizard:prepare:go", ctx.t(resumed ? "wizard.prepare.continue"
    : "wizard.prepare"), () => ctx.send({type: "prepare-start", lang: ctx.lang}), words)];
}

// -- a reloaded page -----------------------------------------------------------------------

const TASK_FIELDS = Object.freeze({brief: "wizard.task.brief", hint: "wizard.task.hint",
  idea: "wizard.task.idea"});

function fieldLabel(ctx, field) {
  if (Object.hasOwn(TASK_FIELDS, field.name)) return ctx.t(TASK_FIELDS[field.name]);
  if (field.name === "materials") return ctx.t("wizard.resume.materials");
  return ctx.t("wizard.instr.field_custom", {step: field.name.replace(/^instruction:/, "")});
}

//: One field of a missing document. The task's own words go through the task's events, the rest
//: through `resume-edit`; the model holds every value, so a redraw never loses one.
function resumeField(ctx, field) {
  const onTask = field.kept === "task";
  const onValue = onTask ? (value) => ctx.send({type: `edit-${field.name}`, value})
    : (value) => ctx.send({type: "resume-edit", name: field.name, value});
  return textField(ctx, {key: onTask ? `wizard:${field.name}` : `wizard:resume:${field.name}`,
    name: field.name, multi: true, label: fieldLabel(ctx, field), value: field.value, onValue,
    extra: field.required ? [element("small", {text: ctx.t("wizard.instr.required")})] : []});
}

function note(ctx, key, params) {
  return element("p", {text: ctx.t(key, params)});
}

function resumeBody(ctx, resume) {
  const kind = resume.kind;
  if (kind === "reading") return [note(ctx, "wizard.resume.reading")];
  if (kind === "failed") return [note(ctx, "wizard.resume.failed", {code: resume.code})];
  if (kind === "no_run") {
    return [note(ctx, "wizard.resume.no_run", {title: resume.title}),
      action("wizard:resume:restart", ctx.t("wizard.resume.restart"),
        () => ctx.send({type: "resume-restart"}))];
  }
  if (kind === "exit") {
    const outcome = {runId: resume.runId, stage: resume.stage};
    return [note(ctx, `wizard.resume.exit_${resume.stage}`), action("wizard:resume:open",
      ctx.t("wizard.resume.open"), () => ctx.leave(outcome))];
  }
  if (kind === "preview") return [note(ctx, "wizard.resume.preview")];
  return [note(ctx, "wizard.resume.retype"),
    ...resume.fields.map((field) => resumeField(ctx, field))];
}

function resumeBlock(ctx, facts) {
  if (facts.resume === null || facts.pressed) return [];
  const retry = facts.resume.kind === "failed" ? [action("wizard:prepare:retry",
    ctx.t("wizard.chain.retry"), () => ctx.send({type: "prepare-retry"}))] : [];
  return [element("div", {"data-resume": facts.resume.kind}, [...resumeBody(ctx, facts.resume),
    ...retry])];
}

/** The body of step 5. */
export function prepareBody(ctx) {
  const facts = prepareFacts(ctx.wizard);
  const refusal = facts.phase === "refused" ? [refusalNote(ctx, facts.refusal)] : [];
  const ready = facts.prepared ? [element("p", {"data-prepared": "",
    text: ctx.t("wizard.chain.ready")})] : [];
  return [element("section", {className: "desk-wizard__prepare", "data-prepare": facts.phase}, [
    element("h3", {text: ctx.t("wizard.prepare.heading")}),
    element("ol", {className: "desk-wizard__chain", "data-chain": ""},
      facts.links.map((row, at) => linkRow(ctx, row, at))),
    ...resumeBlock(ctx, facts), ...chainNote(ctx, facts), ...refusal, ...ready,
    element("div", {className: "desk-wizard__chain-actions"},
      [...refusalActions(ctx, facts), ...startButton(ctx, facts)])])];
}
