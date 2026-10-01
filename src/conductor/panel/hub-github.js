"use strict";
// GitHub choices are text only; callbacks use the hub's existing door.
import {hubText, codeWords} from "./hub-copy.js";
import {node} from "./hub-rail.js";

function control(key, text, action, disabled = false) {
  const made = node("button", {type: "button", text, "data-focus": key,
    ...(disabled ? {disabled: ""} : {})});
  made.addEventListener("click", action);
  return made;
}

function repositories(locale, value, actions) {
  const say = (key) => hubText(locale, `hub.add.${key}`);
  const owner = node("input", {type: "text", maxlength: "39", value: value.owner ?? "",
    "aria-label": say("github_owner"), "data-focus": "github-owner"});
  const load = control("github-list", say("github_list"),
    () => actions.repositories(owner.value.trim()), value.listing);
  const rows = [node("div", {className: "hub-add__sources"}, [
    node("label", {text: say("github_owner")}, [owner]), load])], choices = [];
  for (const repo of value.repos ?? []) {
    if (typeof repo.full_name !== "string") continue;
    choices.push(node("div", {}, [control(`repo:${repo.full_name}`, repo.full_name,
      () => actions.repository(repo.full_name)),
    node("span", {text: typeof repo.description === "string" ? repo.description.slice(0, 200) : ""})]));
  }
  rows.push(node("div", {className: "hub-repositories"}, choices));
  if (value.truncated) rows.push(node("p", {text: say("github_truncated")}));
  if (value.listError) rows.push(node("p", {role: "alert", text: codeWords(locale, value.listError)}));
  return rows;
}

export function githubFields(locale, add, actions) {
  const say = (key) => hubText(locale, `hub.add.${key}`);
  const value = add.github ?? {state: "loading"};
  const state = ["loading", "ok", "not_logged_in", "not_pinned", "changed", "unreachable", "failed"]
    .includes(value.state) ? value.state : "failed";
  const rows = [node("div", {className: "hub-add__sources"}, [node("p", {text: say(`github_${state}`)}),
    control("github-refresh", say("github_refresh"), actions.github, state === "loading")])];
  if (state === "not_logged_in") rows.push(node("code", {
    text: "gh auth login --hostname github.com --web"}), node("p", {text: say("github_pinned_login")}));
  if (state === "ok") {
    rows.push(node("p", {text: String(value.login ?? "")}), ...repositories(locale, value, actions));
    const repo = node("input", {type: "text", value: add.repo ?? "", maxlength: "140",
      "aria-label": say("github_repo"), "data-focus": "github-repo"});
    repo.addEventListener("change", () => actions.repository(repo.value.trim()));
    rows.push(node("label", {text: say("github_repo")}, [repo]));
  }
  return rows;
}
