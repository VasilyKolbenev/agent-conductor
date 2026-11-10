"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {sceneOf} from "./studio-scene-model.js";
import {answerFor, atlasInspector, matchesAtlasAttempt} from "./studio-atlas-inspector.js";
import {patchStep, renderOrbit} from "./arachnid-orbit.js";

const rows = value => Array.isArray(value) ? value : [];
const controls = {
  limits: /лимит|квот|остаток|quota|usage|limits?/i,
  memory: /памят|истори[яю]|memory|history/i,
  participants: /участник|харнесс|команд[ауые]|participants?|harness|team/i,
};
const topics = {
  tests: /тест|проверки|tests?|assert/i,
  verdict: /вердикт|проверяющ|checker|verdict/i,
  diff: /измен|патч|разниц|diff|chang|patch/i,
};
const commandOf = (words, text) => Object.keys(words).find(name => words[name].test(text));
const shortCommands = {
  limits: /^(?:(?:покажи )?(?:лимиты|квоты|остаток)|(?:show )?(?:limits|quotas|usage))$/,
  memory: /^(?:(?:покажи )?(?:память|историю|история)|(?:show )?(?:memory|history))$/,
  participants: /^(?:(?:покажи )?(?:участники|участников|харнессы)|(?:show )?(?:participants|harnesses|team))$/,
};
function directPanel(message) {
  const text = message.trim().toLowerCase().replace(/^\//, "").replace(/[.?!]+$/, "");
  return Object.keys(shortCommands).find(name => shortCommands[name].test(text));
}
function button(text, onClick, cls = "") {
  const node = element("button", {type: "button", className: cls, text});
  node.addEventListener("click", onClick);
  return node;
}
function newSession() {
  return {draft: "", messages: [], step: null, actions: new Map(), choices: new Map()};
}

export function arachnidConversation(center, inspector, door) {
  const fields = Object.fromEntries(["intro", "orbitHere", "resultHere", "messages", "quick",
    "send", "command"].map(id => [id, center.querySelector("#" + id)]));
  const sessions = new Map(), events = door.stop();
  let model = null, state = null, scene = null, open = false, read = null, controller = null;
  let signature = null, generation = 0, paintedMessages = null, disposed = false;
  const tr = (key, params) => localize(model, "atlas." + key, params);
  const words = (en, ru) => model.locale === "ru" ? ru : en;
  const step = () => scene?.steps.find(row => row.nodeId === state?.step);
  function actions(s) {
    return rows(model.detail?.records).filter(row => row.record_type === "action_request"
      && row.record?.run_id === model.runId && row.record.node_id === s?.nodeId)
      .map(row => row.record);
  }
  function selected(s) {
    const options = actions(s);
    return options.find(a => a.action_id === state.actions.get(s?.nodeId)) || options.at(-1);
  }
  function held(action) {
    if (!state.choices.has(action.action_id)) state.choices.set(action.action_id,
      {tab: "diff", file: null, test: null});
    return state.choices.get(action.action_id);
  }
  function transcript() {
    const content = JSON.stringify([model.sessionId, model.locale,
      state.messages.map(row => [row.role, row.text])]);
    if (paintedMessages === content) return;
    paintedMessages = content;
    fields.messages.replaceChildren(...state.messages.map(row => {
      const who = tr(row.role === "user" ? "you" : "title");
      return element("div", {className: "msg " + row.role},
        [element("b", {text: who}), element("p", {text: row.text})]);
    }));
  }
  function settle(epoch, evidence) {
    let changed = false;
    for (const row of state?.messages || []) {
      if (row.wait !== epoch) continue;
      row.text = evidence ? answerFor(model, row.topic, evidence) : tr("unavailable");
      delete row.wait; changed = true;
    }
    if (changed) transcript();
  }
  function revoke() {
    if (model && state) settle(generation, null);
    generation++; controller?.abort(); controller = null; signature = null; read = null;
  }
  function load(refresh = false) {
    const s = step(), a = s && patchStep(s) ? selected(s) : null;
    const key = open && model.ready && a ? JSON.stringify([model.sessionId, model.runId, s.nodeId,
      a.action_id, a.attempt_id, rows(model.detail.records).length]) : null;
    if (key === signature && !refresh) return;
    revoke();
    if (!key) return;
    const epoch = generation, run = model.runId, pending = door.stop();
    signature = key; controller = pending; read = {phase: "loading"};
    Promise.resolve().then(() => pending.signal.aborted ? null
      : door.readAttempt(run, s.nodeId, a.action_id, pending)).then(value => {
      if (disposed || generation !== epoch || signature !== key) return;
      read = matchesAtlasAttempt(value, a, s, run)
        ? {phase: "ready", value} : {phase: "unavailable"};
      settle(epoch, read.value); drawInspector(); summary();
    }, () => {
      if (disposed || generation !== epoch || signature !== key) return;
      read = {phase: "unavailable"}; settle(epoch, null); drawInspector(); summary();
    });
  }
  function drawOrbit() {
    if (scene) renderOrbit(fields.orbitHere, model, scene, open ? state.step : null,
      row => choose(row, true));
    else fields.orbitHere.replaceChildren();
  }
  function choose(s, focus = false) {
    if (!s) return;
    state.step = s.nodeId; open = true; door.inspect(true);
    load(); drawOrbit(); drawInspector(); summary();
    if (focus) inspector.querySelector("h2")?.focus({preventScroll: true});
  }
  function close() {
    if (!open) return;
    const last = state.step;
    revoke(); open = false; inspector.replaceChildren(); door.inspect(false);
    drawOrbit(); summary();
    [...fields.orbitHere.querySelectorAll("[data-step]")].find(n => n.dataset.step === last)
      ?.focus({preventScroll: true});
  }
  function summary() {
    const host = fields.resultHere;
    host.replaceChildren();
    const patches = scene?.steps.filter(patchStep) || [];
    const s = patchStep(step()) ? step() : patches.length === 1 ? patches[0] : null;
    if (!s) return;
    const row = button("", () => choose(s, true), "result-summary");
    row.append(element("span", {className: "summary-label",
      text: (s.title || s.nodeId) + " · " + tr("diff")}));
    const e = open && step() === s ? read?.value : null;
    if (e?.files_total != null) row.append(element("span", {className: "summary-stat",
      text: tr("files", {n: String(e.files_total)})}));
    if (e?.tests.status === "recorded") row.append(element("span", {className: "summary-stat",
      text: words("Tests", "Тесты") + " · " + e.tests.summary.total}));
    row.append(element("span", {className: "summary-arrow", "aria-hidden": "true", text: "↗"}));
    host.append(row);
  }
  function drawInspector() {
    const focus = inspector.contains(document.activeElement) ? document.activeElement : null;
    populateInspector();
    if (!focus || focus.isConnected) return;
    const restored = focus.matches("h2") ? inspector.querySelector("h2")
      : focus.matches("[data-atlas-attempt]") ? inspector.querySelector("[data-atlas-attempt]")
      : [...inspector.querySelectorAll("[data-focus]")]
        .find(n => n.dataset.focus === focus.dataset.focus);
    restored?.focus({preventScroll: true});
  }
  function populateInspector() {
    const s = step();
    if (!open || !s) return;
    const showIds = inspector.querySelector(".atlas-attempt-ids")?.open === true;
    const body = element("section", {className: "inspect-body", "data-atlas-inspector": ""});
    const actor = scene.participants.find(p => p.instanceId === s.ownerId);
    const owner = [actor?.adapter, s.ownerId].filter(Boolean).join(" · ");
    body.append(element("div", {className: "detail-heading"}, [
      element("small", {className: "eyebrow", text: owner}),
      element("h2", {text: s.title || s.nodeId, tabindex: "-1"})]));
    inspector.replaceChildren(body);
    if (!patchStep(s)) {
      if (!model.ready) { body.append(element("p", {text: tr("offline")})); return; }
      const description = localize(model, "scene." + s.word);
      body.append(element("p", {className: "check-card", text: description}));
      for (const a of actions(s)) {
        const result = rows(model.detail?.records).find(r => r.record_type === "action_result"
          && r.record?.action_id === a.action_id && r.record.attempt_id === a.attempt_id
          && r.record.instance_id === a.instance_id)?.record;
        const fact = [a.attempt_id, result?.outcome].filter(Boolean).join(" · ");
        body.append(element("p", {text: fact}));
      }
      return;
    }
    const options = actions(s), a = selected(s);
    if (!a) { body.append(element("p", {text: tr("no_attempt")})); return; }
    const select = element("select", {"data-atlas-attempt": "", "aria-label": tr("attempt")});
    options.forEach((item, i) => {
      const text = tr("attempt_name", {n: String(i + 1), total: String(options.length),
        id: item.action_id});
      select.append(element("option", {value: item.action_id, text}));
    });
    select.value = a.action_id;
    select.addEventListener("change", () => {
      state.actions.set(s.nodeId, select.value); load(); drawInspector(); summary();
      inspector.querySelector("select")?.focus({preventScroll: true});
    });
    const ids = element("dl");
    for (const [key, value] of [["run", a.run_id], ["step", a.node_id],
      ["action", a.action_id], ["attempt", a.attempt_id]]) {
      ids.append(element("dt", {text: tr(key)}),
        element("dd", {}, [element("code", {text: value})]));
    }
    const details = element("details", {className: "atlas-attempt-ids"}, [
      element("summary", {"data-focus": "atlas:ids", text: tr("execution_ids")}), ids]);
    details.open = showIds;
    body.append(element("div", {className: "atlas-attempt-context"}, [
      element("label", {className: "atlas-attempt"},
        [element("span", {text: tr("attempt")}), select]),
      details]));
    if (model.ready && read?.phase === "ready") {
      atlasInspector(body, model, read.value, held(a), (change, switchTab = false) => {
        const before = document.activeElement?.dataset.focus;
        Object.assign(held(a), change); drawInspector();
        const name = switchTab ? "atlas:tab:" + change.tab : before;
        [...inspector.querySelectorAll("[data-focus]")].find(n => n.dataset.focus === name)
          ?.focus({preventScroll: true});
      });
    } else body.append(element("p", {role: "status", text: tr(!model.ready ? "offline"
      : read?.phase === "loading" ? "loading" : "unavailable")}));
    const refresh = button(tr("refresh"), () => { load(true); drawInspector(); }, "atlas-refresh");
    refresh.dataset.focus = "atlas:refresh";
    refresh.disabled = !model.ready || read?.phase === "loading"; body.append(refresh);
  }
  function ask(text) {
    const message = text.trim();
    if (!state || !message) return;
    state.messages.push({role: "user", text: message});
    state.draft = ""; fields.command.value = "";
    const planning = model.sessionId?.startsWith("new/") && typeof door.planMessage === "function";
    const panel = planning ? directPanel(message) : commandOf(controls, message);
    const topic = commandOf(topics, message);
    const reply = {role: "atlas", text: ""};
    if (panel) {
      close();
      reply.text = {limits: words("Subscription limits", "Лимиты подписок"),
        memory: words("Session history", "История сессии"),
        participants: words("Session participants", "Участники сессии")}[panel];
      state.messages.push(reply); transcript(); door.command(panel); return;
    }
    if (planning && door.planMessage(model.sessionId, message)) { transcript(); return; }
    if (topic) {
      const patches = scene?.steps.filter(patchStep) || [];
      const s = step() || (patches.length === 1 ? patches[0] : null);
      if (patchStep(s)) {
        const a = selected(s);
        if (a) held(a).tab = topic;
        choose(s);
        if (!a) reply.text = tr("no_attempt");
        else if (read?.phase === "ready") reply.text = answerFor(model, topic, read.value);
        else if (read?.phase === "loading") Object.assign(reply,
          {text: tr("loading"), wait: generation, topic});
        else reply.text = tr(model.ready ? "unavailable" : "offline");
      } else reply.text = tr(s ? "not_patch" : "select");
    } else reply.text = scene ? tr("ask_help") : words(
      "Ask about session history, participants or subscription limits.",
      "Можно открыть историю сессии, участников или лимиты подписок.");
    state.messages.push(reply); transcript();
    fields.messages.lastElementChild?.scrollIntoView({block: "nearest"});
  }
  function paint() {
    const participants = scene?.participants.map(p => p.adapter).filter(Boolean) || [];
    const names = [...new Set(participants)].join(" · ");
    fields.intro.textContent = names
      ? words("Run participants", "Участники запуска") + " · " + names
      : model.runId && !scene ? words("No cycle is available for this run.",
        "Для этого запуска пока нет схемы цикла.") : "";
    fields.quick.replaceChildren();
    if (scene?.steps.some(patchStep)) {
      const proof = tr("ask_tests");
      fields.quick.append(button(proof, () => ask(proof)));
    }
    const limits = words("Limits", "Лимиты");
    fields.quick.append(button(limits, () => ask(limits)));
    drawOrbit(); summary(); transcript();
    if (open) drawInspector();
  }
  function sync(next) {
    if (disposed) return;
    const switching = model?.sessionId !== next.sessionId || model?.runId !== next.runId;
    if (switching) {
      if (state) state.draft = fields.command.value;
      revoke();
      if (open) { open = false; inspector.replaceChildren(); door.inspect(false); }
    }
    model = next;
    const sessionId = typeof next.sessionId === "string" ? next.sessionId : null;
    if (sessionId !== null && !sessions.has(sessionId)) sessions.set(sessionId, newSession());
    state = sessions.get(sessionId) || null;
    fields.command.disabled = !state;
    fields.send.querySelector("button[type=submit]").disabled = !state;
    scene = next.detail?.run?.run_id === next.runId && next.runId ? sceneOf(next.detail) : null;
    if (!state) {
      paintedMessages = null;
      for (const key of ["intro", "orbitHere", "resultHere", "messages", "quick"])
        fields[key].replaceChildren();
      fields.command.value = ""; return;
    }
    if (switching) fields.command.value = state.draft;
    if (open && !step()) {
      revoke(); open = false; inspector.replaceChildren(); door.inspect(false);
    }
    load(); paint();
  }
  fields.command.addEventListener("input", () => {
    if (state) state.draft = fields.command.value;
  }, {signal: events.signal});
  fields.send.addEventListener("submit", e => {
    e.preventDefault(); ask(fields.command.value);
  }, {signal: events.signal});
  return {sync, close, history: () => (state?.messages || []).map(({role, text}) => ({role, text})),
    dispose() { disposed = true; revoke(); events.abort(); sessions.clear(); }};
}
