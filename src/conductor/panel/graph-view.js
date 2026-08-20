"use strict";
// Every Graph node is built from text: no markup string is ever parsed here.
// Identity and status stay on separate channels — the harness accent reaches
// the badge swatch and nothing else; status reaches the glyph, the word and
// the chip contour, exactly the split index.html documents for the panel.
import {element, field} from "./command-view.js";
import {AVAILABILITY_STATES, DECISION_ACTIONS, GATE_CHANNEL,
  OUTCOME_CHANNEL, PHASE_CHANNEL, STAGE_NAMES} from "./graph-payload.js";

// Geometry constants the layout renders and the browser suite measures.
export const CELL = Object.freeze({width: 210, height: 118, gapX: 46, gapY: 18});

const GATE_GLYPHS = Object.freeze({
  pending: "○ pending",
  satisfied: "✓ approved",
  failed: "✕ rejected",
  changes_requested: "■ changes requested",
  waived: "◇ waived",
  // Two standing receipts for one gate: the journal supports two answers and
  // therefore neither. Said as its own word, never softened into pending and
  // never rounded up into approved.
  unknown: "? two standing decisions",
});
const HEALTH_CHANNEL = Object.freeze({
  ready: "pass", busy: "wait", offline: "fail", degraded: "wait",
  unknown: "none",
});
// AVAILABILITY_STATES in channel order: available, experimental, unavailable.
const AVAILABILITY_CHANNEL = Object.freeze(Object.fromEntries(
  AVAILABILITY_STATES.map((state, index) => [state, ["pass", "wait", "fail"][index]])));
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
      text: "No registry rows in this payload."}));
    return;
  }
  const list = element("ul", {className: "g-palette"});
  for (const row of state.registry) {
    const item = element("li", {className: "g-palette__row"}, [
      badge(state.registry, row.id),
    ]);
    // A row that names its availability gets the chip; one that does not
    // claims nothing and shows nothing — never a default. The label is the
    // vocabulary word in capitals, so EXPERIMENTAL and UNAVAILABLE cannot be
    // read as anything softer.
    if (row.availability) {
      item.append(chip(AVAILABILITY_CHANNEL[row.availability],
        row.availability.toUpperCase()));
    }
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

//: The gate word on screen and the ONE document it came from. A durable gate
//: answers from the run's projection; a fixture gate answers from its own
//: field. There is no third source and no default — a gate that neither
//: document states draws no chip rather than a reassuring one.
function gateWord(node) {
  if (node.runtime !== null) return node.runtime.decision;
  return node.gate === null ? null : node.gate.state;
}

//: The run's position, as chips, kept in one place so a definition chip and a
//: runtime chip are never built by the same line. `observed` and the outcome
//: are two chips on purpose: a boundary reached is not a result reported, and
//: one chip carrying both is precisely the inference safety law 9 forbids.
function runtimeChips(node) {
  const facts = node.runtime;
  const chips = [chip(PHASE_CHANNEL[facts.phase], facts.phase)];
  chips.push(facts.outcome === null
    ? chip("none", "no result recorded")
    : chip(OUTCOME_CHANNEL[facts.outcome], facts.outcome));
  if (facts.decision !== null) {
    chips.push(chip(GATE_CHANNEL[facts.decision],
      GATE_GLYPHS[facts.decision], true));
  }
  if (facts.pass !== null && node.loop !== null) {
    chips.push(element("span", {className: "mono g-loop-pass",
      text: `↻ pass ${facts.pass} of ×${node.loop.bound}`
        + (facts.boundReached ? " · bound reached" : "")}));
  }
  return chips;
}

// The chip row, in reading order: what the plan says, then — behind its own
// rule and label — what the run says. A word only ever appears where a
// document states one, so a node whose position comes from the runtime
// projection draws no health and no phase among the plan's chips.
function nodeChips(node) {
  const chips = element("span", {className: "g-node__chips"});
  if (node.health !== null) chips.append(chip(HEALTH_CHANNEL[node.health],
    node.health));
  if (node.phase !== null) chips.append(chip(PHASE_CHANNEL[node.phase],
    node.phase));
  const gate = gateWord(node);
  if (gate !== null && node.runtime === null) {
    chips.append(chip(GATE_CHANNEL[gate], GATE_GLYPHS[gate], true));
  }
  // A loop wears its BOUND where the graph is read: the one sanctioned shape
  // of a cycle is "at most ×N", said out loud. The bound is the plan's and
  // sits here; which pass a run is on is the projection's and sits with the
  // other runtime chips, so a ceiling is never read as a position.
  if (node.loop) chips.append(element("span",
    {className: "mono g-loop-bound", text: node.loop.pass !== null
      ? `↻ pass ${node.loop.pass}/${node.loop.bound}`
      : `↻ ×${node.loop.bound}`}));
  if (node.runtime !== null) {
    const run = element("span", {className: "g-node__run"});
    run.append(element("i", {className: "mono g-node__runlabel", text: "run"}));
    for (const part of runtimeChips(node)) run.append(part);
    chips.append(run);
  }
  if (node.draft) chips.append(chip("none", "LOCAL DRAFT"));
  return chips;
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
  button.append(head);
  // The semantic stage is its own numbered line — never inferred from the
  // runtime phase, which says what happened, not which step this is.
  if (node.stage) button.append(element("span", {className: "mono g-stage",
    text: `${STAGE_NAMES.indexOf(node.stage) + 1}/5 · ${node.stage}`}));
  button.append(element("span", {className: "g-node__title", text: node.title}));
  button.append(nodeChips(node));
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
      "Recorded in this window only, beside whatever the run's own journal "
      + "says. Nothing is executed or sent."}),
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

