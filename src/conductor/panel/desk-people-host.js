"use strict";
// One owner for the desk's quota timer and the People panel. All readings pass
// through the shared project-bound transport; a hidden or disconnected desk
// schedules nothing and a retired answer never reaches either surface.
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {instantText} from "./desk-time.js";
import {projectRuns, projectProviders} from "./studio-model.js";
import {participantsOf} from "./studio-runread.js";
import {NO_QUOTAS, projectQuotas, reduceQuotas} from "./studio-quotas-model.js";
import {quotaFlow} from "./studio-quotaflow.js";
import {quotaSection} from "./studio-quotas.js";
import {mountAgents} from "./studio-people.js";
import {path} from "./desk-transport.js";

const PROJECT = /^[0-9a-f]{32}$/;
const SNAPSHOT = ["project_id", "taken_at"];
const BASE = ["as_of", "max_age_seconds", "providers", "snapshots"];
const words = (locale, key, values) => localize({locale: locale()}, key, values);

function admitted(payload, locale) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)
      || Object.getPrototypeOf(payload) !== Object.prototype) return null;
  const keys = Object.keys(payload).sort().join(",");
  const base = BASE.slice().sort().join(",");
  const view = [...BASE, "hub_snapshot"].sort().join(",");
  if (keys !== base && keys !== view) return null;
  let snapshot = undefined;
  if (keys === view) {
    snapshot = payload.hub_snapshot;
    if (snapshot !== null && (typeof snapshot !== "object" || Array.isArray(snapshot)
        || Object.getPrototypeOf(snapshot) !== Object.prototype
        || Object.keys(snapshot).sort().join(",") !== SNAPSHOT.slice().sort().join(",")
        || !PROJECT.test(snapshot.project_id)
        || !instantText(locale(), snapshot.taken_at).known)) return null;
  }
  const clean = Object.fromEntries(BASE.map((key) => [key, payload[key]]));
  return projectQuotas(clean, {allowEmptySnapshots: snapshot !== undefined}) === null
    ? null : {clean, snapshot};
}

function sourceLine(snapshot, locale) {
  if (snapshot === undefined) return null;
  if (snapshot === null) return words(locale, "desk.quota.view_empty");
  return words(locale, "desk.quota.view_snapshot", {
    time: instantText(locale(), snapshot.taken_at).short});
}

function compact(row, providers, locale) {
  const names = row.binding_ids.map((id) => providers.get(id) ?? id).join(", ");
  let value = words(locale, "desk.quota.no_data");
  if (row.state === "observed" && row.freshness === "current") {
    if (Array.isArray(row.balances)) {
      value = row.balances.map((balance) => `${words(locale, "desk.quota.balance")}: `
        + `${balance.total_balance} ${balance.currency}`).join(" · ") || value;
    } else {
      const current = row.windows.filter((window) => window.freshness === "current"
        && window.remaining_percent !== null);
      const limiting = current.sort((left, right) => left.remaining_percent - right.remaining_percent
        || (Date.parse(left.resets_at) || Infinity) - (Date.parse(right.resets_at) || Infinity))[0];
      if (limiting) value = `${words(locale, current.length > 1
        ? "desk.quota.lowest_remaining" : "desk.quota.remaining")}: `
        + `${limiting.remaining_percent}%` + (limiting.resets_at === null ? ""
          : ` · ${words(locale, "desk.quota.resets")}: `
            + instantText(locale(), limiting.resets_at).short);
    }
  } else if (row.freshness === "stale") value = words(locale, "desk.quota.stale");
  return element("li", {className: "desk-quota__account", "data-quota-bindings": row.binding_ids.join(" "),
    text: `${names}: ${value}`});
}

