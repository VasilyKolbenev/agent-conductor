"use strict";
// The inspector's SIXTH section: where a step goes next, and on what.
//
// Split out of `studio-sections.js` before that module reached the project's
// line cap, at the same seam and for the same reason the artifacts section was:
// that file is "the six sections, in one order", and this is the one of them
// that is about to grow. A connection is no longer only the two steps it joins
// -- it may carry a CONDITION -- so the routing controls, the gate's own
// answer, and the loop's ceiling all belong together in one place a reader can
// hold at once.
//
// THE DESIGN, in one sentence each, because these are the three ways a plan
// says what happens next and they are deliberately not interchangeable:
//
//   a condition   narrows one road to ONE word the step behind it produces.
//                 Eight words, four families, no operator and no expression:
//                 `graph_conditions.EDGE_CONDITIONS` owns them and this module
//                 offers exactly the family the source's kind can produce.
//   a gate        ANSWERS, and its answer routes. `Decision routing` below is
//                 therefore a derived reading of the roads already drawn, never
//                 a second place to draw one -- a control there would be a
//                 second authority over the same edges.
//   a loop        REOPENS, bounded. The bound is a ceiling on the POSITION and
//                 never a count of reopenings beside it.
//
// A step carrying no capability produces no word at all, so it is offered no
// condition on any road out of it -- the contract refuses one, and a select
// that offered it would be a control whose every use is refused on save.
//
// The dependency runs one way: this module reaches the toolkit and the shared
// vocabularies, and neither the sections nor the frame. Two halves of one
// inspector that could import each other would close the ring the split was
// drawn to open.
import {element, field} from "./command-view.js";
import {
  call,
  commit,
  context,
  editable,
  note,
  option,
  sectionOf,
  selectField,
  textField,
} from "./studio-fields.js";

//: `graph_definition.MIN_LOOP_BOUND` / `MAX_LOOP_BOUND`. A copy of the layer
//: that owns it, held equal by `tests/test_studio_canvas.py` against the Python
//: contract rather than trusted here.
export const LOOP_BOUND = Object.freeze({min: 1, max: 99});

//: `graph_conditions.EDGE_CONDITIONS` and `_CONDITIONS_BY_KIND`. A COPY,
//: like every other vocabulary in this window, because the module table
//: forbids reaching the edit module from here -- and held equal to the
//: Python owner, and to that module's own copy, by
//: `tests/test_studio_wiring.py` rather than trusted.
export const EDGE_CONDITIONS = Object.freeze([
  "on_approved", "on_rejected", "on_changes_requested", "on_waived",
  "on_succeeded", "on_failed",
  "on_bound_reached", "on_bound_remaining"]);
export const CONDITIONS_BY_KIND = Object.freeze({
  gate: Object.freeze([
    "on_approved", "on_rejected", "on_changes_requested", "on_waived"]),
  task: Object.freeze(["on_succeeded", "on_failed"]),
  loop: Object.freeze(["on_bound_reached", "on_bound_remaining"]),
});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function outgoingRows(box, form) {
  const outgoing = form.edges.filter((edge) => edge.from_node === form.node.node_id);
  if (!outgoing.length) {
    note(box, "No outgoing connection: this step ends the plan as drawn.");
    return;
  }
  const list = element("ul", {className: "studio-edges"});
  for (const edge of outgoing) {
    const id = `${edge.from_node} ${edge.to_node}`;
    const item = element("li", {className: "studio-edge-row", "data-edge": id});
    const open = element("button", {className: "studio-edge-row__select",
      "data-focus": `edge-select-${id}`, type: "button"},
    [element("span", {className: "mono", text: `→ ${edge.to_node}`})]);
    open.addEventListener("click", () => call(form.handlers, "onSelect",
      {kind: "edge", id}));
    const drop = element("button", {"aria-label": `Disconnect `
      + `${edge.from_node} from ${edge.to_node}`,
    className: "studio-edge-row__drop", "data-focus": `edge-drop-${id}`,
    type: "button"}, [element("span", {text: "Disconnect"})]);
    drop.addEventListener("click", () => call(form.handlers, "onEdit", {
      type: "delete-edge", fromId: edge.from_node, toId: edge.to_node}));
    item.append(open, conditionControl(form, edge), editable(drop, form));
    list.append(item);
  }
  box.append(list);
}

//: What the step BEHIND a road can produce, or nothing at all.
//
// A task carrying no capability is carried out by nobody: no adapter runs it,
// no receipt is written for it, and it produces no word. The contract refuses a
// condition on any road out of one, so this offers none -- a select whose every
// use is refused on save is worse than no select.
function conditionWords(node) {
  if (node.kind === "task" && !node.capability) return [];
  return CONDITIONS_BY_KIND[node.kind] || [];
}

