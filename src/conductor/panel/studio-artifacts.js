"use strict";
// The inspector's INPUTS AND OUTPUTS: what a step requires before it can run,
// what it publishes, and what a run bound to it actually produced.
//
// Split out of `studio-sections.js` before that module reached the project's
// line cap, at the seam its own header already named. That file is "the six
// sections, in one order"; this is one of the six, and it is the one that grows
// -- everything the artifact trio owes is a control in this section, and adding
// it in place would have pushed the sections module through the cap on the same
// day.
//
// The dependency still runs one way and it now runs through four files: the
// frame knows about the sections and about this one, both know about the field
// primitives, and the primitives know nothing about any of them. Nothing here
// imports `studio-sections.js`, which is what keeps the split from closing into
// a ring.
//
// The completeness rule applies here exactly as it does next door: a field is
// finished when it is validated in the primitive it is built from, written
// through `handlers.onEdit`, stored by the draft route and read back by the real
// product -- or it says, in place, that this harness does not support it. Every
// unsupported line carries `data-unsupported`, and the sentence itself is
// written in one place, `studio-fields.unsupported`.
import {context, note, sectionOf, unsupported} from "./studio-fields.js";

//: The one shape this module asks of a payload before reading it. Kept here
//: rather than imported: it is one line, and a section reaching next door to
//: answer a question about its own argument would be an import drawn for
//: nothing. `studio-inspector.js` carries its own copy for the same reason.
function rows(value) { return Array.isArray(value) ? value : []; }

// -- 4. Inputs and outputs -------------------------------------------------

export function artifactSection(form) {
  const {run} = form;
  const box = sectionOf("artifacts", "Inputs and outputs");
  unsupported(box, "Required input artifacts", "A workflow step declares "
    + "resources — model, tool, skill, session, sandbox, filesystem — and no "
    + "artifact requirement, so nothing would read one.");
  unsupported(box, "Produced artifacts", "A workflow step declares no output "
    + "contract. What a run actually produced is durable, and it is shown "
    + "below as the run's own fact.");
  unsupported(box, "Handoff mapping", "This build carries no step-to-step "
    + "artifact mapping in a workflow document.");
  unsupported(box, "Missing-artifact behaviour", "With no declared artifact "
    + "requirement there is no missing-artifact case for a policy to answer.");
  const refs = run && run.position ? rows(run.position.evidence_refs) : [];
  if (run && run.position) {
    context(box, "Evidence references", refs.length ? refs.join(", ") : "none",
      `the durable records of run ${run.runId}`);
    note(box, "Identifiers only. Nothing here states that any of them "
      + "verified anything.");
  }
  return box;
}
