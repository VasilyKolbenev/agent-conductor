"use strict";
// The canvas's edge layer: the SVG line each connection is drawn with, the wide
// unpainted twin that carries its interaction, and the dashed return a loop
// step states. It left `studio-canvas.js` when that file neared the line cap,
// and it took the drawing and nothing else: the layout cells, the measured row
// pitch, the stage box and the selection all arrive in `context`, so this module
// measures nothing, keeps no gesture state and reaches no network and no clock.
//
// It may not import the canvas that draws it (that would close a ring), which is
// why the two three-line helpers below are copies of the canvas's own.
import {localize} from "./studio-i18n.js";
import {CELL, cellMid, cellX, cellY, edgeId} from "./studio-layout.js";

const SVG_NS = "http://www.w3.org/2000/svg";

function call(handlers, name, value) {
  const handler = handlers && handlers[name];
  if (typeof handler === "function") handler(value);
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
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
  return [path, hit, ...flowMarks(cells, edge, id, context, path, hit)];
}

//: What only a flow's road carries (a Studio document never has these keys): the word it is
//: drawn with and the mark a diagnostic row left at it. The word is text the caller already said in
//: the reader's language, set in the middle of the road; the mark is an attribute and, on the road's
//: label, a word, so no colour alone says a road is at fault.
function flowMarks(cells, edge, id, context, path, hit) {
  const severity = isObject(edge.mark) ? String(edge.mark.severity) : null;
  if (severity !== null) {
    path.setAttribute("data-diag", severity);
    hit.setAttribute("data-diag", severity);
  }
  if (typeof edge.label !== "string" && severity === null) return [];
  const from = cells[edge.from_node], to = cells[edge.to_node];
  const x = (cellX(from) + CELL.width + cellX(to)) / 2;
  const y = (cellMid(from, context.pitch) + cellMid(to, context.pitch)) / 2 - 4;
  const said = [edge.label, isObject(edge.mark) ? edge.mark.text : null]
    .filter((part) => typeof part === "string" && part !== "");
  const label = document.createElementNS(SVG_NS, "text");
  label.setAttribute("class", "studio-edge__label");
  label.setAttribute("data-edge-label", id);
  label.setAttribute("x", String(x));
  label.setAttribute("y", String(y));
  label.setAttribute("text-anchor", "middle");
  label.setAttribute("pointer-events", "none");
  label.textContent = said.join(" · ");
  return said.length === 0 ? [] : [label];
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

export function drawEdges(svg, nodes, edges, context) {
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
