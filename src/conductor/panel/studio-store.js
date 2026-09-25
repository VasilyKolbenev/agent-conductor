"use strict";
// The Studio's reducer: one frozen state value, moved only by `reduce`.
//
// It touches no DOM and opens no socket, and it holds the boundary call: the
// module table gives it `studio-model.js` and gives transport no reason to know
// what a payload means.
//
// TWO SPELLINGS, ONE VALUE. `studio-model.js` answers in camelCase and the five
// mounting modules read the wire's own snake_case. The boundary JUDGES here and
// what is stored is the WIRE value it admitted -- rebuilt from the settled
// projection where the boundary DROPS rows (roster, starters, controls), and
// carried verbatim where it refuses the whole payload instead (workflows, runs,
// one run read). Nothing reaches the state the boundary did not admit.
//
// The draft rules below are this product's most expensive invariants, measured
// on `graph-store.js:186-267` and carried here unchanged.
import {draftFrom, frozenCopy, projectWorkflow} from "./studio-draft.js";
import {EDIT_TYPES, MAX_EDGES, MAX_NODES, MAX_RESOURCES, NODE_KINDS,
  applyEdit, nodeIds} from "./studio-edits.js";
import {projectProviders, projectRuns,
  projectStarters, projectWorkflows} from "./studio-model.js";
import {projectRunRead} from "./studio-situation.js";
import {projectControls, wireControls} from "./studio-controls.js";
import {NO_DOCUMENT, documentCleared, documentEdited, documentSpent}
  from "./studio-rundraft.js";
import {decisionRows, participantsOf} from "./studio-runread.js";
import {readWrites, stepAnswered, stepWriting} from "./studio-runwrites.js";
import {NO_FOLDS, NO_OPENING, NO_STARTER, foldMoved, openingCleared,
  openingEdited, starterEdited} from "./studio-toolbardraft.js";
import {changeSummary} from "./studio-review.js";
import {NO_TASKS, reduceTasks} from "./studio-tasks-model.js";
import {NO_QUOTAS, reduceQuotas} from "./studio-quotas-model.js";

//: The seven words a screen container may stand in; the plain sentence beside
//: each is the view's.
export const PHASES = Object.freeze(["empty", "loading", "ready", "stale",
  "refused", "failed", "disconnected"]);
//: The five screens, in the product's own order.
export const SCREENS = Object.freeze(
  ["overview", "workflow", "runs", "decisions", "agents"]);
//: `graph_template.SCHEMA_VERSION`, the one a draft document must claim.
export {WORKFLOW_SCHEMA, draftFrom} from "./studio-draft.js";
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ZOOM = Object.freeze({min: 0.4, max: 2});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }
function text(value) { return typeof value === "string" ? value : ""; }
//: A notice is a string of data, `{key, params}` said in the reader's language, or a list of
//: either (`studio-i18n.js` noticeText). What this module says itself is always a key.
function noticeOf(value) {
  return typeof value === "string" || Array.isArray(value) || typeof value?.key === "string" ? value : "";
}
const said = (key, params = {}) => Object.freeze({key, params: Object.freeze({...params})});

// A frozen copy built key by key -- the transport module still holds the
// parsed payload. Every key is DEFINED rather than assigned, so a document
// carrying `__proto__` gets an own property, never the prototype setter.

const NO_DRAFT = Object.freeze({key: null, action: "approve", actor: "",
  reason: ""});
//: What a person has typed against ONE step of a run's plan, and which step
//: that is. Nothing about the WORK is here: a proposal's instance, capability,
//: arguments and ceiling are the frozen plan's and are never typed, so the only
//: fields this draft can hold are the three a person supplies and the id that
//: says whose they are. Frozen like `NO_DRAFT`, and reset by the same event: a
//: landed run read moves the run, so a draft against the run that was there is
//: not a draft against this one.
//:
//: `generation` is the fifth field and is not typed by anybody: it counts
//: every choice of step, every clearing of the draft and every typed word,
//: so a write minted from an earlier draft can tell that the words on screen
//: are no longer the ones it spent. A write IN FLIGHT is not a fact about the
//: draft at all -- it is `runs.writes`' (`studio-runwrites.js`) -- so nothing
//: that moves the draft, and no read, can give a shut control back.
const NO_STEP = Object.freeze({nodeId: null, proposedBy: "", rationale: "",
  confirmedBy: "", generation: 0});

