"use strict";
// The Studio's payload boundary: wire shapes in, settled internal values out.
//
// This module imports nothing, reaches no DOM node and opens no socket. It
// validates and it REFUSES; it never repairs. Every closed vocabulary below is
// a copy of the Python layer that owns it and tests/test_studio_source.py holds
// each copy to its owner, so a word this window draws is a word the runtime can
// actually mint.
//
// One rule decides between the two ways a bad row may be answered, and it is
// about the READER rather than about the row:
//
//   * a row the user must be able to REACH -- a workflow, a run, a journal
//     record -- is never dropped. The payload is refused instead, and the
//     screen says so. Dropping one would show a shorter truth as the whole
//     truth: a run you cannot see is worse than a run you cannot read.
//   * a row that only DECORATES -- the provider roster, the starter offers --
//     is dropped, and the rest of the answer still renders. The screen is
//     poorer and nothing it shows is wrong.
//
// The internal names are camelCase and the wire names are snake_case, and that
// is deliberate: a value that has been through this module is spelled
// differently from one that has not, so a module downstream cannot quietly read
// an unsettled payload and be mistaken for one that read a settled value.

// ── closed vocabularies, each a copy of its Python owner ──────────────────
//: command/contract_values.py ControlMode, through studio_contracts.CONTROL_MODES.
//: The whole authority ladder; there is no hidden autonomous mode.
//: The two ceilings a workflow step may place on itself, and the ranges
//: `graph_definition.settled_bounds` holds them to. A vocabulary rather than a
//: rule of this window's own: the numbers are the Python contract's, and
//: `tests/test_studio_canvas.py` pins them to it in both directions.
//:
//: The empty field means ABSENT and never zero. "This step has no limit" and
//: "this step may run for no time at all" are different sentences, and only
//: one of them is a plan.
export const CEILINGS = Object.freeze({
  timeout_seconds: Object.freeze({min: 1, max: 86400,
    what: "a timeout in seconds"}),
  attempt_bound: Object.freeze({min: 1, max: 99, what: "an attempt bound"}),
});

//: What a person may put in a ceiling field, judged by the vocabulary above.
//: Here rather than in the reducer because it moves no state: given a node and
//: a typed value it answers the same way forever, which is what everything else
//: in this module does. The window refuses out of range at the FIELD so a
//: person is told there rather than at a publish.
export function withCeiling(node, name, value) {
  const rule = CEILINGS[name];
  const raw = typeof value === "string" ? value.trim() : "";
  if (raw === "") {
    const {[name]: _dropped, ...rest} = node;
    return {node: rest, notice: ""};
  }
  const number = Number(raw);
  if (!Number.isInteger(number) || number < rule.min || number > rule.max) {
    return {node, notice: `${rule.what} is a whole number from ${rule.min} `
      + `to ${rule.max}, or empty for no limit.`};
  }
  return {node: {...node, [name]: number}, notice: ""};
}

export const CONTROL_MODES = Object.freeze(
  ["observe", "propose", "confirm", "policy"]);
//: command/adapters/provider.py AVAILABILITY_STATES -- whether THIS BUILD on
//: THIS MACHINE can reach a provider at all.
export const PROVIDER_AVAILABILITY = Object.freeze(
  ["available", "executable_absent", "version_mismatch", "unconfigured"]);
//: command/adapters/provider.py IMPLEMENTATION_STATES -- what this build's
//: transport for a provider IS. A different question from availability, and
//: the two share no value, so neither can be read as the other.
export const PROVIDER_IMPLEMENTATION = Object.freeze(
  ["real_experimental", "fixture_only", "unproven"]);
//: command/workflow_draft.py DIAGNOSTIC_CODES. A diagnostic is coded by the
//: exception TYPE the real constructor raised; the prose is never parsed.
export const DIAGNOSTIC_CODES = Object.freeze(
  ["template_refused", "contract_refused"]);
//: command/contract_values.py _RUN_STATES. This is the envelope's CREATION
//: word and never a live position -- the wire spells it `envelope_status` for
//: exactly that reason, and this window keeps the spelling.
export const RUN_STATES = Object.freeze(
  ["created", "active", "paused", "blocked", "complete", "failed",
    "cancelled", "unknown"]);
