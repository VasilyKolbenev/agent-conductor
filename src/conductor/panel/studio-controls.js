"use strict";
// What the controls route says, and what this window will not believe from it.
//
// Split out of `studio-model` when that module stood at its 800-line cap with
// this seam owed. The subject is one route's answer: which capabilities a
// binding declares, and what is actually protecting the run a person is about
// to confirm.
//
// The isolation half is why this is strict. A screen that renders a protection
// the server did not claim is worse than one that renders nothing: it is an
// assurance nobody made. So a standing must be one of four known words, only
// one of which may be drawn as a protection, and the words a row is rendered
// with come from the reference block the SAME answer carried -- never from a
// copy kept here. A second copy in JavaScript is a second table the moment
// either is edited, and the one a person reads would be the one nobody checks
// against the guards.
import {
  exactKeys, frozenJson, frozenList, isId, isPlainObject, projectProviders,
  projectVendorDetail,
} from "./studio-model.js";
import {taskChannelShape} from "./studio-automation-providers.js";

const CONTROLS_KEYS = ["instances", "providers", "isolation_facts"];
const CONTROL_ROW_KEYS = ["instance_id", "adapter_id", "model", "controls",
  "argument_schemas", "isolation", "task_channel"];
const FACT_KEYS = ["name", "category", "sentence"];
//: A standing carries `vendor_detail` only for the vendor's own mechanism, so
//: the shape is "the three, optionally plus that one".
const STANDING_KEYS = ["name", "category", "standing"];
const STANDING_WITH_VENDOR = [...STANDING_KEYS, "vendor_detail"];
//: The ONE word this window may render as a protection. `unknown` is an
//: unmeasured combination, `not_applicable` is a protection this configuration
//: does not have, and `stated_absence` is something this build openly does not
//: do. None of the three is a guarantee.
export const ACTIVE = "active";
const STANDINGS = new Set([ACTIVE, "not_applicable", "stated_absence", "unknown"]);

function projectFacts(rows) {
  if (!Array.isArray(rows)) return null;
  const out = [];
  const named = new Set();
  for (const row of rows) {
    if (!isPlainObject(row) || !exactKeys(row, FACT_KEYS)) return null;
    if (!isId(row.name) || !isId(row.category)) return null;
    if (typeof row.sentence !== "string" || !row.sentence.trim()) return null;
    if (named.has(row.name)) return null;
    named.add(row.name);
    out.push(Object.freeze({
      name: row.name, category: row.category, sentence: row.sentence,
    }));
  }
  return frozenList(out);
}

//: The standings arrive keyed by ROAD, because what protects a step is a fact
//: about the transport bound to it AND the capability that step takes: a review
//: and a dispatch on one binding do not run the same checks. A single list for
//: both would have to be their union or their intersection, and each of those
//: is wrong for one of the two.
function projectRoads(value, controls, known) {
  if (!isPlainObject(value)) return null;
  const out = {};
  for (const [capability, rows] of Object.entries(value)) {
    // Never a road this binding does not declare: a standing under a
    // capability the row does not offer is an answer about a step that cannot
    // be proposed, and rendering it would put a protection on a screen for
    // work this binding refuses to do.
    if (!isId(capability) || !controls.includes(capability)) return null;
    const settled = projectStandings(rows, known);
    if (settled === null) return null;
    out[capability] = settled;
  }
  return Object.freeze(out);
}

