"use strict";
// The Runs screen: every run this project holds, one run read whole, and the
// journal that run actually wrote. Every node here is built from text; no
// markup string is ever parsed, nothing is fetched, and no clock is read.
//
// Three honesty rules govern this file, and each of them exists because the
// backend already refuses to pretend:
//
//  1. `envelope_status` is a CREATION-TIME word. A `RunEnvelope` is immutable,
//     so its status says what the run was OPENED as and never where it now
//     stands -- which is why the wire spells it with `envelope_` in front. It
//     is rendered as "opened as", never as a live position, and nothing on
//     this screen derives a run-wide phase word: the journal does not carry
//     one, and a word invented here is a guess a reader would trust.
//  2. A run whose journal does not replay arrives with `unreadable: true` and
//     every derived field null. It is DRAWN, with the marker and with what the
//     operator can do about it -- a run you cannot see is worse than one you
//     cannot read.
//  3. `pass` counts attempts on the ONE node a loop reopens and `bound` is the
//     greatest pass, so "pass N of B" is two facts about the same scale. The
//     position comes from the runtime projection and the ceiling from the
//     definition; neither is computed from the other.
//
// The timeline is the journal in append order and nothing else. It never
// invents a step and never skips one: it walks `records`, names the durable
// `record_type` every row came from, and a kind this build does not know is
// shown BY NAME rather than dropped.
import {element} from "./command-view.js";

// -- closed vocabularies, each a copy of exactly one Python owner ------------
//
// Held equal to their owners by tests/test_studio_runs.py, which reads this
// source and the Python module side by side. A word added on either side and
// not the other reds that module.

//: graph_projection.NODE_PHASES -- how far a node's CURRENT action got. Read
//: `observed` as "a boundary was reached", never as success: the outcome is a
//: separate word from a separate record (safety law 9).
export const NODE_PHASES = Object.freeze(
  ["idle", "proposed", "requested", "running", "observed"]);
//: graph_projection.GATE_STATES. `unknown` is the projection refusing to
//: choose between two standing receipts, not a soft pending.
export const GATE_STATES = Object.freeze(
  ["idle", "satisfied", "failed", "changes_requested", "waived", "unknown"]);
//: contract_values._RESULT_OUTCOMES -- what an ActionResultReceipt may say.
export const RESULT_OUTCOMES = Object.freeze(
  ["cancelled", "failed", "rejected", "succeeded", "unknown",
    "verification_failed"]);
//: contract_values._VERIFICATION_STATES -- what an EvidenceRef may say.
export const VERIFICATION_STATES = Object.freeze(
  ["error", "mismatch", "unavailable", "unverified", "verified"]);
//: contract_values._RUN_STATES -- the words a RunEnvelope's status may hold.
export const RUN_STATES = Object.freeze(
  ["active", "blocked", "cancelled", "complete", "created", "failed",
    "paused", "unknown"]);
//: attempts.ATTEMPT_PHASES -- the two durable boundaries of one attempt.
export const ATTEMPT_PHASES = Object.freeze(
  ["effect_lease", "execution_observed"]);
//: run_store._RECORDS -- every record kind a run directory may hold, with the
//: plain-language name this screen puts beside the protocol word. The keys are
//: the contract; the values are prose and are never parsed.
export const RECORD_KINDS = Object.freeze({
  action_proposal: "A lane proposed an action",
  action_request: "A Human authorized one request",
  action_result: "A result was observed",
  adapter_observation: "An adapter reported its health",
  artifact: "An artifact was written",
  attempt_event: "An attempt crossed a durable boundary",
  decision: "A Human answered a gate",
  evidence: "Evidence was claimed",
  graph_definition: "The run was given its plan",
});
//: contract_values.ControlMode -- the whole authority ladder, and what each
//: rung PERMITS. There is no hidden autonomous rung.
export const CONTROL_MODES = Object.freeze({
  observe: "Reads and reports. Nothing is proposed and nothing runs.",
  propose: "May propose work. Nothing runs without a Human authorizing it.",
  confirm: "A Human confirms each proposal, and only then may it run.",
  policy: "A written policy authorizes requests instead of a Human.",
});
//: The five steps of the real progression, in the one order they can happen.
//: The first, second and fifth are record kinds; the third and fourth are the
//: two phases of an `attempt_event`. Nothing here decides that a step is
//: MISSING -- a step is named only when a record carries it.
export const TIMELINE_STEPS = Object.freeze([
  "action_proposal", "action_request", "effect_lease", "execution_observed",
  "action_result"]);