//: command/contract_values.py _RESULT_OUTCOMES. `verification_failed` is one
//: of them and it is not a success: a process that exits 0 has finished, which
//: is not the same as having been verified.
export const RESULT_OUTCOMES = Object.freeze(
  ["succeeded", "failed", "cancelled", "rejected", "unknown",
    "verification_failed"]);
//: command/run_store.py _RECORDS -- every kind of durable record a run's
//: journal may carry. A row naming anything else refuses the whole read: the
//: timeline may never skip a step the journal holds.
export const RECORD_KINDS = Object.freeze(
  ["action_request", "action_result", "evidence", "decision",
    "action_proposal", "adapter_observation", "attempt_event",
    "graph_definition", "artifact", "run_terminal"]);
//: command/contracts.py RunEnvelope._FIELDS -- the seven words a run envelope
//: answers for. The durable contract also carries an `extra` seam, so a key
//: outside this list is not a fault and is not refused; it is simply a key this
//: window reads nothing from and carries nowhere.
export const ENVELOPE_KEYS = Object.freeze(
  ["schema_version", "run_id", "cycle_id", "created_at", "config_digest",
    "mode", "status"]);

// The id grammar and the UTC-instant grammar, both frozen. The instant regex
// is character for character graph-payload.js's copy, and both answer the one
// corpus tests/fixtures/utc_instant_parity_corpus.json.
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const UTC_INSTANT =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|\+00:00)$/;
const MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
//: How deep a carried JSON value may nest before this boundary refuses it. A
//: published revision and a frozen configuration are both shallow; the bound
//: exists so a hostile payload cannot make the copier recurse without end.
const MAX_JSON_DEPTH = 32;
//: The longest text this window will carry in one field.
const TEXT_LIMIT = 4096;

export function isId(value) {
  return typeof value === "string" && ID_RE.test(value);
}

export function isDigest(value) {
  return typeof value === "string" && DIGEST_RE.test(value);
}

export function isInstant(value) {
  if (typeof value !== "string") return false;
  const m = UTC_INSTANT.exec(value);
  if (!m) return false;
  const year = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const maxDay = month === 2 && leap ? 29 : MONTH_LENGTHS[month - 1];
  if (day < 1 || day > maxDay) return false;
  const hour = Number(m[4]), minute = Number(m[5]), second = Number(m[6]);
  return hour <= 23 && minute <= 59 && second <= 59;
}

function isText(value) {
  return typeof value === "string" && value.length > 0
    && value.length <= TEXT_LIMIT;
}

function isCount(value) {
  return Number.isInteger(value) && value >= 0;
}

