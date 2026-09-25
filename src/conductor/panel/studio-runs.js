"use strict";
import {localize} from "./studio-i18n.js";
// The Runs screen: every run this project holds, one run read whole, and the
// journal that run actually wrote. Every node here is built from text; no
// markup string is ever parsed, nothing is fetched, and no clock is read.
//
// Three honesty rules:
//  1. `envelope_status` is a CREATION-TIME word: the immutable RunEnvelope
//     says what the run was "opened as", not its current position. Current
//     progress is read from the journal and the server's projections.
//  2. An `unreadable: true` run is drawn with its marker and recovery road;
//     its null derived facts are not converted into a guessed outcome.
//  3. `pass` counts attempts on the ONE node a loop reopens; `bound` is the
//     greatest pass. The position and ceiling come from separate owners,
//     so "pass N of B" compares facts on the same scale, not guesses.
//
// The timeline walks every `records` row in append order. Unknown durable
// kinds are shown by name, never dropped or replaced with invented steps.
import {element} from "./command-view.js";
import {projectTaskBinding} from "./command-projection.js";
//: The closed vocabularies and the one-voice sentence, re-exported under the
//: names they have always had. See `studio-runwords.js` for why they moved and
//: why that module imports nothing.
export {
  ALL_ROADS,
  ATTEMPT_PHASES,
  CONTROL_MODES,
  GATE_STATES,
  NODE_PHASES,
  RECORD_KINDS,
  RESULT_OUTCOMES,
  RUN_STATES,
  TIMELINE_STEPS,
  VERIFICATION_FAILED_NOTE,
  VERIFICATION_STATES,
} from "./studio-runwords.js";
//: What this file's own rendering reads. The `export` above is the public
//: surface; this is the working set, and the two lists are separate because a
//: name can be one without being the other.
import {
  ALL_ROADS,
  ATTEMPT_PHASES,
  CHANNEL_GLYPHS,
  CONTROL_MODES,
  GATE_CHANNEL,
  INSTANT_FIELDS,
  OUTCOME_CHANNEL,
  PHASE_CHANNEL,
  RECORD_KINDS,
  ROW_FACTS,
  TIMELINE_STEPS,
  VERIFICATION_CHANNEL,
  VERIFICATION_FAILED_NOTE,
} from "./studio-runwords.js";
//: Whether an authorized attempt on one step is still unanswered, read off the
//: run's own records the way `graph_schedule` reads it. A projection over one
//: run read, so it lives with the other projections rather than here.
import {attemptInFlight} from "./studio-runread.js";
//: The two controls a position row may carry, from the module that owns them.
//: They are the one part of this screen that WRITES, and they live next door so
//: that the part a reader has to audit is a whole file rather than a region of
//: this one. Nothing about the offer rule is decided here.
import {stepControls} from "./studio-runstep.js";
//: The form that publishes a document into a run, and the instruction a
//: step's proposal bound: the other write on this screen, in its own file for
//: the step control's reason.
import {boundSources, documentSection} from "./studio-rundocs.js";
import {participantDeck, participantSelection, releaseParticipants,
  restoreParticipantScroll} from "./studio-participants.js";
import {runHeading} from "./studio-runhead.js";

//: The one sentence, handed to whichever container is showing the word. Every
//: container carrying `verification_failed` needs its OWN copy -- one written
//: elsewhere on the screen does not cover a section that shows the word alone
//: -- and spelling that rule at each site is how a sixth site came to forget
//: it. Spelled once here, spread into whatever is being built.
export const PHASE_SENTENCES = Object.freeze({
  empty: "Nothing has been read yet.",
  loading: "Reading this project's runs.",
  ready: "Read.",
  stale: "Shown from an earlier read; a newer one has not landed.",
  refused: "This read was refused. Nothing below is newer than the refusal.",
  failed: "This read failed. Nothing below is newer than the failure.",
  disconnected: "The live connection is down, so nothing here updates.",
});

