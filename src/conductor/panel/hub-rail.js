"use strict";
// The hub's column of projects (spec 4.1.10, 4.3.3, 4.5.4): what each project's line says, the one
// action it offers, the tasks under it, and the list of what waits for you across all of them.
//
// The first half is pure: values in, values out, no markup. A project's line is the hub's own two
// closed values, `working` and `state`, through the table of 4.1.10 -- the page has no word of its
// own for what a project is doing -- and the words of a task are `desk-status.js` through
// `desk-status-copy.js`, so the same task is told in the same words as the desk's rail tells it.
// What waits for you is `attentionItems` of the shared module, and the ids that go with an item
// (project, task, run, gate) come from the row the hub gave and never from a word on the screen.
// The page has no rule of its own about a run: nothing here compares a run's state, a human state
// or an outcome; that is the shared module's.
//
// The second half draws that, as text nodes and elements, and sends what a person does to its
// handlers: a press is a call, never a write made here.
import {deskHash, preferenceHash} from "./desk-hash.js";
import {attentionItems, taskStatus} from "./desk-status.js";
import {instantText} from "./desk-time.js";
import {codeWords, hubText, paramsOf} from "./hub-copy.js";

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const rows = (value) => (Array.isArray(value) ? value.filter(isObject) : []);
const text = (value) => (typeof value === "string" ? value : null);
//: The states in which a process of the project is alive: the project cannot be taken out of the list
//: or opened for viewing from under it.
const ALIVE = Object.freeze(["starting", "running", "stopping", "stop_overdue"]);
const STATES = Object.freeze([...ALIVE, "stopped", "stop_uncertain", "failed", "busy_elsewhere",
  "recovery_required", "identity_mismatch", "missing"]);
//: The states that ask a person to look, told by a tone and never by the tone alone.
const AMBER = Object.freeze(["stop_overdue", "stop_uncertain", "failed", "busy_elsewhere",
  "recovery_required", "identity_mismatch", "missing"]);

/** The short text of an instant in the reader's language, and the exact one for a hint. */
function clock(locale, iso) {
  const at = instantText(locale, text(iso));
  return {short: at.short, exact: at.exact, known: at.known};
}

// -- the line of a project --------------------------------------------------------------------

//: The project that is still closing (its process is stopping) and the one that blocks the seat
//: (a stop that is not proven), other than `self`: the names two clarifications of 4.1.10 give.
function other(ctx, self, states) {
  return rows(ctx.projects).find((one) => one.project_id !== self.project_id
    && states.includes(one.state));
}

function workingWord(project, ctx) {
  const {locale} = ctx, position = String(project.queue_position ?? "");
  if (project.working === "active") return hubText(locale, "hub.working.active");
  if (project.working === "queued") {
    const at = project.queue_position ?? ctx.queue.indexOf(project.project_id) + 1;
    return hubText(locale, "hub.working.queued", {position: String(at)});
  }
  if (project.working === "view") {
    return project.queue_position === null || project.queue_position === undefined
      ? hubText(locale, "hub.working.view")
      : hubText(locale, "hub.working.view_queued", {position});
  }
  if (project.working !== "stopped") return "";
  const at = clock(locale, project.stopped_at);
  return at.known ? hubText(locale, "hub.working.stopped_since", {time: at.short})
    : hubText(locale, "hub.working.stopped");
}

//: The word a process state has of its own (`stopped` and `running` have none: the working word is
//: theirs).
export function stateWord(project, ctx) {
  const {locale} = ctx, at = clock(locale, project.drain_deadline);
  const timed = (name) => hubText(locale, at.known ? `hub.state.${name}` : `hub.state.${name}_open`,
    at.known ? {time: at.short} : {});
  const words = {
    starting: () => hubText(locale, project.working === "view" ? "hub.state.starting_view"
      : "hub.state.starting_active"),
    stopping: () => timed("stopping"), stop_overdue: () => timed("stop_overdue"),
    stop_uncertain: () => hubText(locale, "hub.state.stop_uncertain"),
    failed: () => hubText(locale, "hub.state.failed", {reason: codeWords(locale,
      project.state_code)}),
    busy_elsewhere: () => hubText(locale, "hub.state.busy_elsewhere"),
    recovery_required: () => hubText(locale, "hub.state.recovery_required"),
    identity_mismatch: () => hubText(locale, "hub.state.identity_mismatch"),
    missing: () => hubText(locale, "hub.state.missing"),
  };
  return Object.hasOwn(words, project.state) ? words[project.state]() : "";
}