//: The draft cleared, one generation on: what every road that resets it says,
//: so a spent or moved draft is never mistaken for a later one by a write
//: that was minted from it (R07B of the review of `8dec0e4`).
function cleared(step) {
  return Object.freeze({...NO_STEP, generation: step.generation + 1});
}
const WORKFLOWS = Object.freeze({
  phase: "empty",
  list: Object.freeze([]),
  starters: Object.freeze([]),
  selectedId: null,
  //: The last landed read of the chosen workflow, verbatim; and the DRAWING,
  //: which is the document this window is editing, saved or not.
  detail: null,
  draft: null,
  //: The drawing as the last read left it: an edit since makes `draft` another object.
  readDraft: null,
  //: The one mark that tells a composed step from a durable one. It lives
  //: BESIDE the document because a draft document is a closed key set: a mark
  //: written into a node would make the drawing FOREIGN, and an unsavable
  //: drawing is not a drawing.
  localIds: Object.freeze([]),
  //: `durable` is a stored draft adopted unchanged; `local` is anything this
  //: window composed or edited on top of it.
  provenance: "none",
  //: The server's answer about the SAVED draft, and what this window already
  //: sees would be refused about the UNSAVED one. Two documents, two lists.
  diagnostics: Object.freeze([]),
  problems: Object.freeze([]),
  publishable: false,
  //: The server's word for "this draft would repeat the standing revision".
  //: Kept apart from `publishable` because the two are different sentences to
  //: a person: one says the drawing is broken, the other says it is a copy.
  unchanged: false,
  //: What publishing WOULD change, computed once when the read lands, from the
  //: two documents that read already carries. Null until there is a draft to
  //: compare. It is state and not a render-time computation for the reason
  //: `diagnostics` is: the review a person confirms must be the review that
  //: was on screen when they read it.
  changes: null,
  //: Whether the publish REVIEW is open. Publishing is two steps now: this
  //: window shows what would be written and waits, and only a Confirm writes.
  reviewing: false,
  nextRevision: null,
  savedAt: null,
  //: The digest of the saved draft the last read carried, echoed on publish.
  reviewedDigest: null,
  //: Whether this window may WRITE. Not "is the socket up": between choosing a
  //: workflow and its read landing the drawing is still the previous
  //: workflow's, and a save taken from it would write one workflow's document
  //: to another's draft. Readiness names one answer about one workflow, is
  //: taken away the moment another is chosen, and is given back only by a
  //: landed read of the chosen one. A refused or failed read grants nothing.
  writeReady: false,
  savePhase: "idle",   // idle | submitting | refused | outcome-unknown | saved
  saveNotice: "",
  //: The toolbar's own facts (`studio-toolbardraft.js`): the folds a person
  //: touched, the start box and the run form as typed. Kept across every
  //: read; cleared with the rest of this slice when another workflow is chosen.
  folds: NO_FOLDS, starter: NO_STARTER, opening: NO_OPENING,
});

export const EMPTY = Object.freeze({
  screen: "overview",
  connection: "connecting",   // connecting | open | closed
  notice: said("phase.empty"),
  //: WHOSE sentence the notice above is. A read may replace its own sentence
  //: with a newer one or with nothing; it may not delete a sentence about what
  //: the PERSON just did. Every write on this surface announces itself and then
  //: triggers the authoritative re-read of what it changed -- so a read that
  //: blanks the notice erases the receipt for the write that caused the read,
  //: within one animation frame of it appearing. That is how "The decision is a
  //: durable receipt in this run's journal" came to be drawn for ten
  //: milliseconds and read by nobody.
  noticeFrom: "read",   // read | human
  //: `project.name` is null until a workflows read lands, and stays null when
  //: the project has no name to show -- scaffolded before this build wrote one,
  //: or still carrying the template placeholder. Null is displayed as a
  //: sentence, never as a blank and never as a guess.
  project: Object.freeze({name: null, warnings: Object.freeze([])}),
  providers: Object.freeze([]),
  tasks: NO_TASKS,
  quotas: NO_QUOTAS,
  workflows: WORKFLOWS,
  canvas: Object.freeze({pan: Object.freeze({x: 0, y: 0}), zoom: 1,
    selection: Object.freeze({kind: null, id: null})}),
  runs: Object.freeze({phase: "empty", list: Object.freeze([]),
    selectedId: null, detail: null, step: NO_STEP, document: NO_DOCUMENT,
    writes: Object.freeze({})}),
  decisions: Object.freeze({phase: "empty", list: Object.freeze([]),
    draft: NO_DRAFT}),
  agents: Object.freeze({phase: "empty", participants: Object.freeze([])}),
});