function conditionControl(form, edge) {
  const words = conditionWords(form.node);
  if (!words.length) {
    return element("span", {className: "studio-edge-row__note",
      text: "carries out no work — no condition"});
  }
  const control = element("select", {"data-edge-condition":
    `${edge.from_node} ${edge.to_node}`,
  "data-focus": `edge-condition-${edge.from_node} ${edge.to_node}`,
  name: "edge_condition"},
  [option("", "always — unconditional"),
    ...words.map((word) => option(word, conditionLabel(word)))]);
  control.value = typeof edge.condition === "string" ? edge.condition : "";
  control.addEventListener("change", () => call(form.handlers, "onEdit", {
    type: "set-edge-condition", fromId: edge.from_node, toId: edge.to_node,
    value: control.value}));
  return editable(control, form);
}

//: One word, one sentence a person reads. Derived from the vocabulary rather
//: than typed beside it: a word this build gains and nobody labels would show
//: as its own identifier, which is a control nobody can use.
function conditionLabel(word) {
  return word.replace(/^on_/, "").replace(/_/g, " ");
}

//: Where a decision SENDS this run, read off the roads already drawn.
//
// Read-only on purpose. A gate answers, and the answer routes down whichever
// road carries that word -- so the place to change routing is the road, and a
// second control here would be a second authority over one edge. What this
// gives a person is the reading they cannot get from the edge list alone: which
// answer opens which step.
function decisionRouting(box, form) {
  if (form.node.kind !== "gate") {
    context(box, "Decision routing", "none — only a gate's answer routes",
      "the workflow contract");
    return;
  }
  const outgoing = form.edges.filter(
    (edge) => edge.from_node === form.node.node_id);
  const routed = outgoing.filter((edge) => typeof edge.condition === "string");
  if (!outgoing.length) {
    context(box, "Decision routing", "none — this gate opens no step",
      "the workflow document");
    return;
  }
  if (!routed.length) {
    context(box, "Decision routing",
      `every answer opens ${outgoing.map((edge) => edge.to_node).join(", ")}`,
      "the workflow document");
    return;
  }
  const list = element("ul", {className: "studio-routes"});
  for (const edge of routed) {
    list.append(element("li", {className: "studio-route",
      "data-route": `${edge.condition} ${edge.to_node}`,
      text: `${conditionLabel(edge.condition)} → ${edge.to_node}`}));
  }
  box.append(field("Decision routing", list));
}

