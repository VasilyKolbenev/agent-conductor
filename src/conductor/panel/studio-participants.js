"use strict";
// The command deck reads ONE frozen run, not the currently edited workflow or
// the machine's installed-provider roster. A planet is an instance: two steps
// using one instance remain one planet, and two instances using one adapter
// remain two. Selection is presentation only and never authorizes execution.
import {element} from "./command-view.js";
import {attemptInFlight} from "./studio-runread.js";
import {VERIFICATION_FAILED_NOTE} from "./studio-runwords.js";

function rows(value) { return Array.isArray(value) ? value : []; }
function show(value) { return value === null || value === undefined
  || value === "" ? "not stated" : String(value); }
function note(text) { return element("p", {className: "studio-note", text}); }
function fact(label, value) { return note(`${label}: ${show(value)}`); }

export function participantSelection(mount) {
  const deck = mount.querySelector("[data-deck-run]");
  const chosen = deck && deck.querySelector('[aria-pressed="true"]');
  return chosen ? {run: deck.getAttribute("data-deck-run"),
    instance: chosen.getAttribute("data-instance")} : null;
}

function stepsOf(detail, instance) {
  return rows(detail.graph?.definition?.nodes)
    .filter((node) => node.instance_id === instance
      || node.verifier_instance_id === instance);
}

function stepRead(detail, node) {
  const runtime = rows(detail.graph?.runtime?.nodes)
    .find((row) => row.node_id === node.node_id);
  const scheduled = rows(detail.graph?.schedule?.nodes)
    .find((row) => row.node_id === node.node_id);
  const body = [element("strong", {text: show(node.title || node.node_id)}),
    fact("Step", node.node_id), fact("Kind", node.kind)];
  if (attemptInFlight(detail, node.node_id)) {
    body.push(note("Awaiting an attempt result. This is not proof that the "
      + "vendor process is still running."));
  }
  body.push(fact("Execution phase", runtime?.phase),
    fact("Outcome", runtime?.outcome), fact("Plan position", scheduled?.state));
  if (runtime?.outcome === "verification_failed") {
    body.push(note(VERIFICATION_FAILED_NOTE));
  }
  for (const [key, label] of [["blocked_by", "Waiting on"],
    ["closed_by", "Closed by"], ["awaiting_artifacts", "Missing documents"]]) {
    if (rows(scheduled?.[key]).length) {
      body.push(fact(label, scheduled[key].join(", ")));
    }
  }
  if (node.loop) body.push(fact("Loop", `pass ${show(runtime?.pass)} of `
    + `${show(node.loop.bound)}; returns to ${show(node.loop.back_to)}`));
  const outgoing = rows(detail.graph?.definition?.edges)
    .filter((edge) => edge.from_node === node.node_id);
  for (const edge of outgoing) {
    // GraphEdge omits its condition for an unconditional road. That is a
    // known default, unlike a missing runtime observation or quota sample.
    const condition = Object.prototype.hasOwnProperty.call(edge, "condition")
      ? show(edge.condition) : "unconditional";
    body.push(fact("Route", `${show(edge.to_node)} · ${condition}`));
  }
  return element("li", {className: "studio-deck__step"}, body);
}

function inspector(detail, instance) {
  const steps = stepsOf(detail, instance.id);
  const controls = rows(detail.controls?.instances)
    .find((row) => row.instance_id === instance.id);
  const body = [element("h4", {text: instance.id}),
    fact("Harness (adapter)", instance.adapter),
    fact("Model", instance.model)];
  if (!Object.prototype.hasOwnProperty.call(instance, "model")) {
    body.push(note("This build pinned no model for this instance, so "
      + "whatever the provider's own configuration decides is what runs."));
  }
  body.push(controls
    ? fact("Capabilities this build can serve", controls.controls.length
      ? controls.controls.join(", ") : "none served by this build")
    : note("This run's controls read has not landed here, so what this "
      + "binding can be asked to do is not stated."));
  body.push(element("h4", {text: "Steps in this run"}));
  body.push(steps.length
    ? element("ul", {className: "studio-deck__steps"},
      steps.map((node) => {
        const read = stepRead(detail, node);
        const duties = [];
        if (node.instance_id === instance.id) duties.push("perform");
        if (node.verifier_instance_id === instance.id) duties.push("verify");
        read.prepend(fact("Responsibility", duties.join(" + ")));
        return read;
      }))
    : note("No plan step is assigned to this instance."));
  body.push(note("Subscription usage and reset time are not reported by "
    + "this run. No quota estimate is made."));
  return body;
}

function planet(detail, instance, select) {
  const steps = stepsOf(detail, instance.id);
  const pending = steps.filter((node) =>
    attemptInFlight(detail, node.node_id)).length;
  const button = element("button", {type: "button",
    className: "studio-planet", "data-instance": instance.id,
    "data-focus-key": `participant:${instance.id}`, "aria-pressed": "false",
    "aria-controls": "studioParticipantInspector"}, [
    element("span", {className: "studio-planet__orb", "aria-hidden": "true",
      text: Array.from(instance.id).slice(0, 2).join("").toUpperCase()}),
    element("strong", {text: instance.id}),
    element("span", {className: "studio-note", text: instance.adapter}),
    element("span", {className: "studio-note", text:
      `${steps.length} assigned step(s) · ${pending} step(s) awaiting result`}),
    element("span", {className: "studio-planet__selection", text: "Inspect"}),
  ]);
  button.addEventListener("click", () => select(instance.id));
  return button;
}

export function participantDeck(detail, previous) {
  const bound = rows(detail.config?.instances);
  const run = detail.run?.run_id;
  const deck = element("section", {className: "studio-section studio-deck",
    "data-deck-run": run}, [element("h3", {text: "Assigned to"}),
    note("One planet per participant, not per step. These are the bindings "
      + "frozen into this run; selecting one does not start it.")]);
  if (!bound.length) {
    deck.append(note("This run's frozen configuration binds no instance, "
      + "so no adapter carries any step of it."));
    return deck;
  }
  const fleet = element("div", {className: "studio-deck__fleet",
    role: "group", "aria-label": "Participants in this run"});
  const panel = element("section", {className: "studio-deck__inspector",
    id: "studioParticipantInspector", "aria-label": "Selected participant"});
  function select(id) {
    const instance = bound.find((row) => row.id === id);
    if (!instance) return;
    for (const button of fleet.querySelectorAll("[data-instance]")) {
      const chosen = button.getAttribute("data-instance") === id;
      button.setAttribute("aria-pressed", String(chosen));
      button.querySelector(".studio-planet__selection").textContent =
        chosen ? "Selected" : "Inspect";
    }
    panel.replaceChildren(...inspector(detail, instance));
  }
  for (const instance of bound) fleet.append(planet(detail, instance, select));
  deck.append(element("div", {className: "studio-deck__body"}, [fleet, panel]));
  const retained = previous?.run === run
    && bound.some((row) => row.id === previous.instance);
  select(retained ? previous.instance : bound[0].id);
  return deck;
}
