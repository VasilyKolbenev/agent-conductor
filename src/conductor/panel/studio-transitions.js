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
  unsupported,
} from "./studio-fields.js";

//: `graph_definition.MIN_LOOP_BOUND` / `MAX_LOOP_BOUND`. A copy of the layer
//: that owns it, held equal by `tests/test_studio_canvas.py` against the Python
//: contract rather than trusted here.
export const LOOP_BOUND = Object.freeze({min: 1, max: 99});

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
    item.append(open, editable(drop, form));
    list.append(item);
  }
  box.append(list);
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

function gateControls(box, form) {
  if (form.node.kind === "gate") {
    textField(box, form, "Gate id", "gate_id", form.node.gate_id,
      "The id a Human's decision receipt names. A run's gate state is read "
      + "through it, and through nothing else.");
  } else {
    context(box, "Human decision", "none — only a gate step carries one",
      "the workflow contract");
  }
  unsupported(box, "Decision routing", "This build runs one plan: a decision "
    + "records approval, rejection, changes requested or a waiver, and it "
    + "does not choose between two different onward paths.");
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

export function transitionSection(form) {
  const box = sectionOf("transitions", "Transitions");
  box.append(element("h4", {text: "Outgoing connections"}));
  outgoingRows(box, form);
  connectControl(box, form);
  unsupported(box, "Edge conditions", "A connection carries exactly the two "
    + "steps it joins. There is no condition field for one to be stored in.");
  box.append(element("h4", {text: "Human decision routing"}));
  gateControls(box, form);
  box.append(element("h4", {text: "Loop"}));
  loopControls(box, form);
  return box;
}