// -- what the boundary admitted, in the wire's own words ------------------
function wireProviders(value) {
  return Object.freeze(projectProviders(value).map((row) => Object.freeze({
    provider_id: row.providerId, display_name: row.displayName,
    availability: row.availability, implementation: row.implementation,
    auth: row.auth, controls: row.controls,
    vendor_sandbox: row.vendorSandbox,
  })));
}

function wireStarters(value) {
  return Object.freeze(projectStarters(value).map((row) => Object.freeze({
    starter_id: row.starterId, title: row.title, revision: row.revision,
    caveats: row.caveats, document: row.document,
  })));
}

// `wireControls` lives in `studio-controls`, beside the projection that settled
// these values: one module owns the controls answer from the wire to the screen.

// -- the drawing ----------------------------------------------------------
//: A draft document is exactly `{schema_version, title, nodes, edges}`, and
//: the two `workflow_draft.NOT_YET_FIELDS` names -- `template_id`, `revision`
//: -- are carried by every starter and every published revision. So it is
//: REBUILT from a draft's four keys rather than copied and pruned: neither word
//: can ride in and make the drawing something the save route refuses.

// What an authoritative read REPLACES, and what it may not. The DURABLE arm
// and only that: the read really does bring a stored draft, so that document
// wins and exactly the COMPOSED steps ride on top of it, told apart by
// `localIds`. Three things it will not do: cross a workflow change, because
// one workflow's unsaved step offered on another's screen is that workflow's;
// keep an id the stored draft now carries, because the server is then the
// authority on that step; or draw an edge with an end the merged drawing does
// not hold, which is a line from nothing.
function heldDraft(state, durable, workflowId) {
  const held = state.workflows;
  const local = new Set(held.localIds);
  const adopted = {draft: durable, localIds: Object.freeze([]),
    provenance: "durable"};
  if (!local.size || held.selectedId !== workflowId || held.draft === null) {
    return adopted;
  }
  const arrived = new Set(nodeIds(durable));
  const kept = rows(held.draft.nodes).filter(
    (node) => local.has(node.node_id) && !arrived.has(node.node_id));
  if (!kept.length) return adopted;
  const keptIds = new Set(kept.map((node) => node.node_id));
  const nodes = [...rows(durable.nodes), ...kept];
  const known = new Set(nodes.map((node) => node.node_id));
  const carried = rows(held.draft.edges).filter((edge) =>
    (keptIds.has(edge.from_node) || keptIds.has(edge.to_node))
    && known.has(edge.from_node) && known.has(edge.to_node));
  return {
    draft: frozenCopy({...durable, nodes, edges: [...rows(durable.edges), ...carried]}),
    localIds: Object.freeze([...keptIds]),
    provenance: "local",
  };
}

// A read that brings NOTHING keeps the WHOLE drawing, not just the composed
// part. Measured on the Graph window before that fix: nine steps on screen,
// zero after the socket came back, because a reconnect always ends in a re-read
// and the empty arm reset to EMPTY. A plan missing eight of its nine steps is
// not a plan.
//
// A DURABLE drawing is never held across an answer: it belongs to the workflow
// that answered with it, and carrying it into another's "has no draft" would
// show one workflow's stored document as another's unsaved one -- the mixing
// this seam refuses, in its worst direction. Crossing a workflow change is
// refused at the door the Human's own action opens, not here.
function localPlan(state) {
  const held = state.workflows;
  if (held.draft === null || held.provenance === "durable") return null;
  return {draft: held.draft, localIds: held.localIds, provenance: "local"};
}