//: The words of the line, before they are joined. A project that is to be the active one while the
//: former active one is still closing says so in place of «В работе»; one that could not become active
//: because the former is not closed says that in place of everything. A project that carries the
//: code of an unreadable status file says it after its own state word, because its `state` is what
//: the rest says (usually `stopped`) and no word of it would say why nothing starts; a failed one
//: already says the clause of its code.
function lineParts(project, ctx) {
  const blocking = other(ctx, project, ["stop_uncertain", "recovery_required"]);
  if (project.state_code === "active_not_closed" && blocking !== undefined) {
    return [hubText(ctx.locale, "hub.line.not_active", {name: String(blocking.name ?? "")})];
  }
  const closing = other(ctx, project, ["stopping", "stop_overdue"]);
  const waits = project.working === "active" && project.state !== "running"
    && closing !== undefined;
  const first = waits ? hubText(ctx.locale, "hub.line.becomes_active",
    {name: String(closing.name ?? "")}) : workingWord(project, ctx);
  const unreadable = project.state_code === "status_unreadable" && project.state !== "failed"
    ? hubText(ctx.locale, "hub.state.status_unreadable") : "";
  return [first, stateWord(project, ctx), unreadable].filter((part) => part !== "");
}

// -- the actions of a project -------------------------------------------------------------------

/** The new order of a queue with `id` moved by `delta` places, or null when it cannot move. */
export function moveInQueue(queue, id, delta) {
  const at = queue.indexOf(id), to = at + delta;
  if (at < 0 || to < 0 || to >= queue.length) return null;
  const next = [...queue];
  next.splice(to, 0, ...next.splice(at, 1));
  return next;
}

//: Whether an active project is working now: a switch to another project then asks first.
function activeIsWorking(ctx, project) {
  const active = rows(ctx.projects).find((one) => one.project_id === ctx.activeId);
  return active !== undefined && active.project_id !== project.project_id
    && ["running", "starting"].includes(active.state);
}

const act = (id, target, key, locale, extra = {}) => ({id, target, label: hubText(locale, key),
  confirm: null, ...extra});

function ownAction(project, ctx) {
  const {locale} = ctx, view = project.working === "view";
  const again = view ? "projectView" : "projectActivate";
  const by = {
    stop_uncertain: [act("recover", "projectRecover", "hub.act.recover", locale)],
    recovery_required: [act("recover", "projectRecover", "hub.act.recover", locale)],
    failed: [act("restart", again, "hub.act.restart", locale)],
    busy_elsewhere: [act("recheck", again, "hub.act.recheck", locale)],
    identity_mismatch: [act("forget", "projectForget", "hub.act.forget", locale)],
    missing: [act("forget", "projectForget", "hub.act.forget", locale)],
  };
  return Object.hasOwn(by, project.state) ? by[project.state] : null;
}

/** The moves a project waiting in the queue offers: raise, lower (where they can be made) and the flag. */
export function queueActions(project, ctx) {
  const {locale, queue} = ctx, list = [];
  for (const [id, delta, key] of [["raise", -1, "hub.act.raise"], ["lower", 1, "hub.act.lower"]]) {
    const order = moveInQueue(queue, project.project_id, delta);
    if (order !== null) list.push(act(id, "queueOrder", key, locale, {order}));
  }
  return [...list, act("clear_flag", null, "hub.act.clear_flag", locale)];
}

function workingActions(project, ctx) {
  const {locale} = ctx, ask = activeIsWorking(ctx, project) ? "switch" : null;
  if (project.working === "active") {
    return [act("stop", "projectStop", "hub.act.stop", locale, {confirm: "stop"})];
  }
  if (project.working === "queued") return queueActions(project, ctx);
  //: «Continue» is the word of a stopped project that has a run to resume; a project in view is made
  //: active whatever it holds (spec 4.1.10).
  const resumes = project.working === "stopped" && text(project.resume_run_id) !== null;
  const start = act("activate", "projectActivate", resumes ? "hub.act.resume"
    : "hub.act.activate", locale, {confirm: ask});
  if (project.working === "view") {
    return [start, act("close_view", "projectStop", "hub.act.view_close", locale)];
  }
  return project.working === "stopped" ? [start] : [];
}

