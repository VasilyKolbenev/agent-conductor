"use strict";
// The wire doors of the Studio and, after it, the desk: the one read door, the
// one mutation door and the one stream door, moved out of the boot module so a
// second window can be built on them without a second copy.
//
// This is the ONLY module of the Studio and the desk that touches the network.
// `graph.js` and the classic `command.js` keep doors of their own, each under
// its own source gate; here the gates pin two `fetch(` -- one read, one write --
// and one `new EventSource(`.
// What a caller does with an answer, and which screen it lands on, stays with
// the caller: this module opens the doors and knows nothing else.
//
// The statements were moved out of `studio.js`, and the text is not identical: a
// name that lived in the boot module's closure had to cross the seam. What
// differs from the Studio's text is exactly this. The reader's language is a
// `locale` accessor handed to `createTransport`, where the boot module read its
// own preferences. The session drop that `submit` and the dropped-stream handler
// each did inline is `dropSession`, handed out. The payload judgment that
// `loadSession` made inline is `foreignSession`. The stream is opened by
// `openStream`, the wire step of a write is `postJson`, and both of those and
// `readJson` are module-level functions that take what they use, because the
// doors that keep nothing between calls have no need of the closure:
// `sessionDoors` holds only what a window remembers, its token and its session
// epoch, so no function here runs past fifty lines. The request each door makes
// -- its address, headers and body, its deadline, the way a refusal is
// translated -- is the request the boot module made, with one header added to it.
//
// That header is the project claim of spec 4.5.1. The window hands `createTransport` a
// `claimed` accessor, and each of the two doors that touch the wire puts what it answers in
// `X-Conduct-Project` through `claimHeader`, at the moment of the request: nothing is sent
// while the window is bound to no project, and the Studio, which binds to none, sends nothing.
// `seal` is the terminal call of a desk that turned out to be open for another project: the
// token is forgotten, the stream is closed, and every read and write that follows is refused
// with the code project_mismatch, without a request; `sealable` adds it around `sessionDoors`.
import {refusalCode} from "./command-projection.js";

//: A GET is aborted at READ_DEADLINE, its body included -- wide, as a healthy
//: read can queue behind a write. LATE is this window's word for it.
const READ_DEADLINE = 20000;
export const LATE = "read_late";

export const path = Object.freeze({
  tasks: () => "/command/tasks",
  project: () => "/command/project",
  workflows: () => "/command/workflows",
  workflow: (id) => `/command/workflows/${encodeURIComponent(id)}`,
  revision: (id, n) => `/command/workflows/${encodeURIComponent(id)}`
    + `/revisions/${encodeURIComponent(String(n))}`,
  draft: (id) => `/command/workflows/${encodeURIComponent(id)}/draft`,
  revisions: (id) => `/command/workflows/${encodeURIComponent(id)}/revisions`,
  runs: () => "/command/runs",
  run: (id) => `/command/runs/${encodeURIComponent(id)}`,
  controls: (id) => `/command/runs/${encodeURIComponent(id)}/controls`,
  decisions: (id) => `/command/runs/${encodeURIComponent(id)}/decisions`,
  proposals: (id) => `/command/runs/${encodeURIComponent(id)}/proposals`,
  actions: (id) => `/command/runs/${encodeURIComponent(id)}/actions`,
  artifacts: (id) => `/command/runs/${encodeURIComponent(id)}/artifacts`,
  automation: (id) => `/command/runs/${encodeURIComponent(id)}/automation`,
  automationPreview: (id) => `/command/runs/${encodeURIComponent(id)}/automation/preview`,
  automationAuthorize: (id) => `/command/runs/${encodeURIComponent(id)}/automation/authorize`,
  automationControl: (id) => `/command/runs/${encodeURIComponent(id)}/automation/control`,
  // Lane L's route-canon 3 (spec 6.2.3, 9.1.6): the run's materials document, written once
  // a run exists, and the documents of the project's HEAD -- the list, and one by its id.
  materials: (id) => `/command/runs/${encodeURIComponent(id)}/materials`,
  projectDocuments: () => "/command/project/documents",
  projectDocument: (id) => `/command/project/documents/${encodeURIComponent(id)}`,
  // The continue-after flag (spec 4.3.4): one path, read with a GET and written with a POST.
  autoContinue: () => "/command/project/auto-continue",
});
// Closed mutation targets share the same CSRF and refusal door.
const WRITE_TARGETS = Object.freeze(["draft", "revisions", "runs",
  "decisions", "proposals", "actions", "artifacts", "tasks",
  "automationPreview", "automationAuthorize", "automationControl", "materials",
  "autoContinue"]);

// -- the doors that hold no state ----------------------------------------------
//
// These touch the wire and remember nothing between calls, so they live at
// module level: the state a window keeps (its token and its session epoch) is in
// `sessionDoors`, and everything that needs none of it is here.

//: The claim of spec 4.5.1: the project this window is bound to, as the one header both
//: doors add to the headers they already build. Nothing while the window is bound to none.
function claimHeader(claimed) {
  const id = claimed();
  return typeof id === "string" ? {"X-Conduct-Project": id} : {};
}

//: The one read door. Every GET on this surface goes through it, so a refusal
//: is translated in one place and no caller invents a second vocabulary for
//: what went wrong -- and every GET is bounded in one place, body and all.
//: `locale` answers the reader's language at the moment of the request.
async function readJson(locale, claimed, target, stop = new AbortController()) {
  const timer = setTimeout(() => stop.abort(LATE), READ_DEADLINE);
  let response, payload;
  try {
    response = await fetch(target, {cache: "no-store", signal: stop.signal,
      headers: {"Accept-Language": locale(), ...claimHeader(claimed)}});
    payload = await response.json();
  } catch (_error) {
    throw new Error(stop.signal.aborted ? LATE : "store_error");
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) throw new Error(refusalCode(payload));
  return payload;
}

