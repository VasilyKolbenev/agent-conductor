"use strict";
// The pure rules of connecting git and of the first commit (spec 9.8, lane L's contract), as
// functions of plain values: which answer of the route is which, what a body is made of, and what
// the two terminal commands of a wait for the owner's signature are.
//
// Nothing here keeps state, reaches a clock, a store or a wire, and nothing is imported: the
// state that holds a press is `desk-wizard-git-run.js`, the words are `desk-wizard-git-copy.js`,
// and what is drawn is `desk-wizard-git-view.js`.
//
// Every answer is taken only with its exact keys (a shape the contract does not have is `null`,
// never a guess), and every free text of an answer (`requested_by`, `author`, a branch, a path)
// stays a string to be drawn as text: nothing here parses it, and none of it but `signing.*`,
// held to its own safe set, ever reaches a command.

//: THE switch of the first commit's confirmation. It is open since lane L opened the route
//: (8.7), in the same candidate: the desk sends the confirm and the continue. Were it false, the
//: desk would send neither and draw the controls that would send them disabled with their
//: reason. It has one reader, `initialGit`, and the guard that holds it to lane L's route.
export const FIRST_COMMIT_CONFIRM_OPEN = true;

//: The twenty closed reasons of `409 git_setup_refused` (`error.detail.reason`), the order of the
//: route's own list, each with a notice in the catalogue (`git_setup.reason.<reason>`).
export const GIT_SETUP_REASONS = Object.freeze([
  "already_git", "not_a_git_repository", "project_not_repo_root", "tracks_product_dir",
  "unsafe_directory", "unsafe_git_route", "git_exclude_failed", "git_identity_missing",
  "head_exists", "index_exists", "index_locked", "too_many_files", "paths_changed",
  "setup_damaged", "setup_terms_changed", "task_run_active", "git_failed", "git_timed_out",
  "signing_required", "signing_ref_unsupported"]);
//: The other codes the route answers with that the desk reads: each has an `error.<code>` notice.
export const GIT_SETUP_CODES = Object.freeze(["project_not_active", "contract_invalid",
  "windows_path_too_long", "tool_unavailable"]);
//: Refusals the desk's own door gives without sending anything: the target is not wired in this
//: build, or the window is bound to another project. They say nothing about the repository.
export const UNSENT_CODES = Object.freeze(["route_not_found", "project_mismatch"]);
//: What a press does about each reason: offer the same press again, prepare a new preview, wait
//: for the person's signature, finish with the original terms, or nothing.
export const REFUSAL_ACTIONS = Object.freeze({
  already_git: "none", not_a_git_repository: "none", project_not_repo_root: "none",
  tracks_product_dir: "none", unsafe_directory: "none", unsafe_git_route: "none",
  git_exclude_failed: "none", git_identity_missing: "none", head_exists: "none",
  index_exists: "none", index_locked: "retry", too_many_files: "none", paths_changed: "new_preview",
  setup_damaged: "none", setup_terms_changed: "original", task_run_active: "none",
  git_failed: "none", git_timed_out: "retry", signing_required: "wait",
  signing_ref_unsupported: "new_preview"});
//: The words of a preview's `warnings`, and of a `manual` row's reason, that the desk has its own
//: sentence for. Any other warning is said by its code; any other reason, by a general sentence
//: that says the file is left out and carries the code.
export const WARNING_WORDS = Object.freeze(["signing_required", "suspicious_name",
  "nested_repository"]);
//: The eight values `manual[].reason` takes in the current preview (`git_setup_snapshot._manual`):
//: its own three and the codes of `portal_violation` and `first_directory_violation`. The twelve of
//: `RouteViolationCode` are that set united with codes this path never gives.
export const MANUAL_REASONS = Object.freeze(["symlink", "junction", "reparse_point", "hard_link",
  "irregular_file", "unportable_name", "unreadable", "not_directory"]);
