//: The canvas's LAYOUT: where a step sits, and which connection joins which.
//:
//: Pure arithmetic over a node list and an edge list. It was parked in
//: `studio-model.js` when `studio-canvas.js` reached the project's line cap,
//: and it never belonged there: that module is the PAYLOAD BOUNDARY -- it
//: decides what this window will accept off the wire -- and layout decides
//: nothing about trust. Keeping the two together meant every edit to either
//: was an edit to a file at its cap.
//:
//: It imports nothing, for the boundary's own reason: a computation that could
//: reach a neighbour could answer from something other than the two lists it
//: was handed.

//
// `studio-canvas.js` crossed the line cap and this is the half of it that
// computes rather than draws. It is placement arithmetic over a document,
// with no DOM, no clock and no network -- this module's own character --
// and the canvas re-exports both names so nothing downstream had to move.

export function edgeId(from, to) { return `${from} ${to}`; }
export function edgeEnds(id) {
  const parts = String(id).split(" ");
  return parts.length === 2 ? {from: parts[0], to: parts[1]} : null;
}

// -- layout ----------------------------------------------------------------

//: What a step's document says about where it sits, or null for "you decide".
//:
//: The two axes are read separately and both must be whole numbers, because a
//: half-placed step -- an x with no y -- would be drawn at a coordinate this
//: window invented, and a person would have no way to tell that from one they
//: chose. `graph_template.NodePosition` refuses the same shape one layer down;
//: this is that rule at the reading end, where a document that never passed
//: through the contract still arrives.
export function placement(node) {
  const at = node && node.position;
  if (!at || typeof at !== "object" || Array.isArray(at)) return null;
  if (!Number.isInteger(at.x) || !Number.isInteger(at.y)) return null;
  return {x: at.x, y: at.y};
}

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
  let far = {x: 0, y: 0};
  for (const node of nodes) {
    const placed = placement(node);
    if (placed !== null) {
      // A step somebody PUT somewhere sits there and takes no row from the
      // grid: consuming one would leave a hole in the column it was dragged
      // out of, and the steps below it would slide up when it moved.
      cells[node.node_id] = {column: null, row: null, x: placed.x, y: placed.y};
      far = {x: Math.max(far.x, placed.x), y: Math.max(far.y, placed.y)};
      continue;
    }
    const column = depth.get(node.node_id) - floor;
    const row = used.get(column) || 0;
    used.set(column, row + 1);
    cells[node.node_id] = {column, row, x: null, y: null};
  }
  return {
    cells,
    far,
    columns: nodes.length ? Math.max(...depth.values()) - floor + 1 : 0,
    rows: used.size ? Math.max(...used.values()) : 0,
    // Depth is computed for EVERY step, placed or not, so a back edge is still
    // a back edge after somebody drags its ends around. Where a box sits and
    // what the plan does are two questions, and this answers the second.
    back: new Set(live.filter((edge) => depth.get(edge.to_node)
      <= depth.get(edge.from_node)).map((edge) => edgeId(edge.from_node, edge.to_node))),
  };
}


// -- pixels ----------------------------------------------------------------
//
// A cell is a place in the grid; these turn one into the pixels a step, its
// port and an edge end are drawn at. They came here from `studio-canvas.js`
// when that module reached the line cap, and this is where they belonged: the
// module docstring above already says this file is placement arithmetic, and
// nothing here draws.

export const CELL = Object.freeze({width: 210, height: 112, gapX: 46, gapY: 36});
//: The grid a move snaps to, pointer and keyboard alike. Small enough that a
//: person places a step where they meant to, coarse enough that two steps
//: nudged to the same place really do line up.
export const MOVE_STEP = 8;
//: One keyboard nudge per arrow, four ways. A grid step rather than a pixel:
//: a person nudging a step should see it move, and pressing an arrow forty
//: times to cross a gap is a control nobody uses twice.
export const MOVE_NUDGE = Object.freeze({
  ArrowUp: {x: 0, y: -MOVE_STEP * 4}, ArrowDown: {x: 0, y: MOVE_STEP * 4},
  ArrowLeft: {x: -MOVE_STEP * 4, y: 0}, ArrowRight: {x: MOVE_STEP * 4, y: 0},
});
//: Where one step is DRAWN. A step somebody placed answers with the pixels it
//: was placed at; a step nobody has touched answers from the grid, exactly as
//: every step did before positions existed. The two live in one pair of
//: functions rather than in every caller, so ports, edge paths, the stage box
//: and the drag all follow a placement without knowing there is such a thing.
export function cellX(cell) {
  return cell.x === null ? cell.column * (CELL.width + CELL.gapX) : cell.x;
}
export function cellY(cell, pitch) {
  return cell.y === null ? cell.row * pitch : cell.y;
}
export function cellMid(cell, pitch) {
  return cellY(cell, pitch) + (pitch - CELL.gapY) / 2;
}

//: Where a step would land if the pointer let go here: its drawn position plus
//: the gesture, with the view's zoom divided out, snapped to the grid a
//: keyboard move uses so a dragged step and a nudged one can line up. Whole
//: pixels, because that is what the document stores.
export function droppedAt(cell, pitch, delta, zoom) {
  const scale = zoom > 0 ? zoom : 1;
  const x = cellX(cell) + delta.x / scale;
  const y = cellY(cell, pitch) + delta.y / scale;
  return {x: Math.round(x / MOVE_STEP) * MOVE_STEP,
          y: Math.round(y / MOVE_STEP) * MOVE_STEP};
}
