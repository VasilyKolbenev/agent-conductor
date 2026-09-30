"use strict";
// The summary at the foot of the desk (spec 5.1 and 5.4): a bar with four counters, a strip of
// tasks and what is going on now in the run on the scene, and, on a press, the panel "кто что
// делал и сделал" -- every task with the word the rail gives it and what the records say of who
// did, checked and accepted, and the participants of the run on the scene. It draws what the
// boot module hands it and reads nothing: the sorting, the digests and the people are
// `desk-summary-model.js`'s, the words are `desk-summary-copy.js` and the status words of
// `desk-status-copy.js`.
//
// The bar is drawn when its numbers are known -- both lists read and the reads that say which
// tasks were closed landed -- and not before, so a count that is about to change is not shown.
// A counter's hint says what it counts; "closed" says exactly what the spec says it means. The
// panel opens and folds by a press and keeps that memory in its own DOM (the way the feed keeps
// its documents): a redraw reads it off the mount before the mount is replaced.
import {element} from "./command-view.js";
import {MESSAGES, localize} from "./studio-i18n.js";
import {instantText} from "./desk-time.js";
import {PLACES, digestOf, nowOf, participantsOf, summaryOf} from "./desk-summary-model.js";

const PANEL_ID = "deskSummaryPanel";
const GLYPHS = Object.freeze({working: "●", waiting: "◆", closed: "✓", left: "○", unclear: "?"});
//: The tone a place carries in the strip and beside a task: amber asks for a person and ion says
//: it goes; a task accepted is told by its glyph and its words.
const TONES = Object.freeze({working: "ion", waiting: "amber", closed: "done"});
//: The chip's edge is toned for the two places that ask for a look.
const CHIP_TONES = Object.freeze({working: "ion", waiting: "amber"});

const tone = (place) => (Object.hasOwn(TONES, place) ? TONES[place] : null);

// -- the bar --------------------------------------------------------------------------------------

function chip(view, place, count) {
  const found = Object.hasOwn(CHIP_TONES, place) ? CHIP_TONES[place] : null;
  return element("span", {className: "desk-sum__chip", "data-tone": found,
    title: localize(view, `summary.caption_${place}`)}, [
    element("span", {className: "desk-sum__glyph", "aria-hidden": "true", text: GLYPHS[place]}),
    element("span", {className: "desk-sum__label",
      text: localize(view, `summary.label_${place}`)}),
    element("b", {text: String(count)})]);
}

//: What is going on now in the run on the scene, or null when no run is drawn: the attempts in
//: flight with the harness that makes each, the steps that ask a person, or that nothing does.
function nowText(view) {
  const detail = view.run.detail;
  if (detail === null) return null;
  const now = nowOf(detail);
  const parts = now.doing.map((one) => `${one.harness ?? one.instance} · ${one.step}`);
  if (now.asking.length > 0) {
    parts.push(localize(view, "summary.now_asking", {steps: now.asking.join(", ")}));
  }
  const what = parts.length === 0 ? localize(view, "summary.now_idle") : parts.join("; ");
  return localize(view, "summary.now", {run: detail.run.run_id, what});
}

function bar(view, summary, open) {
  const now = nowText(view);
  return element("button", {type: "button", className: "desk-sum__bar",
    "aria-expanded": String(open), "aria-controls": PANEL_ID, "data-focus-key": "summary:toggle"}, [
    element("span", {className: "desk-sum__chips"}, PLACES
      .filter((place) => place !== "unclear" || summary.counts.unclear > 0)
      .map((place) => chip(view, place, summary.counts[place]))),
    element("span", {className: "desk-sum__track", "aria-hidden": "true"},
      summary.rows.map((row) => element("i", {"data-tone": tone(row.place)}))),
    ...(now === null ? [] : [element("span", {className: "desk-sum__now", text: now})]),
    element("span", {className: "desk-sum__more",
      text: localize(view, open ? "summary.less" : "summary.more")})]);
}

// -- the panel: the tasks --------------------------------------------------------------------------

//: A task's status word with the parameters its wording names and no other (the rail's rule).
function wordsOf(view, row) {
  const id = `desk_status.${row.key}`;
  const wanted = [...MESSAGES[id][view.locale].matchAll(/\{([a-z_]+)\}/g)].map((found) => found[1]);
  const params = Object.fromEntries(wanted.map((name) => [name, String(row.params[name])]));
  return localize(view, id, params);
}

//: Who, as a person reads it: the harness, else the instance; each once.
function whoIs(people) {
  return [...new Set(people.map((one) => one.harness ?? one.instance))].join(", ");
}

//: The facts a run digest gives a task's row, each only when the records name someone.
function factsOf(view, digest) {
  if (digest === null) return [];
  const pass = digest.pass === null ? []
    : [localize(view, "scene.pass", {pass: String(digest.pass.pass),
      bound: String(digest.pass.bound)})];
  const said = (key, who) => (who.length === 0 ? [] : [localize(view, key, {who})]);
  return [...pass, ...said("summary.did", whoIs(digest.did)),
    ...said("summary.checked", whoIs(digest.verified)),
    ...said("summary.accepted", digest.accepted.join(", "))];
}

//: The title as the rail draws it: a repeated or unreadable title carries the tail of its id.
function titleOf(view, summary, row) {
  const repeated = summary.rows.filter((other) => other.title === row.title).length > 1;
  const named = row.title ?? localize(view, "desk.rail.unreadable");
  return repeated || row.title === null ? `${named} · ${row.task_id.slice(-8)}` : named;
}

