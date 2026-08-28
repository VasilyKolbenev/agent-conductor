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
import {element} from "./command-view.js";

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
  "add", "connect", "delete-edge", "delete-node", "duplicate", "reorder",
  "set-field",
]);

//: Cell geometry, in the units the browser suite measures. Same model as
//: `graph-view.CELL`. The width is `studio.css`'s own `.studio-node` width so
//: a step fills its slot and its port sits on its edge; the row pitch is
//: generous because that rule declares a MIN height and a step grows.
export const CELL = Object.freeze({width: 210, height: 112, gapX: 46, gapY: 36});
const ZOOM_MIN = 0.4;
const ZOOM_MAX = 2;
const ZOOM_STEP = 1.25;
const PAN_STEP = 64;
//: How far a pointer must travel before a press becomes a drag rather than a
//: click. Below it the gesture selects, which is what a shaky hand meant.
const DRAG_SLOP = 4;
const SVG_NS = "http://www.w3.org/2000/svg";

export function edgeId(from, to) { return `${from} ${to}`; }
export function edgeEnds(id) {
  const parts = String(id).split(" ");
  return parts.length === 2 ? {from: parts[0], to: parts[1]} : null;
}

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

// -- layout ----------------------------------------------------------------

//: Columns from the longest path, rows from declaration order -- the model
//: `graph-payload.computeLayout` uses, with the one difference that matters
//: here: a DRAFT may hold a cycle, so this never refuses. An edge that still
//: does not move the plan forward after relaxation is reported as `back` and
//: is drawn dashed and labelled rather than silently straightened.
export function canvasLayout(nodes, edges) {
  const order = new Map(nodes.map((node, index) => [node.node_id, index]));
  const depth = new Map(nodes.map((node) => [node.node_id, 0]));
  const live = edges.filter(
    (edge) => order.has(edge.from_node) && order.has(edge.to_node));
  // Clamped as well as bounded. Without the ceiling a cycle keeps pushing its
  // own members one column further apart every round, so two steps pointing at
  // each other drew across five columns of empty grid; no plan is ever deeper
  // than it has steps.
  const deepest = Math.max(0, nodes.length - 1);
  for (let round = 0; round < nodes.length; round += 1) {
    let moved = false;
    for (const edge of live) {
      const next = Math.min(deepest, depth.get(edge.from_node) + 1);
      if (next > depth.get(edge.to_node)) {
        depth.set(edge.to_node, next);
        moved = true;
      }
    }
    if (!moved) break;
  }
  const floor = nodes.length ? Math.min(...depth.values()) : 0;
  const used = new Map();
  const cells = {};
  for (const node of nodes) {
    const column = depth.get(node.node_id) - floor;
    const row = used.get(column) || 0;
    used.set(column, row + 1);
    cells[node.node_id] = {column, row};
  }
  return {
    cells,
    columns: nodes.length ? Math.max(...depth.values()) - floor + 1 : 0,
    rows: nodes.length ? Math.max(...used.values()) : 0,
    back: new Set(live.filter((edge) => depth.get(edge.to_node)
      <= depth.get(edge.from_node)).map((edge) => edgeId(edge.from_node, edge.to_node))),
  };
}

function cellX(cell) { return cell.column * (CELL.width + CELL.gapX); }
function cellY(cell) { return cell.row * (CELL.height + CELL.gapY); }

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
    text: documentSentence(shown)}));
  strip.append(element("p", {className: "mono studio-canvas__phase",
    text: `read: ${typeof workflows.phase === "string" ? workflows.phase : "empty"}`}));
  const problems = rows(workflows.diagnostics).length;
  if (shown.kind === "draft") {
    strip.append(element("p", {className: "studio-canvas__diagnostics",
      text: problems
        ? `${problems} problem${problems === 1 ? "" : "s"} block publishing this draft.`
        : "Nothing blocks publishing this draft."}));
  }
  if (runtime) strip.append(element("p", {className: "studio-canvas__runnote",
    text: `Run ${runtime.runId} is a DIFFERENT document. This build cannot `
      + "prove it followed this workflow revision — a materialized plan "
      + "records no workflow identity — so a step id is the only join, and "
      + "run words appear only inside the boxes marked run."}));
  return strip;
}

function documentSentence(shown) {
  if (shown.kind === "draft") {
    return "Editing the DRAFT — an unpublished workflow document. "
      + "Nothing here has run.";
  }
  if (shown.kind === "published") {
    const named = shown.revision === null ? "" : ` ${shown.revision}`;
    return `Showing published revision${named} — immutable and read-only. `
      + "Save a draft to change this workflow.";
  }
  return "No workflow document is open. Choose a workflow, or start one from "
    + "a bundled starter.";
}