/**
 * The line of a project and what it offers: `{text, tone, hint, actions}`. `ctx` is `{locale,
 * projects, activeId, queue}` as the hub's last answer gave them. The line is the working word and,
 * after a middle dot, the word of the process state when it has one; the first action is the main one.
 */
export function projectLine(project, ctx) {
  const known = isObject(project) && STATES.includes(project.state);
  if (!known) return {text: "", tone: null, hint: null, actions: []};
  const parts = lineParts(project, ctx);
  const tone = AMBER.includes(project.state) ? "amber"
    : project.working === "active" && project.state === "running" ? "ion" : null;
  const actions = ownAction(project, ctx) ?? (ALIVE.includes(project.state) && project.state
    !== "running" ? [] : workingActions(project, ctx));
  return {text: parts.join(" · "), tone, actions, hint: project.state === "stop_overdue"
    ? hubText(ctx.locale, "hub.state.stop_overdue_hint") : null};
}

/** The entries of the «⋯» menu of a project: opening for viewing, closing a view, leaving the list. */
export function menuItems(project) {
  if (!isObject(project) || !STATES.includes(project.state)) return [];
  const items = [];
  const free = !ALIVE.includes(project.state);
  if (["stopped", "failed"].includes(project.state) && project.working !== "active") {
    items.push({id: "view_open", target: "projectView", key: "hub.act.view_open"});
  }
  if (project.working === "view" && !free) {
    items.push({id: "close_view", target: "projectStop", key: "hub.act.view_close"});
  }
  if (free) items.push({id: "forget", target: "projectForget", key: "hub.act.forget"});
  return items;
}

/** The sentences a confirmation says: a switch names the working project; a stop the one after it. */
export function confirmWords(kind, project, ctx) {
  const {locale} = ctx;
  if (kind === "switch") {
    const active = rows(ctx.projects).find((one) => one.project_id === ctx.activeId);
    return [hubText(locale, "hub.confirm.switch", {name: String(active?.name ?? "")})];
  }
  const next = ctx.queue.filter((id) => id !== project.project_id)[0];
  const after = rows(ctx.projects).find((one) => one.project_id === next);
  return [hubText(locale, "hub.confirm.stop"), ...(after === undefined ? []
    : [hubText(locale, "hub.confirm.stop_next", {name: String(after.name ?? "")})])];
}

//: The one shape an address of a desk may have (spec 4.5.5): a loopback address, a port, the desk's page.
const DESK_URL = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})\/panel\/desk\.html$/;

/**
 * The address a project's running desk is opened at, in a tab of its own: the `desk_url` the hub gave
 * (never one typed into the page's address), held to the rule of 4.5.5 (a port up to 65535 that is
 * not the hub's own), with the navigation (`task`, `run`, `gate`, `panel`, `new`) and the language and
 * theme as its address words. Null when the project has no running desk or its address is not one.
 */
export function deskLink(project, nav, prefs, hubPort) {
  const found = isObject(project) && project.state === "running"
    ? DESK_URL.exec(text(project.desk_url) ?? "") : null;
  if (found === null || Number(found[1]) > 65535 || found[1] === String(hubPort)) return null;
  const address = {project: project.project_id, task: nav.task ?? null, run: nav.run ?? null,
    gate: nav.gate ?? null, panel: nav.panel ?? null, new: nav.new ?? null};
  return `${project.desk_url}${preferenceHash(deskHash(address), prefs)}`;
}

// -- tasks, and the note of a project read from a snapshot ------------------------------------------

/** What to say under a project whose data is not live: its snapshot's moment, or that it has none. */
export function mutedNote(project, ctx) {
  if (!isObject(project) || project.data === "live") return null;
  if (project.data === "none") return hubText(ctx.locale, "hub.rail.no_data");
  const at = clock(ctx.locale, project.snapshot_at);
  return at.known ? hubText(ctx.locale, "desk_status.snapshot", {time: at.short})
    : hubText(ctx.locale, "desk_status.snapshot_unknown");
}

const TONES = Object.freeze({waiting_you: "amber", queue_confirmation: "amber", running: "ion"});

