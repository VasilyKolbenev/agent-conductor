"use strict";
// Two lenses on ONE definition. Roles are not installed harnesses: only a run
// binds them. Orbit selection is presentation state, never an edit or authority.
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";

const views = new WeakMap();
const hasRole = (value) => typeof value === "string" && value !== "";

function groupsOf(nodes) {
  const roles = new Map();
  for (const node of nodes) {
    const names = new Set([node.role_id, node.verifier_role_id].filter(hasRole));
    for (const id of names) {
      if (!roles.has(id)) roles.set(id, {id, members: []});
      roles.get(id).members.push({node, duty: node.role_id === id
        ? (node.verifier_role_id === id ? "both" : "perform") : "verify"});
    }
  }
  const unassigned = nodes.filter((node) => !hasRole(node.role_id));
  if (unassigned.length) roles.set(null, {id: null, members: unassigned.map(
    (node) => ({node, duty: node.kind === "gate" ? "gate" : node.kind === "loop" ? "loop" : "none"}))});
  return [...roles.values()];
}

function memberList(group, selection, handlers, state) {
  const list = element("div", {className: "studio-orbit__steps"});
  for (const {node, duty} of group.members) {
    const selected = selection.kind === "node" && selection.id === node.node_id;
    const button = element("button", {type: "button", className: "studio-orbit__step",
      "data-orbit-step": node.node_id, "data-focus": `orbit-step:${node.node_id}`,
      "aria-pressed": String(selected)}, [
      element("span", {text: node.title || node.node_id}),
      element("span", {className: "studio-orbit__detail", text:
        `${localize(state, `workflow_detail.orbit_duty_${duty}`)} · ${node.kind} · ${node.node_id}`}),
    ]);
    button.disabled = typeof handlers?.onSelect !== "function";
    button.addEventListener("click", () => handlers.onSelect(
      {kind: "node", id: node.node_id}));
    list.append(button);
  }
  return list;
}

function roleButton(group, index, count, selected, choose, state) {
  const button = element("button", {type: "button", className: "studio-planet studio-orbit__role",
    "data-orbit-role": group.id ?? "", "data-focus": `orbit-role:${group.id ?? ""}`,
    "aria-pressed": String(selected)}, [
    element("span", {className: "studio-planet__orb", "aria-hidden": "true",
      text: group.id === null ? "◇" : String(index + 1).padStart(2, "0")}),
    element("span", {text: group.id ?? localize(state, "workflow_detail.orbit_unassigned")}),
    element("span", {className: "studio-planet__selection", text:
      `${selected ? `${localize(state, "workflow_detail.orbit_selected")} · ` : ""}${localize(state, `workflow_detail.orbit_steps${group.members.length === 1 ? "_one" : ""}`, {count: String(group.members.length)})}`}),
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

function draw(panel, groups, held, selection, handlers, state) {
  const fleet = element("div", {className: "studio-orbit__fleet"
    + (groups.length > 8 ? " studio-orbit__fleet--compact" : "")});
  const centre = element("div", {className: "studio-orbit__centre"}, [
    element("strong", {text: localize(state, "workflow_detail.orbit_team")}),
    element("span", {className: "studio-orbit__detail", text: localize(state, "workflow_detail.orbit_roles_note")}),
  ]);
  fleet.append(centre);
  const selected = groups.find((group) => group.id === held.role) || groups[0];
  held.role = selected?.id;
  groups.forEach((group, index) => fleet.append(roleButton(
    group, index, groups.length, group === selected, () => {
      held.role = group.id;
      draw(panel, groups, held, selection, handlers, state);
      fit(panel);
      [...panel.querySelectorAll("[data-orbit-role]")].find(
        (button) => button.dataset.orbitRole === (group.id ?? ""))?.focus();
    }, state)));
  const duties = element("section", {className: "studio-orbit__duties"}, [
    element("h3", {text: selected ? (selected.id ?? localize(state, "workflow_detail.orbit_unassigned")) : localize(state, "workflow_detail.orbit_no_roles")}),
    element("p", {className: "studio-note", text: localize(state, "workflow_detail.orbit_choose_step")}),
  ]);
  if (selected) duties.append(memberList(selected, selection, handlers, state));
  else duties.append(element("p", {text: localize(state, "workflow_detail.orbit_empty")}));
  panel.replaceChildren(fleet, duties, element("p", {className: "studio-note", text: localize(state, "workflow_detail.orbit_positions_note")}));
}

/** Local lens state survives redraws, but never crosses a workflow/revision. */
export function workflowOrbit(mount, scope, nodes, selection, handlers, stage, tools, reflow, state = {}) {
  let held = views.get(mount);
  held?.observer?.disconnect();
  if (!held || held.scope !== scope) {
    held = {scope, mode: "connections", role: undefined};
    views.set(mount, held);
  }
  const panel = element("section", {className: "studio-orbit", "aria-label": localize(state, "workflow_detail.orbit_region")});
  draw(panel, groupsOf(nodes), held, selection, handlers, state);
  const switches = element("div", {className: "studio-lenses", role: "group",
    "aria-label": localize(state, "workflow_detail.orbit_lenses")});
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
  for (const [mode, title] of [["team", localize(state, "workflow_detail.lens_team")], ["connections", localize(state, "workflow_detail.lens_connections")]]) {
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
