"use strict";
// The workflow canvas: DOM step buttons over an SVG edge layer, exactly the
// two-layer shape `graph-view.js` already ships, with pan, zoom, selection and
// editing added on top of it. Every string enters as a text node; no markup is
// ever parsed here, and this module reaches no network and no clock.
//
// The one thing this file refuses to do is mix two documents. A workflow
// DEFINITION -- a draft, or a published revision -- is what is drawn. What a
// RUN did is a different document naming no workflow, so it is drawn only
// where the run's own plan carries the same step id, always inside a container
// labelled `run`, and the banner says out loud that a step id is the only join
// this build has: `studio_routes.run_row` states the same from the other side.
import {localize} from "./studio-i18n.js";
import {element} from "./command-view.js";
// The pure half of the canvas: where a step goes, and how an edge is named.
// It moved next door when this file crossed the line cap, and is re-exported
// so the surface both other slices code against did not move with it.
import {CELL, MOVE_NUDGE, canvasLayout, cellMid, cellX, cellY, droppedAt,
  edgeEnds, edgeId} from "./studio-layout.js";
import {workflowOrbit} from "./studio-orbit.js";
export {CELL, canvasLayout, edgeEnds, edgeId};

// -- vocabularies this module consumes -------------------------------------
//
// Copies of the layers that own them, held equal to the PYTHON side by
// `tests/test_studio_canvas.py` rather than to a second list written down
// beside this one. `studio-inspector.js` carries the same copies because the
// module table forbids it importing this file; that test holds the two equal.

//: `graph_definition.NODE_KINDS`. A cycle has one sanctioned shape: a `loop`.
export const NODE_KINDS = Object.freeze(["task", "gate", "loop"]);
//: `graph_projection.NODE_PHASES` -- where a run's own records carry a step.
export const NODE_PHASES = Object.freeze([
  "idle", "proposed", "requested", "running", "observed"]);
//: `graph_projection.GATE_STATES`.
export const GATE_STATES = Object.freeze([
  "idle", "satisfied", "failed", "changes_requested", "waived", "unknown"]);
//: `graph_definition.DALIO_STAGES`, in the ONE order the product numbers them.
export const STAGE_NAMES = Object.freeze([
  "goal", "identify", "diagnose", "design", "do"]);

//: The shape-and-word each step wears. A glyph is a SHAPE carried in text, so
//: it survives a stylesheet that has not landed and a colour-blind reader;
//: `studio.css` adds the contour on the `--<kind>` class beside it.
export const KIND_MARKS = Object.freeze({
  task: Object.freeze({glyph: "▭", label: "Task"}),
  gate: Object.freeze({glyph: "⬡", label: "Human gate"}),
  loop: Object.freeze({glyph: "↻", label: "Loop"}),
});
//: A review step is a TASK whose capability is `review`. It is derived from the
//: document's own word and never from a provider id, so no provider-name switch
//: is needed to tell a review apart from any other work.
export const REVIEW_CAPABILITY = "review";
export const REVIEW_MARK = Object.freeze({
  glyph: "◇", label: "Review"});

//: Every edit either surface may ask for. One closed vocabulary, one callback:
//: `handlers.onEdit` is the single door to the draft document, so slice D wires
//: one function and a new kind of edit cannot arrive unremarked.
export const EDIT_TYPES = Object.freeze([
  "add", "connect", "delete-edge", "delete-node", "duplicate", "move",
  "reorder", "set-edge-condition", "set-field",
]);

//: Cell geometry, in the units the browser suite measures. Same model as
//: `graph-view.CELL`, with one difference: the height is the FLOOR that
//: `.studio-nodes .studio-node` declares, never the pitch -- `restack` measures
//: that, because a step grows past its floor and a constant cannot follow it.
const ZOOM_MIN = 0.4;
const ZOOM_MAX = 2;
const ZOOM_STEP = 1.25;
const PAN_STEP = 64;
//: How far a pointer must travel before a press becomes a drag rather than a
//: click. Below it the gesture selects, which is what a shaky hand meant.
const DRAG_SLOP = 4;
const SVG_NS = "http://www.w3.org/2000/svg";