function connectControl(box, form) {
  const others = form.nodes.filter((row) => row.node_id !== form.node.node_id);
  if (!others.length) {
    note(box, "There is no other step to connect this one to.");
    return;
  }
  const target = element("select", {"data-focus": "connect-target",
    name: "connect_to"}, others.map((row) => option(row.node_id,
      `${row.node_id} — ${row.title}`)));
  const go = element("button", {className: "studio-connect",
    "data-focus": "connect-go", type: "button"},
  [element("span", {text: "Connect"})]);
  go.addEventListener("click", () => call(form.handlers, "onEdit", {
    type: "connect", fromId: form.node.node_id, toId: target.value}));
  const wrapper = field("Connect to", editable(target, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper, editable(go, form));
}

//: `graph_values.GATE_SUCCESS_DEMANDS` -- what a gate may demand of the answer
//: that settles it. Held to the Python owner by a source test rather than
//: trusted here, like every other closed vocabulary on this surface.
export const GATE_SUCCESS_DEMANDS = Object.freeze(["human_approval"]);
//: What each of those words is offered AS. The control is built from the
//: vocabulary above rather than from a second list beside it, so a word the
//: Python layer grows appears here instead of being silently unofferable --
//: and a word with no sentence yet shows as itself rather than as nothing,
//: which is a visible fault instead of a missing option.
const DEMAND_LABELS = Object.freeze({
  human_approval: "yes — this gate may not be waived",
});

//: The one thing a gate may demand, and the only place it can be said.
//:
//: It is a TIGHTENING and it is the only kind this vocabulary may grow: saying
//: it removes an answer, and saying nothing leaves every answer a gate has
//: always had. What it removes is `waive` -- the one answer that closes a gate
//: without judging the work -- and the removal is real at three doors: this
//: window stops offering it, the server refuses it before anything is written,
//: and the store refuses a journal that carries one anyway.
function gateDemand(box, form) {
  const named = typeof form.node.success_requires === "string"
    ? form.node.success_requires : "";
  selectField(box, form, "Require explicit human approval — waiver disabled",
    "success_requires",
    [{value: "", label: "no — this gate may be approved, rejected, sent back "
      + "for changes, or waived"}].concat(
      GATE_SUCCESS_DEMANDS.map((word) => ({value: word,
        label: DEMAND_LABELS[word] || word}))),
    named);
  note(box, "Waiving is the one answer that closes a gate without judging the "
    + "work. Requiring explicit human approval removes it: the Decisions "
    + "screen stops offering it, the server refuses it before anything is "
    + "recorded, and a journal carrying one is refused when it is read. "
    + "Rejecting and requesting changes stay available — this makes the gate "
    + "harder to pass, never harder to fail. A connection out of this gate on "
    + "`on_waived` becomes a road no run could travel, so publishing one is "
    + "refused.");
}

function gateControls(box, form) {
  if (form.node.kind === "gate") {
    textField(box, form, "Gate id", "gate_id", form.node.gate_id,
      "The id a Human's decision receipt names. A run's gate state is read "
      + "through it, and through nothing else.");
    gateDemand(box, form);
  } else {
    context(box, "Human decision", "none — only a gate step carries one",
      "the workflow contract");
  }
  decisionRouting(box, form);
}

function loopControls(box, form) {
  if (form.node.kind !== "loop") {
    context(box, "Loop", "none — only a loop step reopens work",
      "the workflow contract");
    return;
  }
  const loop = isObject(form.node.loop) ? form.node.loop : {};
  const targets = form.nodes.filter((row) => row.node_id !== form.node.node_id);
  selectField(box, form, "Reopens (back_to)", "loop_back_to",
    targets.map((row) => ({value: row.node_id,
      label: `${row.node_id} — ${row.title}`})), loop.back_to || "");
  const bound = element("input", {"data-edit-field": "loop_bound",
    "data-focus": "edit-loop_bound", max: String(LOOP_BOUND.max),
    min: String(LOOP_BOUND.min), name: "loop_bound", step: "1", type: "number"});
  bound.value = loop.bound === undefined ? "" : String(loop.bound);
  bound.addEventListener("change", () => {
    const value = Number(bound.value);
    if (!Number.isInteger(value) || value < LOOP_BOUND.min
        || value > LOOP_BOUND.max) {
      call(form.handlers, "onStatus", `A loop bound is a whole number from `
        + `${LOOP_BOUND.min} to ${LOOP_BOUND.max}.`);
      return;
    }
    commit(form, "loop_bound", value);
  });
  const wrapper = field("Loop bound (greatest pass)", editable(bound, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper);
  note(box, "A bound is a ceiling on the POSITION — the greatest pass this "
    + "work may reach — never a count of reopenings beside it. Which pass a "
    + "run is on is the run's own fact and is shown under Assignment's run "
    + "context, never here.");
}

//: The SAME select, on the edge's own panel in the frame next door.
//
// Exported rather than rebuilt there, because the two surfaces must not be able
// to offer different words for one road -- and because the frame may not reach
// the module that owns this vocabulary. A road whose source this drawing no
// longer carries, or whose source produces no word, states the fact rather than
// offering a control nothing could accept.
export function edgeConditionRow(box, form, fromId, toId) {
  const source = form.nodes.filter(isObject)
    .find((node) => node.node_id === fromId);
  const edge = form.edges.filter(isObject).find(
    (row) => row.from_node === fromId && row.to_node === toId);
  if (!source || !edge) {
    context(box, "Condition", "none — this drawing does not carry that road",
      "the workflow document");
    return;
  }
  const words = conditionWords(source);
  if (!words.length) {
    context(box, "Condition",
      `none — ${fromId} carries out no work, so it produces no word`,
      "the workflow contract");
    return;
  }
  const control = element("select", {"data-edge-condition": `${fromId} ${toId}`,
    "data-focus": "edge-condition", name: "edge_condition"},
  [option("", "always — unconditional"),
    ...words.map((word) => option(word, conditionLabel(word)))]);
  control.value = typeof edge.condition === "string" ? edge.condition : "";
  control.addEventListener("change", () => call(form.handlers, "onEdit", {
    type: "set-edge-condition", fromId, toId, value: control.value}));
  const wrapper = field("Condition", editable(control, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper);
}


export function transitionSection(form) {
  const box = sectionOf("transitions", "Transitions");
  box.append(element("h4", {text: "Outgoing connections"}));
  outgoingRows(box, form);
  connectControl(box, form);
  box.append(element("h4", {text: "Human decision routing"}));
  gateControls(box, form);
  box.append(element("h4", {text: "Loop"}));
  loopControls(box, form);
  return box;
}