export function createPeopleHost({mount, pult, door, locale, onForeign}) {
  let disposed = false, connected = false, open = false, rosterEpoch = 0;
  let rosterPhase = "empty", rosterLoaded = false, providers = [], snapshot = undefined;
  const sources = new WeakMap();
  let state = Object.freeze({quotas: NO_QUOTAS});
  let latestRun = null;
  const heading = element("h2"), sourceNote = element("p", {className: "desk-quota__source"});
  const rosterNote = element("p", {role: "status"}), panel = element("div");
  const alive = () => !disposed;
  const quotaTime = (at) => instantText(locale(), at).short;
  const shownQuotas = () => snapshot === null && state.quotas.phase === "ready"
    && state.quotas.payload?.snapshots.length === 0
    ? {phase: "no_data", payload: null} : state.quotas;

  async function read(target, stop) {
    try { return await door.readJson(target, stop); }
    catch (error) {
      if (error instanceof Error && error.message === "project_mismatch") onForeign();
      throw error;
    }
  }

  function renderPult() {
    if (disposed) return;
    const quotas = shownQuotas(), payload = quotas.payload;
    const body = [element("h3", {text: words(locale, "desk.quota.head")})];
    const source = sourceLine(snapshot, locale);
    if (source !== null) body.push(element("p", {className: "desk-quota__source", text: source}));
    if (quotas.phase !== "ready") body.push(element("p", {className: "desk-quota__state",
      text: words(locale, `desk.quota.${quotas.phase}`)}));
    if (payload === null || payload.snapshots.length === 0) {
      if (quotas.phase !== "no_data") body.push(element("p", {
        text: words(locale, "desk.quota.no_data")}));
    } else {
      const names = new Map(payload.providers.map((row) => [row.provider_id, row.display_name]));
      body.push(element("ul", {className: "desk-quota__list"},
        payload.snapshots.map((row) => compact(row, names, locale))));
    }
    pult.querySelector("[data-desk-quotas]")?.remove();
    pult.append(element("section", {className: "desk-quota", "data-desk-quotas": "",
      "data-quota-phase": quotas.phase}, body));
  }

  function render(run = latestRun) {
    if (disposed) return;
    latestRun = run;
    renderPult();
    if (!open) return;
    if (!mount.contains(panel)) mount.replaceChildren(heading, sourceNote, rosterNote, panel);
    heading.textContent = words(locale, "desk.people");
    rosterNote.hidden = rosterPhase === "ready";
    rosterNote.textContent = rosterNote.hidden ? "" : words(locale, `desk.people.${rosterPhase}`);
    const source = sourceLine(snapshot, locale);
    sourceNote.hidden = source === null;
    sourceNote.textContent = source ?? "";
    panel.hidden = !rosterLoaded;
    if (!rosterLoaded) return;
    const people = {locale: locale(), quotaTime, hideStaleQuotas: true,
      quotas: shownQuotas(), providers,
      agents: {phase: run?.phase ?? "empty", participants: run?.detail
        ? participantsOf(run.detail) : []}};
    mountAgents(panel, people, {refreshAgents: refreshRoster, refreshQuotas: flow.refreshQuotas});
  }

  const flow = quotaFlow({read: async (target, stop) => {
    const payload = await read(target, stop);
    const settled = admitted(payload, locale);
    if (settled === null) throw new Error("quota_unreadable");
    sources.set(settled.clean, settled.snapshot);
    return settled.clean;
  }, dispatch: (event) => {
    if (!alive()) return;
    if (event.type === "quotas-loaded") snapshot = sources.get(event.payload);
    state = reduceQuotas(state, {...event, allowEmptySnapshots: snapshot !== undefined});
    render();
  }, enabled: () => alive() && connected && !document.hidden,
  stop: () => new AbortController(), cancel: (timer) => clearTimeout(timer),
  schedule: (callback) => setTimeout(callback, 60000)});

  async function refreshRoster() {
    if (disposed || !open) return;
    const asked = ++rosterEpoch;
    rosterPhase = "loading";
    render();
    try {
      const payload = await read(path.runs());
      const settled = projectRuns(payload);
      const rows = projectProviders(payload?.providers);
      if (settled === null || rows.length !== payload.providers.length) throw new Error("roster_unreadable");
      if (disposed || asked !== rosterEpoch || !open) return;
      providers = payload.providers;
      rosterLoaded = true;
      rosterPhase = "ready";
    } catch (_error) {
      if (disposed || asked !== rosterEpoch || !open) return;
      rosterPhase = "failed";
    }
    render();
  }

  function show(value) {
    if (disposed || open === value) return;
    open = value;
    if (!open) { rosterEpoch += 1; mount.replaceChildren(); }
    else if (rosterPhase !== "ready") void refreshRoster();
    render();
  }
  function connection(value) {
    if (disposed) return;
    connected = value;
    if (value) flow.syncQuotas();
    else flow.disconnectQuotas();
  }
  function suspend() { connection(false); }
  function dispose() {
    if (disposed) return;
    disposed = true;
    rosterEpoch += 1;
    flow.disposeQuotas();
    document.removeEventListener("visibilitychange", visible);
    mount.replaceChildren();
  }
  function visible() { if (!disposed) flow.syncQuotas(); }
  document.addEventListener("visibilitychange", visible);
  return Object.freeze({render, show, isOpen: () => open, connection, suspend, dispose});
}