function isRevision(value) {
  return Number.isInteger(value) && value >= 1;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function has(row, key) {
  return Object.prototype.hasOwnProperty.call(row, key);
}

// A closed shape: exactly its own keys, no more and no fewer. JSON.parse makes
// "__proto__" and "constructor" OWN properties, so Object.keys sees them and
// they are refused as any other unknown key is.
function exactKeys(row, keys) {
  const own = Object.keys(row);
  return own.length === keys.length && keys.every((key) => has(row, key));
}

// Is this a JSON value this window is willing to carry unread? Depth-bounded,
// and closed to the six JSON types -- a function, an undefined or a class
// instance is not one, so nothing can ride in behind a copy.
function isJson(value, depth) {
  if (depth > MAX_JSON_DEPTH) return false;
  if (value === null) return true;
  const kind = typeof value;
  if (kind === "string") return value.length <= TEXT_LIMIT;
  if (kind === "boolean") return true;
  if (kind === "number") return Number.isFinite(value);
  if (Array.isArray(value)) {
    return value.every((item) => isJson(item, depth + 1));
  }
  if (kind !== "object") return false;
  return Object.keys(value).every(
    (key) => typeof key === "string" && isJson(value[key], depth + 1));
}

// A frozen copy, built key by key from a value `isJson` has already admitted.
// The copy matters as much as the freeze: the caller keeps a reference to the
// payload it parsed, and a value this module answered with must not change
// under a reader because somebody still holding that reference wrote to it.
function frozenJson(value) {
  if (Array.isArray(value)) {
    return Object.freeze(value.map(frozenJson));
  }
  if (isPlainObject(value)) {
    const out = {};
    for (const key of Object.keys(value)) out[key] = frozenJson(value[key]);
    return Object.freeze(out);
  }
  return value;
}

function frozenList(rows) {
  return Object.freeze(rows);
}

// ── the roster and the offers: decoration, so a bad row is DROPPED ────────
const PROVIDER_KEYS = ["provider_id", "display_name", "availability",
  "implementation", "controls"];

//: One provider as this build resolved it. Two rows for one provider id are
//: two answers to one question and NEITHER survives -- the rule
//: graph-payload.js's deployment projection already settled: "first wins" is
//: not a fact about the provider, it hands arrival order the authority to name
//: what a user is about to start a run on.
export function projectProviders(rows) {
  if (!Array.isArray(rows)) return frozenList([]);
  const out = [];
  const conflicted = new Set();
  for (const row of rows) {
    if (!isPlainObject(row) || !exactKeys(row, PROVIDER_KEYS)) continue;
    if (!isId(row.provider_id) || !isText(row.display_name)) continue;
    if (!PROVIDER_AVAILABILITY.includes(row.availability)) continue;
    if (!PROVIDER_IMPLEMENTATION.includes(row.implementation)) continue;
    if (!Array.isArray(row.controls) || !row.controls.every(isId)) continue;
    if (out.some((kept) => kept.providerId === row.provider_id)) {
      conflicted.add(row.provider_id);
      continue;
    }
    out.push(Object.freeze({
      providerId: row.provider_id,
      displayName: row.display_name,
      availability: row.availability,
      implementation: row.implementation,
      controls: frozenList(row.controls.slice()),
    }));
  }
  return frozenList(out.filter((row) => !conflicted.has(row.providerId)));
}

const STARTER_KEYS = ["starter_id", "title", "revision", "caveats", "document"];

//: The workflow documents this BUILD ships, offered as a starting point. The
//: document travels whole and is carried unread: what makes it a template is
//: the publish route's question, and asking it a second time here is how two
//: judges are born.
//:
//: `revision` and `caveats` are carried because every shipped starter has the
//: same title and they are NOT equivalent choices. They are derived server-side from
//: the documents themselves, so this end judges their SHAPE and never their
//: content: a caveat is prose from the route, and a row whose caveats are not a
//: list of strings is refused like any other malformed row.
export function projectStarters(rows) {
  if (!Array.isArray(rows)) return frozenList([]);
  const out = [];
  const seen = new Set();
  for (const row of rows) {
    if (!isPlainObject(row) || !exactKeys(row, STARTER_KEYS)) continue;
    if (!isId(row.starter_id) || !isText(row.title)) continue;
    if (!Number.isInteger(row.revision) || row.revision < 1) continue;
    if (!Array.isArray(row.caveats)
        || !row.caveats.every((line) => isText(line))) continue;
    if (!isPlainObject(row.document) || !isJson(row.document, 0)) continue;
    if (seen.has(row.starter_id)) continue;
    seen.add(row.starter_id);
    out.push(Object.freeze({
      starterId: row.starter_id,
      title: row.title,
      revision: row.revision,
      caveats: frozenList(row.caveats.slice()),
      document: frozenJson(row.document),
    }));
  }
  return frozenList(out);
}

// ── workflows ────────────────────────────────────────────────────────────
//: `project` is a name or null, and null is a real answer: a project
//: scaffolded before this build named one, or one still carrying the template
//: placeholder, has none to show. The key is REQUIRED even so -- a payload that
//: omits it was written by something this window has not been told about.
const WORKFLOWS_KEYS = ["project", "workflows", "providers", "starters"];
const WORKFLOW_ROW_KEYS = ["workflow_id", "title", "latest_revision",
  "revisions", "has_draft", "unreadable"];

function projectRevisionList(value) {
  if (!Array.isArray(value) || !value.every(isRevision)) return null;
  for (let i = 1; i < value.length; i += 1) {
    if (value[i] <= value[i - 1]) return null;
  }
  return frozenList(value.slice());
}

function projectWorkflowRow(row) {
  if (!isPlainObject(row) || !exactKeys(row, WORKFLOW_ROW_KEYS)) return null;
  if (!isId(row.workflow_id)) return null;
  if (row.title !== null && !isText(row.title)) return null;
  if (typeof row.has_draft !== "boolean") return null;
  if (typeof row.unreadable !== "boolean") return null;
  const revisions = projectRevisionList(row.revisions);
  if (revisions === null) return null;
  // The latest revision is the last one, or there are none at all. A payload
  // that disagrees with itself is refused rather than reconciled: choosing
  // which half to believe is the repair this boundary does not do.
  const latest = row.latest_revision;
  const expected = revisions.length ? revisions[revisions.length - 1] : null;
  if (latest !== expected) return null;
  return Object.freeze({
    workflowId: row.workflow_id,
    title: row.title,
    latestRevision: latest,
    revisions,
    hasDraft: row.has_draft,
    unreadable: row.unreadable,
  });
}

//: `GET /command/workflows`. A workflow row is navigation, so an unreadable
//: one refuses the list rather than vanishing from it.
//: `templates.NAME_RE` is the Python owner: letters, digits, space and
//: . _ - + ( ), opening on a letter or digit, at most 64 characters. Held here
//: as a shape rather than copied as a regex, because the two spellings would
//: drift and this window reads the name for display and for nothing else.
const PROJECT_NAME_MAX = 64;

function isProjectName(value) {
  return isText(value) && value.length <= PROJECT_NAME_MAX
    && value.trim() === value;
}

export function projectWorkflows(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, WORKFLOWS_KEYS)) {
    return null;
  }
  if (!Array.isArray(payload.workflows)) return null;
  const rows = [];
  const seen = new Set();
  for (const row of payload.workflows) {
    const settled = projectWorkflowRow(row);
    if (settled === null) return null;
    if (seen.has(settled.workflowId)) return null;
    seen.add(settled.workflowId);
    rows.push(settled);
  }
  // A name is held to the same rule the writer is held to, so a value that
  // could not have been written by `conduct init` is refused rather than
  // rendered: this string goes into the largest type on the Overview.
  if (payload.project !== null && !isProjectName(payload.project)) return null;
  return Object.freeze({
    project: payload.project,
    workflows: frozenList(rows),
    providers: projectProviders(payload.providers),
    starters: projectStarters(payload.starters),
  });
}

