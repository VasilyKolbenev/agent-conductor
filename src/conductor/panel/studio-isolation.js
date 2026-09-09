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

//: What each unsettled standing MEANS, in words a person reads. A standing that
//: lived only in `data-standing` was a distinction for a developer with an
//: inspector open: on the screen, "nobody measured this" and "this build openly
//: does not do it" were the same paragraph, which is the confusion the four
//: words exist to end.
const STANDING_WORDS = {
  unknown: "Not established for this configuration — nothing here says it "
    + "does or does not stand.",
  not_applicable: "Not a protection this configuration has: it needs "
    + "something this run did not ask for.",
};

//: The vendor's own mechanism has THREE answers and each is a different
//: sentence. The absence of a CLI flag is never written as "this vendor has no
//: sandbox": what this build can say is what it ASKED for.
const VENDOR_UNKNOWN =
  "This integration carries no reviewed declaration for this provider, so "
  + "nothing is stated here either way — neither that a vendor sandbox mode is "
  + "requested nor that none is.";
const VENDOR_NONE =
  "This integration reviewed this provider and requests NO vendor sandbox "
  + "mode on any road. That is a statement about what this build asks for, not "
  + "a finding that the vendor ships none.";

function vendorLine(row) {
  // The vendor's own words, per road, marked as a mode that was REQUESTED. A
  // platform may or may not enforce it, and this build never presents it as
  // proof that the operating system confined anything.
  //
  // The KEY is what makes this row the vendor's; a row without it gets no line
  // at all, and is a different question entirely.
  if (!Object.hasOwn(row, "vendor_detail")) return null;
  const detail = row.vendor_detail;
  let text = VENDOR_UNKNOWN;
  if (Array.isArray(detail)) {
    text = detail.length === 0 ? VENDOR_NONE
      : `Requested of the vendor — ${detail
        .map(([road, tokens]) => `${road}: ${tokens}`).join("; ")}. Whether the `
        + "platform enforces it is the vendor's business, not a boundary this "
        + "build imposes.";
  }
  return element("p", {className: "studio-isolation-vendor", text});
}

function rowItem(row, words) {
  const said = words.get(row.name);
  if (!said) return null;
  const item = element("li", {className: `studio-isolation-${row.standing}`,
    "data-fact": row.name, "data-standing": row.standing},
  [element("span", {text: said.sentence})]);
  const vendor = vendorLine(row);
  // A row speaks for itself where it can: the vendor's own line already says
  // which of its three answers this is, so a second sentence saying "not
  // established" beside it would be the same fact twice.
  if (vendor !== null) item.append(vendor);
  else if (Object.hasOwn(STANDING_WORDS, row.standing)) {
    item.append(element("p", {className: "studio-isolation-standing",
      text: STANDING_WORDS[row.standing]}));
  }
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
 * Drawn from the SELECTED binding and the SELECTED road. A step bound to
 * another instance gets that instance's answer; a step taking another
 * capability gets that road's, because a review and a dispatch on one binding
 * do not run the same checks. A step whose binding or road the server did not
 * describe gets no section at all -- an absent answer is never drawn as a
 * reassuring one.
 */
export function isolationFacts(detail, node, capability) {
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
      active.filter((row) => row.category === category), words, title))
    .filter(Boolean);
  const absences = standings.filter((row) => row.category === NOT_ISOLATED);
  const notIsolated = group(absences, words, NOT_ISOLATED_TITLE);
  if (notIsolated !== null) groups.push(notIsolated);
  // Everything the server could not answer for, said OUT LOUD rather than left
  // out. Silence about a check reads as "nothing to say here", which is itself
  // a reassurance -- and these are the rows where this build knows least.
  const unsettled = standings.filter(
    (row) => row.category !== NOT_ISOLATED && row.standing !== ACTIVE);
  const open = group(unsettled, words, UNSETTLED_TITLE);
  if (open !== null) groups.push(open);
  if (!groups.length) return [];
  const summary = `${active.length} check${active.length === 1 ? "" : "s"} `
    + `stand for ${binding.instance_id} · ${binding.adapter_id} on the `
    + `${capability} road. `
    + "This build starts an ordinary process with your own rights.";
  return [element("section", {className: "studio-isolation",
    "data-instance": binding.instance_id},
  [element("p", {className: "studio-isolation-summary", text: summary}),
    element("details", {className: "studio-isolation-detail"},
      [element("summary", {text: "What that means"}), ...groups])])];
}
