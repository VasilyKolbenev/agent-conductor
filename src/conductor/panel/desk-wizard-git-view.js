"use strict";
// The git block of step 2, drawn: connecting git, the exclusion step, the first commit (the kind,
// the preview, the confirmation), the wait while a request works, an unfinished first commit with
// the wait for the person's signature, and what the last press came to.
//
// It draws what `firstFacts` says and works nothing out itself: a button whose press is blocked is
// disabled with the reason on screen beside it, a request that works is a wait with words and no
// figure, a lost answer is said to be unknown and then what the read shows, and every text a person
// or a foreign file chose (a branch, an author, a path) is a text node and nothing else. Every
// press is one event of the model's closed table handed to the host through `ctx.send`.
import {element} from "./command-view.js";
import {action, choice, later, textField} from "./desk-wizard-draw.js";
import {MANUAL_REASONS, WARNING_WORDS} from "./desk-wizard-git.js";

const line = (value, attributes = {}) => element("p", {...attributes, text: value});

//: The reason a press is blocked, in words (null when it may go).
function why(ctx, block) {
  return block === null ? null : ctx.t(`wizard.first.why.${block}`);
}

//: A button for a press of the model: disabled, with the reason beside it, while it is blocked.
function press(ctx, facts, spec, onPress) {
  return action(spec.key, spec.label, onPress, why(ctx, facts.blocks[spec.kind]));
}

// -- the exits and the name -----------------------------------------------------------------

function connectBlock(ctx, facts) {
  const starter = ctx.wizard.mode.starterId !== null;
  return element("div", {className: "desk-wizard__connect", "data-git-connect": ""}, [
    line(ctx.t("wizard.first.connect.effect")), element("code", {text: "git init"}),
    line(ctx.t("wizard.first.connect.exclude")),
    ...(starter ? [line(ctx.t("wizard.first.connect.starter"))] : []),
    press(ctx, facts, {kind: "init", key: "wizard:git:connect_git",
      label: ctx.t("wizard.exit.connect_git")}, () => ctx.send({type: "git-init"}))]);
}

/** The exit `connect_git` (what it does, and the button) or `first_commit` (opens the panel). */
export function firstExit(ctx, id, facts) {
  const view = ctx.wizard.mode.view;
  if (id === "connect_git") {
    return view ? later(ctx, id, "wizard:git:connect_git", ctx.t("wizard.exit.connect_git"))
      : connectBlock(ctx, facts);
  }
  return action("wizard:git:first_commit", ctx.t("wizard.exit.first_commit"),
    () => ctx.send({type: "git-start"}),
    view ? ctx.t("wizard.first.why.project_not_active") : null);
}

/** The field the person's name is typed in, wherever a press that carries it can be made. */
export function firstName(ctx, facts) {
  const shown = facts.shown, acts = shown.connect || shown.exclude || shown.panel
    || shown.continue;
  if (!acts || ctx.wizard.mode.view) return [];
  return [textField(ctx, {key: "wizard:git:actor", name: "git-actor", multi: false,
    locked: facts.phase === "busy", label: ctx.t("wizard.first.actor"), value: facts.actor,
    onValue: (value) => ctx.send({type: "actor-edit", value})})];
}

// -- the preview ----------------------------------------------------------------------------

function warningRow(ctx, word) {
  const known = WARNING_WORDS.includes(word);
  return line(known ? ctx.t(`wizard.first.warning.${word}`)
    : ctx.t("wizard.first.warning.other", {code: word}), {"data-git-warning": word});
}

function manualRow(ctx, row) {
  const words = MANUAL_REASONS.includes(row.reason) ? ctx.t(`wizard.first.manual.${row.reason}`)
    : ctx.t("wizard.first.manual.other", {code: row.reason});
  return element("li", {"data-git-manual-row": row.path}, [
    element("code", {text: row.path}), element("small", {text: ` ${words}`})]);
}

function fileRow(ctx, row) {
  return element("li", {"data-git-file": row.path}, [element("code", {text: row.path}),
    element("small", {text: ` ${ctx.t("wizard.first.preview.file_meta",
      {length: String(row.length), mode: row.git_mode})}`})]);
}

