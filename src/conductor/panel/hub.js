"use strict";
// The hub page's boot module: it reads the page's address, says the frame in the reader's language
// and draws what the page holds. It is the one module of the hub that may touch the platform (the
// language the browser prefers), the wire and the clock; the rest of the page is values and text
// nodes. Every word comes from `hub-copy.js`, and the page imports neither the Studio's catalogue nor
// its view helper (spec 4.1.10).
//
// The address holds identifiers and interface words only (spec 4.5.2): the page reads and writes
// `lang` and `theme` through the shared `desk-hash.js`, with `history.replaceState` (which does not
// fire a `hashchange`), and never puts a token, a path or a line of text in it.
import {preferenceHash, readPreferences} from "./desk-hash.js";
import {hubText} from "./hub-copy.js";
import {mountRail, node} from "./hub-rail.js";
import {mountCenter, mountSide} from "./hub-stub.js";

const byId = (id) => document.getElementById(id);
const THEMES = Object.freeze([null, "dark", "light"]);

//: What the page holds. The lists are what the hub last said, and stay empty until a read lands.
const state = {locale: "en", theme: null, projects: [], activeId: null, queue: [], noticed: {},
  selection: {project_id: null, task_id: null, run_id: null, gate_id: null}, menu: null,
  limits: null, status: ""};

// -- the language and the theme ---------------------------------------------------------------

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

function remember() {
  history.replaceState(null, "", preferenceHash(location.hash, {locale: state.locale,
    theme: state.theme}));
}

function choose(change) {
  Object.assign(state, change);
  remember();
  render();
}

// -- the top bar ----------------------------------------------------------------------------------

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

function topActions() {
  const {locale} = state;
  const themes = THEMES.map((value) => [value, hubText(locale, `hub.theme.${value ?? "system"}`)]);
  byId("hubActions").replaceChildren(
    blocked("new-task", hubText(locale, "hub.new_task"), hubText(locale, "hub.new_task.blocked")),
    blocked("add-project", hubText(locale, "hub.add_project"),
      hubText(locale, "hub.add_project.blocked")),
    segment("lang", hubText(locale, "hub.lang.label"), [["en", "EN"], ["ru", "RU"]], locale,
      (value) => choose({locale: value})),
    segment("theme", hubText(locale, "hub.theme.label"), themes, state.theme,
      (value) => choose({theme: value})));
  byId("hubPath").textContent = hubText(locale, "hub.path.none");
}

// -- drawing ----------------------------------------------------------------------------------------

//: A pass replaces what it draws, so the control that had focus is found again by its key.
function render() {
  const held = document.activeElement?.dataset?.focus ?? null;
  applyAppearance();
  topActions();
  const view = {locale: state.locale, theme: state.theme, prefs: {locale: state.locale,
    theme: state.theme}, hubPort: location.port, projects: state.projects, activeId: state.activeId,
  queue: state.queue, selection: state.selection, menu: state.menu, noticed: state.noticed,
  limits: state.limits, now: Date.now()};
  const handlers = {onSelect: () => {}, onOpen: () => {}, onAct: () => {}, onMenu: () => {}};
  mountRail(byId("hubRail"), view, handlers);
  mountCenter(byId("hubCenter"), view, handlers);
  mountSide(byId("hubSide"), view, handlers);
  byId("hubStatus").textContent = state.status;
  if (held !== null) {
    document.querySelector(`[data-focus="${CSS.escape(held)}"]`)?.focus();
  }
}

function boot() {
  const preferences = readPreferences(location.hash, navigator.language);
  Object.assign(state, {locale: preferences.locale, theme: preferences.theme});
  render();
}

boot();