function taskItem(view, summary, row) {
  const note = row.key === "outcome_verification_failed"
    ? [element("span", {className: "desk-sum__task-note",
      text: localize(view, "view.verification_note")})] : [];
  return element("li", {className: "desk-sum__task", "data-tone": tone(row.place)}, [
    element("span", {className: "desk-sum__glyph", "data-tone": tone(row.place),
      "aria-hidden": "true", text: GLYPHS[row.place]}),
    element("strong", {className: "desk-sum__task-title", text: titleOf(view, summary, row)}),
    element("span", {className: "desk-sum__task-what",
      text: [wordsOf(view, row), ...factsOf(view, row.digest)].join(" · ")}, note)]);
}

// -- the panel: the participants of the run on the scene ----------------------------------------

function personItem(view, one) {
  const role = [one.harness, localize(view, `scene.duty_${one.duty}`)]
    .filter((part) => part !== null).join(" · ");
  const facts = [
    ...(one.actions > 0 ? [localize(view, "summary.actions", {count: String(one.actions)})] : []),
    ...(one.checks > 0 ? [localize(view, "summary.checks", {count: String(one.checks)})] : []),
    ...(one.documents.length > 0
      ? [localize(view, "summary.documents", {refs: one.documents.join(", ")})] : [])];
  const said = one.last === null ? null : instantText(view.locale, one.last);
  return element("li", {className: "desk-sum__person"}, [
    element("strong", {className: "desk-sum__person-name", text: one.instance}),
    element("span", {className: "desk-sum__person-role", text: role}),
    element("span", {className: "desk-sum__facts"}, [
      ...facts.map((fact) => element("span", {className: "desk-sum__fact", text: fact})),
      ...(said === null || !said.known ? [] : [
        element("span", {className: "desk-sum__last", text: localize(view, "summary.last")}),
        element("time", {datetime: said.exact, title: said.exact, text: said.short})])])]);
}

function people(view) {
  const detail = view.run.detail;
  if (detail === null) {
    return [element("p", {className: "desk-sum__no-run", text: localize(view, "summary.no_run")})];
  }
  return [
    element("h3", {className: "desk-sum__cap desk-sum__people-head",
      text: localize(view, "summary.people", {run: detail.run.run_id})}),
    element("ul", {className: "desk-sum__people"},
      participantsOf(detail).map((one) => personItem(view, one)))];
}

// -- the panel -----------------------------------------------------------------------------------------

//: The explanation behind the mark: what each place counts, in the words of its hint.
function how(view, open) {
  return element("details", {className: "desk-sum__how", open: open ? "" : null}, [
    element("summary", {"data-focus-key": "summary:how",
      text: `ⓘ ${localize(view, "summary.how")}`}),
    ...PLACES.map((place) => element("p", {}, [
      element("strong", {text: localize(view, `summary.label_${place}`)}),
      document.createTextNode(`: ${localize(view, `summary.caption_${place}`)}`)]))]);
}

function buildPanel(view, summary, held) {
  const open = held !== null && held.open;
  const close = element("button", {type: "button", className: "desk-sum__close",
    "data-focus-key": "summary:close", text: localize(view, "summary.less")});
  return {close, node: element("section", {className: "desk-sum__panel", id: PANEL_ID,
    role: "region", "aria-label": localize(view, "summary.panel"), hidden: open ? null : ""}, [
    element("div", {className: "desk-sum__head"}, [
      element("h2", {className: "desk-sum__title", text: localize(view, "summary.panel")}), close]),
    how(view, held !== null && held.how),
    element("h3", {className: "desk-sum__cap", text: localize(view, "summary.tasks")}),
    element("ul", {className: "desk-sum__tasks"},
      summary.rows.map((row) => taskItem(view, summary, row))),
    ...people(view)])};
}

// -- the mount --------------------------------------------------------------------------------------

//: What the mount held before this pass: whether the panel was open, whether its explanation was,
//: and where it was scrolled. Null when it held no summary.
function heldBy(mount) {
  const toggle = mount.querySelector(".desk-sum__bar");
  if (toggle === null) return null;
  return {open: toggle.getAttribute("aria-expanded") === "true",
    how: Boolean(mount.querySelector(".desk-sum__how")?.open),
    scroll: mount.querySelector(".desk-sum__panel")?.scrollTop ?? 0};
}

//: The digests the panel draws facts from: those the closing reads brought, and the run on the
//: scene for its own task (the same facts, from a run already in hand).
function digests(view) {
  const found = new Map(view.closing);
  const detail = view.run.detail;
  const digest = detail === null ? null : digestOf(detail);
  if (digest !== null && view.taskId !== null && !found.has(view.taskId)) {
    found.set(view.taskId, digest);
  }
  return found;
}

//: A press opens and folds the panel and says so on the bar; nothing is asked of the boot module.
function wire(button, shown, close, view) {
  const set = (open) => {
    button.setAttribute("aria-expanded", String(open));
    shown.hidden = !open;
    button.querySelector(".desk-sum__more").textContent = localize(view,
      open ? "summary.less" : "summary.more");
  };
  button.addEventListener("click", () => set(button.getAttribute("aria-expanded") !== "true"));
  close.addEventListener("click", () => {
    set(false);
    button.focus();
  });
}

export function mountSummary(mount, view) {
  const held = heldBy(mount);
  const summary = view.foreign || !view.listed || view.closing === null ? null
    : summaryOf({tasks: view.tasks, runs: view.runs, automation: view.automation,
      closing: digests(view)});
  if (summary === null || summary.total === 0) {
    mount.replaceChildren();
    return;
  }
  const shown = buildPanel(view, summary, held);
  const button = bar(view, summary, held !== null && held.open);
  wire(button, shown.node, shown.close, view);
  mount.replaceChildren(element("div", {className: "desk-sum"}, [button, shown.node]));
  if (held !== null) shown.node.scrollTop = held.scroll;
}
