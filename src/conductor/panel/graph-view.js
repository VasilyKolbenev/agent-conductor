"use strict";
// Every Graph node is built from text: no markup string is ever parsed here.
// Identity and status stay on separate channels — the harness accent reaches
// the badge swatch and nothing else; status reaches the glyph, the word and
// the chip contour, exactly the split index.html documents for the panel.
import {element, field} from "./command-view.js";
import {DECISION_ACTIONS, GATE_CHANNEL, PHASE_CHANNEL} from "./graph-store.js";

// Geometry constants the layout renders and the browser suite measures.
export const CELL = Object.freeze({width: 210, height: 118, gapX: 46, gapY: 18});

const GATE_GLYPHS = Object.freeze({
  pending: "○ pending",
  satisfied: "✓ approved",
  failed: "✕ rejected",
  changes_requested: "■ changes requested",
  waived: "◇ waived",
});
const HEALTH_CHANNEL = Object.freeze({
  ready: "pass", busy: "wait", offline: "fail", degraded: "wait",
  unknown: "none",
});
// The glyph half of the status channel, so no chip speaks through colour
// alone — the same three-carrier rule (glyph, word, contour) the panel's
// pills follow. Gate chips carry their own glyph inside GATE_GLYPHS.
const CHANNEL_GLYPHS = Object.freeze({
  pass: "✓", wait: "●", fail: "✕", none: "·",
});

// The monogram an unregistered harness gets, from its own string and from
// nothing else — the rule conductor/harnesses.py _monogram states, held to one
// table of example strings by the browser suite beside index.html's copy.
const MONO_SPLIT = /[^\p{L}\p{N}]+/u;
export function monogramOf(id) {
  const words = String(id).split(MONO_SPLIT).filter((word) => word);
  if (!words.length) return "?";
  const initials = words.length > 1 ? [...words[0]][0] + [...words[1]][0]
    : [...words[0]].slice(0, 2).join("");
  return [...initials.toUpperCase()].slice(0, 2).join("");
}

export function badge(registry, harnessId) {
  const row = registry.find((entry) => entry.id === harnessId);
  const name = row ? row.name : String(harnessId);
  const monogram = row ? row.monogram : monogramOf(harnessId);
  const root = element("span", {className: "hb"}, [
    element("span", {className: "hb__m", text: monogram}),
    element("span", {className: "hb__n", text: name}),
  ]);
  // The accent pair lands on the badge root, where graph.css resolves
  // --hb from it; on a child the custom property would never be read and
  // every registered product would silently draw the neutral badge.
  if (row) root.style.setProperty("--hb-dark", row.dark);
  if (row) root.style.setProperty("--hb-light", row.light);
  return root;
}

function chip(channel, text, ownGlyph = false) {
  const node = element("span", {className: `g-chip g-chip--${channel}`});
  if (!ownGlyph) {
    node.append(element("i", {className: "gl", text: CHANNEL_GLYPHS[channel]}),
      " ");
  }
  node.append(element("span", {text}));
  return node;
}

export function renderPalette(mount, state) {
  mount.replaceChildren(element("h2", {text: "Harness palette"}));
  if (!state.registry.length) {
    mount.append(element("p", {className: "empty",
      text: "No registry rows in this fixture."}));
    return;
  }
  const list = element("ul", {className: "g-palette"});
  for (const row of state.registry) {
    const item = element("li", {className: "g-palette__row"}, [
      badge(state.registry, row.id),
    ]);
    // projectRegistry admits only https docs, and this arm re-states the
    // gate where the href is written, as index.html harnessBadge does.
    if (row.docs.startsWith("https://")) {
      item.append(element("a", {className: "hb__d", href: row.docs,
        rel: "noreferrer noopener", target: "_blank", text: "docs"}));
    }
    list.append(item);
  }
  mount.append(list);
}

function evidenceRow(item) {
  const channel = {verified: "pass", unverified: "wait", unavailable: "none",
    mismatch: "fail", error: "fail"}[item.verification];
  return element("li", {className: "g-evidence"}, [
    element("span", {className: "mono", text: `${item.kind} ${item.evidence_id}`}),
    chip(channel, item.verification),
  ]);
}

