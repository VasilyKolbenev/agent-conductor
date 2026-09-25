"use strict";
// The Studio's shell chrome and its Overview screen.
//
// It writes DOM and nothing else: no `fetch(`, no stream, no clock, no storage.
// Every control it builds calls a handler the transport module owns, so a
// button that WRITES is still built by the module that owns the door it writes
// through -- what is built here is the shape, and the door is passed in.
//
// Every sentence on the Overview is DERIVED from a payload. Where a fact is not
// derivable from a durable record this build keeps, the screen says exactly
// that instead of guessing: `project.name` is the first of them, and there is
// no place in this file where a missing value becomes a plausible one.
import {element, field} from "./command-view.js";
import {RESULT_OUTCOMES} from "./studio-model.js";
import {reachable, runForm} from "./studio-runform.js";
import {saveRefusal} from "./studio-shell.js";
import {localize, noticeText} from "./studio-i18n.js";
import {newestRun} from "./studio-taskruns.js";

//: The one sentence `verification_failed` never appears without.
export const VERIFICATION_NOTE = "Process exit 0 proves the process finished, "
  + "not that the work was verified.";
const NOT_STATED = "not stated";
const NEW_DRAFT = "Edit as new draft";
const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}";
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function show(state, value) {
  if (value === null || value === undefined || value === "") return localize(state, "view.not_stated");
  if (Array.isArray(value)) return value.length ? value.join(", ") : localize(state, "view.not_stated");
  return String(value);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

function chip(channel, word) {
  const glyph = {pass: "✓", wait: "●", fail: "✕", none: "·"}[channel] || "·";
  return element("span", {className: `studio-chip studio-chip--${
    glyph === "·" ? "none" : channel}`}, [
    element("i", {className: "studio-glyph", text: glyph}),
    element("span", {text: word}),
  ]);
}

function fact(state, label, value) {
  return element("p", {className: "studio-row"}, [
    element("span", {text: `${label}: `}),
    element("span", {className: "studio-mono", text: show(state, value)}),
  ]);
}

function note(value) { return element("p", {className: "studio-hint", text: value}); }

//: A control whose handler was not wired is DISABLED and says why. It never
//: disappears: a button that vanishes teaches a user the product cannot do the
//: thing, when what happened is that this screen was mounted without its wire.
function button(state, handlers, name, label, argument, extra) {
  const call = handlerOf(handlers, name);
  const control = element("button", Object.assign({className: "studio-btn",
    "data-focus": `action:${name}`, text: label, type: "button"}, extra || {}));
  if (call === null) {
    control.disabled = true;
    control.title = localize(state, "view.m069", {name: String(name)});
    return control;
  }
  control.addEventListener("click", () => call(argument));
  return control;
}

function option(value, label) {
  return element("option", {text: label === undefined ? value : label, value});
}

function card(title, children) {
  return element("section", {className: "studio-card"},
    [element("h3", {text: title}), ...children]);
}

// -- the Overview ---------------------------------------------------------
//: The chosen workflow's row in the list, or null. The LIST is the authority on
//: a workflow's name: a detail read carries revisions and a draft, not a title.
function chosenWorkflow(state) {
  return rows(state.workflows.list).find(
    (row) => row.workflow_id === state.workflows.selectedId) || null;
}

//: The most recent run, by the instant the run itself recorded. A row that does
//: not replay carries no instant, so it can never be "the latest" -- it is
//: counted among the blocked instead, where it can be acted on.
function latestRun(state) {
  const selected = newestRun(state.runs, undefined);
  return selected.state === "known" ? selected.row : null;
}

function gatesWaiting(state) {
  if (state.connection !== "open" || state.runs.phase !== "ready") return [];
  const needed = new Set(rows(state.runs.detail?.graph?.situation?.gates)
    .filter((gate) => gate.needs_decision).map((gate) => gate.gate_id));
  return rows(state.decisions.list).filter((row) => needed.has(row.gate_id));
}

//: What stops this project running, each row naming the payload it came from.
//: Nothing here is a severity this window invented: a row exists because a read
//: answered with it.
export function blockingRows(state) {
  const held = state.workflows;
  const found = [];
  for (const line of rows(held.problems)) {
    found.push({where: "workflow", screen: "workflow", text: noticeText(state, line)});
  }
  for (const row of rows(held.diagnostics)) {
    found.push({where: "workflow", screen: "workflow",
      text: localize(state, "view.m070", {message: String(row.message)})});
  }
  for (const row of rows(held.list).filter((entry) => entry.unreadable === true)) {
    found.push({where: "workflow", screen: "workflow",
      text: localize(state, "view.m071", {id: String(row.workflow_id)})});
  }
  for (const row of rows(state.runs.list).filter((entry) => entry.unreadable === true)) {
    found.push({where: "run", screen: "runs",
      text: localize(state, "view.m072", {id: String(row.run_id)})});
  }
  for (const [capability, steps] of unservedCapabilities(state)) {
    found.push({where: "agents", screen: "agents",
      text: localize(state, "view.m073", {capability: String(capability), count: String(steps.length), steps: steps.join(", ")})});
  }
  return found;
}

//: Which capabilities THIS drawing needs that nothing available can carry out.
//:
//: This used to be one row per provider that was not `available`, which on a
//: fresh install meant five blocking rows before the person had a workflow that
//: needed any of them -- the mandate's own complaint, and a fair one: an
//: unconfigured provider is a setup fact for the Agents screen, not a thing
//: standing between this project and a run.
//:
//: What genuinely blocks is a capability the chosen steps declare and no
//: available provider offers. It names the capability and the steps rather than
//: the provider, because the plan asks for a capability and which product
//: serves it is bound when a run opens. With no workflow chosen there is
//: nothing to be blocked ON, and this answers empty.
//:
//: Read off the PUBLISHED revision and never off the drawing, for the reason
//: `runForm` gives in `studio-runform.js`: a run materializes a revision, so a
//: capability only this window has drawn is one no run could ask for yet.
function unservedCapabilities(state) {
  const detail = object(state.workflows.detail);
  const published = detail === null ? null : object(detail.published);
  const needed = new Map();
  for (const node of rows(published && published.nodes)) {
    if (!node || typeof node.capability !== "string") continue;
    if (!needed.has(node.capability)) needed.set(node.capability, []);
    needed.get(node.capability).push(node.node_id);
  }
  const servable = new Set();
  for (const row of rows(state.providers)) {
    if (row.availability !== "available") continue;
    for (const control of rows(row.controls)) servable.add(control);
  }
  return [...needed].filter(([capability]) => !servable.has(capability));
}

//: Whether this project could start a run, and WHY -- never a bare yes. The two
//: conditions are the ones the open-run route itself enforces: a revision must
//: exist to materialize, and every provider named must be one this build
//: resolved as available.
export function readiness(state) {
  const workflow = chosenWorkflow(state);
  const revision = workflow === null ? null : workflow.latest_revision;
  const providers = reachable(state);
  if (workflow === null) {
    return {ready: false, channel: "wait",
      why: localize(state, "view.m001")};
  }
  if (revision === null) {
    return {ready: false, channel: "wait",
      why: localize(state, "view.m074", {id: String(workflow.workflow_id)})};
  }
  if (!providers.length) {
    return {ready: false, channel: "fail",
      why: localize(state, "view.m002")};
  }
  return {ready: true, channel: "pass",
    why: localize(state, "view.m075", {revision: String(revision), count: String(providers.length)})};
}

function whatThisIs(state, handlers) {
  const workflow = chosenWorkflow(state);
  const body = [
    element("p", {className: "studio-hint", text: state.project.name !== null
      ? localize(state, "view.m076", {name: String(state.project.name)})
      : localize(state, "view.m003")}),
  ];
  if (workflow === null) {
    body.push(note(localize(state, "view.m004")),
    button(state, handlers, "onScreen", localize(state, "view.m005"), "workflow"));
    return card(localize(state, "view.m006"), body);
  }
  body.push(fact(state, localize(state, "view.m007"), workflow.workflow_id),
    fact(state, localize(state, "view.m008"), workflow.title),
    fact(state, localize(state, "view.m009"), workflow.revisions),
    fact(state, localize(state, "view.m010"), workflow.latest_revision),
    fact(state, localize(state, "view.m011"), workflow.has_draft ? localize(state, "view.m093") : localize(state, "view.m094")),
    button(state, handlers, "onScreen", localize(state, "view.m012"), "workflow"));
  if (state.workflows.provenance === "local") {
    body.push(note(localize(state, "view.m013")));
  }
  return card(localize(state, "view.m006"), body);
}

function readyCard(state) {
  const answer = readiness(state);
  return card(localize(state, "view.m014"), [
    chip(answer.channel, answer.ready ? localize(state, "view.m015") : localize(state, "view.m016")),
    note(answer.why),
  ]);
}

function blockedCard(state, handlers) {
  const found = blockingRows(state);
  if (!found.length) {
    return card(localize(state, "view.m017"), [
      note(localize(state, "view.m018")),
    ]);
  }
  const list = element("ul", {className: "studio-list"});
  for (const row of found.slice(0, 12)) {
    list.append(element("li", {className: "studio-row"}, [
      element("span", {text: row.text}),
      button(state, handlers, "onScreen", localize(state, "view.m019"), row.screen),
    ]));
  }
  const body = [chip("fail", localize(state, "view.m077", {count: String(found.length)})), list];
  if (found.length > 12) {
    body.push(note(localize(state, "view.m078", {count: String(found.length - 12)})));
  }
  return card(localize(state, "view.m017"), body);
}

function needsYouCard(state, handlers) {
  const situation = state.runs.detail?.graph?.situation;
  const fresh = state.connection === "open" && state.runs.phase === "ready" && situation;
  const value = fresh ? situation.state : "unknown";
  const body = [note(localize(state, `bridge.${value}`))];
  if (fresh) for (const row of situation.checked) {
    if (row.count > 0 && row.reason !== "run_ended") body.push(note(localize(state,
      `bridge.${row.reason}`, {count: String(row.count)})));
  }
  if (gatesWaiting(state).length) body.push(button(state, handlers, "onScreen",
    localize(state, "scene.open_decisions"), "decisions"));
  return card(localize(state, "bridge.attention"), body);
}

function outcomeChannel(word) {
  if (word === "succeeded") return "pass";
  if (word === null || word === undefined) return "none";
  return RESULT_OUTCOMES.includes(word) ? "fail" : "none";
}

function latestRunCard(state, handlers) {
  const row = latestRun(state);
  if (row === null) {
    return card(localize(state, "view.m020"), [
      note(rows(state.runs.list).length
        ? localize(state, "view.m021")
        : localize(state, "view.m022")),
      button(state, handlers, "onScreen", localize(state, "view.m023"), "runs"),
    ]);
  }
  const body = [
    fact(state, localize(state, "view.m024"), row.run_id), fact(state, localize(state, "view.m025"), row.created_at),
    fact(state, localize(state, "view.m026"), row.mode),
    fact(state, localize(state, "view.m027"), row.envelope_status),
    note(localize(state, "view.m028")),
    chip(outcomeChannel(row.last_outcome),
      localize(state, "view.m079", {outcome: show(state, row.last_outcome)})),
  ];
  if (row.last_outcome === "verification_failed") body.push(note(localize(state, "view.verification_note")));
  if (row.last_outcome === null) {
    body.push(note(localize(state, "view.m029")));
  }
  body.push(fact(state, localize(state, "bridge.attention"), localize(state, `bridge.${state.connection === "open" ? row.human_state || "unknown" : "unknown"}`)),
    fact(state, localize(state, "view.m030"), row.open_actions),
    button(state, handlers, "onSelectRun", localize(state, "view.m031"), row.run_id));
  return card(localize(state, "view.m020"), body);
}

/** Draw source-derived Overview facts, latest run and attention first.
 * `mount` is #bodyOverview; `state` is frozen; `handlers` own navigation.
 */
export function mountOverview(mount, state, handlers) {
  const sections = [
    ["latest", latestRunCard(state, handlers)],
    ["attention", needsYouCard(state, handlers)],
    ["blocked", blockedCard(state, handlers)],
    ["ready", readyCard(state)], ["context", whatThisIs(state, handlers)],
  ];
  mount.classList.add("studio-overview");
  mount.replaceChildren(...sections.map(([name, node]) => {
    node.classList.add(`studio-overview__${name}`); return node;
  }));
}

// -- the workflow toolbar -------------------------------------------------
function workflowPicker(state, handlers) {
  const choose = handlerOf(handlers, "onChooseWorkflow");
  const held = rows(state.workflows.list);
  const chosen = state.workflows.selectedId || "";
  // A workflow just STARTED is not in the server's list — nothing has been
  // saved under that id yet — so setting `value` to it matched no option and
  // the picker fell back to localize(state, "view.m032"). A person who had named a
  // workflow and seeded its drawing was told nothing was chosen, and only a
  // reload (after a save) fixed it. It gets an option of its own, saying what
  // it is, so the picker reports the state the rest of the screen is in.
  const unsaved = chosen && !held.some((row) => row.workflow_id === chosen)
    ? [option(chosen, localize(state, "view.m080", {id: String(chosen)}))] : [];
  const control = element("select", {"data-focus": "pick-workflow",
    name: "workflow"}, [option("", localize(state, "view.m032"))].concat(
    held.map((row) => option(row.workflow_id,
      `${row.workflow_id}${row.title === null ? "" : ` — ${row.title}`}`)),
    unsaved));
  control.value = chosen;
  if (choose === null) control.disabled = true;
  else control.addEventListener("change", () => choose(control.value || null));
  return field(localize(state, "view.m007"), control);
}

//: What one starter is CALLED in the picker, and what it is not.
//:
//: Not its title. EVERY shipped starter is titled `Dalio five-step cycle`, so
//: a list of titles offered rows a person could not tell apart and could
//: not choose between — and they are not equivalent: one ships four review
//: steps that cannot succeed. The revision separates them, and the caveat
//: says which one to avoid — but NOT here (R08 of the review of `8dec0e4`):
//: a native option's text is the select's intrinsic width, and one caveat of
//: 191 characters made the control 1379px wide and the page 1399 in a 1280px
//: window. The label says that a note exists; `starterNote` draws the note
//: itself, whole, under the control, for the starter chosen.
function starterLabel(state, row) {
  const named = localize(state, "view.m081", {title: String(row.title), revision: String(row.revision)});
  return rows(row.caveats).length === 0
    ? localize(state, "view.m082", {name: named})
    : localize(state, "view.m083", {name: named});
}

//: The chosen starter's caveats, every one and in full, as readable text.
function starterNote(state, row) {
  if (row === null) return localize(state, "view.m033");
  const caveats = rows(row.caveats);
  return caveats.length === 0
    ? localize(state, "view.m084", {title: String(row.title), revision: String(row.revision)})
    : caveats.join(" ");
}

//: Starting a workflow is TWO facts: the id it will live under, and the
//: document it starts from. Neither is guessed: a blank start is an empty
//: drawing, and every other offer is a document this BUILD ships. Both are
//: drawn from the reducer's own copy and committed back on change
//: (`studio-toolbardraft.js`): a frame lands on every write of any run, and
//: a control drawn from nothing lost the id a person was typing. The letters
//: typed since the last change, and the caret, are the boot module's focus
//: net's to carry across the render; committing on every keystroke moved the
//: caret to the end and doubled an IME's composition (the fold review).
function executionChoice(state, held, edit) {
  const execution = element("select", {"data-focus": "new-execution", name: "new-execution"}, [
    option("", localize(state, "automation.workflow_manual")),
    option("bounded-run-v1", localize(state, "automation.workflow_bounded"))]);
  execution.value = held.executionContract || "";
  execution.disabled = edit === null;
  execution.addEventListener("change", () => { if (edit) edit({executionContract: execution.value}); });
  return execution;
}

function starterControls(state, handlers) {
  const box = element("div", {className: "studio-field studio-field--row"});
  const held = object(state.workflows.starter) || {};
  const edit = handlerOf(handlers, "editStarter");
  const name = element("input", {autocomplete: "off",
    "data-focus": "new-workflow", maxlength: "128", name: "new-workflow",
    pattern: ID_PATTERN, spellcheck: "false", type: "text"});
  name.value = typeof held.workflowId === "string" ? held.workflowId : "";
  const starters = rows(state.workflows.starters);
  const from = element("select", {"data-focus": "new-from", name: "new-from"},
    [option("", localize(state, "view.m034"))].concat(starters.map(
      (row) => option(row.starter_id, starterLabel(state, row)))));
  from.value = typeof held.starterId === "string" ? held.starterId : "";
  const execution = executionChoice(state, held, edit);
  const chosen = starters.find((row) => row.starter_id === from.value) || null;
  const said = element("p", {className: "studio-hint",
    "data-starter-note": "", text: starterNote(state, chosen)});
  if (edit === null) {
    name.disabled = true;
    from.disabled = true;
    name.title = localize(state, "view.m035");
  } else {
    name.addEventListener("change", () => edit({workflowId: name.value}));
    from.addEventListener("change", () => edit({starterId: from.value}));
  }
  const start = handlerOf(handlers, "onStartWorkflow");
  const go = element("button", {className: "studio-btn",
    "data-focus": "action:onStartWorkflow", text: localize(state, "view.m036"),
    type: "button"});
  if (start === null) {
    go.disabled = true;
    go.title = localize(state, "view.m037");
  } else {
    go.addEventListener("click", () => start(
      {workflowId: name.value.trim(), starterId: from.value || null, executionContract: execution.value}));
  }
  // The three facts and their one action stand in one row; what they mean reads beneath
  // them, so an open start box costs one row of controls and one line of notes.
  box.append(field(localize(state, "view.m038"), name), field(localize(state, "view.m039"), from),
    field(localize(state, "automation.workflow_kind"), execution), go,
    element("div", {className: "studio-notes"}, [said, note(localize(state, "automation.workflow_note"))]));
  return box;
}


function saveControls(state, handlers) {
  const held = state.workflows;
  const box = element("div", {className: "studio-field studio-field--row"});
  const save = button(state, handlers, "onSaveDraft", localize(state, "primary.workflow"), null);
  const publish = button(state, handlers, "onPublish",
    held.nextRevision === null ? localize(state, "view.m040")
      : localize(state, "view.m085", {revision: String(held.nextRevision)}), null);
  const check = button(state, handlers, "onValidate", localize(state, "view.m041"), null);
  // The copy road is shut with a reason whenever pressing it would do nothing.
  const shut = held.draft !== null
    ? localize(state, "view.m042")
    : (object(held.detail) === null || object(held.detail.published) === null
      ? localize(state, "view.m043")
      : (held.writeReady ? null
        : localize(state, "view.m044")));
  const fresh = button(state, handlers, "onEditPublished", localize(state, "view.new_draft"), null,
    {disabled: shut === null ? null : "", title: shut});
  const refusal = saveRefusal(held, state);
  if (refusal !== null) {
    save.disabled = true;
    save.title = refusal;
  }
  if (!held.writeReady || !held.publishable) {
    publish.disabled = true;
    publish.title = held.unchanged
      ? localize(state, "view.m045")
      : (held.publishable
        ? localize(state, "view.m044")
        : localize(state, "view.m046"));
  }
  box.append(check, save, publish, fresh);
  if (held.reviewing) box.append(publishReview(state, handlers));
  return box;
}

//: One line per KIND of change, and the ids under it. A person about to create
//: an immutable revision is answering "is this what I meant", and a count with
//: no names cannot be checked against what they remember doing.
function changeLines(state, changes) {
  const lines = [];
  if (changes === null) return lines;
  if (changes.first) {
    lines.push(localize(state, "view.m088", {title: String(changes.title.to)}));
  } else if (changes.title !== null) {
    lines.push(localize(state, "view.m089", {before: String(changes.title.from), after: String(changes.title.to)}));
  }
  const named = [[localize(state, "view.m047"), changes.added],
                 [localize(state, "view.m048"), changes.removed],
                 [localize(state, "view.m049"), changes.changed],
                 [localize(state, "view.m050"), changes.edgesAdded],
                 [localize(state, "view.m051"), changes.edgesRemoved]];
  for (const [label, ids] of named) {
    if (ids.length) lines.push(`${label} (${ids.length}): ${ids.join(", ")}`);
  }
  return lines;
}

//: The step between the pointer and a durable revision. It states the number
//: about to be created, what would change, and that validation passed -- and
//: it offers a way out. Cancel writes nothing at all: it closes this panel and
//: leaves the draft, the drawing and the standing revisions exactly as they
//: were, which is why it is a button and not a smaller word.
function publishReview(state, handlers) {
  const held = state.workflows;
  const lines = changeLines(state, held.changes);
  const box = element("div", {className: "studio-review",
    "data-review": "publish"});
  box.append(element("h3", {text: localize(state, "view.m086", {revision: String(held.nextRevision)})}));
  box.append(element("p", {className: "studio-hint", text:
    localize(state, "view.m052")}));
  box.append(element("p", {className: "studio-fact__v", text:
    held.diagnostics.length === 0
      ? localize(state, "view.m053")
      : localize(state, "view.m054")}));
  if (held.changes !== null && held.changes.first) {
    box.append(element("p", {className: "studio-hint", text:
      localize(state, "view.m055")}));
  }
  if (held.changes === null) {
    box.append(element("p", {className: "studio-hint", text:
      localize(state, "view.m056")}));
  } else if (lines.length === 0) {
    box.append(element("p", {className: "studio-hint", text:
      localize(state, "view.m057")}));
  } else {
    box.append(element("ul", {className: "studio-review__changes"},
      lines.map((line) => element("li", {text: line}))));
  }
  box.append(button(state, handlers, "onPublishConfirm",
    localize(state, "view.m087", {revision: String(held.nextRevision)}), null));
  box.append(button(state, handlers, "onPublishCancel", localize(state, "view.m058"), null));
  return box;
}

function saveLine(state) {
  const held = state.workflows;
  const said = element("p", {className: "studio-state",
    "data-save": held.savePhase, text: noticeText(state, held.saveNotice)});
  return said;
}

//: A box folded behind a summary that names its state. The toolbar's forms
//: stood 395px tall over the canvas, which began at 653 of 800 (R08 of the
//: review of `8dec0e4`). `<details>` is the platform's own disclosure: the
//: summary is a focusable, keyboard-toggled control with no script of its
//: own, and what is folded stays in the document. Which boxes start OPEN is
//: decided by the state, so nothing a person needs now is hidden: the start
//: box while no workflow is chosen, the run box while a revision is published
//: and no drawing is being edited. The summary says what the fold holds and
//: where that stands, so a closed one is a sentence and not a blank.
//:
//: A fold a person TOUCHED is theirs (`studio-toolbardraft.js`): the toggle
//: is recorded and drawn back on every render, where the state-decided one
//: used to close the box on the next frame. The one drawn from state is not
//: a choice, so a toggle that reports what was drawn records nothing. The
//: summary carries a focus key, so the render the toggle provokes gives the
//: keyboard back the summary it was standing on.
function disclosure(name, summary, open, body, handlers) {
  const box = element("details", Object.assign({className: "studio-fold",
    "data-fold": name}, open ? {open: ""} : {}),
  [element("summary", {"data-focus": `fold:${name}`, text: summary}), body]);
  const fold = handlerOf(handlers, "onFold");
  if (fold !== null) {
    box.addEventListener("toggle", () => {
      if (box.open !== open) fold(name, box.open);
    });
  }
  return box;
}

//: Which way a fold stands: the person's own choice while they have made
//: one, and otherwise as the state decides.
function foldOpen(held, name, byState) {
  const chosen = (object(held.folds) || {})[name];
  return typeof chosen === "boolean" ? chosen : byState;
}

//: What the run fold holds and where that stands, in the order a person
//: meets the states: no workflow chosen, one chosen and not yet read (or
//: refused), one chosen and unpublished, published.
function runSummary(state, held) {
  const chosen = typeof held.selectedId === "string" && held.selectedId !== "";
  if (!chosen) return localize(state, "view.m059");
  const detail = object(held.detail);
  if (detail === null) return localize(state, "view.m060");
  const published = object(detail.published);
  return published === null
    ? localize(state, "view.m061")
    : localize(state, "view.m090", {revision: String(published.revision)});
}

/**
 * Draw the workflow toolbar: which workflow, how to start one, the two write
 * doors and the form that opens a run.
 *
 * The run form itself is `studio-runform.js`'s: it is the only part of this
 * toolbar that starts something running rather than describing the document,
 * and it left here when this file reached the line cap. It and the start box
 * sit behind a disclosure each (`disclosure`), open or folded by the state.
 *
 * @param {Element} mount `#workflowToolbar`
 * @param {object} state the reducer's frozen value
 * @param {object} handlers `onChooseWorkflow`, `onStartWorkflow`, `onValidate`,
 *   `onSaveDraft`, `onPublish`, `onEditPublished`, `onOpenRun`
 */
export function mountToolbar(mount, state, handlers) {
  const held = state.workflows;
  const chosen = typeof held.selectedId === "string" && held.selectedId !== "";
  const detail = object(held.detail);
  const published = detail !== null && object(detail.published) !== null;
  mount.replaceChildren(workflowPicker(state, handlers),
    disclosure("start", localize(state, "view.m062"), foldOpen(held, "start", !chosen),
      starterControls(state, handlers), handlers),
    saveControls(state, handlers), saveLine(state),
    disclosure("run", runSummary(state, held),
      foldOpen(held, "run", published && held.draft === null),
      runForm(state, handlers), handlers));
}

// -- the diagnostics panel ------------------------------------------------
function diagList(state, title, said, lines, code) {
  const box = element("div", {className: "studio-section"});
  box.append(element("h4", {text: title}), note(said));
  if (!lines.length) {
    box.append(element("p", {className: "studio-hint",
      text: localize(state, "view.m063")}));
    return box;
  }
  const list = element("ul", {className: "studio-list"});
  for (const line of lines) {
    list.append(element("li", {className: "studio-diag"}, [
      element("span", {className: "studio-diag__code", text: code}),
      element("span", {text: noticeText(state, line)}),
    ]));
  }
  box.append(list);
  return box;
}

/**
 * Draw what stops this workflow being published -- two lists, because they
 * describe two documents and neither may answer for the other.
 *
 * @param {Element} mount `#workflowDiagnostics`
 * @param {object} state the reducer's frozen value
 */
export function mountDiagnostics(mount, state) {
  const held = state.workflows;
  mount.replaceChildren(element("h3", {text: localize(state, "view.m064")}));
  mount.append(
    diagList(state, localize(state, "view.m065"),
      localize(state, "view.m066"),
      rows(held.problems), "local"),
    diagList(state, localize(state, "view.m067"),
      held.savedAt === null
        ? localize(state, "view.m068")
        : localize(state, "view.m091", {at: String(held.savedAt)}),
      rows(held.diagnostics).map((row) => row.message), "server"));
  if (held.publishable) {
    mount.append(element("p", {className: "studio-hint",
      text: localize(state, "view.m092", {revision: show(state, held.nextRevision)})}));
  }
}

//: The id grammar, exported so the transport module refuses the same spellings
//: these controls advertise rather than a second opinion about them.
export function isId(value) {
  return typeof value === "string" && ID_RE.test(value);
}
