"use strict";
// The centre of the hub's page and its right column (spec 4.1.9, 4.1.10, 4.5.4, 4.5.5).
//
// When no project is chosen, or the chosen one has no running desk, the centre is a stub: the
// project's line and its one main action (the rail's own words for the same project: one rule for a
// project's line wherever it is drawn), and the countdown of a stop that is under way. A project
// whose desk runs has no stub: its centre is the desk itself, in the frame `hub-frame.js` mounts, and
// the right column is the desk's own. Beside the stub stand the queue of projects and the limits of
// the active project, one card per account.
//
// The first half is pure. The countdown is handed the clock and never reads it; a limit that has no
// reading is «no data» and never a zero; an account the hub could not confirm is a card of its own and
// says so; nothing here compares a run's state, because the words of a run are the shared module's.
// The second half draws that as text nodes and elements; a press is a call to a handler.
import {instantText} from "./desk-time.js";
import {frameAddress} from "./hub-frame.js";
import {hubText} from "./hub-copy.js";
import {actionControl, mutedNote, node, projectLine, queueActions, stateWord}
  from "./hub-rail.js";

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const rows = (value) => (Array.isArray(value) ? value.filter(isObject) : []);
const text = (value) => (typeof value === "string" ? value : null);

// -- a stop under way --------------------------------------------------------------------------------

/**
 * «Остановка: осталось m:ss» for a stop whose deadline the hub wrote, from the clock handed in as
 * milliseconds; null when there is no deadline, it is not an instant, or it has passed.
 */
export function drainText(locale, deadline, nowMs) {
  if (!instantText(locale, deadline).known || !Number.isFinite(nowMs)) return null;
  const left = Math.ceil((Date.parse(deadline) - nowMs) / 1000);
  if (left <= 0) return null;
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  return hubText(locale, "hub.center.drain", {time: clock});
}

/**
 * What the stub says of a project: `{line, tone, hint, actions, note, drain}`. The line, tone, hint
 * and actions are the rail's (`projectLine`), the note is the snapshot it was read from, and the drain
 * is the countdown while the project is stopping.
 */
export function stubModel(project, ctx, nowMs) {
  const said = projectLine(project, ctx);
  return {line: said.text, tone: said.tone, hint: said.hint, actions: said.actions,
    note: mutedNote(project, ctx),
    drain: project.state === "stopping" ? drainText(ctx.locale, project.drain_deadline, nowMs)
      : null};
}

/**
 * Which of the three things the centre shows: `choose` (no project, or one the hub does not list),
 * `running` (a desk the hub gave an address for, which the frame shows) or `stub`.
 */
export function centerCase(view) {
  const project = rows(view.projects).find((one) => one.project_id === view.selection.project_id);
  if (project === undefined) return "choose";
  return frameAddress(project, view.hubPort) === null ? "stub" : "running";
}

// -- the queue of projects -----------------------------------------------------------------------------

/**
 * The queue of projects as the hub keeps it: who is in progress (and what its process is doing when it
 * is not simply running), then each project waiting for its turn with its place, the moment its flag
 * was set and its controls. A place is its place in the hub's queue; a project the hub does not list
 * has no row.
 */
export function queueModel(view) {
  const {locale} = view, all = rows(view.projects);
  const ctx = {locale, projects: all, activeId: view.activeId, queue: view.queue};
  const active = all.find((one) => one.project_id === view.activeId);
  const word = active === undefined ? "" : stateWord(active, ctx);
  const now = active === undefined ? hubText(locale, "hub.queue.none_active")
    : hubText(locale, "hub.queue.now", {name: String(active.name ?? "")})
      + (word === "" ? "" : ` · ${word}`);
  const entries = view.queue.map((id, at) => [all.find((one) => one.project_id === id), at + 1])
    .filter(([project]) => project !== undefined);
  return {now, rows: entries.map(([project, position]) => {
    const since = instantText(locale, text(project.auto_continue?.set_at));
    const words = {position: String(position), name: String(project.name ?? "")};
    return {project_id: project.project_id, exact: since.known ? since.exact : "",
      text: since.known ? hubText(locale, "hub.queue.entry", {...words, time: since.short})
        : hubText(locale, "hub.queue.entry_open", words),
      actions: queueActions(project, ctx)};
  })};
}

// -- the limits of the active project ------------------------------------------------------------------

function span(locale, minutes) {
  if (Number.isInteger(minutes) && minutes >= 120 && minutes % 60 === 0) {
    return hubText(locale, "hub.limits.hours", {count: String(minutes / 60)});
  }
  return Number.isInteger(minutes) && minutes > 0
    ? hubText(locale, "hub.limits.minutes", {count: String(minutes)}) : null;
}

function windowRow(locale, one) {
  const left = Number.isFinite(one.remaining_percent) ? String(Math.round(one.remaining_percent))
    : null;
  if (left === null) return {text: hubText(locale, "hub.limits.missing"), quiet: true};
  const label = span(locale, one.duration_minutes) ?? String(one.window_id ?? one.limit_id ?? "");
  const reset = instantText(locale, text(one.resets_at));
  const said = reset.known ? hubText(locale, "hub.limits.window", {label, value: left,
    time: reset.short}) : hubText(locale, "hub.limits.window_open", {label, value: left});
  const current = one.freshness === "current" || one.freshness === undefined;
  return {text: current ? said : `${said} · ${hubText(locale, "hub.limits.stale")}`, quiet: false};
}

function balanceRow(locale, one) {
  return {text: `${hubText(locale, "hub.limits.balance", {amount: String(one.total_balance),
    currency: String(one.currency)})} · ${hubText(locale, "hub.limits.no_reset")}`, quiet: false};
}