function paletteButton(kind, editable, handlers, selection) {
  const mark = KIND_MARKS[kind];
  const button = element("button", {
    className: `studio-palette__add studio-palette__add--${kind}`,
    "data-add-kind": kind, "data-focus": `add-${kind}`,
    disabled: editable ? null : "", type: "button",
    title: `Add a ${mark.label.toLowerCase()} after the selected step`,
  }, [element("span", {text: `${mark.glyph} Add ${mark.label.toLowerCase()}`})]);
  button.addEventListener("click", () => call(handlers, "onEdit", {
    type: "add", kind,
    afterId: selection.kind === "node" ? selection.id : null}));
  return button;
}

function palette(editable, handlers, selection) {
  const bar = element("div", {className: "studio-palette",
    role: "group", "aria-label": "Add a step"});
  for (const kind of NODE_KINDS) {
    bar.append(paletteButton(kind, editable, handlers, selection));
  }
  bar.append(element("p", {className: "studio-palette__note", text: editable
    ? "A new step is added after the selected one, unbound and unconnected "
      + "until you give it a role in the inspector."
    : "A published revision is immutable, so no step can be added to it."}));
  return bar;
}

function viewButton(label, key, aria, action) {
  const button = element("button", {"aria-label": aria,
    className: "studio-view__button", "data-focus": `view-${key}`,
    "data-view": key, type: "button"}, [element("span", {text: label})]);
  button.addEventListener("click", action);
  return button;
}

function viewControls(view, handlers) {
  const bar = element("div", {className: "studio-view", role: "group",
    "aria-label": "Pan and zoom"});
  const move = (dx, dy) => call(handlers, "onView", {
    pan: {x: view.x + dx, y: view.y + dy}, zoom: view.zoom});
  bar.append(
    viewButton("◀", "left", "Pan left", () => move(PAN_STEP, 0)),
    viewButton("▶", "right", "Pan right", () => move(-PAN_STEP, 0)),
    viewButton("▲", "up", "Pan up", () => move(0, PAN_STEP)),
    viewButton("▼", "down", "Pan down", () => move(0, -PAN_STEP)),
    viewButton("−", "out", "Zoom out", () => call(handlers, "onView", {
      pan: {x: view.x, y: view.y},
      zoom: Math.max(ZOOM_MIN, view.zoom / ZOOM_STEP)})),
    viewButton("+", "in", "Zoom in", () => call(handlers, "onView", {
      pan: {x: view.x, y: view.y},
      zoom: Math.min(ZOOM_MAX, view.zoom * ZOOM_STEP)})),
    viewButton("Reset view", "reset", "Reset pan and zoom",
      () => call(handlers, "onView", {pan: {x: 0, y: 0}, zoom: 1})),
    element("p", {className: "mono studio-view__level",
      text: `zoom ${Math.round(view.zoom * 100)}% · pan `
        + `${Math.round(view.x)},${Math.round(view.y)}`}));
  return bar;
}

//: Every pointer road on this canvas has a key beside it, written down where
//: the canvas is rather than in a document nobody opens.
const KEY_LEGEND = "Keyboard: arrows move the selection · Alt+Up/Down "
  + "moves the selected step earlier or later · Shift+arrows pan · "
  + "+ and − zoom, 0 resets · t, g, l add a task, a human gate or a "
  + "loop after the selection · d duplicates · Delete removes · "
  + "Esc clears. Connecting two steps is a drag from a step's port, or the "
  + "Transitions section of the inspector.";

// -- the drawn step --------------------------------------------------------

function markOf(node) {
  if (node.kind === "task" && node.capability === REVIEW_CAPABILITY) {
    return REVIEW_MARK;
  }
  return KIND_MARKS[node.kind] || {glyph: "?", label: `unknown: ${node.kind}`};
}

function runStrip(row) {
  const strip = element("span", {className: "studio-node__run"});
  strip.append(element("i", {className: "mono studio-node__runlabel", text: "run"}));
  strip.append(element("span", {className: "mono",
    text: NODE_PHASES.includes(row.phase) ? row.phase : "unreadable phase"}));
  strip.append(element("span", {className: "mono", text: row.outcome === null
    || row.outcome === undefined ? "no result recorded" : String(row.outcome)}));
  if (typeof row.decision === "string") {
    strip.append(element("span", {className: "mono",
      text: `gate: ${GATE_STATES.includes(row.decision) ? row.decision : "unreadable"}`}));
  }
  if (typeof row.pass === "number") {
    strip.append(element("span", {className: "mono", text: `pass ${row.pass}`
      + (row.bound_reached ? " · bound reached" : "")}));
  }
  return strip;
}

