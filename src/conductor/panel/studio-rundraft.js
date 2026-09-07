"use strict";
// The document a person is composing on the Runs screen: which reference it
// answers, what kind of text it is, its bytes -- and the run it is for.
//
// Split out of `studio-store.js` at the line cap, along the seam the step
// draft already draws: what a person has typed against ONE run, kept across
// every read of that run, and cleared when another run is chosen or when the
// write that spends it is accepted. It touches no DOM and holds no rule about
// what may be published: the boundary (`api_contracts.parse_artifact`) judges
// the body, and the form beside it says why a press is shut.
//
// `generation` is not typed by anybody and moves on every clearing and on
// every typed word, for the reason the step draft carries one: a write minted
// from an earlier draft must be able to tell that the words on screen are no
// longer the ones it spent, so a document published while a person is already
// composing the next one does not empty the editor under their hands.

//: A draft addressed to no run. `mediaType` starts on the kind every shipped
//: document is; the other two are the person's.
export const NO_DOCUMENT = Object.freeze({
  runId: null, artifactRef: "", mediaType: "text/markdown", content: "",
  generation: 0,
});
//: The three keys a person may move, and the whole of what they may move.
const TYPED = Object.freeze(["artifactRef", "mediaType", "content"]);

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

//: The draft cleared, one generation on.
export function documentCleared(document) {
  return Object.freeze({...NO_DOCUMENT, generation: document.generation + 1});
}

//: One typed field of the draft, addressed to the run on screen. A draft
//: standing for another run is not edited but REPLACED: what was typed against
//: one run is not a document for another. A patch naming any key but the three
//: moves nothing, which keeps the id and the run out of a control's reach; a
//: word that did move takes the generation with it.
export function documentEdited(state, patch) {
  const runId = state.runs.selectedId;
  if (typeof runId !== "string" || !isObject(patch)) return state;
  const held = state.runs.document;
  const next = {...(held.runId === runId ? held : {...NO_DOCUMENT,
    generation: held.generation}), runId};
  let moved = false;
  for (const key of TYPED) {
    if (Object.hasOwn(patch, key) && typeof patch[key] === "string") {
      next[key] = patch[key];
      moved = true;
    }
  }
  if (!moved) return state;
  next.generation = held.generation + 1;
  return Object.freeze({...state, runs: Object.freeze({...state.runs,
    document: Object.freeze(next)})});
}

//: The accepted road spends the draft -- only the draft it was minted from:
//: this run, this generation. Anything else is somebody's unsent words.
export function documentSpent(state, event) {
  const held = state.runs.document;
  if (held.runId !== event.runId || held.generation !== event.generation) {
    return state;
  }
  return Object.freeze({...state, runs: Object.freeze({...state.runs,
    document: documentCleared(held)})});
}