// -- what this window can already see would be refused --------------------
//: The rules the DRAFT route refuses outright -- a document that is FOREIGN
//: rather than merely incomplete -- asked here so a save refuses beside the
//: control that asked for it instead of posting a body the server rejects with
//: no diagnostics. What a draft is ALLOWED to be missing is absent from this
//: list on purpose: that is what `diagnostics` reports.
function nodeProblems(node, found) {
  const named = ID_RE.test(text(node.node_id)) ? node.node_id : said("notice.a_step");
  const step = (key, extra = {}) => found.push(said(key, {step: named, ...extra}));
  if (!ID_RE.test(text(node.node_id))) found.push(said("notice.problem_id_grammar"));
  if (!text(node.title).trim()) step("notice.problem_step_title");
  if (!NODE_KINDS.includes(node.kind)) step("notice.problem_step_kind");
  if (Object.hasOwn(node, "role_id") !== Object.hasOwn(node, "capability")) step("notice.problem_half_binding");
  if (Object.hasOwn(node, "verifier_role_id") && !Object.hasOwn(node, "role_id")) {
    step("notice.problem_verifier_no_role");
  }
  if (Object.hasOwn(node, "required_evidence") && !Object.hasOwn(node, "role_id")) {
    step("notice.problem_evidence_no_role");
  }
  if (Object.hasOwn(node, "failure_policy") && !Object.hasOwn(node, "role_id")) {
    step("notice.problem_policy_no_role");
  }
  // The half of the missing-artifact pairing rule this module can answer. The
  // contract's rule is about the CAPABILITY -- only the two the reviewed
  // schemas hand documents to may name a policy -- and which those are lives in
  // `command-projection`, which the module table does not grant this file and
  // should not: a reducer that could read the argument schemas could answer
  // about a step from something other than the draft it was given. So the
  // binding half is caught here, before the wire, and a capability SWITCH that
  // strands a policy is refused at the door by `TemplateNode`, whose sentence
  // names the capability and sends the person to the control they changed.
  if (Object.hasOwn(node, "missing_artifact_policy")
      && !Object.hasOwn(node, "capability")) {
    step("notice.problem_missing_artifact_no_capability");
  }
  if (rows(node.resources).length > MAX_RESOURCES) step("notice.problem_resources", {max: String(MAX_RESOURCES)});
}

export function saveProblems(draft) {
  if (!isObject(draft)) return Object.freeze([]);
  const found = [];
  if (!text(draft.title).trim()) found.push(said("notice.problem_workflow_name"));
  if (rows(draft.nodes).length > MAX_NODES) found.push(said("notice.problem_max_nodes", {max: String(MAX_NODES)}));
  if (rows(draft.edges).length > MAX_EDGES) found.push(said("notice.problem_max_edges", {max: String(MAX_EDGES)}));
  for (const node of rows(draft.nodes)) nodeProblems(node, found);
  return Object.freeze(found);
}

function edited(state, edit) {
  const held = state.workflows;
  if (!EDIT_TYPES.includes(edit && edit.type)) return state;
  if (held.draft === null) {
    return spoken(state, said("notice.edit_no_draft"));
  }
  // The document half lives next door and answers with a draft or a refusal;
  // everything below this line is the STATE half, which is what stayed here.
  const answer = applyEdit(held.draft, edit);
  if (answer.draft === null) {
    return answer.notice ? spoken(state, answer.notice) : state;
  }
  const draft = frozenCopy(answer.draft);
  const localIds = answer.added
    ? Object.freeze([...held.localIds, answer.added]) : held.localIds;
  return Object.freeze({...state,
    notice: answer.notice || state.notice,
    noticeFrom: answer.notice ? "human" : state.noticeFrom,
    workflows: Object.freeze({...held, draft, localIds, provenance: "local",
      problems: saveProblems(draft), savePhase: "idle", saveNotice: ""}),
  });
}

// -- the arms -------------------------------------------------------------
//: Every caller of this is the PERSON: the `status` arm a control dispatches
//: into, an edit their drawing refused, a starting document they opened. A read
//: that has something to say writes its own sentence and says `read` where it
//: writes it, so there is no second kind of caller here to parameterise for.
function spoken(state, notice) {
  return Object.freeze({...state, notice, noticeFrom: "human"});
}

//: What a landed read leaves in the notice: nothing of its own, and whatever
//: the person's last action put there. One rule, spelled once, for every arm
//: that used to write `notice: ""` -- which is a read deleting a sentence it
//: did not write.
function afterRead(state) {
  return state.noticeFrom === "human"
    ? {notice: state.notice, noticeFrom: "human"}
    : {notice: "", noticeFrom: "read"};
}

// A save outcome is carried THROUGH the authoritative answer that follows it;
// an answer carrying none leaves the one on screen alone. It is cleared where
// it becomes wrong: when the chosen workflow changes.
function carried(held, event) {
  return Object.hasOwn(event, "savePhase")
    ? {savePhase: event.savePhase, saveNotice: event.saveNotice}
    : {savePhase: held.savePhase, saveNotice: held.saveNotice};
}