function nodeLines(node, parents) {
  const mark = markOf(node);
  const lines = [
    element("span", {className: "studio-node__kind",
      text: `${mark.glyph} ${mark.label}`}),
    element("span", {className: "studio-node__title", text: String(node.title)}),
    element("span", {className: "mono studio-node__id", text: String(node.node_id)}),
    element("span", {className: "mono studio-node__role", text: node.role_id
      ? `role: ${node.role_id}` : "no role — nothing will run this step"}),
  ];
  if (node.stage) {
    lines.push(element("span", {className: "mono studio-node__stage",
      text: `${STAGE_NAMES.indexOf(node.stage) + 1}/5 · ${node.stage}`}));
  }
  if (node.gate_id) {
    lines.push(element("span", {className: "mono studio-node__gate",
      text: `gate id: ${node.gate_id}`}));
  }
  if (isObject(node.loop)) {
    lines.push(element("span", {className: "mono studio-node__loop",
      text: `↻ at most ×${node.loop.bound} · reopens `
        + `${node.loop.back_to}`}));
  }
  lines.push(element("span", {className: "mono studio-node__from",
    text: parents.length ? `after ${parents.join(", ")}` : "start"}));
  return lines;
}

function nodeButton(node, cell, context) {
  const pressed = context.selection.kind === "node"
    && context.selection.id === node.node_id;
  const button = element("button", {
    "aria-pressed": String(pressed),
    className: `studio-node studio-node--${node.kind}`,
    "data-focus": `node-${node.node_id}`, "data-node-id": node.node_id,
    type: "button",
  }, nodeLines(node, context.parents.get(node.node_id) || []));
  button.style.setProperty("--x", `${cellX(cell)}px`);
  button.style.setProperty("--y", `${cellY(cell)}px`);
  const row = context.runtime && context.runtime.byNode.get(node.node_id);
  if (row) button.append(runStrip(row));
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

//: Dragging a step changes its ORDER in the document, which is the fact the
//: layout reads -- a workflow step has no coordinates and this build stores
//: none, so a drag that moved only pixels would be a control writing inert
//: data. The row a step is dropped on is the index it takes.
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
    if (context.gesture.moved) button.style.transform = `translate(0px, ${dy}px)`;
  });
  button.addEventListener("pointerup", (event) => {
    if (!origin) return;
    const dy = event.clientY - origin.y;
    origin = null;
    button.style.transform = "";
    if (!context.gesture.moved) return;
    const step = Math.round(dy / (context.view.zoom * (CELL.height + CELL.gapY)));
    if (step !== 0) {
      call(context.handlers, "onEdit", {
        type: "reorder", nodeId: node.node_id,
        index: context.index.get(node.node_id) + step});
    }
  });
}

//: A real button beside the step, not nested inside it: the step stays a
//: `<button>` and both remain reachable by Tab.
function portButton(node, cell, context) {
  const port = element("button", {
    "aria-label": `Connect from ${node.title}. Drag to another step, or use `
      + "the Transitions section of the inspector.",
    className: "studio-port", "data-focus": `port-${node.node_id}`,
    "data-port": node.node_id, disabled: context.editable ? null : "",
    type: "button"}, [element("span", {text: "→"})]);
  port.style.setProperty("--x", `${cellX(cell) + CELL.width}px`);
  port.style.setProperty("--y", `${cellY(cell) + CELL.height / 2}px`);
  port.addEventListener("click", () => call(context.handlers, "onStatus",
    "Drag from this port onto another step to connect them, or use the "
    + "Transitions section of the inspector."));
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
      call(context.handlers, "onStatus",
        "A connection needs a different step under the pointer when you let go.");
      return;
    }
    call(context.handlers, "onEdit", {
      type: "connect", fromId: node.node_id, toId: to});
  });
}

// -- the edge layer --------------------------------------------------------