//: A message takes the parameters its text names and no other: the status carries facts (a queue
//: position, the reason a run stalled) that a given wording may not use.
function statusText(locale, word) {
  const id = `desk_status.${word.key}`;
  return hubText(locale, id, Object.fromEntries(paramsOf(id).map((name) =>
    [name, String(word.params[name])])));
}

function snapshotNote(locale, word) {
  if (typeof word.params.snapshot_at !== "string") return null;
  const at = clock(locale, word.params.snapshot_at);
  return at.known ? hubText(locale, "desk_status.snapshot", {time: at.short})
    : hubText(locale, "desk_status.snapshot_unknown");
}

//: The title of a task; two tasks may share one, and a title names nothing, so a repeated or an
//: unreadable title carries the tail of its id.
function titleOf(locale, tasks, task) {
  const named = text(task.title) || hubText(locale, "desk_status.task_unreadable");
  const repeated = tasks.filter((one) => one.task?.title === task.title).length > 1;
  const id = text(task.task_id);
  return (repeated || task.unreadable) && id !== null ? `${named} · ${id.slice(-8)}` : named;
}

/**
 * The tasks of a project, one row each: `{task_id, run_id, title, text, tone, snapshot}`. The word is
 * `taskStatus` of the shared module over the row's raw fields, said in the reader's language; the
 * snapshot is the caption of a project read from a snapshot (null for a live one).
 */
export function taskRows(project, ctx) {
  if (!isObject(project)) return [];
  const all = rows(project.tasks);
  const entries = isObject(project.task_queue) ? rows(project.task_queue.entries) : [];
  return all.map((one) => {
    const task = isObject(one.task) ? one.task : {};
    const run = isObject(one.run) ? one.run : null;
    const entry = run === null ? null : entries.find((held) => held.run_id === run.run_id) ?? null;
    const word = taskStatus({task: one.task, run, automation: one.automation ?? null, entry,
      attention: one.attention ?? null, data: project.data, snapshot_at: project.snapshot_at});
    return {task_id: text(task.task_id), run_id: run === null ? null : text(run.run_id),
      title: titleOf(ctx.locale, all, task), text: statusText(ctx.locale, word),
      tone: Object.hasOwn(TONES, word.key) ? TONES[word.key] : null,
      snapshot: snapshotNote(ctx.locale, word)};
  });
}

// -- what waits for you -----------------------------------------------------------------------------

function sinceText(locale, since) {
  const at = clock(locale, since.at);
  if (since.kind === "waiting") {
    return {text: hubText(locale, "desk_status.since_waiting", {time: at.short}), exact: at.exact};
  }
  return {text: at.known ? hubText(locale, "desk_status.since_observed", {time: at.short})
    : hubText(locale, "desk_status.since_observed_unknown"), exact: at.exact};
}

function itemRow(project, item, ctx) {
  const {locale} = ctx, since = sinceText(locale, item.since);
  const task = rows(project.tasks).map((one) => one.task).find((held) => isObject(held)
    && held.task_id === item.task_id);
  const reason = hubText(locale, `desk_status.${item.key}`), name = String(project.name ?? "");
  const words = task === undefined
    ? hubText(locale, "hub.waiting.row_project", {project: name, reason, since: since.text})
    : hubText(locale, "hub.waiting.row_task", {project: name, reason, since: since.text,
      task: titleOf(locale, rows(project.tasks), task)});
  return {key: `${item.project_id}/${item.run_id ?? ""}/${item.reason}`,
    project_id: item.project_id, task_id: item.task_id, run_id: item.run_id,
    gate_id: item.gate_id, reason: item.reason, text: words, exact: since.exact,
    note: mutedNote(project, ctx)};
}

/**
 * Everything that waits for a person, across the projects, in the order of the projects and then of
 * the shared module's table. `noticed` maps a project id to the moment this page first saw it have
 * something waiting (`noticedMap`): the time given for a reason the hub dated by nothing.
 */
export function attentionList(projects, noticed, ctx) {
  const list = [];
  for (const project of rows(projects)) {
    const observed = text(noticed?.[project.project_id]);
    for (const item of attentionItems({...project, observed_at: observed})) {
      list.push(itemRow(project, item, ctx));
    }
  }
  return list;
}