function workflowsLoaded(state, event) {
  const settled = projectWorkflows(event.payload);
  if (settled === null) {
    return Object.freeze({...state,
      workflows: Object.freeze({...state.workflows, phase: "failed"}),
      noticeFrom: "read",
      notice: said("notice.workflows_unreadable")});
  }
  return Object.freeze({...state,
    // The boundary already refused a name this build could not have written,
    // so `settled.project` is a name or null and never a value to be checked
    // again on the way to the screen.
    project: Object.freeze({name: settled.project,
      warnings: state.project.warnings}),
    providers: wireProviders(event.payload.providers),
    workflows: Object.freeze({...state.workflows, phase: "ready",
      list: frozenCopy(event.payload.workflows),
      starters: wireStarters(event.payload.starters)}),
    agents: Object.freeze({...state.agents, phase: "ready"}),
    ...afterRead(state),
  });
}

function workflowLoaded(state, event) {
  const settled = projectWorkflow(event.payload);
  if (settled === null) return workflowUnread(state, event, "failed", said("notice.workflow_unreadable"));
  const payload = frozenCopy(event.payload);
  const stored = payload.draft === null ? null : payload.draft.document;
  const brought = stored === null ? null : draftFrom(stored);
  const merged = brought === null
    ? localPlan(state)
    : heldDraft(state, brought, payload.workflow_id);
  const draft = merged === null ? null : merged.draft;
  return Object.freeze({...state,
    workflows: Object.freeze({...state.workflows, phase: "ready",
      selectedId: payload.workflow_id, detail: payload,
      draft, readDraft: draft, localIds: merged === null ? Object.freeze([]) : merged.localIds,
      provenance: merged === null ? "none" : merged.provenance,
      diagnostics: payload.diagnostics, problems: saveProblems(draft),
      publishable: payload.publishable, nextRevision: payload.next_revision,
      unchanged: payload.unchanged === true,
      changes: changeSummary(payload.published, draft),
      // The identity of the SAVED draft this read carried. A publish echoes it
      // so the server can refuse when the draft has moved since the review.
      reviewedDigest: payload.draft === null ? null : payload.draft.digest,
      // A landed read closes any open review: what it showed was computed from
      // the previous answer, and confirming a review a newer read has already
      // replaced is the stale-state write this step exists to prevent.
      reviewing: false,
      savedAt: payload.draft === null ? null : payload.draft.saved_at,
      writeReady: event.ready === true, ...carried(state.workflows, event)}),
    ...afterRead(state),
  });
}

// A refused or failed READ brings no durable fact and is not the Human doing
// anything, so it may not destroy the drawing this window holds. The state word
// carries the refusal, the write door stays shut, and the notice says who holds
// what is on screen.
function workflowUnread(state, event, phase, notice) {
  const kept = localPlan(state);
  const held = state.workflows;
  return Object.freeze({...state,
    workflows: Object.freeze({...held, phase,
      draft: kept === null ? held.draft : kept.draft,
      localIds: kept === null ? held.localIds : kept.localIds,
      provenance: kept === null ? held.provenance : kept.provenance,
      writeReady: false, ...carried(held, event)}),
    noticeFrom: "read",
    notice: kept === null ? notice : Object.freeze([notice, said("notice.drawing_held")]),
  });
}

// The one door a held drawing is let go through, and it is the Human's own
// action rather than a transport event: choosing another workflow. A drawing
// made against one workflow is not a draft of another's, and the save door
// beside it writes to whichever is chosen -- so it goes HERE, before the new
// read goes out.
function workflowChosen(state, workflowId) {
  if (state.workflows.selectedId === workflowId) return state;
  return Object.freeze({...state,
    workflows: Object.freeze({...WORKFLOWS, phase: "loading",
      list: state.workflows.list, starters: state.workflows.starters,
      selectedId: workflowId}),
    canvas: Object.freeze({...state.canvas,
      selection: Object.freeze({kind: null, id: null})}),
    // A Human action, not a read: this one is ENTITLED to clear the sentence,
    // because the sentence it clears was about the workflow being left.
    notice: "", noticeFrom: "read",
  });
}

function runsLoaded(state, event) {
  const settled = projectRuns(event.payload);
  if (settled === null) {
    return Object.freeze({...state,
      runs: Object.freeze({...state.runs, phase: "failed"}),
      noticeFrom: "read",
      notice: said("notice.runs_unreadable")});
  }
  return Object.freeze({...state,
    providers: wireProviders(event.payload.providers),
    runs: Object.freeze({...state.runs, phase: "ready",
      list: frozenCopy(event.payload.runs)}),
    ...afterRead(state),
  });
}

