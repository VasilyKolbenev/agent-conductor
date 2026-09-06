"use strict";
// The one place on the Runs screen that WRITES A DOCUMENT: a durable artifact
// under a reference this run's plan can consume.
//
// R04 of the review of `8dec0e4`: a clean project holds no `instructions/`
// directory and no screen could publish an artifact, so the shipped starter's
// first step -- which reads `instruction-plan` and `artifact-brief` -- could
// not be run from the product, and owner acceptance step 12 sent a person to
// a PowerShell block. The write goes through the ONE mutation door the boot
// module holds, to the `/artifacts` route that already exists, and the
// accepting read is the frame that route already publishes.
//
// NOTHING HERE IS FREE TEXT BUT THE DOCUMENT ITSELF. The reference is chosen
// from what the plan reads -- every step's input list and every dispatch's
// instruction reference, as the reviewed schema marks them -- because a
// document under a reference nothing reads is a record nobody will meet. The
// id is minted from the reference the way an attempt id is minted from its
// step (R09): counted, bounded, never typed. The kind of text is the
// boundary's own closed pair. What a person supplies is the bytes.
//
// It builds fragments and mounts nothing; `studio-runs.js` owns the screen and
// calls this once per run read, under the positions, and once per position
// row for the instruction a step's proposal bound.
import {element} from "./command-view.js";
import {CAPABILITY_FIELDS} from "./command-projection.js";
import {boundDocument} from "./studio-runread.js";
import {
  ARTIFACT_CONTENT_LIMIT,
  ARTIFACT_MEDIA_TYPES,
  STREAM_DOWN_REASON,
  WRITING_NOTE,
} from "./studio-runwords.js";

//: The key a document write holds in the run screen's `writes`, beside the
//: step writes keyed by node id. No plan step can be named this: the id
//: grammar (`contract_values._id`) admits no `@`, so the two namespaces cannot
//: meet, by construction.
export const DOCUMENT_KEY = "@document";
//: What the write MEANS, said by the window after it lands. `studio-runwrite`
//: announces it; the form says the rest before the press.
export const PUBLISHED_NOTE = "The document is a durable record in this run's "
  + "journal. A step waiting for its reference is offered on the read that "
  + "follows, and a proposal made from now on binds it.";
const PUBLISH_NOTE = "A document published here is immutable and is never "
  + "edited or removed: a second document under the same reference stands "
  + "beside the first, and whatever is proposed afterwards binds the newest "
  + "one standing when the proposal is written.";
//: The kinds the reviewed projection marks a step's INPUTS with, and the one
//: field a dispatch reads its instruction under.
const INPUT_KINDS = Object.freeze(["artifact-ids", "artifact-ids-required"]);
const INSTRUCTION_FIELD = "instruction_ref";
//: `contract_values._id`'s budget, and the form this whole file is about.
const ID_LIMIT = 128;
const FORM = "document";
const NOT_STATED = "not stated";

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function plain(value) { return typeof value === "string" ? value : ""; }

function show(value) {
  if (value === null || value === undefined || value === "") return NOT_STATED;
  return String(value);
}

function note(value) {
  return element("p", {className: "studio-note", text: value});
}