/**
 * The moment this page first saw each project with something waiting: the first sight stands while
 * the project keeps something waiting, and is dropped once it has nothing. The hub has no moment for
 * the reasons that come from grants, the queue and the project's own state; this page says when it
 * first saw them, from the hub's `computed_at`, never from its own clock.
 */
export function noticedMap(previous, projects, computedAt) {
  const next = {};
  for (const project of rows(projects)) {
    if (attentionItems(project).length === 0) continue;
    const held = text(previous?.[project.project_id]) ?? text(computedAt);
    if (held !== null) next[project.project_id] = held;
  }
  return Object.freeze(next);
}

/** How many items wait for a person. */
export const waitingCount = (list) => list.length;

/** The number of items per project id. */
export function waitingByProject(list) {
  const counts = {};
  for (const item of list) counts[item.project_id] = (counts[item.project_id] ?? 0) + 1;
  return counts;
}

// -- drawing ----------------------------------------------------------------------------------------

/** An element with attributes (`text` and `className` are the two that are not set as attributes). */
export function node(tag, attrs = {}, children = []) {
  const made = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (name === "text") made.textContent = value;
    else if (name === "className") made.className = value;
    else made.setAttribute(name, value);
  }
  made.append(...children);
  return made;
}

const button = (key, label, onClick, extra = {}) => {
  const made = node("button", {type: "button", "data-focus": key, text: label, ...extra});
  made.addEventListener("click", onClick);
  return made;
};

//: An action that cannot be done now is drawn beside the reason, never as a button that does nothing.
function blockedControl(view, action, reason) {
  return node("span", {className: "hub-blocked"}, [node("button", {type: "button",
    className: "hub-project__act", disabled: "", "aria-disabled": "true", "data-action": action.id,
    text: action.label}), node("small", {className: "hub-why", text: reason})]);
}

/**
 * The control of one action of a project. «Снять флаг» is not a write of the hub's: it is a link to the
 * project's own desk at the block that holds the flag (spec 4.3.4), so it is a link when the desk runs
 * and is blocked, with its reason, when it does not. Every other action is a press and a call to
 * `handlers.onAct`; `view` is `{locale, prefs, hubPort}`.
 */
export function actionControl(view, project, action, handlers, prefix) {
  if (action.id === "clear_flag") {
    const link = deskLink(project, {panel: "continue"}, view.prefs, view.hubPort);
    return link === null
      ? blockedControl(view, action, hubText(view.locale, "hub.act.clear_flag_blocked"))
      : node("a", {href: link, target: "_blank", rel: "noopener", className: "hub-project__act",
        "data-action": action.id, text: action.label});
  }
  return button(`${prefix}:${project.project_id}:${action.id}`, action.label,
    () => handlers.onAct(action, project), {className: "hub-project__act",
      "data-action": action.id});
}

function actionButtons(view, project, said, handlers) {
  return said.actions.map((action) => actionControl(view, project, action, handlers, "act"));
}

function menuBlock(view, ctx, project, handlers) {
  const items = menuItems(project);
  if (items.length === 0) return [];
  const opened = view.menu === project.project_id, {locale} = ctx;
  const toggle = button(`menu:${project.project_id}`, hubText(locale, "hub.act.menu"),
    () => handlers.onMenu(opened ? null : project.project_id), {className: "hub-project__menu",
      "aria-expanded": String(opened),
      "aria-label": hubText(locale, "hub.rail.menu", {name: String(project.name ?? "")})});
  const entry = (item) => {
    const label = hubText(locale, item.key);
    return node("li", {}, [button(`act:${project.project_id}:${item.id}`, label,
      () => handlers.onAct({id: item.id, target: item.target, label, confirm: null}, project))]);
  };
  const list = opened ? [node("ul", {className: "hub-project__items", "data-menu": ""},
    items.map(entry))] : [];
  return [toggle, ...list];
}

function taskButton(view, project, task, handlers) {
  const made = button(`task:${project.project_id}:${task.task_id}`, "", () => handlers.onOpen({
    project_id: project.project_id, task_id: task.task_id, run_id: task.run_id, gate_id: null}),
  {className: "hub-task", "data-task-id": task.task_id, "data-tone": task.tone,
    "aria-pressed": String(view.selection.task_id === task.task_id)});
  made.append(node("strong", {className: "hub-task__title", text: task.title}),
    node("span", {className: "hub-task__state", text: task.text}),
    ...(task.snapshot === null ? [] : [node("small", {className: "hub-task__snapshot",
      text: task.snapshot})]));
  return made;
}

