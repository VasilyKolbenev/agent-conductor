"use strict";
// Trace is a lens on the admitted scene. It owns geometry, never run state.
// The plan is drawn as a route over a planet's limb: work sits ON the horizon,
// human decisions hang on their own contour beneath it, and a loop returns
// under both. Every mark restates a fact of the scene; nothing moves by itself.
import {element} from "./command-view.js";
import {traceLayout} from "./studio-scene-model.js";
import {localize} from "./studio-i18n.js";

const HEIGHT = 450, PLANET_TOP = 12, TAIL = 30, CLOSE = 60, DEPTH = {task: 0, gate: 78, loop: 124};
const svg = (tag, attrs) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
};
const glyph = (word) => word === "needs_decision" ? "◇" : word === "decision_unknown" ? "?"
  : word === "closed" ? "⊘" : word === "awaiting_result" ? "◉"
  : ["settled", "outcome_succeeded", "decision_satisfied"].includes(word) ? "✓"
  : word === "outcome_unknown" ? "?" : word === "outcome_cancelled" ? "⊘"
  : word.startsWith("outcome_") ? "×" : "○";

// Two letters that tell participants apart: taken from what an id does NOT
// share with every other id in the run, so `instance-role-thinker` and
// `instance-role-checker` read TH and CH rather than IN and IN.
export function participantBadge(id, ids) {
  const parts = (value) => String(value).split(/[-_.\s]+/).filter(Boolean);
  const own = parts(id).filter((part) => !ids.every((other) => parts(other).includes(part)));
  const source = own.length ? own : parts(id).slice(-1);
  const letters = source.length >= 2 ? source.slice(0, 2).map((part) => part[0])
    : Array.from(source[0] || String(id)).slice(0, 2);
  return letters.join("").toUpperCase();
}
// The limb is one quadratic: 246 at both edges, 210 at the centre.
const limb = (x, width) => 246 - 144 * (width ? x / width : 0) * (1 - (width ? x / width : 0));
const along = (from, to, width, depth) => {
  const count = Math.max(2, Math.ceil(Math.abs(to - from) / 24)), parts = [];
  for (let at = 0; at <= count; at += 1) {
    const x = from + (to - from) * at / count;
    parts.push(`${at ? "L" : "M"} ${x.toFixed(1)} ${(limb(x, width) + depth).toFixed(1)}`);
  }
  return parts.join(" ");
};

function stepButton(step, state, choose) {
  const control = element("button", {type: "button", className: "studio-trace__step",
    "data-trassa-step": step.nodeId, "data-kind": step.kind, "data-word": step.word,
    "data-focus-key": `trace-step:${step.nodeId}`, "aria-pressed": "false", title: step.title}, [
    element("span", {className: "studio-trace__point", text: glyph(step.word)}),
    element("span", {className: "studio-trace__title", text: step.title}),
    element("span", {className: "studio-trace__word", text: localize(state, `scene.${step.word}`)}),
  ]);
  if (step.kind === "gate") control.dataset.trassaGate = step.nodeId;
  control.addEventListener("click", () => choose(step.ownerId, step.nodeId));
  return control;
}

function planetButton(participant, state, choose, ids) {
  const control = element("button", {type: "button", className: "studio-planet studio-trace__planet",
    "data-trassa-instance": participant.instanceId, "data-word": participant.word,
    "data-focus-key": `trace-participant:${participant.instanceId}`,
    "aria-pressed": "false", title: participant.instanceId}, [
    element("span", {className: "studio-planet__orb", "aria-hidden": "true",
      text: participantBadge(participant.instanceId, ids)}),
    element("strong", {text: participant.instanceId}),
    element("span", {className: "studio-trace__duty",
      text: `${localize(state, `scene.duty_${participant.duty}`)} · ${participant.adapter}`}),
    element("span", {className: "studio-trace__word", text: localize(state, `scene.${participant.word}`)}),
  ]);
  control.addEventListener("click", () => choose(participant.instanceId, null));
  return control;
}

// The model ends 24px after its last mark and that mark's words are wider, so the
// lens keeps a tail. A plan that misses the window by a few percent is drawn
// tighter instead of growing a scrollbar for one clipped word; a longer plan scrolls.
function fitted(geometry, available) {
  const needed = geometry.width + TAIL;
  const scale = needed > available && needed <= available * 1.14 ? available / needed : 1;
  const shift = (point) => ({...point, x: point.x * scale});
  return {scale, width: Math.max(available, needed * scale), points: geometry.points.map(shift),
    planets: geometry.planets.map(shift)};
}