function call(handlers, name, value) {
  const handler = handlers && handlers[name];
  if (typeof handler === "function") handler(value);
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

// -- what is on screen -----------------------------------------------------

//: The one document the canvas draws, and WHICH one it is. A draft wins when
//: there is one, because a draft is the editable document; otherwise the latest
//: published revision is shown, read-only, because a revision is immutable.
//: `none` is a real state and says so rather than drawing an empty grid.
export function canvasDocument(state) {
  const workflows = isObject(state) && isObject(state.workflows)
    ? state.workflows : {};
  const draft = workflows.draft;
  const held = isObject(draft) && !Array.isArray(draft.nodes)
    && isObject(draft.document) ? draft.document : draft;
  if (isObject(held) && Array.isArray(held.nodes)) {
    return {kind: "draft", document: held, revision: null};
  }
  const detail = isObject(workflows.detail) ? workflows.detail : {};
  const published = detail.published;
  if (isObject(published) && Array.isArray(published.nodes)) {
    return {kind: "published", document: published,
      revision: published.revision === undefined ? null : published.revision};
  }
  return {kind: "none", document: null, revision: null};
}

//: The pan and zoom this render draws at, clamped to what the view supports.
export function canvasView(state) {
  const canvas = isObject(state) && isObject(state.canvas) ? state.canvas : {};
  const pan = isObject(canvas.pan) ? canvas.pan : {};
  const zoom = Number(canvas.zoom);
  return {
    x: Number.isFinite(Number(pan.x)) ? Number(pan.x) : 0,
    y: Number.isFinite(Number(pan.y)) ? Number(pan.y) : 0,
    zoom: Number.isFinite(zoom) ? Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom)) : 1,
  };
}

function selectionOf(state) {
  const canvas = isObject(state) && isObject(state.canvas) ? state.canvas : {};
  const selection = isObject(canvas.selection) ? canvas.selection : {};
  const kind = selection.kind === "node" || selection.kind === "edge"
    ? selection.kind : null;
  return {kind, id: kind === null ? null : String(selection.id)};
}

//: The run's projection, keyed by step id -- or null when no run read is in
//: hand. Nothing is defaulted: a step the run's plan does not name draws no
//: run words at all, exactly as `graph-view.nodeChips` refuses to.
export function runtimeIndex(state) {
  const detail = isObject(state) && isObject(state.runs) ? state.runs.detail : null;
  const graph = isObject(detail) ? detail.graph : null;
  const runtime = isObject(graph) ? graph.runtime : null;
  if (!isObject(runtime) || !Array.isArray(runtime.nodes)) return null;
  const byNode = new Map();
  for (const row of runtime.nodes) {
    if (isObject(row) && typeof row.node_id === "string") byNode.set(row.node_id, row);
  }
  return {runId: String(runtime.run_id), byNode};
}

//: The row pitch, MEASURED, with every step and port put on it and the box
//: they need. `CELL.height` is a FLOOR -- `.studio-nodes .studio-node` declares
//: it as a `min-height` and a step grows past it -- so the constant pitch
//: `height + gapY` drew each step in a column on top of the one above it. The
//: tallest step the browser really laid out is the pitch instead, so no step
//: reaches the row below; one no pass has mounted measures 0 and keeps the
//: floor. The box holds the trailing gap: the last ports are inside it.
//: Called twice a pass -- once on the detached stage, once mounted -- and the
//: second call is what corrects the floor's guess. It moves nothing when the
//: two agree, so a render that changed no step's height writes no style.
function restack(stage, drawn, context) {
  let tallest = CELL.height;
  for (const each of drawn) tallest = Math.max(tallest, each.node.offsetHeight);
  if (tallest + CELL.gapY === context.pitch) return false;
  context.pitch = tallest + CELL.gapY;
  for (const each of drawn) {
    each.node.style.setProperty("--x", `${cellX(each.cell)}px`);
    each.node.style.setProperty("--y", `${cellY(each.cell, context.pitch)}px`);
    each.port.style.setProperty("--x", `${cellX(each.cell) + CELL.width}px`);
    each.port.style.setProperty("--y", `${cellMid(each.cell, context.pitch)}px`);
  }
  // The stage holds the grid AND anything dragged past it, or a step placed to
  // the right of every column would sit outside the scrollable area and be
  // unreachable by the pointer that put it there.
  const far = context.layout.far;
  context.box = {
    width: Math.max(context.layout.columns * (CELL.width + CELL.gapX),
                    far.x + CELL.width),
    height: Math.max(0, context.layout.rows * context.pitch - CELL.gapY,
                     far.y + context.pitch - CELL.gapY)};
  stage.style.width = `${context.box.width}px`;
  stage.style.height = `${context.box.height}px`;
  return true;
}

// -- focus, kept across an idempotent re-render ----------------------------
//
// Read before the pass, handed to the control's successor after it, the way
// `graph.js:127-150` does. Every focusable this module writes carries
// `data-focus`, so the successor is one query rather than a guess at a shape.