function nodeButton(state, node, onSelect) {
  const cell = state.layout.cells[node.node_id];
  const pressed = state.selection === node.node_id;
  const button = element("button", {
    "aria-pressed": String(pressed), className: `g-node g-node--${node.kind}`,
    "data-node-id": node.node_id, type: "button",
  });
  button.style.setProperty("--x", `${cell.column * (CELL.width + CELL.gapX)}px`);
  button.style.setProperty("--y", `${cell.row * (CELL.height + CELL.gapY)}px`);
  const head = element("span", {className: "g-node__head"});
  if (node.harness !== null) head.append(badge(state.registry, node.harness));
  else head.append(element("span", {className: "hb__n", text: "no harness"}));
  button.append(head,
    element("span", {className: "g-node__title", text: node.title}));
  const chips = element("span", {className: "g-node__chips"}, [
    chip(HEALTH_CHANNEL[node.health], node.health),
    chip(PHASE_CHANNEL[node.phase], node.phase),
  ]);
  if (node.gate) chips.append(
    chip(GATE_CHANNEL[node.gate.state], GATE_GLYPHS[node.gate.state], true));
  button.append(chips);
  const parents = state.edges.filter((edge) => edge.to === node.node_id);
  button.append(element("span", {className: "g-node__from mono", text:
    parents.length ? `after ${parents.map((edge) => edge.from).join(", ")}`
      : "start"}));
  button.addEventListener("click", () => onSelect(node.node_id));
  return button;
}

function edgePath(cells, edge) {
  const from = cells[edge.from], to = cells[edge.to];
  const x1 = from.column * (CELL.width + CELL.gapX) + CELL.width;
  const y1 = from.row * (CELL.height + CELL.gapY) + CELL.height / 2;
  const x2 = to.column * (CELL.width + CELL.gapX);
  const y2 = to.row * (CELL.height + CELL.gapY) + CELL.height / 2;
  const bend = Math.max(18, (x2 - x1) / 2);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("class", "g-edge");
  path.setAttribute("data-edge", `${edge.from} ${edge.to}`);
  path.setAttribute("d", `M ${x1} ${y1} C ${x1 + bend} ${y1}, `
    + `${x2 - bend} ${y2}, ${x2} ${y2}`);
  return path;
}

export function renderGraph(mount, svg, state, onSelect) {
  mount.querySelectorAll(".g-node").forEach((node) => node.remove());
  svg.replaceChildren();
  if (state.layout.columns) {
    const width = state.layout.columns * (CELL.width + CELL.gapX) - CELL.gapX;
    const height = state.layout.rows * (CELL.height + CELL.gapY) - CELL.gapY;
    svg.setAttribute("viewBox", `0 0 ${Math.max(1, width)} ${Math.max(1, height)}`);
    svg.setAttribute("width", String(Math.max(1, width)));
    svg.setAttribute("height", String(Math.max(1, height)));
  } else {
    // A refused or empty state must not keep the last graph's canvas.
    for (const name of ["viewBox", "width", "height"]) svg.removeAttribute(name);
  }
  for (const edge of state.edges) svg.append(edgePath(state.layout.cells, edge));
  for (const node of state.nodes) mount.append(nodeButton(state, node, onSelect));
}

function draftInput(draft, key, attributes) {
  const control = element("input", attributes);
  control.value = draft[key];
  control.addEventListener("input", () => { draft[key] = control.value; });
  return control;
}

// Draft keys double as control names: they are the reducer-event field names.
function draftSelect(draft, key, options) {
  const control = element("select", {name: key}, options);
  if ([...control.options].some((option) => option.value === draft[key])) {
    control.value = draft[key];
  } else {
    draft[key] = control.value;
  }
  control.addEventListener("change", () => { draft[key] = control.value; });
  return control;
}

function decisionForm(node, draft, onDecide) {
  const form = element("form", {className: "g-decide"}, [
    element("h3", {text: "Human gate decision"}),
    element("p", {className: "g-note", text:
      "Recorded in this window's fixture only. Nothing is executed or sent."}),
  ]);
  const action = draftSelect(draft, "action",
    Object.keys(DECISION_ACTIONS).map((name) =>
      element("option", {text: name, value: name})));
  const actor = draftInput(draft, "actor", {autocomplete: "off",
    maxlength: "128", name: "actor",
    pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}", required: "",
    spellcheck: "false", type: "text"});
  const reason = draftInput(draft, "reason", {autocomplete: "off",
    maxlength: "200", name: "reason", spellcheck: "false", type: "text"});
  form.append(field("Action", action), field("Decided by", actor),
    field("Reason", reason),
    element("button", {name: "record", text: "Record decision", type: "submit"}));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onDecide({gateId: node.gate.gate_id, action: draft.action,
      actor: draft.actor.trim(), reason: draft.reason});
  });
  return form;
}