// The card's middle: the loop bound, the draft label, capabilities, and the
// closed resource attachments — a node that attaches nothing shows no
// Resources section, claiming nothing.
function appendDetailFacts(mount, node, nodes) {
  if (node.stage) {
    mount.append(element("p", {className: "mono g-det__meta",
      text: `stage ${STAGE_NAMES.indexOf(node.stage) + 1} of 5 — ${node.stage}`}));
  }
  if (node.loop) {
    const passText = node.loop.pass !== null
      ? `pass ${node.loop.pass} of ${node.loop.bound}`
      : `at most ×${node.loop.bound} passes`;
    const target = node.loop.backTo === null ? null
      : nodes.find((row) => row.node_id === node.loop.backTo);
    mount.append(element("p", {className: "mono g-det__meta",
      text: `bounded loop · ${passText}`
        + (target ? ` · reopens: ${target.title}` : "")}));
    mount.append(element("p", {className: "g-note", text:
      "A pass reopens work — it executes nothing, and every effect still "
      + "needs its own fresh Confirm."}));
  }
  if (node.draft) {
    const draftChip = chip("none",
      "LOCAL DRAFT — held in this window, written to no run");
    // The one sentence-length chip: it must wrap, not widen the page.
    draftChip.classList.add("g-chip--long");
    mount.append(draftChip);
  }
  const names = node.capabilities.length ? node.capabilities.join(", ") : "none";
  mount.append(element("p", {className: "mono g-det__meta",
    text: `capabilities: ${names}`}));
  if (node.resources.length) {
    mount.append(element("h3", {text: "Resources"}));
    mount.append(element("ul", {className: "g-resources"},
      node.resources.map((row) => element("li", {className: "mono",
        text: `${row.kind}: ${row.name}`}))));
  }
}

// What the PLAN binds this step to, under its own heading. `instance`, not
// a product name: the plan names where work runs and the configuration names
// which adapter serves it, and this window never collapses the two.
function appendPlanBinding(mount, node) {
  if (node.binding === null) return;
  mount.append(element("h3", {className: "g-det__plan", text: "Plan binding"}));
  mount.append(element("p", {className: "mono g-det__meta",
    text: `instance: ${node.binding.instanceId}`}));
  mount.append(element("p", {className: "mono g-det__meta",
    text: `capability: ${node.binding.capability}`}));
  if (!node.binding.argumentRows.length) return;
  mount.append(element("ul", {className: "g-arguments"},
    node.binding.argumentRows.map((row) => element("li", {className: "mono"}, [
      element("span", {className: "g-arg__name", text: row.name}),
      element("span", {className: "g-arg__value", text: row.value}),
    ]))));
}

