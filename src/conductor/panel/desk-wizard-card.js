"use strict";
// Step 6, «Запуск», drawn: the terms card with the server's numbers, the countdown, who signs, and
// the buttons the slot allows.
//
// It draws what `launchFacts` says and nothing it works out itself: every number is the server's, a
// button that may not be pressed is disabled with the reason on screen, and every press is one
// event of the model's closed table handed to the host through `ctx.send`. Leaving (to point the
// desk at the slot to free, or at the flag block) goes through `ctx.leave`. The explanations behind
// an ⓘ are open or closed in the model, so the redraw of a ticking clock keeps them as they are.
import {element} from "./command-view.js";
import {action, choice, instantText, textField, timeText} from "./desk-wizard-draw.js";
import {LAUNCH_REFUSALS, LAUNCH_WHY, SKIP_STOPS, launchFacts, roleKind}
  from "./desk-wizard-model.js";

const START = "wizard:launch:start";
const ENQUEUE = "wizard:launch:enqueue";
const SKIP = "wizard:launch:skip";
const INPUTS = Object.freeze({"artifact-brief": "wizard.launch.input_brief",
  "artifact-materials": "wizard.launch.input_materials"});

const changedMark = (facts, name) => (facts.changed.includes(name) ? "true" : null);
const shortDigest = (digest) => String(digest).replace("sha256:", "").slice(0, 12);
const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

//: One line of the card: it carries its own name and whether it changed with the last card.
function line(facts, name, children) {
  return element("div", {className: "desk-wizard__line", "data-line": name,
    "data-changed": changedMark(facts, name)}, children);
}

//: An ⓘ that opens the explanation the model holds open under `name`.
function info(ctx, facts, name, body) {
  const on = facts.infos.includes(name);
  const mark = choice(`wizard:launch:info:${name}`, "ⓘ", "switch", on,
    () => ctx.send({type: "launch-info", name}));
  mark.setAttribute("aria-label", ctx.t("wizard.launch.info"));
  return [mark, ...(on ? [element("p", {"data-info": name, text: body})] : [])];
}

function roleWords(ctx, roleId) {
  const kind = roleKind(roleId);
  return kind === "custom" ? ctx.t("wizard.role.custom", {name: roleId.replace("role-", "")})
    : ctx.t(`wizard.role.${kind}`);
}

// -- the lines of the card ---------------------------------------------------------------

function warningRow(ctx, one) {
  const params = {actions: String(one.actions), limit: String(one.limit)};
  return element("p", {"data-warning": one.code,
    text: ctx.t(`wizard.launch.warn.${one.code}`, params)});
}

function actionsLine(ctx, facts) {
  const {card} = facts, params = {max: String(card.actions.max), of: String(card.actions.of)};
  const text = card.spent === null ? ctx.t("wizard.launch.actions", params)
    : ctx.t("wizard.launch.actions_spent", {...params, spent: String(card.spent.actions)});
  const pass = (name, key, row) => element("p", {[name]: "", text: ctx.t(key,
    {actions: String(row.actions), time: timeText(ctx, row.seconds)})});
  const exhausted = card.exhausted ? [element("p", {role: "alert", "data-exhausted": "",
    text: ctx.t("wizard.launch.exhausted", {spent: String(card.spent?.actions ?? 0),
      of: String(card.actions.of)})})] : [];
  return line(facts, "actions", [element("p", {"data-terms-actions": "", text}),
    pass("data-terms-clean", "wizard.budget.clean", card.clean),
    pass("data-terms-worst", "wizard.budget.worst", card.worst),
    ...card.warnings.map((one) => warningRow(ctx, one)), ...exhausted]);
}

function timeLine(ctx, facts) {
  return line(facts, "time", [element("p", {"data-terms-time": "", text: ctx.t(
    "wizard.launch.time", {time: timeText(ctx, facts.card.time)})}),
  ...info(ctx, facts, "time", ctx.t("wizard.launch.time_info"))]);
}

function windowLine(ctx, facts) {
  const queued = facts.controls.enqueue.shown;
  return line(facts, "window", [element("p", {"data-terms-window": "", text: ctx.t(
    "wizard.launch.window", {time: timeText(ctx, facts.card.window)})}),
  ...(queued ? [element("small", {"data-window-queued": "",
    text: ctx.t("wizard.launch.window_queued")})] : [])]);
}

function stepRow(ctx, row) {
  const who = row.role === null ? row.step : `${roleWords(ctx, row.role)} · ${row.step}`;
  const parts = [who, row.harness ?? ctx.t("wizard.launch.step_no_harness"),
    ctx.t("wizard.launch.step_timeout", {time: timeText(ctx, row.timeout)}),
    ctx.t("wizard.launch.step_attempts", {count: String(row.attempts)}),
    ...(row.clamped ? [ctx.t("wizard.launch.step_clamped")] : [])];
  return element("li", {"data-plan-step": row.step, "data-clamped": row.clamped ? "true" : null,
    text: parts.join(" · ")});
}