//: The wire step of the one mutation door. Its target comes from the closed
//: list and its body from the caller; the token is read off the session it is
//: handed and goes into a request header and nowhere else. The answer is what
//: the wire said and nothing more: `unknown` when the request could not be
//: made or answered at all (what landed is then not known), `refused` with the
//: code the refusal vocabulary gives the body, or `accepted` with the body.
async function postJson(locale, claimed, session, target, subject, body) {
  let response;
  try {
    response = await fetch(path[target](subject), {
      body: JSON.stringify(body),
      headers: {"Content-Type": "application/json", "Accept-Language": locale(),
        ...claimHeader(claimed), "X-Conduct-CSRF": session.token},
      method: "POST",
    });
  } catch (_error) {
    return {status: "unknown"};
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok) return {code: refusalCode(payload), payload, status: "refused"};
  return {payload, status: "accepted"};
}

//: The two refusals that say the session itself is not this window's, so the
//: token that carried the write is gone and the next write mints another.
const SESSION_REFUSALS = Object.freeze(["csrf_denied", "same_origin_denied"]);

//: `graph.js:209-226`, in shape and in order. The exact key set is checked
//: rather than the two keys read, and the origin is compared to this window's
//: own: an answer that is not exactly this window's session is not a token.
function foreignSession(payload) {
  return !payload || Object.keys(payload).sort().join(",") !== "csrf_token,origin"
    || typeof payload.csrf_token !== "string" || !payload.csrf_token
    || payload.origin !== location.origin;
}

//: The one stream door. The caller owns what each frame means.
function openStream() {
  return new EventSource("/events");
}

//: The doors of one window. `locale` is a function that answers the reader's
//: language at the moment of each request, so a change of language reaches the
//: next read and the next write without this module holding a copy of it; `claimed`
//: answers the project the window is bound to in the same way.
//:
//: The token this window's session minted is held in ONE variable here. It goes
//: into a request header and nowhere else: never a URL, never a DOM node, never
//: storage. A generation travels with it so an answer authorized by a session
//: that has since rotated cannot land.
function sessionDoors(locale, claimed) {
  let csrfToken = "", sessionEpoch = 0;
  const read = (target, stop) => readJson(locale, claimed, target, stop);

  // A session that rotated under the request makes its answer unusable: a
  // token that arrived for a generation nobody is waiting for is not this
  // window's token.
  async function loadSession() {
    if (csrfToken) return {generation: sessionEpoch, token: csrfToken};
    const generation = ++sessionEpoch;
    const payload = await read("/command/session");
    if (generation !== sessionEpoch || foreignSession(payload)) {
      throw new Error("same_origin_denied");
    }
    csrfToken = payload.csrf_token;
    return {generation, token: csrfToken};
  }

  // The one mutation door. Nothing else in this file reaches the wire with a
  // method, and a Human's click is the only thing that reaches this.
  async function submit(target, subject, body) {
    if (!WRITE_TARGETS.includes(target)) return {status: "refused",
      code: "route_not_found"};
    let session;
    try {
      session = await loadSession();
    } catch (error) {
      return {code: error instanceof Error ? error.message : "store_error",
        status: "refused"};
    }
    const answer = await postJson(locale, claimed, session, target, subject, body);
    if (SESSION_REFUSALS.includes(answer.code)) dropSession();
    // A session rotated under an in-flight write makes its answer unusable:
    // this window cannot say what landed, and saying nothing landed would be a
    // claim about a durable record it did not observe.
    return answer.status === "accepted" && session.generation !== sessionEpoch
      ? {status: "unknown"} : answer;
  }

  //: A dropped stream rotates the session: the token that authorized a write
  //: issued before the drop is gone, and its answer can no longer be counted.
  function dropSession() {
    sessionEpoch += 1;
    csrfToken = "";
  }

  return Object.freeze({readJson: read, submit, dropSession, openStream});
}

//: The terminal state of a desk open for another project (spec 4.5.1), added around the
//: doors of one window. `seal` forgets the token, closes the stream the window opened and
//: ends every door: a read is refused by throwing project_mismatch, a write answers it as
//: refused, and a stream is not opened -- none of them reaches the wire, and not even a
//: session is asked for. A refused read is a rejected promise, never a throw that would
//: slip past a caller's `.catch`.
function sealable(door) {
  let sealed = false, stream = null;
  async function guardedRead(target, stop) {
    if (sealed) throw new Error("project_mismatch");
    return door.readJson(target, stop);
  }
  async function guardedWrite(target, subject, body) {
    if (sealed) return {status: "refused", code: "project_mismatch"};
    return door.submit(target, subject, body);
  }
  function guardedStream() {
    if (sealed) throw new Error("project_mismatch");
    stream = door.openStream();
    return stream;
  }
  function seal() {
    sealed = true;
    door.dropSession();
    if (stream !== null) stream.close();
    stream = null;
  }
  return Object.freeze({readJson: guardedRead, submit: guardedWrite,
    openStream: guardedStream, dropSession: door.dropSession, seal});
}

export function createTransport(locale, claimed = () => null) {
  return sealable(sessionDoors(locale, claimed));
}