// What the RUN did, under its own heading and never mixed into the plan's.
// Every identifier here is a join key into the durable records and nothing
// more: no verification, no label, no digest, no exit code — those live where
// a contract validated them, and repeating them here without one would be
// this window inventing a claim.
function appendRunPosition(mount, node) {
  if (node.runtime === null) return;
  const facts = node.runtime;
  mount.append(element("h3", {className: "g-det__run", text: "Run position"}));
  mount.append(element("div", {className: "g-det__chips"}, runtimeChips(node)));
  mount.append(element("p", {className: "g-note", text:
    "Computed from the durable records on every read and stored nowhere. "
    + "`observed` means an execution boundary was reached — it is not "
    + "success."}));
  mount.append(element("p", {className: "mono g-det__meta", text:
    `observed at: ${facts.observedAt === null ? "—" : facts.observedAt}`}));
  const attempts = facts.attempts.length ? facts.attempts.join(", ") : "none";
  mount.append(element("p", {className: "mono g-det__meta",
    text: `attempts: ${attempts}`}));
  mount.append(element("p", {className: "mono g-det__meta", text:
    `evidence refs: ${facts.evidenceRefs.length
      ? facts.evidenceRefs.join(", ") : "none"}`}));
  if (facts.evidenceRefs.length) {
    mount.append(element("p", {className: "g-note", text:
      "Identifiers only. Nothing here states that any of them verified."}));
  }
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
  const chips = element("div", {className: "g-det__chips"});
  // "health", not "availability": that word now names the harness-level
  // state in the palette, and one word must not carry two claims. Both are
  // the run's words, so both are absent when the run's own document is the
  // source and they are drawn under Run position instead.
  if (node.health !== null) {
    chips.append(chip(HEALTH_CHANNEL[node.health], `health: ${node.health}`));
  }
  if (node.phase !== null) {
    chips.append(chip(PHASE_CHANNEL[node.phase], `phase: ${node.phase}`));
  }
  mount.append(element("p", {className: "g-det__title", text: node.title}), head,
    element("p", {className: "mono g-det__meta",
      text: `${node.node_id} · ${node.kind}`}), chips);
  appendDetailFacts(mount, node, state.nodes);
  appendPlanBinding(mount, node);
  appendRunPosition(mount, node);
  if (node.runtime === null) {
    mount.append(element("h3", {text: "Evidence"}));
    mount.append(node.evidence.length
      ? element("ul", {className: "g-evidence-list"}, node.evidence.map(evidenceRow))
      : element("p", {className: "empty", text: "No evidence recorded."}));
  }
  const gate = gateWord(node);
  if (gate !== null) {
    mount.append(chip(GATE_CHANNEL[gate],
      `${node.gate.gate_id}: ${GATE_GLYPHS[gate]}`, true));
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
    const gate = gateWord(node);
    const item = element("li", {className: "g-gate",
      "data-gate-state": gate}, [
      element("span", {className: "mono", text: node.gate.gate_id}),
      chip(GATE_CHANNEL[gate], GATE_GLYPHS[gate], true),
    ]);
    // An own-key read: "constructor" is a valid gate id, and an inherited
    // member must never render as an attribution nobody recorded.
    const local = Object.hasOwn(state.decisions, node.gate.gate_id)
      ? state.decisions[node.gate.gate_id] : null;
    // Beside the durable answer, never instead of it: on a run-stated gate
    // the chip above stays the journal's word and this line says whose draft
    // is sitting next to it, unsubmitted.
    if (local) item.append(element("span", {className: "g-note",
      text: `LOCAL DRAFT by ${local.actor} — not submitted`}));
    list.append(item);
  }
  mount.append(list);
}