function edgePath(cells, edge, back) {
  const from = cells[edge.from_node];
  const to = cells[edge.to_node];
  const x1 = cellX(from) + CELL.width;
  const y1 = cellY(from) + CELL.height / 2;
  const x2 = cellX(to);
  const y2 = cellY(to) + CELL.height / 2;
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
  const path = edgePath(cells, edge, context.layout.back.has(id));
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
  hit.setAttribute("aria-label", `Connection from ${edge.from_node} to `
    + `${edge.to_node}${context.layout.back.has(id) ? ", a step backwards" : ""}`);
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
function loopReturn(cells, node) {
  const from = cells[node.node_id];
  const to = cells[node.loop.back_to];
  if (!from || !to) return null;
  const path = document.createElementNS(SVG_NS, "path");
  const x1 = cellX(from) + CELL.width / 2;
  const y1 = cellY(from) + CELL.height;
  const x2 = cellX(to) + CELL.width / 2;
  const y2 = cellY(to) + CELL.height;
  const drop = CELL.gapY + CELL.height / 2;
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
  const width = context.layout.columns * (CELL.width + CELL.gapX) - CELL.gapX;
  const height = context.layout.rows * (CELL.height + CELL.gapY) - CELL.gapY;
  svg.setAttribute("viewBox", `0 0 ${Math.max(1, width)} ${Math.max(1, height)}`);
  svg.setAttribute("width", String(Math.max(1, width)));
  svg.setAttribute("height", String(Math.max(1, height)));
  for (const node of nodes) {
    if (isObject(node.loop) && cells[node.node_id]) {
      const path = loopReturn(cells, node);
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
  const {selection, handlers, editable, index} = context;
  if (!editable) return false;
  const kind = keyAdds(event.key);
  if (kind) {
    call(handlers, "onEdit", {type: "add", kind,
      afterId: selection.kind === "node" ? selection.id : null});
    return true;
  }
  if (selection.kind === null) return false;
  if (event.key === "Delete" || event.key === "Backspace") {
    call(handlers, "onEdit", selection.kind === "node"
      ? {type: "delete-node", nodeId: selection.id}
      : {type: "delete-edge", ...edgeEnds(selection.id)});
    return true;
  }
  if (event.key === "d" && selection.kind === "node") {
    call(handlers, "onEdit", {type: "duplicate", nodeId: selection.id});
    return true;
  }
  const at = index.get(selection.id);
  if (event.altKey && selection.kind === "node" && at !== undefined
      && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
    call(handlers, "onEdit", {type: "reorder", nodeId: selection.id,
      index: at + (event.key === "ArrowDown" ? 1 : -1)});
    return true;
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

function emptyNote(shown) {
  return element("p", {className: "studio-canvas__empty", text: shown.kind === "none"
    ? "Nothing is drawn because no workflow document is open."
    : "This workflow document has no steps yet. Add one from the palette, or "
      + "press t, g or l."});
}

//: ONE transformed layer, and the edge layer rides inside it. `studio.css`
//: leaves `#workflowEdges` in normal flow, so an edge layer left where the
//: markup puts it draws a band ABOVE the steps instead of behind them -- and
//: two independently transformed siblings would have to be kept in step by
//: hand, a drift a pointer finds before a reader does. So the provided SVG is
//: appended INTO the stage: it keeps its id, its class and its place under
//: `#workflowCanvas`, and inherits the one transform instead of copying it.
//: The browser hit-tests a transformed subtree in its transformed position, so
//: no coordinate is converted by hand at any zoom. The stage's box is sized to
//: the drawing; the SVG's viewBox stays the content box `drawEdges` set.
function applyView(stage, layout, view) {
  const width = layout.columns
    ? layout.columns * (CELL.width + CELL.gapX) - CELL.gapX : 0;
  const height = layout.rows
    ? layout.rows * (CELL.height + CELL.gapY) - CELL.gapY : 0;
  stage.style.position = "relative";
  stage.style.transformOrigin = "0 0";
  stage.style.transform =
    `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`;
  stage.style.width = `${Math.max(0, width)}px`;
  stage.style.height = `${Math.max(0, height)}px`;
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
    index: new Map(nodes.map((node, at) => [node.node_id, at])),
    layout, parents, runtime, selection: selectionOf(state), view,
  };
  // The stage is focusable, so it carries a focus key like every other
  // control: it is where the keyboard road starts.
  const stage = element("div", {className: "studio-canvas__stage",
    "data-editable": String(context.editable), "data-focus": "canvas-stage",
    tabindex: "0"});
  // Layout this module owns, because it owns the two-layer geometry. Every
  // colour on both layers is `studio.css`'s; nothing here paints.
  applyView(stage, layout, view);
  if (svg) {
    svg.style.position = "absolute";
    svg.style.left = "0";
    svg.style.top = "0";
    drawEdges(svg, nodes, edges, context);
    stage.append(svg);
  }
  for (const node of nodes) {
    const cell = layout.cells[node.node_id];
    stage.append(nodeButton(node, cell, context), portButton(node, cell, context));
  }
  bindKeys(stage, nodes, context);
  bindPan(stage, view, handlers);
  const chrome = element("div", {className: "studio-canvas__chrome"}, [
    banner(shown, state, runtime), palette(context.editable, handlers,
      context.selection), viewControls(view, handlers),
    element("p", {className: "mono studio-canvas__keys", text: KEY_LEGEND}),
    element("p", {className: "studio-canvas__positions", text:
      "Free positions are not stored by this build — a workflow step has "
      + "no coordinates. Dragging a step changes its ORDER in the document, "
      + "which is what the layout reads; columns come from the connections."}),
  ]);
  // Chrome first, drawing after, both in normal flow: the well scrolls one
  // column and no control is stacked over a step.
  mount.replaceChildren(chrome, stage);
  if (!nodes.length) chrome.append(emptyNote(shown));
  restoreFocus(mount, key);
}