function stepsLine(ctx, facts) {
  return line(facts, "steps", [element("h4", {text: ctx.t("wizard.launch.steps")}),
    element("ul", {}, facts.card.steps.map((row) => stepRow(ctx, row)))]);
}

function harnessesLine(ctx, facts) {
  const rows = facts.card.harnesses.map((one) => element("li", {"data-harness": one.id,
    text: one.version === null ? one.name : ctx.t("wizard.launch.harness_version",
      {name: one.name, version: one.version})}));
  return line(facts, "harnesses", [element("h4", {text: ctx.t("wizard.launch.harnesses")}),
    element("ul", {}, rows)]);
}

function receiveRow(ctx, facts, name, label, digest) {
  return element("li", {"data-receives": name}, [element("span", {text: label}),
    ...info(ctx, facts, name, ctx.t("wizard.launch.digest", {digest: shortDigest(digest)}))]);
}

function seedLine(ctx, seed) {
  if (seed === null) return [];
  const text = seed.kind === "request" ? ctx.t("wizard.launch.seed_request")
    : ctx.t("wizard.launch.seed_copy", {ref: seed.ref ?? "HEAD", commit: seed.commit});
  return [element("p", {"data-seed": seed.kind, text})];
}

function receivesLine(ctx, facts) {
  const {receives} = facts.card;
  const inputs = receives.inputs.map((row) => receiveRow(ctx, facts, `input:${row.ref}`,
    Object.hasOwn(INPUTS, row.ref) ? ctx.t(INPUTS[row.ref])
      : ctx.t("wizard.launch.input_other", {ref: row.ref}), row.digest));
  const steps = receives.instructions.map((row) => receiveRow(ctx, facts,
    `instruction:${row.step}`, ctx.t("wizard.launch.instruction", {step: row.step}), row.digest));
  return line(facts, "receives", [element("h4", {text: ctx.t("wizard.launch.receives")}),
    element("ul", {}, [...inputs, ...steps]), ...seedLine(ctx, receives.seed)]);
}

function termsCard(ctx, facts) {
  return [element("div", {className: "desk-wizard__terms", "data-terms": ""}, [
    actionsLine(ctx, facts), timeLine(ctx, facts), windowLine(ctx, facts),
    stepsLine(ctx, facts), harnessesLine(ctx, facts), receivesLine(ctx, facts)])];
}

// -- what surrounds the card -------------------------------------------------------------

//: The countdown to `valid_until`; at zero the desk asks again by itself, six times in a row and
//: then the owner alone may.
function countdownBlock(ctx, facts) {
  const left = facts.countdown;
  if (left === null) return [];
  const text = left.seconds === 0 ? ctx.t("wizard.launch.countdown_over")
    : ctx.t("wizard.launch.countdown", {left: clock(left.seconds)});
  const spent = facts.repeatsSpent ? [element("p", {"data-repeats-spent": "",
    text: ctx.t("wizard.launch.repeats_spent")})] : [];
  return [element("p", {"data-countdown": String(left.seconds), text}), ...spent];
}

function refreshButton(ctx, facts) {
  const wanted = facts.repeatsSpent || facts.error !== null;
  return wanted ? [action("wizard:launch:refresh", ctx.t("wizard.launch.refresh"),
    () => ctx.send({type: "launch-refresh"}))] : [];
}

function errorLine(ctx, facts) {
  if (facts.error === null) {
    return facts.card === null ? [element("p", {"data-launch-waiting": "",
      text: ctx.t("wizard.launch.waiting")})] : [];
  }
  const key = facts.card === null ? "wizard.launch.unreadable" : "wizard.launch.preview_failed";
  return [element("p", {role: "alert", "data-launch-error": facts.error,
    text: ctx.t(key, {code: facts.error})})];
}

//: Another card replaced the one the owner looked at: which lines changed, and the press that
//: says they have been looked at.
function changedBlock(ctx, facts) {
  if (facts.seen) return [];
  const names = facts.changed.map((name) => ctx.t(`wizard.launch.line.${name}`));
  const text = names.length === 0 ? ctx.t("wizard.launch.changed_quiet")
    : ctx.t("wizard.launch.changed", {lines: names.join(", ")});
  return [element("div", {"data-changed-note": ""}, [element("p", {text}),
    action("wizard:launch:seen", ctx.t("wizard.launch.seen"),
      () => ctx.send({type: "launch-seen"}))])];
}

function actorField(ctx, facts) {
  return textField(ctx, {key: "wizard:launch:actor", name: "actor", multi: false,
    label: ctx.t("wizard.launch.actor"), value: facts.actor,
    locked: facts.result !== null || facts.skip !== null,
    onValue: (value) => ctx.send({type: "actor-edit", value}),
    extra: [element("small", {text: ctx.t("wizard.launch.actor_hint")})]});
}

