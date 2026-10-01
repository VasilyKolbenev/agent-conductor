"use strict";
// The folder form is only a view. hub.js owns the session, wire and polling.
import {codeWords, hubText} from "./hub-copy.js";
import {node} from "./hub-rail.js";

const button = (key, text, action, disabled = false) => {
  const made = node("button", {type: "button", "data-focus": key, text,
    ...(disabled ? {disabled: ""} : {})});
  made.addEventListener("click", action);
  return made;
};

export function folderForm(locale, add, actions) {
  const say = (key) => hubText(locale, `hub.add.${key}`);
  const title = node("h2", {text: say("heading")});
  const close = button("folder-close", say("close"), actions.close);
  const children = [title, close, node("p", {text: say("intro")}),
    button("folder-choose", say("choose"), actions.choose,
      add.mode === "picking" || add.mode === "running")];
  if (add.mode === "picking") {
    children.push(node("p", {text: say("window")}),
      button("folder-cancel", say("cancel"), actions.cancel));
  }
  if (add.folder) children.push(node("p", {text: `${say("folder")}: ${add.folder}`}));
  if (add.mode === "picked") {
    const name = node("input", {type: "text", value: add.name, maxlength: "64",
      "aria-label": say("name"), "data-focus": "folder-name"});
    name.addEventListener("input", () => actions.name(name.value));
    children.push(node("label", {text: say("name")}, [name]));
    if (add.project === "legacy") {
      const check = node("input", {type: "checkbox", "data-focus": "folder-writers"});
      check.checked = add.consent;
      check.addEventListener("change", () => actions.consent(check.checked));
      children.push(node("label", {text: say("writers")}, [check]));
    }
    children.push(node("p", {text: say("ownership")}),
      button("folder-submit", say("submit"), actions.submit,
        !add.name.trim() || (add.project === "legacy" && !add.consent)));
  }
  if (add.mode === "running" || add.mode === "done" || add.mode === "failed") {
    children.push(node("p", {text: `${say("progress")}: ${say(`step.${add.step || "admit"}`)}`}));
  }
  if (add.result) {
    children.push(node("p", {text: `${say("result")}: ${add.result.folder} · ${add.result.git} · ${add.result.providers} · ${add.result.exclude}`}));
  }
  if (add.mode === "done") children.push(node("p", {text: say("serving")}));
  if (add.error) children.push(node("p", {role: "alert",
    text: `${say("error")}: ${codeWords(locale, add.error)}`}));
  return node("section", {className: "hub-banner hub-add", "data-banner": "folder-add"}, children);
}
