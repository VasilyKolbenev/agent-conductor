"use strict";
// The hub page's boot module: it reads the page's address, asks the hub for what a person sees, draws
// it, and sends what a person does. It is the one module of the hub page that may touch the platform
// (the language the browser prefers), the wire and the clock; the rest of the page is values and text
// nodes. Every word comes from `hub-copy.js`, and the page imports neither the Studio's catalogue nor
// its view helper (spec 4.1.10).
//
// The wire has three doors and no other. One reads (`GET` of the four routes of `READS`), one writes
// (`POST` of the fourteen targets of `WRITE_TARGETS`, each with the token the hub gave this page, an
// identifier built only from the grammar of 4.6.3, and a body of a fixed shape) and one stream brings
// frames. A frame is an identifier and nothing more: it is never a fact on the screen, it makes the
// page read the matching route again (reads of one route never overlap, and a burst is read once
// more, not once each). A press is shown as done only after the hub's answer and the read that follows
// it. The page never asks a child's server: that is the desk's business, in a window of its own.
//
// The address holds identifiers and interface words only (spec 4.5.2): `project`, `task`, `run`,
// `gate`, `lang` and `theme`, written by the shared grammar with `history.replaceState` (which does
// not fire a `hashchange`), and never a token, a path or a line of text.
import {deskHash, preferenceHash, readDeskHash, readPreferences} from "./desk-hash.js";
import {codeWords, hubText} from "./hub-copy.js";
import {confirmWords, deskLink, mountRail, node, noticedMap, projectLine, unlistedNotes}
  from "./hub-rail.js";
import {mountCenter, mountSide} from "./hub-stub.js";

const byId = (id) => document.getElementById(id);
const THEMES = Object.freeze([null, "dark", "light"]);
//: A read or a write that has not answered in this long is lost (answered `unknown`, never repeated).
const LIMIT_MS = 10000;
//: The pause before the stream is opened again after it was closed by an error, doubled each time.
const REOPEN_MS = Object.freeze({first: 1000, last: 30000});
//: The four reads the page may make, by name.
const READS = Object.freeze({
  session: "/hub/session",
  projects: "/hub/projects",
  limits: "/hub/limits",
  setup: "/hub/setup",
});
//: `HUB_WRITE_TARGETS` of spec 4.6.3: every write the page may make, and the route it writes.
const WRITE_TARGETS = Object.freeze({
  pickFolder: "/hub/dialogs/folder",
  pickCancel: "/hub/dialogs/{pick}/cancel",
  projectAdd: "/hub/projects",
  projectsHome: "/hub/setup/projects-home",
  toolPin: "/hub/tools/{tool}/pin",
  projectActivate: "/hub/projects/{project}/activate",
  projectView: "/hub/projects/{project}/view",
  projectStop: "/hub/projects/{project}/stop",
  projectRecover: "/hub/projects/{project}/recover",
  projectProviders: "/hub/projects/{project}/providers",
  projectForget: "/hub/projects/{project}/forget",
  loginRecover: "/hub/logins/{login}/recover",
  operationCancel: "/hub/operations/{operation}/cancel",
  queueOrder: "/hub/queue/order",
});
//: The grammar of each identifier a route may carry (spec 4.6.3): an id that does not fit is never
//: put in a path.
const IDS = Object.freeze({pick: /^pick-[0-9a-f]{32}$/, tool: /^(?:gh|git)$/,
  project: /^[0-9a-f]{32}$/, login: /^[0-9a-f]{64}$/, operation: /^operation-[0-9a-f]{32}$/});
//: The frames that make the page read again, by kind, and the read each makes.
const FRAMES = Object.freeze({projects: "projects", project: "projects", limits: "limits",
  setup: "setup"});
//: The states of a tool (`git`, `gh`) that ask a person to look.
const UNSETTLED = Object.freeze(["not_pinned", "changed", "too_old", "unreadable"]);

//: What the page holds. The lists are what the hub last said, and stay as they were when a read fails.
const state = {locale: "en", theme: null, projects: [], activeId: null, queue: [], computedAt: null,
  unlisted: [], noticed: {}, limits: null, setup: null, registryBad: false, readState: "loading",
  stream: "connecting", selection: {project_id: null, task_id: null, run_id: null, gate_id: null},
  menu: null, confirm: null, notice: null, busy: false, cancelFocus: false};