// -- what may be pressed -----------------------------------------------------------------

function whyWords(ctx, code) {
  return LAUNCH_WHY.includes(code) ? ctx.t(`wizard.launch.why.${code}`)
    : ctx.t("wizard.launch.why.other", {code});
}

function pressable(ctx, control, key, label, onClick) {
  if (!control.shown) return [];
  const blocked = control.blocked === null ? null : whyWords(ctx, control.blocked);
  return [action(key, label, onClick, blocked)];
}

//: The slot's unreadable state has its own way out (read again); a stuck slot points at the desk.
function slotNotes(ctx, facts) {
  const {controls} = facts, out = [];
  if (controls.why !== null) {
    out.push(element("p", {"data-launch-why": controls.why, text: whyWords(ctx, controls.why)}));
  }
  if (controls.why === "slot_unread" || facts.lostUnread) {
    out.push(action("wizard:launch:reread", ctx.t(facts.lostUnread ? "wizard.launch.reread_lost"
      : "wizard.launch.reread"), () => ctx.send({type: "launch-reread"})));
  }
  if (controls.release) {
    out.push(element("div", {"data-launch-release": ""}, [
      element("p", {text: ctx.t("wizard.launch.release")}),
      action("wizard:launch:release", ctx.t("wizard.launch.release_open"),
        () => ctx.leave({runId: controls.holder ?? facts.runId, stage: "release_slot"}))]));
  }
  if (controls.caption !== null) {
    out.push(element("p", {"data-launch-caption": controls.caption,
      text: ctx.t(`wizard.launch.caption_${controls.caption}`)}));
  }
  return out;
}

function buttons(ctx, facts) {
  const {controls} = facts;
  return [element("div", {className: "desk-wizard__launch-actions"}, [
    ...pressable(ctx, controls.start, START, ctx.t("wizard.launch.start"),
      () => ctx.send({type: "launch-start"})),
    ...pressable(ctx, controls.enqueue, ENQUEUE, ctx.t("wizard.launch.enqueue"),
      () => ctx.send({type: "launch-enqueue"})),
    ...pressable(ctx, controls.skip, SKIP, ctx.t("wizard.launch.skip"),
      () => ctx.send({type: "launch-skip"}))]), ...slotNotes(ctx, facts)];
}

// -- «Пропустить вперёд»: the dialog, the steps, and the stop -----------------------------

function skipDialog(ctx, facts) {
  const {holder} = facts.skip;
  const task = holder.title ?? ctx.t("wizard.launch.skip_holder_unknown");
  const until = holder.expiresAt === null ? "—" : instantText(holder.expiresAt);
  return [element("div", {className: "desk-wizard__skip", "data-skip-dialog": ""}, [
    element("p", {text: ctx.t("wizard.launch.skip_dialog", {task, until})}),
    action("wizard:launch:skip-confirm", ctx.t("wizard.launch.skip"),
      () => ctx.send({type: "launch-skip-confirm"})),
    action("wizard:launch:skip-cancel", ctx.t("wizard.launch.skip_cancel"),
      () => ctx.send({type: "launch-skip-cancel"}))])];
}

//: What the card says of one step: done, not done, or (nothing says) still being read while the
//: press runs and not known once it stopped.
function stepStatus(facts, row) {
  if (row.done === null) return facts.skip.phase === "running" ? "reading" : "unknown";
  return row.done ? "done" : "todo";
}

function skipSteps(ctx, facts) {
  const rows = facts.skip.steps.map((row) => {
    const status = stepStatus(facts, row);
    return element("li", {"data-skip-step": row.step, "data-status": status,
      "data-failed": facts.skip.stop?.step === row.step ? "true" : null,
      text: `${ctx.t(`wizard.launch.skip_step.${row.step}`)} · `
        + ctx.t(`wizard.launch.skip_status.${status}`)});
  });
  return element("ul", {"data-skip-steps": ""}, rows);
}

function skipQueue(ctx, facts) {
  if (facts.skip.queue.length === 0) return [];
  const rows = facts.skip.queue.map((row) => element("li", {
    text: `${row.position}. ${row.title ?? "—"}`}));
  return [element("div", {"data-skip-queue": ""}, [
    element("h4", {text: ctx.t("wizard.launch.skip_queue")}), element("ul", {}, rows)])];
}

