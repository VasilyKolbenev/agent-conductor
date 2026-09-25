"use strict";
// The command deck reads ONE frozen run, not the currently edited workflow or
// the machine's installed-provider roster. A planet is an instance: two steps
// using one instance remain one planet, and two instances using one adapter
// remain two. Selection is presentation only and never authorizes execution.
import {feedbackFindings} from "./studio-feedback.js";
import {element} from "./command-view.js";
import {sceneOf} from "./studio-scene-model.js";
import {participantBadge, traceView} from "./studio-trace.js";
import {localize} from "./studio-i18n.js";
import {latestDocument, attemptInFlight} from "./studio-runread.js";
import {inputRefs} from "./studio-rundocs.js";
import {CAPABILITY_FIELDS} from "./command-projection.js";
import {VERIFICATION_FAILED_NOTE, RECORD_KINDS} from "./studio-runwords.js";

const observers = new WeakMap();
let diagramId = 0;
export function releaseParticipants(mount) {
  const deck = mount.querySelector("[data-deck-run]");
  observers.get(deck)?.disconnect();
}

function rows(value) { return Array.isArray(value) ? value : []; }
function show(state, value) { return value === null || value === undefined
  || value === "" ? localize(state, "participants.m1") : String(value); }
function note(text) { return element("p", {className: "studio-note", text}); }
function fact(state, label, value) { return note(`${label}: ${show(state, value)}`); }

export function participantSelection(mount) {
  const deck = mount.querySelector("[data-deck-run]");
  return deck ? {run: deck.dataset.deckRun, instance: deck.dataset.selectedInstance || "",
    step: deck.dataset.detailStep, lens: deck.dataset.deckLens,
    traceScroll: deck.querySelector(".studio-trace")?.scrollLeft || 0,
    open: [...deck.querySelectorAll("[data-detail-fold][open]")].map((el) => el.dataset.detailFold),
    about: Boolean(deck.querySelector(".studio-deck__about")?.open),
    scroll: deck.querySelector(".studio-deck__inspector")?.scrollTop || 0} : null;
}

export function restoreParticipantScroll(mount, previous) {
  const deck = mount.querySelector("[data-deck-run]");
  if (deck?.dataset.deckRun === previous?.run
    && deck?.dataset.selectedInstance === previous?.instance
    && deck?.dataset.detailStep === previous?.step) {
    const panel = deck?.querySelector(".studio-deck__inspector");
    if (panel) panel.scrollTop = previous.scroll;
  }
}

function stepsOf(detail, instance) {
  return rows(detail.graph?.definition?.nodes)
    .filter((node) => node.instance_id === instance
      || node.verifier_instance_id === instance);
}

function routesOf(state, detail, bound) {
  const nodes = rows(detail.graph?.definition?.nodes);
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const known = new Set(bound.map((instance) => instance.id));
  const routes = new Map();
  function add(from, to, label) {
    if (from === to || !known.has(from) || !known.has(to)) return;
    const key = JSON.stringify([from, to]);
    if (!routes.has(key)) routes.set(key, {from, to, labels: new Set()});
    routes.get(key).labels.add(label);
  }
  for (const edge of rows(detail.graph?.definition?.edges)) {
    add(byId.get(edge.from_node)?.instance_id, byId.get(edge.to_node)?.instance_id,
      Object.prototype.hasOwnProperty.call(edge, "condition")
        ? show(state, edge.condition) : "unconditional");
  }
  for (const node of nodes) add(node.instance_id, node.verifier_instance_id, "verification");
  return [...routes.values()];
}

function svgElement(tag, attributes) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function routeLine(svg, route, a, b, markerId) {
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  if (length <= a.r + b.r) return;
  const ux = (b.x - a.x) / length, uy = (b.y - a.y) / length;
  const start = [a.x + ux * a.r, a.y + uy * a.r];
  const end = [b.x - ux * b.r, b.y - uy * b.r];
  const bend = Math.min(64, length / 4);
  const control = [(start[0] + end[0]) / 2 - uy * bend,
    (start[1] + end[1]) / 2 + ux * bend];
  const path = svgElement("path", {class: "studio-deck__route",
    "data-from": route.from, "data-to": route.to,
    d: `M ${start} Q ${control} ${end}`, "marker-end": `url(#${markerId})`});
  const title = svgElement("title", {});
  title.textContent = `${route.from} → ${route.to}: ${[...route.labels].join(", ")}`;
  const x = (start[0] + 2 * control[0] + end[0]) / 4;
  const y = (start[1] + 2 * control[1] + end[1]) / 4 - 13;
  const kind = route.labels.has("verification") ? "verification" : "route";
  const label = svgElement("g", {class: "studio-deck__route-label", "data-kind": kind,
    transform: `translate(${x - 8} ${y - 8})`});
  // A lens means a verification assignment, never a successful verification.
  label.append(svgElement("path", {d: kind === "verification"
    ? "M 11 7 A 4 4 0 1 1 3 7 A 4 4 0 1 1 11 7 M 10 10 L 15 15"
    : "M 1 8 H 15 M 10 3 L 15 8 L 10 13"}));
  path.append(title); svg.append(path, label);
}

