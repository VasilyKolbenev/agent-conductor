"use strict";
// The desk uses its existing transport's single SSE connection. Frames only ask for
// reads; they never supply facts for the page. refresh({runId, current}) must test
// current() before applying each answer. A null runId asks for a full refresh.
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function connectDeskStream({door, refresh, onConnection, onForeign}) {
  let source = null, disposed = false, connected = false, generation = 0;
  let busy = false, pending = undefined;

  function connection(value) {
    if (!disposed) onConnection(value);
  }

  function foreign() {
    dispose();
    onForeign();
  }

  // Coalesce while a read is out. Different runs, or a state frame, require a
  // complete read. A reconnect cannot make a pre-disconnect answer current.
  function request(runId) {
    if (disposed || !connected) return;
    pending = pending === undefined || pending === runId ? runId : null;
    void drain();
  }

  async function drain() {
    if (busy || disposed || !connected || pending === undefined) return;
    const runId = pending, asked = generation;
    const current = () => !disposed && connected && generation === asked;
    pending = undefined;
    busy = true;
    try {
      const settled = await refresh({runId, current});
      if (current()) connection(settled === true ? "open" : "closed");
    } catch (error) {
      if (!disposed && error instanceof Error && error.message === "project_mismatch") foreign();
      else if (current()) connection("closed");
    } finally {
      busy = false;
      if (!disposed && connected && pending !== undefined) void drain();
    }
  }

  function message(event) {
    if (disposed || !connected) return;
    let frame;
    try { frame = JSON.parse(event.data); } catch (_error) { return; }
    if (frame === null || typeof frame !== "object" || Array.isArray(frame)) return;
    if (frame.kind === "state") request(null);
    else if (frame.kind === "run" && typeof frame.run_id === "string"
        && ID.test(frame.run_id)) request(frame.run_id);
  }

  function opened() {
    if (disposed) return;
    generation += 1;
    connected = true;
    connection("connecting");
    request(null);
  }

  function dropped() {
    if (disposed) return;
    generation += 1;
    connected = false;
    pending = undefined;
    door.dropSession();
    connection("closed");
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    generation += 1;
    connected = false;
    pending = undefined;
    if (source !== null) {
      source.removeEventListener("message", message);
      source.removeEventListener("open", opened);
      source.removeEventListener("error", dropped);
      source.close();
    }
  }

  connection("connecting");
  try {
    source = door.openStream();
    source.addEventListener("message", message);
    source.addEventListener("open", opened);
    source.addEventListener("error", dropped);
  } catch (error) {
    if (error instanceof Error && error.message === "project_mismatch") foreign();
    else dropped();
  }
  return Object.freeze({dispose});
}
