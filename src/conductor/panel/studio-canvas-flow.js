"use strict";
// What only a flow draws on the canvas (spec 5.6.3, 7.4, 7.7), kept out of `studio-canvas.js`
// so that file keeps its headroom under the line cap.
//
// The canvas draws steps and roads and keeps drawing what it is given; the «Схема» hands it a flow's
// projection (`desk-flow-graph.js`). These are the hooks that projection uses, and every one is
// inert without its key, so a Studio document, which never carries them, is drawn as it was:
// a step's branch number, the note of a branch that waits its turn and the words of the mark a
// diagnostic row left (text the caller already said in the reader's language, so no colour alone
// tells that a step is at fault); the palette the caller chose in place of the three kinds; and the
// say-so that the banner, which speaks of a `GraphTemplate` draft, is not wanted.
//
// It builds elements through the view's helper and reaches no network and no clock.
import {element} from "./command-view.js";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/** The lines a flow's step adds to its button: branch number, waiting note, mark words. */
export function flowLines(node) {
  const lines = [];
  if (typeof node.badge === "string") {
    lines.push(element("span", {className: "mono studio-node__branch", text: node.badge}));
  }
  if (typeof node.note === "string" && node.note !== "") {
    lines.push(element("span", {className: "studio-node__waits", text: node.note}));
  }
  if (isObject(node.mark)) {
    lines.push(element("span", {className: "mono studio-node__diag", text: String(node.mark.text)}));
  }
  return lines;
}

/** The attributes a flow's step adds to its button; a step with neither adds none. */
export function flowAttributes(node) {
  return {"data-branch": typeof node.badge === "string" ? node.badge : null,
    "data-diag": isObject(node.mark) ? String(node.mark.severity) : null};
}

/** The palette rows the caller chose (`state.canvas.palette`), or null for the three kinds. */
export function customPalette(state) {
  const rows = isObject(state) && isObject(state.canvas) ? state.canvas.palette : null;
  return Array.isArray(rows) && rows.length > 0 ? rows.filter(isObject) : null;
}

/** One button of that palette: its edit goes out with the selected step as `afterId`. */
export function customButton(entry, editable, handlers, selection) {
  const button = element("button", {
    className: "studio-palette__add", "data-add-kind": entry.key,
    "data-focus": `add-${entry.key}`, disabled: editable ? null : "", type: "button",
    title: entry.title}, [element("span", {text: entry.text})]);
  button.addEventListener("click", () => {
    if (handlers && typeof handlers.onEdit === "function") {
      handlers.onEdit({...entry.edit, afterId: selection.kind === "node" ? selection.id : null});
    }
  });
  return button;
}

/** Whether the caller asks for no banner (`state.canvas.banner === false`). */
export function quietBanner(state) {
  return isObject(state) && isObject(state.canvas) && state.canvas.banner === false;
}