export const MODES = Object.freeze(["snapshot", "empty"]);
//: The presses a `sending` record can name: the four bodies and the continue of the confirm.
export const KINDS = Object.freeze(["init", "exclude", "preview", "confirm", "continue"]);

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const OID = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/;
const SAFE_BRANCH = /^refs\/heads\/[A-Za-z0-9._/-]+$/;
const MESSAGE_PATH = /^conductor(?:\.v3)?\/git\/msg-first-[0-9a-f]{32}\.txt$/;
const CONTROL = /[\u0000-\u001f\u007f]/;
const WORD = /^[a-z_]{1,32}$/;
const TEXT_LIMIT = 1024;
const BRANCH_LIMIT = 240;
const FILE_LIMIT = 5000;

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function keysAre(value, names) {
  return record(value) && Object.keys(value).sort().join(",") === [...names].sort().join(",");
}

function text(value, limit = TEXT_LIMIT) {
  return typeof value === "string" && value.length > 0 && value.length <= limit
    && !CONTROL.test(value);
}

function branch(value) {
  return text(value, BRANCH_LIMIT) && value.startsWith("refs/heads/") && value.length > 11;
}

function frozen(value) {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const item of Object.values(value)) frozen(item);
  return Object.freeze(value);
}

//: The message the product gives an empty first commit (lane L's contract, section 3: fixed, not a
//: setting). The page may show it beside the starter's second step; a test holds it to the
//: product's own constant.
export const EMPTY_COMMIT_MESSAGE = "Начало проекта (Conduct)";

//: The slice the wizard keeps for this block: the switch (copied once from the literal above), the
//: door (whether the desk's transport has the target the setup route is reached by: only an
//: explicit `false` closes it, so a host that does not say is not blamed), the panel and the mode
//: the person chose, the validated preview, the press counter, the request in flight, the last
//: answer's words and the starter's chain of two steps (null until it is pressed).
export function initialGit(open, door = true) {
  return {open: open === true, door: door !== false, panel: null, mode: null, preview: null,
    list: false, seq: 0, sending: null, result: null, chain: null};
}

// -- the shapes of the answers --------------------------------------------------------------

function authorHolds(author) {
  return keysAre(author, ["name", "email"]) && text(author.name) && text(author.email);
}

function fileRow(row) {
  return keysAre(row, ["path", "length", "sha256", "git_oid", "git_mode"]) && text(row.path, 4096)
    && Number.isSafeInteger(row.length) && row.length >= 0 && DIGEST.test(row.sha256)
    && OID.test(row.git_oid) && ["100644", "100755"].includes(row.git_mode);
}

function manualRow(row) {
  return keysAre(row, ["path", "reason"]) && text(row.path, 4096) && WORD.test(row.reason ?? "");
}

const PREVIEW_KEYS = ["step", "mode", "head", "target_ref", "object_format", "author", "signing",
  "files", "manual", "warnings", "digest_version", "paths_digest"];

function previewHolds(found, mode) {
  const rows = (list, one) => Array.isArray(list) && list.length <= FILE_LIMIT && list.every(one);
  return keysAre(found, PREVIEW_KEYS) && found.step === "first_commit" && found.mode === mode
    && found.head === null && branch(found.target_ref)
    && ["sha1", "sha256"].includes(found.object_format) && authorHolds(found.author)
    && typeof found.signing === "boolean" && rows(found.files, fileRow)
    && rows(found.manual, manualRow) && Array.isArray(found.warnings)
    && found.warnings.every((word) => typeof word === "string" && WORD.test(word))
    && found.digest_version === 2 && DIGEST.test(found.paths_digest)
    && (mode !== "empty" || (found.files.length === 0 && found.manual.length === 0));
}

/** The route's `{setup: PREVIEW}` for `mode`, deep-frozen, or null unless it is exactly that. */
export function projectPreview(payload, mode) {
  if (!keysAre(payload, ["setup"]) || !MODES.includes(mode)) return null;
  return previewHolds(payload.setup, mode) ? frozen(structuredClone(payload.setup)) : null;
}

const RECEIPT_KEYS = ["schema_version", "step", "mode", "paths_digest", "digest_version",
  "target_ref", "commit", "tree", "object_format", "file_count", "signature", "requested_by",
  "recorded_at"];