let token = null;
let tick = null;
let reopen = REOPEN_MS.first;

// -- the wire: one door to read, one to write, one stream ---------------------------------------

async function answerOf(response) {
  const payload = await response.json().catch(() => null);
  if (response.ok) return {status: "accepted", code: null, payload};
  const code = payload !== null && typeof payload === "object" && payload.error
    && typeof payload.error.code === "string" ? payload.error.code : "refused";
  return {status: "refused", code, payload};
}

const LOST = Object.freeze({status: "unknown", code: null, payload: null});

async function read(name) {
  try {
    return await answerOf(await fetch(READS[name], {cache: "no-store",
      credentials: "same-origin", headers: {Accept: "application/json"},
      signal: AbortSignal.timeout(LIMIT_MS)}));
  } catch (_error) {
    return LOST;
  }
}

//: A route with its identifiers filled in, each by its own grammar; one that does not fit throws.
function fill(pattern, params) {
  return pattern.replace(/\{([a-z]+)\}/g, (_found, name) => {
    const value = params[name];
    if (typeof value !== "string" || !IDS[name].test(value)) throw new Error("not an identifier");
    return value;
  });
}

async function write(target, params, body) {
  let path = null;
  try {
    path = fill(WRITE_TARGETS[target], params);
  } catch (_error) {
    return {status: "refused", code: "contract_invalid", payload: null};
  }
  try {
    return await answerOf(await fetch(path, {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-Conduct-CSRF": token},
      body: JSON.stringify(body), signal: AbortSignal.timeout(LIMIT_MS)}));
  } catch (_error) {
    return LOST;
  }
}

//: The write token of this page, asked for once, before the first write.
async function ensureSession() {
  if (token !== null) return;
  const answer = await read("session"), held = answer.payload;
  if (answer.status === "accepted" && held !== null && typeof held.csrf_token === "string") {
    token = held.csrf_token;
  }
}

// -- landing what was read --------------------------------------------------------------------------

const isList = (value) => Array.isArray(value);
const isObject = (value) => value !== null && typeof value === "object" && !isList(value);
const BAD_REGISTRY = Object.freeze(["registry_invalid", "registry_busy"]);
const NOTHING = Object.freeze({project_id: null, task_id: null, run_id: null, gate_id: null});

function landProjects(answer) {
  const held = answer.payload;
  if (answer.status !== "accepted" || !isObject(held) || !isList(held.projects)
      || !isList(held.project_queue)) {
    state.readState = "failed";
    state.registryBad = answer.status === "refused" && BAD_REGISTRY.includes(answer.code);
    return;
  }
  const projects = held.projects.filter(isObject);
  Object.assign(state, {projects, activeId: held.active_project_id ?? null,
    queue: held.project_queue.filter((id) => typeof id === "string"),
    computedAt: held.computed_at ?? null, readState: "ready", registryBad: false,
    unlisted: isList(held.unlisted_closing) ? held.unlisted_closing.filter(isObject) : [],
    noticed: noticedMap(state.noticed, projects, held.computed_at)});
  if (state.selection.project_id !== null
      && !projects.some((one) => one.project_id === state.selection.project_id)) {
    state.selection = NOTHING;
    writeAddress();
  }
}

function land(name, answer) {
  if (name === "projects") landProjects(answer);
  else if (answer.status === "accepted" && isObject(answer.payload)) state[name] = answer.payload;
  render();
}

const reading = {projects: {busy: false, again: false}, limits: {busy: false, again: false},
  setup: {busy: false, again: false}};

//: Read a route; while a read of it is out, ask for one more when it lands (never two at once).
async function refresh(name) {
  const slot = reading[name];
  if (slot.busy) {
    slot.again = true;
    return;
  }
  slot.busy = true;
  do {
    slot.again = false;
    land(name, await read(name));
  } while (slot.again);
  slot.busy = false;
}

const refreshAll = () => Promise.all(["projects", "limits", "setup"].map(refresh));

// -- the stream: frames are identifiers ------------------------------------------------------------

