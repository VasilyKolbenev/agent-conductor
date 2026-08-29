//: What publishing a drawing WOULD change about the revision now standing.
//:
//: Its own module because it is neither of the two things around it. The
//: reducer next door answers "what does this event do to what is on screen";
//: `studio-runread.js` answers "what does one run read say". This answers a
//: third question -- "what would this write change" -- over two documents the
//: workflow read already carries, and it is the only thing between a person
//: and a durable, immutable revision they did not mean to create.
//:
//: It is computed when a read lands rather than when the panel renders, so the
//: review a person confirms is the review that was on their screen when they
//: read it. A summary recomputed at paint time could describe a document that
//: arrived after they decided.

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

//: What publishing this drawing would change about the standing revision.
//:
//: Structural and not textual: a person confirming a write needs to know which
//: steps appear, disappear and differ, and a line-by-line diff of canonical
//: JSON answers a question nobody asked. Node identity is `node_id`, which is
//: the one field a step keeps across an edit; a step whose id changed reads as
//: one removed and one added, which is what it durably is.
//:
//: Answers null when there is nothing to compare -- no drawing, or nothing
//: published yet -- and the screen says which of those it is rather than
//: showing an empty summary that looks like "no changes".
export function changeSummary(published, draft) {
  if (!isObject(draft)) return null;
  // A FIRST revision has nothing to compare against, and "nothing to compare"
  // is not the same as "nothing to review". What it creates is the whole
  // document, so every step and every connection is an addition -- which is a
  // readable summary rather than an apology for the absence of one.
  if (!isObject(published)) {
    return Object.freeze({
      first: true,
      title: Object.freeze({from: null, to: draft.title}),
      added: Object.freeze(rows(draft.nodes).filter(isObject)
        .map((node) => node.node_id)),
      removed: Object.freeze([]),
      changed: Object.freeze([]),
      edgesAdded: Object.freeze(rows(draft.edges).filter(isObject)
        .map((edge) => `${edge.from_node}->${edge.to_node}`)),
      edgesRemoved: Object.freeze([]),
    });
  }
  const before = new Map(rows(published.nodes).filter(isObject)
    .map((node) => [node.node_id, node]));
  const after = new Map(rows(draft.nodes).filter(isObject)
    .map((node) => [node.node_id, node]));
  const changed = [];
  for (const [id, node] of after) {
    if (!before.has(id)) continue;
    if (JSON.stringify(before.get(id)) !== JSON.stringify(node)) changed.push(id);
  }
  const edgeKey = (edge) => `${edge.from_node}->${edge.to_node}`;
  const beforeEdges = new Set(rows(published.edges).filter(isObject).map(edgeKey));
  const afterEdges = new Set(rows(draft.edges).filter(isObject).map(edgeKey));
  return Object.freeze({
    first: false,
    title: published.title === draft.title ? null
      : Object.freeze({from: published.title, to: draft.title}),
    added: Object.freeze([...after.keys()].filter((id) => !before.has(id))),
    removed: Object.freeze([...before.keys()].filter((id) => !after.has(id))),
    changed: Object.freeze(changed),
    edgesAdded: Object.freeze([...afterEdges].filter((k) => !beforeEdges.has(k))),
    edgesRemoved: Object.freeze([...beforeEdges].filter((k) => !afterEdges.has(k))),
  });
}