function fact(label, value, attributes) {
  return element("p", Object.assign({className: "studio-fact"},
    attributes || {}), [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v", text: show(value)}),
  ]);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

function mountedWithout(name) {
  return `This screen was mounted without a ${name} handler.`;
}

function runOf(detail) {
  return (object(detail.run) || {}).run_id;
}

function byteLength(value) {
  return new TextEncoder().encode(value).length;
}

// -- what the plan reads --------------------------------------------------------

//: Every reference this run's plan can consume, in plan order and once each:
//: the input lists the reviewed schema marks on every step, and every
//: dispatch's instruction reference. Read off the frozen definition, so a
//: document can only be published under a name some step will read.
function consumableRefs(detail) {
  const graph = object(detail.graph);
  const definition = graph === null ? null : object(graph.definition);
  const found = [];
  const take = (ref) => {
    if (typeof ref === "string" && !found.includes(ref)) found.push(ref);
  };
  for (const node of rows(definition === null ? null : definition.nodes)) {
    const held = object(node.arguments) || {};
    for (const [name, kind] of rows(CAPABILITY_FIELDS[node.capability])) {
      if (INPUT_KINDS.includes(kind)) rows(held[name]).forEach(take);
      else if (name === INSTRUCTION_FIELD) take(held[name]);
    }
  }
  return found;
}

//: Every document this run holds, in journal order.
function documentsOf(detail) {
  return rows(detail.records)
    .filter((row) => row.record_type === "artifact")
    .map((row) => object(row.record) || {});
}

// -- the id, minted as an attempt id is minted (R09) ------------------------------

//: FNV-1a, 64 bits, over the UTF-8 bytes of a name. A copy of
//: `studio-runstep.fnv64`, held equal to it by a source guard: the step
//: fragment exports nothing but its builder, and a projection that could be
//: imported from anywhere would be a second place to look for one rule.
function fnv64(text) {
  let hash = 0xcbf29ce484222325n;
  for (const byte of new TextEncoder().encode(text)) {
    hash ^= BigInt(byte);
    hash = (hash * 0x100000001b3n) & 0xffffffffffffffffn;
  }
  return hash.toString(16).padStart(16, "0");
}

function countersUnder(prefix, ids) {
  return ids
    .filter((id) => typeof id === "string" && id.startsWith(prefix))
    .map((id) => id.slice(prefix.length))
    .filter((tail) => /^[0-9]+$/.test(tail))
    .map((tail) => Number(tail));
}

//: The next id under a reference: `<ref>-<n>` while it fits the budget, the
//: digest form `<hex16>.<n>` once it does not. The named form ends in
//: `-<digits>` and the digest form in `.<digits>`, so no id of one form equals
//: any id of the other; `n` is the greatest already spelled under EITHER form
//: plus one, and the minted id is bumped until it is free of the run's whole
//: set -- the server's own refusal stays the authority for what one window
//: cannot see.
function documentId(ref, ids) {
  const named = `${ref}-`;
  const digested = `${fnv64(ref)}.`;
  const taken = [...countersUnder(named, ids), ...countersUnder(digested, ids)];
  const spell = (counter) => {
    const plain = `${named}${counter}`;
    return plain.length <= ID_LIMIT ? plain : `${digested}${counter}`;
  };
  let counter = taken.length ? Math.max(...taken) + 1 : 0;
  let minted = spell(counter);
  while (ids.includes(minted)) minted = spell(++counter);
  return minted;
}

// -- the draft, and what a person sees ----------------------------------------------

//: Whether this run's document write is in flight: membership in the run
//: screen's `writes`, which no read and no change of run alters.
function writingOf(state, runId) {
  const writes = object((object(state.runs) || {}).writes) || {};
  return Object.hasOwn(writes, `${runId}/${DOCUMENT_KEY}`);
}

//: The draft for THIS run, or an empty one carrying the standing generation.
function draftFor(state, runId) {
  const held = object((object(state.runs) || {}).document) || {};
  if (held.runId === runId) return held;
  return {runId, artifactRef: "", mediaType: ARTIFACT_MEDIA_TYPES[0],
    content: "", generation: Number.isInteger(held.generation)
      ? held.generation : 0};
}

//: A copy of `studio-runstep.liveValue`, held equal by a source guard: what
//: the person SEES in the control being replaced is carried into the one
//: drawn in its place, for the same form only.
function liveValue(step, name, fallback) {
  const active = document.activeElement;
  if (!active || !active.getAttribute
      || active.getAttribute("name") !== name
      || typeof active.value !== "string") {
    return fallback;
  }
  const form = active.closest("[data-step]");
  return form !== null && form.getAttribute("data-step") === step
    ? active.value : fallback;
}

//: What stops this document being written, in the person's words, or null.
//: The rules are the boundary's own, asked here so the control refuses beside
//: the person rather than on the wire.
function whyNotPublishable(ref, refs, content, bytes) {
  if (!refs.includes(ref)) return "Choose the reference this document answers.";
  if (!content.trim()) {
    return "Write the document: an empty body is refused at the boundary.";
  }
  if (bytes > ARTIFACT_CONTENT_LIMIT) {
    return `This document is ${bytes - ARTIFACT_CONTENT_LIMIT} bytes over the `
      + `${ARTIFACT_CONTENT_LIMIT}-byte bound, so it cannot be published.`;
  }
  return null;
}

// -- the controls ---------------------------------------------------------------

function option(value, label) {
  return element("option", {text: label === undefined ? value : label, value});
}

function selectControl(name, key, value, choices, edit, label) {
  const control = element("select", {"data-focus-key": `field:${name}`, name},
    choices.map((row) => option(row.value, row.label)));
  control.value = value;
  if (edit === null) control.disabled = true;
  else control.addEventListener("change", () => edit({[key]: control.value}));
  return element("label", {className: "studio-field"}, [
    element("span", {text: label}), control,
  ]);
}

//: The document itself, with its size said live beside it: a bound a person
//: meets only at the press is a bound they meet too late.
function contentControl(value, edit, size) {
  const control = element("textarea", {"data-focus-key": "field:content",
    name: "content", rows: "8", spellcheck: "false"});
  control.value = value;
  if (edit === null) control.disabled = true;
  else {
    control.addEventListener("change", () => edit({content: control.value}));
    control.addEventListener("input", () => {
      size.textContent = `${byteLength(control.value)} of `
        + `${ARTIFACT_CONTENT_LIMIT} bytes`;
    });
  }
  return element("label", {className: "studio-field"}, [
    element("span", {text: `The document (up to ${ARTIFACT_CONTENT_LIMIT} `
      + "bytes of UTF-8)"}), control,
  ]);
}

//: Start from a document this run already holds: its bytes and its kind are
//: copied into the editor, where a person still reads and publishes them.
function copyControls(documents, edit) {
  if (!documents.length) {
    return [note("This run holds no document yet to start from.")];
  }
  const from = element("select", {"data-focus-key": "field:start_from",
    name: "start_from"}, documents.map((row) => option(row.artifact_id,
    `${show(row.artifact_id)} · ${show(row.artifact_ref)} · `
      + `${show(row.media_type)}`)));
  const copy = element("button", {className: "studio-btn",
    "data-focus-key": "document:copy", text: "Copy into the editor",
    type: "button"});
  if (edit === null) copy.disabled = true;
  else {
    copy.addEventListener("click", () => {
      const chosen = documents.find((row) => row.artifact_id === from.value);
      if (chosen === undefined) return;
      edit({content: plain(chosen.content),
        mediaType: plain(chosen.media_type)});
    });
  }
  return [element("label", {className: "studio-field"}, [
    element("span", {text: "Start from an existing document"}), from]), copy];
}

function submitControl(stops, shut, missing, writing, live) {
  const button = element("button", {"data-focus-key": "document:publish",
    text: "Publish this document", type: "submit"});
  button.disabled = stops !== null || shut;
  const said = [];
  if (writing) said.push(note(WRITING_NOTE));
  if (!live) said.push(note(STREAM_DOWN_REASON));
  if (stops !== null) said.push(note(stops));
  if (missing !== null) said.push(note(mountedWithout(missing)));
  return [button, ...said];
}

// -- the section ----------------------------------------------------------------

//: The form, drawn from the plan, the journal and the draft.
function documentForm(detail, state, handlers, refs) {
  const runId = runOf(detail);
  const draft = draftFor(state, runId);
  const edit = handlerOf(handlers, "editDocument");
  const submit = handlerOf(handlers, "publishDocument");
  const live = state.connection === "open";
  const writing = writingOf(state, runId);
  const shut = submit === null || edit === null || !live || writing;
  const ref = liveValue(FORM, "artifact_ref", plain(draft.artifactRef));
  const media = liveValue(FORM, "media_type", plain(draft.mediaType));
  const content = liveValue(FORM, "content", plain(draft.content));
  const bytes = byteLength(content);
  const documents = documentsOf(detail);
  const minted = refs.includes(ref)
    ? documentId(ref, documents.map((row) => row.artifact_id)) : null;
  const stops = whyNotPublishable(ref, refs, content, bytes);
  const size = element("span", {className: "studio-fact__v",
    text: `${bytes} of ${ARTIFACT_CONTENT_LIMIT} bytes`});
  const form = element("form", {className: "studio-step", "data-step": FORM}, [
    element("h4", {text: "Publish a document"}), note(PUBLISH_NOTE),
    selectControl("artifact_ref", "artifactRef", ref,
      [{value: "", label: "choose a reference"}].concat(
        refs.map((row) => ({value: row, label: row}))),
      edit, "Reference this document answers"),
    fact("Document id", minted === null
      ? "minted from the reference once one is chosen" : minted),
    selectControl("media_type", "mediaType", media,
      ARTIFACT_MEDIA_TYPES.map((row) => ({value: row, label: row})), edit,
      "Kind of text"),
    contentControl(content, edit, size),
    element("p", {className: "studio-fact", "data-document-bytes": String(bytes)},
      [element("span", {className: "studio-fact__k", text: "Size"}), size]),
    ...copyControls(documents, edit),
    ...submitControl(stops, shut, submit === null ? "publishDocument"
      : (edit === null ? "editDocument" : null), writing, live),
  ]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (stops !== null || shut || minted === null) return;
    submit({runId, generation: draft.generation, body: {
      artifact_id: minted, artifact_ref: ref, media_type: media,
      content: content}});
  });
  return form;
}