//: A frame the page takes: an object of a known kind whose identifiers fit their grammar.
function frameOf(data) {
  let frame = null;
  try {
    frame = JSON.parse(data);
  } catch (_error) {
    return null;
  }
  if (!isObject(frame) || !Object.hasOwn(FRAMES, frame.kind)) return null;
  const fits = frame.kind !== "project" || IDS.project.test(String(frame.project_id));
  return fits ? frame : null;
}

function openStream() {
  const stream = new EventSource("/hub/events");
  stream.onopen = () => {
    state.stream = "open";
    reopen = REOPEN_MS.first;
    render();
  };
  stream.onmessage = (event) => {
    const frame = frameOf(event.data);
    if (frame !== null) refresh(FRAMES[frame.kind]);
  };
  stream.onerror = () => {
    state.stream = "lost";
    render();
    if (stream.readyState !== 2) return;
    stream.close();
    setTimeout(openStream, reopen);
    reopen = Math.min(reopen * 2, REOPEN_MS.last);
  };
}

// -- the address, the language and the theme ------------------------------------------------------------

function writeAddress() {
  const {project_id: project, task_id: task, run_id: run, gate_id: gate} = state.selection;
  history.replaceState(null, "", preferenceHash(deskHash({project, task, run, gate}),
    {locale: state.locale, theme: state.theme}));
}

function applyAppearance() {
  const root = document.documentElement;
  root.lang = state.locale;
  if (state.theme === null) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", state.theme);
  document.title = hubText(state.locale, "hub.page_title");
  for (const holder of document.querySelectorAll("[data-i18n-label]")) {
    holder.setAttribute("aria-label", hubText(state.locale, holder.dataset.i18nLabel));
  }
}

function choose(change) {
  Object.assign(state, change);
  writeAddress();
  render();
}

function select(selection) {
  Object.assign(state, {selection, menu: null, notice: null});
  writeAddress();
  render();
}

// -- what a person presses ------------------------------------------------------------------------------

const asked = () => ({locale: state.locale, projects: state.projects, activeId: state.activeId,
  queue: state.queue});

//: The notice that follows a write: what the hub said, in words; a refusal in the clause of its code.
function noticeOf(answer) {
  if (answer.status === "accepted") return {key: "hub.notice.accepted", code: null};
  if (answer.status === "refused") return {key: "hub.notice.refused", code: answer.code};
  return {key: "hub.notice.unknown", code: null};
}

async function perform(action, project) {
  if (state.busy) return;
  Object.assign(state, {busy: true, confirm: null, menu: null});
  await ensureSession();
  const params = action.params ?? {project: project.project_id};
  const answer = await write(action.target, params, action.order ? {order: action.order} : {});
  Object.assign(state, {busy: false, notice: noticeOf(answer)});
  render();
  await refreshAll();
}

function act(action, project) {
  if (state.busy) return;
  if (action.confirm) {
    Object.assign(state, {confirm: {action, project_id: project.project_id}, menu: null,
      notice: null, cancelFocus: true});
    render();
    return;
  }
  state.notice = null;
  perform(action, project);
}

const handlers = Object.freeze({
  onSelect: (id) => select({project_id: id, task_id: null, run_id: null, gate_id: null}),
  onOpen: (nav) => select(nav),
  onAct: act,
  onMenu: (id) => {
    state.menu = id;
    render();
  },
});

// -- the top bar -------------------------------------------------------------------------------------------

const selected = () => state.projects.find((one) => one.project_id
  === state.selection.project_id);

const segment = (name, label, options, current, onPick) => node("span",
  {className: "hub-seg", role: "group", "aria-label": label}, options.map(([value, text]) => {
  const one = node("button", {type: "button", "data-focus": `seg:${name}:${value}`, text,
    "aria-pressed": String(value === current)});
  one.addEventListener("click", () => onPick(value));
  return one;
}));

//: A control that cannot be used is drawn beside the reason it cannot, never as a button that does
//: nothing when pressed.
function blocked(key, label, reason) {
  return node("span", {className: "hub-blocked"}, [node("button", {type: "button",
    "data-focus": key, className: "hub-action", disabled: "", "aria-disabled": "true",
    text: label}), node("small", {className: "hub-why", text: reason})]);
}