//: The list of files is drawn whole, behind its toggle: what the confirmation covers is what the
//: person can read, so no row is left out.
function listParts(ctx, facts) {
  const found = facts.preview;
  if (found.files.length === 0) return [];
  const toggle = action("wizard:git:list", ctx.t(`wizard.first.preview.list_${facts.list
    ? "hide" : "show"}`), () => ctx.send({type: "git-list"}));
  return [toggle, ...(facts.list ? [element("ul", {"data-git-files": ""},
    found.files.map((row) => fileRow(ctx, row)))] : [])];
}

function previewBlock(ctx, facts) {
  const found = facts.preview, count = facts.mode === "empty"
    ? ctx.t("wizard.first.preview.empty")
    : ctx.t("wizard.first.preview.files", {count: String(found.files.length)});
  const manual = found.manual.length === 0 ? [] : [line(ctx.t("wizard.first.preview.manual")),
    element("ul", {"data-git-manual": ""}, found.manual.map((row) => manualRow(ctx, row)))];
  return element("div", {className: "desk-wizard__preview", "data-git-preview": found.mode}, [
    element("h4", {text: ctx.t("wizard.first.preview.heading")}),
    line(ctx.t("wizard.first.preview.branch", {ref: found.target_ref}), {"data-git-branch": ""}),
    line(ctx.t("wizard.first.preview.author", {name: found.author.name,
      email: found.author.email}), {"data-git-author": ""}),
    line(count, {"data-git-count": ""}), ...found.warnings.map((word) => warningRow(ctx, word)),
    ...manual, ...listParts(ctx, facts)]);
}

// -- the first commit ------------------------------------------------------------------------

function modeChoice(ctx, facts) {
  if (facts.modes.length === 1) {
    return line(ctx.t("wizard.first.mode.starter"), {"data-git-mode": ""});
  }
  return element("div", {role: "radiogroup", "aria-label": ctx.t("wizard.first.mode.label")},
    facts.modes.map((mode) => choice(`wizard:git:mode:${mode}`,
      ctx.t(`wizard.first.mode.${mode}`), "radio", facts.mode === mode,
      () => ctx.send({type: "git-mode", mode}))));
}

function commitPanel(ctx, facts) {
  const again = facts.preview !== null || facts.result?.action === "new_preview";
  return element("section", {className: "desk-wizard__commit", "data-git-commit": facts.mode}, [
    element("h4", {text: ctx.t("wizard.first.commit.heading")}), modeChoice(ctx, facts),
    line(ctx.t(`wizard.first.commit.effect_${facts.mode}`)),
    press(ctx, facts, {kind: "preview", key: "wizard:git:preview",
      label: ctx.t(again ? "wizard.first.preview.again" : "wizard.first.preview.prepare")},
    () => ctx.send({type: "git-preview"})),
    ...(facts.preview === null ? [] : [previewBlock(ctx, facts)]),
    press(ctx, facts, {kind: "confirm", key: "wizard:git:confirm",
      label: ctx.t("wizard.first.confirm")}, () => ctx.send({type: "git-confirm"}))]);
}

function excludeBlock(ctx, facts) {
  return element("div", {className: "desk-wizard__exclude", "data-git-exclude": ""}, [
    line(ctx.t("wizard.first.exclude.effect")),
    press(ctx, facts, {kind: "exclude", key: "wizard:git:exclude",
      label: ctx.t("wizard.first.exclude.button")}, () => ctx.send({type: "git-exclude"}))]);
}

// -- an unfinished first commit and the wait for the person's signature ----------------------

function termRow(name, value) {
  return element("li", {"data-git-term": name, text: value});
}

//: What the product stored, as text: each of these is free text a person or a foreign file chose.
function termsView(ctx, terms) {
  return element("ul", {className: "desk-wizard__terms"}, [
    termRow("mode", ctx.t(`wizard.first.mode.${terms.mode}`)),
    termRow("files", ctx.t("wizard.first.preview.files", {count: String(terms.file_count)})),
    termRow("branch", ctx.t("wizard.first.preview.branch", {ref: terms.target_ref})),
    termRow("author", ctx.t("wizard.first.preview.author",
      {name: terms.author.name, email: terms.author.email})),
    termRow("by", ctx.t("wizard.first.pending.by", {name: terms.requested_by}))]);
}

//: A command to copy, read only. Its soft wrap keeps a long branch inside the page, and the value
//: is set as a property so no markup is ever parsed.
function commandArea(ctx, kind, text) {
  const area = element("textarea", {readonly: "", rows: "2", spellcheck: "false",
    "data-focus": `wizard:git:command:${kind}`, "data-git-command": kind,
    "aria-label": ctx.t(`wizard.first.sign.label_${kind}`)});
  area.value = text;
  return area;
}