//: `unchanged` is the server's word for "this draft repeats the standing
//: revision". It is a separate key from `publishable` and not folded into it,
//: because the two are different sentences to a person: one says the drawing
//: is broken, the other says it is a copy, and a screen that could only say
//: "not publishable" would send a user looking for a mistake they did not make.
//: `warnings` is beside `diagnostics` and is nothing like it: a diagnostic
//: stops a publish and a warning never does. The window admits it as its
//: own key for that reason -- folding the two together would make a screen
//: unable to say "this will publish, and here is what to know about it".
//: `success_criteria` is a READING the server derives per step -- what
//: counts as success, in the words of the rules that enforce it. It is
//: admitted here because this is a CLOSED set and it refused the payload
//: outright when the key first arrived, which is the boundary working: a
//: key nobody declared is a key nobody reviewed. Admitting it is not the
//: same as trusting it -- the inspector renders the sentences and holds no
//: opinion about them, and a malformed row is skipped where it is drawn.
const WORKFLOW_KEYS = ["workflow_id", "revisions", "latest_revision",
  "unreadable_revisions", "published", "draft", "diagnostics", "warnings",
  "publishable", "unchanged", "next_revision", "success_criteria"];
//: `digest` names WHICH draft this is, so a publish can echo back the one it
//: reviewed. The window computes no hash of its own: it carries the server's
//: word and hands it back, and the server compares.
const DRAFT_KEYS = ["document", "saved_at", "digest"];
const DIAGNOSTIC_KEYS = ["code", "message", "node_id", "field"];

function projectDiagnostics(rows) {
  if (!Array.isArray(rows)) return null;
  const out = [];
  for (const row of rows) {
    if (!isPlainObject(row) || !exactKeys(row, DIAGNOSTIC_KEYS)) return null;
    if (!DIAGNOSTIC_CODES.includes(row.code)) return null;
    if (!isText(row.message)) return null;
    if (row.node_id !== null && !isId(row.node_id)) return null;
    if (row.field !== null && !isText(row.field)) return null;
    out.push(Object.freeze({
      code: row.code, message: row.message,
      nodeId: row.node_id, field: row.field,
    }));
  }
  return frozenList(out);
}