function receiptHolds(found) {
  return keysAre(found, RECEIPT_KEYS) && found.schema_version === 1
    && found.step === "first_commit" && MODES.includes(found.mode)
    && (found.paths_digest === null ? found.mode === "empty"
      : found.mode === "snapshot" && DIGEST.test(found.paths_digest))
    && found.digest_version === 2 && branch(found.target_ref) && OID.test(found.commit)
    && OID.test(found.tree) && ["sha1", "sha256"].includes(found.object_format)
    && Number.isSafeInteger(found.file_count) && found.file_count >= 0
    && ["not_required", "present"].includes(found.signature) && text(found.requested_by)
    && text(found.recorded_at, 64);
}

/** The receipt `{setup: RECEIPT}` of a first commit, deep-frozen, or null. */
export function projectReceipt(payload) {
  if (!keysAre(payload, ["setup"])) return null;
  return receiptHolds(payload.setup) ? frozen(structuredClone(payload.setup)) : null;
}

const STEP_KEYS = ["schema_version", "step", "requested_by", "recorded_at", "object_format",
  "exclude", "warnings"];

/** The receipt of `init` or `exclude`, deep-frozen, or null. */
export function projectStepReceipt(payload, step) {
  if (!keysAre(payload, ["setup"]) || !["init", "exclude"].includes(step)) return null;
  const found = payload.setup;
  const good = keysAre(found, STEP_KEYS) && found.schema_version === 1 && found.step === step
    && text(found.requested_by) && text(found.recorded_at, 64)
    && ["sha1", "sha256"].includes(found.object_format)
    && ["written", "present"].includes(found.exclude) && Array.isArray(found.warnings)
    && (found.warnings.length === 0 || (found.warnings.length === 1
      && found.warnings[0] === "nested_repository"));
  return good ? frozen(structuredClone(found)) : null;
}

// -- the pending first commit ---------------------------------------------------------------

function termsHold(terms) {
  return keysAre(terms, ["mode", "paths_digest", "digest_version", "requested_by", "file_count",
    "target_ref", "author"]) && MODES.includes(terms.mode)
    && (terms.paths_digest === null ? terms.mode === "empty"
      : terms.mode === "snapshot" && DIGEST.test(terms.paths_digest))
    && terms.digest_version === 2 && text(terms.requested_by)
    && Number.isSafeInteger(terms.file_count) && terms.file_count >= 0
    && terms.file_count <= FILE_LIMIT && branch(terms.target_ref) && authorHolds(terms.author);
}

function signingHolds(signing, terms) {
  return keysAre(signing, ["tree", "target_ref", "message_path"]) && OID.test(signing.tree)
    && SAFE_BRANCH.test(signing.target_ref) && signing.target_ref.length <= BRANCH_LIMIT
    && signing.target_ref === terms.target_ref && MESSAGE_PATH.test(signing.message_path);
}

/**
 * What the read's `first_commit_pending` says, taken only in its closed shapes: null (nothing
 * pending), `{state: "unfinished", terms}`, `{state: "awaiting_signature", terms, signing}`,
 * `{state: "damaged"}`. Anything else, an absent key included, is `{state: "unreadable"}`: the
 * desk then offers nothing to send and does not say a first commit is done.
 */
export function projectPending(value) {
  const unreadable = Object.freeze({state: "unreadable"});
  if (value === null) return null;
  if (!record(value)) return unreadable;
  if (keysAre(value, ["state"])) {
    return value.state === "damaged" ? Object.freeze({state: "damaged"}) : unreadable;
  }
  const stored = value.state === "unfinished" && keysAre(value, ["state", "terms"])
    && termsHold(value.terms);
  if (stored) return frozen(structuredClone(value));
  const waits = value.state === "awaiting_signature"
    && keysAre(value, ["state", "terms", "signing"]) && termsHold(value.terms);
  return waits && signingHolds(value.signing, value.terms) ? frozen(structuredClone(value))
    : unreadable;
}

/**
 * The pending first commit of the one git read: null when the read has not landed or failed, when
 * it says nothing is pending, or when the server is older than the key (it then has no operation
 * of the product to leave pending); otherwise `projectPending` of what the read carries.
 */
export function pendingOf(read) {
  const git = read && read.status === "ok" ? read.payload?.git : null;
  if (!record(git) || !Object.hasOwn(git, "first_commit_pending")) return null;
  return projectPending(git.first_commit_pending);
}