//: Which field carries a record's instant. A kind absent from this map states
//: no instant this build knows, and is said so rather than stamped with one.
const INSTANT_FIELDS = Object.freeze({
  action_proposal: "proposed_at", action_request: "requested_at",
  action_result: "observed_at", adapter_observation: "observed_at",
  artifact: "created_at", attempt_event: "recorded_at",
  decision: "decided_at", evidence: "observed_at",
  graph_definition: "created_at",
});
//: The identity fields each kind is summarised by, in reading order. Payload
//: bodies (`arguments`, `content`) are deliberately absent: a timeline row is
//: an index into the journal, never a second copy of it.
const ROW_FACTS = Object.freeze({
  action_proposal: ["proposal_id", "attempt_id", "node_id", "instance_id",
    "capability", "proposed_by"],
  action_request: ["action_id", "attempt_id", "node_id", "instance_id",
    "capability", "mode", "requested_by"],
  action_result: ["receipt_id", "action_id", "attempt_id", "instance_id",
    "outcome", "exit_code", "detail", "evidence_refs"],
  adapter_observation: ["observation_id", "adapter_id", "instance_id",
    "health", "available_capabilities", "detail"],
  artifact: ["artifact_id", "artifact_ref", "media_type", "source_action_id",
    "input_artifact_ids"],
  attempt_event: ["event_id", "action_id", "attempt_id", "instance_id",
    "adapter_id", "phase", "outcome", "exit_code"],
  decision: ["receipt_id", "gate_id", "action", "actor", "reason",
    "supersedes"],
  evidence: ["evidence_id", "kind", "label", "uri", "verification",
    "verified_by", "verified_at"],
  graph_definition: ["graph_id", "schema_version"],
});
//: Status is its own channel and never the only carrier: every chip below
//: draws a glyph and a word as well.
const OUTCOME_CHANNEL = Object.freeze({
  succeeded: "pass", failed: "fail", cancelled: "none", rejected: "fail",
  verification_failed: "fail", unknown: "none",
});
const PHASE_CHANNEL = Object.freeze({
  idle: "none", proposed: "wait", requested: "wait", running: "wait",
  observed: "wait",
});
const GATE_CHANNEL = Object.freeze({
  idle: "wait", satisfied: "pass", failed: "fail",
  changes_requested: "wait", waived: "none", unknown: "wait",
});
const VERIFICATION_CHANNEL = Object.freeze({
  verified: "pass", unverified: "wait", unavailable: "none",
  mismatch: "fail", error: "fail",
});
const CHANNEL_GLYPHS = Object.freeze({
  pass: "✓", wait: "●", fail: "✕", none: "·",
});
//: The one sentence `verification_failed` must never appear without. The
//: protocol word travels beside it, never instead of it.
export const VERIFICATION_FAILED_NOTE = "Process exit 0 proves the process "
  + "finished, not that the work was verified. This run reached the end of an "
  + "action and its verification did not pass, so nothing here says the work "
  + "is done.";
//: The seven words a screen container may stand in, and the plain sentence
//: each one is said with.
export const PHASE_SENTENCES = Object.freeze({
  empty: "Nothing has been read yet.",
  loading: "Reading this project's runs.",
  ready: "Read.",
  stale: "Shown from an earlier read; a newer one has not landed.",
  refused: "This read was refused. Nothing below is newer than the refusal.",
  failed: "This read failed. Nothing below is newer than the failure.",
  disconnected: "The live connection is down, so nothing here updates.",
});

const NOT_STATED = "not stated";

