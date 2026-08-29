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