function tasksBlock(view, ctx, project, handlers) {
  const tasks = taskRows(project, ctx);
  if (tasks.length === 0) {
    return [node("p", {className: "hub-project__none", text: hubText(ctx.locale,
      "hub.rail.tasks_none")})];
  }
  return [node("ul", {className: "hub-tasks", "data-tasks": ""}, tasks.map((task) =>
    node("li", {}, [taskButton(view, project, task, handlers)])))];
}

function headOf(ctx, project, selected, count, handlers) {
  const badge = count === 0 ? [] : [node("span", {className: "hub-project__badge",
    "data-badge": "", "aria-label": hubText(ctx.locale, "hub.rail.badge", {count: String(count)}),
    text: `◆ ${count}`})];
  return node("div", {className: "hub-project__head"}, [button(`project:${project.project_id}`,
    String(project.name ?? project.folder ?? ""), () => handlers.onSelect(project.project_id),
    {className: "hub-project__name", "aria-pressed": String(selected)}), ...badge]);
}

function projectBlock(view, ctx, project, byProject, handlers) {
  const said = projectLine(project, ctx), note = mutedNote(project, ctx);
  const selected = view.selection.project_id === project.project_id;
  const head = headOf(ctx, project, selected, byProject[project.project_id] ?? 0, handlers);
  return node("li", {className: "hub-project", "data-project-id": project.project_id,
    "data-working": project.working, "data-state": project.state,
    "data-muted": String(project.data !== "live"), "data-selected": String(selected)}, [head,
    node("p", {className: "hub-project__line", "data-tone": said.tone, text: said.text,
      title: said.hint}),
    ...(note === null ? [] : [node("p", {className: "hub-project__note", text: note})]),
    node("div", {className: "hub-project__actions"},
      [...actionButtons(view, project, said, handlers), ...menuBlock(view, ctx, project, handlers)]),
    ...(selected ? tasksBlock(view, ctx, project, handlers) : [])]);
}

function waitingBlock(ctx, list, handlers) {
  const row = (item) => node("li", {}, [button(`waiting:${item.key}`, item.text,
    () => handlers.onOpen({project_id: item.project_id, task_id: item.task_id,
      run_id: item.run_id, gate_id: item.gate_id}),
    {className: "hub-waiting__item", "data-reason": item.reason, title: item.exact})]);
  const body = list.length === 0
    ? [node("p", {className: "hub-waiting__none", text: hubText(ctx.locale, "hub.waiting.none")})]
    : [node("ul", {className: "hub-waiting__list"}, list.map(row))];
  return node("section", {className: "hub-waiting", "data-waiting-list": ""},
    [node("h2", {className: "hub-rail__head", text: hubText(ctx.locale, "hub.waiting.heading")}),
      ...body]);
}

/**
 * Draw the column into `mount`: the heading and the count of what waits, one block per project (the
 * chosen one opens into its tasks) and the list of what waits for you. `view` is `{locale, projects,
 * activeId, queue, selection: {project_id, task_id}, menu, noticed}` and `handlers` is `{onSelect,
 * onOpen, onAct, onMenu}`; a press is a call to one of them.
 */
export function mountRail(mount, view, handlers) {
  const ctx = {locale: view.locale, projects: view.projects, activeId: view.activeId,
    queue: view.queue};
  const list = attentionList(view.projects, view.noticed, ctx);
  const all = rows(view.projects), byProject = waitingByProject(list);
  const head = node("h2", {className: "hub-rail__head"}, [
    node("span", {text: hubText(ctx.locale, "hub.rail.heading", {count: String(all.length)})}),
    node("span", {className: "hub-rail__count", "data-waiting": "",
      text: hubText(ctx.locale, "hub.rail.waiting", {count: String(waitingCount(list))})})]);
  const body = all.length === 0
    ? node("p", {className: "hub-rail__none", text: hubText(ctx.locale, "hub.rail.none")})
    : node("ul", {className: "hub-rail__projects"}, all.map((project) =>
      projectBlock(view, ctx, project, byProject, handlers)));
  mount.replaceChildren(head, body, waitingBlock(ctx, list, handlers));
}
