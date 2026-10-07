"use strict";
// The folder form is only a view. hub.js owns the session, wire and polling.
import {codeWords, hubText} from "./hub-copy.js";
import {node} from "./hub-rail.js";
import {githubFields} from "./hub-github.js";

const button = (key, text, action, disabled = false) => {
  const made = node("button", {type: "button", "data-focus": key, text,
    ...(disabled ? {disabled: ""} : {})});
  made.addEventListener("click", action);
  return made;
};

function fields(locale, add, actions) {
  const say = (key) => hubText(locale, `hub.add.${key}`);
  const children = [];
  let folder = null;
  if (add.source !== "folder") {
    folder = node("input", {type: "text", value: add.folder, maxlength: "40",
      "aria-label": say("folder"), "data-focus": "scratch-folder"});
    children.push(node("label", {text: say("folder")}, [folder]));
  }
  const name = node("input", {type: "text", value: add.name, maxlength: "64",
    "aria-label": say("name"), "data-focus": "folder-name"});
  children.push(node("label", {text: say("name")}, [name]));
  if (add.project === "legacy") {
    const check = node("input", {type: "checkbox", "data-focus": "folder-writers"});
    check.checked = add.consent;
    check.addEventListener("change", () => actions.consent(check.checked));
    children.push(node("label", {text: say("writers")}, [check]));
  }
  const blocked = () => !name.value.trim() || (folder !== null && !folder.value)
    || (add.project === "legacy" && !add.consent)
    || (add.source === "github" && (!/^[A-Za-z0-9][A-Za-z0-9-]{0,38}\/[A-Za-z0-9._-]{1,100}$/.test(add.repo)
      || add.github?.state !== "ok"));
  const submit = button("folder-submit", say("submit"), actions.submit, blocked());
  folder?.addEventListener("input", () => {
    actions.folder(folder.value);
    submit.disabled = blocked();
  });
  name.addEventListener("input", () => {
    actions.name(name.value);
    submit.disabled = blocked();
  });
  return [node("div", {className: "hub-add__fields"}, children),
    node("p", {text: say("ownership")}), submit];
}

function outcome(locale, add) {
  const say = (key) => hubText(locale, `hub.add.${key}`), children = [];
  if (["running", "done", "failed"].includes(add.mode)) children.push(node("p", {
    text: `${say("progress")}: ${say(`step.${add.step || "admit"}`)}`}));
  if (add.result && add.mode === "done") children.push(node("p", {
    text: `${say("result")}: ${add.result.folder} · ${add.result.git} · ${add.result.providers} · ${add.result.exclude}`}));
  if (add.mode === "done") children.push(node("p", {text: say("serving")}));
  if (add.mode === "cancelled") children.push(node("p", {text: say("cancelled")}));
  if (add.mode === "failed" && add.result?.cloned) children.push(node("p", {
    text: hubText(locale, "hub.add.cloned_not_added", {folder: add.result.folder})}));
  if (add.error) children.push(node("p", {role: "alert",
    text: `${say("error")}: ${codeWords(locale, add.error)}`}));
  return children;
}

export function folderForm(locale, add, actions) {
  const say = (key) => hubText(locale, `hub.add.${key}`);
  const title = node("h2", {text: say("heading")});
  const close = button("folder-close", say("close"), actions.close);
  const children = [node("div", {className: "hub-add__header"}, [title, close]),
    node("div", {className: "hub-add__sources"}, [
    button("source-folder", say("source_folder"), () => actions.source("folder"), add.mode === "running"),
    button("source-scratch", say("source_scratch"), () => actions.source("scratch"), add.mode === "running"),
    button("source-github", say("source_github"), () => actions.source("github"), add.mode === "running")]),
    node("p", {text: say(add.source === "folder" ? "intro"
      : add.source === "github" ? "github_intro" : "scratch_intro")})];
  if (add.source === "folder") children.push(
    button("folder-choose", say("choose"), actions.choose,
      add.mode === "picking" || add.mode === "running"));
  else children.push(node("p", {text: `${say("home")}: ${add.home}`}),
    button("projects-home", say("change_home"), actions.home,
      add.mode === "picking" || add.mode === "running" || add.github?.state === "loading"));
  if (add.mode === "picking") {
    children.push(node("p", {text: say("window")}),
      button("folder-cancel", say("cancel"), actions.cancel));
  }
  if (add.folder) children.push(node("p", {text: `${say("folder")}: ${add.folder}`}));
  if (add.source === "github" && add.mode === "picked") children.push(...githubFields(locale, add, actions));
  if (add.mode === "picked") children.push(...fields(locale, add, actions));
  children.push(...outcome(locale, add));
  if (add.source === "github" && add.mode === "running" && add.step === "clone") {
    children.push(button("clone-cancel", say("github_cancel"), actions.cancelClone, add.cancelling));
  }
  return node("section", {className: "hub-banner hub-add", "data-banner": "folder-add"}, children);
}
