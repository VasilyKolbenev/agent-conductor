"use strict";
// The feed "Ход работы" (spec 5.1 and 5.3): the journal of the run on the scene, drawn as the
// facts its records state. It draws what the boot module hands it -- the run read the scene is
// drawn from -- and reads nothing, opens no door and has nothing to press: a feed is a list, and
// a document opens in its own row. The rows are `desk-feed-model.js`'s, the words that say them
// are `desk-feed-copy.js` and the Studio's own for an outcome, a duty and a finding's kind.
//
// A row is an author line (the harness and what it did, or the person who decided), one sentence
// about one step, the reason a person gave, the sentence a check that did not pass owes in the
// SAME row, the Studio's sentence that a check made by the step's own adapter names no independent
// checker, the exact time in a hint, and, for a document, its text -- as text, never as markup.
// The newest row is at the bottom and is the current one (`aria-current`), and the list scrolls.
//
// A redraw keeps what a person did to it, read off the mount before it is replaced (the way the
// scene keeps its lens): which documents are open, where the list was scrolled, and whether the
// reader stood at the bottom. A reader at the bottom stays there as rows arrive; one who
// scrolled up is not pulled down; another run starts at the bottom.
import {element} from "./command-view.js";
import {MESSAGES, localize} from "./studio-i18n.js";
import {instantText} from "./desk-time.js";
import {feedRows} from "./desk-feed-model.js";

//: How far from the bottom a list may stand and still be "at the bottom", in pixels.
const NEAR_BOTTOM = 4;

//: The title of a step, or the words that say the plan names none.
function stepOf(view, row, none = "feed.step_none") {
  return row.step === null ? localize(view, none) : row.step.title;
}

//: The one sentence of each kind of row.
const SAYS = Object.freeze({
  proposed: (view, row) => localize(view, "feed.proposed", {step: stepOf(view, row)}),
  started: (view, row) => localize(view, "feed.started", {step: stepOf(view, row)}),
  result: (view, row) => localize(view, "feed.result", {step: stepOf(view, row),
    word: localize(view, `scene.outcome_${row.word}`)}),
  verdict: (view, row) => localize(view, "feed.verdict", {step: stepOf(view, row),
    word: localize(view, `feed.verdict_${row.word}`)}),
  decision: (view, row) => localize(view, "feed.decision", {
    step: stepOf(view, row, "feed.gate_none"),
    word: localize(view, `feed.decision_${row.word}`)}),
  document: (view, row) => localize(view, "feed.document", {ref: row.doc.ref}),
  findings: (view, row) => localize(view, "feed.findings", {step: stepOf(view, row)}),
});

//: What a live attempt adds to its sentence: that it is going, and the pass a loop stands on.
function liveWords(view, row) {
  if (!row.live) return "";
  const pass = row.pass === null ? ""
    : ` · ${localize(view, "scene.pass", {pass: String(row.pass.pass),
      bound: String(row.pass.bound)})}`;
  return ` · ${localize(view, "feed.live")}${pass}`;
}

//: The author line: the harness and what it did, the person and their part, or that nobody
//: is known. The separator is punctuation and belongs to no language.
function whoLine(view, row) {
  const {who} = row;
  if (who.kind === "unknown") {
    return element("p", {className: "desk-feed__who",
      text: localize(view, "feed.participant_unknown")});
  }
  const person = who.kind === "person";
  const name = person ? who.name ?? localize(view, "feed.person")
    : who.harness ?? who.instance ?? localize(view, "feed.participant_unknown");
  const part = person ? (row.kind === "decision" ? localize(view, "scene.gate") : null)
    : localize(view, `scene.duty_${who.duty}`);
  return element("p", {className: "desk-feed__who"}, [
    element("strong", {className: "desk-feed__name", text: name}),
    ...(part === null ? [] : [document.createTextNode(" · "),
      element("span", {className: "desk-feed__duty", text: part})])]);
}

//: The time of the record in the reader's language, the exact value in the hint; a record with
//: no instant says so in words and never draws an empty place.
function timeOf(view, row) {
  const said = instantText(view.locale, row.at);
  return said.known
    ? element("time", {className: "desk-feed__at", datetime: said.exact, title: said.exact,
      text: said.short})
    : element("span", {className: "desk-feed__at", text: said.short});
}