// Three answers, so "there is no draft" and "this draft is not readable" can
// never be confused: `null` is the workflow that has no draft, `undefined` is
// the refusal, and a frozen value is the draft. A single null would make an
// unreadable draft look like a workflow nobody has started drawing.
function projectDraft(value) {
  if (value === null) return null;
  if (!isPlainObject(value) || !exactKeys(value, DRAFT_KEYS)) return undefined;
  if (!isInstant(value.saved_at)) return undefined;
  if (!isPlainObject(value.document) || !isJson(value.document, 0)) {
    return undefined;
  }
  return Object.freeze({
    document: frozenJson(value.document), savedAt: value.saved_at,
  });
}

//: `GET /command/workflows/<id>` and the answer both write routes give back.
//: The draft document and the published document travel unread: whether either
//: constructs a revision is the server's own question, and its answer is the
//: `diagnostics` array beside them.
export function projectWorkflow(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, WORKFLOW_KEYS)) {
    return null;
  }
  if (!isId(payload.workflow_id)) return null;
  if (typeof payload.unchanged !== "boolean") return null;
  const revisions = projectRevisionList(payload.revisions);
  if (revisions === null) return null;
  const latest = revisions.length ? revisions[revisions.length - 1] : null;
  if (payload.latest_revision !== latest) return null;
  // The next revision is the one this workflow would publish into, and the
  // publish route computes it the same way. A payload naming another number is
  // asking this window to offer a publish the route would refuse.
  if (payload.next_revision !== (latest === null ? 1 : latest + 1)) return null;
  const unreadable = projectRevisionList(payload.unreadable_revisions);
  if (unreadable === null) return null;
  if (!unreadable.every((number) => revisions.includes(number))) return null;
  if (payload.published !== null
      && (!isPlainObject(payload.published) || !isJson(payload.published, 0))) {
    return null;
  }
  const draft = projectDraft(payload.draft);
  if (draft === undefined) return null;
  const diagnostics = projectDiagnostics(payload.diagnostics);
  if (diagnostics === null) return null;
  // Sentences, not rows: a warning has no code and nothing acts on it.
  if (!Array.isArray(payload.warnings)
      || !payload.warnings.every((row) => typeof row === "string")) {
    return null;
  }
  if (typeof payload.publishable !== "boolean") return null;
  // Publishable is true only when there IS a draft and nothing stops it. A
  // workflow with no draft has nothing to publish, which is a different thing
  // from a draft that would be refused, and the two never share a word.
  if (payload.publishable
      && (draft === null || diagnostics.length > 0)) return null;
  return Object.freeze({
    workflowId: payload.workflow_id,
    revisions,
    latestRevision: latest,
    unreadableRevisions: unreadable,
    published: payload.published === null ? null
      : frozenJson(payload.published),
    draft,
    diagnostics,
    warnings: frozenList(payload.warnings),
    publishable: payload.publishable,
    nextRevision: payload.next_revision,
  });
}

const REVISION_KEYS = ["workflow_id", "revision", "document"];

//: `GET /command/workflows/<id>/revisions/<n>` -- one immutable revision.
export function projectRevision(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, REVISION_KEYS)) {
    return null;
  }
  if (!isId(payload.workflow_id) || !isRevision(payload.revision)) return null;
  if (!isPlainObject(payload.document) || !isJson(payload.document, 0)) {
    return null;
  }
  return Object.freeze({
    workflowId: payload.workflow_id,
    revision: payload.revision,
    document: frozenJson(payload.document),
  });
}

// ── runs ─────────────────────────────────────────────────────────────────
const RUNS_KEYS = ["runs", "providers"];
const RUN_ROW_KEYS = ["run_id", "unreadable", "cycle_id", "created_at", "mode",
  "envelope_status", "graph_id", "undecided_gates", "open_actions",
  "last_outcome", "workflow_id", "revision"];
//: What a row whose run did not replay says about everything but its identity.
//: The provenance is in this list rather than outside it because "this run
//: cannot be read" and "this run followed no workflow" must not arrive here as
//: the same row: an unreadable run knows nothing, including that.
const UNREADABLE_ROW_FIELDS = ["cycle_id", "created_at", "mode",
  "envelope_status", "graph_id", "undecided_gates", "open_actions",
  "last_outcome", "workflow_id", "revision"];

