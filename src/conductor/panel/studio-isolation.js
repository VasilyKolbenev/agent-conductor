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
import {localize as L} from "./studio-i18n.js";
import {element} from "./command-view.js";

const ACTIVE = "active";
const REFUSED = "refused_before_spawn";
const DETECTED = "detected_after_spawn";
//: The heading each group is given. A category with no rows for this binding is
//: not drawn at all rather than drawn empty: an empty heading reads as "nothing
//: here", which is a claim.
const GROUPS = [
  [REFUSED, "agents.isolation_before"],
  [DETECTED, "agents.isolation_after"],
];
//: What the third category is called where a person reads it. The word
//: "isolation" is deliberately absent from the first two headings: they are
//: refusals and detections, and calling either isolation is the confusion this
//: whole surface exists to end.
const NOT_ISOLATED = "not_isolated";
const NOT_ISOLATED_TITLE = "agents.isolation_absent";
//: And the rows this configuration has no answer for. Named as unsettled rather
//: than dropped: a check nobody could establish is a thing to tell somebody
//: before they authorize a run, not a thing to leave off the page.
const UNSETTLED_TITLE = "agents.isolation_unsettled";

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

//: What each unsettled standing MEANS, in words a person reads. A standing that
//: lived only in `data-standing` was a distinction for a developer with an
//: inspector open: on the screen, "nobody measured this" and "this build openly
//: does not do it" were the same paragraph, which is the confusion the four
//: words exist to end.
const STANDING_WORDS = Object.freeze({unknown: "agents.isolation_unknown", not_applicable: "agents.isolation_not_applicable"});

function vendorLine(row, state) {
  // The vendor's own words, per road, marked as a mode that was REQUESTED. A
  // platform may or may not enforce it, and this build never presents it as
  // proof that the operating system confined anything.
  //
  // The KEY is what makes this row the vendor's; a row without it gets no line
  // at all, and is a different question entirely.
  if (!Object.hasOwn(row, "vendor_detail")) return null;
  const detail = row.vendor_detail;
  let text = L(state, "agents.isolation_vendor_unknown");
  if (Array.isArray(detail)) {
    text = detail.length === 0 ? L(state, "agents.isolation_vendor_none")
      : L(state, "agents.isolation_requested", {requests: detail.map(([road, tokens]) => `${road}: ${tokens}`).join("; ")});
  }
  return element("p", {className: "studio-isolation-vendor", text});
}

function rowItem(row, words, state) {
  const said = words.get(row.name);
  if (!said) return null;
  const item = element("li", {className: `studio-isolation-${row.standing}`,
    "data-fact": row.name, "data-standing": row.standing},
  [element("span", {text: said.sentence})]);
  const vendor = vendorLine(row, state);
  // A row speaks for itself where it can: the vendor's own line already says
  // which of its three answers this is, so a second sentence saying "not
  // established" beside it would be the same fact twice.
  if (vendor !== null) item.append(vendor);
  else if (Object.hasOwn(STANDING_WORDS, row.standing)) {
    item.append(element("p", {className: "studio-isolation-standing",
      text: L(state, STANDING_WORDS[row.standing])}));
  }
  return item;
}

function group(rows, words, title, state) {
  const items = rows.map((row) => rowItem(row, words, state)).filter(Boolean);
  if (!items.length) return null;
  return element("section", {className: "studio-isolation-group"},
    [element("h5", {text: L(state, title)}), element("ul", {}, items)]);
}

/**
 * The isolation summary for one step, or nothing when the server said nothing.
 *
 * Drawn from the SELECTED binding and the SELECTED road. A step bound to
 * another instance gets that instance's answer; a step taking another
 * capability gets that road's, because a review and a dispatch on one binding
 * do not run the same checks. A step whose binding or road the server did not
 * describe gets no section at all -- an absent answer is never drawn as a
 * reassuring one.
 */
export function isolationFacts(detail, node, capability, state = {}) {
  const binding = bindingFor(detail, node);
  const words = wordsFrom(detail);
  if (binding === null || !words.size) return [];
  const roads = binding.isolation;
  if (roads === null || typeof roads !== "object"
    || typeof capability !== "string"
    || !Object.hasOwn(roads, capability)) return [];
  const standings = roads[capability];
  if (!Array.isArray(standings) || !standings.length) return [];
  const active = standings.filter(
    (row) => row.standing === ACTIVE && row.category !== NOT_ISOLATED);
  const groups = GROUPS
    .map(([category, title]) => group(
      active.filter((row) => row.category === category), words, title, state))
    .filter(Boolean);
  const absences = standings.filter((row) => row.category === NOT_ISOLATED);
  const notIsolated = group(absences, words, NOT_ISOLATED_TITLE, state);
  if (notIsolated !== null) groups.push(notIsolated);
  // Everything the server could not answer for, said OUT LOUD rather than left
  // out. Silence about a check reads as "nothing to say here", which is itself
  // a reassurance -- and these are the rows where this build knows least.
  const unsettled = standings.filter(
    (row) => row.category !== NOT_ISOLATED && row.standing !== ACTIVE);
  const open = group(unsettled, words, UNSETTLED_TITLE, state);
  if (open !== null) groups.push(open);
  if (!groups.length) return [];
  const summary = L(state, active.length === 1 ? "agents.isolation_summary_one" : "agents.isolation_summary", {count: String(active.length), instance: binding.instance_id, adapter: binding.adapter_id, capability});
  return [element("section", {className: "studio-isolation",
    "data-instance": binding.instance_id},
  [element("p", {className: "studio-isolation-summary", text: summary}),
    element("details", {className: "studio-isolation-detail"},
      [element("summary", {text: L(state, "agents.isolation_details")}), ...groups])])];
}