//: A finding: its kind in the Studio's words, what the checker said, and where it points.
function findingItem(view, item) {
  const key = `feedback.${item.kind}`;
  const where = item.path === null ? null
    : (item.line === null ? item.path : `${item.path}:${item.line}`);
  return element("li", {className: "desk-feed__finding"}, [
    ...(Object.hasOwn(MESSAGES, key) ? [element("strong", {text: localize(view, key)})] : []),
    element("p", {text: item.summary}),
    ...(where === null ? [] : [element("p", {className: "desk-feed__where", text: where})])]);
}

//: The text that opens in a row: a document's own words as plain text, or the findings of a
//: checker. A document past the feed's limit says so instead.
function opening(view, row) {
  if (row.findings !== null) {
    return [element("ul", {className: "desk-feed__findings"},
      row.findings.map((item) => findingItem(view, item)))];
  }
  if (row.doc === null || row.doc.content === null) return [];
  return [element("pre", {className: "desk-feed__text", tabindex: "0", text: row.doc.content})];
}

function disclosure(view, row) {
  if (row.doc !== null && row.doc.tooLarge) {
    return [element("p", {className: "desk-feed__note", text: localize(view, "feed.doc_large")})];
  }
  const body = opening(view, row);
  if (body.length === 0) return [];
  return [element("details", {className: "desk-feed__doc", "data-doc": row.key}, [
    element("summary", {"data-focus-key": `feed:doc:${row.key}`,
      text: localize(view, "feed.doc_open")}), ...body])];
}

function tone(row) {
  if (row.live) return "ion";
  return row.needsNote ? "amber" : null;
}

function rowItem(view, row) {
  const reason = row.reason === null ? []
    : [element("p", {className: "desk-feed__reason",
      text: localize(view, "feed.reason", {reason: row.reason})})];
  const note = row.needsNote
    ? [element("p", {className: "desk-feed__note", text: localize(view, "view.verification_note")})]
    : [];
  const own = row.ownCheck
    ? [element("p", {className: "desk-feed__note", text: localize(view, "runstep.same_adapter")})]
    : [];
  return element("li", {className: "desk-feed__row", "data-kind": row.kind, "data-tone": tone(row)},
    [whoLine(view, row), timeOf(view, row),
      element("p", {className: "desk-feed__what",
        text: SAYS[row.kind](view, row) + liveWords(view, row)}),
      ...reason, ...note, ...own, ...disclosure(view, row)]);
}

//: What the mount held before this pass, or null when it held no list.
function heldBy(mount) {
  const log = mount.querySelector(".desk-feed__log");
  if (log === null) return null;
  return {run: log.dataset.run, scroll: log.scrollTop,
    atBottom: log.scrollHeight - log.scrollTop - log.clientHeight <= NEAR_BOTTOM,
    open: [...log.querySelectorAll("details[open]")].map((node) => node.dataset.doc)};
}

//: The documents that were open stay open, and the list keeps its place unless the reader
//: stood at the bottom or this is another run: then the newest row is in view.
function restore(log, held, runId) {
  const same = held !== null && held.run === runId;
  for (const node of log.querySelectorAll("details")) {
    node.open = same && held.open.includes(node.dataset.doc);
  }
  log.scrollTop = same && !held.atBottom ? held.scroll : log.scrollHeight;
}

function head(view, runId) {
  return element("div", {className: "desk-feed__head"}, [
    element("h2", {className: "desk-feed__title",
      text: localize(view, "feed.title", {run: runId})}),
    element("span", {className: "desk-feed__order", text: localize(view, "feed.order")})]);
}

export function mountFeed(mount, view) {
  const held = heldBy(mount);
  const detail = view.foreign ? null : view.run.detail;
  if (detail === null) {
    mount.replaceChildren();
    return;
  }
  const runId = detail.run.run_id;
  const rows = feedRows(detail);
  if (rows.length === 0) {
    mount.replaceChildren(head(view, runId),
      element("p", {className: "desk-feed__none", text: localize(view, "feed.none")}));
    return;
  }
  const items = rows.map((row) => rowItem(view, row));
  items[items.length - 1].setAttribute("aria-current", "true");
  const log = element("ol", {className: "desk-feed__log", "data-run": runId, tabindex: "0",
    "data-focus-key": "feed:log", "aria-label": localize(view, "feed.title", {run: runId})},
  items);
  mount.replaceChildren(head(view, runId), log);
  restore(log, held, runId);
}