const RING = {minWidth: 620, maxPlanets: 6, card: 132, row: 190, orb: 30};
// Planets take the upper arc, left to right in plan order; the lower arc is the
// human contour's, so a decision never lands under a participant's card.
const angleAt = (index, count) => count <= 1 ? 1.5 * Math.PI : Math.PI + Math.PI * index / (count - 1);
const pointAt = (centre, radius, theta) => ({x: centre.x + radius.rx * Math.cos(theta),
  y: centre.y + radius.ry * Math.sin(theta)});

// Planets in the order the plan first uses them, clockwise over the top from the
// left; a participant the plan never uses comes last. An angle is composition only.
function ringOrder(scene) {
  const first = new Map();
  for (const step of scene.steps) {
    for (const id of [step.ownerId, step.verifierId]) if (id && !first.has(id)) first.set(id, step.slot);
  }
  return scene.participants.map((row) => row.instanceId)
    .sort((a, b) => (first.get(a) ?? 1e9) - (first.get(b) ?? 1e9));
}

// Human decisions and bounded returns run right to left along the lower arc in
// plan order, so the picture reads as the cycle does: up the left, across the
// top, down the right and back along the bottom to where a return lands.
function contourAngles(scene) {
  const marks = scene.steps.filter((row) => row.kind !== "task");
  return new Map(marks.map((step, index) => [step.nodeId,
    Math.PI * (55 + 70 * index / Math.max(1, marks.length - 1)) / 180]));
}

function ringPlaces(fleet, scene) {
  const width = fleet.clientWidth, height = fleet.clientHeight, order = ringOrder(scene);
  if (width < RING.minWidth || order.length > (width >= 700 ? RING.maxPlanets : RING.maxPlanets - 1)) return null;
  const centre = {x: width / 2, y: height / 2 - 4};
  const inner = {rx: Math.min(width / 2 - RING.card / 2 - 12, 290), ry: Math.min(height / 2 - 126, 104)};
  const outer = {rx: Math.min(inner.rx + 50, width / 2 - 54), ry: inner.ry + 44};
  const angles = new Map(order.map((id, index) => [id, angleAt(index, order.length)]));
  const planets = new Map(order.map((id) => [id, pointAt(centre, inner, angles.get(id))]));
  // A card between the left and right ends of the arc reads upward, into the free sky.
  const up = new Set(order.filter((id) => angles.get(id) > Math.PI + 0.01 && angles.get(id) < 2 * Math.PI - 0.01));
  const core = {x: centre.x, y: centre.y + 60};
  return {centre, core, inner, outer, planets, up, gates: gatePlaces(scene, centre, outer, planets, up, core)};
}

const clearOf = (point, boxes) => !boxes.some((box) => point.x + 52 > box.left && point.x - 52 < box.right
  && point.y + 56 > box.top && point.y - 14 < box.bottom);

// A decision mark slides along the contour until it stands clear of every
// planet's card and of the core; the plan's order still decides where it starts.
function gatePlaces(scene, centre, outer, planets, up, core) {
  const boxes = [...planets].map(([id, p]) => ({left: p.x - 70, right: p.x + 70,
    top: up.has(id) ? p.y - 150 : p.y - 40, bottom: up.has(id) ? p.y + 40 : p.y + 150}));
  boxes.push({left: core.x - 112, right: core.x + 112, top: core.y - 22, bottom: core.y + 22});
  const gates = new Map(), tries = [0, .15, -.15, .3, -.3, .45, -.45, .6, -.6, .75, -.75, .9, -.9];
  for (const [id, theta] of contourAngles(scene)) {
    const point = tries.map((delta) => pointAt(centre, outer, theta + delta)).find((candidate) => clearOf(candidate, boxes))
      || pointAt(centre, outer, theta);
    gates.set(id, point);
    boxes.push({left: point.x - 52, right: point.x + 52, top: point.y - 14, bottom: point.y + 56});
  }
  return gates;
}

// A narrow window or a large team: rows of cards, the fleet scrolling if it must.
function listPlaces(fleet, ids) {
  const columns = Math.max(1, Math.floor((fleet.clientWidth - 16) / (RING.card + 8)));
  const planets = new Map(ids.map((id, index) => [id, {
    x: 8 + RING.card / 2 + (index % columns) * (RING.card + 8),
    y: RING.orb + 8 + Math.floor(index / columns) * RING.row}]));
  return {planets, gates: new Map(), height: 16 + Math.ceil(ids.length / columns) * RING.row};
}