export function renderTimeline(mount, state) {
  mount.replaceChildren(element("h2", {text: "Execution timeline"}));
  if (!state.timeline.length) {
    // A durable read carries positions, not instants: the run projection
    // names the current action's time and no earlier one, so there is no
    // timeline to show rather than an empty one to imply.
    mount.append(element("p", {className: "empty",
      text: state.provenance.source === "durable"
        ? "The run read carries positions, not a history of events. "
          + "Each node's own card names its current action's instant."
        : "No recorded events."}));
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
  mount.replaceChildren();
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
    element("option", {value: node.node_id, text:
      node.draft ? `${node.title} — LOCAL DRAFT` : node.title})));
  const placement = draftSelect(draft, "placement", [
    element("option", {text: "after", value: "after"}),
    element("option", {text: "parallel with", value: "parallel"}),
  ]);
  form.append(field("Step title", title), field("Harness", harness),
    field("Placement", placement), field("Anchor step", anchor),
    element("button", {name: "add", text: "Add step to drawing", type: "submit"}));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onCompose({title: draft.title, harness: draft.harness || null,
      anchorId: draft.anchor, placement: draft.placement});
  });
  mount.append(form);
}

//: The word a reader sees for each source, and the ONE place either is
//: spelled for the screen. `LOCAL DRAFT` and `DURABLE` never share a token,
//: so no drawing this window made can be dressed in the other's word.
const SOURCE_LABEL = Object.freeze({
  durable: "DURABLE — written to the run's journal",
  fixture: "LOCAL DRAFT — held in this window, written to no run",
});

// The provenance line: where the drawing on screen came from, and — only for
// a durable plan — the digest computed over it on this very read. A fixture
// has no digest to show, because nothing has checked it and nothing could.
export function renderSource(mount, state) {
  mount.replaceChildren();
  const durable = state.provenance.source === "durable";
  mount.append(chip(durable ? "pass" : "none",
    SOURCE_LABEL[state.provenance.source]));
  if (!durable) return;
  mount.append(element("span", {className: "mono g-src__id",
    text: `graph: ${state.provenance.graphId}`}));
  mount.append(element("span", {className: "mono g-src__digest",
    text: state.provenance.digest}));
  mount.append(element("span", {className: "g-note", text:
    "The digest is computed over the plan on every read and stored beside "
    + "it nowhere. The plan is immutable: it is written once, never edited."}));
}

const SAVE_NOTE = Object.freeze({
  durable: "This run already follows a plan. A graph is written once and "
    + "never edited, so a different plan is refused rather than applied.",
  fixture: "Save writes the drawing above to the named run as its one "
    + "immutable plan. Only this button writes it, and only what the plan "
    + "declares is sent — no phase, outcome, pass or decision goes with it.",
});

// The save door, and the whole of it: one button, pressed by a Human, and no
// other path into this handler. Nothing about the drawing, the stream or a
// reconnect may reach it — a plan that reaches the journal can never be
// edited, so it may only ever be written on purpose.
export function renderSave(mount, state, draft, onSave) {
  mount.replaceChildren(element("h2", {text: "Write the plan"}));
  const durable = state.provenance.source === "durable";
  const form = element("form", {className: "g-save"});
  const graphId = draftInput(draft, "graphId", {autocomplete: "off",
    maxlength: "128", name: "graphId",
    pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}", required: "",
    spellcheck: "false", type: "text"});
  form.append(field("Graph id", graphId), element("button",
    {name: "save", text: "Save plan to run", type: "submit"}));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onSave(draft.graphId.trim());
  });
  mount.append(form, element("p", {className: "g-note",
    text: SAVE_NOTE[durable ? "durable" : "fixture"]}));
  // Said where the shut door is, not only in the status line above it: a
  // control a reader cannot press owes them the reason on its own card.
  if (!state.writeReady) {
    mount.append(element("p", {className: "g-note g-save__shut", text:
      "The run-event stream is not carrying, so this window cannot know what "
      + "it would be writing on top of. Writing resumes when the stream is "
      + "back and this run has been read again."}));
  }
}
