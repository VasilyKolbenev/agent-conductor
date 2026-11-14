"use strict";
import {element} from "./command-view.js";
import {readDeskHash, readPreferences} from "./desk-hash.js";
import {createTransport, path} from "./desk-transport.js";
import {isId, projectRuns} from "./studio-model.js";
import {projectRunRead} from "./studio-situation.js";
import {projectTasks} from "./studio-tasks-model.js";
import {compareInstants} from "./studio-taskruns.js";
import {utilityDrawer} from "./studio-utilities.js";
import {word} from "./arachnid-copy.js";
import {harnesses, showHarnesses, showLimits, showMemory} from "./arachnid-panels.js";
import {arachnidConversation} from "./arachnid-conversation.js";
import {findReviewSource} from "./arachnid-review-source.js";
import {manualReviewEvidence} from "./arachnid-manual-review.js";
import {atlasPlanning} from "./arachnid-planning.js";
import {attachLayout} from "./arachnid-layout.js";
import {attachPalette} from "./arachnid-palette.js";
import {createNextAction} from "./arachnid-next.js";

const $ = id => document.getElementById(id);
const fields = () => new URLSearchParams(location.hash.slice(1));

function legacy() {
  if (!fields().has("screen")) return false;
  history.replaceState(history.state, "", "/panel/studio.html" + location.hash);
  location.reload();
  return true;
}