function placeFleet(fleet, places) {
  const move = (node, point) => {
    node.style.setProperty("--orb-x", `${point.x}px`); node.style.setProperty("--orb-y", `${point.y}px`);
  };
  for (const button of fleet.querySelectorAll("[data-instance]")) {
    const point = places.planets.get(button.dataset.instance) || {x: RING.card / 2, y: RING.orb + 8};
    const upward = Boolean(places.up?.has(button.dataset.instance));
    button.classList.toggle("studio-planet--up", upward);
    move(button, {x: point.x, y: point.y + (upward ? 1 : -1) * (RING.orb + 8)});
  }
  for (const mark of fleet.querySelectorAll("[data-orbit-kind]")) {
    const point = mark.dataset.orbitKind === "core" ? places.core : places.gates.get(mark.dataset.orbitStep);
    mark.hidden = !point;
    if (point) move(mark, point);
  }
}

function drawRings(svg, places) {
  for (const [radius, kind] of [[places.inner, "ring"], [places.outer, "contour"]]) {
    svg.append(svgElement("ellipse", {class: "studio-deck__ring", "data-kind": kind, stroke: "currentColor",
      cx: places.centre.x, cy: places.centre.y, rx: radius.rx, ry: radius.ry}));
  }
}

// Every step resolves to one mark: its owner's planet, its gate on the contour,
// or the bounded return at the core. Planet-to-planet roads are the routes.
function anchorsOf(scene, places, orbs) {
  const anchors = new Map();
  for (const step of scene.steps) {
    if (step.kind === "task" && orbs.has(step.ownerId)) anchors.set(step.nodeId, orbs.get(step.ownerId));
    else if (places.gates.has(step.nodeId)) anchors.set(step.nodeId, {...places.gates.get(step.nodeId), r: 24});
  }
  return anchors;
}