function focusKey(mount) {
  const active = document.activeElement;
  if (!active || !mount.contains(active)) return null;
  return active.getAttribute ? active.getAttribute("data-focus") : null;
}

function restoreFocus(mount, key) {
  if (!key) return;
  const successor = mount.querySelector(`[data-focus="${key}"]`);
  if (successor) successor.focus();
}

// -- the chrome: which document, which run, and every pointerless road ------

function banner(shown, state, runtime) {
  const workflows = isObject(state) && isObject(state.workflows)
    ? state.workflows : {};
  const strip = element("div", {className: "studio-canvas__banner",
    "data-document": shown.kind});
  strip.append(element("p", {className: "studio-canvas__document",
    text: documentSentence(shown, state)}));
  strip.append(element("p", {className: "mono studio-canvas__phase",
    text: localize(state, "workflow_detail.read_phase", {phase: readPhase(workflows.phase, state)})}));
  const problems = rows(workflows.diagnostics).length;
  if (shown.kind === "draft") {
    strip.append(element("p", {className: "studio-canvas__diagnostics",
      text: problems ? localize(state, problems === 1 ? "workflow_detail.publishing_one"
        : "workflow_detail.publishing_blocked", {count: String(problems)})
        : localize(state, "workflow_detail.publishing_ready")}));
  }
  if (runtime) strip.append(element("p", {className: "studio-canvas__runnote",
    text: localize(state, "workflow_detail.run_join_note", {run: String(runtime.runId)})}));
  return strip;
}

function documentSentence(shown, state) {
  if (shown.kind === "draft") {
    return localize(state, "workflow_detail.draft_sentence");
  }
  if (shown.kind === "published") {
    const named = shown.revision === null ? "" : ` ${shown.revision}`;
    return localize(state, "workflow_detail.revision_sentence", {revision: named});
  }
  return localize(state, "workflow_detail.no_workflow");
}

function paletteButton(kind, editable, handlers, selection, state) {
  const mark = KIND_MARKS[kind];
  const button = element("button", {
    className: `studio-palette__add studio-palette__add--${kind}`,
    "data-add-kind": kind, "data-focus": `add-${kind}`,
    disabled: editable ? null : "", type: "button",
    title: localize(state, "workflow_detail.add_after", {kind: localize(state, `workflow_detail.kind_${kind}`).toLowerCase()}),
  }, [element("span", {text: localize(state, "workflow_detail.add_kind", {glyph: mark.glyph, kind: localize(state, `workflow_detail.kind_${kind}`).toLowerCase()})})]);
  button.addEventListener("click", () => call(handlers, "onEdit", {
    type: "add", kind,
    afterId: selection.kind === "node" ? selection.id : null}));
  return button;
}

function palette(editable, handlers, selection, state) {
  const bar = element("div", {className: "studio-palette",
    role: "group", "aria-label": localize(state, "workflow_detail.add_step")});
  for (const kind of NODE_KINDS) {
    bar.append(paletteButton(kind, editable, handlers, selection, state));
  }
  bar.append(element("p", {className: "studio-palette__note", text: editable
    ? localize(state, "workflow_detail.new_step_note")
    : localize(state, "workflow_detail.published_note")}));
  return bar;
}

function viewButton(label, key, aria, action) {
  const button = element("button", {"aria-label": aria,
    className: "studio-view__button", "data-focus": `view-${key}`,
    "data-view": key, type: "button"}, [element("span", {text: label})]);
  button.addEventListener("click", action);
  return button;
}

function viewControls(view, handlers, state) {
  const bar = element("div", {className: "studio-view", role: "group",
    "aria-label": localize(state, "workflow_detail.pan_zoom")});
  const move = (dx, dy) => call(handlers, "onView", {
    pan: {x: view.x + dx, y: view.y + dy}, zoom: view.zoom});
  bar.append(
    viewButton("◀", "left", localize(state, "workflow_detail.pan_left"), () => move(PAN_STEP, 0)),
    viewButton("▶", "right", localize(state, "workflow_detail.pan_right"), () => move(-PAN_STEP, 0)),
    viewButton("▲", "up", localize(state, "workflow_detail.pan_up"), () => move(0, PAN_STEP)),
    viewButton("▼", "down", localize(state, "workflow_detail.pan_down"), () => move(0, -PAN_STEP)),
    viewButton("−", "out", localize(state, "workflow_detail.zoom_out"), () => call(handlers, "onView", {
      pan: {x: view.x, y: view.y},
      zoom: Math.max(ZOOM_MIN, view.zoom / ZOOM_STEP)})),
    viewButton("+", "in", localize(state, "workflow_detail.zoom_in"), () => call(handlers, "onView", {
      pan: {x: view.x, y: view.y},
      zoom: Math.min(ZOOM_MAX, view.zoom * ZOOM_STEP)})),
    viewButton(localize(state, "workflow_detail.reset_view"), "reset", localize(state, "workflow_detail.reset_pan_zoom"),
      () => call(handlers, "onView", {pan: {x: 0, y: 0}, zoom: 1})),
    element("p", {className: "mono studio-view__level",
      text: localize(state, "workflow_detail.view_reading", {zoom: String(Math.round(view.zoom * 100)), x: String(Math.round(view.x)), y: String(Math.round(view.y))})}));
  return bar;
}

