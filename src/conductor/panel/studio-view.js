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

//: The seven words a screen container may stand in, and the plain sentence each
//: is said with. `studio-runs.js` and `studio-people.js` carry the same table
//: for their own banners; tests/test_studio_wiring.py holds the keys equal.
export const PHASE_SENTENCES = Object.freeze({
  empty: "Nothing has been read yet.",
  loading: "Reading.",
  ready: "Read.",
  stale: "Shown from an earlier read; a newer one has not landed.",
  refused: "This read was refused. Nothing below is newer than the refusal.",
  failed: "This read failed. Nothing below is newer than the failure.",
  disconnected: "The live connection is down, so nothing here updates.",
});
//: Which word wins when a screen is fed by two reads. The least-read source
//: names the screen: an Overview that says `ready` while its run list failed
//: would be reporting one half as the whole.
const PHASE_ORDER = Object.freeze(
  ["failed", "refused", "loading", "stale", "empty", "ready"]);
//: The one sentence `verification_failed` never appears without.
export const VERIFICATION_NOTE = "Process exit 0 proves the process finished, "
  + "not that the work was verified.";
const NOT_STATED = "not stated";
const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}";
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function show(value) {
  if (value === null || value === undefined || value === "") return NOT_STATED;
  if (Array.isArray(value)) return value.length ? value.join(", ") : NOT_STATED;
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

function fact(label, value) {
  return element("p", {className: "studio-row"}, [
    element("span", {text: `${label}: `}),
    element("span", {className: "studio-mono", text: show(value)}),
  ]);
}

function note(value) { return element("p", {className: "studio-hint", text: value}); }

//: A control whose handler was not wired is DISABLED and says why. It never
//: disappears: a button that vanishes teaches a user the product cannot do the
//: thing, when what happened is that this screen was mounted without its wire.
function button(handlers, name, label, argument, extra) {
  const call = handlerOf(handlers, name);
  const control = element("button", Object.assign({className: "studio-btn",
    "data-focus": `action:${name}`, text: label, type: "button"}, extra || {}));
  if (call === null) {
    control.disabled = true;
    control.title = `This screen was mounted without a ${name} handler.`;
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

// -- the shell ------------------------------------------------------------
//: Which of the seven words a screen stands in. A dropped stream outranks every
//: read: the facts on screen may be true and none of them is current.
export function screenPhase(state, screen) {
  if (state.connection === "closed") return "disconnected";
  if (screen === "overview") {
    const seen = [state.workflows.phase, state.runs.phase];
    return PHASE_ORDER.find((word) => seen.includes(word)) || "empty";
  }
  const held = object(state[screen === "workflow" ? "workflows" : screen]);
  const word = held === null ? "empty" : held.phase;
  return Object.hasOwn(PHASE_SENTENCES, word) ? word : "failed";
}

function connectionSentence(state) {
  if (state.connection === "open") {
    return "Connected. Live changes reach this window.";
  }
  return state.connection === "connecting"
    ? "Connecting to this project's live stream."
    : "Connection lost. What is on screen is the last thing that was read; "
      + "nothing here updates and nothing may be written until it is back.";
}

//: The header's one primary action, chosen by the screen showing. It is a verb
//: a person recognises, and it is the same door the screen's own controls use.
const PRIMARY = Object.freeze({
  overview: ["onScreen", "Edit the workflow", "workflow"],
  workflow: ["onSaveDraft", "Save draft", null],
  runs: ["onRefreshRuns", "Read runs again", null],
  decisions: ["onRefreshRun", "Read this run again", null],
  agents: ["onRefreshAgents", "Read the roster again", null],
});

function primaryAction(state, handlers) {
  const named = PRIMARY[state.screen] || PRIMARY.overview;
  const control = button(handlers, named[0], named[1], named[2]);
  if (state.screen === "workflow" && !state.workflows.writeReady) {
    control.disabled = true;
    control.title = "This workflow has not been read since the connection "
      + "came back, so nothing may be written to it yet.";
  }
  return control;
}

function tab(node, state, handlers) {
  const screen = node.getAttribute("data-screen");
  const current = screen === state.screen;
  node.setAttribute("aria-selected", String(current));
  node.tabIndex = current ? 0 : -1;
  if (node.dataset.wired === "yes") return;
  node.dataset.wired = "yes";
  const call = handlerOf(handlers, "onScreen");
  if (call === null) node.disabled = true;
  else node.addEventListener("click", () => call(screen));
}

/**
 * Write the shell chrome: header, tabs, the state word on every screen, and
 * the one status sentence.
 *
 * Safe to call repeatedly with the same state. The tab buttons are the ones
 * `studio.html` already carries -- they are wired once and updated after, so a
 * re-render never replaces the control a keyboard is standing on.
 *
 * @param {object} mounts the shell nodes, by the ids studio.html froze
 * @param {object} state the reducer's frozen value
 * @param {object} handlers `onScreen`, and the primary action of each screen
 */
export function mountShell(mounts, state, handlers) {
  // The heading names the PROJECT when the map gives one, because that is the
  // thing a person opened. It falls back to the workflow being worked on, and
  // then to the product's own name: `conduct init` writes a project name on
  // every road now, but a project scaffolded before it did carries none, and a
  // placeholder shown as a fact would be worse than the fallback.
  const workflow = chosenWorkflow(state);
  mounts.project.textContent = state.project.name !== null
    ? state.project.name
    : (workflow === null ? "Workflow Studio"
      : (workflow.title || workflow.workflow_id));
  mounts.connection.textContent = connectionSentence(state);
  mounts.connection.setAttribute("data-connection", state.connection);
  mounts.primary.replaceChildren(primaryAction(state, handlers));
  for (const node of rows(mounts.tabs)) tab(node, state, handlers);
  for (const [screen, screenMount] of Object.entries(mounts.screens)) {
    const phase = screenPhase(state, screen);
    screenMount.setAttribute("data-state", phase);
    screenMount.hidden = screen !== state.screen;
    mounts.states[screen].textContent = PHASE_SENTENCES[phase];
  }
  mounts.status.textContent = state.notice;
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
  return rows(state.runs.list)
    .filter((row) => row.unreadable !== true && typeof row.created_at === "string")
    .reduce((best, row) => best === null || row.created_at > best.created_at
      ? row : best, null);
}

function gatesWaiting(state) {
  return rows(state.decisions.list).filter((row) => row.decision === "idle");
}

//: What stops this project running, each row naming the payload it came from.
//: Nothing here is a severity this window invented: a row exists because a read
//: answered with it.
export function blockingRows(state) {
  const held = state.workflows;
  const found = [];
  for (const line of rows(held.problems)) {
    found.push({where: "workflow", screen: "workflow", text: line});
  }
  for (const row of rows(held.diagnostics)) {
    found.push({where: "workflow", screen: "workflow",
      text: `The saved draft does not yet construct a revision: ${row.message}`});
  }
  for (const row of rows(held.list).filter((entry) => entry.unreadable === true)) {
    found.push({where: "workflow", screen: "workflow",
      text: `Workflow ${row.workflow_id} has a revision this build cannot read.`});
  }
  for (const row of rows(state.runs.list).filter((entry) => entry.unreadable === true)) {
    found.push({where: "run", screen: "runs",
      text: `Run ${row.run_id} did not replay, so nothing derived from it can `
        + "be shown. It is listed rather than hidden."});
  }
  for (const [capability, steps] of unservedCapabilities(state)) {
    found.push({where: "agents", screen: "agents",
      text: `No available provider serves ${capability}, and ${steps.length} `
        + `step(s) of this workflow need it: ${steps.join(", ")}.`});
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
      why: "No workflow is chosen, so there is nothing to start."};
  }
  if (revision === null) {
    return {ready: false, channel: "wait",
      why: `${workflow.workflow_id} has no published revision yet. A run `
        + "follows a revision, so publish the draft first."};
  }
  if (!providers.length) {
    return {ready: false, channel: "fail",
      why: "No configured provider is available on this machine, so nothing "
        + "could carry a step out. The Agents screen says exactly what to write."};
  }
  return {ready: true, channel: "pass",
    why: `Revision ${revision} is published and ${providers.length} provider`
      + `${providers.length === 1 ? " is" : "s are"} available on this machine. `
      + "Which roles a run can bind is settled when it is opened."};
}

function whatThisIs(state, handlers) {
  const workflow = chosenWorkflow(state);
  const body = [
    element("p", {className: "studio-hint", text: state.project.name !== null
      ? `This is ${state.project.name}, the project this server was `
        + "started in. The name comes from conductor/map.toml."
      : "This project has no name yet: its conductor/map.toml carries none, "
        + "or still carries the placeholder a template ships with. Set "
        + "`project` there and restart to see it here."}),
  ];
  if (workflow === null) {
    body.push(note("No workflow is chosen. The Workflow screen lists every "
      + "one this project holds and can start a new one."),
    button(handlers, "onScreen", "Choose a workflow", "workflow"));
    return card("What this is", body);
  }
  body.push(fact("Workflow", workflow.workflow_id),
    fact("Name", workflow.title),
    fact("Published revisions", workflow.revisions),
    fact("Latest revision", workflow.latest_revision),
    fact("Unsaved draft on the server", workflow.has_draft ? "yes" : "no"),
    button(handlers, "onScreen", "Edit this workflow", "workflow"));
  if (state.workflows.provenance === "local") {
    body.push(note("The drawing on screen has changes this window is holding "
      + "and the server has not been given. Saving the draft is what stores "
      + "them."));
  }
  return card("What this is", body);
}

function readyCard(state) {
  const answer = readiness(state);
  return card("Ready to run?", [
    chip(answer.channel, answer.ready ? "ready to open a run" : "not yet"),
    note(answer.why),
  ]);
}

function blockedCard(state, handlers) {
  const found = blockingRows(state);
  if (!found.length) {
    return card("What is blocked", [
      note("Nothing read so far is blocking. That is a statement about what "
        + "has been read, not a promise about what has not."),
    ]);
  }
  const list = element("ul", {className: "studio-list"});
  for (const row of found.slice(0, 12)) {
    list.append(element("li", {className: "studio-row"}, [
      element("span", {text: row.text}),
      button(handlers, "onScreen", "Open it", row.screen),
    ]));
  }
  const body = [chip("fail", `${found.length} blocking`), list];
  if (found.length > 12) {
    body.push(note(`${found.length - 12} more are on the screens above.`));
  }
  return card("What is blocked", body);
}

function needsYouCard(state, handlers) {
  const waiting = gatesWaiting(state);
  if (!rows(state.decisions.list).length) {
    return card("What needs you", [
      note(state.runs.selectedId === null
        ? "No run is open here, so nothing is waiting on a person. Gates "
          + "appear once a run reaches one."
        : "This run's plan names no gate, so nothing in it waits for a person."),
    ]);
  }
  if (!waiting.length) {
    return card("What needs you", [chip("pass", "nothing waiting"),
      note("Every gate this run names has been answered. A decision is never "
        + "edited; answering again writes a receipt that supersedes it.")]);
  }
  const list = element("ul", {className: "studio-list"});
  for (const row of waiting) {
    list.append(element("li", {className: "studio-row"}, [
      element("span", {text: show(row.title)}),
      element("span", {className: "studio-mono",
        text: `${show(row.run_id)} · ${show(row.gate_id)}`}),
    ]));
  }
  return card("What needs you", [
    chip("wait", `${waiting.length} waiting for a decision`), list,
    button(handlers, "onScreen", "Open the decisions", "decisions"),
  ]);
}

function outcomeChannel(word) {
  if (word === "succeeded") return "pass";
  if (word === null || word === undefined) return "none";
  return RESULT_OUTCOMES.includes(word) ? "fail" : "none";
}

function latestRunCard(state, handlers) {
  const row = latestRun(state);
  if (row === null) {
    return card("The most recent run", [
      note(rows(state.runs.list).length
        ? "Every run this project holds is one whose journal did not replay, "
          + "so none of them can name a most recent."
        : "This project holds no run yet. Opening one from the Workflow "
          + "screen is what creates the first."),
      button(handlers, "onScreen", "Open the Runs screen", "runs"),
    ]);
  }
  const body = [
    fact("Run", row.run_id), fact("Opened at", row.created_at),
    fact("Authority (mode)", row.mode),
    fact("Opened as", row.envelope_status),
    note("Opened as is what the run was CREATED as. A run envelope is "
      + "immutable, so it never reports where the run now stands."),
    chip(outcomeChannel(row.last_outcome),
      `last outcome: ${show(row.last_outcome)}`),
  ];
  if (row.last_outcome === "verification_failed") body.push(note(VERIFICATION_NOTE));
  if (row.last_outcome === null) {
    body.push(note("No action of this run has recorded a result yet, which is "
      + "a different thing from a result that was bad."));
  }
  body.push(fact("Gates waiting", row.undecided_gates),
    fact("Actions still open", row.open_actions),
    button(handlers, "onSelectRun", "Read this run", row.run_id));
  return card("The most recent run", body);
}

/**
 * Draw the Overview: what this is, whether it can run, what is blocked, what
 * needs a person, and the most recent run -- each derived from a payload.
 *
 * @param {Element} mount the Overview body (`#bodyOverview`)
 * @param {object} state the reducer's frozen value
 * @param {object} handlers `onScreen`, `onSelectRun`
 */
export function mountOverview(mount, state, handlers) {
  mount.replaceChildren(
    whatThisIs(state, handlers), readyCard(state),
    blockedCard(state, handlers), needsYouCard(state, handlers),
    latestRunCard(state, handlers));
}

// -- the workflow toolbar -------------------------------------------------
function workflowPicker(state, handlers) {
  const choose = handlerOf(handlers, "onChooseWorkflow");
  const held = rows(state.workflows.list);
  const chosen = state.workflows.selectedId || "";
  // A workflow just STARTED is not in the server's list — nothing has been
  // saved under that id yet — so setting `value` to it matched no option and
  // the picker fell back to "choose a workflow". A person who had named a
  // workflow and seeded its drawing was told nothing was chosen, and only a
  // reload (after a save) fixed it. It gets an option of its own, saying what
  // it is, so the picker reports the state the rest of the screen is in.
  const unsaved = chosen && !held.some((row) => row.workflow_id === chosen)
    ? [option(chosen, `${chosen} — new, not saved yet`)] : [];
  const control = element("select", {"data-focus": "pick-workflow",
    name: "workflow"}, [option("", "choose a workflow")].concat(
    held.map((row) => option(row.workflow_id,
      `${row.workflow_id}${row.title === null ? "" : ` — ${row.title}`}`)),
    unsaved));
  control.value = chosen;
  if (choose === null) control.disabled = true;
  else control.addEventListener("change", () => choose(control.value || null));
  return field("Workflow", control);
}

//: What one starter is CALLED in the picker.
//:
//: Not its title. EVERY shipped starter is titled `Dalio five-step cycle`, so
//: a list of titles offered rows a person could not tell apart and could
//: not choose between — and they are not equivalent: one ships four review
//: steps that cannot succeed. The revision separates them and the caveat says
//: which one to avoid, both derived by the route from the documents themselves.
function starterLabel(row) {
  const named = `${row.title} · revision ${row.revision}`;
  return rows(row.caveats).length === 0
    ? `${named} — ready to run`
    : `${named} — ${row.caveats[0]}`;
}

//: Starting a workflow is TWO facts: the id it will live under, and the
//: document it starts from. Neither is guessed: a blank start is an empty
//: drawing, and every other offer is a document this BUILD ships.
function starterControls(state, handlers) {
  const box = element("div", {className: "studio-field"});
  const name = element("input", {autocomplete: "off",
    "data-focus": "new-workflow", maxlength: "128", name: "new-workflow",
    pattern: ID_PATTERN, spellcheck: "false", type: "text"});
  const from = element("select", {"data-focus": "new-from", name: "new-from"},
    [option("", "start blank")].concat(rows(state.workflows.starters).map(
      (row) => option(row.starter_id, starterLabel(row)))));
  const start = handlerOf(handlers, "onStartWorkflow");
  const go = element("button", {className: "studio-btn",
    "data-focus": "action:onStartWorkflow", text: "Start a workflow",
    type: "button"});
  if (start === null) {
    go.disabled = true;
    go.title = "This screen was mounted without an onStartWorkflow handler.";
  } else {
    go.addEventListener("click", () => start(
      {workflowId: name.value.trim(), starterId: from.value || null}));
  }
  box.append(field("New workflow id", name), field("Start from", from), go);
  return box;
}

function saveControls(state, handlers) {
  const held = state.workflows;
  const box = element("div", {className: "studio-field"});
  const save = button(handlers, "onSaveDraft", "Save draft", null);
  const publish = button(handlers, "onPublish",
    held.nextRevision === null ? "Publish revision"
      : `Publish revision ${held.nextRevision}`, null);
  const check = button(handlers, "onValidate", "Validate", null);
  //: The road out of a published revision, named once so the control and the
  //: sentence beside it cannot drift apart, and shut with a reason -- never a
  //: bare grey button -- whenever pressing it would do nothing.
  const NEW_DRAFT = "Edit as new draft";
  const shut = held.draft !== null
    ? "There is already a drawing on screen; edit it and save the draft."
    : (object(held.detail) === null || object(held.detail.published) === null
      ? "This workflow has no published revision to copy."
      : (held.writeReady ? null
        : "This workflow has not been read since the connection came back."));
  const fresh = button(handlers, "onEditPublished", NEW_DRAFT, null,
    {disabled: shut === null ? null : "", title: shut});
  if (!held.writeReady || held.draft === null
      || held.savePhase === "submitting") {
    save.disabled = true;
    save.title = held.draft !== null
      ? "This workflow has not been read since the connection came back."
      : shut !== null ? "There is no drawing to save."
        : `There is no drawing to save. ${NEW_DRAFT} copies the published `
          + "revision into one you can change.";
  }
  if (!held.writeReady || !held.publishable) {
    publish.disabled = true;
    publish.title = held.unchanged
      ? "This draft is the revision already published, word for word. "
        + "Publishing it would record an edit that never happened."
      : (held.publishable
        ? "This workflow has not been read since the connection came back."
        : "Publishing needs a SAVED draft the server says would construct a "
          + "revision. Save the drawing first, then read what stops it.");
  }
  box.append(check, save, publish, fresh);
  if (held.reviewing) box.append(publishReview(state, handlers));
  return box;
}

//: One line per KIND of change, and the ids under it. A person about to create
//: an immutable revision is answering "is this what I meant", and a count with
//: no names cannot be checked against what they remember doing.
function changeLines(changes) {
  const lines = [];
  if (changes === null) return lines;
  if (changes.first) {
    lines.push(`Creates the workflow "${changes.title.to}"`);
  } else if (changes.title !== null) {
    lines.push(`Title: "${changes.title.from}" becomes "${changes.title.to}"`);
  }
  const named = [["Steps added", changes.added],
                 ["Steps removed", changes.removed],
                 ["Steps changed", changes.changed],
                 ["Connections added", changes.edgesAdded],
                 ["Connections removed", changes.edgesRemoved]];
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
  const lines = changeLines(held.changes);
  const box = element("div", {className: "studio-review",
    "data-review": "publish"});
  box.append(element("h3", {text: `Publish revision ${held.nextRevision}?`}));
  box.append(element("p", {className: "studio-hint", text:
    "A revision is immutable. Once written it stands, and later edits become "
    + "further revisions rather than changing this one."}));
  box.append(element("p", {className: "studio-fact__v", text:
    held.diagnostics.length === 0
      ? "Validation: the server says this draft would construct a revision."
      : "Validation: the server refuses this draft."}));
  if (held.changes !== null && held.changes.first) {
    box.append(element("p", {className: "studio-hint", text:
      "This is the first revision, so there is nothing to compare it against. "
      + "What it creates is listed in full."}));
  }
  if (held.changes === null) {
    box.append(element("p", {className: "studio-hint", text:
      "There is no drawing to review."}));
  } else if (lines.length === 0) {
    box.append(element("p", {className: "studio-hint", text:
      "No structural change was found between this drawing and the revision "
      + "now standing."}));
  } else {
    box.append(element("ul", {className: "studio-review__changes"},
      lines.map((line) => element("li", {text: line}))));
  }
  box.append(button(handlers, "onPublishConfirm",
    `Confirm and publish revision ${held.nextRevision}`, null));
  box.append(button(handlers, "onPublishCancel", "Cancel", null));
  return box;
}

function saveLine(state) {
  const held = state.workflows;
  const said = element("p", {className: "studio-state",
    "data-save": held.savePhase, text: held.saveNotice});
  return said;
}

/**
 * Draw the workflow toolbar: which workflow, how to start one, the two write
 * doors and the form that opens a run.
 *
 * The run form itself is `studio-runform.js`'s: it is the only part of this
 * toolbar that starts something running rather than describing the document,
 * and it left here when this file reached the line cap.
 *
 * @param {Element} mount `#workflowToolbar`
 * @param {object} state the reducer's frozen value
 * @param {object} handlers `onChooseWorkflow`, `onStartWorkflow`, `onValidate`,
 *   `onSaveDraft`, `onPublish`, `onEditPublished`, `onOpenRun`
 */
export function mountToolbar(mount, state, handlers) {
  mount.replaceChildren(workflowPicker(state, handlers),
    starterControls(state, handlers), saveControls(state, handlers),
    saveLine(state), runForm(state, handlers));
}

// -- the diagnostics panel ------------------------------------------------
function diagList(title, said, lines, code) {
  const box = element("div", {className: "studio-section"});
  box.append(element("h4", {text: title}), note(said));
  if (!lines.length) {
    box.append(element("p", {className: "studio-hint",
      text: "Nothing here stops it."}));
    return box;
  }
  const list = element("ul", {className: "studio-list"});
  for (const line of lines) {
    list.append(element("li", {className: "studio-diag"}, [
      element("span", {className: "studio-diag__code", text: code}),
      element("span", {text: line}),
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
  mount.replaceChildren(element("h3", {text: "What stops publishing"}));
  mount.append(
    diagList("The drawing on screen",
      "What this window can already see the save route would refuse. It is "
      + "about the UNSAVED drawing and nothing has been sent.",
      rows(held.problems), "local"),
    diagList("The draft on the server",
      held.savedAt === null
        ? "No draft is stored for this workflow yet."
        : `The server's own answer about the draft it stored at ${held.savedAt}.`,
      rows(held.diagnostics).map((row) => row.message), "server"));
  if (held.publishable) {
    mount.append(element("p", {className: "studio-hint",
      text: `Nothing stops publishing revision ${show(held.nextRevision)}.`}));
  }
}

//: The id grammar, exported so the transport module refuses the same spellings
//: these controls advertise rather than a second opinion about them.
export function isId(value) {
  return typeof value === "string" && ID_RE.test(value);
}
