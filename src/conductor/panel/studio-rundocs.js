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
import {localize} from "./studio-i18n.js";
import {element} from "./command-view.js";
import {CAPABILITY_FIELDS} from "./command-projection.js";
import {boundDocument, endingOf} from "./studio-runread.js";
import {
  ARTIFACT_CONTENT_LIMIT,
  ARTIFACT_MEDIA_TYPES,
  MATERIAL_BINDING,
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
//: The kinds the reviewed projection marks a step's INPUTS with, and the one
//: field a dispatch reads its instruction under.
const INPUT_KINDS = Object.freeze(["artifact-ids", "artifact-ids-required"]);
const INSTRUCTION_FIELD = "instruction_ref";
//: `contract_values._id`'s budget, and the form this whole file is about.
const ID_LIMIT = 128;
const FORM = "document";

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function plain(value) { return typeof value === "string" ? value : ""; }

function show(value, state = {}) {
  if (value === null || value === undefined || value === "") return localize(state, "run_docs.not_stated");
  return String(value);
}

function note(value) {
  return element("p", {className: "studio-note", text: value});
}

function fact(label, value, attributes, state = {}) {
  return element("p", Object.assign({className: "studio-fact"},
    attributes || {}), [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v", text: show(value, state)}),
  ]);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

function mountedWithout(name, state) {
  return localize(state, "run_docs.missing_handler", {name: String(name)});
}

function runOf(detail) {
  return (object(detail.run) || {}).run_id;
}

function byteLength(value) {
  return new TextEncoder().encode(value).length;
}

// -- what the plan reads --------------------------------------------------------

/**
 * The references one step READS, as the reviewed schema marks its arguments.
 *
 * In argument order and once each; a dispatch's `artifact_refs`, a review's
 * `target_artifact_refs`. The instruction reference is not among them: it is
 * read under its own field and said under its own fact.
 *
 * @param {string} capability The step's capability, a key of the schema.
 * @param {object} held The step's arguments, the plan's or a proposal's.
 * @returns {Array<string>} The references, possibly none.
 */
export function inputRefs(capability, held) {
  const found = [];
  const arguments_ = object(held) || {};
  for (const [name, kind] of rows(CAPABILITY_FIELDS[capability])) {
    if (!INPUT_KINDS.includes(kind)) continue;
    for (const ref of rows(arguments_[name])) {
      if (typeof ref === "string" && !found.includes(ref)) found.push(ref);
    }
  }
  return found;
}

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
    inputRefs(node.capability, node.arguments).forEach(take);
    take((object(node.arguments) || {})[INSTRUCTION_FIELD]);
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
function whyNotPublishable(ref, refs, content, bytes, state) {
  if (!refs.includes(ref)) return localize(state, "run_docs.choose_reference");
  if (!content.trim()) {
    return localize(state, "run_docs.empty_body");
  }
  if (bytes > ARTIFACT_CONTENT_LIMIT) {
    return localize(state, "run_docs.over_limit", {over: String(bytes - ARTIFACT_CONTENT_LIMIT), limit: String(ARTIFACT_CONTENT_LIMIT)});
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
function contentControl(value, edit, size, state) {
  const control = element("textarea", {"data-focus-key": "field:content",
    name: "content", rows: "8", spellcheck: "false"});
  control.value = value;
  if (edit === null) control.disabled = true;
  else {
    control.addEventListener("change", () => edit({content: control.value}));
    control.addEventListener("input", () => {
      size.textContent = localize(state, "run_docs.size", {bytes: String(byteLength(control.value)), limit: String(ARTIFACT_CONTENT_LIMIT)});
    });
  }
  return element("label", {className: "studio-field"}, [
    element("span", {text: localize(state, "run_docs.body_label", {limit: String(ARTIFACT_CONTENT_LIMIT)})}), control,
  ]);
}

//: Start from a document this run already holds: its bytes and its kind are
//: copied into the editor, where a person still reads and publishes them.
function copyControls(documents, edit, state) {
  if (!documents.length) {
    return [note(localize(state, "run_docs.no_source"))];
  }
  const from = element("select", {"data-focus-key": "field:start_from",
    name: "start_from"}, documents.map((row) => option(row.artifact_id,
    `${show(row.artifact_id, state)} · ${show(row.artifact_ref, state)} · `
      + `${show(row.media_type, state)}`)));
  const copy = element("button", {className: "studio-btn",
    "data-focus-key": "document:copy", text: localize(state, "run_docs.copy"),
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
    element("span", {text: localize(state, "run_docs.start_from")}), from]), copy];
}

function submitControl(stops, shut, missing, writing, live, state) {
  const button = element("button", {"data-focus-key": "document:publish",
    text: localize(state, "run_docs.publish_this"), type: "submit"});
  button.disabled = stops !== null || shut;
  const said = [];
  if (writing) said.push(note(localize(state, "run_docs.writing")));
  if (!live) said.push(note(localize(state, "run_docs.stream_down")));
  if (stops !== null) said.push(note(stops));
  if (missing !== null) said.push(note(mountedWithout(missing, state)));
  return [button, ...said];
}

// -- the section ----------------------------------------------------------------

//: The form, drawn from the plan, the journal and the draft.
/**
 * The task channel of each participant this run binds, and the bound its WHOLE task meets.
 *
 * A published document travels inside the doer's task, so a person preparing input is told the
 * bound the server states for each adapter this run names (review ruling R2), never one number
 * for every channel. The fact is read off the controls answer; an adapter it states none for is
 * not named.
 */
export function channelNotes(detail) {
  const said = new Map();
  for (const row of rows((object(detail.controls) || {}).instances)) {
    const channel = object((object(row) || {}).task_channel);
    if (channel !== null && !said.has(row.adapter_id)) {
      said.set(row.adapter_id, {adapter: row.adapter_id, channel: channel.channel,
        limit: channel.limit});
    }
  }
  return [...said.values()].sort((a, b) => (a.adapter < b.adapter ? -1 : 1));
}

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
  const stops = whyNotPublishable(ref, refs, content, bytes, state);
  const size = element("span", {className: "studio-fact__v",
    text: localize(state, "run_docs.size", {bytes: String(bytes), limit: String(ARTIFACT_CONTENT_LIMIT)})});
  const form = element("form", {className: "studio-step", "data-step": FORM}, [
    element("h4", {text: localize(state, "run_docs.heading")}), note(localize(state, "run_docs.publish_note")),
    ...channelNotes(detail).map((row) => note(localize(state, `run_docs.channel_${row.channel}`,
      {adapter: row.adapter, limit: String(row.limit)}))),
    selectControl("artifact_ref", "artifactRef", ref,
      [{value: "", label: localize(state, "run_docs.reference_placeholder")}].concat(
        refs.map((row) => ({value: row, label: row}))),
      edit, localize(state, "run_docs.reference_label")),
    fact(localize(state, "run_docs.document_id"), minted === null
      ? localize(state, "run_docs.minted_id") : minted, null, state),
    selectControl("media_type", "mediaType", media,
      ARTIFACT_MEDIA_TYPES.map((row) => ({value: row, label: row})), edit,
      localize(state, "run_docs.media_type")),
    contentControl(content, edit, size, state),
    element("p", {className: "studio-fact", "data-document-bytes": String(bytes)},
      [element("span", {className: "studio-fact__k", text: localize(state, "run_docs.size_label")}), size]),
    ...copyControls(documents, edit, state),
    ...submitControl(stops, shut, submit === null ? "publishDocument"
      : (edit === null ? "editDocument" : null), writing, live, state),
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
  const graph = object(detail.graph);
  const ending = endingOf(detail, graph === null ? null : graph.schedule);
  // A run that is over -- its plan's own word, or the ending it recorded --
  // offers no step a document any more, so the form is not drawn: the
  // server refuses a recorded terminal (`run_terminal`) and a complete plan
  // would keep a document nothing reads. What is over is said.
  const body = ending.ended
    ? [note(localize(state, "run_docs.ended", {ending: ending.plan_word === null ? localize(state, "run_docs.ending_recorded")
      : localize(state, "run_docs.ending_plan", {status: planEnding(ending.plan_word, state)})}))]
    : refs.length
      ? [documentForm(detail, state, handlers, refs)]
      : [note(localize(state, "run_docs.no_references"))];
  return element("section", {className: "studio-section",
    "data-section": "documents"},
  [element("h3", {text: localize(state, "run_docs.heading")}), ...body]);
}

/**
 * The sources a step's LATEST proposal bound, said beside the step.
 *
 * The instruction, for a step whose arguments name an instruction reference,
 * and every input the reviewed schema marks; only on a step on which a
 * proposal stands or stood. What it bound is what that proposal runs when
 * confirmed, and a document published since is not it.
 *
 * @param {object} detail The whole run read.
 * @param {object} node The plan's frozen node.
 * @returns {Array<Element>} One fact per bound source, or none.
 */
export function boundSources(detail, node, state = {}) {
  const held = object(node.arguments) || {};
  const ref = held[INSTRUCTION_FIELD];
  const inputs = inputRefs(node.capability, held);
  if (typeof ref !== "string" && !inputs.length) return [];
  const proposals = rows(detail.records)
    .filter((row) => row.record_type === "action_proposal")
    .map((row) => object(row.record) || {})
    .filter((record) => record.node_id === node.node_id);
  if (!proposals.length) return [];
  const latest = proposals[proposals.length - 1];
  if (latest.input_binding !== MATERIAL_BINDING) {
    return [note(localize(state, "run_docs.unversioned"))];
  }
  const bound = (source) => boundDocument(
    rows(detail.records), latest.proposal_id, source);
  const said = [];
  if (typeof ref === "string") {
    const found = bound(ref);
    said.push(fact(localize(state, "run_docs.bound_instruction", {ref, proposal: show(latest.proposal_id, state)}),
      found === null ? localize(state, "run_docs.local_instruction", {ref})
        : localize(state, "run_docs.bound_document", {id: show(found.artifact_id, state)}), null, state));
  }
  for (const input of inputs) {
    const found = bound(input);
    said.push(fact(localize(state, "run_docs.bound_input", {ref: input, proposal: show(latest.proposal_id, state)}),
      found === null ? localize(state, "run_docs.missing_document")
        : localize(state, "run_docs.bound_document", {id: show(found.artifact_id, state)}), null, state));
  }
  return said;
}

// Only the server's declared argument schema establishes this legacy hold.
// A native or other capability is not classified by its argument spellings.
export function needsMaterialReproposal(proposal, detail) {
  if (proposal === null || proposal.input_binding === MATERIAL_BINDING
      || !["dispatch", "review"].includes(proposal.capability)) return false;
  const controls = object(detail.controls) || {};
  const instance = rows(controls.instances).find(
    (row) => row.instance_id === proposal.instance_id) || {};
  const schemas = object(instance.argument_schemas) || {};
  return schemas[proposal.capability] === "deep-arguments-v1";
}

//: Stored as its key, so the sentence on screen switches with the language.
export function publishedNote(_state = {}) {
  return Object.freeze({key: "run_docs.published"});
}

function planEnding(value, state) {
  return ["complete", "cancelled", "failed"].includes(value)
    ? localize(state, `run_docs.ending_${value}`) : String(value);
}