//: Every pointer road on this canvas has a key beside it, written down where
//: the canvas is rather than in a document nobody opens.

// -- the drawn step --------------------------------------------------------

function markOf(node, state) {
  if (node.kind === "task" && node.capability === REVIEW_CAPABILITY) {
    return {...REVIEW_MARK, label: localize(state, "workflow_detail.kind_review")};
  }
  return KIND_MARKS[node.kind] ? {...KIND_MARKS[node.kind], label: localize(state, `workflow_detail.kind_${node.kind}`)}
    : {glyph: "?", label: localize(state, "workflow_detail.kind_unknown", {kind: String(node.kind)})};
}


function readPhase(value, state) {
  const word = typeof value === "string" ? value : "empty";
  return ["empty", "loading", "ready", "failed"].includes(word)
    ? localize(state, `workflow_detail.read_${word}`) : word;
}

function outcomeLabel(value, state) {
  const known = ["cancelled", "failed", "rejected", "succeeded", "unknown", "verification_failed"];
  return known.includes(value) ? localize(state, `scene.outcome_${value}`) : String(value);
}

function stageLabel(value, state) {
  return STAGE_NAMES.includes(value) ? localize(state, `workflow_detail.stage_${value}`) : String(value);
}

function runStrip(row, state) {
  const strip = element("span", {className: "studio-node__run"});
  strip.append(element("i", {className: "mono studio-node__runlabel", text: localize(state, "workflow_detail.run_label")}));
  strip.append(element("span", {className: "mono",
    text: NODE_PHASES.includes(row.phase) ? localize(state, `workflow_detail.phase_${row.phase}`)
      : localize(state, "workflow_detail.phase_unreadable")}));
  strip.append(element("span", {className: "mono", text: row.outcome === null
    || row.outcome === undefined ? localize(state, "workflow_detail.no_result") : outcomeLabel(row.outcome, state)}));
  if (typeof row.decision === "string") {
    strip.append(element("span", {className: "mono",
      text: localize(state, "workflow_detail.gate_reading", {decision: GATE_STATES.includes(row.decision)
        ? localize(state, `workflow_detail.decision_${row.decision}`)
        : localize(state, "workflow_detail.phase_unreadable")})}));
  }
  if (typeof row.pass === "number") {
    strip.append(element("span", {className: "mono", text: localize(state, "workflow_detail.pass_reading", {pass: String(row.pass), bound: row.bound_reached ? localize(state, "workflow_detail.bound_reached") : ""})}));
  }
  return strip;
}

function nodeLines(node, parents, state) {
  const mark = markOf(node, state);
  const lines = [
    element("span", {className: "studio-node__kind",
      text: `${mark.glyph} ${mark.label}`}),
    element("span", {className: "studio-node__title", text: String(node.title)}),
    element("span", {className: "mono studio-node__id", text: String(node.node_id)}),
    element("span", {className: "mono studio-node__role", text: node.role_id
      ? localize(state, "workflow_detail.role_reading", {role: String(node.role_id)}) : localize(state, "workflow_detail.no_role")}),
  ];
  if (node.stage) {
    lines.push(element("span", {className: "mono studio-node__stage",
      text: `${STAGE_NAMES.indexOf(node.stage) + 1}/5 · ${stageLabel(node.stage, state)}`}));
  }
  if (node.gate_id) {
    lines.push(element("span", {className: "mono studio-node__gate",
      text: localize(state, "workflow_detail.gate_id_reading", {id: String(node.gate_id)})}));
  }
  if (isObject(node.loop)) {
    lines.push(element("span", {className: "mono studio-node__loop",
      text: localize(state, "workflow_detail.loop_reading", {bound: String(node.loop.bound), step: String(node.loop.back_to)})}));
  }
  lines.push(element("span", {className: "mono studio-node__from",
    text: parents.length ? localize(state, "workflow_detail.after", {steps: parents.join(", ")}) : localize(state, "workflow_detail.start")}));
  return lines;
}