//: The run read, the decisions waiting in it and the participants it froze
//: move together: all three come out of the SAME answer, and leaving one
//: standing while the others move would put two runs on one screen.
//: `said` is the notice and whose it is, together: every caller of this has an
//: opinion about both, and passing the sentence alone is what let a read blank
//: a Human's receipt.
//: What a landed read does to what a person is TYPING, which is nothing at all
//: when it is a read of the SAME run.
//
// Both drafts used to be reset here unconditionally, and every road into this
// function is a READ: a `run` frame for an attempt event on another branch, a
// `state` frame, the reconnect's own re-read. So the words vanished from under
// a person's hands while the control beside them promised that what they typed
// is kept -- and owner acceptance step 16 asks for the opposite in so many
// words: coming back from a dropped connection may not throw somebody out of
// the field they were typing in.
//
// A read that brings ANOTHER run, or none, still resets both: a draft is about
// one step and one gate of ONE run, and it means nothing about another.
//
// The WRITE roads clear their own draft before the read they provoke, which is
// why an accepted write still comes back to an empty form. That is deliberate
// and it is where the clearing belongs: the write knows those words are spent,
// and a read never does.
//
// A read says NOTHING about a write in flight. The flag used to live on the
// draft and go off here, so a read landing under a pending POST -- the `run`
// frame every write provokes, or a person pressing Read -- gave the control
// back and a second press wrote a second durable proposal (R07A of the review
// of `8dec0e4`). What is in flight is `runs.writes`' and only the write's own
// end moves it.
function keptDrafts(state, detail) {
  const same = detail !== null
    && detail.run.run_id === state.runs.selectedId;
  return {
    draft: same ? state.decisions.draft : NO_DRAFT,
    step: same ? state.runs.step : cleared(state.runs.step),
    document: same ? state.runs.document : documentCleared(state.runs.document),
  };
}

function runMoved(state, phase, detail, said) {
  const kept = keptDrafts(state, detail);
  return Object.freeze({...state,
    // A run read carries the run's warnings and says nothing about the
    // project's name, so the name already read is kept rather than cleared:
    // opening a run must not un-name the project on screen.
    project: Object.freeze({name: state.project.name,
      warnings: detail === null ? Object.freeze([]) : detail.warnings}),
    runs: Object.freeze({...state.runs, phase, detail, step: kept.step,
      document: kept.document,
      selectedId: detail === null ? state.runs.selectedId : detail.run.run_id}),
    decisions: Object.freeze({...state.decisions, phase, draft: kept.draft,
      list: detail === null ? Object.freeze([]) : decisionRows(detail)}),
    agents: Object.freeze({...state.agents, phase,
      participants: detail === null
        ? Object.freeze([]) : participantsOf(detail)}),
    ...said,
  });
}

function runLoaded(state, event) {
  if (projectRunRead(event.read) === null) {
    // A read of the SAME run -- the epoch guard admits no other -- that this
    // build cannot project is still a read of the same run: what a person
    // typed against it is kept, and only the writes in flight are not this
    // road's to touch either. An error road is not a change of run.
    const failed = runMoved(state, "failed", null, {noticeFrom: "read",
      notice: said("notice.run_unreadable")});
    return Object.freeze({...failed,
      runs: Object.freeze({...failed.runs, step: state.runs.step,
        document: state.runs.document}),
      decisions: Object.freeze({...failed.decisions,
        draft: state.decisions.draft})});
  }
  const controls = isObject(event.controls)
    ? projectControls(event.controls) : null;
  const detail = frozenCopy({...event.read,
    controls: controls === null ? null : wireControls(controls)});
  const moved = runMoved(state, "ready", detail, afterRead(state));
  // The one read that gives an ANSWERED write's control back: this run's.
  const read = Object.freeze({...moved, runs: Object.freeze({...moved.runs,
    writes: readWrites(moved.runs.writes, detail.run.run_id)})});
  return controls === null ? read : Object.freeze({...read,
    providers: wireProviders(event.controls.providers)});
}

function runChosen(state, runId) {
  if (state.runs.selectedId === runId) return state;
  return Object.freeze({...runMoved(state, "loading", null,
      {notice: state.notice, noticeFrom: state.noticeFrom}),
    runs: Object.freeze({...state.runs, phase: "loading", selectedId: runId,
      detail: null, step: cleared(state.runs.step),
      document: documentCleared(state.runs.document)})});
}

