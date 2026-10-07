"use strict";
// The three toggles of the top bar, and what a press on one of them means while the desk boots.
//
// The boot reads its address once, at its start, and applies it when the claim and the lists have
// landed (spec 4.5.1: the claim first, everything else after it). A press on a toggle in between is
// the person's choice of a panel. It is recorded here, drawn pressed, and opens nothing; when the
// boot has applied the task and the run its address names it opens the person's LAST choice
// instead of the panel the address names (spec 4.5.3 applies the selection before its panel). A
// press made again changes the choice, and the same toggle pressed twice is a choice of none, which
// replaces a panel the address names as well. After that the toggles are what they always were.
//
// The continue-after block is one of the person's choices too: opening it in between is a choice of
// the block (`choose("continue")`) and closing it a choice of none (`choose(null)`), each replacing
// whatever was chosen before, a press and the panel the address names alike.
//
// A hash can arrive in between as well (the hub moves a mounted desk by replacing its fragment).
// The events of the window are ordered: a hash that names a panel, or that moves the task and
// names none, replaces what was pressed before it and the panel the address named, and is what
// the boot opens unless the person chooses again; a hash that names no panel (the language alone,
// a repeat of what was heard) replaces nothing; what the person chooses after a hash replaces it.
// A hash is judged against the one heard before it, the address of the boot being the first. The
// panel of a hash heard in the window is therefore decided when it is heard, and the rest of it
// (task, run, wizard) is the router's, once the boot has finished: `hear` gives the router a
// ticket, and `after` takes the panel out of what the router would ask for a hash that has one.
// The router applies the hashes of the window one after another (`inTurn`), each against the
// address it carried: two hashes are two choices, and the later does not erase the earlier.
//
// The page and the desk's state come in as arguments; this module reaches neither by name.

//: The toggle of each panel, by the id of its button.
const PANELS = Object.freeze({deskFlowToggle: "cycle", deskPeopleToggle: "people",
  deskRunToggle: "run"});
const NAMES = Object.freeze(Object.values(PANELS));

//: `first` is the address the boot applies, and `moves(last, next)` what `next` asks of a desk
//: whose address was `last` (`navigationChange` of the address grammar).
export function createToggles({byId, panels, closeContinue, remember, render, first, moves}) {
  // `undefined` is no choice at all; `null` is a choice, the one of a person who closed what they
  // had pressed or opened; `"continue"` is the block.
  let chosen;
  // The panel a hash heard while the boot reads names (`null`: none), `undefined` if none did.
  let heard;
  let last = first;
  let choices = 0;
  let booting = true;
  let applied = false;
  // The application of the hash heard last: the next one starts when it has ended.
  let ahead = Promise.resolve();

  //: A press of the toggle of `panel`: kept while the boot has not opened a panel, a toggle after.
  function press(panel) {
    choices += 1;
    closeContinue();
    if (!booting) {
      panels.toggle(panel);
      remember();
      return;
    }
    chosen = (chosen ?? null) === panel ? null : panel;
    render();
  }

  //: The person opened (`"continue"`) or closed (`null`) the block while the boot has not opened a
  //: panel: that is their last choice, drawn at once so that no toggle stays pressed beside it.
  function choose(value) {
    choices += 1;
    if (!booting) return;
    const pressed = NAMES.includes(chosen);
    chosen = value;
    if (pressed) render();
  }

  //: A hash has arrived, `next` read. While the boot has not opened a panel, a hash that moves the
  //: panel replaces the choice made before it: a hash that moves the task and names none closes
  //: the block, which is the panel it was open as. The ticket says whether the panel of this hash
  //: was decided here and how many choices the person had made when it arrived.
  function hear(next) {
    const ticket = Object.freeze({asked: choices, decided: booting});
    if (!booting) return ticket;
    const change = moves(last, next);
    last = next;
    const named = change.steps.some((step) => step.key === "panel");
    if (!named && !change.reset.includes("panel")) return ticket;
    const pressed = NAMES.includes(chosen);
    heard = named ? next.panel : null;
    chosen = undefined;
    if (!named) closeContinue();
    if (pressed) render();
    return ticket;
  }

  //: What a hash still asks once the boot is over: not its panel when `hear` decided it, nor when
  //: the person has chosen since it arrived (their choice stands).
  function after(ticket, change) {
    if (!ticket.decided && choices === ticket.asked) return change;
    const steps = change.steps.filter((step) => step.key !== "panel");
    const reset = change.reset.filter((key) => key !== "panel");
    return Object.freeze({steps: Object.freeze(steps), reset: Object.freeze(reset)});
  }

  //: `job` applies a hash once `ready` (the boot) has settled and every job given before it has
  //: ended, so a hash heard meanwhile is applied against what the one before it left, and none is
  //: lost to a newer one. A job that fails is told to its own caller and holds back none after it.
  function inTurn(ready, job) {
    const turn = ahead.then(() => ready).then(job);
    ahead = turn.catch(() => {});
    return turn;
  }

  //: The panel the boot opens, given the one its address names: the person's, if they chose, else
  //: the one a hash heard since names. The window of presses is closed by this call, in the turn
  //: that opens the panel, so no press can fall between the two.
  function resolve(named) {
    booting = false;
    if (chosen !== undefined) return chosen;
    return heard === undefined ? named : heard;
  }

  //: The toggles drawn: pressed for the choice while the boot has not opened a panel, else for the
  //: panel that is open; none of them in a desk that is open for another project.
  function draw(foreign) {
    for (const [id, panel] of Object.entries(PANELS)) {
      const open = booting && chosen !== undefined ? chosen === panel : panels.isOpen(panel);
      byId(id).hidden = foreign;
      byId(id).setAttribute("aria-expanded", String(open));
    }
  }

  for (const [id, panel] of Object.entries(PANELS)) {
    byId(id).addEventListener("click", () => press(panel));
  }

  return Object.freeze({draw, resolve, choose, hear, after, inTurn, names: NAMES,
    //: The boot has applied everything its address names, the wizard included.
    finish: () => { applied = true; }, applied: () => applied});
}
