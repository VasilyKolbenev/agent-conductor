"use strict";
// Boot module of the desk: it stands the regions of spec 5.1 on the page and
// says, on each, the phase of the read that feeds it.
//
// This is the shell and nothing more. The five mounts are in `desk.html`, empty,
// each in the machine word `empty`; a mount that a read feeds goes to `loading`
// and then to the word its read earned -- `ready`, `refused` or `failed` -- and
// the top bar says the whole of it in one plain sentence. Nothing is drawn into a
// mount yet: the modules that fill them arrive one region at a time.
//
// It reaches the wire only through `desk-transport.js`, the ONLY module of the
// panel that touches the network, and holds no door, no timer and no storage of
// its own. Facts enter through a READ and through nothing else, and this module
// writes nothing at all. It reads the two routes that exist for it today; the
// project route and its header are lane H's and are not faked here.
import {LATE, createTransport, path} from "./desk-transport.js";
import {message} from "./studio-i18n.js";

//: The two reads the shell makes on load, each named for the route it asks. A
//: route is only ever `path.<name>` of the transport module.
const READS = Object.freeze({
  tasks: () => path.tasks(),
  runs: () => path.runs(),
});
//: The five mounts, in reading order, and the read that feeds each. A mount with
//: no read of its own stays in the word `empty`: the scene and the feed follow a
//: chosen task, and the pult follows the gates of a run, none of which exists to
//: read on load.
const REGIONS = Object.freeze([
  Object.freeze({id: "deskRail", reads: "tasks"}),
  Object.freeze({id: "deskScene", reads: null}),
  Object.freeze({id: "deskFeed", reads: null}),
  Object.freeze({id: "deskSummary", reads: "runs"}),
  Object.freeze({id: "deskPult", reads: null}),
]);
//: What the transport answers when the wire gave no answer at all: the read was
//: abandoned at its deadline, or the request could not be made. Any other answer
//: is the server's own refusal.
const UNANSWERED = Object.freeze([LATE, "store_error"]);

//: The phase a failed read puts its region in.
function phaseOf(error) {
  const code = error instanceof Error ? error.message : "store_error";
  return UNANSWERED.includes(code) ? "failed" : "refused";
}

//: The one word for a set of phases: the worst of them.
function worst(phases) {
  if (phases.includes("failed")) return "failed";
  return phases.includes("refused") ? "refused" : "ready";
}

(() => {
  const shell = document.getElementById("deskShell");
  if (!shell) return;
  const byId = (id) => document.getElementById(id);
  //: The page's own language is the language of record: `<html lang>` says it,
  //: and anything but Russian is read as English.
  const locale = () => (document.documentElement.lang === "ru" ? "ru" : "en");
  const {readJson} = createTransport(locale);

  function mark(node, phase) {
    node.setAttribute("data-state", phase);
  }

  function say(phase) {
    byId("deskStatus").textContent = message(locale(), `phase.${phase}`);
  }

  //: One read, settled into the phase it puts its region in. The answer's body is
  //: not used yet -- the mounts are empty -- so what this establishes is that the
  //: route answers this window, in the words its own refusal vocabulary has.
  async function settle(target) {
    try {
      await readJson(target);
      return "ready";
    } catch (error) {
      return phaseOf(error);
    }
  }

  async function load() {
    const fed = REGIONS.filter(({reads}) => reads !== null);
    fed.forEach(({id}) => mark(byId(id), "loading"));
    mark(shell, "loading");
    say("loading");
    const phases = await Promise.all(fed.map(({reads}) => settle(READS[reads]())));
    fed.forEach(({id}, index) => mark(byId(id), phases[index]));
    mark(shell, worst(phases));
    say(worst(phases));
  }

  load();
})();