/**
 * The section that publishes a document into this run, or says why none can be.
 *
 * @param {object} detail The whole run read: its records, graph and run.
 * @param {object} state The reducer's frozen value, whole.
 * @param {object} handlers `editDocument(patch)`, `publishDocument(row)`.
 * @returns {Element} One section, always: a plan that reads no document is
 *   told so rather than shown nothing.
 */
export function documentSection(detail, state, handlers) {
  const refs = consumableRefs(detail);
  const body = refs.length
    ? [documentForm(detail, state, handlers, refs)]
    : [note("This run's plan names no document reference: no step reads "
      + "one, so there is nothing a document published here could be for.")];
  return element("section", {className: "studio-section",
    "data-section": "documents"},
  [element("h3", {text: "Publish a document"}), ...body]);
}

/**
 * The instruction a step's LATEST proposal bound, said beside the step.
 *
 * Only for a step whose arguments name an instruction reference and on which
 * a proposal stands or stood; what it bound is what ran or will run, and a
 * document published since is not it.
 *
 * @param {object} detail The whole run read.
 * @param {object} node The plan's frozen node.
 * @returns {Array<Element>} One fact, or none.
 */
export function boundInstruction(detail, node) {
  const held = object(node.arguments) || {};
  const ref = held[INSTRUCTION_FIELD];
  if (typeof ref !== "string") return [];
  const proposals = rows(detail.records)
    .filter((row) => row.record_type === "action_proposal")
    .map((row) => object(row.record) || {})
    .filter((record) => record.node_id === node.node_id);
  if (!proposals.length) return [];
  const latest = proposals[proposals.length - 1];
  const bound = boundDocument(rows(detail.records), latest.proposal_id, ref);
  return [fact(`Instruction ${ref} bound by ${show(latest.proposal_id)}`,
    bound === null ? `the machine's instructions/${ref}.md, if it exists`
      : `durable document ${show(bound.artifact_id)}`)];
}