function newTaskControl() {
  const {locale} = state, project = selected();
  const link = project === undefined ? null : deskLink(project, {new: "task"},
    {locale, theme: state.theme}, location.port);
  return link === null ? blocked("new-task", hubText(locale, "hub.new_task"),
    hubText(locale, "hub.new_task.blocked"))
    : node("a", {href: link, target: "_blank", rel: "noopener", className: "hub-action",
      "data-primary": "true", "data-focus": "new-task", text: hubText(locale, "hub.new_task")});
}

//: The bar over a project opened for viewing: who is in progress, and the way to make this one so.
function viewBar() {
  const project = selected(), {locale} = state;
  if (project === undefined || project.working !== "view") return [];
  const active = state.projects.find((one) => one.project_id === state.activeId);
  const words = active === undefined ? hubText(locale, "hub.view.no_active")
    : hubText(locale, "hub.view.with_active", {name: String(active.name ?? "")});
  const start = projectLine(project, asked()).actions.find((one) => one.id === "activate");
  const button = start === undefined ? [] : [node("button", {type: "button",
    "data-focus": "view:activate", className: "hub-action", text: start.label})];
  button.forEach((one) => one.addEventListener("click", () => act(start, project)));
  return [node("span", {className: "hub-view"}, [node("span", {text: words}), ...button])];
}

function pathText() {
  const project = selected();
  if (project === undefined) return hubText(state.locale, "hub.path.none");
  const row = (isList(project.tasks) ? project.tasks : []).find((one) => isObject(one.task)
    && one.task.task_id === state.selection.task_id);
  return [String(project.name ?? project.folder ?? ""), row === undefined ? null
    : String(row.task.title ?? row.task.task_id), row === undefined ? null
    : state.selection.run_id].filter((part) => part !== null).join(" › ");
}

function topActions() {
  const {locale} = state;
  const themes = THEMES.map((value) => [value, hubText(locale, `hub.theme.${value ?? "system"}`)]);
  byId("hubActions").replaceChildren(newTaskControl(),
    blocked("add-project", hubText(locale, "hub.add_project"),
      hubText(locale, "hub.add_project.blocked")), ...viewBar(),
    segment("lang", hubText(locale, "hub.lang.label"), [["en", "EN"], ["ru", "RU"]], locale,
      (value) => choose({locale: value})),
    segment("theme", hubText(locale, "hub.theme.label"), themes, state.theme,
      (value) => choose({theme: value})));
  byId("hubPath").textContent = pathText();
}

// -- notices, the confirmation and the status line -------------------------------------------------

function banner(name, words, extras = [], exact = "") {
  return node("div", {className: "hub-banner", "data-banner": name}, [node("span",
    {text: words, title: exact === "" ? null : exact}), ...extras]);
}

function loginBanner(one) {
  const press = node("button", {type: "button", "data-focus": `login:${one.login_key}`,
    text: hubText(state.locale, "hub.act.recover_login")});
  press.addEventListener("click", () => perform({id: "recover_login", target: "loginRecover",
    params: {login: one.login_key}, confirm: null}, null));
  return banner("login", hubText(state.locale, "hub.banner.login", {harness: String(one.harness)}),
    [press]);
}

function setupBanners() {
  const setup = state.setup, {locale} = state;
  if (!isObject(setup)) return [];
  const tools = isObject(setup.tools) ? Object.values(setup.tools) : [];
  const small = (key) => node("small", {text: hubText(locale, key)});
  const list = [];
  if (setup.profile === "absent") {
    list.push(banner("profile", hubText(locale, "hub.banner.profile_absent"),
      [small("hub.banner.profile_how")]));
  } else if (setup.profile === "invalid") {
    list.push(banner("profile", hubText(locale, "hub.banner.profile_invalid")));
  }
  if (tools.some((one) => isObject(one) && UNSETTLED.includes(one.state))) {
    list.push(banner("tools", hubText(locale, "hub.banner.tools")));
  }
  list.push(...(isList(setup.logins) ? setup.logins : []).filter((one) => isObject(one)
    && one.state === "unclosed").map(loginBanner));
  if (isObject(setup.projects_home) && setup.projects_home.state === "invalid") {
    list.push(banner("home", hubText(locale, "hub.banner.home_invalid")));
  }
  if (setup.hub_job === "kill_on_close") {
    list.push(banner("job", hubText(locale, "hub.banner.job"), [small("hub.banner.job_how")]));
  }
  return list;
}

