"use strict";
// The wire doors of the Studio and, after it, the desk: the one read door, the
// one mutation door and the one stream door, moved out of the boot module so a
// second window can be built on them without a second copy.
//
// This is the ONLY module of the panel that touches the network. `graph.js`
// holds the same position in its own window and the source gates pin both the
// same way: two `fetch(` -- one read, one write -- and one `new EventSource(`.
// What a caller does with an answer, and which screen it lands on, stays with
// the caller: this module opens the doors and knows nothing else.
//
// Nothing here has been changed in the move. The one addition is the seam the
// move needed: the reader's language and the session drop were names in the boot
// module's closure, and they are a `locale` accessor handed in and a
// `dropSession` handed out.
import {refusalCode} from "./command-projection.js";

//: A GET is aborted at READ_DEADLINE, its body included -- wide, as a healthy
//: read can queue behind a write. LATE is this window's word for it.
const READ_DEADLINE = 20000;
export const LATE = "read_late";

export const path = Object.freeze({
  tasks: () => "/command/tasks",
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
});
// Closed mutation targets share the same CSRF and refusal door.
const WRITE_TARGETS = Object.freeze(["draft", "revisions", "runs",
  "decisions", "proposals", "actions", "artifacts", "tasks",
  "automationPreview", "automationAuthorize", "automationControl"]);

//: The doors of one window. `locale` is a function that answers the reader's
//: language at the moment of each request, so a change of language reaches the
//: next read and the next write without this module holding a copy of it.
export function createTransport(locale) {
  // The token this process minted, held in ONE module-local variable. It goes
  // into a request header and nowhere else: never a URL, never a DOM node,
  // never storage. A generation travels with it so an answer authorized by a
  // session that has since rotated cannot land.
  let csrfToken = "", sessionEpoch = 0;

  // -- reads ---------------------------------------------------------------
  //
  // The one read door. Every GET on this surface goes through it, so a refusal
  // is translated in one place and no caller invents a second vocabulary for
  // what went wrong -- and every GET is bounded in one place, body and all.
  async function readJson(target, stop = new AbortController()) {
    const timer = setTimeout(() => stop.abort(LATE), READ_DEADLINE);
    let response, payload;
    try {
      response = await fetch(target, {cache: "no-store", signal: stop.signal,
        headers: {"Accept-Language": locale()}});
      payload = await response.json();
    } catch (_error) {
      throw new Error(stop.signal.aborted ? LATE : "store_error");
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) throw new Error(refusalCode(payload));
    return payload;
  }

  //: `graph.js:209-226`, in shape and in order. The exact key set is checked
  //: rather than the two keys read, the origin is compared to this window's
  //: own, and a session that rotated under the request makes its answer
  //: unusable -- a token that arrived for a generation nobody is waiting for
  //: is not this window's token.
  async function loadSession() {
    if (csrfToken) return {generation: sessionEpoch, token: csrfToken};
    const generation = ++sessionEpoch;
    const payload = await readJson("/command/session");
    if (generation !== sessionEpoch
        || !payload || Object.keys(payload).sort().join(",") !== "csrf_token,origin"
        || typeof payload.csrf_token !== "string" || !payload.csrf_token
        || payload.origin !== location.origin) throw new Error("same_origin_denied");
    csrfToken = payload.csrf_token;
    return {generation, token: csrfToken};
  }

  // -- the one mutation door -----------------------------------------------
  //
  // Its target comes from a closed list and its body from the caller. Nothing
  // else in this file reaches the wire with a method, and a Human's click is
  // the only thing that reaches this.
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
    let response;
    try {
      response = await fetch(path[target](subject), {
        body: JSON.stringify(body),
        headers: {"Content-Type": "application/json", "Accept-Language": locale(),
          "X-Conduct-CSRF": session.token},
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
    if (!response.ok) {
      const code = refusalCode(payload);
      if (["csrf_denied", "same_origin_denied"].includes(code)) {
        sessionEpoch += 1;
        csrfToken = "";
      }
      return {code, payload, status: "refused"};
    }
    // A session rotated under an in-flight write makes its answer unusable:
    // this window cannot say what landed, and saying nothing landed would be a
    // claim about a durable record it did not observe.
    return session.generation !== sessionEpoch
      ? {status: "unknown"} : {payload, status: "accepted"};
  }

  //: A dropped stream rotates the session: the token that authorized a write
  //: issued before the drop is gone, and its answer can no longer be counted.
  function dropSession() {
    sessionEpoch += 1;
    csrfToken = "";
  }

  //: The one stream door. The caller owns what each frame means.
  function openStream() {
    return new EventSource("/events");
  }

  return Object.freeze({readJson, submit, dropSession, openStream});
}
