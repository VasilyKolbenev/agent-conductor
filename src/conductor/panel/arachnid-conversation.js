"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {sceneOf} from "./studio-scene-model.js";
import {
  answerFor, atlasInspector, atlasTestSummary, matchesAtlasAttempt,
} from "./studio-atlas-inspector.js";
import {patchStep, renderOrbit} from "./arachnid-orbit.js";
import {handoffData} from "./arachnid-handoff-data.js";
import {handoffVerdictAnswer, renderHandoff} from "./arachnid-handoff.js";
import {
  continuationPin, handoffIntent, handoffPin, sameContinuation, sameHandoff,
} from "./arachnid-handoff-context.js";

const rows = value => Array.isArray(value) ? value : [];
const controls = {
  limits: /лимит|квот|остаток|quota|usage|limits?/i,
  memory: /памят|истори[яю]|memory|history/i,
  participants: /участник|харнесс|команд[ауые]|participants?|harness|team/i,
};
const topics = {
  tests: /тест|проверки|tests?|assert/i,
  verdict: /вердикт|проверяющ|checker|verdict/i,
  diff: /измен|исправил|поменял|поправил|патч|разниц|diff|chang|patch|\bfix(?:ed)?\b/i,
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
  return {draft: "", messages: [], scope: null, choices: new Map(), handoff: null};
}