function nodeButton(node, context) {
  const pressed = context.selection.kind === "node"
    && context.selection.id === node.node_id;
  const button = element("button", {
    "aria-pressed": String(pressed),
    className: `studio-node studio-node--${node.kind}`,
    "data-focus": `node-${node.node_id}`, "data-node-id": node.node_id,
    type: "button",
  }, nodeLines(node, context.parents.get(node.node_id) || [], context.state));
  const row = context.runtime && context.runtime.byNode.get(node.node_id);
  if (row) button.append(runStrip(row, context.state));
  // The flag is CONSUMED, not only read: a keyboard Enter has no pointerdown
  // to reset it and would otherwise be swallowed by an older drag.
  button.addEventListener("click", () => {
    const dragged = context.gesture.moved;
    context.gesture.moved = false;
    if (dragged) return;
    call(context.handlers, "onSelect", {kind: "node", id: node.node_id});
  });
  bindNodeDrag(button, node, context);
  return button;
}

//: Dragging a step MOVES it: the document stores a position now, so where a
//: person puts a box is a fact this build keeps and reads back. It used to
//: change the step's ORDER instead, because a step had no coordinates and a
//: drag that moved only pixels would have been a control writing nothing --
//: the honest behaviour for a build that could not store the answer.
//:
//: Order is still a fact and still editable, in the inspector, where it is
//: named as what it is. The two stopped being the same gesture the moment
//: either could be expressed on its own.
function bindNodeDrag(button, node, context) {
  let origin = null;
  button.addEventListener("pointerdown", (event) => {
    if (!context.editable || event.button !== 0) return;
    origin = {x: event.clientX, y: event.clientY};
    context.gesture.moved = false;
    button.setPointerCapture(event.pointerId);
  });
  button.addEventListener("pointermove", (event) => {
    if (!origin) return;
    const dy = event.clientY - origin.y;
    const dx = event.clientX - origin.x;
    if (Math.abs(dx) + Math.abs(dy) > DRAG_SLOP) context.gesture.moved = true;
    // Both axes now: the x delta used to be measured and thrown away.
    if (context.gesture.moved) {
      button.style.transform = `translate(${dx}px, ${dy}px)`;
    }
  });
  button.addEventListener("pointerup", (event) => {
    if (!origin) return;
    const delta = {x: event.clientX - origin.x, y: event.clientY - origin.y};
    origin = null;
    button.style.transform = "";
    if (!context.gesture.moved) return;
    const cell = context.layout.cells[node.node_id];
    if (!cell) return;
    const at = droppedAt(cell, context.pitch, delta, context.view.zoom);
    call(context.handlers, "onEdit", {
      type: "move", nodeId: node.node_id, x: at.x, y: at.y});
  });
}

//: A real button beside the step, not nested inside it: the step stays a
//: `<button>` and both stay reachable by Tab. `restack` puts it on the step's
//: right edge through the two custom properties `.studio-port` reads.
function portButton(node, context) {
  const port = element("button", {
    "aria-label": localize(context.state, "workflow_detail.port_aria", {title: String(node.title)}),
    className: "studio-port", "data-focus": `port-${node.node_id}`,
    "data-port": node.node_id, disabled: context.editable ? null : "",
    type: "button"}, [element("span", {text: "→"})]);
  port.addEventListener("click", () => call(context.handlers, "onStatus",
    {key: "workflow_detail.port_help"}));
  bindConnectDrag(port, node, context);
  return port;
}

function bindConnectDrag(port, node, context) {
  let live = false;
  port.addEventListener("pointerdown", (event) => {
    if (!context.editable || event.button !== 0) return;
    live = true;
    port.setPointerCapture(event.pointerId);
  });
  port.addEventListener("pointerup", (event) => {
    if (!live) return;
    live = false;
    const under = document.elementFromPoint(event.clientX, event.clientY);
    const target = under && under.closest ? under.closest("[data-node-id]") : null;
    const to = target && target.getAttribute("data-node-id");
    if (!to || to === node.node_id) {
      call(context.handlers, "onStatus", {key: "workflow_detail.port_no_target"});
      return;
    }
    call(context.handlers, "onEdit", {
      type: "connect", fromId: node.node_id, toId: to});
  });
}

// -- the edge layer --------------------------------------------------------