function placed(scene, geometry) {
  const kinds = new Map(scene.steps.map((step) => [step.nodeId, step.kind]));
  let before = null;
  return new Map(geometry.points.map((point) => {
    const kind = kinds.get(point.id);
    // A loop's slot is narrow: beside a gate its mark would sit on the gate's words.
    const x = kind === "loop" && before !== null && point.x - before < CLOSE + 8
      ? Math.min(before + CLOSE + 8, geometry.width - 52) : point.x;
    before = x;
    return [point.id, {x, y: limb(x, geometry.width) + (DEPTH[kind] ?? 0), kind}];
  }));
}

// A road between two depths leaves the upper mark sideways and enters the lower
// one from above, so it never runs through the words printed under a mark.
function descent(a, b) {
  const [high, low] = a.y <= b.y ? [a, b] : [b, a], side = low.x >= high.x ? 1 : -1;
  // Too close to clear the upper words: go round them and enter from the far side.
  if (Math.abs(low.x - high.x) < CLOSE) {
    return `M ${high.x + 15 * side} ${high.y + 2} C ${high.x + 74 * side} ${high.y + 2} `
      + `${low.x + 66 * side} ${low.y - 26} ${low.x + 15 * side} ${low.y}`;
  }
  return `M ${high.x + 15 * side} ${high.y + 2} C ${high.x + 62 * side} ${high.y + 6} `
    + `${low.x - 34 * side} ${low.y - 40} ${low.x - 10 * side} ${low.y - 13}`;
}

function arrow(layer, x, y, dx, dy, open) {
  layer.append(svg("path", {class: "studio-trace__arrow", "data-open": String(open),
    d: `M ${x - 5 * dx - 4 * dy} ${y - 5 * dy + 4 * dx} L ${x} ${y} L ${x - 5 * dx + 4 * dy} ${y - 5 * dy - 4 * dx}`}));
}

function drawLink(layer, link, points, state, width) {
  const a = points.get(link.from), b = points.get(link.to);
  if (!a || !b) return;
  const level = a.kind === b.kind, side = b.x >= a.x ? 1 : -1;
  const path = svg("path", {class: "studio-trace__link", "data-open": String(link.open),
    d: level ? along(a.x + 16 * side, b.x - 16 * side, width, DEPTH[a.kind] ?? 0) : descent(a, b)});
  const title = svg("title", {});
  title.textContent = `${link.from} → ${link.to}${link.condition ? `: ${link.condition}` : ""}`;
  path.append(title); layer.append(path);
  if (level) arrow(layer, b.x - 17 * side, limb(b.x - 17 * side, width) + (DEPTH[b.kind] ?? 0), side, 0, link.open);
  else if (b.y > a.y && Math.abs(b.x - a.x) < CLOSE) arrow(layer, b.x + 15 * side, b.y, -side, 0, link.open);
  else if (b.y > a.y) arrow(layer, b.x - 10 * side, b.y - 13, 0.6 * side, 0.8, link.open);
  else arrow(layer, b.x - 15 * side, b.y + 2, side, 0, link.open);
  if (!link.condition) return;
  const text = svg("text", {x: (a.x + b.x) / 2 + 26 * side, y: (a.y + b.y) / 2 - 12, "text-anchor": "middle"});
  text.textContent = localize(state, `condition.${link.condition}`); layer.append(text);
}

function tethers(layer, scene, points, selected, x, foot) {
  for (const participant of scene.participants.filter((row) => row.instanceId === selected)) {
    for (const [duty, ids] of [["perform", participant.performs], ["verify", participant.verifies]]) {
      for (const target of ids.map((id) => points.get(id)).filter(Boolean)) {
        const bend = (foot + target.y - 16) / 2;
        layer.append(svg("path", {class: "studio-trace__tether", "data-duty": duty, "data-open": "true",
          d: `M ${x} ${foot} C ${x} ${bend} ${target.x} ${bend} ${target.x} ${target.y - 18}`}));
      }
    }
  }
}

function pips(layer, loop, x, y) {
  const bound = Number.isInteger(loop.bound) ? Math.min(loop.bound, 8) : 0;
  for (let at = 0; at < bound; at += 1) {
    const cx = x - (bound - 1) * 7 + at * 14;
    layer.append(svg("path", {class: "studio-trace__pip", "data-open": String(at < (loop.pass ?? 0)),
      d: `M ${cx - 4} ${y} a 4 4 0 1 0 8 0 a 4 4 0 1 0 -8 0`}));
  }
}