export function renderDetail(mount, state, decisionDraft, onDecide) {
  mount.replaceChildren();
  const node = state.nodes.find((row) => row.node_id === state.selection);
  if (!node) {
    mount.append(element("p", {className: "empty",
      text: "Select a node to read its card."}));
    return;
  }
  const head = element("div", {className: "g-det__head"});
  if (node.harness !== null) head.append(badge(state.registry, node.harness));
  mount.append(element("p", {className: "g-det__title", text: node.title}), head,
    element("p", {className: "mono g-det__meta",
      text: `${node.node_id} · ${node.kind}`}),
    element("div", {className: "g-det__chips"}, [
      chip(HEALTH_CHANNEL[node.health], `availability: ${node.health}`),
      chip(PHASE_CHANNEL[node.phase], `phase: ${node.phase}`),
    ]));
  const names = node.capabilities.length ? node.capabilities.join(", ") : "none";
  mount.append(element("p", {className: "mono g-det__meta",
    text: `capabilities: ${names}`}));
  mount.append(element("h3", {text: "Evidence"}));
  mount.append(node.evidence.length
    ? element("ul", {className: "g-evidence-list"}, node.evidence.map(evidenceRow))
    : element("p", {className: "empty", text: "No evidence recorded."}));
  if (node.gate) {
    mount.append(chip(GATE_CHANNEL[node.gate.state],
      `${node.gate.gate_id}: ${GATE_GLYPHS[node.gate.state]}`, true));
    mount.append(decisionForm(node, decisionDraft, onDecide));
  }
}

export function renderGates(mount, state) {
  mount.replaceChildren(element("h2", {text: "Human gates"}));
  const gates = state.nodes.filter((node) => node.gate);
  if (!gates.length) {
    mount.append(element("p", {className: "empty", text: "No gates in this graph."}));
    return;
  }
  const list = element("ul", {className: "g-gate-list"});
  for (const node of gates) {
    const item = element("li", {className: "g-gate",
      "data-gate-state": node.gate.state}, [
      element("span", {className: "mono", text: node.gate.gate_id}),
      chip(GATE_CHANNEL[node.gate.state], GATE_GLYPHS[node.gate.state], true),
    ]);
    const local = state.decisions[node.gate.gate_id];
    if (local) item.append(element("span", {className: "g-note",
      text: `by ${local.actor} (fixture-only)`}));
    list.append(item);
  }
  mount.append(list);
}

export function renderTimeline(mount, state) {
  mount.replaceChildren(element("h2", {text: "Execution timeline"}));
  if (!state.timeline.length) {
    mount.append(element("p", {className: "empty", text: "No recorded events."}));
    return;
  }
  const list = element("ol", {className: "g-timeline"});
  for (const row of state.timeline) {
    list.append(element("li", {className: "g-timeline__row"}, [
      element("span", {className: "mono g-timeline__at", text: row.at}),
      element("span", {className: "mono", text: row.node_id}),
      chip(PHASE_CHANNEL[row.phase], row.phase),
    ]));
  }
  mount.append(list);
}

export function renderComposer(mount, state, draft, onCompose) {
  mount.replaceChildren(element("h2", {text: "Compose"}));
  if (!state.nodes.length) return;
  const form = element("form", {className: "g-compose"});
  const title = draftInput(draft, "title", {autocomplete: "off",
    maxlength: "80", name: "title", required: "", spellcheck: "false",
    type: "text"});
  const harness = draftSelect(draft, "harness", [
    element("option", {text: "no harness", value: ""}),
    ...state.registry.map((row) =>
      element("option", {text: row.name, value: row.id})),
  ]);
  const anchor = draftSelect(draft, "anchor", state.nodes.map((node) =>
    element("option", {text: node.title, value: node.node_id})));
  const placement = draftSelect(draft, "placement", [
    element("option", {text: "after", value: "after"}),
    element("option", {text: "parallel with", value: "parallel"}),
  ]);
  form.append(field("Step title", title), field("Harness", harness),
    field("Placement", placement), field("Anchor step", anchor),
    element("button", {name: "add", text: "Add step to fixture", type: "submit"}));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onCompose({title: draft.title, harness: draft.harness || null,
      anchorId: draft.anchor, placement: draft.placement});
  });
  mount.append(form);
}
