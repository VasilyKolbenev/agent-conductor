"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {word as shellWord} from "./arachnid-copy.js";
import {ADVICE_WORKFLOW} from "./desk-wizard-cycle.js";

export function patchStep(step) {
  return step?.kind === "task" && step.node.capability === "dispatch"
    && step.node.arguments?.profile === "implement-patch-v1";
}

// The track and its buttons share the prototype's 600 × 220 coordinate system.
function angle(index, count) {
  return (count === 1 ? -45 : -178 + (238 * index / (count - 1))) * Math.PI / 180;
}
function point(theta) {
  return [300 + 220 * Math.cos(theta), 110 + 65 * Math.sin(theta)];
}

function guardianState(view, scene) {
  if (!scene.ending.ended && scene.steps.some(step => step.word === "awaiting_result")) {
    return view.detail?.config?.workflow?.id === ADVICE_WORKFLOW ? "thinking" : "sending";
  }
  if (!scene.ending.ended && scene.steps.some(step => step.word === "needs_decision")) return "waiting";
  const latest = view.detail?.records?.findLast(row =>
    row.record_type === "action_result" || row.record_type === "action_request");
  return latest?.record_type === "action_result" ? "receiving" : "waiting";
}

export function renderOrbit(host, view, scene, chosen, select) {
  const steps = scene.steps.filter(row => row.kind === "task");
  const ru = view.locale === "ru";
  const flowId = view.detail?.config?.workflow?.id || view.detail?.config?.cycle?.id;
  const dalio = typeof flowId === "string" && /^dalio(?:-|$)/.test(flowId)
    && steps.map(row => row.nodeId).join("/") === "goal/identify/diagnose/design/do";
  const orbitName = dalio ? (ru ? "Орбита Далио" : "Dalio orbit") : localize(view, "atlas.orbit");
  const actualFocus = host.ownerDocument.activeElement?.closest("[data-step]")?.dataset.step;
  host.replaceChildren();
  if (!steps.length) return;
  const section = element("section", {className: "orbit", "aria-label": orbitName});
  const settled = steps.filter(s => s.scheduled?.state === "settled").length;
  const title = element("h2", {text: orbitName});
  const header = element("div", {className: "orbit-header"}, [title,
    element("span", {className: "mono", text: settled + " / " + steps.length
      + (ru ? " шагов" : " steps")})]);
  const stage = element("div", {className: steps.length > 6 ? "stage stage-list" : "stage",
    role: "group", "aria-label": localize(view, "atlas.orbit")});
  const template = host.ownerDocument.getElementById("orbital-plane");
  if (template) stage.append(template.content.cloneNode(true));
  const selectedIndex = steps.findIndex(row => row.nodeId === chosen);
  const arc = stage.querySelector(".selected-arc");
  if (arc && selectedIndex > 0) {
    arc.removeAttribute("hidden");
    arc.setAttribute("d", "M " + point(angle(selectedIndex - 1, steps.length)).join(" ")
      + " A 220 65 0 0 1 " + point(angle(selectedIndex, steps.length)).join(" "));
  }
  const core = stage.querySelector(".core-name");
  if (core) {
    const pose = guardianState(view, scene);
    stage.dataset.guardian = pose;
    core.textContent = shellWord(view.locale, "assistantHeading");
    core.append(element("small", {text: shellWord(view.locale, "orbit." + pose)}));
  }
  const tilt = -9 * Math.PI / 180;
  steps.forEach((row, index) => {
    const theta = angle(index, steps.length), x = 220 * Math.cos(theta), y = 65 * Math.sin(theta);
    const label = row.title || row.nodeId;
    const state = localize(view, "scene." + row.word);
    const actor = scene.participants.find(p => p.instanceId === row.ownerId);
    const button = element("button", {type: "button", className: "node", "data-step": row.nodeId,
      "data-status": row.word, "aria-pressed": String(row.nodeId === chosen), "aria-label": label,
      "aria-description": [state, actor?.adapter || row.ownerId].filter(Boolean).join(" · "),
      title: label + " · " + state});
    if (patchStep(row)) button.dataset.effect = "patch";
    button.dataset.stage = row.node.stage || (patchStep(row) ? "do" : "custom");
    button.style.left = (300 + x * Math.cos(tilt) - y * Math.sin(tilt)) / 6 + "%";
    button.style.top = (110 + x * Math.sin(tilt) + y * Math.cos(tilt)) / 2.2 + "%";
    const name = element("span", {className: "node-label", text: label});
    if (row.ownerId) name.append(element("small", {className: "node-role",
      text: actor?.adapter || row.ownerId}));
    const planet = element("i", {className: "planet", "aria-hidden": "true"},
      [element("i", {className: "planet-detail"})]);
    button.append(planet, name);
    button.addEventListener("click", () => select(row));
    button.addEventListener("keydown", event => {
      const count = steps.length;
      const next = {Home: 0, End: count - 1, ArrowLeft: (index - 1 + count) % count,
        ArrowRight: (index + 1) % count};
      if (!Object.hasOwn(next, event.key)) return;
      event.preventDefault(); stage.querySelectorAll("[data-step]")[next[event.key]].focus();
    });
    stage.append(button);
  });
  const footer = element("div", {className: "orbit-footer"});
  const word = scene.ending.plan_word;
  const other = {open: ru ? "Цикл открыт" : "Cycle open",
    stalled: ru ? "Цикл остановился" : "Cycle stalled"};
  if (word) footer.append(element("span", {text: other[word]
    || (["complete", "cancelled", "failed"].includes(word)
      ? localize(view, "run_docs.ending_" + word) : word)}));
  footer.append(element("span", {className: "orbit-legend", text: scene.runId}));
  section.append(header, stage, footer); host.append(section);
  if (actualFocus) [...stage.querySelectorAll("[data-step]")]
    .find(node => node.dataset.step === actualFocus)?.focus({preventScroll: true});
}
