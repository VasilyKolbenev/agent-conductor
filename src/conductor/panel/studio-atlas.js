"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {sceneOf} from "./studio-scene-model.js";
import {answerFor, atlasInspector, matchesAtlasAttempt} from "./studio-atlas-inspector.js";

const tr = (view, key, args) => localize(view, "atlas." + key, args);
const rows = value => Array.isArray(value) ? value : [];
const patchStep = step => step.kind === "task" && step.node.capability === "dispatch"
  && step.node.arguments?.profile === "implement-patch-v1";

function attempts(detail, step) {
  return rows(detail.records).filter(row => row.record_type === "action_request"
    && row.record?.node_id === step.nodeId).map(row => row.record);
}
function button(text, attrs, action) {
  const node = element("button", {type: "button", text, ...attrs});
  node.addEventListener("click", action);
  return node;
}
function session() {
  return {step: null, actions: new Map(), choices: new Map(), draft: "", messages: []};
}
function pick(state, step, requests) {
  const saved = state.actions.get(step.nodeId);
  return requests.find(row => row.action_id === saved) || requests.at(-1) || null;
}
function intent(text) {
  const words = text.toLocaleLowerCase();
  if (/тест|test|assert/.test(words)) return "tests";
  if (/вердикт|проверяющ|принима|checker|verdict|accept/.test(words)) return "verdict";
  if (/измен|патч|diff|chang|patch/.test(words)) return "diff";
  return null;
}