function seeded(state, event) {
  const draft = draftFrom(event.document);
  if (draft === null) {
    return spoken(state, said("notice.starter_unreadable"));
  }
  return Object.freeze({...state,
    // Every step of a seeded drawing is this window's until it is saved, so
    // every id is a local one and a later read may take none of them.
    workflows: Object.freeze({...state.workflows, draft,
      localIds: Object.freeze(nodeIds(draft)), provenance: "local",
      problems: saveProblems(draft), savePhase: "idle", saveNotice: ""}),
    notice: said("notice.seeded_unsaved"),
    noticeFrom: "human",
  });
}

function connectionMoved(state, value) {
  const open = value === "open";
  return Object.freeze({...state, connection: value,
    workflows: Object.freeze({...state.workflows,
      // A reconnect does not by itself make this window current again: what it
      // missed while it was down is unknown, so readiness is granted by the
      // READ that follows and by nothing else.
      writeReady: open ? state.workflows.writeReady : false}),
    notice: open ? state.notice : said("notice.connection_lost"),
    noticeFrom: open ? state.noticeFrom : "read",
  });
}

function canvasMoved(state, event) {
  const zoom = Number(event.zoom);
  const pan = isObject(event.pan) ? event.pan : {};
  return Object.freeze({...state, canvas: Object.freeze({...state.canvas,
    pan: Object.freeze({
      x: Number.isFinite(Number(pan.x)) ? Number(pan.x) : state.canvas.pan.x,
      y: Number.isFinite(Number(pan.y)) ? Number(pan.y) : state.canvas.pan.y}),
    zoom: Number.isFinite(zoom)
      ? Math.min(ZOOM.max, Math.max(ZOOM.min, zoom)) : state.canvas.zoom})});
}

function selected(state, selection) {
  const kind = isObject(selection)
    && (selection.kind === "node" || selection.kind === "edge")
    ? selection.kind : null;
  return Object.freeze({...state, canvas: Object.freeze({...state.canvas,
    selection: Object.freeze({kind,
      id: kind === null ? null : String(selection.id)})})});
}

function decisionDrafted(state, patch) {
  const draft = state.decisions.draft;
  const next = {...draft};
  for (const key of ["action", "actor", "reason"]) {
    if (isObject(patch) && Object.hasOwn(patch, key)) next[key] = patch[key];
  }
  return Object.freeze({...state, decisions: Object.freeze({...state.decisions,
    draft: Object.freeze(next)})});
}

//: Which STEP the run screen's draft is addressing, and nothing else carried
//: over. It clears rather than merges for `decisionChosen`'s reason: what was
//: typed against one step is not an answer about another, and a draft that kept
//: a field across a change of subject would propose one step in another's name.
//
// Choosing the step already chosen moves NOTHING. A control is drawn with the
// draft it saw, and a frame can redraw the form between two keystrokes: the
// control drawn first still says "choose this step" on its own change, and a
// reset here would drop the words a later control committed a moment ago.
function stepChosen(state, event) {
  const nodeId = typeof event.nodeId === "string" ? event.nodeId : null;
  if (nodeId !== null && state.runs.step.nodeId === nodeId) return state;
  return Object.freeze({...state, runs: Object.freeze({...state.runs,
    step: Object.freeze({...NO_STEP, nodeId,
      generation: state.runs.step.generation + 1})})});
}

//: One typed field of that draft. The three keys are closed: a patch naming
//: anything else -- a node id, a capability, an argument, `writing` -- moves
//: nothing, which is what keeps the plan's own facts out of a person's reach
//: and keeps the write flag out of a control's. A word that DID move takes
//: the generation with it: a write minted before it spends nothing of it.
function stepDrafted(state, patch) {
  const next = {...state.runs.step};
  let moved = false;
  for (const key of ["proposedBy", "rationale", "confirmedBy"]) {
    if (isObject(patch) && Object.hasOwn(patch, key)) {
      next[key] = patch[key];
      moved = true;
    }
  }
  if (!moved) return state;
  next.generation = state.runs.step.generation + 1;
  return Object.freeze({...state, runs: Object.freeze({...state.runs,
    step: Object.freeze(next)})});
}

//: The accepted road spends the draft -- and only the draft it was minted
//: from: this run, this step, this generation. One that has since moved to
//: another step, been cleared and re-chosen, or had a word typed into it --
//: the name typed into the Confirm form the proposal's own frame drew, while
//: that proposal's answer was still on the wire -- is somebody's unsent words
//: and is left alone; alpha's answer used to empty omega's fields (R07B).
function stepSpent(state, event) {
  const step = state.runs.step;
  if (state.runs.selectedId !== event.runId || step.nodeId !== event.nodeId
      || step.generation !== event.generation) {
    return state;
  }
  return Object.freeze({...state, runs: Object.freeze({...state.runs,
    step: cleared(step)})});
}