function projectRunRow(row) {
  if (!isPlainObject(row) || !exactKeys(row, RUN_ROW_KEYS)) return null;
  if (!isId(row.run_id) || typeof row.unreadable !== "boolean") return null;
  if (row.unreadable) {
    // A run that does not replay is LISTED, and every derived field of it is
    // null. A row claiming to be unreadable while still naming a mode or an
    // outcome is a row that read something, and this window may not decide
    // which half of it to believe.
    return UNREADABLE_ROW_FIELDS.every((key) => row[key] === null)
      ? Object.freeze({
        runId: row.run_id, unreadable: true, cycleId: null, createdAt: null,
        mode: null, envelopeStatus: null, graphId: null, undecidedGates: null,
        openActions: null, lastOutcome: null, workflow: null,
      })
      : null;
  }
  // Both halves or neither, held here as well as at the frozen configuration:
  // a row naming a workflow at no revision, or a revision of no workflow, is
  // half a provenance and this window shows none rather than half.
  if ((row.workflow_id === null) !== (row.revision === null)) return null;
  if (row.workflow_id !== null
      && (!isId(row.workflow_id) || !Number.isInteger(row.revision)
          || row.revision < 1)) {
    return null;
  }
  if (!isId(row.cycle_id) || !isInstant(row.created_at)) return null;
  if (!CONTROL_MODES.includes(row.mode)) return null;
  if (!RUN_STATES.includes(row.envelope_status)) return null;
  if (row.graph_id !== null && !isId(row.graph_id)) return null;
  if (!isCount(row.undecided_gates) || !isCount(row.open_actions)) return null;
  if (row.last_outcome !== null
      && !RESULT_OUTCOMES.includes(row.last_outcome)) return null;
  return Object.freeze({
    runId: row.run_id,
    unreadable: false,
    cycleId: row.cycle_id,
    createdAt: row.created_at,
    mode: row.mode,
    envelopeStatus: row.envelope_status,
    graphId: row.graph_id,
    undecidedGates: row.undecided_gates,
    openActions: row.open_actions,
    lastOutcome: row.last_outcome,
    workflow: row.workflow_id === null ? null
      : Object.freeze({id: row.workflow_id, revision: row.revision}),
  });
}

//: `GET /command/runs`. A run row is navigation: a row this window cannot read
//: refuses the list rather than disappearing from it.
export function projectRuns(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, RUNS_KEYS)) return null;
  if (!Array.isArray(payload.runs)) return null;
  const rows = [];
  const seen = new Set();
  for (const row of payload.runs) {
    const settled = projectRunRow(row);
    if (settled === null) return null;
    if (seen.has(settled.runId)) return null;
    seen.add(settled.runId);
    rows.push(settled);
  }
  return Object.freeze({
    runs: frozenList(rows),
    providers: projectProviders(payload.providers),
  });
}