function signView(ctx, facts) {
  const commands = facts.commands;
  if (commands === null) return [];
  return [line(ctx.t("wizard.first.sign.intro")), line(ctx.t("wizard.first.sign.commit")),
    commandArea(ctx, "commit", commands.commit), line(ctx.t("wizard.first.sign.update")),
    commandArea(ctx, "update", commands.update),
    line(ctx.t("wizard.first.sign.oid"), {"data-git-oid-hint": ""}),
    line(ctx.t("wizard.first.sign.level"))];
}

function pendingView(ctx, facts) {
  const state = facts.pending.state, waits = state === "awaiting_signature";
  const stored = waits || state === "unfinished";
  const go = facts.shown.continue ? [press(ctx, facts, {kind: "continue",
    key: "wizard:git:continue",
    label: ctx.t(waits ? "wizard.first.check_again" : "wizard.first.continue")},
  () => ctx.send({type: "git-continue"}))] : [];
  return element("section", {className: "desk-wizard__pending", "data-git-pending": state}, [
    line(ctx.t(`wizard.first.pending.${state}`)),
    ...(stored ? [termsView(ctx, facts.pending.terms)] : []),
    ...(state === "damaged" ? [line(ctx.t("git_setup.reason.setup_damaged"))] : []),
    ...(waits ? signView(ctx, facts) : []), ...go]);
}

// -- what the last press came to ----------------------------------------------------------------

function doneLines(ctx, result) {
  const found = result.receipt;
  if (result.kind === "init" || result.kind === "exclude") {
    const warned = result.kind === "init" && found.warnings.length > 0;
    return [line(ctx.t(`wizard.first.done.${result.kind}`)),
      ...(warned ? found.warnings.map((word) => warningRow(ctx, word)) : [])];
  }
  const made = line(ctx.t("wizard.first.done.confirm", {ref: found.target_ref,
    commit: found.commit.slice(0, 7), count: String(found.file_count)}));
  return found.signature === "present" ? [made, line(ctx.t("wizard.first.done.signature_present"))]
    : [made];
}

function resultLines(ctx, result) {
  if (result.status === "done") return doneLines(ctx, result);
  if (result.status === "unsent") return [line(ctx.t(result.notice))];
  if (result.status === "lost") {
    return [line(ctx.t("wizard.first.lost.head")),
      line(ctx.t(result.verdict), {"data-git-verdict": ""})];
  }
  const tool = result.tool === null ? [] : [line(ctx.t("wizard.first.tool",
    {tool: result.tool.name, reason: result.tool.reason}))];
  return [line(ctx.t(result.notice)), ...tool,
    ...(result.next === null ? [] : [line(ctx.t(result.next))])];
}

function resultView(ctx, facts) {
  const result = facts.result;
  if (result === null) return [];
  return [element("div", {className: "desk-wizard__result", role: "status",
    "data-git-result": result.status, "data-git-result-kind": result.kind,
    "data-git-notice": result.status === "refused" ? result.notice : null},
  resultLines(ctx, result))];
}

/** The block under the exits: the wait, the exclusion step, the first commit, the last answer. */
export function firstPanel(ctx, facts) {
  const parts = [];
  if (facts.phase === "busy") {
    parts.push(line(ctx.t(`wizard.first.busy.${facts.busy}`), {"data-git-busy": ""}));
  }
  if (facts.shown.exclude) parts.push(excludeBlock(ctx, facts));
  if (facts.shown.panel) parts.push(commitPanel(ctx, facts));
  if (facts.shown.pending) parts.push(pendingView(ctx, facts));
  parts.push(...resultView(ctx, facts));
  if (parts.length === 0) return [];
  const root = element("section", {className: "desk-wizard__first", "data-git-first": "",
    "data-git-phase": facts.phase, "aria-busy": facts.phase === "busy" ? "true" : "false"},
  parts);
  //: A branch, a path or a name is any text Git or a person chose, and may have no place to break:
  //: it wraps anywhere instead of widening the page. The stylesheet is lane D1's, so the one
  //: property is set here until a rule for this block stands there.
  root.style.overflowWrap = "anywhere";
  return [root];
}