function contourLink(svg, a, b, places, markerId, link, state) {
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  if (length <= a.r + b.r) return;
  const ux = (b.x - a.x) / length, uy = (b.y - a.y) / length;
  const mid = {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
  // A road whose straight line would run through the core's words bends well past them.
  const overCore = Math.abs(mid.x - places.core.x) < 130 && Math.abs(mid.y - places.core.y) < 70;
  const bend = overCore ? 72 : Math.min(40, length / 4);
  const away = Math.hypot(mid.x - places.centre.x, mid.y - places.centre.y) || 1;
  const control = {x: mid.x + (mid.x - places.centre.x) / away * bend,
    y: mid.y + (mid.y - places.centre.y) / away * bend};
  const path = svgElement("path", {class: "studio-deck__contour", "data-kind": link.kind,
    "data-open": String(link.open), stroke: "currentColor", "marker-end": `url(#${markerId})`,
    d: `M ${a.x + ux * a.r} ${a.y + uy * a.r} Q ${control.x} ${control.y} ${b.x - ux * b.r} ${b.y - uy * b.r}`});
  const title = svgElement("title", {});
  title.textContent = `${link.from} → ${link.to}${link.condition ? `: ${link.condition}` : ""}`;
  path.append(title); svg.append(path);
  if (!link.condition) return;
  const word = svgElement("text", {class: "studio-deck__word", fill: "currentColor", "text-anchor": "middle",
    x: control.x, y: control.y + (control.y > places.centre.y ? 14 : -6)});
  word.textContent = localize(state, `condition.${link.condition}`); svg.append(word);
}

function contourLinks(svg, scene, places, orbs, markerId, state) {
  const anchors = anchorsOf(scene, places, orbs);
  const returns = scene.loops.map((loop) => ({from: loop.nodeId, to: loop.backTo, kind: "return",
    condition: null, open: loop.pass >= 2 && scene.positions.includes(loop.backTo)}));
  for (const link of [...scene.links, ...returns]) {
    const a = anchors.get(link.from), b = anchors.get(link.to);
    if (!a || !b || a === b || (a.orb && b.orb)) continue;
    contourLink(svg, a, b, places, markerId, link, state);
  }
}

function routeDiagram(fleet, routes, orbit) {
  const svg = svgElement("svg", {class: "studio-deck__routes", "aria-hidden": "true"});
  const markerId = `participant-route-${++diagramId}`;
  fleet.prepend(svg);
  function draw() {
    const places = orbit && fleet.clientWidth ? ringPlaces(fleet, orbit.scene)
      || listPlaces(fleet, orbit.scene.participants.map((row) => row.instanceId)) : null;
    if (places) placeFleet(fleet, places);
    const rect = fleet.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const height = Math.max(rect.height, places?.height || 0);
    svg.style.height = `${height}px`;
    svg.setAttribute("viewBox", `0 0 ${rect.width} ${height}`);
    svg.replaceChildren();
    const marker = svgElement("marker", {id: markerId, viewBox: "0 0 10 10",
      refX: "9", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto"});
    marker.append(svgElement("path", {d: "M 0 0 L 10 5 L 0 10 z"}));
    const defs = svgElement("defs", {}); defs.append(marker); svg.append(defs);
    if (places?.centre) drawRings(svg, places);
    const points = new Map([...fleet.querySelectorAll("[data-instance]")].map((button) => {
      const orb = button.querySelector(".studio-planet__orb").getBoundingClientRect();
      return [button.dataset.instance, {x: orb.x - rect.x + orb.width / 2,
        y: orb.y - rect.y + fleet.scrollTop + orb.height / 2, r: orb.width / 2 + 13, orb: true}];
    }));
    if (places?.centre) contourLinks(svg, orbit.scene, places, points, markerId, orbit.state);
    for (const route of routes) {
      const a = points.get(route.from), b = points.get(route.to);
      if (!a || !b) continue;
      routeLine(svg, route, a, b, markerId);
    }
  }
  const observer = new ResizeObserver(draw);
  observer.observe(fleet);
  return observer;
}

function disclosure(key, title, body) {
  return element("details", {className: "studio-inspect-more", "data-detail-fold": key}, [
    element("summary", {text: title, "data-focus-key": `participant-fold:${key}`}),
    element("div", {className: "studio-detail-pane", role: "region", "aria-label": title,
      tabindex: "0", "data-focus-key": `participant-body:${key}`}, body),
  ]);
}

function flowStage(kind, title, body) {
  const icon = svgElement("svg", {viewBox: "0 0 20 20", "aria-hidden": "true"});
  const paths = {input: "M 5 2 H 12 L 16 6 V 18 H 5 Z M 12 2 V 6 H 16 M 8 10 H 13 M 8 13 H 13",
    action: "M 7 4 L 16 10 L 7 16 Z", result: "M 3 5 H 17 V 17 H 3 Z M 3 10 H 7 L 9 13 H 11 L 13 10 H 17"};
  icon.append(svgElement("path", {d: paths[kind]}));
  return element("section", {className: "studio-step-flow__stage", "data-flow": kind}, [
    icon, element("div", {className: "studio-step-flow__body"}, [
      element("h5", {text: title}), element("div", {className: "studio-step-flow__value"}, body)]),
  ]);
}

function documentRead(state, doc, key) {
  // The fold key includes the immutable document identity: a live refresh must
  // never substitute newer bytes under an already-open reference silently.
  const fold = disclosure(encodeURIComponent(JSON.stringify([key, doc.artifact_id])), doc.artifact_ref, [
    fact(state, localize(state, "participants.m2"), doc.artifact_id), fact(state, localize(state, "participants.m3"), doc.source_action_id),
    element("pre", {className: "studio-document-text", text: doc.content}),
  ]);
  fold.classList.add("studio-document-ref");
  return fold;
}

function inputRead(state, detail, node) {
  const refs = inputRefs(node.capability, node.arguments);
  const instruction = node.arguments?.instruction_ref;
  if (typeof instruction === "string" && !refs.includes(instruction)) refs.unshift(instruction);
  if (!refs.length) return [note(localize(state, "participants.m4"))];
  return [disclosure(`inputs:${node.node_id}`, localize(state, "participants.m59", {count: String(refs.length)}), [
    note(localize(state, "participants.m5")),
    ...refs.map((ref) => {
      const doc = latestDocument(detail.records, ref);
      return doc ? documentRead(state, doc, `input:${node.node_id}:${ref}`)
        : fact(state, ref, ref === instruction ? localize(state, "participants.m6")
          : localize(state, "participants.m7"));
    }),
  ])];
}

function outputRead(state, detail, node) {
  const records = rows(detail.records);
  const sources = new Set(records.filter((row) => row.record_type === "action_request"
    && row.record?.node_id === node.node_id).map((row) => row.record.action_id));
  const docs = records.filter((row) => row.record_type === "artifact"
    && typeof row.record?.source_action_id === "string"
    && sources.has(row.record.source_action_id)).map((row) => row.record);
  if (!docs.length) return [note(localize(state, "participants.m8"))];
  return [disclosure(`outputs:${node.node_id}`, localize(state, "participants.m60", {count: String(docs.length)}), [
    note(localize(state, "participants.m9")),
    ...docs.map((doc) => {
      const result = records.find((row) => row.record_type === "action_result"
        && row.record?.action_id === doc.source_action_id)?.record;
      const read = documentRead(state, doc, `output:${node.node_id}`);
      read.querySelector(".studio-detail-pane").prepend(
        fact(state, localize(state, "participants.m10"), result?.outcome || localize(state, "participants.m11")));
      if (result?.outcome === "verification_failed") {
        read.querySelector(".studio-detail-pane").prepend(note(localize(state, "view.verification_note")));
      }
      return read;
    }),
  ])];
}

function stepStatus(state, runtime, scheduled) {
  if (runtime?.outcome) return localize(state, `scene.outcome_${runtime.outcome}`);
  return ({runnable: localize(state, "participants.m12"), blocked: localize(state, "participants.m13"), unreachable: localize(state, "participants.m14"),
    settled: localize(state, "participants.m15")})[scheduled?.state]
    || ({idle: localize(state, "participants.m16"), proposed: localize(state, "participants.m17"), requested: localize(state, "participants.m18"),
      running: localize(state, "participants.m19"), observed: localize(state, "participants.m20")})[runtime?.phase]
    || localize(state, "participants.m21");
}

function stepRead(state, detail, node, instance) {
  const runtime = rows(detail.graph?.runtime?.nodes)
    .find((row) => row.node_id === node.node_id);
  const scheduled = rows(detail.graph?.schedule?.nodes)
    .find((row) => row.node_id === node.node_id);
  const body = [element("strong", {text: attemptInFlight(detail, node.node_id)
    ? localize(state, "participants.m19") : stepStatus(state, runtime, scheduled)})];
  const technical = [fact(state, localize(state, "participants.m22"), node.node_id), fact(state, localize(state, "participants.m23"), node.kind),
    fact(state, localize(state, "participants.m24"), runtime?.phase), fact(state, localize(state, "participants.m25"), runtime?.outcome),
    fact(state, localize(state, "participants.m26"), scheduled?.state), fact(state, localize(state, "participants.m27"), node.purpose)];
  for (const [name, kind] of rows(CAPABILITY_FIELDS[node.capability])) {
    if (kind === "artifact-id") technical.push(fact(state, localize(state, "participants.m28"), node.arguments?.[name]));
  }
  if (attemptInFlight(detail, node.node_id)) {
    body.push(note(localize(state, "participants.m29")));
  }
  if (runtime?.outcome === "verification_failed") {
    body.push(note(localize(state, "view.verification_note")));
  }
  for (const [key, label] of [["blocked_by", localize(state, "participants.m30")],
    ["closed_by", localize(state, "participants.m31")], ["awaiting_artifacts", localize(state, "participants.m32")]]) {
    if (rows(scheduled?.[key]).length) {
      body.push(fact(state, label, scheduled[key].join(", ")));
    }
  }
  if (node.loop) body.push(fact(state, localize(state, "participants.m33"), localize(state, "participants.m61", {pass: show(state, runtime?.pass), bound: show(state, node.loop.bound), step: show(state, node.loop.back_to)})));
  const outgoing = rows(detail.graph?.definition?.edges)
    .filter((edge) => edge.from_node === node.node_id);
  for (const edge of outgoing) {
    // GraphEdge omits its condition for an unconditional road. That is a
    // known default, unlike a missing runtime observation or quota sample.
    const condition = Object.prototype.hasOwnProperty.call(edge, "condition")
      ? show(state, edge.condition) : "unconditional";
    technical.push(fact(state, localize(state, "participants.m34"), `${show(state, edge.to_node)} · ${condition}`));
  }
  if (node.verifier_instance_id === instance.id) body.unshift(note(
    localize(state, "participants.m62", {role: localize(state, node.instance_id === instance.id ? "participants.task_review" : "participants.review")})));
  return element("li", {className: "studio-deck__step"}, [
    element("div", {className: "studio-step-flow"}, [
      flowStage("input", localize(state, "participants.m35"), inputRead(state, detail, node)),
      flowStage("action", localize(state, "participants.m36"), body),
      flowStage("result", localize(state, "participants.m37"), outputRead(state, detail, node)),
    ]),
    ...feedbackFindings(detail, node.node_id, state),
    disclosure("parameters", localize(state, "participants.m38"), [...technical, ...parameters(state, detail, instance)]),
  ]);
}

function parameters(state, detail, instance) {
  const controls = rows(detail.controls?.instances)
    .find((row) => row.instance_id === instance.id);
  const body = [fact(state, localize(state, "participants.m39"), instance.adapter), fact(state, localize(state, "participants.m40"), instance.model),
    fact(state, localize(state, "participants.m41"), stepsOf(detail, instance.id).length)];
  if (!Object.prototype.hasOwnProperty.call(instance, "model")) {
    body.push(note(localize(state, "participants.m42")));
  }
  body.push(controls
    ? fact(state, localize(state, "participants.m43"), controls.controls.length
      ? controls.controls.join(", ") : localize(state, "participants.m44"))
    : note(localize(state, "participants.m45")));
  body.push(note(localize(state, "participants.m46")));
  return body;
}

function tasks(state, detail, instance, deck) {
  const steps = stepsOf(detail, instance.id);
  if (!steps.length) return [note(localize(state, "participants.m47")),
    disclosure("parameters", localize(state, "participants.m38"), parameters(state, detail, instance))];
  const select = element("select", {"aria-label": localize(state, "participants.m48"),
    "data-focus-key": "participant-step"}, steps.map((node) => element("option", {
      value: node.node_id, text: node.title || node.node_id})));
  select.value = steps.some((node) => node.node_id === deck.dataset.detailStep)
    ? deck.dataset.detailStep : steps[0].node_id;
  const list = element("ul", {className: "studio-deck__steps"});
  function draw() {
    deck.dataset.detailStep = select.value;
    const node = steps.find((row) => row.node_id === select.value);
    if (!node) return;
    const read = stepRead(state, detail, node, instance);
    list.replaceChildren(read);
  }
  select.addEventListener("change", draw);
  draw();
  return [select, list];
}

function history(state, detail, instance) {
  const list = element("ol", {className: "studio-deck__steps"});
  rows(detail.records).forEach((wrapper, index) => {
    const record = wrapper.record;
    if (!record || (record.instance_id !== instance.id
      && record.verifier_instance_id !== instance.id)) return;
    const item = element("li", {className: "studio-deck__step", value: index + 1}, [
      element("strong", {text: Object.hasOwn(RECORD_KINDS, wrapper.record_type) ? localize(state, `runs.record_${wrapper.record_type}`) : show(state, wrapper.record_type)}),
      fact(state, localize(state, "participants.m49"), wrapper.record_type),
    ]);
    for (const key of ["node_id", "action_id", "phase", "outcome", "verification",
      "recorded_at", "proposed_at", "completed_at"]) {
      if (record[key] !== undefined && record[key] !== null) item.append(fact(state, key, record[key]));
    }
    if (record.outcome === "verification_failed") item.append(note(localize(state, "view.verification_note")));
    list.append(item);
  });
  return [note(localize(state, "participants.m50")),
  list.children.length ? list : note(localize(state, "participants.m51"))];
}

function inspector(state, detail, instance, deck) {
  return [element("h4", {text: instance.id}),
    element("div", {className: "studio-deck__content"}, tasks(state, detail, instance, deck)),
    disclosure("history", localize(state, "participants.m52"), history(state, detail, instance))];
}

function planet(state, detail, instance, select, word = null, ids = [instance.id]) {
  const steps = stepsOf(detail, instance.id);
  const pending = steps.filter((node) =>
    attemptInFlight(detail, node.node_id)).length;
  const button = element("button", {type: "button",
    className: "studio-planet", "data-instance": instance.id,
    "data-focus-key": `participant:${instance.id}`, "aria-pressed": "false",
    "aria-controls": "studioParticipantInspector"}, [
    element("span", {className: "studio-planet__orb", "aria-hidden": "true",
      text: participantBadge(instance.id, ids)}),
    element("strong", {text: instance.id}),
    element("span", {className: "studio-note", text: instance.adapter}),
    ...(pending ? [element("span", {className: "studio-note", text:
      localize(state, "participants.m63", {count: String(pending)})})] : []),
    element("span", {className: "studio-planet__selection", text: localize(state, "participants.m53")}),
  ]);
  if (word) button.dataset.word = word;
  button.addEventListener("click", () => select(instance.id));
  return button;
}

const markGlyph = (step) => step.kind === "loop" ? "↻" : step.word === "needs_decision" ? "◇"
  : ["decision_satisfied", "settled"].includes(step.word) ? "✓"
  : ["decision_failed", "decision_changes_requested"].includes(step.word) ? "×"
  : ["decision_unknown", "attention_unconfirmed"].includes(step.word) ? "?" : "○";

// A human decision or a bounded return on the Orbit: a control that opens the
// same inspector the Trace opens for it, and never a route or an authority.
function orbitMark(step, scene, state, select) {
  const loop = scene.loops.find((row) => row.nodeId === step.nodeId);
  const word = !loop ? localize(state, `scene.${step.word}`)
    : loop.boundReached ? localize(state, "scene.bound_reached")
    : localize(state, "scene.pass", {pass: String(loop.pass ?? "—"), bound: String(loop.bound ?? "—")});
  const mark = element("button", {type: "button", className: `studio-deck__mark studio-deck__mark--${step.kind}`,
    "data-orbit-step": step.nodeId, "data-orbit-kind": step.kind, "data-word": step.word,
    "data-focus-key": `orbit-step:${step.nodeId}`, "aria-pressed": "false",
    "aria-controls": "studioParticipantInspector", title: step.title, "aria-label": `${step.title} · ${word}`}, [
    element("span", {className: "studio-deck__mark-point", "aria-hidden": "true", text: markGlyph(step)}),
    // The core is one short row: the return's title is its tooltip and accessible name.
    ...(loop ? [] : [element("strong", {text: step.title})]),
    element("span", {className: "studio-note", text: word})]);
  mark.hidden = true;
  mark.addEventListener("click", () => select(step.ownerId, step.nodeId));
  return mark;
}

// The core says where the run stands; it is not a control.
function orbitCore(scene, state) {
  const current = scene.steps.find((step) => step.nodeId === scene.positions[0]);
  const core = element("div", {className: "studio-deck__core", "data-orbit-kind": "core",
    text: scene.ending.ended ? localize(state, "scene.run_ended")
      : current ? `${current.title} · ${localize(state, `scene.${current.word}`)}` : localize(state, "scene.team")});
  core.hidden = true;
  return core;
}

function sceneInspector(detail, step, scene, state, handlers) {
  if (step.kind === "gate") {
    const gate = step.gate;
    const button = element("button", {type: "button", text: localize(state, "scene.open_decisions"),
      "data-focus-key": `scene-decision:${step.nodeId}`});
    button.addEventListener("click", () => handlers?.showDecisions?.(detail.run.run_id));
    button.disabled = typeof handlers?.showDecisions !== "function";
    const standing = rows(detail.records).find((row) => row.record_type === "decision"
      && row.record?.receipt_id === gate?.standing_receipt)?.record;
    return [element("h4", {text: step.title}), note(localize(state, "scene.gate")),
      note(localize(state, `scene.${step.word}`)), note(step.node.purpose || ""),
      ...(gate?.standing_belongs_to_current_lap === false
        ? [note(localize(state, "scene.previous_answer"))] : []),
      ...(standing ? [note(standing.reason)] : []), button];
  }
  const loop = scene.loops.find((row) => row.nodeId === step.nodeId);
  return [element("h4", {text: step.title}), note(localize(state, "scene.loop")),
    note(localize(state, "scene.pass", {pass: String(loop?.pass ?? "—"), bound: String(loop?.bound ?? "—")})),
    note(localize(state, "scene.back_to", {step: loop?.backTo || "—"})),
    ...(loop?.boundReached ? [note(localize(state, "scene.bound_reached"))] : []),
    ...(loop?.reason?.kind === "decision" ? [note(loop.reason.text), note(localize(state,
      "scene.evidence_count", {count: String(loop.reason.evidenceCount)}))] : []),
    ...(loop?.reason?.kind === "outcome" ? [note(localize(state, `scene.outcome_${loop.reason.outcome}`))] : [])];
}

function deckSelection(detail, bound, scene, deck, fleet, panel, state, handlers) {
  let trace = null;
  function select(id, requested = null) {
    const instance = bound.find((row) => row.id === id);
    const special = scene?.steps.find((row) => row.nodeId === requested && row.kind !== "task");
    if (!instance && !special) return;
    const before = deck.dataset.selectedInstance;
    const kept = [...panel.querySelectorAll("[data-detail-fold][open]")].map((el) => el.dataset.detailFold);
    const own = instance ? stepsOf(detail, id) : [];
    const active = own.find((node) => scene?.positions.includes(node.node_id));
    const retained = deck.dataset.selectedInstance === id ? deck.dataset.detailStep : "";
    deck.dataset.detailStep = requested || retained || active?.node_id || own[0]?.node_id || "";
    deck.dataset.selectedInstance = instance?.id || "";
    for (const button of fleet.querySelectorAll("[data-instance]")) {
      const chosen = button.dataset.instance === deck.dataset.selectedInstance;
      button.setAttribute("aria-pressed", String(chosen));
      button.querySelector(".studio-planet__selection").textContent = localize(state,
        chosen ? "scene.selected" : "scene.select");
    }
    for (const button of deck.querySelectorAll("[data-team-instance]"))
      button.setAttribute("aria-pressed", String(button.dataset.teamInstance === deck.dataset.selectedInstance));
    for (const mark of fleet.querySelectorAll("[data-orbit-step]"))
      mark.setAttribute("aria-pressed", String(!instance && mark.dataset.orbitStep === deck.dataset.detailStep));
    panel.replaceChildren(...(special ? sceneInspector(detail, special, scene, state, handlers)
      : inspector(state, detail, instance, deck)));
    if (instance && instance.id === before) { // the same participant again: what a person opened stays open
      for (const fold of panel.querySelectorAll("[data-detail-fold]")) fold.open = kept.includes(fold.dataset.detailFold);
    }
    trace?.select(deck.dataset.selectedInstance, deck.dataset.detailStep);
    panel.scrollTop = 0;
  }
  panel.addEventListener("change", () => trace?.select(deck.dataset.selectedInstance, deck.dataset.detailStep));
  return {select, attach: (view) => { trace = view; }};
}

function lenses(deck, fleet, trace, state) {
  const bar = element("div", {className: "studio-lenses", role: "group",
    "aria-label": localize(state, "scene.lenses")});
  function show(state, mode, recenter) {
    deck.dataset.deckLens = mode; fleet.hidden = mode !== "orbit"; trace.root.hidden = mode !== "trassa";
    for (const button of bar.children) button.setAttribute("aria-pressed", String(button.dataset.runLens === mode));
    if (mode === "trassa") trace.show(recenter); // show(recenter): a redraw of the same run keeps its scroll
  }
  for (const [mode, key] of [["trassa", "scene.trace"], ["orbit", "scene.orbit"]]) {
    const button = element("button", {type: "button", className: "studio-lens",
      "data-run-lens": mode, "data-focus-key": `run-lens:${mode}`, text: localize(state, key)});
    button.addEventListener("click", () => show(state, mode, true)); bar.append(button);
  }
  show(state, deck.dataset.deckLens || "trassa", false);
  return bar;
}

function deckAbout(detail, bound, state) {
  return element("details", {className: "studio-deck__about"}, [
    element("summary", {text: localize(state, "participants.m54"), "data-focus-key": "participant-about"}),
    note(localize(state, "scene.scroll_team", {count: String(bound.length)})),
    note(localize(state, "participants.m55")),
    note(localize(state, "participants.m56")),
    ...routesOf(state, detail, bound).map((route) => note(
      `${route.from} → ${route.to}: ${[...route.labels].join(", ")}`)),
    note(localize(state, "scene.legend")),
  ]);
}

function teamRoster(bound, state, choose, ids) {
  const group = element("nav", {className: "studio-team-roster", "aria-label": localize(state, "scene.team")});
  for (const instance of bound) {
    // The same letters the planets carry; the whole id is in the name a reader hears.
    const badge = participantBadge(instance.id, ids);
    const button = element("button", {type: "button", text: badge, "aria-label": `${badge} · ${instance.id}`,
      "data-team-instance": instance.id, "data-focus-key": `team:${instance.id}`,
      "aria-pressed": "false", title: `${instance.id} · ${instance.adapter} · ${instance.model || "—"}`});
    button.addEventListener("click", () => choose(instance.id)); group.append(button);
  }
  return group;
}

function drawDeck(detail, bound, scene, deck, previous, state, handlers) {
  const fleet = element("div", {className: "studio-deck__fleet", "data-count": String(bound.length),
    role: "group", "aria-label": localize(state, "participants.m57")});
  const panel = element("section", {className: "studio-deck__inspector",
    id: "studioParticipantInspector", "aria-label": localize(state, "participants.m58")});
  const selection = deckSelection(detail, bound, scene, deck, fleet, panel, state, handlers);
  const words = new Map((scene?.participants || []).map((row) => [row.instanceId, row.word]));
  const ids = bound.map((row) => row.id);
  for (const instance of bound) {
    fleet.append(planet(state, detail, instance, selection.select, words.get(instance.id), ids));
  }
  if (scene) {
    fleet.dataset.kind = "ring"; // one fixed box: the Orbit places everything inside it
    for (const step of scene.steps.filter((row) => row.kind !== "task")) {
      fleet.append(orbitMark(step, scene, state, selection.select));
    }
    fleet.append(orbitCore(scene, state));
  }
  const stage = element("div", {className: "studio-deck__scene"}, [fleet]);
  const head = element("div", {className: "studio-deck__head"}); // lenses, note, roster: above BOTH columns
  let trace = null;
  if (scene) {
    trace = traceView(scene, state, selection.select, previous ? previous.traceScroll : null);
    selection.attach(trace); stage.prepend(trace.root);
    head.append(lenses(deck, fleet, trace, state),
      teamRoster(bound, state, (id) => { selection.select(id); trace.reveal(id); }, ids));
  } else head.append(note(localize(state, "scene.no_plan")));
  if (scene?.steps.some((step) => step.outcome === "verification_failed")) stage.append(note(localize(state, "view.verification_note")));
  deck.append(head, element("div", {className: "studio-deck__body"}, [stage, panel]), deckAbout(detail, bound, state));
  deck.dataset.selectedInstance = previous?.instance || "";
  deck.dataset.detailStep = previous?.step || "";
  const active = scene?.steps.find((step) => scene.positions.includes(step.nodeId) && step.ownerId);
  selection.select(previous?.instance || active?.ownerId || bound[0].id, previous?.step || null);
  if (previous) for (const fold of deck.querySelectorAll("[data-detail-fold]")) {
    fold.open = rows(previous.open).includes(fold.dataset.detailFold);
  }
  deck.querySelector(".studio-deck__about").open = previous?.about || false;
  const observer = routeDiagram(fleet, routesOf(state, detail, bound), scene ? {scene, state} : null);
  observers.set(deck, {disconnect: () => { observer.disconnect(); trace?.dispose(); }});
}

export function participantDeck(detail, previous, state = {}, handlers = {}) {
  const bound = rows(detail.config?.instances), run = detail.run?.run_id;
  const deck = element("section", {className: "studio-section studio-deck",
    "data-deck-run": run}, [element("h3", {text: localize(state, "scene.team")})]);
  if (!bound.length) {
    deck.append(note(localize(state, "scene.no_instances"))); return deck;
  }
  const retained = previous?.run === run ? previous : null;
  deck.dataset.deckLens = retained?.lens || "trassa";
  let scene = sceneOf(detail);
  if (scene && state.connection === "closed") scene = {...scene,
    positions: [], steps: scene.steps.map((step) => step.word === "needs_decision"
      ? {...step, word: "attention_unconfirmed"} : step)};
  drawDeck(detail, bound, scene, deck, retained, state, handlers);
  return deck;
}