const RUN_READ_KEYS = ["run", "config", "records", "warnings", "graph"];
const RECORD_ROW_KEYS = ["record_type", "record"];
//: A frozen configuration as the PRODUCT writes it, in the same closed-set
//: shape the cycle below already needed. `workflow` is written only by the
//: open-run route and only when a run follows a plan at all: `conduct preview`
//: and the control loop freeze no workflow reference, and a run that names none
//: is a run this window must still be able to OPEN.
//:
//: The pair is REQUIRED-plus-OPTIONAL rather than exact for exactly the reason
//: the cycle is. An exact set of two refuses every run that records its plan;
//: an exact set of three refuses every run that does not. Both mistakes are the
//: same mistake the cycle already made once, when a boundary demanding `{id}`
//: refused the `{id, phases}` the first run most people ever have.
const CONFIG_REQUIRED = ["cycle", "instances"];
const CONFIG_KEYS = ["cycle", "instances", "workflow"];
//: Both halves or neither: a workflow at no revision names a plan whose shape
//: nobody can fetch, and a revision of nothing names no plan at all. Named
//: RUN_ for the reference a RUN froze; `WORKFLOW_KEYS` above is a different
//: document -- the workflow read's own payload -- and one module scope holds
//: both.
const RUN_WORKFLOW_KEYS = ["id", "revision"];
//: A frozen cycle as the PRODUCT writes it, rather than as one road writes it.
//: `command/studio_contracts.py RunInput.snapshot` -- the Studio's own open-run
//: route -- writes `{id}`. `command/preview.py FROZEN_CONFIG` and
//: `command/control_loop.py FROZEN_CONFIG` write `{id, phases}`, through the
//: same `RunStore.create_run` into the same runs directory this window lists,
//: so a run from `conduct preview` or from the integration smoke is a run this
//: window must be able to OPEN and not merely list.
//:
//: `phases` is admitted and it is not read: this window takes nothing out of a
//: cycle but its id, and the word's owner (`schema.py`, `cycle.phases must be a
//: list of strings`) puts no id grammar on a phase name, so neither does this
//: copy. The set stays CLOSED all the same -- a cycle carrying a third key is a
//: configuration written by something this window has never been told about,
//: and it refuses the read whole rather than reading the half it recognises.
const CYCLE_REQUIRED = ["id"];
const CYCLE_KEYS = ["id", "phases"];
//: An instance entry omits `model` rather than spelling it null: the frozen
//: configuration reads absence as "this build pinned none", and refuses an
//: explicit null, because a configuration that chose a value chose one that is
//: not a model id.
const INSTANCE_REQUIRED = ["id", "adapter"];
const INSTANCE_KEYS = ["id", "adapter", "model"];

function projectEnvelope(value) {
  if (!isPlainObject(value)) return null;
  if (!ENVELOPE_KEYS.every((key) => has(value, key))) return null;
  if (!isId(value.run_id) || !isId(value.cycle_id)) return null;
  if (!isInstant(value.created_at) || !isDigest(value.config_digest)) {
    return null;
  }
  if (!CONTROL_MODES.includes(value.mode)) return null;
  if (!RUN_STATES.includes(value.status)) return null;
  if (!Number.isInteger(value.schema_version)) return null;
  return Object.freeze({
    runId: value.run_id,
    cycleId: value.cycle_id,
    createdAt: value.created_at,
    configDigest: value.config_digest,
    mode: value.mode,
    envelopeStatus: value.status,
    schemaVersion: value.schema_version,
  });
}

function projectInstance(row) {
  if (!isPlainObject(row)) return null;
  const own = Object.keys(row);
  if (!own.every((key) => INSTANCE_KEYS.includes(key))) return null;
  if (!INSTANCE_REQUIRED.every((key) => has(row, key))) return null;
  if (!isId(row.id) || !isId(row.adapter)) return null;
  if (has(row, "model") && !isId(row.model)) return null;
  return Object.freeze({
    id: row.id, adapter: row.adapter,
    model: has(row, "model") ? row.model : null,
  });
}

function projectWorkflowRef(value) {
  if (!has(value, "workflow")) return null;
  const row = value.workflow;
  if (!isPlainObject(row) || !exactKeys(row, RUN_WORKFLOW_KEYS)) return undefined;
  if (!isId(row.id) || !Number.isInteger(row.revision) || row.revision < 1) {
    return undefined;
  }
  return Object.freeze({id: row.id, revision: row.revision});
}

function projectConfig(value) {
  if (!isPlainObject(value)
      || !Object.keys(value).every((key) => CONFIG_KEYS.includes(key))
      || !CONFIG_REQUIRED.every((key) => has(value, key))) {
    return null;
  }
  // `undefined` is a malformed reference and `null` is an absent one: a run
  // that froze no workflow is ordinary, and a run whose reference will not read
  // is a configuration written by something this window has never been told
  // about, so it refuses the read whole rather than showing half a provenance.
  const workflow = projectWorkflowRef(value);
  if (workflow === undefined) return null;
  const cycle = value.cycle;
  if (!isPlainObject(cycle)
      || !Object.keys(cycle).every((key) => CYCLE_KEYS.includes(key))
      || !CYCLE_REQUIRED.every((key) => has(cycle, key))) {
    return null;
  }
  // The id is read; `phases` is only held to its shape. A cycle whose phases
  // are not a list of names is a configuration written by something this
  // window does not know, and it refuses the read rather than reading past it.
  if (!isId(cycle.id)
      || (has(cycle, "phases")
          && (!Array.isArray(cycle.phases) || !cycle.phases.every(isText)))) {
    return null;
  }
  if (!Array.isArray(value.instances)) return null;
  const instances = [];
  const seen = new Set();
  for (const row of value.instances) {
    const settled = projectInstance(row);
    if (settled === null || seen.has(settled.id)) return null;
    seen.add(settled.id);
    instances.push(settled);
  }
  return Object.freeze({
    cycleId: value.cycle.id, instances: frozenList(instances),
    workflow,
  });
}