export function arachnidConversation(center, inspector, door) {
  const fields = Object.fromEntries(["intro", "orbitHere", "resultHere", "messages", "scopeHere",
    "quick", "send", "command"].map(id => [id, center.querySelector("#" + id)]));
  const sessions = new Map(), events = door.stop();
  let model = null, state = null, scene = null, open = false, read = null, controller = null;
  let signature = null, generation = 0, paintedMessages = null, disposed = false;
  let handoffPanel = false, projection = null, projectionDetail = null, pair = null;
  const tr = (key, params) => localize(model, "atlas." + key, params);
  const words = (en, ru) => model.locale === "ru" ? ru : en;
  const step = () => scene?.steps.find(row => row.nodeId === state?.scope?.nodeId);
  function actions(s) {
    return rows(model.detail?.records).filter(row => row.record_type === "action_request"
      && row.record?.run_id === model.runId && row.record.node_id === s?.nodeId)
      .map(row => row.record);
  }
  function selected(s) {
    const scope = state?.scope;
    if (!scope || scope.nodeId !== s?.nodeId) return null;
    return actions(s).find(a => a.action_id === scope.actionId && a.attempt_id === scope.attemptId);
  }
  function pin(s, action, options) {
    state.scope = {nodeId: s.nodeId, title: s.title || s.nodeId, actionId: action?.action_id,
      attemptId: action?.attempt_id, number: action ? options.indexOf(action) + 1 : null};
  }
  function scopeName(scope) {
    if (!scope) return tr("whole_cycle");
    return scope.number ? scope.title + " · " + tr("attempt_number", {n: String(scope.number)})
      : scope.title;
  }
  function drawScope() {
    const host = fields.scopeHere;
    if (!scene) { host.replaceChildren(); return; }
    const focused = host.contains(document.activeElement);
    const menu = element("select", {"data-atlas-scope": "", "aria-label": tr("chat_scope")});
    menu.append(element("option", {value: "", text: tr("whole_cycle")}));
    const scope = state.scope;
    for (const s of scene.steps) {
      const text = scope?.nodeId === s.nodeId ? scopeName(scope) : s.title || s.nodeId;
      menu.append(element("option", {value: s.nodeId, text}));
    }
    if (scope && !step()) {
      menu.append(element("option", {value: scope.nodeId, disabled: "", text: scopeName(scope)}));
    }
    menu.value = scope?.nodeId || "";
    menu.disabled = !model.ready;
    menu.addEventListener("change", () => {
      if (menu.value) { openStep(model.runId, menu.value); return; }
      close(); state.scope = null; state.handoff = null; revoke(); paint();
      host.querySelector("select")?.focus({preventScroll: true});
    });
    host.replaceChildren(element("label", {className: "atlas-scope"}, [
      element("span", {className: "atlas-scope-label", text: tr("chat_scope")}), menu]));
    if (focused) menu.focus({preventScroll: true});
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
      const msg = element("div", {className: "msg " + row.role},
        [element("b", {text: who}), element("p", {text: row.text})]);
      if (row.origin) msg.append(element("small", {className: "atlas-origin",
        title: [row.origin.nodeId, row.origin.actionId, row.origin.attemptId].join(" · "),
        text: scopeName(row.origin)}));
      return msg;
    }));
  }
  function settle(epoch, evidence) {
    let changed = false;
    for (const row of state?.messages || []) {
      if (row.wait !== epoch) continue;
      row.text = evidence ? evidenceAnswer(row.topic, evidence) : tr("unavailable");
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
      const checker = scene.participants.filter(p => p.instanceId === s.verifierId);
      const sameChecker = !value?.verdict || checker.length === 1
        && value.verdict.adapter_id === checker[0].adapter;
      read = sameChecker && matchesAtlasAttempt(value, a, s, run)
        ? {phase: "ready", value} : {phase: "unavailable"};
      settle(epoch, read.value); drawInspector(); summary();
    }, () => {
      if (disposed || generation !== epoch || signature !== key) return;
      read = {phase: "unavailable"}; settle(epoch, null); drawInspector(); summary();
    });
  }
  function drawOrbit() {
    if (scene) renderOrbit(fields.orbitHere, model, scene, state.scope?.nodeId,
      row => choose(row, true));
    else fields.orbitHere.replaceChildren();
  }
  function choose(s, focus = false) {
    if (!s || !model.ready) return;
    handoffPanel = false; state.handoff = null;
    if (state.scope?.nodeId !== s.nodeId) {
      const options = actions(s);
      pin(s, options.at(-1), options);
    }
    open = true; door.inspect(true);
    load(); drawOrbit(); drawScope(); drawInspector(); summary();
    if (focus) inspector.querySelector("h2")?.focus({preventScroll: true});
  }
  function close() {
    if (!open) return;
    const wasHandoff = handoffPanel;
    handoffPanel = false;
    const last = state.scope?.nodeId;
    revoke(); open = false; inspector.replaceChildren(); door.inspect(false);
    drawOrbit(); summary();
    const orbitNode = [...fields.orbitHere.querySelectorAll("[data-step]")]
      .find(n => n.dataset.step === last);
    (wasHandoff ? fields.command : orbitNode || fields.scopeHere.querySelector("select") || fields.command)
      .focus({preventScroll: true});
  }
  function paletteSteps() {
    return !model?.ready || !scene ? [] : scene.steps.map(s =>
      ({runId: model.runId, nodeId: s.nodeId, title: s.title || s.nodeId}));
  }
  function openStep(runId, nodeId) {
    if (disposed || !model?.ready || !runId || model.runId !== runId) return false;
    const s = scene?.steps.find(row => row.nodeId === nodeId);
    if (!s) return false;
    choose(s, true); return true;
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
    if (e?.tests.status === "recorded" && e.tests.summary) row.append(element("span", {
      className: "summary-stat",
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
  function evidenceSummary(e) {
    const paths = e.files.slice(0, 2);
    const files = e.files_total === null ? tr("no_files") : paths.length < e.files_total
      ? tr("partial", {shown: String(paths.length), total: String(e.files_total)})
      : tr("files", {n: String(e.files_total)});
    const tests = e.tests, verdict = e.verdict;
    const testReport = atlasTestSummary(model, tests);
    const table = element("dl");
    for (const [key, value] of [
      ["outcome", e.outcome ? localize(model, "scene.outcome_" + e.outcome) : tr("pending_result")],
      ["files", files], ["tests", testReport],
      ["checker", verdict ? verdict.instance_id + " · " + verdict.adapter_id : tr("not_recorded")],
      ["verdict", tr(!verdict ? "no_verdict" : verdict.status === "unavailable"
        ? "verifier_unavailable" : verdict.status)],
    ]) {
      const fact = element("dd", {"data-atlas-fact": key, text: value});
      if (key === "files" && paths.length) {
        fact.append(element("ul", {className: "atlas-summary-paths"},
          paths.map(f => element("li", {text: f.path}))));
      }
      table.append(element("dt", {text: tr("fact_" + key)}), fact);
    }
    const heading = element("h3", {text: tr("attempt_summary")});
    return element("section", {className: "atlas-attempt-summary"}, [heading, table]);
  }
  function populateInspector() {
    if (open && handoffPanel) { drawHandoff(); return; }
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
    const options = actions(s), a = selected(s);
    if (!patchStep(s)) {
      if (!model.ready) { body.append(element("p", {text: tr("offline")})); return; }
      const description = localize(model, "scene." + s.word);
      body.append(element("p", {className: "check-card", text: description}));
      if (!options.length && !state.scope?.actionId) return;
    }
    if (!a) {
      const note = state.scope?.actionId ? "attempt_missing" : "no_attempt";
      body.append(element("p", {role: "status", text: tr(!model.ready ? "offline" : note)}));
      if (!options.length) return;
    }
    const select = element("select", {"data-atlas-attempt": "", "aria-label": tr("attempt")});
    if (!a) select.append(element("option", {value: "", text: tr("pick_attempt"), disabled: ""}));
    options.forEach((item, i) => {
      const text = tr("attempt_name", {n: String(i + 1), total: String(options.length),
        id: item.action_id});
      select.append(element("option", {value: item.action_id, text}));
    });
    select.value = a?.action_id || "";
    select.disabled = !model.ready;
    select.addEventListener("change", () => {
      const next = options.find(option => option.action_id === select.value);
      if (!model.ready || !next) return;
      pin(s, next, options); load(); drawScope(); drawInspector(); summary();
      inspector.querySelector("select")?.focus({preventScroll: true});
    });
    const context = element("div", {className: "atlas-attempt-context"}, [
      element("label", {className: "atlas-attempt"},
        [element("span", {text: tr("attempt")}), select])]);
    body.append(context);
    if (!a) return;
    const ids = element("dl");
    for (const [key, value] of [["run", a.run_id], ["step", a.node_id],
      ["action", a.action_id], ["attempt", a.attempt_id]]) {
      ids.append(element("dt", {text: tr(key)}),
        element("dd", {}, [element("code", {text: value})]));
    }
    const details = element("details", {className: "atlas-attempt-ids"}, [
      element("summary", {"data-focus": "atlas:ids", text: tr("execution_ids")}), ids]);
    details.open = showIds;
    context.append(details);
    if (!patchStep(s)) {
      const result = rows(model.detail.records).find(r => r.record_type === "action_result"
        && r.record?.run_id === a.run_id && r.record.action_id === a.action_id
        && r.record.attempt_id === a.attempt_id && r.record.instance_id === a.instance_id)?.record;
      body.append(element("p", {text: result ? localize(model, "scene.outcome_" + result.outcome)
        : tr("pending_result")}));
      return;
    }
    if (model.ready && read?.phase === "ready") {
      body.append(evidenceSummary(read.value));
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
  function activeTransfer() {
    const h = state?.handoff;
    if (!model.ready || !h || !model.runId || h.runId !== model.runId
        || model.detail?.run?.run_id !== h.runId) return null;
    const adapters = h.from + "/" + h.to;
    if (model.detail !== projectionDetail || pair !== adapters) {
      projectionDetail = model.detail; pair = adapters;
      projection = handoffData(model.detail, h.from, h.to);
    }
    if (!projection || projection.runId !== h.runId) return null;
    const linkIndex = projection.links.findIndex(row => sameHandoff(row, h.link));
    const link = projection.links[linkIndex];
    const options = link ? projection.continuations.filter(
      row => row.fromArtifactId === link.target.artifactId) : [];
    const continuation = options.find(row => sameContinuation(row, h.continuation));
    return {graph: projection, link, linkIndex, options, continuation,
      continuationIndex: continuation ? projection.continuations.indexOf(continuation) : -1};
  }
  function setLink(link) {
    const h = state.handoff;
    h.link = handoffPin(link); h.selectedKey = "source"; h.continuation = null;
    const {options} = activeTransfer();
    if (options.length === 1) h.continuation = continuationPin(options[0]);
  }
  function selectProof() {
    const row = activeTransfer()?.continuation?.target;
    const s = row && scene?.steps.find(item => item.nodeId === row.nodeId && patchStep(item));
    const options = s ? actions(s) : [];
    const a = options.find(item => item.action_id === row.actionId
      && item.attempt_id === row.attemptId && item.instance_id === row.instanceId);
    state.scope = null;
    if (a) pin(s, a, options);
    load();
  }
  function evidenceAnswer(topic, evidence) {
    if (topic === "handoff-verdict") return handoffVerdictAnswer(model.locale, evidence);
    if (topic === "tests-in-handoff") return testAnswer(evidence);
    if (topic !== "changes") return answerFor(model, topic, evidence);
    const overview = answerFor(model, "diff", evidence);
    const file = evidence.files.find(f => f.diff_status === "available" && f.lines.length);
    if (!file) return overview;
    const hunk = file.lines.findIndex(line => line.startsWith("@@"));
    if (hunk < 0) return overview;
    const excerpt = [];
    for (const line of file.lines.slice(hunk + 1)) {
      if (line.startsWith("@@")) break;
      if (/^[+-].*\S/.test(line)) excerpt.push(line);
      if (excerpt.length === 8) break;
    }
    return excerpt.length ? overview + "\n" + file.path + "\n" +
      excerpt.map(line => line.length > 128 ? line.slice(0, 127) + "…" : line).join("\n")
      : overview;
  }
  function testAnswer(evidence) {
    const status = atlasTestSummary(model, evidence.tests);
    if (evidence.tests.status !== "recorded") return status;
    const output = evidence.tests.protocol?.output || "";
    const cases = [...output.matchAll(/^(test_[\w]+)\s+\([^\n]+?\)\s+\.\.\. ok\s*$/gm)]
      .slice(0, 5).map(match => match[1]);
    const names = cases.length ? "\n" + cases.join(", ") : "";
    return status + names + words(
      ". The report applies to the selected Do attempt. Individual findings have no test links.",
      ". Протокол относится к попытке Do. Связи отдельных выводов с тестами не записаны.");
  }
  function readHandoff(intent, reply) {
    if (intent.kind === "other-author") {
      if (handoffPanel) close();
      reply.text = words("This handoff leads to a different harness. Select the requested step.",
        "В этой передаче правку выполняет другой харнесс. Выберите нужный шаг.");
      return;
    }
    if (intent.kind === "clarify" || !model.ready || !scene) {
      reply.text = words("Select a run and ask what Grok handed to Codex.",
        "Выберите запуск и спросите, что Grok передал Codex.");
      return;
    }
    handoffPanel = true; open = true;
    if (intent.kind === "transfer") {
      revoke(); state.scope = null;
      state.handoff = {from: intent.from, to: intent.to, runId: model.runId,
        view: "handoff", link: null, continuation: null, selectedKey: "source"};
      const data = activeTransfer();
      if (data?.graph.links.length === 1) setLink(data.graph.links[0]);
    } else {
      state.handoff.view = intent.kind; state.handoff.selectedKey = "check"; selectProof();
    }
    const current = activeTransfer(), link = current?.link;
    if (!link) {
      reply.text = current?.graph.links.length ? words("Choose a handoff in the inspector.",
        "Выберите нужную передачу в инспекторе.") : words("No recorded handoff for this pair.",
        "В этом запуске нет подтверждённой передачи между этими участниками.");
    } else if (intent.kind === "transfer") {
      const excerpt = link.source.excerpt || "";
      const paragraph = excerpt.match(/(?:^|[.!?]\s*)#{1,4} [^\n]+\n+([^#\n][^\n]*)/m)?.[1]
        || excerpt;
      reply.text = words("The recorded input to ", "Вход для ") + link.target.adapter
        + " · " + link.target.nodeId + " — " + link.source.artifactRef + " ("
        + link.source.adapter + "). " + paragraph.slice(0, 320);
    } else if (!current.continuation || !selected(step())) {
      reply.text = words("Choose a linked Do attempt if one is recorded.",
        "Выберите связанную попытку Do, если для неё записан вход.");
    } else {
      const topic = {changes: "changes", tests: "tests-in-handoff", verdict: "handoff-verdict"}
        [intent.kind];
      reply.origin = state.scope;
      if (read?.phase === "ready") reply.text = evidenceAnswer(topic, read.value);
      else if (read?.phase === "loading") Object.assign(reply,
        {text: tr("loading"), wait: generation, topic});
      else reply.text = tr("unavailable");
    }
    door.inspect(true); drawOrbit(); drawScope(); drawInspector(); summary();
  }
  function drawHandoff() {
    const current = activeTransfer();
    if (!current) { inspector.replaceChildren(element("p", {text: tr("unavailable")})); return; }
    const h = state.handoff;
    const selectedAction = selected(step());
    renderHandoff(inspector, model.locale, current.graph,
      {view: h.view, linkIndex: current.linkIndex, continuationIndex: current.continuationIndex,
        selectedKey: h.selectedKey, phase: read?.phase || "unavailable",
        file: selectedAction ? held(selectedAction).file : null,
        evidence: current.continuation && read?.phase === "ready" ? read.value : null}, {
        select: key => { h.selectedKey = key; drawInspector(); },
        file: path => { if (selectedAction) held(selectedAction).file = path; drawInspector(); },
        link: index => {
          const link = current.graph.links[index];
          if (!link) return;
          setLink(link);
          if (h.view !== "handoff") selectProof();
          drawInspector(); drawScope(); drawOrbit();
        },
        continuation: index => {
          const next = current.graph.continuations[index];
          if (!current.options.includes(next)) return;
          h.continuation = continuationPin(next);
          if (h.view !== "handoff") selectProof();
          drawInspector(); drawScope(); drawOrbit();
        },
        tests: () => ask(words("Which of those were tested?", "Что из этого проверили тестами?")),
      });
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
    const intent = model.runId ? handoffIntent(message, state.handoff) : null;
    if (intent && !(panel && ["changes", "other-author", "verdict"].includes(intent.kind))) {
      readHandoff(intent, reply); state.messages.push(reply); paint();
      fields.messages.lastElementChild?.scrollIntoView({block: "nearest"}); return;
    }
    if (!planning && (panel || topic)) {
      if (handoffPanel) close();
      state.handoff = null;
    }
    if (panel) {
      close();
      reply.text = {limits: words("Subscription limits", "Лимиты подписок"),
        memory: words("Session history", "История сессии"),
        participants: words("Session participants", "Участники сессии")}[panel];
      state.messages.push(reply); transcript(); door.command(panel); return;
    }
    if (planning && door.planMessage(model.sessionId, message)) { transcript(); return; }
    if (topic) {
      const s = step();
      if (patchStep(s)) {
        const a = selected(s);
        if (a) held(a).tab = topic;
        reply.origin = state.scope;
        choose(s);
        if (!a) reply.text = tr(state.scope.actionId ? "attempt_missing" : "no_attempt");
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
    const patches = scene?.steps.filter(patchStep) || [];
    const target = patchStep(step()) ? step() : patches.length === 1 ? patches[0] : null;
    if (target && model.ready) {
      const proof = tr("step_tests", {step: target.title || target.nodeId});
      fields.quick.append(button(proof, () => { choose(target); ask(proof); }));
    }
    if (model.ready && model.runId && participants.includes("grok-build")
        && participants.includes("codex")) {
      const q = words("What did Grok hand to Codex?", "Что Grok передал Codex?");
      fields.quick.append(button(q, () => ask(q)));
      if (state.handoff?.link) {
        const next = words("Which of those were tested?", "Что из этого проверили тестами?");
        fields.quick.append(button(next, () => ask(next)));
      }
    }
    const limits = words("Limits", "Лимиты");
    fields.quick.append(button(limits, () => ask(limits)));
    drawScope(); drawOrbit(); summary(); transcript();
    if (open) drawInspector();
  }
  function sync(next) {
    if (disposed) return;
    const switching = model?.sessionId !== next.sessionId || model?.runId !== next.runId;
    if (switching) {
      if (state) state.draft = fields.command.value;
      revoke();
      handoffPanel = false; projectionDetail = null; projection = null;
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
      for (const key of ["intro", "orbitHere", "resultHere", "messages", "scopeHere", "quick"])
        fields[key].replaceChildren();
      fields.command.value = ""; return;
    }
    if (switching) fields.command.value = state.draft;
    if (open && !handoffPanel && !step()) {
      revoke(); open = false; inspector.replaceChildren(); door.inspect(false);
    }
    if (open && handoffPanel && state.handoff?.view !== "handoff") selectProof();
    else load();
    paint();
  }
  fields.command.addEventListener("input", () => {
    if (state) state.draft = fields.command.value;
  }, {signal: events.signal});
  fields.send.addEventListener("submit", e => {
    e.preventDefault(); ask(fields.command.value);
  }, {signal: events.signal});
  return {sync, close, paletteSteps, openStep,
    history: () => (state?.messages || []).map(({role, text, origin}) =>
      ({role, text: origin ? scopeName(origin) + " · " + text : text})),
    dispose() { disposed = true; revoke(); events.abort(); sessions.clear(); }};
}