function edgePath(cells, edge, back, pitch) {
  const from = cells[edge.from_node];
  const to = cells[edge.to_node];
  const x1 = cellX(from) + CELL.width;
  const y1 = cellMid(from, pitch);
  const x2 = cellX(to);
  const y2 = cellMid(to, pitch);
  const bend = Math.max(18, Math.abs(x2 - x1) / 2);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("class", back ? "studio-edge studio-edge--back" : "studio-edge");
  path.setAttribute("fill", "none");
  // The drawn line is inert; its wide twin below carries every interaction.
  path.setAttribute("pointer-events", "none");
  path.setAttribute("d", `M ${x1} ${y1} C ${x1 + bend} ${y1}, `
    + `${x2 - bend} ${y2}, ${x2} ${y2}`);
  return path;
}

//: A wide, unpainted twin of each edge: `pointer-events="stroke"` hit-tests
//: stroke geometry whether or not a stylesheet paints it, so an edge is
//: clickable at any zoom without this module writing one colour.
function edgeHit(cells, edge, context) {
  const id = edgeId(edge.from_node, edge.to_node);
  const selected = context.selection.kind === "edge" && context.selection.id === id;
  const hit = document.createElementNS(SVG_NS, "path");
  const path = edgePath(cells, edge, context.layout.back.has(id), context.pitch);
  hit.setAttribute("class", "studio-edge__hit");
  hit.setAttribute("d", path.getAttribute("d"));
  hit.setAttribute("fill", "none");
  hit.setAttribute("stroke-width", "16");
  hit.setAttribute("pointer-events", "stroke");
  hit.setAttribute("role", "button");
  hit.setAttribute("tabindex", "0");
  hit.setAttribute("aria-pressed", String(selected));
  hit.setAttribute("data-edge", id);
  hit.setAttribute("data-focus", `edge-${id}`);
  hit.setAttribute("aria-label", localize(context.state, "workflow_detail.edge_aria", {from: String(edge.from_node), to: String(edge.to_node), back: context.layout.back.has(id)
      ? localize(context.state, "workflow_detail.edge_back") : ""}));
  const select = () => call(context.handlers, "onSelect", {kind: "edge", id});
  hit.addEventListener("click", select);
  hit.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select();
    }
  });
  return [path, hit];
}

//: The one edge a `loop` node states rather than draws. `back_to` is not in
//: `edges` -- that list is a DAG -- so the return is its own dashed, labelled
//: line and can never be mistaken for a forward dependency.
function loopReturn(cells, node, pitch) {
  const from = cells[node.node_id];
  const to = cells[node.loop.back_to];
  if (!from || !to) return null;
  const path = document.createElementNS(SVG_NS, "path");
  const x1 = cellX(from) + CELL.width / 2;
  const y1 = cellY(from, pitch) + pitch - CELL.gapY;
  const x2 = cellX(to) + CELL.width / 2;
  const y2 = cellY(to, pitch) + pitch - CELL.gapY;
  const drop = pitch / 2;
  path.setAttribute("class", "studio-edge studio-edge--loop");
  path.setAttribute("fill", "none");
  path.setAttribute("data-loop-return", edgeId(node.node_id, node.loop.back_to));
  path.setAttribute("d", `M ${x1} ${y1} C ${x1} ${y1 + drop}, `
    + `${x2} ${y2 + drop}, ${x2} ${y2}`);
  return path;
}

function drawEdges(svg, nodes, edges, context) {
  const cells = context.layout.cells;
  svg.replaceChildren();
  if (!context.layout.columns) {
    for (const name of ["viewBox", "width", "height"]) svg.removeAttribute(name);
    return;
  }
  const {width, height} = context.box;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  for (const node of nodes) {
    if (isObject(node.loop) && cells[node.node_id]) {
      const path = loopReturn(cells, node, context.pitch);
      if (path) svg.append(path);
    }
  }
  for (const edge of edges) {
    if (cells[edge.from_node] && cells[edge.to_node]) {
      svg.append(...edgeHit(cells, edge, context));
    }
  }
}

// -- keyboard --------------------------------------------------------------

function neighbour(nodes, layout, from, key) {
  const here = layout.cells[from];
  if (!here) return null;
  const axis = key === "ArrowUp" || key === "ArrowDown" ? "row" : "column";
  const forward = key === "ArrowDown" || key === "ArrowRight";
  const same = axis === "row" ? "column" : "row";
  const candidates = nodes.filter((node) => {
    const cell = layout.cells[node.node_id];
    return cell && cell[same] === here[same]
      && (forward ? cell[axis] > here[axis] : cell[axis] < here[axis]);
  });
  if (!candidates.length) return null;
  candidates.sort((a, b) => layout.cells[a.node_id][axis]
    - layout.cells[b.node_id][axis]);
  return (forward ? candidates[0] : candidates[candidates.length - 1]).node_id;
}