// The run read supplies selectable nodes, not authority. Each inspector read has its own epoch.
export function atlasScene(root, door) {
  const sessions = new Map();
  let view, detail, scene, current, shell, read, token = 0, stop, key = null;
  let ready = false, factCount = 0, previousLocale = null;

  function revoke() {
    if (current && view) settlePending(token, null);
    token += 1;
    if (stop) stop.abort();
    stop = null; key = null; read = null;
  }
  function settlePending(epoch, evidence) {
    let updated = false;
    for (const row of current.messages) {
      if (row.wait !== epoch) continue;
      row.text = evidence ? answerFor(view, row.tab, evidence) : tr(view, "unavailable");
      delete row.wait; updated = true;
    }
    if (updated && shell) drawLog();
  }
  function step() { return scene?.steps.find(row => row.nodeId === current?.step); }
  function request() {
    const chosen = step();
    return chosen && patchStep(chosen) ? pick(current, chosen, attempts(detail, chosen)) : null;
  }
  function choice(action) {
    if (!current.choices.has(action.action_id)) current.choices.set(action.action_id,
      {tab: "diff", file: null, test: null});
    return current.choices.get(action.action_id);
  }

  function load(refresh = false) {
    const selected = step(), action = request();
    const next = action && ready ? JSON.stringify([scene.runId, selected.nodeId,
      action.action_id, action.attempt_id]) : null;
    if (next === key && !refresh) return;
    revoke();
    if (!next) return;
    key = next; read = {phase: "loading"};
    const epoch = token;
    const run = scene.runId;
    stop = door.stop();
    Promise.resolve(door.read(run, selected.nodeId, action.action_id, stop)).then(answer => {
      if (epoch !== token || key !== next) return;
      read = matchesAtlasAttempt(answer, action, selected, run)
        ? {phase: "ready", value: answer} : {phase: "unavailable"};
      settlePending(epoch, read.value);
      drawInspector();
    }, () => {
      if (epoch !== token || key !== next) return;
      read = {phase: "unavailable"};
      settlePending(epoch, null);
      drawInspector();
    });
  }

  function selectStep(id, focus = false) {
    current.step = id;
    load(); drawOrbit(); drawInspector();
    if (focus) shell.heading.focus({preventScroll: true});
  }
  function close() {
    const selected = current.step;
    selectStep(null);
    [...shell.plane.querySelectorAll("[data-atlas-step]")]
      .find(b => b.dataset.atlasStep === selected)?.focus();
  }

  function drawOrbit() {
    const steps = scene.steps.filter(s => s.kind === "task");
    shell.plane.replaceChildren(element("span", {className: "atlas-track", "aria-hidden": "true"}),
      element("span", {className: "atlas-core", "aria-hidden": "true",
        text: tr(view, "title")}));
    shell.plane.classList.toggle("atlas-plane--list", steps.length > 6);
    steps.forEach((row, i) => {
      const title = row.node.title || row.nodeId, selected = current.step === row.nodeId;
      const b = button("", {"aria-label": title, "aria-pressed": String(selected),
        className: "atlas-node", "data-atlas-step": row.nodeId,
        "data-atlas-status": row.word,
        "data-focus": "atlas:orbit:" + row.nodeId}, () => selectStep(row.nodeId, true));
      const angle = 2 * Math.PI * i / steps.length - 2.85;
      b.style.setProperty("--atlas-x", (50 + 38 * Math.cos(angle)) + "%");
      b.style.setProperty("--atlas-y", (49 + 30 * Math.sin(angle)) + "%");
      const label = element("span", {className: "atlas-node-name", text: title});
      b.append(element("i", {"aria-hidden": "true"}), label);
      const actor = scene.participants.find(p => p.instanceId === row.ownerId);
      if (row.ownerId) b.append(element("small", {text: actor?.adapter || row.ownerId}));
      b.title = title + " · " + localize(view, "scene." + row.word)
        + (row.ownerId ? " · " + row.ownerId : "");
      shell.plane.append(b);
    });
  }

  function drawLog() {
    shell.log.replaceChildren();
    for (const row of current.messages) {
      shell.log.append(element("div", {className: "atlas-message"}, [
        element("small", {text: tr(view, row.human ? "you" : "title")
          + (row.id ? " · " + row.id : "")}),
        element("p", {text: row.text}),
      ]));
    }
  }

  function ask(text) {
    const question = text.trim();
    if (!question) return;
    const tab = intent(question);
    if (!request() && tab) {
      const options = scene.steps.filter(patchStep);
      if (options.length === 1) selectStep(options[0].nodeId);
    }
    const action = request();
    const id = action?.action_id || "";
    let answer = tr(view, "ask_help");
    if (tab && !action) answer = tr(view, step() ? "no_attempt" : "select");
    if (tab && action) {
      const held = choice(action);
      held.tab = tab;
      if (tab === "tests") held.test = null;
      answer = ready && read?.phase === "ready" ? answerFor(view, tab, read.value)
        : tr(view, !ready ? "offline" : read?.phase === "loading" ? "loading" : "unavailable");
    }
    const message = {human: false, id, text: answer};
    if (action && tab && ready && read?.phase === "loading") {
      message.wait = token; message.tab = tab;
    }
    current.messages.push({human: true, id, text: question}, message);
    current.draft = ""; shell.input.value = "";
    drawLog(); drawInspector();
    shell.log.scrollTop = shell.log.scrollHeight;
    if (action && shell.chat.inert) shell.heading.focus({preventScroll: true});
  }

  function syncSheet() {
    if (!shell) return;
    // The text on the sheet's close button is visible only in the sheet layout.
    const open = !shell.panel.hidden && shell.closeLabel.getClientRects().length > 0;
    const movesFocus = open && shell.chat.contains(document.activeElement);
    shell.chat.inert = open;
    if (movesFocus) shell.heading.focus({preventScroll: true});
  }

  function createShell() {
    const header = element("header", {className: "atlas-header"}, [
      element("span", {className: "atlas-emblem", "aria-hidden": "true", text: "✧"}),
      element("h2", {text: tr(view, "title")}), element("small", {text: tr(view, "scope")}),
    ]);
    const plane = element("div", {className: "atlas-plane", role: "group",
      "aria-label": tr(view, "orbit")});
    const log = element("div", {className: "atlas-log", role: "log",
      "aria-label": tr(view, "conversation"), "aria-live": "polite"});
    const input = element("input", {type: "text", maxlength: "1000", autocomplete: "off",
      "aria-label": tr(view, "message"), placeholder: tr(view, "message"),
      "data-atlas-field": "", "data-focus": "atlas:message:" + scene.runId});
    input.value = current.draft;
    input.addEventListener("input", () => { current.draft = input.value; });
    const form = element("form", {className: "atlas-form"}, [input,
      element("button", {type: "submit", text: tr(view, "send")})]);
    form.addEventListener("submit", event => { event.preventDefault(); ask(input.value); });
    const prompts = element("div", {className: "atlas-prompts"});
    for (const name of ["ask_diff", "ask_tests", "ask_verdict"]) {
      const label = tr(view, name);
      prompts.append(button(label, {"data-focus": "atlas:" + name}, () => ask(label)));
    }
    const chat = element("div", {className: "atlas-chat"}, [header,
      element("section", {className: "atlas-orbit"}, [
        element("h3", {text: tr(view, "orbit")}), plane,
      ]), log, prompts, form]);
    const heading = element("h3", {tabindex: "-1", text: tr(view, "inspect")});
    const closeLabel = element("span", {className: "atlas-sheet-close", text: tr(view, "close")});
    const closeButton = button("×", {"aria-label": tr(view, "close"), "data-atlas-close": "",
      "data-focus": "atlas:close"}, close);
    closeButton.append(closeLabel);
    const body = element("div", {className: "atlas-inspector-body"});
    const panel = element("aside", {className: "atlas-inspector", "data-atlas-inspector": "",
      "aria-label": tr(view, "inspect"), hidden: ""}, [
      element("header", {className: "atlas-inspector-head"}, [heading, closeButton]), body]);
    root.replaceChildren(chat, panel);
    shell = {chat, plane, log, input, panel, heading, closeLabel, body};
    drawLog();
  }

  function drawInspector() {
    if (!shell) return;
    const selected = step();
    shell.panel.hidden = !selected;
    root.classList.toggle("atlas-open", Boolean(selected));
    syncSheet();
    shell.body.replaceChildren();
    if (!selected) return;
    shell.heading.textContent = selected.title || selected.nodeId;
    if (!patchStep(selected)) { shell.body.append(element("p", {text: tr(view, "not_patch")})); return; }
    const options = attempts(detail, selected);
    const action = request();
    if (!action) { shell.body.append(element("p", {text: tr(view, "no_attempt")})); return; }
    const picker = element("select", {"data-atlas-attempt": "", "aria-label": tr(view, "attempt"),
      "data-focus": "atlas:attempt"});
    options.forEach((row, i) => {
      const name = tr(view, "attempt_name", {n: String(i + 1), total: String(options.length),
        id: row.action_id});
      picker.append(element("option", {value: row.action_id, text: name}));
    });
    picker.value = action.action_id;
    picker.addEventListener("change", () => {
      current.actions.set(selected.nodeId, picker.value); load(); drawInspector();
      shell.body.querySelector("[data-atlas-attempt]").focus({preventScroll: true});
    });
    shell.body.append(element("label", {className: "atlas-attempt"},
      [element("span", {text: tr(view, "attempt")}), picker]));
    if (ready && read?.phase === "ready") {
      const held = choice(action);
      atlasInspector(shell.body, view, read.value, held, (patch, selectTab = false) => {
        const before = document.activeElement?.dataset.focus;
        Object.assign(held, patch);
        drawInspector();
        const focus = selectTab ? "atlas:tab:" + patch.tab : before;
        [...shell.body.querySelectorAll("[data-focus]")].find(n => n.dataset.focus === focus)?.focus();
      });
    } else {
      const phase = !ready ? "offline" : read?.phase === "loading" ? "loading" : "unavailable";
      shell.body.append(element("p", {role: "status", text: tr(view, phase)}));
    }
    const refresh = button(tr(view, "refresh"), {className: "atlas-refresh",
      "data-focus": "atlas:refresh"}, () => { load(true); drawInspector(); });
    refresh.disabled = !ready || read?.phase === "loading";
    const controls = button(localize(view, "bridge.region"), {"data-focus": "atlas:controls"},
      () => document.getElementById("studioBridge")?.querySelector("button,summary")?.focus());
    shell.body.append(refresh, controls);
  }

  function sync(next) {
    const d = next.runs.detail;
    const selected = next.screen === "runs" && next.runs.selectedId === d?.run?.run_id;
    const nextScene = selected ? (detail === d ? scene : sceneOf(d)) : null;
    if (!nextScene?.steps.some(patchStep)) {
      if (shell) { revoke(); root.replaceChildren(); root.hidden = true; }
      shell = detail = scene = current = null; ready = false;
      return;
    }
    const fresh = scene?.runId !== nextScene.runId;
    const localeChanged = next.locale !== previousLocale;
    const wasReady = ready, detailChanged = detail !== d;
    view = next; detail = d; scene = nextScene; previousLocale = next.locale;
    ready = next.connection === "open" && next.runs.phase === "ready";
    if (fresh) {
      revoke();
      if (!sessions.has(scene.runId)) sessions.set(scene.runId, session());
      current = sessions.get(scene.runId);
    }
    if (fresh || localeChanged) { root.hidden = false; createShell(); }
    const records = rows(d.records).length;
    if (fresh || localeChanged || detailChanged || wasReady !== ready) {
      if (current.step && !step()) current.step = null;
      load(!fresh && ready && records !== factCount);
      drawOrbit(); drawInspector();
    }
    factCount = records;
  }
  root.addEventListener("keydown", event => {
    if (event.key === "Escape" && current?.step) { event.preventDefault(); close(); }
  });
  window.addEventListener("resize", syncSheet);
  return {sync};
}
