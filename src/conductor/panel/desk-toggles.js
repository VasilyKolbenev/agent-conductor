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
// The page and the desk's state come in as arguments; this module reaches neither by name.

//: The toggle of each panel, by the id of its button.
const PANELS = Object.freeze({deskFlowToggle: "cycle", deskPeopleToggle: "people",
  deskRunToggle: "run"});

export function createToggles({byId, panels, closeContinue, remember, render}) {
  // `undefined` is no press at all; `null` is a choice, the one of a person who closed what they
  // had pressed.
  let chosen;
  let booting = true;
  let applied = false;

  //: A press of the toggle of `panel`: kept while the boot has not opened a panel, a toggle after.
  function press(panel) {
    closeContinue();
    if (!booting) {
      panels.toggle(panel);
      remember();
      return;
    }
    chosen = (chosen ?? null) === panel ? null : panel;
    render();
  }

  //: The panel the boot opens, given the one its address names: the person's, if they pressed.
  //: The window of presses is closed by this call, in the turn that opens the panel, so no press
  //: can fall between the two.
  function resolve(named) {
    booting = false;
    return chosen === undefined ? named : chosen;
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

  return Object.freeze({draw, resolve, names: Object.freeze(Object.values(PANELS)),
    //: The boot has applied everything its address names, the wizard included.
    finish: () => { applied = true; }, applied: () => applied});
}