function keyAdds(key) {
  return {t: "task", g: "gate", l: "loop"}[key] || null;
}

function panKey(key, view, handlers) {
  const move = {ArrowLeft: [PAN_STEP, 0], ArrowRight: [-PAN_STEP, 0],
    ArrowUp: [0, PAN_STEP], ArrowDown: [0, -PAN_STEP]}[key];
  if (!move) return false;
  call(handlers, "onView", {
    pan: {x: view.x + move[0], y: view.y + move[1]}, zoom: view.zoom});
  return true;
}

function zoomKey(key, view, handlers) {
  const factor = {"+": ZOOM_STEP, "=": ZOOM_STEP, "-": 1 / ZOOM_STEP}[key];
  if (factor) {
    call(handlers, "onView", {pan: {x: view.x, y: view.y},
      zoom: Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, view.zoom * factor))});
    return true;
  }
  if (key !== "0") return false;
  call(handlers, "onView", {pan: {x: 0, y: 0}, zoom: 1});
  return true;
}

function selectionKey(event, nodes, context) {
  const {selection, layout, handlers} = context;
  if (event.key === "Escape") {
    call(handlers, "onSelect", null);
    return true;
  }
  if (!event.key.startsWith("Arrow")) return false;
  if (selection.kind !== "node") {
    if (!nodes.length) return false;
    call(handlers, "onSelect", {kind: "node", id: nodes[0].node_id});
    return true;
  }
  const next = neighbour(nodes, layout, selection.id, event.key);
  if (next) call(handlers, "onSelect", {kind: "node", id: next});
  return Boolean(next);
}

function editKey(event, context) {
  const {selection, handlers, editable} = context;
  if (!editable) return false;
  const kind = keyAdds(event.key);
  if (kind) {
    call(handlers, "onEdit", {type: "add", kind,
      afterId: selection.kind === "node" ? selection.id : null});
    return true;
  }
  if (selection.kind === null) return false;
  if (event.key === "Delete" || event.key === "Backspace") {
    // The edit vocabulary names an end `fromId`/`toId`, as both inspector
    // callers do; `edgeEnds` answers in the document's own two words.
    const ends = edgeEnds(selection.id) || {};
    call(handlers, "onEdit", selection.kind === "node"
      ? {type: "delete-node", nodeId: selection.id}
      : {type: "delete-edge", fromId: ends.from, toId: ends.to});
    return true;
  }
  if (event.key === "d" && selection.kind === "node") {
    call(handlers, "onEdit", {type: "duplicate", nodeId: selection.id});
    return true;
  }
  // Alt and an arrow MOVE the selected step, on the same grid a drag snaps to
  // and on all four axes -- pointer parity, which is the point: every gesture
  // the canvas offers a pointer it offers a keyboard, or the canvas is a
  // pointer-only surface with a keyboard story told about it. Order is edited
  // in the inspector, by two buttons that say "Move earlier" and "Move later".
  const nudge = MOVE_NUDGE[event.key];
  if (event.altKey && selection.kind === "node" && nudge) {
    const cell = context.layout.cells[selection.id];
    if (cell) {
      call(handlers, "onEdit", {
        type: "move", nodeId: selection.id,
        x: cellX(cell) + nudge.x, y: cellY(cell, context.pitch) + nudge.y});
      return true;
    }
  }
  return false;
}

function bindKeys(stage, nodes, context) {
  stage.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey) return;
    const handled = event.shiftKey
      ? panKey(event.key, context.view, context.handlers)
      : editKey(event, context) || zoomKey(event.key, context.view, context.handlers)
        || selectionKey(event, nodes, context);
    if (handled) event.preventDefault();
  });
}

//: Dragging the background pans, captured on the stage so no listener
//: outlives the gesture. "Background" is said as what it is NOT: the edge
//: layer fills the drawing, so testing for the stage element itself would make
//: the pan unreachable everywhere the SVG lies -- which is everywhere.
const HELD = "[data-node-id],[data-port],[data-edge]";

function bindPan(stage, view, handlers) {
  let origin = null;
  stage.addEventListener("pointerdown", (event) => {
    const on = event.target;
    if (event.button !== 0 || (on.closest && on.closest(HELD))) return;
    origin = {x: event.clientX, y: event.clientY, panX: view.x, panY: view.y};
    stage.setPointerCapture(event.pointerId);
  });
  stage.addEventListener("pointermove", (event) => {
    if (!origin) return;
    call(handlers, "onView", {zoom: view.zoom, pan: {
      x: origin.panX + (event.clientX - origin.x),
      y: origin.panY + (event.clientY - origin.y)}});
  });
  stage.addEventListener("pointerup", () => { origin = null; });
}