function loopArcs(layer, scene, points, state) {
  for (const loop of scene.loops) {
    const from = points.get(loop.nodeId), to = points.get(loop.backTo);
    if (!from || !to) continue;
    const floor = Math.min(HEIGHT - 44, Math.max(from.y, to.y) + 78), middle = (from.x + to.x) / 2;
    const turn = to.x <= from.x ? 1 : -1;  // leave on the side the road returns to, clear of the words
    layer.append(svg("path", {class: "studio-trace__return",
      "data-open": String(loop.pass >= 2 && scene.positions.includes(loop.backTo)),
      d: `M ${from.x - 13 * turn} ${from.y + 3} C ${from.x - 84 * turn} ${floor + 30} ${to.x} ${floor + 26} ${to.x} ${to.y + 58}`}));
    arrow(layer, to.x, to.y + 58, 0, -1, loop.pass >= 2 && scene.positions.includes(loop.backTo));
    pips(layer, loop, middle, floor + 10);
    const label = svg("text", {x: middle, y: floor + 32, "text-anchor": "middle"});
    label.textContent = loop.boundReached ? localize(state, "scene.bound_reached")
      : localize(state, "scene.pass", {pass: String(loop.pass ?? "—"), bound: String(loop.bound ?? "—")});
    layer.append(label);
  }
}

function backdrop(layer, width) {
  const edge = limb(0, width), apex = 2 * 210 - edge;
  const crest = `M 0 ${edge} Q ${width / 2} ${apex} ${width} ${edge}`;
  layer.replaceChildren(
    svg("path", {class: "studio-trace__horizon", d: `${crest} L ${width} ${HEIGHT} L 0 ${HEIGHT} Z`}),
    svg("path", {class: "studio-trace__glow", "data-open": "true", d: crest}),
    svg("path", {class: "studio-trace__contour", d: along(0, width, width, DEPTH.gate)}));
}

function drawGeometry(inner, scene, geometry, state, selected) {
  inner.style.width = `${geometry.width}px`;
  inner.style.setProperty("--trace-step", `${Math.floor(100 * geometry.scale)}px`);
  const layer = inner.querySelector("svg"), points = placed(scene, geometry);
  layer.setAttribute("viewBox", `0 0 ${geometry.width} ${HEIGHT}`);
  backdrop(layer, geometry.width);
  const planets = new Map(geometry.planets.map((point) => [point.id, point.x]));
  for (const button of inner.querySelectorAll("[data-trassa-instance]")) {
    button.style.left = `${planets.get(button.dataset.trassaInstance)}px`;
    // The tether leaves from under the card it belongs to, never across its words.
    if (button.dataset.trassaInstance === selected) tethers(layer, scene, points, selected,
      planets.get(selected), Math.min(PLANET_TOP + button.offsetHeight + 6, 174));
  }
  for (const link of scene.links) drawLink(layer, link, points, state, geometry.width);
  loopArcs(layer, scene, points, state);
  for (const button of inner.querySelectorAll("[data-trassa-step]")) {
    const point = points.get(button.dataset.trassaStep);
    if (point) { button.style.left = `${point.x}px`; button.style.top = `${point.y - 14}px`; }
  }
}

export function traceView(scene, state, choose, previous) {
  const root = element("section", {className: "studio-trace", "aria-label": localize(state, "scene.trace"),
    tabindex: "0", "data-focus-key": "trace-scroll"});
  const ids = scene.participants.map((row) => row.instanceId);
  const inner = element("div", {className: "studio-trace__inner"}, [svg("svg", {"aria-hidden": "true"}),
    ...scene.participants.map((row) => planetButton(row, state, choose, ids)),
    ...scene.steps.map((row) => stepButton(row, state, choose))]);
  root.append(inner);
  let centre = previous === null, selected = scene.participants[0]?.instanceId || null;
  function layout() {
    if (!root.isConnected || root.hidden || !root.clientWidth) return;
    const geometry = fitted(traceLayout(scene, Math.max(0, root.clientWidth - TAIL)), root.clientWidth);
    drawGeometry(inner, scene, geometry, state, selected);
    if (centre) {
      const point = geometry.points.find((row) => row.id === scene.positions[0]);
      root.scrollLeft = Math.max(0, (point?.x || 0) - root.clientWidth / 2); centre = false;
    } else if (previous !== null) { root.scrollLeft = previous; previous = null; }
  }
  const observer = new ResizeObserver(layout); observer.observe(root);
  return {root, reveal: (id) => {
    const planet = [...root.querySelectorAll("[data-trassa-instance]")].find((node) => node.dataset.trassaInstance === id);
    if (planet) root.scrollLeft = Math.max(0, parseFloat(planet.style.left) - root.clientWidth / 2);
  }, dispose: () => observer.disconnect(), show: (recenter) => {
    if (recenter) centre = true; layout();
  }, select: (instance, step) => {
    selected = instance; layout();
    for (const button of root.querySelectorAll("[aria-pressed]")) button.setAttribute("aria-pressed",
      String(button.dataset.trassaStep ? button.dataset.trassaStep === step : button.dataset.trassaInstance === instance));
  }};
}