function show(value) {
  if (value === null || value === undefined || value === "") return NOT_STATED;
  if (Array.isArray(value)) return value.length ? value.join(", ") : NOT_STATED;
  return String(value);
}

function chip(channel, word) {
  const known = CHANNEL_GLYPHS[channel] ? channel : "none";
  return element("span", {className: `studio-chip studio-chip--${known}`}, [
    element("i", {className: "studio-chip__g", text: CHANNEL_GLYPHS[known]}),
    element("span", {text: word}),
  ]);
}

function fact(label, value) {
  return element("p", {className: "studio-fact"}, [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v", text: show(value)}),
  ]);
}

function note(value) {
  return element("p", {className: "studio-note", text: value});
}

function protocolWord(value) {
  return element("span", {className: "studio-mono", text: value});
}

function section(title, children) {
  return element("section", {className: "studio-section"},
    [element("h3", {text: title}), ...children]);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

//: A control whose handler was not wired is DISABLED and says why. It never
//: disappears: a button that vanishes teaches a user the product cannot do the
//: thing, when what happened is that this screen was mounted without its wire.
function actionButton(handlers, name, label, run) {
  const call = handlerOf(handlers, name);
  const button = element("button", {
    "data-focus-key": `action:${name}`, text: label, type: "button",
  });
  if (call === null) {
    button.disabled = true;
    button.title = `This screen was mounted without a ${name} handler.`;
    return button;
  }
  button.addEventListener("click", () => call(run));
  return button;
}

function banner(phase) {
  const word = PHASE_SENTENCES[phase] ? phase : "failed";
  return element("p", {className: `studio-banner studio-banner--${word}`}, [
    element("span", {text: PHASE_SENTENCES[word]}), " ", protocolWord(word),
  ]);
}

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

// -- the list -----------------------------------------------------------------

//: The plan a run froze itself to follow, as one phrase for a list row.
//:
//: Both halves or neither: `workflow_id` and `revision` are written together by
//: the route and are null together for a run opened without a workflow, so a
//: row showing an id with no revision would be describing a state the store
//: cannot produce. The revision is the half that matters — two runs of one
//: workflow at two revisions are two different plans.
function followed(row) {
  if (typeof row.workflow_id !== "string"
      || !Number.isInteger(row.revision)) {
    return "no workflow";
  }
  return `${row.workflow_id} rev ${row.revision}`;
}

function runSummary(row) {
  if (row.unreadable === true) {
    return [chip("fail", "unreadable"),
      element("span", {className: "studio-run__meta",
        text: "this journal did not replay"})];
  }
  const waiting = row.undecided_gates;
  // WHICH plan this run froze itself to follow, first, because it is the
  // question a list of runs is usually being scanned for. The detail below has
  // always shown it and the row payload has always carried it -- the row simply
  // did not render it, so telling two runs of two workflows apart meant opening
  // both. A run that follows no workflow says so rather than showing a gap.
  const parts = [followed(row),
    `opened as ${show(row.envelope_status)}`,
    `mode ${show(row.mode)}`,
    `${show(waiting)} gate(s) waiting`,
    `${show(row.open_actions)} action(s) open`];
  const carried = [element("span", {className: "studio-run__meta",
    text: parts.join(" · ")})];
  if (typeof row.last_outcome === "string") {
    carried.unshift(chip(OUTCOME_CHANNEL[row.last_outcome] || "none",
      row.last_outcome));
  }
  return carried;
}

function runButton(row, selectedId, handlers) {
  const runId = show(row.run_id);
  const button = element("button", {
    "aria-pressed": runId === selectedId ? "true" : "false",
    className: "studio-run", "data-focus-key": `run:${runId}`, type: "button",
  }, [element("span", {className: "studio-run__id", text: runId}),
    ...runSummary(row)]);
  const select = handlerOf(handlers, "selectRun");
  if (select === null) {
    button.disabled = true;
    button.title = "This screen was mounted without a selectRun handler.";
  } else button.addEventListener("click", () => select(row.run_id));
  return button;
}

//: One row of the list, and the sentence its outcome word may never be shown
//: without. The list is the FIRST place a reader meets that word -- before
//: they have chosen anything to read -- so it is the place the rule matters
//: most. The sentence is the one exported constant the detail already draws:
//: there is a single copy of it in this file and it cannot drift from itself.
//:
//: It stands in the row BESIDE the button rather than inside it. A button's
//: accessible name is the words it contains and a paragraph is not phrasing
//: content, so a sentence put inside the control would be invalid markup and
//: a name too long to be spoken as one.
function runRow(row, selectedId, handlers) {
  const item = element("li", {}, [runButton(row, selectedId, handlers)]);
  if (row.last_outcome === "verification_failed") {
    item.append(note(VERIFICATION_FAILED_NOTE));
  }
  return item;
}

function runList(state, handlers) {
  const list = rows(state.list);
  const body = [banner(state.phase),
    actionButton(handlers, "refreshRuns", "Read runs again", null)];
  if (!list.length) {
    body.push(note("This project holds no runs yet. Opening one from the "
      + "Workflow screen is what creates the first."));
  } else {
    const items = element("ul", {className: "studio-runs__rows"});
    for (const row of list) items.append(runRow(row, state.selectedId, handlers));
    body.push(items);
  }
  return element("nav", {className: "studio-runs__list",
    "aria-label": "Runs"}, body);
}

// -- one run ------------------------------------------------------------------

function identitySection(detail, handlers) {
  const run = object(detail.run) || {};
  // The frozen configuration owns this fact; the boundary already refused the
  // read if the reference was there and malformed, so `null` here means the
  // run genuinely froze none.
  const followed = (object(detail.config) || {}).workflow || null;
  const mode = show(run.mode);
  const body = [
    fact("Run", run.run_id), fact("Cycle", run.cycle_id),
    fact("Opened at", run.created_at),
    fact("Authority (mode)", mode),
    note(CONTROL_MODES[mode] || "This build does not describe that mode."),
    fact("Opened as", run.status),
    note("Opened as is what the run was CREATED as. A run envelope is "
      + "immutable, so it never reports where the run now stands — the "
      + "records below do that."),
    fact("Configuration digest", run.config_digest),
    // Read out of the run's own frozen configuration, which is the document
    // `config_digest` above is taken over -- so the two facts on this screen
    // stand or fall together, and a run that froze no workflow says so in
    // words rather than showing a plausible one.
    fact("Workflow", followed === null
      ? "none — this run was opened without one"
      : followed.id),
    fact("Revision", followed === null
      ? "none — a run that follows no workflow follows no revision"
      : `revision ${followed.revision}`),
    note(followed === null
      ? "A run may be opened with no workflow at all; `conduct preview` and "
        + "the integration smoke both are. Nothing was lost."
      : "Frozen when the run was opened. Publishing a later revision of this "
        + "workflow does not move it: a run follows the plan it started with."),
  ];
  const warnings = rows(detail.warnings);
  if (warnings.length) {
    body.push(element("ul", {className: "studio-warnings"},
      warnings.map((line) => element("li", {text: show(line)}))));
  }
  body.push(actionButton(handlers, "showDecisions", "Open the decisions here",
    run.run_id));
  return section("This run", body);
}

//: The frozen binding, joined to what this build can serve. The binding comes
//: from the run's own configuration snapshot; the capability list comes from
//: the controls read and is joined BY IDENTITY, never by a displayed label.
function assignmentSection(detail) {
  const config = object(detail.config) || {};
  const bound = rows(config.instances);
  const controls = object(detail.controls);
  const declared = new Map(rows(controls && controls.instances)
    .map((row) => [row.instance_id, row]));
  if (!bound.length) {
    return section("Assigned to", [note("This run's frozen configuration "
      + "binds no instance, so no adapter carries any step of it.")]);
  }
  const list = element("ul", {className: "studio-bindings"});
  for (const row of bound) {
    const joined = declared.get(row.id);
    const item = element("li", {className: "studio-binding"}, [
      element("span", {className: "studio-mono", text: show(row.id)}),
      fact("Harness (adapter)", row.adapter),
      fact("Model", Object.prototype.hasOwnProperty.call(row, "model")
        ? row.model : null),
    ]);
    if (!Object.prototype.hasOwnProperty.call(row, "model")) {
      item.append(note("This build pinned no model for this instance, so "
        + "whatever the provider's own configuration decides is what runs."));
    }
    item.append(joined
      ? fact("Capabilities this build can serve", joined.controls)
      : note("This run's controls read has not landed here, so what this "
        + "binding can be asked to do is not stated."));
    list.append(item);
  }
  return section("Assigned to", [list]);
}

function planSection(detail) {
  const graph = object(detail.graph);
  if (graph === null || graph.definition === null
      || graph.definition === undefined) {
    return section("Plan", [note("This run follows no plan. Its actions are "
      + "not bound to any step, so there is no position to report.")]);
  }
  const definition = object(graph.definition) || {};
  return section("Plan", [
    fact("Plan", definition.graph_id),
    fact("Digest", graph.definition_digest),
    fact("Steps", rows(definition.nodes).length),
    note("A plan is written once and never edited. Editing the workflow it "
      + "came from makes a new revision and leaves this one exactly as it "
      + "was."),
  ]);
}

function loopLine(node, runtime) {
  const loop = object(node.loop);
  if (loop === null) return null;
  const at = typeof runtime.pass === "number"
    ? `pass ${runtime.pass} of ${loop.bound}`
    : `at most ${show(loop.bound)} passes`;
  const reached = runtime.bound_reached === true
    ? " · no pass left" : "";
  return element("p", {className: "studio-mono studio-loop",
    text: `bounded loop · ${at} · reopens ${show(loop.back_to)}`
      + reached});
}

function positionRow(node, runtime) {
  const item = element("li", {className: "studio-position"}, [
    element("span", {className: "studio-position__t", text: show(node.title)}),
    element("span", {className: "studio-mono",
      text: `${show(node.node_id)} · ${show(node.kind)}`}),
    chip(PHASE_CHANNEL[runtime.phase] || "none", show(runtime.phase)),
  ]);
  if (typeof runtime.outcome === "string") {
    item.append(chip(OUTCOME_CHANNEL[runtime.outcome] || "none",
      runtime.outcome));
  }
  if (typeof runtime.decision === "string") {
    item.append(chip(GATE_CHANNEL[runtime.decision] || "none",
      `gate ${runtime.decision}`));
  }
  item.append(fact("Observed at", runtime.observed_at),
    fact("Attempts", rows(runtime.attempt_ids).length),
    fact("Evidence", runtime.evidence_refs));
  const loop = loopLine(node, runtime);
  if (loop !== null) item.append(loop);
  if (runtime.outcome === "verification_failed") {
    item.append(note(VERIFICATION_FAILED_NOTE));
  }
  return item;
}

//: Where each step stands, from the runtime projection joined to the plan by
//: `node_id` -- the one name the two documents share. There is deliberately no
//: run-wide phase word: the journal carries none.
function positionSection(detail) {
  const graph = object(detail.graph);
  const runtime = graph ? object(graph.runtime) : null;
  if (runtime === null) {
    return section("Where this run stands", [note("This run follows no plan, "
      + "so there is nothing to stand on. Its journal is below.")]);
  }
  const definition = object(graph.definition) || {};
  const planned = new Map(rows(definition.nodes)
    .map((node) => [node.node_id, node]));
  const list = element("ul", {className: "studio-positions"});
  for (const row of rows(runtime.nodes)) {
    list.append(positionRow(planned.get(row.node_id) || {}, row));
  }
  return section("Where this run stands", [
    note("Each step reports its CURRENT action only. Observed says an "
      + "execution boundary was reached — the outcome beside it is what "
      + "came of it, and the two are never the same fact."),
    list]);
}

function evidenceItem(record) {
  return element("li", {className: "studio-evidence"}, [
    element("span", {className: "studio-mono",
      text: `${show(record.kind)} ${show(record.evidence_id)}`}),
    element("span", {text: show(record.label)}),
    chip(VERIFICATION_CHANNEL[record.verification] || "none",
      show(record.verification)),
    fact("Where", record.uri),
  ]);
}

function outcomeSection(records) {
  const results = records.filter((row) => row.record_type === "action_result");
  const evidence = records.filter((row) => row.record_type === "evidence");
  const body = [];
  if (!results.length) {
    body.push(note("No result has been observed for this run."));
  } else {
    const last = object(results[results.length - 1].record) || {};
    body.push(fact("Last outcome", last.outcome),
      chip(OUTCOME_CHANNEL[last.outcome] || "none", show(last.outcome)),
      fact("Exit code", last.exit_code),
      fact("Detail recorded by the code", last.detail),
      fact("Action", last.action_id));
    if (last.outcome === "verification_failed") {
      body.push(note(VERIFICATION_FAILED_NOTE));
    }
  }
  if (!evidence.length) {
    body.push(note("This run claims no evidence, so nothing about it has "
      + "been verified."));
  } else {
    body.push(element("ul", {className: "studio-evidences"},
      evidence.map((row) => evidenceItem(object(row.record) || {}))));
  }
  return section("Outcome and verification", body);
}

function artifactSection(records) {
  const written = records.filter((row) => row.record_type === "artifact");
  if (!written.length) {
    return section("Artifacts", [note("This run wrote no artifact.")]);
  }
  const list = element("ul", {className: "studio-artifacts"});
  for (const row of written) {
    const record = object(row.record) || {};
    list.append(element("li", {className: "studio-artifact"}, [
      element("span", {className: "studio-mono", text: show(record.artifact_id)}),
      fact("Handoff name", record.artifact_ref),
      fact("Media type", record.media_type),
      fact("Written at", record.created_at),
      fact("From action", record.source_action_id),
      fact("Built on", record.input_artifact_ids),
      fact("Characters", typeof record.content === "string"
        ? record.content.length : null),
    ]));
  }
  return section("Artifacts", [list]);
}

// -- the timeline -------------------------------------------------------------

//: Which of the five progression steps a row IS, or null. An `attempt_event`
//: answers with its own phase; every other kind answers with its own name.
//: Nothing here decides a step is missing.
function stepOf(kind, record) {
  if (kind !== "attempt_event") {
    return TIMELINE_STEPS.includes(kind) ? kind : null;
  }
  const phase = record ? record.phase : null;
  return ATTEMPT_PHASES.includes(phase) ? phase : null;
}

function timelineFacts(kind, record) {
  const names = ROW_FACTS[kind];
  const carried = element("div", {className: "studio-row__facts"});
  if (!names) {
    carried.append(note("This build does not know this record kind. It is "
      + "shown by the name the journal gave it and is not interpreted."));
    return carried;
  }
  for (const name of names) {
    if (!Object.prototype.hasOwnProperty.call(record, name)) continue;
    carried.append(fact(name, record[name]));
  }
  return carried;
}

function timelineChip(kind, record) {
  if (kind === "action_result" || kind === "attempt_event") {
    if (typeof record.outcome !== "string") return null;
    return chip(OUTCOME_CHANNEL[record.outcome] || "none", record.outcome);
  }
  if (kind === "evidence" && typeof record.verification === "string") {
    return chip(VERIFICATION_CHANNEL[record.verification] || "none",
      record.verification);
  }
  if (kind === "decision" && typeof record.action === "string") {
    return chip("wait", record.action);
  }
  return null;
}

function timelineRow(wrapper, index) {
  const kind = show(wrapper.record_type);
  const record = object(wrapper.record) || {};
  const instantField = INSTANT_FIELDS[kind];
  const step = stepOf(kind, record);
  const head = element("p", {className: "studio-row__head"}, [
    element("span", {className: "studio-row__n", text: `${index + 1}`}),
    element("span", {text: RECORD_KINDS[kind] || "An unknown record kind"}),
    protocolWord(kind),
  ]);
  if (step !== null) head.append(protocolWord(`step: ${step}`));
  head.append(element("span", {className: "studio-row__at",
    text: instantField ? show(record[instantField])
      : "no instant this build knows"}));
  const badge = timelineChip(kind, record);
  if (badge !== null) head.append(badge);
  const item = element("li", {className: "studio-row"},
    [head, timelineFacts(kind, record)]);
  if (record.outcome === "verification_failed") {
    item.append(note(VERIFICATION_FAILED_NOTE));
  }
  return item;
}

function timelineSection(records) {
  if (!records.length) {
    return section("Timeline", [note("This run's journal is empty: nothing "
      + "has been proposed, authorized, attempted or decided.")]);
  }
  const list = element("ol", {className: "studio-timeline"});
  records.forEach((wrapper, index) => list.append(timelineRow(wrapper, index)));
  return section("Timeline", [
    note("Every row is one durable record, in the order the run appended it, "
      + "named by the record it came from. A step that is not here was never "
      + "written."),
    list]);
}

// -- the detail column --------------------------------------------------------

function unreadableDetail(row) {
  return element("div", {className: "studio-runs__detail"}, [
    element("h2", {text: show(row.run_id)}),
    chip("fail", "unreadable"),
    note("This run's journal did not replay, so nothing derived from it can "
      + "be shown. It is listed rather than hidden."),
    fact("Where it lives", `conductor/runs/${show(row.run_id)}/`),
    note("What you can do: read that directory, keep it, and report it. "
      + "Nothing in this screen repairs a run — listing and reading are "
      + "both read-only, by design, so a damaged journal is never rewritten "
      + "underneath you."),
  ]);
}

function selectedRow(state) {
  return rows(state.list).find((row) => row.run_id === state.selectedId) || null;
}

function detailColumn(state, handlers) {
  const row = selectedRow(state);
  if (row !== null && row.unreadable === true) return unreadableDetail(row);
  const detail = object(state.detail);
  if (detail === null) {
    return element("div", {className: "studio-runs__detail"}, [
      note(state.selectedId
        ? "This run has been chosen and its read has not landed here yet."
        : "Choose a run on the left to read it whole.")]);
  }
  const records = rows(detail.records);
  return element("div", {className: "studio-runs__detail"}, [
    element("h2", {text: show((object(detail.run) || {}).run_id)}),
    identitySection(detail, handlers),
    assignmentSection(detail),
    planSection(detail),
    positionSection(detail),
    outcomeSection(records),
    artifactSection(records),
    timelineSection(records),
  ]);
}

// -- the mount ----------------------------------------------------------------

function focusKey(mount) {
  const active = document.activeElement;
  if (!active || active === document.body) return null;
  if (!mount.contains(active) || !active.getAttribute) return null;
  return active.getAttribute("data-focus-key");
}

function restoreFocus(mount, key) {
  if (!key) return;
  const successor = mount.querySelector(`[data-focus-key="${key}"]`);
  if (successor) successor.focus();
}

/**
 * Draw the Runs screen: every run, the one chosen, and its durable journal.
 *
 * Safe to call repeatedly with the same state: the whole subtree is replaced
 * each pass and focus intent is carried across it, so a keyboard Human is
 * never dropped to the top of the document by a re-render they did not ask
 * for.
 *
 * @param {Element} mount The screen container this module owns entirely.
 * @param {object} state The reducer's frozen value.
 * @param {object} handlers Callbacks this module invokes and never defines:
 *   `selectRun(runId)`, `refreshRuns()`, `showDecisions(runId)`.
 */
export function mountRuns(mount, state, handlers) {
  const key = focusKey(mount);
  const runs = object(state && state.runs) || {};
  mount.replaceChildren(element("div", {className: "studio-runs"}, [
    element("h2", {text: "Runs"}),
    element("p", {className: "studio-lede", text:
      "A run is one execution: an immutable envelope, the configuration it "
      + "was frozen against, and the journal it wrote. Everything below is "
      + "read out of that journal and nothing is stored twice."}),
    runList(runs, handlers),
    detailColumn(runs, handlers),
  ]));
  restoreFocus(mount, key);
}
