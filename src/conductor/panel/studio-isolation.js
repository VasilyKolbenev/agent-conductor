"use strict";
// What is protecting THIS step, said before a person confirms it.
//
// One short sentence on the form, and the rows behind a disclosure beside it.
// Not a screen of its own and not a glossary: somebody deciding whether to let
// a model touch their project needs to know three things and needs them here --
// what stops it before it starts, what is only noticed afterwards, and what is
// not confined at all.
//
// Every word rendered comes from the server's own reference block, joined to
// this binding's standings by name. This module keeps no copy of the text: a
// second copy is a second table the moment either is edited, and the one a
// person reads would be the one nobody checks against the guards.
//
// Only `active` is drawn as a protection. `not_applicable` is a protection this
// configuration does not have, `unknown` is a combination nobody measured, and
// a stated absence is something this build openly does not do -- none of the
// three is a guarantee, and each says which it is in its own words.
import {element} from "./command-view.js";

const ACTIVE = "active";
const REFUSED = "refused_before_spawn";
const DETECTED = "detected_after_spawn";
//: The heading each group is given. A category with no rows for this binding is
//: not drawn at all rather than drawn empty: an empty heading reads as "nothing
//: here", which is a claim.
const GROUPS = [
  [REFUSED, "Stopped before the step runs"],
  [DETECTED, "Noticed only after it has run"],
];
//: What the third category is called where a person reads it. The word
//: "isolation" is deliberately absent from the first two headings: they are
//: refusals and detections, and calling either isolation is the confusion this
//: whole surface exists to end.
const NOT_ISOLATED = "not_isolated";
const NOT_ISOLATED_TITLE = "Not confined by this build";
//: And the rows this configuration has no answer for. Named as unsettled rather
//: than dropped: a check nobody could establish is a thing to tell somebody
//: before they authorize a run, not a thing to leave off the page.
const UNSETTLED_TITLE = "Not established for this configuration";

function bindingFor(detail, node) {
  const controls = detail && detail.controls;
  const rows = controls && Array.isArray(controls.instances)
    ? controls.instances : [];
  return rows.find((row) => row.instance_id === node.instance_id) || null;
}

function wordsFrom(detail) {
  const controls = detail && detail.controls;
  const rows = controls && Array.isArray(controls.isolation_facts)
    ? controls.isolation_facts : [];
  return new Map(rows.map((row) => [row.name, row]));
}

function vendorLine(row) {
  // The vendor's own words, per road, marked as a mode that was REQUESTED. A
  // platform may or may not enforce it, and this build never presents it as
  // proof that the operating system confined anything.
  if (!Array.isArray(row.vendor_detail) || !row.vendor_detail.length) return null;
  const pairs = row.vendor_detail
    .map(([road, tokens]) => `${road}: ${tokens}`).join("; ");
  return element("p", {className: "studio-isolation-vendor",
    text: `Requested of the vendor — ${pairs}. Whether the platform enforces `
      + "it is the vendor's business, not a boundary this build imposes."});
}

function rowItem(row, words) {
  const said = words.get(row.name);
  if (!said) return null;
  const item = element("li", {className: `studio-isolation-${row.standing}`,
    "data-fact": row.name, "data-standing": row.standing},
  [element("span", {text: said.sentence})]);
  const vendor = vendorLine(row);
  if (vendor !== null) item.append(vendor);
  return item;
}

function group(rows, words, title) {
  const items = rows.map((row) => rowItem(row, words)).filter(Boolean);
  if (!items.length) return null;
  return element("section", {className: "studio-isolation-group"},
    [element("h5", {text: title}), element("ul", {}, items)]);
}

/**
 * The isolation summary for one step, or nothing when the server said nothing.
 *
 * Drawn from the SELECTED binding only. A step bound to another instance gets
 * that instance's answer, and a step whose binding the server did not describe
 * gets no section at all -- an absent answer is never drawn as a reassuring one.
 */
export function isolationFacts(detail, node) {
  const binding = bindingFor(detail, node);
  const words = wordsFrom(detail);
  if (binding === null || !Array.isArray(binding.isolation)
    || !binding.isolation.length || !words.size) return [];
  const active = binding.isolation.filter(
    (row) => row.standing === ACTIVE && row.category !== NOT_ISOLATED);
  const groups = GROUPS
    .map(([category, title]) => group(
      active.filter((row) => row.category === category), words, title))
    .filter(Boolean);
  const absences = binding.isolation.filter(
    (row) => row.category === NOT_ISOLATED);
  const notIsolated = group(absences, words, NOT_ISOLATED_TITLE);
  if (notIsolated !== null) groups.push(notIsolated);
  // Everything the server could not answer for, said OUT LOUD rather than left
  // out. Silence about a check reads as "nothing to say here", which is itself
  // a reassurance -- and these are the rows where this build knows least.
  const unsettled = binding.isolation.filter(
    (row) => row.category !== NOT_ISOLATED && row.standing !== ACTIVE);
  const open = group(unsettled, words, UNSETTLED_TITLE);
  if (open !== null) groups.push(open);
  if (!groups.length) return [];
  const summary = `${active.length} check${active.length === 1 ? "" : "s"} `
    + `stand for ${binding.instance_id} · ${binding.adapter_id}. `
    + "This build starts an ordinary process with your own rights.";
  return [element("section", {className: "studio-isolation",
    "data-instance": binding.instance_id},
  [element("p", {className: "studio-isolation-summary", text: summary}),
    element("details", {className: "studio-isolation-detail"},
      [element("summary", {text: "What that means"}), ...groups])])];
}