// -- the mount -------------------------------------------------------------

function emptyNote(shown, state) {
  return element("p", {className: "studio-canvas__empty", text: shown.kind === "none"
    ? localize(state, "workflow_detail.empty_canvas")
    : localize(state, "workflow_detail.empty_steps")});
}

/**
 * Draw one workflow document, and every road for editing it.
 *
 * @param {Element} mount the node layer (`#workflowNodes`)
 * @param {Element} svg the edge layer (`#workflowEdges`)
 * @param {object} state the reducer's frozen value
 * @param {object} handlers `onSelect`, `onView`, `onEdit`, `onStatus`
 */
export function mountCanvas(mount, svg, state, handlers) {
  const key = focusKey(mount);
  const shown = canvasDocument(state);
  const view = canvasView(state);
  const nodes = rows(shown.document && shown.document.nodes).filter(
    (node) => isObject(node) && typeof node.node_id === "string");
  const edges = rows(shown.document && shown.document.edges).filter(
    (edge) => isObject(edge) && typeof edge.from_node === "string"
      && typeof edge.to_node === "string");
  const layout = canvasLayout(nodes, edges);
  const runtime = runtimeIndex(state);
  const parents = new Map(nodes.map((node) => [node.node_id, edges.filter(
    (edge) => edge.to_node === node.node_id).map((edge) => edge.from_node)]));
  const context = {
    editable: shown.kind === "draft", gesture: {moved: false}, handlers,
    index: new Map(nodes.map((node, at) => [node.node_id, at])), pitch: 0,
    layout, parents, runtime, selection: selectionOf(state), view, state,
  };
  // The stage is focusable: it is where the keyboard road starts, so it
  // carries a focus key like every other control.
  const stage = element("div", {className: "studio-canvas__stage",
    "data-editable": String(context.editable), "data-focus": "canvas-stage",
    tabindex: "0"});
  const drawn = nodes.map((node) => ({cell: layout.cells[node.node_id],
    node: nodeButton(node, context), port: portButton(node, context)}));
  restack(stage, drawn, context);
  // ONE transformed layer, and the edge layer rides inside it: `studio.css`
  // leaves `#workflowEdges` in normal flow, so an edge layer left where the
  // markup puts it draws a band ABOVE the steps rather than behind them. The
  // browser hit-tests a transformed subtree in its transformed position, so no
  // coordinate is converted by hand at any zoom.
  stage.style.transform =
    `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`;
  if (svg) {
    svg.style.position = "absolute";
    svg.style.left = "0";
    svg.style.top = "0";
    drawEdges(svg, nodes, edges, context);
    stage.append(svg);
  }
  for (const each of drawn) stage.append(each.node, each.port);
  bindKeys(stage, nodes, context);
  bindPan(stage, view, handlers);
  const help = element("details", {className: "studio-canvas__help"}, [
    element("summary", {"data-focus": "canvas-help",
      text: localize(state, "workflow_detail.canvas_help")}),
    element("p", {className: "mono studio-canvas__keys", text: localize(state, "workflow_detail.canvas_keys")}),
    element("p", {className: "studio-canvas__positions", text:
      localize(state, "workflow_detail.canvas_positions")}),
  ]);
  help.open = mount.querySelector(".studio-canvas__help")?.open === true;
  const tools = element("div", {className: "studio-canvas__tools"}, [
    palette(context.editable, handlers, context.selection, state), viewControls(view, handlers, state), help]);
  const reflow = () => { if (restack(stage, drawn, context) && svg) drawEdges(svg, nodes, edges, context); };
  const scope = JSON.stringify([state.workflows?.selectedId, shown.kind, shown.revision]);
  const orbit = workflowOrbit(mount, scope, nodes, context.selection, handlers, stage, tools, reflow, context.state);
  const chrome = element("div", {className: "studio-canvas__chrome"}, [
    element("div", {className: "studio-canvas__heading"}, [banner(shown, state, runtime), orbit.switches]), tools]);
  // Chrome first, drawing after, both in normal flow: the well scrolls one
  // column and no control is stacked over a step.
  mount.replaceChildren(chrome, orbit.panel, stage);
  orbit.refresh();
  if (restack(stage, drawn, context) && svg) drawEdges(svg, nodes, edges, context);
  if (!nodes.length) chrome.append(emptyNote(shown, state));
  restoreFocus(mount, key);
}