/**
 * The two commands of a wait for the person's signature, from `signing` ALONE (never from the
 * stored terms: a branch there is any name Git accepts). Each value is checked against its own safe
 * set and put in verbatim, with no quoting; `<oid>` stays literal, it is what the first command
 * prints. Null when a value leaves its set, so no command is ever composed from one.
 */
export function signCommands(signing) {
  if (!keysAre(signing, ["tree", "target_ref", "message_path"]) || !OID.test(signing.tree)
      || !SAFE_BRANCH.test(signing.target_ref) || signing.target_ref.length > BRANCH_LIMIT
      || !MESSAGE_PATH.test(signing.message_path)) return null;
  return Object.freeze({
    commit: `git commit-tree ${signing.tree} -S -F ${signing.message_path}`,
    update: `git update-ref ${signing.target_ref} <oid> ${"0".repeat(signing.tree.length)}`});
}

// -- the bodies -----------------------------------------------------------------------------

export const stepBody = (step, actor) => Object.freeze({step, actor});

export const previewBody = (mode) => Object.freeze({step: "first_commit", mode, preview: true});

//: The confirm: `paths_digest` is the preview's digest for a snapshot and exactly null for an
//: empty first commit (the preview of an empty one still carries the digest of the empty list).
export function confirmBody(mode, preview, actor) {
  return Object.freeze({step: "first_commit", mode,
    paths_digest: mode === "empty" ? null : preview.paths_digest, actor});
}

//: The continue is the same body, built from the stored terms and the actor of NOW. The stored
//: `requested_by` is never the actor of the continue.
export function continueBody(terms, actor) {
  return Object.freeze({step: "first_commit", mode: terms.mode, paths_digest: terms.paths_digest,
    actor});
}

// -- what an answer was ---------------------------------------------------------------------

function toolOf(detail) {
  const tool = record(detail) ? detail.tool : undefined;
  const why = record(detail) ? detail.reason : undefined;
  return WORD.test(tool ?? "") && WORD.test(why ?? "") ? {name: tool, reason: why} : null;
}

function refusal(kind, result) {
  const code = typeof result.code === "string" ? result.code : "";
  if (UNSENT_CODES.includes(code)) return {status: "unsent", kind, code};
  const detail = result.payload?.error?.detail;
  if (code === "git_setup_refused") {
    const reason = record(detail) ? detail.reason : undefined;
    return GIT_SETUP_REASONS.includes(reason)
      ? {status: "refused", kind, code, reason, tool: null}
      : {status: "lost", kind, cause: "unlisted"};
  }
  if (GIT_SETUP_CODES.includes(code)) {
    return {status: "refused", kind, code, reason: null,
      tool: code === "tool_unavailable" ? toolOf(detail) : null};
  }
  return {status: "lost", kind, cause: code === "store_error" ? "store_error" : "unlisted"};
}

function accepted(kind, result, mode) {
  if (kind === "preview") {
    const preview = projectPreview(result.payload, mode);
    return preview === null ? null : {status: "done", kind, preview, receipt: null};
  }
  const receipt = kind === "init" || kind === "exclude"
    ? projectStepReceipt(result.payload, kind) : projectReceipt(result.payload);
  return receipt === null ? null : {status: "done", kind, preview: null, receipt};
}

/**
 * What one answer of a press was, from the door's own result `{status, code, payload}`:
 * `done` (the exact answer of this press: a preview or a receipt), `refused` (the route's closed
 * word: a reason of the twenty, or one of the other four codes), `unsent` (the desk's own door
 * turned the press away; nothing reached the route), or `lost` (no answer the desk can read: an
 * unknown outcome, a code outside the table, an accepted answer that is not the exact shape).
 * A lost answer is never a refusal and is never worded as one.
 */
export function classify(kind, result, mode = null) {
  if (!KINDS.includes(kind) || !record(result)) return Object.freeze({status: "lost", kind,
    cause: "unreadable"});
  let found;
  if (result.status === "accepted") {
    found = accepted(kind === "continue" ? "confirm" : kind, result, mode);
    if (found !== null) found = {...found, kind};
    else found = {status: "lost", kind, cause: "unreadable"};
  } else if (result.status === "refused") found = refusal(kind, result);
  else found = {status: "lost", kind, cause: "unknown"};
  return frozen(found);
}