function alsoSay(state, outcome) {
  return outcome === "verification_failed"
    ? [note(localize(state, "runs.verification_failed_note"))] : [];
}

//: The seven words a screen container may stand in, and the plain sentence
//: each one is said with.


const NOT_STATED = "not stated";

function show(state, value) {
  if (value === null || value === undefined || value === "") return localize(state, "runs.copy_8");
  if (Array.isArray(value)) return value.length ? value.join(", ") : localize(state, "runs.copy_8");
  return String(value);
}

function chip(channel, word) {
  const known = CHANNEL_GLYPHS[channel] ? channel : "none";
  return element("span", {className: `studio-chip studio-chip--${known}`}, [
    element("i", {className: "studio-chip__g", text: CHANNEL_GLYPHS[known]}),
    element("span", {text: word}),
  ]);
}

function fact(state, label, value) {
  return element("p", {className: "studio-fact"}, [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v", text: show(state, value)}),
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
function actionButton(state, handlers, name, label, run) {
  const call = handlerOf(handlers, name);
  const button = element("button", {
    "data-focus-key": `action:${name}`, text: label, type: "button",
  });
  if (call === null) {
    button.disabled = true;
    button.title = localize(state, "runs.copy_11", {name: String(name)});
    return button;
  }
  button.addEventListener("click", () => call(run));
  return button;
}

function banner(state, phase) {
  const word = PHASE_SENTENCES[phase] ? phase : "failed";
  return element("p", {className: `studio-banner studio-banner--${word}`}, [
    element("span", {text: localize(state, "runs.phase_" + word)}), " ", protocolWord(word),
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
function followed(state, row) {
  if (typeof row.workflow_id !== "string"
      || !Number.isInteger(row.revision)) {
    return localize(state, "runs.copy_14");
  }
  return localize(state, "runs.copy_15", {id: String(row.workflow_id), revision: String(row.revision)});
}

function runSummary(state, row, connected) {
  if (row.unreadable === true) {
    return [chip("fail", localize(state, "runs.unreadable")),
      element("span", {className: "studio-run__meta",
        text: localize(state, "runs.copy_16")})];
  }
  const human = connected ? row.human_state : "unknown";
  // WHICH plan this run froze itself to follow, first, because it is the
  // question a list of runs is usually being scanned for. The detail below has
  // always shown it and the row payload has always carried it -- the row simply
  // did not render it, so telling two runs of two workflows apart meant opening
  // both. A run that follows no workflow says so rather than showing a gap.
  const parts = [followed(state, row),
    localize(state, "runs.copy_17", {status: String(show(state, row.envelope_status))}),
    localize(state, "runs.copy_18", {mode: String(show(state, row.mode))}),
    human === "required" ? localize(state, "runs.copy_19")
      : human === "not_required" ? localize(state, "runs.copy_20") : localize(state, "runs.copy_21"),
    localize(state, "runs.copy_22", {count: String(show(state, row.open_actions))})];
  const carried = [element("span", {className: "studio-run__meta",
    text: parts.join(" · ")})];
  if (typeof row.last_outcome === "string") {
    carried.unshift(chip(OUTCOME_CHANNEL[row.last_outcome] || "none",
      row.last_outcome));
  }
  return carried;
}

function runButton(state, row, selectedId, handlers, connected) {
  const runId = show(state, row.run_id);
  const button = element("button", {
    "aria-pressed": runId === selectedId ? "true" : "false",
    className: "studio-run", "data-focus-key": `run:${runId}`, type: "button",
  }, [element("span", {className: "studio-run__id", text: runId}),
    ...runSummary(state, row, connected)]);
  const select = handlerOf(handlers, "selectRun");
  if (select === null) {
    button.disabled = true;
    button.title = localize(state, "runs.copy_26");
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
function runRow(state, row, selectedId, handlers, connected) {
  const item = element("li", {}, [runButton(state, row, selectedId, handlers, connected)]);
  item.append(...alsoSay(state, row.last_outcome));
  return item;
}

function runList(state, runs, handlers, expanded, taskId, connected) {
  const list = rows(runs.list).filter((row) => !taskId || row.task_id === taskId);
  const picker = element("details", {className: "studio-run-picker"}, [
    element("summary", {"data-focus-key": "run-picker", text:
      runs.selectedId ? localize(state, "runs.copy_27") : localize(state, "runs.copy_28")}),
  ]);
  picker.open = expanded ?? !runs.selectedId;
  const body = [element("div", {className: "studio-run-bar"}, [
    ...(runs.phase === "ready" ? [] : [banner(state, runs.phase)]),
    actionButton(state, handlers, "refreshRuns", localize(state, "runs.copy_30"), null)]), picker];
  if (!list.length) {
    picker.append(note(localize(state, "runs.copy_31")));
  } else {
    const items = element("ul", {className: "studio-runs__rows"});
    for (const row of list) items.append(runRow(state, row, runs.selectedId, handlers, connected));
    picker.append(items);
  }
  return element("nav", {className: "studio-runs__list",
    "aria-label": localize(state, "runs.copy_32")}, body);
}

// -- one run ------------------------------------------------------------------

function identitySection(state, detail, handlers) {
  const run = object(detail.run) || {};
  // The frozen configuration owns this fact; the boundary already refused the
  // read if the reference was there and malformed, so `null` here means the
  // run genuinely froze none.
  const followed = (object(detail.config) || {}).workflow || null;
  const mode = show(state, run.mode);
  const task = projectTaskBinding(detail);
  const body = [
    fact(state, localize(state, "runs.copy_33"), task.state === "bound" ? `${task.title || task.taskId} · ${task.taskId}`
      : task.state === "none" ? localize(state, "runs.copy_35") : localize(state, "runs.copy_36")),
    ...(task.state === "bound" ? [fact(state, localize(state, "runs.copy_37"), task.workScope)] : []),
    fact(state, localize(state, "runs.copy_38"), run.run_id), fact(state, localize(state, "runs.copy_39"), run.cycle_id),
    fact(state, localize(state, "runs.copy_40"), run.created_at),
    fact(state, localize(state, "runs.copy_41"), mode),
    note((CONTROL_MODES[mode] ? localize(state, "runs.mode_" + mode) : null) || localize(state, "runs.copy_42")),
    fact(state, localize(state, "runs.copy_43"), run.status),
    note(localize(state, "runs.copy_44")),
    fact(state, localize(state, "runs.copy_45"), run.config_digest),
    // Read out of the run's own frozen configuration, which is the document
    // `config_digest` above is taken over -- so the two facts on this screen
    // stand or fall together, and a run that froze no workflow says so in
    // words rather than showing a plausible one.
    fact(state, localize(state, "runs.copy_46"), followed === null
      ? localize(state, "runs.copy_47")
      : followed.id),
    fact(state, localize(state, "runs.copy_48"), followed === null
      ? localize(state, "runs.copy_49")
      : localize(state, "runs.copy_50", {revision: String(followed.revision)})),
    note(followed === null
      ? localize(state, "runs.copy_51")
      : localize(state, "runs.copy_52")),
  ];
  const warnings = rows(detail.warnings);
  if (warnings.length) {
    body.push(element("ul", {className: "studio-warnings"},
      warnings.map((line) => element("li", {text: show(state, line)}))));
  }
  body.push(actionButton(state, handlers, "showDecisions", localize(state, "runs.copy_54"),
    run.run_id));
  return section(localize(state, "runs.copy_55"), body);
}

//: The frozen binding, joined to what this build can serve. The binding comes
//: from the run's own configuration snapshot; the capability list comes from
//: the controls read and is joined BY IDENTITY, never by a displayed label.
function planSection(state, detail) {
  const graph = object(detail.graph);
  if (graph === null || graph.definition === null
      || graph.definition === undefined) {
    return section(localize(state, "runs.copy_56"), [note(localize(state, "runs.copy_57"))]);
  }
  const definition = object(graph.definition) || {};
  return section(localize(state, "runs.copy_58"), [
    fact(state, localize(state, "runs.copy_59"), definition.graph_id),
    fact(state, localize(state, "runs.copy_60"), graph.definition_digest),
    fact(state, localize(state, "runs.copy_61"), rows(definition.nodes).length),
    ...planWord(state, graph),
    note(localize(state, "runs.copy_62")),
  ]);
}

//: What each run word MEANS. `complete` is the one a reader will get wrong: it
//: says the plan has nothing left to open and never that the run succeeded.
const PLAN_WORDS = Object.freeze({
  open: "runs.copy_63",
  complete: "runs.copy_64",
  stalled: "runs.copy_65",
});

function lastWhere(nodes, pick) {
  const found = nodes.filter(pick);
  return found.length ? found[found.length - 1] : null;
}

//: Where the plan stands, and the facts a person needs BESIDE it.
//
// The neutral channel and never `pass`. A green tick against `complete` would
// be the product telling somebody their run worked when what it knows is only
// that there is nothing left to do -- and the run that burned every retry lands
// on the same word. So the word is stated, and the loop's position and the last
// answer are stated beside it, because those two tell the two apart.
function planWord(state, graph) {
  const schedule = object(graph.schedule);
  if (schedule === null) return [];
  const word = typeof schedule.run_state === "string"
    ? schedule.run_state : "unknown";
  const body = [element("p", {className: "studio-fact"}, [
    element("span", {className: "studio-fact__k", text: localize(state, "runs.copy_66")}),
    chip("none", word),
    element("span", {className: "studio-fact__v",
      text: (PLAN_WORDS[word] ? localize(state, PLAN_WORDS[word]) : null) || localize(state, "runs.copy_67")}),
  ])];
  const runtime = object(graph.runtime);
  const nodes = rows(runtime && runtime.nodes);
  const spent = lastWhere(nodes, (row) => row.bound_reached === true);
  const gate = lastWhere(nodes, (row) => typeof row.decision === "string"
    && row.decision !== "idle");
  const seen = lastWhere(nodes, (row) => typeof row.outcome === "string");
  if (spent) body.push(fact(state, localize(state, "runs.copy_68"), localize(state, "runs.copy_69", {id: String(show(state, spent.node_id))})));
  if (gate) body.push(fact(state, localize(state, "runs.copy_70"), `${show(state, gate.node_id)} — `
    + `${gate.decision}`));
  if (seen) body.push(fact(state, localize(state, "runs.copy_72"), `${show(state, seen.node_id)} — `
    + `${seen.outcome}`));
  if (seen) body.push(...alsoSay(state, seen.outcome));
  return body;
}

function loopLine(state, node, runtime) {
  const loop = object(node.loop);
  if (loop === null) return null;
  const at = typeof runtime.pass === "number"
    ? localize(state, "runs.copy_74", {pass: String(runtime.pass), bound: String(loop.bound)})
    : localize(state, "runs.copy_75", {bound: String(show(state, loop.bound))});
  const reached = runtime.bound_reached === true
    ? localize(state, "runs.copy_76") : "";
  return element("p", {className: "studio-mono studio-loop",
    text: localize(state, "runs.copy_78", {at: String(at), step: String(show(state, loop.back_to))})
      + reached});
}

//: Why a step stands where it does, off the server's own schedule.
function standingOf(schedule, nodeId) {
  return rows(schedule && schedule.nodes)
    .find((node) => node.node_id === nodeId) || null;
}

//: Why a step is blocked when the plan itself has nothing more to say about it.
//
// A `blocked` row naming no road, awaiting no document and with attempts left
// is one of exactly two situations, and `graph_schedule` produces no third: an
// attempt on it has not answered, so `attempt_in_flight` blocks the step until
// its result lands; or a halt rewrote every runnable row to blocked
// (`_stop_runnable`) so nothing further is offered as work. Until this was
// asked the row drew a bare `plan: blocked` chip with no sentence at all -- a
// person meeting it could not tell a worker that is running from a run that
// has stopped.
//
// `flying` is the RECORDS' answer and never the runtime phase's -- see
// `attemptInFlight`, which is where two readings of the phase went wrong.
function stillOwed(state, flying) {
  return flying
    ? localize(state, "runs.copy_79")
    : localize(state, "runs.copy_80");
}

function planStanding(state, item, standing, flying) {
  if (standing === null) return;
  item.append(chip("none", localize(state, "runs.copy_81", {state: String(show(state, standing.state))})));
  // A settled step is DONE with, and the plan says so rather than leaving the
  // word to be read as "waiting". The one thing that reopens it is a loop, and
  // that is stated because it is the only road back.
  if (standing.state === "settled") {
    item.append(note(localize(state, "runs.copy_82")));
    return;
  }
  if (standing.state === "blocked" && standing.attempts_spent === true) {
    item.append(note(localize(state, "runs.copy_83")));
    return;
  }
  // A step waiting for a DOCUMENT is asked about before the roads are. The two
  // are different sentences and only one of them is about this plan's shape:
  // `blocked_by` carries predecessors, so rendering it for an artifact wait
  // printed an empty "Waiting on" beside a rule about roads -- a true sentence
  // about the wrong thing, and a person reading it would go looking for a step
  // that does not exist. Both are said when both are true.
  const awaited = rows(standing.awaiting_artifacts);
  if (standing.state === "blocked" && awaited.length) {
    item.append(fact(state, localize(state, "runs.copy_84"), awaited.join(", ")));
    item.append(note(localize(state, "runs.copy_86")));
  }
  if (standing.state === "blocked") {
    const roads = rows(standing.blocked_by);
    if (roads.length) {
      item.append(fact(state, localize(state, "runs.copy_87"), roads.join(", ")));
      item.append(note(localize(state, "runs.all_roads")));
    } else if (!awaited.length) {
      item.append(note(stillOwed(state, flying)));
    }
    return;
  }
  if (standing.state === "unreachable") {
    const closed = rows(standing.closed_by);
    item.append(note(closed.length
      ? localize(state, "runs.copy_89", {steps: String(closed.join(", "))})
      : localize(state, "runs.copy_90")));
  }
}

function positionRow(node, runtime, standing, detail, state, handlers) {
  const item = element("li", {className: "studio-position"}, [
    element("span", {className: "studio-position__t", text: show(state, node.title)}),
    element("span", {className: "studio-mono",
      text: `${show(state, node.node_id)} · ${show(state, node.kind)}`}),
    chip(PHASE_CHANNEL[runtime.phase] || "none", show(state, runtime.phase)),
  ]);
  if (typeof runtime.outcome === "string") {
    item.append(chip(OUTCOME_CHANNEL[runtime.outcome] || "none",
      runtime.outcome));
  }
  if (typeof runtime.decision === "string") {
    item.append(chip(GATE_CHANNEL[runtime.decision] || "none",
      localize(state, "runs.copy_92", {decision: String(runtime.decision)})));
  }
  item.append(fact(state, localize(state, "runs.copy_93"), runtime.observed_at),
    fact(state, localize(state, "runs.copy_94"), rows(runtime.attempt_ids).length),
    fact(state, localize(state, "runs.copy_95"), runtime.evidence_refs));
  const loop = loopLine(state, node, runtime);
  if (loop !== null) item.append(loop);
  const plan = standing === undefined ? null : standing;
  // The RUNTIME row's id, never the plan node's: a runtime row the definition
  // does not name arrives here with an empty node, and an absent id would then
  // match every unbound request in the journal.
  planStanding(state, item, plan, attemptInFlight(detail, runtime.node_id));
  item.append(...boundSources(detail, node, state));
  item.append(...alsoSay(state, runtime.outcome));
  // …and last, the one thing on this screen a person can DO to the run. It is
  // offered on the SCHEDULE's word and nothing else; the sentences above have
  // already said why a row that gets none gets none.
  item.append(...stepControls(node, runtime, plan, detail, state, handlers));
  return item;
}

//: Where each step stands, from the runtime projection joined to the plan by
//: `node_id` -- the one name the two documents share. There is deliberately no
//: run-wide phase word: the journal carries none.
function positionSection(detail, state, handlers) {
  const graph = object(detail.graph);
  const runtime = graph ? object(graph.runtime) : null;
  if (runtime === null) {
    return section(localize(state, "runs.copy_96"), [note(localize(state, "runs.copy_97"))]);
  }
  const definition = object(graph.definition) || {};
  const planned = new Map(rows(definition.nodes)
    .map((node) => [node.node_id, node]));
  const list = element("ul", {className: "studio-positions"});
  const schedule = object(graph.schedule);
  for (const row of rows(runtime.nodes)) {
    list.append(positionRow(planned.get(row.node_id) || {}, row,
      standingOf(schedule, row.node_id), detail, state, handlers));
  }
  return section(localize(state, "runs.copy_98"), [
    note(localize(state, "runs.copy_99")),
    list]);
}

function evidenceItem(state, record) {
  return element("li", {className: "studio-evidence"}, [
    element("span", {className: "studio-mono",
      text: `${show(state, record.kind)} ${show(state, record.evidence_id)}`}),
    element("span", {text: show(state, record.label)}),
    chip(VERIFICATION_CHANNEL[record.verification] || "none",
      show(state, record.verification)),
    fact(state, localize(state, "runs.copy_101"), record.uri),
    fact(state, localize(state, "runs.copy_102"), record.verified_by),
    fact(state, localize(state, "runs.copy_103"), record.verifier_instance_id),
  ]);
}

function outcomeSection(state, records) {
  const results = records.filter((row) => row.record_type === "action_result");
  const evidence = records.filter((row) => row.record_type === "evidence");
  const body = [];
  if (!results.length) {
    body.push(note(localize(state, "runs.copy_104")));
  } else {
    const last = object(results[results.length - 1].record) || {};
    body.push(fact(state, localize(state, "runs.copy_105"), last.outcome),
      chip(OUTCOME_CHANNEL[last.outcome] || "none", show(state, last.outcome)),
      fact(state, localize(state, "runs.copy_106"), last.exit_code),
      fact(state, localize(state, "runs.copy_107"), last.detail),
      fact(state, localize(state, "runs.copy_108"), last.action_id));
    body.push(...alsoSay(state, last.outcome));
  }
  if (!evidence.length) {
    body.push(note(localize(state, "runs.copy_109")));
  } else {
    body.push(element("ul", {className: "studio-evidences"},
      evidence.map((row) => evidenceItem(state, object(row.record) || {}))));
  }
  return section(localize(state, "runs.copy_110"), body);
}

function artifactSection(state, records) {
  const written = records.filter((row) => row.record_type === "artifact");
  if (!written.length) {
    return section(localize(state, "runs.copy_111"), [note(localize(state, "runs.copy_112"))]);
  }
  const list = element("ul", {className: "studio-artifacts"});
  for (const row of written) {
    const record = object(row.record) || {};
    const source = records.filter((item) => item.record_type === "action_result")
      .map((item) => object(item.record) || {})
      .filter((item) => item.action_id === record.source_action_id).at(-1);
    list.append(element("li", {className: "studio-artifact"}, [
      element("span", {className: "studio-mono", text: show(state, record.artifact_id)}),
      fact(state, localize(state, "runs.copy_113"), record.artifact_ref),
      fact(state, localize(state, "runs.copy_114"), record.media_type),
      fact(state, localize(state, "runs.copy_115"), record.created_at),
      fact(state, localize(state, "runs.copy_116"), record.source_action_id),
      fact(state, localize(state, "runs.copy_117"), source ? source.outcome : record.source_action_id
        ? localize(state, "runs.copy_118") : localize(state, "runs.copy_119")),
      ...(source ? alsoSay(state, source.outcome) : []),
      ...(source && source.outcome !== "succeeded" ? [note(localize(state, "runs.copy_120"))] : []),
      fact(state, localize(state, "runs.copy_121"), record.input_artifact_ids),
      fact(state, localize(state, "runs.copy_122"), typeof record.content === "string"
        ? record.content.length : null),
    ]));
  }
  return section(localize(state, "runs.copy_123"), [list]);
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

function timelineFacts(state, kind, record) {
  const names = ROW_FACTS[kind];
  const carried = element("div", {className: "studio-row__facts"});
  if (!names) {
    carried.append(note(localize(state, "runs.copy_124")));
    return carried;
  }
  for (const name of names) {
    if (!Object.prototype.hasOwnProperty.call(record, name)) continue;
    carried.append(fact(state, name, record[name]));
  }
  return carried;
}

function timelineChip(state, kind, record) {
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

function timelineRow(state, wrapper, index) {
  const kind = show(state, wrapper.record_type);
  const record = object(wrapper.record) || {};
  const instantField = INSTANT_FIELDS[kind];
  const step = stepOf(kind, record);
  const head = element("p", {className: "studio-row__head"}, [
    element("span", {className: "studio-row__n", text: `${index + 1}`}),
    element("span", {text: (RECORD_KINDS[kind] ? localize(state, "runs.record_" + kind) : null) || localize(state, "runs.copy_126")}),
    protocolWord(kind),
  ]);
  if (step !== null) head.append(protocolWord(localize(state, "runs.copy_127", {step: String(step)})));
  head.append(element("span", {className: "studio-row__at",
    text: instantField ? show(state, record[instantField])
      : localize(state, "runs.copy_128")}));
  const badge = timelineChip(state, kind, record);
  if (badge !== null) head.append(badge);
  const item = element("li", {className: "studio-row"},
    [head, timelineFacts(state, kind, record)]);
  item.append(...alsoSay(state, record.outcome));
  return item;
}

function timelineSection(state, records) {
  if (!records.length) {
    return section(localize(state, "runs.copy_129"), [note(localize(state, "runs.copy_130"))]);
  }
  const list = element("ol", {className: "studio-timeline"});
  records.forEach((wrapper, index) => list.append(timelineRow(state, wrapper, index)));
  return section(localize(state, "runs.copy_131"), [
    note(localize(state, "runs.copy_132")),
    list]);
}

// -- the detail column --------------------------------------------------------

function unreadableDetail(state, row) {
  return element("div", {className: "studio-runs__detail"}, [
    element("h2", {text: show(state, row.run_id)}),
    chip("fail", localize(state, "runs.unreadable")),
    note(localize(state, "runs.copy_133")),
    fact(state, localize(state, "runs.copy_134"), `conductor/runs/${show(state, row.run_id)}/`),
    note(localize(state, "runs.copy_135")),
  ]);
}

function selectedRow(state) {
  return rows(state.list).find((row) => row.run_id === state.selectedId) || null;
}

function detailColumn(runs, state, handlers, participant) {
  const row = selectedRow(runs);
  if (row !== null && row.unreadable === true) return unreadableDetail(state, row);
  const detail = object(runs.detail);
  if (detail === null) {
    return element("div", {className: "studio-runs__detail"}, [
      note(runs.selectedId
        ? localize(state, "runs.copy_136")
        : localize(state, "runs.copy_137"))]);
  }
  const records = rows(detail.records);
  return element("div", {className: "studio-runs__detail",
    "data-subject": `run:${String((object(detail.run) || {}).run_id)}`}, [
    runHeading(state, detail, detail.task?.title || show(state, (object(detail.run) || {}).run_id)),
    participantDeck(detail, participant, state, handlers),
    identitySection(state, detail, handlers),
    planSection(state, detail),
    positionSection(detail, state, handlers),
    documentSection(detail, state, handlers),
    outcomeSection(state, records),
    artifactSection(state, records),
    timelineSection(state, records),
  ]);
}

// -- the mount ----------------------------------------------------------------

//: Where focus stood: the control's key, and the FORM it stood in. Three
//: runnable steps draw three `field:proposed_by` controls under one key, so
//: a restore by key alone landed on the first of them -- alpha's -- and the
//: tail of a word typed into omega went to alpha, whose change re-chose the
//: draft and emptied omega (the slice-3 review's P3). The successor is
//: sought within the same form, and the caret travels with the words.
function focusKey(mount) {
  const active = document.activeElement;
  if (!active || active === document.body) return null;
  if (!mount.contains(active) || !active.getAttribute) return null;
  const key = active.getAttribute("data-focus-key");
  if (key === null) return null;
  const form = active.closest("[data-step]");
  const typed = typeof active.setSelectionRange === "function";
  return {key, step: form === null ? null : form.getAttribute("data-step"),
    run: mount.querySelector("[data-deck-run]")?.dataset.deckRun,
    start: typed ? active.selectionStart : null,
    end: typed ? active.selectionEnd : null};
}

function restoreFocus(mount, key) {
  if (key === null) return;
  // A participant, and the caret in a text control, belong to the run they were read in.
  if ((key.key.startsWith("participant") || key.start !== null)
    && key.run !== mount.querySelector("[data-deck-run]")?.dataset.deckRun) return;
  const within = key.step === null ? "" : `[data-step="${key.step}"] `;
  const successor = mount.querySelector(
    `${within}[data-focus-key="${key.key}"]`);
  if (!successor) return;
  const fold = successor.closest(".studio-inspect-more");
  if (fold && !fold.open && successor.tagName !== "SUMMARY") {
    fold.querySelector("summary").focus(); return;
  }
  const picker = successor.closest(".studio-run-picker");
  if (picker && !picker.open && successor.tagName !== "SUMMARY") {
    picker.querySelector("summary").focus(); return;
  }
  successor.focus();
  if (key.start !== null && typeof successor.setSelectionRange === "function") {
    successor.setSelectionRange(key.start, key.end);
  }
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
 *   `selectRun(runId)`, `refreshRuns()`, `showDecisions(runId)`, and the four
 *   `studio-runstep.js` invokes on a step this screen hands it.
 */
export function mountRuns(mount, state, handlers) {
  const key = focusKey(mount);
  const participant = participantSelection(mount);
  releaseParticipants(mount);
  // The WHOLE state travels into the detail column: a step control is gated on
  // the stream being open, which is a fact about the window and not about this
  // screen's own slice.
  const whole = object(state) || {};
  const runs = object(whole.runs) || {};
  const expanded = mount.dataset.pickerRun === (runs.selectedId || "")
    ? mount.querySelector(".studio-run-picker")?.open : undefined;
  mount.dataset.pickerRun = runs.selectedId || "";
  const column = detailColumn(runs, whole, handlers, participant);
  // A run read whole puts its name and its controls on one row (studio.css, Runs only).
  const read = column.querySelector("[data-deck-run]") ? " studio-runs--read" : "";
  mount.replaceChildren(element("div", {className: `studio-runs${read}`}, [
    runList(state, runs, handlers, expanded, whole.tasks?.selectedId, whole.connection === "open"),
    column,
  ]));
  restoreFocus(mount, key);
  restoreParticipantScroll(mount, participant);
}
