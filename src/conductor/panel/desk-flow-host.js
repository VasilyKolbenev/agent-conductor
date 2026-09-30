"use strict";
// The desk's host for «Схема»: the existing model decides which read or write is due, the
// existing renderer draws it, and the desk's transport is its only route to the server.
// `desk.js` owns the project claim and seals its transport when onForeign is called.
import {path} from "./desk-transport.js";
import {initialFlow, stepFlow} from "./desk-flow-model.js";
import {mountFlow} from "./desk-flow.js";
import {focusTarget, restoreFocus} from "./studio-focus.js";

const MISMATCH = "project_mismatch";
const LOST_READ = Object.freeze(["read_late", "store_error"]);

function readPath(ask) {
  if (ask.target === "workflows") return path.workflows();
  if (ask.target === "flowRead") return path.flowRead(ask.subject);
  return null;
}

/** Connect one flow panel to the desk's existing, project-bound transport. */
export function createFlowHost({mount, door, locale, nonce, onForeign, onState = () => {}}) {
  let schema = initialFlow({nonce}), epoch = 0, live = true, opened = false;
  const stops = new Set();

  function invalidate() {
    if (!live) return false;
    live = false;
    epoch += 1;
    for (const stop of stops) stop.abort();
    stops.clear();
    return true;
  }

  function foreign() {
    if (invalidate()) onForeign();
  }

  function render() {
    const focused = focusTarget();
    mountFlow(mount, {schema, locale: locale()}, {onFlow: dispatch});
    restoreFocus(mount, focused);
  }

  async function perform(ask) {
    if (!live) return;
    const pending = epoch;
    let result;
    if (ask.door === "read") {
      const target = readPath(ask), stop = new AbortController();
      if (target === null) result = {status: "refused", code: "route_not_found"};
      else {
        stops.add(stop);
        try {
          result = {status: "accepted", payload: await door.readJson(target, stop)};
        } catch (error) {
          const code = error instanceof Error ? error.message : "store_error";
          result = {status: LOST_READ.includes(code) ? "unknown" : "refused", code};
        } finally {
          stops.delete(stop);
        }
      }
    } else if (ask.door === "write" && ask.target === "flow") {
      try {
        result = await door.submit("flow", ask.subject, ask.body);
      } catch (error) {
        result = {status: "unknown", code: error instanceof Error ? error.message : "store_error"};
      }
    } else result = {status: "refused", code: "route_not_found"};
    if (pending !== epoch || !live) return;
    if (result.code === MISMATCH) { foreign(); return; }
    dispatch({type: "answered", ask, result});
  }

  function dispatch(event) {
    if (!live || !opened) return;
    const pending = epoch;
    const step = stepFlow(schema, event);
    schema = step.state;
    onState(schema);
    if (!live || pending !== epoch) return;
    render();
    for (const ask of step.asks) void perform(ask);
  }

  function open() {
    if (!live || opened) return;
    opened = true;
    dispatch({type: "cycles"});
  }

  function dispose() {
    invalidate();
    mount.replaceChildren();
  }

  return Object.freeze({open, dispatch, dispose, state: () => schema});
}