function projectStandings(rows, known) {
  if (!Array.isArray(rows)) return null;
  const out = [];
  for (const row of rows) {
    if (!isPlainObject(row)) return null;
    if (!exactKeys(row, STANDING_KEYS) && !exactKeys(row, STANDING_WITH_VENDOR)) {
      return null;
    }
    if (!isId(row.name) || !isId(row.category)) return null;
    if (!STANDINGS.has(row.standing)) return null;
    // The join has to close, or a standing renders with no words -- and a
    // protection with no words is the shape of an assurance nobody wrote.
    if (!known.has(row.name)) return null;
    // The KEY says this row is about the vendor's own mechanism; its VALUE says
    // which of the three answers the integration gave. Carrying the key on every
    // row -- null where there is no vendor question at all -- would collapse
    // "this is not a vendor row" into "nothing was declared", and the screen
    // could then only tell them apart by which sentence it happened to be
    // rendering. So the key is carried exactly where the server sent it.
    const settled = {name: row.name, category: row.category,
      standing: row.standing};
    if (Object.hasOwn(row, "vendor_detail")) {
      const vendorDetail = projectVendorDetail(row.vendor_detail);
      if (vendorDetail === undefined) return null;
      settled.vendorDetail = vendorDetail;
    }
    out.push(Object.freeze(settled));
  }
  return frozenList(out);
}

// The settled controls answer, back in the wire's own spelling for the screen.
// It lives beside the projection that produced it: one module owns this route's
// answer end to end, so a field that survives the boundary and is then dropped
// on the way to the screen cannot happen in two different files.
export function wireControls(settled) {
  return Object.freeze({
    instances: Object.freeze(settled.instances.map((row) => Object.freeze({
      instance_id: row.instanceId, adapter_id: row.adapterId,
      model: row.model, controls: row.controls,
      argument_schemas: row.argumentSchemas, task_channel: row.taskChannel,
      // Back to the wire's spelling, like every field beside it. The screen
      // reads one convention for a whole row; handing it a camelCase island
      // inside a snake_case row is how a renderer comes to read a key that is
      // never there and draw nothing, silently.
      isolation: Object.freeze(Object.fromEntries(
        Object.entries(row.isolation).map(([capability, facts]) => [
          capability, Object.freeze(facts.map((fact) => Object.freeze(
            Object.hasOwn(fact, "vendorDetail")
              ? {name: fact.name, category: fact.category,
                standing: fact.standing, vendor_detail: fact.vendorDetail}
              : {name: fact.name, category: fact.category,
                standing: fact.standing})))]))),
    }))),
    isolation_facts: settled.isolationFacts,
  });
}

export function projectControls(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, CONTROLS_KEYS)) {
    return null;
  }
  if (!Array.isArray(payload.instances)) return null;
  const facts = projectFacts(payload.isolation_facts);
  if (facts === null) return null;
  const known = new Set(facts.map((row) => row.name));
  const rows = [];
  const conflicted = new Set();
  for (const row of payload.instances) {
    if (!isPlainObject(row) || !exactKeys(row, CONTROL_ROW_KEYS)) return null;
    if (!isId(row.instance_id) || !isId(row.adapter_id)) return null;
    if (row.model !== null && !isId(row.model)) return null;
    if (!Array.isArray(row.controls) || !row.controls.every(isId)) return null;
    if (!isPlainObject(row.argument_schemas) || !Object.entries(row.argument_schemas)
      .every(([capability, schema]) => row.controls.includes(capability)
        && isId(schema))) return null;
    const isolation = projectRoads(row.isolation, row.controls, known);
    if (isolation === null) return null;
    // The bound this binding's whole task meets (review ruling R2): null, or the closed fact.
    if (row.task_channel !== null && !taskChannelShape(row.task_channel)) return null;
    // Two rows for one instance are two answers to one question and neither
    // survives, identical rows included.
    if (rows.some((kept) => kept.instanceId === row.instance_id)) {
      conflicted.add(row.instance_id);
      continue;
    }
    rows.push(Object.freeze({
      instanceId: row.instance_id,
      adapterId: row.adapter_id,
      model: row.model,
      controls: frozenList(row.controls.slice()),
      argumentSchemas: frozenJson(row.argument_schemas),
      isolation,
      taskChannel: row.task_channel === null ? null : frozenJson(row.task_channel),
    }));
  }
  return Object.freeze({
    instances: frozenList(rows.filter(
      (row) => !conflicted.has(row.instanceId))),
    providers: projectProviders(payload.providers),
    isolationFacts: facts,
  });
}
