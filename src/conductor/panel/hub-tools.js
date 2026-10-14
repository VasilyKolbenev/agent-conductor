"use strict";
// The tools the hub page asks a person to pin (spec 8.8, 4.6.3, 4.6.4): `git` and `gh`. `GET
// /hub/setup` lists, for a tool that is not settled, the candidates the hub itself found: an id,
// the last folder and file (`display`) and the version the tool said. A person confirms the
// display and the version, and the id goes to the pin route and nowhere else: the page never sees
// or sends a path, and the id is on no screen and in no attribute.
//
// The first half is pure. A tool is a row only while it asks a person to look (`not_pinned`, or
// pinned and `changed`, `too_old` or `unreadable`); a pin FILE that cannot be read is a row with
// no candidate (the owner has to fix the file first) and is never said as the tool's version. The
// hint that a tool installed a moment ago is found only by a restart of the hub stands beside a
// tool that is not pinned and beside none other (the hub looks once, when it starts). The second
// half draws the rows, as text nodes and elements; a press is a call to a handler.
import {hubText} from "./hub-copy.js";
import {node} from "./hub-rail.js";

//: The two tools, in the order the page lists them.
const TOOLS = Object.freeze(["gh", "git"]);
//: The states of a tool that ask a person to look: the hub lists candidates for these only.
export const UNSETTLED = Object.freeze(["not_pinned", "changed", "too_old", "unreadable"]);
//: The words of `detail.reason` that say the pin FILE is the problem, not the version of the tool
//: (lane H's closed list, held equal to its own by `tests/test_hub_tools.py`).
export const PIN_FILE_REASONS = Object.freeze(["corrupt", "unreadable", "unwritable"]);
//: The id the hub gives a candidate (spec 4.6.4); one that does not fit is not offered.
const CANDIDATE = /^cand-[0-9a-f]{32}$/;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

//: The candidates a person may confirm: an id of the grammar, and the display and the version to
//: confirm it by. Nothing else of what the hub sent comes through.
function offered(list) {
  return (Array.isArray(list) ? list : []).filter((one) => isObject(one)
    && typeof one.candidate_id === "string" && CANDIDATE.test(one.candidate_id)
    && typeof one.display === "string" && typeof one.version === "string")
    .map((one) => ({id: one.candidate_id, text: `${one.display} · ${one.version}`}));
}

/**
 * The rows of the banner of tools: `{tool, state, text, hint, candidates: [{id, text}]}`, one for
 * each tool of `setup.tools` that asks a person to look, in the words of `locale`.
 */
export function toolRows(setup, locale) {
  const held = isObject(setup) && isObject(setup.tools) ? setup.tools : {};
  return TOOLS.flatMap((tool) => {
    const one = held[tool];
    if (!isObject(one) || !UNSETTLED.includes(one.state)) return [];
    const file = one.state === "unreadable" && one.display === null;
    return [{tool, state: one.state,
      text: file ? hubText(locale, "hub.tool.pin_problem.unreadable")
        : hubText(locale, `hub.tool.state.${one.state}`, {tool}),
      hint: one.state === "not_pinned" ? hubText(locale, "hub.tool.restart_to_find") : null,
      candidates: file ? [] : offered(one.candidates)}];
  });
}

/**
 * The notice that follows a press of «Закрепить»: `{key, code}` as the page's other notices are. A
 * pin FILE that cannot be used is told by its own sentence and never by the words of the version.
 */
export function pinNotice(answer) {
  if (answer.status === "accepted") return {key: "hub.tool.pinned", code: null};
  if (answer.status !== "refused") return {key: "hub.notice.unknown", code: null};
  const reason = answer.payload?.error?.detail?.reason;
  if (answer.code === "tool_version_unreadable" && PIN_FILE_REASONS.includes(reason)) {
    return {key: `hub.tool.pin_problem.${reason}`, code: null};
  }
  if (answer.code === "git_changed" || answer.code === "gh_changed") {
    return {key: "hub.tool.pin_changed", code: null};
  }
  if (answer.code === "git_too_old") return {key: "hub.tool.pin_too_old", code: null};
  return {key: "hub.notice.refused", code: answer.code};
}

// -- drawing -----------------------------------------------------------------------------------

/**
 * The blocks of the banner, one for each row: the tool's words, each candidate by display and
 * version with its press, and the hint. A press calls `onPin(tool, id)`; the id is never drawn.
 */
export function toolBlocks(rows, locale, onPin) {
  return rows.map((row) => {
    const candidates = row.candidates.map((one, at) => {
      const press = node("button", {type: "button", "data-focus": `pin:${row.tool}:${at}`,
        text: hubText(locale, "hub.act.pin")});
      press.addEventListener("click", () => onPin(row.tool, one.id));
      return node("div", {className: "hub-tool__candidate"},
        [node("span", {text: one.text}), press]);
    });
    return node("div", {className: "hub-tool", "data-tool": row.tool, "data-state": row.state},
      [node("span", {text: row.text}), ...candidates,
        ...(row.hint === null ? [] : [node("small", {text: row.hint})])]);
  });
}