function projectRecords(rows) {
  if (!Array.isArray(rows)) return null;
  const out = [];
  for (const row of rows) {
    if (!isPlainObject(row) || !exactKeys(row, RECORD_ROW_KEYS)) return null;
    if (!RECORD_KINDS.includes(row.record_type)) return null;
    if (!isPlainObject(row.record) || !isJson(row.record, 0)) return null;
    out.push(Object.freeze({
      recordType: row.record_type, record: frozenJson(row.record),
    }));
  }
  return frozenList(out);
}

//: `GET /command/runs/<id>` -- one run read whole.
//:
//: The journal travels in APPEND ORDER and every row is kept: a timeline may
//: never invent a step the journal does not hold and may never skip one it
//: does, so a row this build cannot name refuses the read. What each record
//: MEANS is not settled here -- the field contracts belong to
//: command-projection.js, which the view layer already owns -- and neither is
//: the graph, whose wire spelling graph-adapter.js is the one module allowed to
//: know. Both are carried as frozen copies of shapes this module has checked
//: and read nothing out of.
export function projectRunRead(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, RUN_READ_KEYS)) {
    return null;
  }
  const run = projectEnvelope(payload.run);
  if (run === null) return null;
  const config = projectConfig(payload.config);
  if (config === null) return null;
  const records = projectRecords(payload.records);
  if (records === null) return null;
  if (!Array.isArray(payload.warnings)
      || !payload.warnings.every(isText)) return null;
  if (payload.graph !== null
      && (!isPlainObject(payload.graph) || !isJson(payload.graph, 0))) {
    return null;
  }
  return Object.freeze({
    run,
    config,
    records,
    warnings: frozenList(payload.warnings.slice()),
    graph: payload.graph === null ? null : frozenJson(payload.graph),
  });
}

// ── controls ─────────────────────────────────────────────────────────────
const CONTROLS_KEYS = ["instances", "providers"];
const CONTROL_ROW_KEYS = ["instance_id", "adapter_id", "model", "controls"];

//: `GET /command/runs/<id>/controls`. `model` is nullable and the null is
//: load-bearing: it says the frozen configuration pinned none, so whatever the
//: provider's own configuration decides is what will run. A row that OMITTED
//: the key would be a server too old to answer the question, and this window
//: must be able to tell the two apart -- so the key is required and its value
//: may be null.
//:
//: Two rows for one instance are two answers to one question and neither
//: survives, identical rows included: what is wrong is that the server answered
//: twice about one instance, and rows that happen to agree today are not
//: evidence about the pair that does not.
export function projectControls(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, CONTROLS_KEYS)) {
    return null;
  }
  if (!Array.isArray(payload.instances)) return null;
  const rows = [];
  const conflicted = new Set();
  for (const row of payload.instances) {
    if (!isPlainObject(row) || !exactKeys(row, CONTROL_ROW_KEYS)) return null;
    if (!isId(row.instance_id) || !isId(row.adapter_id)) return null;
    if (row.model !== null && !isId(row.model)) return null;
    if (!Array.isArray(row.controls) || !row.controls.every(isId)) return null;
    if (rows.some((kept) => kept.instanceId === row.instance_id)) {
      conflicted.add(row.instance_id);
      continue;
    }
    rows.push(Object.freeze({
      instanceId: row.instance_id,
      adapterId: row.adapter_id,
      model: row.model,
      controls: frozenList(row.controls.slice()),
    }));
  }
  return Object.freeze({
    instances: frozenList(rows.filter(
      (row) => !conflicted.has(row.instanceId))),
    providers: projectProviders(payload.providers),
  });
}
