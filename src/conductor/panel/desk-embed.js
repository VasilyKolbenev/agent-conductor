"use strict";
// Embed mode of the desk (spec 4.5.5): whether a hub frames this desk, and the ONE message it
// then says to the page that frames it. The message is the desk's location -- the project and
// the task and run it has drawn -- and it carries no authority: no token, no path, no text of a
// task, and nothing that asks the hub to do anything. It is for display only.
//
// Whether the desk is embedded is a function of three facts and is decided here as one: the
// window is framed, its hash asks for `embed=hub` and names a project, and the server's own
// project claim agrees -- it names that project and a hub origin of the exact grammar of spec
// 4.1.4. The message goes to THAT origin and to no other: the target is the origin the claim
// named, never a wildcard, so a page that is not the hub cannot receive it. The desk has no
// inbound channel: it listens for no message, and the hub speaks to it through the hash alone.
//
// The same claim can say the desk is open for the wrong project: when it names another project
// than the one the desk bound to (an id that differs, or none), the desk is not merely not
// embedded, it ends (spec 4.5.1). `claimNamesAnotherProject` answers that; the boot module acts.
//
// This module is values in and one call out. It reads no route and opens no door; the boot
// module asks the claim and hands the answer here.

//: A hub origin: a loopback origin with a port, no path, no trailing slash, no leading zero.
const HUB_ORIGIN = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/;
//: The largest port a socket can have; a longer run of digits that is still a number is not one.
const MAX_PORT = 65535;

//: A `hub_origin` that is exactly a hub origin, or `null`. Any other spelling -- a name, a
//: scheme, a path, a slash, a leading zero, a port out of range, a value that is not text --
//: is refused rather than repaired.
export function hubOrigin(value) {
  const found = typeof value === "string" ? HUB_ORIGIN.exec(value) : null;
  return found !== null && Number(found[1]) <= MAX_PORT ? value : null;
}

//: Whether the window and its hash ask for embed at all. When they do not, the project claim
//: is not read: a desk nobody framed has nothing to ask the server.
export function embedAsked({framed, address}) {
  return framed === true && address.embed === "hub" && address.project !== null;
}

//: A project claim is a plain object. A refusal, a route that is not there, or any other body
//: is not one.
function plainClaim(claim) {
  return claim !== null && typeof claim === "object" && !Array.isArray(claim);
}

//: The origin the desk may post its location to, or `null` when it is not embedded. The claim
//: is the server's answer to the project read (or `null` when there was none): it must repeat
//: the hash's project and carry a hub origin of the exact grammar.
export function embedTarget({framed, address, claim}) {
  if (!embedAsked({framed, address})) return null;
  if (!plainClaim(claim) || claim.project_id !== address.project) return null;
  return hubOrigin(claim.hub_origin);
}

//: Whether the server's claim names another project than the one the desk bound to (spec
//: 4.5.1): an id that differs, and `null` against an id, either way round; a claim with no
//: `project_id` names none, as `null` does. Only a claim can name a project: a read that gave
//: none names nothing, and that is not this question's answer.
export function claimNamesAnotherProject(bound, claim) {
  return plainClaim(claim) && (claim.project_id ?? null) !== bound;
}

//: The one message. Only the three ids are copied off `at`, so nothing else it may carry can
//: leave with it, and the object is frozen; `origin` is the target a caller took from
//: `embedTarget`.
export function announceLocation(parent, origin, at) {
  parent.postMessage(Object.freeze({kind: "desk-location", project_id: at.project_id,
    task_id: at.task_id, run_id: at.run_id}), origin);
}
