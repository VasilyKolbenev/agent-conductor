"use strict";
// The three centre panels have one owner for mutual exclusion and lifecycle.
// The Flow host is created only when its panel is first opened; the People host
// also updates the Pult while its own panel is closed.
export function createDeskPanels({flowMount, people, run, createFlow, allowed, onChange}) {
  let active = null, flow = null, disposed = false;
  const names = new Set(["cycle", "people", "run"]);
  function open(name) {
    if (disposed || !allowed()) return;
    const next = names.has(name) ? name : null;
    if (active === next) return;
    if (active === "people") people.show(false);
    if (active === "run") run.show(false);
    active = next;
    flowMount.hidden = active !== "cycle";
    if (active === "cycle") {
      if (flow === null) flow = createFlow();
      flow.open();
    }
    if (active === "people") people.show(true);
    if (active === "run") run.show(true);
    onChange();
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    active = null;
    flow?.dispose();
    people.dispose();
    run.dispose();
    flowMount.hidden = true;
  }
  return Object.freeze({open, toggle: (name) => open(active === name ? null : name),
    current: () => active, isOpen: (name) => active === name,
    render: (desk, connection) => { people.render(desk.run); run.render(desk, connection); },
    connection: (value) => people.connection(value),
    refresh: () => flow?.refresh(),
    suspend: () => { flow?.suspend(); people.suspend(); },
    resume: () => flow?.resume(), dispose});
}