//: A project taken off the list that still owes its closing has no row to say so, yet it keeps every
//: next active project from starting. The action the hub names for it has no route (it is the add
//: dialog on the same folder), so it is drawn blocked beside the reason, like «＋ Добавить проект».
function unlistedBanners() {
  const {locale} = state, why = hubText(locale, "hub.unlisted.relist_blocked");
  return unlistedNotes(state.unlisted, {locale}).map((one) => banner("unlisted", one.text,
    one.relist ? [blocked(`unlisted:${one.key}`, hubText(locale, "hub.act.relist"), why)] : [],
    one.exact));
}

function banners() {
  const registry = state.registryBad ? [banner("registry",
    hubText(state.locale, "hub.banner.registry"))] : [];
  byId("hubBanners").replaceChildren(...registry, ...setupBanners(), ...unlistedBanners());
}

function confirmation() {
  const held = state.confirm;
  const project = held === null ? undefined : state.projects.find((one) => one.project_id
    === held.project_id);
  if (project === undefined) {
    byId("hubConfirm").replaceChildren();
    return;
  }
  const {locale} = state;
  const yes = node("button", {type: "button", "data-focus": "confirm:yes", "data-primary": "true",
    text: held.action.label});
  const no = node("button", {type: "button", "data-focus": "confirm:no",
    text: hubText(locale, "hub.confirm.cancel")});
  yes.addEventListener("click", () => perform(held.action, project));
  no.addEventListener("click", () => {
    state.confirm = null;
    render();
  });
  byId("hubConfirm").replaceChildren(node("div", {className: "hub-confirm__box"},
    [...confirmWords(held.action.confirm, project, asked()).map((text) => node("p", {text})),
      node("div", {className: "hub-confirm__buttons"}, [yes, no])]));
}

function statusText() {
  const {locale} = state, held = state.notice;
  if (held !== null) {
    return hubText(locale, held.key, held.key === "hub.notice.refused"
      ? {reason: codeWords(locale, held.code)} : {});
  }
  if (state.readState === "failed") return hubText(locale, "hub.status.failed");
  if (state.stream === "lost") return hubText(locale, "hub.status.stream_lost");
  return hubText(locale, state.readState === "ready" ? "hub.status.ready" : "hub.status.loading");
}

// -- drawing ----------------------------------------------------------------------------------------

//: While the chosen project is stopping, the stub counts down: the page asks to be drawn again in a
//: second, once, and only while there is something to count.
function countdown() {
  clearTimeout(tick);
  tick = null;
  const project = selected();
  const at = project === undefined || project.state !== "stopping" ? NaN
    : Date.parse(project.drain_deadline ?? "");
  if (at > Date.now()) tick = setTimeout(render, 1000);
}

//: A pass replaces what it draws, so the control that had focus is found again by its key.
function render() {
  const held = document.activeElement?.dataset?.focus ?? null;
  applyAppearance();
  topActions();
  const view = {locale: state.locale, theme: state.theme, prefs: {locale: state.locale,
    theme: state.theme}, hubPort: location.port, projects: state.projects,
  activeId: state.activeId, queue: state.queue, selection: state.selection, menu: state.menu,
  noticed: state.noticed, limits: state.limits, now: Date.now()};
  mountRail(byId("hubRail"), view, handlers);
  mountCenter(byId("hubCenter"), view, handlers);
  mountSide(byId("hubSide"), view, handlers);
  banners();
  confirmation();
  byId("hubStatus").textContent = statusText();
  byId("hubShell").dataset.state = state.readState;
  const key = state.cancelFocus ? "confirm:no" : held;
  state.cancelFocus = false;
  if (key !== null) document.querySelector(`[data-focus="${CSS.escape(key)}"]`)?.focus();
  countdown();
}

async function boot() {
  const preferences = readPreferences(location.hash, navigator.language);
  const address = readDeskHash(location.hash);
  Object.assign(state, {locale: preferences.locale, theme: preferences.theme,
    selection: {project_id: address.project, task_id: address.task, run_id: address.run,
      gate_id: address.gate}});
  render();
  await ensureSession();
  await refreshAll();
  openStream();
}

boot();