function phaseMoved(state, screen, event) {
  if (!PHASES.includes(event.phase)) return state;
  // A phase move is a READ saying where it got to, so a sentence it carries is
  // that read's own; one it does not carry leaves the standing sentence alone.
  const carries = event.notice !== undefined && noticeOf(event.notice) === event.notice;
  return Object.freeze({...state, [screen]: Object.freeze({
    ...state[screen], phase: event.phase}),
  notice: carries ? event.notice : state.notice,
  noticeFrom: carries ? "read" : state.noticeFrom});
}

// -- the one way to move --------------------------------------------------
function decisionChosen(state, event) {
  return Object.freeze({...state, decisions: Object.freeze({...state.decisions,
    draft: Object.freeze({...NO_DRAFT,
      key: typeof event.key === "string" ? event.key : null})})});
}

// The save door answers in every phase: a refusal that arrived after the
// drawing changed still has a Human waiting for it, and dropping it would leave
// a submitted document with no reported outcome at all.
function saveMoved(state, event) {
  return Object.freeze({...state, workflows: Object.freeze({...state.workflows,
    savePhase: ["idle", "submitting", "refused", "outcome-unknown", "saved"]
      .includes(event.phase) ? event.phase : "outcome-unknown",
    saveNotice: noticeOf(event.notice)})});
}

const ARMS = Object.freeze({
  "agents-phase": (state, event) => phaseMoved(state, "agents", event),
  "canvas-select": (state, event) => selected(state, event.selection),
  "canvas-view": canvasMoved,
  connection: (state, event) => ["connecting", "open", "closed"]
    .includes(event.state) ? connectionMoved(state, event.state) : state,
  "decision-chosen": decisionChosen,
  "decision-edit": (state, event) => decisionDrafted(state, event.patch),
  "decisions-phase": (state, event) => phaseMoved(state, "decisions", event),
  edit: (state, event) => edited(state, event.edit || {}),
  fold: foldMoved,
  "opening-cleared": openingCleared,
  "opening-edit": (state, event) => openingEdited(state, event.patch),
  "run-chosen": (state, event) => runChosen(state, event.runId),
  "run-loaded": runLoaded,
  "runs-loaded": runsLoaded,
  "runs-phase": (state, event) => phaseMoved(state, "runs", event),
  //: Publishing is two steps, and this arm is the first one. It opens the
  //: review and writes nothing; only a Confirm reaches the wire. It refuses to
  //: open over a workflow the server has not called publishable, so a review
  //: can never be shown for a write that would be refused anyway.
  "publish-review": (state, event) => Object.freeze({...state,
    workflows: Object.freeze({...state.workflows,
      reviewing: event.open === true && state.workflows.publishable
        && state.workflows.writeReady})}),
  save: saveMoved,
  screen: (state, event) => SCREENS.includes(event.screen)
    ? Object.freeze({...state, screen: event.screen}) : state,
  seed: seeded,
  "starter-edit": (state, event) => starterEdited(state, event.patch),
  status: (state, event) => spoken(state, noticeOf(event.notice)),
  "document-edit": (state, event) => documentEdited(state, event.patch),
  "document-spent": documentSpent,
  "step-answered": stepAnswered,
  "step-chosen": stepChosen,
  "step-edit": (state, event) => stepDrafted(state, event.patch),
  "step-spent": stepSpent,
  "step-writing": stepWriting,
  "workflow-chosen": (state, event) => workflowChosen(state, event.workflowId),
  "workflow-loaded": workflowLoaded,
  "workflow-unread": (state, event) => workflowUnread(state, event,
    event.phase === "refused" ? "refused" : "failed", noticeOf(event.notice)),
  "workflows-loaded": workflowsLoaded,
  "workflows-phase": (state, event) => phaseMoved(state, "workflows", event),
});

// An own-key check, not a lookup: an event type is data and "constructor" is a
// spelling of it, so an inherited member is never reached as an arm.
export function reduce(state, event) {
  if (!event || typeof event.type !== "string") return state;
  if (event.type === "run-cleared") { const {phase, list, writes, step, document: doc} = state.runs;
    return Object.freeze({...runChosen(state, null), runs: Object.freeze({...EMPTY.runs, phase,
      list, writes, step: cleared(step), document: documentCleared(doc)})}); }
  return Object.hasOwn(ARMS, event.type)
    ? ARMS[event.type](state, event) : reduceQuotas(reduceTasks(state, event), event);
}