//: What one account's reading says, row by row; a reading the hub did not get is «no data» and is
//: never drawn as a zero.
function cardRows(locale, row) {
  const quiet = (key) => [{text: hubText(locale, key), quiet: true}];
  if (!isObject(row)) return quiet("hub.limits.missing");
  if (row.state === "error") return quiet("hub.limits.error");
  if (row.state === "unavailable") return quiet("hub.limits.unavailable");
  const listed = [...rows(row.windows).map((one) => windowRow(locale, one)),
    ...rows(row.balances).map((one) => balanceRow(locale, one))];
  return row.state === "observed" && listed.length > 0 ? listed : quiet("hub.limits.missing");
}

function caption(locale, limits) {
  if (!isObject(limits) || !["live", "snapshot"].includes(limits.source)) {
    return hubText(locale, "hub.limits.none");
  }
  if (limits.source === "live") return hubText(locale, "hub.limits.live");
  const at = instantText(locale, text(limits.taken_at));
  return at.known ? hubText(locale, "hub.limits.snapshot", {time: at.short})
    : hubText(locale, "desk_status.snapshot_unknown");
}

/**
 * The limits of the active project as the hub gave them (`GET /hub/limits`): `{caption, cards}`, one
 * card per account, `{title, unverified, note, rows: [{text, quiet}]}`. A card's title is its vendor,
 * or for an account the hub could not confirm the bindings of its row, and it says so.
 */
export function limitsModel(limits, locale) {
  const cards = isObject(limits) && ["live", "snapshot"].includes(limits.source)
    ? rows(limits.accounts) : [];
  return {caption: caption(locale, limits), cards: cards.map((card) => {
    const verified = card.verified === true, key = isObject(card.key) ? card.key : {};
    const title = verified ? String(key.vendor ?? "")
      : Array.isArray(key.binding_ids) ? key.binding_ids.join(", ") : "";
    return {title, unverified: !verified,
      note: verified ? null : hubText(locale, "hub.limits.unverified"),
      rows: cardRows(locale, card.row)};
  })};
}

// -- drawing -------------------------------------------------------------------------------------------

function stubBlock(view, project, ctx, handlers) {
  const said = stubModel(project, ctx, view.now);
  const controls = said.actions.map((action) => actionControl(view, project, action, handlers,
    "stub"));
  return node("section", {className: "hub-stub", "data-case": "stub",
    "data-project-id": project.project_id}, [
    node("p", {className: "hub-stub__line", "data-tone": said.tone, title: said.hint, text: said.line}),
    node("p", {className: "hub-center__choose", text: hubText(view.locale, "hub.center.stub")}),
    ...(said.note === null ? [] : [node("p", {className: "hub-project__note", text: said.note})]),
    ...(said.drain === null ? [] : [node("p", {className: "hub-stub__drain", "data-drain": "",
      text: said.drain})]),
    node("div", {className: "hub-stub__actions"}, controls)]);
}

/**
 * Draw the stub of the centre: a choice, or the stub of a project that has no running desk. A project
 * whose desk runs is drawn by nothing here: the frame is its centre.
 */
export function mountCenter(mount, view, handlers) {
  const ctx = {locale: view.locale, projects: view.projects, activeId: view.activeId,
    queue: view.queue};
  const project = rows(view.projects).find((one) => one.project_id
    === view.selection.project_id);
  const shown = centerCase(view);
  mount.replaceChildren(...(shown === "running" ? []
    : [shown === "choose" ? node("p", {className: "hub-center__choose", "data-case": "choose",
      text: hubText(view.locale, "hub.center.choose")}) : stubBlock(view, project, ctx, handlers)]));
}

function queueBlock(view, handlers) {
  const model = queueModel(view), {locale} = view;
  const project = (id) => rows(view.projects).find((one) => one.project_id === id);
  const entry = (one) => node("li", {className: "hub-queue__entry", "data-project-id": one.project_id},
    [node("span", {title: one.exact, text: one.text}), node("div", {className: "hub-queue__buttons"},
      one.actions.map((action) => actionControl(view, project(one.project_id), action, handlers,
        "queue")))]);
  return node("section", {className: "hub-queue", "data-queue": ""}, [
    node("h2", {className: "hub-rail__head", text: hubText(locale, "hub.queue.heading")}),
    node("p", {className: "hub-queue__now", text: model.now}),
    model.rows.length === 0 ? node("p", {className: "hub-rail__none", text: hubText(locale,
      "hub.queue.empty")}) : node("ul", {className: "hub-queue__list"}, model.rows.map(entry))]);
}

function limitsBlock(view) {
  const model = limitsModel(view.limits, view.locale);
  const card = (one) => node("div", {className: "hub-card", "data-unverified": String(one.unverified)},
    [node("span", {className: "hub-card__name", text: one.title}),
      ...(one.note === null ? [] : [node("span", {className: "hub-card__note", text: one.note})]),
      ...one.rows.map((line) => node("p", {className: "hub-card__row", "data-quiet":
        String(line.quiet), text: line.text}))]);
  return node("section", {className: "hub-limits", "data-limits": ""}, [
    node("h2", {className: "hub-rail__head", text: hubText(view.locale, "hub.limits.heading")}),
    node("p", {className: "hub-limits__source", text: model.caption}), ...model.cards.map(card)]);
}

/**
 * Draw the right column: the queue of projects and the limits of the active project, while the centre
 * is a stub or a choice. Beside a running desk the column is that desk's own, so nothing is drawn.
 */
export function mountSide(mount, view, handlers) {
  if (centerCase(view) === "running") {
    mount.replaceChildren();
    return;
  }
  mount.replaceChildren(queueBlock(view, handlers), limitsBlock(view));
}