function boot() {
  let locale, theme, identity, runs = [], tasks = [], providers = [], current = null, detail = null;
  let listState = "loading", detailState = "", connected = false, stream = null;
  let listEpoch = 0, detailEpoch = 0, sideEpoch = 0, identityEpoch = 0, side = null;
  let detailStop, catalogStop, opener, memberFilter, members = [], checking = false, again = false;
  let shownProof = null;
  const leads = new Map();
  const drafts = new Map();
  const adviceRefs = new Map();
  let external = [], utilityEpoch = 0, reconnecting = false, linkEpoch = 0;
  const tr = key => word(locale, key);
  const transport = createTransport(() => locale, () => identity?.project_id ?? claimed());
  const utility = utilityDrawer($("studioUtilities"), {
    project: () => transport.readJson(path.project()), read: () => transport.readJson(path.utilities()),
    bind: id => identity !== null && identity !== undefined && id === identity.project_id && !foreign(),
    post: body => transport.submit("utilities", null, body),
    connected: () => connected && listState === "ready" && !foreign(),
    locale: () => locale, origin: "http://127.0.0.1:" + location.port,
    newId: () => "x-" + crypto.randomUUID(), question: () => $("command").value,
    copy: text => navigator.clipboard.writeText(text),
  });
  const planning = atlasPlanning($("planner"), {
    readJson: route => transport.readJson(route),
    write: (target, subject, body) => transport.submit(target, subject, body),
    valid: (projectId, sessionId, ref) => connected && listState === "ready" && !foreign()
      && identity?.mode === "active" && identity.project_id === projectId
      && current?.kind === "new" && key(current) === sessionId && leads.get(sessionId) === "codex"
      && !fields().has("task") && !fields().has("session") && (fields().get("new") || "1") === current.id
      && claimForAdvice(fields()) === ref && (!fields().has("advice") || ref !== null),
    saveReference: ref => {
      const params = fields();
      if (ref) { params.set("advice", ref.runId); adviceRefs.set(key(current), ref.runId); }
      else { params.delete("advice"); adviceRefs.delete(key(current)); }
      params.set("new", current.id); params.set("project", identity.project_id);
      history.replaceState(history.state, "", "#" + params);
    },
    openRun: (run, task) => { address({kind: "run", id: run, task}); refresh(); },
  });
  const scene = arachnidConversation($("chat"), $("inspection"), {
    reviewSource: (sessionId, controller) => {
      const epoch = linkEpoch, projectId = identity?.project_id;
      const valid = () => !controller.signal.aborted && connected && epoch === linkEpoch
        && identity?.project_id === projectId && !foreign() && listState === "ready"
        && ["new", "task"].includes(current?.kind) && !current.bad
        && key(current) === sessionId && key(addressedSelection()) === sessionId;
      const catalog = new Map(sessions().filter(row => row.kind === "run" && !row.bad
          && row.task !== current?.task)
        .map(row => [row.id, row.task]));
      return findReviewSource({projectId, runIds: [...catalog.keys()], valid,
        taskForRun: id => catalog.get(id),
        readJson: route => transport.readJson(route, controller)});
    },
    reviewLinks: source => {
      const q = new URLSearchParams({session: source.runId, lang: locale});
      if (source.projectId) q.set("project", source.projectId);
      const session = "/#" + q;
      if (source.kind === "operator") q.set("reviewEvidence", source.documentId);
      else {
        q.set("proofNode", source.nodeId); q.set("proofAction", source.actionId);
        q.set("proofAttempt", source.attemptId);
      }
      return {session, attempt: "/#" + q};
    },
    planMessage: (sessionId, text) => planning.message(sessionId, text),
    stop: () => new AbortController(),
    readAttempt: (run, node, action, controller) =>
      transport.readJson(path.atlasAttempt(run, node, action), controller),
    inspect: opened => {
      if (opened) { side = "step"; ++sideEpoch; showAside("inspector"); }
      else if (side === "step") hideAside();
    },
    command: name => openPanel(name, $("command")),
  });
  const nextAction = createNextAction($("nextAction"), {
    valid: validRun, stop: () => new AbortController(),
    readAutomation: (run, stop) => transport.readJson(path.automation(run), stop),
    submit: (target, run, body) => {
      if (!["decisions", "automationPreview", "automationAuthorize"].includes(target)
          || identity?.mode !== "active" || !validRun(identity?.project_id, run, current?.task))
        return Promise.resolve({status: "refused", code: "project_mismatch"});
      return transport.submit(target, run, body);
    },
    refreshRun: run => { if (current?.kind === "run" && current.id === run) readRun(current); },
    id: kind => kind + "-" + crypto.randomUUID(),
    openStep: node => scene.openStep(current?.id, node),
  });
  const palette = attachPalette($("palette"), {
    catalog: paletteCatalog, choose: chooseCommand, locale: () => locale,
    stop: () => new AbortController(), restore: restoreOpener,
  });

  function addressedSelection() {
    const query = fields();
    const focus = ["session", "task", "new"].filter(name => query.has(name));
    if (focus.length > 1 || focus.some(name => query.getAll(name).length !== 1)) return null;
    if (!focus.length) return current;
    if (focus[0] === "new")
      return current?.kind === "new" && current.id === query.get("new") ? current : null;
    return requested(sessions());
  }
  function validRun(project, run, task) {
    const selected = addressedSelection();
    return connected && listState === "ready" && !detailState && !foreign()
      && identity?.project_id === project && current?.kind === "run" && !current.bad
      && selected?.kind === "run" && selected.id === run && selected.task === task
      && current.id === run && current.task === task && detail?.run?.run_id === run
      && detail?.config?.task?.id === task && detail?.task?.id === task;
  }
  function paletteCatalog() {
    if (!identity || foreign() || !connected || listState !== "ready"
        || key(addressedSelection()) !== key(current)) return [];
    const scope = identity.project_id;
    return [
      ...sessions().filter(row => !row.bad).map(row => ({kind: "session", id: key(row), scope,
        label: row.title || tr("newSession"), detail: row.id, keywords: [row.kind]})),
      ...members.map(m => ({kind: "harness", id: m.id, scope, label: m.label,
        detail: m.duty, keywords: [m.id]})),
      ...external.map(row => ({kind: "utility", id: row.utility_id, scope, label: row.label,
        detail: tr(row.mode === "manual" ? "manualTool" : "protocolTool"), keywords: []})),
      ...scene.paletteSteps().map(s => ({kind: "step", id: s.nodeId, scope: s.runId,
        label: s.title, detail: s.runId, keywords: [s.nodeId]})),
      {kind: "limits", id: "limits", scope, label: tr("limits"), detail: "",
        keywords: ["quota", "usage", "квота", "остаток"]},
      {kind: "memory", id: "memory", scope: scope + "/" + key(current),
        label: tr("memory"), detail: current?.title || "", keywords: ["history", "история"]},
    ];
  }
  function chooseCommand(entry) {
    const live = paletteCatalog().find(row => row.kind === entry.kind && row.id === entry.id
      && row.scope === entry.scope);
    if (!live) return false;
    navOpen(false);
    if (live.kind === "session") {
      const row = sessions().find(row => key(row) === live.id && !row.bad);
      if (!row) return false;
      address(row); $("command").focus({preventScroll: true});
    } else if (live.kind === "harness") openPanel("participants", $("paletteOpen"), live.id);
    else if (live.kind === "utility") utility.open(true, live.id);
    else if (live.kind === "step") return scene.openStep(live.scope, live.id);
    else openPanel(live.kind, $("paletteOpen"));
    return true;
  }

  function claimed() { return readDeskHash(location.hash).project; }
  function foreign() {
    const query = fields(), claim = claimed();
    return query.has("project") && (query.getAll("project").length !== 1 || !claim
      || (identity !== undefined && claim !== identity?.project_id));
  }
  function preferences() {
    const prefs = readPreferences(location.hash, navigator.language);
    locale = prefs.locale; theme = prefs.theme;
    document.documentElement.lang = locale;
    document.documentElement.dataset.theme = theme || "dark";
    $("language").value = locale;
    for (const [attr, name] of [["data-ar-label", "text"], ["data-ar-aria", "aria-label"],
      ["data-ar-placeholder", "placeholder"]]) {
      for (const node of document.querySelectorAll("[" + attr + "]")) {
        const label = tr(node.getAttribute(attr));
        if (name === "text") node.textContent = label;
        else node.setAttribute(name, label);
      }
    }
    $("retry").textContent = tr("retry");
  }
  function setPreference(key, value) {
    const params = fields(); params.set(key, value);
    history.replaceState(history.state, "", "#" + params);
    preferences(); paint(); utility.sync();
    if (side && side !== "step") openPanel(side, opener, memberFilter);
  }
  function address(row) {
    const params = fields();
    for (const name of ["session", "task", "new", "advice", "proofNode", "proofAction",
      "proofAttempt", "reviewEvidence"])
      params.delete(name);
    if (row.kind === "new" && adviceRefs.has(key(row))) params.set("advice", adviceRefs.get(key(row)));
    if (identity?.project_id) params.set("project", identity.project_id);
    params.set(row.kind === "run" ? "session" : row.kind, row.id);
    history.pushState(null, "", "#" + params); navigate();
  }
  function toolAddress(page, target) {
    const params = new URLSearchParams();
    for (const key of ["project", "lang", "theme"]) {
      if (fields().has(key)) params.set(key, fields().get(key));
    }
    if (identity?.project_id) params.set("project", identity.project_id);
    for (const [key, value] of Object.entries(target)) if (value) params.set(key, value);
    return "/panel/" + page + ".html#" + params;
  }
  function sessions() {
    if (listState === "foreign") return [];
    const taskMap = new Map(tasks.map(row => [row.task_id, row]));
    const linked = new Set(runs.map(row => row.taskId));
    return [...drafts.values(), ...runs.map(row => ({kind: "run", id: row.runId, time: row.createdAt || "",
      bad: row.unreadable, title: taskMap.get(row.taskId)?.title || row.runId, task: row.taskId})),
    ...tasks.filter(t => !linked.has(t.task_id)).map(t => ({kind: "task", id: t.task_id,
      time: t.created_at || "", title: t.title || t.task_id, bad: t.unreadable, task: t.task_id}))]
      .sort((a, b) => (a.time && b.time ? compareInstants(b.time, a.time)
        : Number(Boolean(b.time)) - Number(Boolean(a.time))) || a.id.localeCompare(b.id));
  }
  function requested(rows) {
    const q = fields(), keys = ["session", "task", "new"].filter(k => q.has(k));
    const blank = {kind: "new", id: "1"};
    if (!keys.length) return rows.find(row => row.kind === "run" && !row.bad)
      || rows.find(row => !row.bad) || blank;
    const key = keys[0], id = q.get(key);
    if (keys.length !== 1 || q.getAll(key).length !== 1) return null;
    if (key === "new") {
      if (drafts.has(id)) return drafts.get(id);
      if (id === "1") return blank;
      if (claimForAdvice(q) && /^[a-f0-9-]{36}$/.test(id)) {
        const row = {kind: "new", id, title: "", time: ""};
        drafts.set(id, row); return row;
      }
      return null;
    }
    if (!isId(id)) return null;
    return rows.find(row => key === "session" ? row.kind === "run" && row.id === id
      : row.task === id) || null;
  }
  function key(row) { return row ? row.kind + "/" + row.id : "missing"; }
  function claimForAdvice(q) {
    return identity?.project_id && q.get("project") === identity.project_id
      && q.getAll("advice").length === 1 && /^advice-[0-9a-f]{20}$/.test(q.get("advice"))
      ? q.get("advice") : null;
  }
  function switchTo(row) {
    if (key(current) !== key(row)) {
      ++detailEpoch; detailStop?.abort(); detail = null; detailState = "";
      if (side === "step") scene.close();
      hideAside();
    }
    current = row;
  }
  function navOpen(value) {
    $("workspace").classList.toggle("nav-open", value);
    $("menu").setAttribute("aria-expanded", String(value));
    syncLayers();
  }
  function syncLayers() {
    const hasMenu = $("menu").getClientRects().length > 0;
    if (!hasMenu) { $("workspace").classList.remove("nav-open"); $("menu").setAttribute("aria-expanded", "false"); }
    const nav = $("workspace").classList.contains("nav-open") && hasMenu;
    const sheet = !$("detail").hidden && $("sheetCloseLabel").getClientRects().length > 0;
    $("sidebar").inert = Boolean(!nav && (hasMenu || sheet));
    $("chat").inert = Boolean(nav || sheet);
    $("detail").inert = Boolean(nav);
    if (sheet && !nav && !$("detail").contains(document.activeElement) && !$("studioUtilities").open) {
      $("close").focus({preventScroll: true});
    }
  }
  function showAside(label) {
    navOpen(false); $("workspace").classList.add("with-detail"); $("detail").hidden = false;
    $("detailTitle").textContent = tr(label);
    syncLayers();
  }
  function hideAside() {
    side = null; ++sideEpoch; $("workspace").classList.remove("with-detail");
    $("detail").hidden = true; $("inspection").replaceChildren();
    syncLayers();
  }
  function restoreOpener(node) {
    const live = node?.isConnected ? node : [...$("harnesses").children, ...$("externalHarnesses").children]
      .find(b => node?.dataset.harness && b.dataset.harness === node.dataset.harness
        || node?.dataset.utility && b.dataset.utility === node.dataset.utility);
    const fallback = $("menu").getClientRects().length ? $("menu") : $("command");
    (live && !live.closest("[inert]") ? live : fallback).focus({preventScroll: true});
  }
  function openPanel(name, trigger, filter = null) {
    if (!["limits", "memory", "participants"].includes(name) || !identity || foreign()) return;
    if (side === "step") scene.close();
    opener = trigger; side = name; memberFilter = filter; showAside(name);
    if (name === "limits") readLimits();
    else paintPanel();
    $("close").focus({preventScroll: true});
  }
  async function paintReviewEvidence() {
    const q = fields(), id = q.get("reviewEvidence"), hash = location.hash;
    const epoch = ++sideEpoch, raw = detail, projectId = identity?.project_id;
    const run = current?.id, task = current?.task, lang = locale;
    const matches = q.get("session") === run && q.getAll("reviewEvidence").length === 1
      && isId(id) && !["proofNode", "proofAction", "proofAttempt"].some(name => q.has(name));
    let evidence;
    if (matches && validRun(projectId, run, task)) {
      $("inspection").replaceChildren(element("p", {role: "status", text: tr("loading")}));
      try { evidence = await manualReviewEvidence(raw, run, task, projectId, id, lang); }
      catch (_) { evidence = null; }
      if (side !== "review-evidence" || sideEpoch !== epoch || hash !== location.hash
          || raw !== detail || lang !== locale || !validRun(projectId, run, task)) return;
    }
    const text = lang === "ru" ? "Указанная запись проверки не найдена."
      : "The cited review record was not found.";
    $("inspection").replaceChildren(evidence || element("p", {role: "status", text}));
  }
  function paintPanel() {
    if (side === "review-evidence") paintReviewEvidence();
    if (side === "memory") showMemory($("inspection"), detail, scene.history(), locale);
    if (side === "participants") showHarnesses($("inspection"), members, memberFilter,
      locale, detail);
  }
  async function readLimits() {
    const epoch = ++sideEpoch;
    $("inspection").replaceChildren(element("p", {text: tr("loading")}));
    try {
      const raw = await transport.readJson(path.quotas());
      if (side === "limits" && sideEpoch === epoch) showLimits($("inspection"), raw, locale, readLimits);
    } catch (_) {
      if (side === "limits" && sideEpoch === epoch) {
        const b = element("button", {type: "button", text: tr("retry")});
        b.addEventListener("click", readLimits);
        $("inspection").replaceChildren(element("p", {text: tr("projection")}), b);
      }
    }
  }
  function paintRail(rows) {
    const chosen = key(current), focused = document.activeElement?.dataset.session;
    const list = rows.map(row => {
      const b = element("button", {type: "button", className: "session", "data-session": key(row),
        "aria-current": String(key(row) === chosen)}, [element("span", {className: "session-copy"},
        [element("strong", {text: row.kind === "new" ? row.title || tr("newSession") : row.title}),
          element("small", {text: row.bad ? tr("unreadable") : row.kind === "new" ? tr("draft") : row.id})])]);
      b.addEventListener("click", () => { navOpen(false); address(row); });
      return b;
    });
    if (!list.length && listState === "ready") list.push(element("p", {className: "rail-empty", text: tr("none")}));
    $("sessions").replaceChildren(...list);
    if (focused) list.find(b => b.dataset.session === focused)?.focus({preventScroll: true});
  }
  function paintPeople() {
    const selected = key(current);
    const subscribed = current?.kind === "new" && identity?.mode === "active" && providers.some(
      p => p.providerId === "codex" && p.auth === "subscription" && p.availability === "available");
    const preferred = leads.get(selected) || (current?.kind === "new"
      && (subscribed || claimForAdvice(fields())) ? "codex" : null);
    members = harnesses(detail, providers, locale);
    const lead = members.find(m => m.id === preferred) || members[0];
    if (lead) leads.set(selected, lead.id);
    $("lead").replaceChildren(...members.map(m => element("option", {value: m.id, text: m.label})));
    $("lead").hidden = !members.length;
    if (lead) $("lead").value = lead.id;
    const rows = members.map(m => {
      const b = element("button", {type: "button", className: "harness", "data-harness": m.id},
        [element("span", {className: "vendor", "aria-hidden": "true", text: m.label.slice(0, 1).toUpperCase()}),
          element("span", {className: "session-copy"}, [element("strong", {text: m.label}),
            element("small", {text: m.duty})])]);
      b.addEventListener("click", () => { leads.set(selected, m.id); $("lead").value = m.id;
        paintPlanning(); openPanel("participants", b, m.id); });
      return b;
    });
    $("harnesses").replaceChildren(...rows);
    paintUtilities();
  }
  function paintUtilities() {
    $("externalHarnesses").replaceChildren(...external.map(row => {
      const b = element("button", {type: "button", className: "harness", "data-utility": row.utility_id},
        [element("span", {className: "vendor", "aria-hidden": "true", text: "›"}),
          element("span", {className: "session-copy"}, [element("strong", {text: row.label}),
            element("small", {text: tr(row.mode === "manual" ? "manualTool" : "protocolTool")})])]);
      b.addEventListener("click", () => { navOpen(false); utility.open(true, row.utility_id); });
      return b;
    }));
    palette.refresh();
  }
  async function readUtilities() {
    if (!identity || !connected || foreign()) return;
    const epoch = ++utilityEpoch;
    try {
      const result = await transport.readJson(path.utilityRegistrations());
      if (epoch !== utilityEpoch) return;
      if (!Array.isArray(result?.utilities)) throw Error();
      external = result.utilities.filter(row => typeof row?.label === "string" && isId(row.utility_id)
        && ["manual", "stdio-v1"].includes(row.mode));
    } catch (_) { if (epoch !== utilityEpoch) return; external = []; }
    paintUtilities();
  }
  function paint() {
    const rows = sessions(), title = current?.kind === "new" ? current.title || tr("newSession")
      : current?.title || (listState === "loading" ? tr("loading") : tr("projection"));
    $("crumb").textContent = title; $("title").textContent = title;
    $("contextLabel").textContent = identity?.mode === "view" ? tr("view")
      : current ? tr(current.kind === "new" ? "draft" : current.kind) : "";
    const incomplete = !current && listState === "ready" ? "missing" : "";
    const phase = ["failed", "foreign", "loading", "offline"].includes(listState) ? listState
      : incomplete || (current?.bad ? "unreadable" : detailState);
    $("notice").textContent = phase ? tr(phase) : "";
    $("retry").hidden = !["failed", "offline", "unreadable"].includes(phase);
    for (const id of ["new", "memory", "limits"]) {
      $(id).disabled = !connected || listState !== "ready";
    }
    $("prepareTask").hidden = identity?.mode !== "active" || !["new", "task"].includes(current?.kind);
    $("prepareTask").textContent = tr(current?.kind === "task" ? "resume" : "start");
    $("prepareTask").href = toolAddress("desk", current?.kind === "task" ? {task: current.task, prepare: "1"}
      : {new: "task"});
    if (identity?.mode === "active" && current?.kind === "run" && detail) {
      const source = planning.planningSession(detail, identity.project_id);
      if (source) {
        const q = fields();
        for (const key of ["task", "session"]) q.delete(key);
        q.set("project", identity.project_id); q.set("new", source.slice(4)); q.set("advice", current.id);
        $("prepareTask").textContent = tr("returnToPlan");
        $("prepareTask").href = "#" + q;
        $("prepareTask").hidden = false;
      }
    }
    $("classic").href = toolAddress("studio", {screen: current?.kind === "run" ? "runs" : "overview",
      run: current?.kind === "run" ? current.id : null, task: current?.task});
    paintRail(rows); paintPeople();
    scene.sync({locale, sessionId: connected && listState === "ready" && current ? key(current) : null,
      runId: current?.kind === "run" ? current.id : null,
      detail, title, ready: connected && listState === "ready" && !detailState && !!current && !current.bad});
    nextAction.sync(identity && current?.kind === "run" ? {
      projectId: identity.project_id, mode: identity.mode, locale, runId: current.id,
      taskId: current.task, detail,
      ready: validRun(identity.project_id, current.id, current.task),
    } : null);
    paintPlanning();
    paintPanel();
    palette.refresh();
  }
  function paintPlanning() {
    const enabled = identity?.project_id && identity.mode === "active" && !foreign()
      && connected && listState === "ready" && current?.kind === "new"
      && leads.get(key(current)) === "codex";
    const ref = claimForAdvice(fields());
    if (enabled && ref) adviceRefs.set(key(current), ref);
    planning.sync(enabled ? {sessionId: key(current), projectId: identity.project_id,
      locale, reference: ref} : null);
    $("local").querySelector("span").textContent = tr(enabled ? "subscriptionPlan" : "local");
    if (enabled) $("prepareTask").hidden = true;
  }
  async function readRun(row) {
    detailStop?.abort(); const stop = new AbortController(); detailStop = stop;
    const epoch = ++detailEpoch;
    if (!detail) detailState = "loading";
    paint();
    try {
      const raw = await transport.readJson(path.run(row.id), stop);
      if (epoch !== detailEpoch) return;
      if (raw?.run?.run_id !== row.id || (raw.task?.id || null) !== (row.task || null)
          || !projectRunRead(raw)) throw Error();
      detail = raw; detailState = "";
    } catch (_) {
      if (epoch !== detailEpoch) return;
      detail = null; detailState = "failed";
    }
    paint();
    const q = fields();
    if (!detail || current?.id !== row.id || q.get("session") !== row.id
        || shownProof === location.hash) return;
    if (q.has("reviewEvidence")) {
      if (side === "step") scene.close();
      side = "review-evidence"; ++sideEpoch; shownProof = location.hash;
      showAside("inspector"); paintPanel(); return;
    }
    if (!q.has("proofAttempt")) return;
    const ids = ["proofNode", "proofAction", "proofAttempt"];
    if (ids.every(id => q.getAll(id).length === 1 && isId(q.get(id)))
        && scene.openAttempt(row.id, ...ids.map(id => q.get(id)))) shownProof = location.hash;
    else $("notice").textContent = locale === "ru" ? "Указанная попытка не найдена."
      : "The cited attempt was not found.";
  }
  function navigate(keep = false) {
    if (shownProof !== location.hash) {
      if (side === "review-evidence") hideAside();
      shownProof = null;
    }
    if (legacy()) return;
    preferences();
    if (listState === "foreign") { location.reload(); return; }
    if (foreign()) { refuse(); return; }
    if (!connected || listState !== "ready") { switchTo(null); paint(); return; }
    const rows = sessions();
    const implicit = !["session", "task", "new"].some(name => fields().has(name));
    const kept = keep === true && implicit && rows.find(row => key(row) === key(current) && !row.bad);
    const row = kept || requested(rows);
    switchTo(row);
    if (listState === "ready" && row?.kind === "run" && !row.bad) readRun(row);
    else paint();
  }
  function retire() {
    ++listEpoch; ++detailEpoch; ++sideEpoch; ++utilityEpoch; external = [];
    catalogStop?.abort(); detailStop?.abort(); detail = null; detailState = "";
    hideAside();
  }
  function refuse() {
    retire(); ++identityEpoch; ++linkEpoch; transport.seal(); connected = false; stream = null;
    if ($("studioUtilities").open) $("studioUtilities").close();
    drafts.clear(); leads.clear(); adviceRefs.clear();
    identity = null; runs = []; providers = []; tasks = []; current = null;
    listState = "foreign"; paint(); utility.sync();
  }
  async function refresh() {
    if (!identity || foreign()) return;
    if (checking) { again = true; return; }
    const epoch = ++listEpoch; checking = true; again = false;
    const stop = new AbortController(); catalogStop = stop;
    try {
      const [r, t] = await Promise.all([transport.readJson(path.runs(), stop), transport.readJson(path.tasks(), stop)]);
      if (epoch !== listEpoch) return;
      const list = projectRuns(r), available = projectTasks(t);
      if (!list || !available) throw Error();
      runs = list.runs; providers = list.providers; tasks = available; listState = "ready";
      navigate(true);
    } catch (_) {
      if (epoch !== listEpoch) return;
      runs = []; providers = []; tasks = []; listState = "failed";
      switchTo(null); paint();
    } finally {
      checking = false;
      if (again && connected && listState !== "foreign") refresh();
    }
  }
  async function start() {
    const epoch = ++identityEpoch;
    if (foreign()) { refuse(); return; }
    listState = "loading"; paint();
    try {
      const next = await transport.readJson(path.project());
      if (epoch !== identityEpoch) return;
      if (!next || !["view", "active"].includes(next.mode)
          || !(next.project_id === null || /^[a-f0-9]{32}$/.test(next.project_id))) throw Error();
      identity = next;
      if (foreign()) { refuse(); return; }
    } catch (err) {
      if (epoch !== identityEpoch) return;
      if (err.message === "project_mismatch") { refuse(); return; }
      listState = "failed"; paint(); return;
    }
    stream = transport.openStream();
    stream.addEventListener("open", onOpen);
    stream.addEventListener("error", () => {
      if (listState === "foreign") return;
      reconnecting = true; ++linkEpoch;
      connected = false; again = false; retire(); transport.dropSession();
      runs = []; tasks = []; providers = []; current = null;
      if (identity?.project_id === null) {
        drafts.clear(); leads.clear();
        if ($("studioUtilities").open) $("studioUtilities").close();
      }
      listState = "offline"; paint(); utility.sync();
    });
    stream.onmessage = event => {
      let frame;
      try { frame = JSON.parse(event.data); } catch (_) { return; }
      if (connected && ["state", "run"].includes(frame?.kind)) { refresh(); planning.tick(); }
    };
  }
  async function onOpen() {
    const epoch = ++linkEpoch;
    // Two unidentified archives can occupy the same port. Tab-local text belongs to the old one.
    if (reconnecting && identity?.project_id === null) { location.reload(); return; }
    try {
      const next = await transport.readJson(path.project());
      if (epoch !== linkEpoch) return;
      if (next?.project_id !== identity?.project_id) { refuse(); return; }
      if (next?.mode !== identity.mode) { location.reload(); return; }
    } catch (error) {
      if (epoch !== linkEpoch) return;
      if (error.message === "project_mismatch") { refuse(); return; }
      listState = "failed"; paint(); return;
    }
    reconnecting = false; connected = true; refresh(); readUtilities(); utility.sync();
  }
  preferences();
  const layout = attachLayout($("workspace"), {
    locale: () => locale, stop: () => new AbortController(),
  });
  syncLayers();
  $("new").addEventListener("click", () => {
    const row = {kind: "new", id: crypto.randomUUID(), title: "", time: new Date().toISOString()};
    drafts.set(row.id, row); navOpen(false); address(row);
    $("command").focus({preventScroll: true}); });
  $("send").addEventListener("submit", () => {
    if (current?.kind !== "new") return;
    const first = scene.history().find(message => message.role === "user");
    if (!first) return;
    if (!drafts.has(current.id)) drafts.set(current.id, {...current, time: new Date().toISOString()});
    const row = drafts.get(current.id);
    if (!row.title) row.title = first.text.slice(0, 72);
    current = row; paint();
  });
  $("studioUtilities").addEventListener("close", () => {
    readUtilities();
    if ($("sidebar").inert && !$("workspace").classList.contains("with-detail")) restoreOpener(null);
  });
  $("menu").addEventListener("click", () => { navOpen(true); $("navClose").focus(); });
  const closeNav = () => { navOpen(false); $("menu").focus({preventScroll: true}); };
  $("navClose").addEventListener("click", closeNav);
  $("backdrop").addEventListener("click", closeNav);
  $("close").addEventListener("click", () => {
    if (side === "step") scene.close();
    else { hideAside(); restoreOpener(opener); }
  });
  document.addEventListener("keydown", event => {
    if (event.defaultPrevented || event.key !== "Escape" || $("studioUtilities").open
        || $("palette").open) return;
    if ($("workspace").classList.contains("nav-open")) { closeNav(); event.preventDefault(); }
    else if (side) { $("close").click(); event.preventDefault(); }
  });
  $("paletteOpen").addEventListener("click", () => palette.open($("paletteOpen")));
  $("limits").addEventListener("click", () => openPanel("limits", $("limits")));
  $("memory").addEventListener("click", () => openPanel("memory", $("memory")));
  $("lead").addEventListener("change", () => {
    leads.set(key(current), $("lead").value); paint();
    if (current?.kind !== "new" || identity?.mode !== "active")
      openPanel("participants", $("lead"), $("lead").value);
  });
  $("attach").addEventListener("click", () => { navOpen(false); utility.open(true); });
  $("language").addEventListener("change", () => setPreference("lang", $("language").value));
  $("theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark";
    setPreference("theme", dark ? "light" : "dark");
  });
  $("retry").addEventListener("click", () => {
    if (!identity) start();
    else if (!connected) location.reload();
    else refresh();
  });
  document.querySelector('a[href="#chat"]').addEventListener("click", event => {
    event.preventDefault(); $("chat").focus();
  });
  window.addEventListener("hashchange", navigate);
  window.addEventListener("resize", syncLayers);
  window.addEventListener("pagehide", event => {
    if (!event.persisted) {
      retire(); nextAction.dispose(); palette.dispose(); scene.dispose(); layout.dispose();
      transport.seal();
    }
  });
  start();
}

if (!legacy()) boot();
