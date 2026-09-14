"use strict";
// Two lenses on ONE definition. Roles are not installed harnesses: only a run
// binds them. Orbit selection is presentation state, never an edit or authority.
import {element} from "./command-view.js";

const views = new WeakMap();
const hasRole = (value) => typeof value === "string" && value !== "";

function groupsOf(nodes) {
  const roles = new Map();
  for (const node of nodes) {
    const names = new Set([node.role_id, node.verifier_role_id].filter(hasRole));
    for (const id of names) {
      if (!roles.has(id)) roles.set(id, {id, members: []});
      roles.get(id).members.push({node, duty: node.role_id === id
        ? (node.verifier_role_id === id ? "perform + verify" : "perform") : "verify"});
    }
  }
  const unassigned = nodes.filter((node) => !hasRole(node.role_id));
  if (unassigned.length) roles.set(null, {id: null, members: unassigned.map(
    (node) => ({node, duty: node.kind === "gate" ? "human decision" :
      node.kind === "loop" ? "loop control" : "not assigned"}))});
  return [...roles.values()];
}

function memberList(group, selection, handlers) {
  const list = element("div", {className: "studio-orbit__steps"});
  for (const {node, duty} of group.members) {
    const selected = selection.kind === "node" && selection.id === node.node_id;
    const button = element("button", {type: "button", className: "studio-orbit__step",
      "data-orbit-step": node.node_id, "data-focus": `orbit-step:${node.node_id}`,
      "aria-pressed": String(selected)}, [
      element("span", {text: node.title || node.node_id}),
      element("span", {className: "studio-orbit__detail", text:
        `${duty} · ${node.kind} · ${node.node_id}`}),
    ]);
    button.disabled = typeof handlers?.onSelect !== "function";
    button.addEventListener("click", () => handlers.onSelect(
      {kind: "node", id: node.node_id}));
    list.append(button);
  }
  return list;
}

function roleButton(group, index, count, selected, choose) {
  const button = element("button", {type: "button", className: "studio-planet studio-orbit__role",
    "data-orbit-role": group.id ?? "", "data-focus": `orbit-role:${group.id ?? ""}`,
    "aria-pressed": String(selected)}, [
    element("span", {className: "studio-planet__orb", "aria-hidden": "true",
      text: group.id === null ? "◇" : String(index + 1).padStart(2, "0")}),
    element("span", {text: group.id ?? "Human & unassigned"}),
    element("span", {className: "studio-planet__selection", text:
      `${selected ? "Selected · " : ""}${group.members.length} step${group.members.length === 1 ? "" : "s"}`}),
  ]);
  // Placement says nothing about ordering or dependencies. On narrow screens
  // the same controls reflow into a list; keyboard order is always the DOM's.
  const angle = 2 * Math.PI * index / count - Math.PI / 2;
  button.style.setProperty("--orb-x", `${50 + 32 * Math.cos(angle)}%`);
  button.style.setProperty("--orb-y", `${50 + 32 * Math.sin(angle)}%`);
  button.addEventListener("click", choose);
  return button;
}

function overlaps(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

function fit(panel) {
  const fleet = panel.querySelector(".studio-orbit__fleet");
  if (!fleet || panel.hidden || !panel.isConnected) return;
  if (fleet.classList.contains("studio-orbit__fleet--compact")) return;
  const bounds = fleet.getBoundingClientRect();
  const centre = fleet.querySelector(".studio-orbit__centre").getBoundingClientRect();
  const boxes = [...fleet.querySelectorAll("[data-orbit-role]")].map(
    (button) => button.getBoundingClientRect());
  const crowded = boxes.some((box, at) => box.left < bounds.left || box.top < bounds.top
    || box.right > bounds.right || box.bottom > bounds.bottom || overlaps(box, centre)
    || boxes.slice(at + 1).some((other) => overlaps(box, other)));
  if (crowded) fleet.classList.add("studio-orbit__fleet--compact");
}

function draw(panel, groups, held, selection, handlers) {
  const fleet = element("div", {className: "studio-orbit__fleet"
    + (groups.length > 8 ? " studio-orbit__fleet--compact" : "")});
  const centre = element("div", {className: "studio-orbit__centre"}, [
    element("strong", {text: "Workflow team"}),
    element("span", {className: "studio-orbit__detail", text: "Roles · not live agents"}),
  ]);
  fleet.append(centre);
  const selected = groups.find((group) => group.id === held.role) || groups[0];
  held.role = selected?.id;
  groups.forEach((group, index) => fleet.append(roleButton(
    group, index, groups.length, group === selected, () => {
      held.role = group.id;
      draw(panel, groups, held, selection, handlers);
      fit(panel);
      [...panel.querySelectorAll("[data-orbit-role]")].find(
        (button) => button.dataset.orbitRole === (group.id ?? ""))?.focus();
    })));
  const duties = element("section", {className: "studio-orbit__duties"}, [
    element("h3", {text: selected ? (selected.id ?? "Human & unassigned") : "No roles yet"}),
    element("p", {className: "studio-note", text:
      "Choose a step to edit its assignment, execution limits, artifacts and verification in the inspector."}),
  ]);
  if (selected) duties.append(memberList(selected, selection, handlers));
  else duties.append(element("p", {text: "Add a step to build your team."}));
  panel.replaceChildren(fleet, duties, element("p", {className: "studio-note", text:
    "Orbit positions are navigation, not execution order. Connections holds the actual routes. "
    + "Harnesses and models are assigned when opening a run."}));
}

/** Local lens state survives redraws, but never crosses a workflow/revision. */
export function workflowOrbit(mount, scope, nodes, selection, handlers, stage, tools, reflow) {
  let held = views.get(mount);
  held?.observer?.disconnect();
  if (!held || held.scope !== scope) {
    held = {scope, mode: "connections", role: undefined};
    views.set(mount, held);
  }
  const panel = element("section", {className: "studio-orbit", "aria-label": "Workflow team orbit"});
  draw(panel, groupsOf(nodes), held, selection, handlers);
  const switches = element("div", {className: "studio-lenses", role: "group",
    "aria-label": "Workflow view"});
  const buttons = [];
  function show() {
    panel.hidden = held.mode !== "team";
    stage.hidden = held.mode !== "connections";
    tools.hidden = held.mode !== "connections";
    for (const [mode, button] of buttons) button.setAttribute(
      "aria-pressed", String(mode === held.mode));
    if (!stage.hidden) reflow();
    fit(panel);
  }
  for (const [mode, title] of [["team", "Team orbit"], ["connections", "Connections"]]) {
    const button = element("button", {type: "button", className: "studio-lens",
      "data-focus": `workflow-lens:${mode}`, "data-lens": mode, text: title});
    buttons.push([mode, button]);
    button.addEventListener("click", () => { held.mode = mode; show(); });
    switches.append(button);
  }
  show();
  held.observer = new ResizeObserver(() => fit(panel));
  held.observer.observe(panel);
  return {switches, panel, refresh: () => fit(panel)};
}