//: The press stopped: why (a refusal the desk has no words for is said by its code), what stands,
//: and the way on. The new run is first in the queue whenever its two steps are done.
function skipStopped(ctx, facts) {
  const {stop, steps} = facts.skip, first = steps.slice(0, 2).every((row) => row.done === true);
  const reason = SKIP_STOPS.includes(stop.code) ? ctx.t(`wizard.launch.skip_stop.${stop.code}`)
    : ctx.t("wizard.launch.skip_stop.other", {code: stop.code});
  return [element("div", {className: "desk-wizard__skip", "data-skip-done": "stopped"}, [
    element("p", {role: "alert", "data-skip-stop": stop.code,
      text: ctx.t("wizard.launch.skip_stopped", {reason})}),
    skipSteps(ctx, facts),
    ...(first ? [element("p", {"data-skip-stands": "",
      text: ctx.t("wizard.launch.skip_stands_first")})] : []),
    ...skipQueue(ctx, facts),
    element("p", {"data-skip-again": "", text: ctx.t("wizard.launch.skip_again")}),
    action("wizard:launch:skip-ack", ctx.t("wizard.launch.skip_ack"),
      () => ctx.send({type: "launch-skip-cancel"}))])];
}

function skipBody(ctx, facts) {
  const {phase} = facts.skip;
  if (phase === "confirm") return skipDialog(ctx, facts);
  if (phase === "stopped") return skipStopped(ctx, facts);
  return [element("div", {className: "desk-wizard__skip", "data-skip-running": ""}, [
    element("p", {text: ctx.t("wizard.launch.skip_running")}), skipSteps(ctx, facts)])];
}

// -- what the last press did -------------------------------------------------------------

function progressLine(ctx, facts) {
  if (!["starting", "enqueuing", "unknown"].includes(facts.phase)) return [];
  if (facts.lostUnread) {
    return [element("p", {role: "alert", "data-launch-progress": facts.phase,
      "data-launch-unread": "", text: ctx.t("wizard.launch.unknown_unread")})];
  }
  return [element("p", {"data-launch-progress": facts.phase,
    text: ctx.t(`wizard.launch.${facts.phase}`)})];
}

//: What the last answer said: a note (the slot was taken, the terms were stale, nothing was
//: written) or a refusal with its code. None of them presses anything by itself.
function answerLines(ctx, facts) {
  const {note, refusal} = facts, out = [];
  if (note !== null) {
    const params = note.kind === "slot_busy"
      ? {holder: note.holderTitle ?? note.holder ?? "—"} : {};
    out.push(element("p", {"data-launch-note": note.kind,
      text: ctx.t(`wizard.launch.note.${note.kind}`, params)}));
  }
  if (refusal !== null) {
    const known = LAUNCH_REFUSALS.includes(refusal.code);
    out.push(element("p", {role: "alert", "data-launch-refusal": refusal.code,
      text: known ? ctx.t(`wizard.launch.refused.${refusal.code}`)
        : ctx.t("wizard.launch.refused.other", {code: refusal.code})}));
  }
  return out;
}

//: Started, or queued. A queue entry in a viewed project keeps the wizard open: the closing line,
//: the line about the flag and the way to it are here, and the owner leaves from here.
function resultBlock(ctx, facts) {
  const {result, viewing, runId} = facts;
  if (result.kind === "started") {
    return [element("p", {"data-launch-result": "started",
      text: ctx.t("wizard.launch.result_started")})];
  }
  const plain = result.position === null ? ctx.t("wizard.launch.result_queued_plain")
    : ctx.t("wizard.launch.result_queued", {position: String(result.position)});
  const text = viewing ? ctx.t("wizard.launch.result_queued_view") : plain;
  const flag = viewing ? [element("p", {"data-launch-flag": "",
    text: ctx.t("wizard.launch.caption_queue_view")}),
  action("wizard:launch:continue", ctx.t("wizard.launch.continue_after"),
    () => ctx.leave({runId, stage: "continue"})),
  action("wizard:launch:done", ctx.t("wizard.close"), () => ctx.leave({runId, stage: "queued"}))]
    : [];
  return [element("p", {"data-launch-result": "queued", text}), ...flag];
}

/** The body of step 6. */
export function runBody(ctx) {
  const facts = launchFacts(ctx.wizard), done = facts.result !== null;
  return [element("section", {className: "desk-wizard__launch", "data-launch": facts.phase,
    "data-viewing": facts.viewing ? "true" : "false"}, [
    element("h3", {text: ctx.t("wizard.launch.heading")}),
    ...(facts.card === null ? [] : termsCard(ctx, facts)), ...errorLine(ctx, facts),
    ...countdownBlock(ctx, facts), ...refreshButton(ctx, facts), ...changedBlock(ctx, facts),
    actorField(ctx, facts), ...progressLine(ctx, facts), ...answerLines(ctx, facts),
    ...(done ? resultBlock(ctx, facts) : facts.skip === null ? buttons(ctx, facts)
      : skipBody(ctx, facts)),
    ...(done && facts.skip !== null ? [skipSteps(ctx, facts)] : [])])];
}
