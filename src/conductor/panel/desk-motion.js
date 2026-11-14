"use strict";
// The desk's transitions (spec 5.5, D11): a task accepted, a task that now waits for the person,
// a task finished, and a new task entering the list. Movement is rare, one-shot and optional.
//
// This module draws; what is a moment is decided by `desk-motion-model.js` over the view of
// each render. It is handed the view by the scene's mount and reads the page's own anchors:
// the rail rows, and in the scene the participants, the gates and the steps the deck drew. It
// writes nothing to any door and reads no door.
//
// What it plays is a layer of its own, `#deskMotion`, a child of the body: the regions are
// redrawn with `replaceChildren` on every render, and a layer inside one of them would be torn
// down with it. Every movement is a Web Animation on a mark of that layer, played once, for no
// longer than 1.2 s (the table in the model), and the mark leaves when it ends.
//
// Reduced motion (`prefers-reduced-motion: reduce`): nothing is drawn and nothing is played. The
// plaque stays: one line, "<task> · <its word>", in the rail's own words, for a few seconds.
// The preference is read at the moment of each play and never kept.
//
// Nothing is played again after a reconnect or a reload: that is the detector's rule (the
// first reading of a life of the stream is a baseline), and this module has no memory of its own
// about what it played. A moment waits until the scene has settled (its run read has landed and
// the page has drawn two frames), so the marks find the anchors where they will stay.
//
// Nothing is drawn where the person cannot see it, and nothing seen then is played later. While the
// tab is hidden (`document.hidden`) a render makes no wait at all -- a hidden page is given no
// frames, so a wait made then would stand until the tab returned -- and clears the layer and what
// waited. While the new-task wizard stands over the desk (its shell, `#deskWizard`, is shown) every
// render, once it has finished drawing, does the same. A tab that leaves or comes back to the
// screen clears the layer too. The detector keeps reading all the while, so the next change after
// the return or the wizard's close is compared with what stood then.
//
// A page can also be given no frames while its tab is NOT hidden: the desk in the hub's frame,
// scrolled out of sight, has `document.hidden` false and gets no `visibilitychange`. So at most ONE
// wait for frames stands at a time. The renders that come while it stands only replace the view it
// will plan over (the last one that has settled); when its frames come it plans once over that
// view, if no later render, hide or wizard has voided it, and a render that settled during the wait
// gets two frames of its own first. What is held is one view, however many renders there were.
import {element} from "./command-view.js";
import {TIMINGS, createDetector, isLive, planOf} from "./desk-motion-model.js";

//: The one query that decides whether anything may move.
const REDUCE = "(prefers-reduced-motion: reduce)";
//: How long the plaque stays. It is words and not movement: the cap of 1.2 s is for movement.
const PLAQUE_MS = 6000;
const LAYER = "deskMotion";
//: The shell of the new-task wizard, drawn over the whole desk while the wizard is open.
const WIZARD = "deskWizard";
const ION = "var(--ion)";
const AMBER = "var(--amber)";
const CENTRED = "translate(-50%, -50%)";
const SPARKS = 8;
const NONE = Object.freeze([]);
//: The anchors of the page. A rail row carries its task id; in the scene the deck draws two
//: lenses (the Trace and the Orbit) and only one is on the screen at a time, so each anchor
//: has both spellings and the one on the screen is the one found.
const RAIL_ROWS = "#deskRail [data-task-id]";
const PARTICIPANTS = "[data-trassa-instance], [data-instance]";
const GATES = "[data-trassa-gate], [data-orbit-kind='gate']";
const STEPS = "[data-trassa-step], [data-orbit-step]";
//: The drawn part of an anchor: the orb of a participant, the point of a step or a mark.
const HEART = ".studio-planet__orb, .studio-trace__point, .studio-deck__mark-point";
//: The counter of what waits for the person, when the desk draws one (the console, D1).
const COUNTER = "[data-attention-count]";
//: The sizes of the marks, in pixels.
const DOT = Object.freeze({width: 10, height: 10});
const SPECK = Object.freeze({width: 6, height: 6});
const RING = Object.freeze({width: 64, height: 64});
const WAVE = Object.freeze({width: 72, height: 72});

const detector = createDetector();
//: Moments seen and not yet played, and the number of the latest render: a wait is void when
//: another render, a hide or the wizard has moved it since the view the wait plans over was made.
let pending = NONE;
let latest = 0;
//: Whether a wait for the scene's frames stands. At most one does, so a page that is given no
//: frames (and is not hidden) is left one wait, however many renders it is handed.
let waiting = false;
//: The view the wait that stands will plan over: the last render that settled and had moments to
//: play, with its number in `latest`. One at a time; nothing once planned or voided.
let held = null;

//: Whether the person allows movement: the negation of the one media query.
function motionAllowed() {
  return !window.matchMedia(REDUCE).matches;
}

//: The one clock of this module: how long the plaque stays on the glass.
function later(call, ms) {
  return setTimeout(call, ms);
}

//: The one place a movement is played. It asks the preference again, at this moment, and
//: plays one mark once; the mark leaves the layer when the movement ends or is cancelled.
function play(node, frames, timing) {
  if (!motionAllowed()) return Promise.resolve(false);
  return node.animate(frames, {duration: timing.duration, delay: timing.delay,
    easing: "ease-out", fill: "forwards"}).finished.then(() => true, () => false)
    .then((done) => { node.remove(); return done; });
}

//: The layer, made when first wanted. It lets every press through and says its plaque to a
//: screen reader as a polite announcement; the marks are hidden from one.
function layer() {
  const found = document.getElementById(LAYER);
  if (found !== null) return found;
  const made = element("div", {id: LAYER, "aria-live": "polite"});
  Object.assign(made.style, {position: "fixed", inset: "0", zIndex: "50", overflow: "hidden",
    pointerEvents: "none"});
  document.body.append(made);
  return made;
}

const shown = (node) => node.getClientRects().length > 0;

//: Where an anchor stands: the middle of its drawn part, in window coordinates.
function centreOf(node) {
  const box = (node.querySelector(HEART) ?? node).getBoundingClientRect();
  return Object.freeze({x: box.left + box.width / 2, y: box.top + box.height / 2});
}

//: The anchors of the scene as it stands drawn, or null when it is not on the screen (a panel
//: covers it). `origin` is the first participant when it is not the one at work, `worker` the one
//: whose result is awaited (else the last), `gate` the gate that waits for a decision (else the
//: first), `end` the last step of the plan, and `middle` the scene itself.
function stageOf() {
  const scene = document.getElementById("deskScene");
  if (scene === null || !shown(scene)) return null;
  const within = (selector) => [...scene.querySelectorAll(selector)].filter(shown);
  const people = within(PARTICIPANTS), gates = within(GATES), steps = within(STEPS);
  const worker = people.find((node) => node.dataset.word === "awaiting_result") ?? people.at(-1);
  const waits = gates.find((node) => node.dataset.word === "needs_decision") ?? gates[0];
  const end = steps.map(centreOf).sort((left, right) => right.x - left.x)[0];
  const middle = scene.getBoundingClientRect();
  return Object.freeze({
    origin: worker !== undefined && people[0] !== worker ? centreOf(people[0]) : null,
    worker: worker === undefined ? null : centreOf(worker),
    gate: waits === undefined ? null : centreOf(waits),
    end: end ?? null,
    middle: Object.freeze({x: middle.left + middle.width / 2, y: middle.top + middle.height / 2}),
  });
}

//: One mark of the layer, standing where it is told and invisible until its movement plays.
function lay(kind, at, size, look) {
  const node = element("div", {"data-fx": kind, "aria-hidden": "true"});
  Object.assign(node.style, {position: "absolute", left: `${at.x}px`, top: `${at.y}px`,
    width: `${size.width}px`, height: `${size.height}px`, opacity: "0", ...look});
  layer().append(node);
  return node;
}

const glow = (color) => ({background: color, borderRadius: "50%", boxShadow: `0 0 14px ${color}`});
const outline = (color) => ({border: `2px solid ${color}`, borderRadius: "50%",
  boxSizing: "border-box"});

//: A mark that goes from one point to another and fades where it lands.
function flight(from, to) {
  const at = (point) => `translate(${point.x - from.x}px, ${point.y - from.y}px) ${CENTRED}`;
  return [{opacity: 1, transform: at(from)}, {opacity: 1, transform: at(to), offset: 0.8},
    {opacity: 0, transform: at(to)}];
}

//: A mark that swells from one size to another while it fades.
function swell(from, to) {
  return [{opacity: 0.9, transform: `${CENTRED} scale(${from})`},
    {opacity: 0, transform: `${CENTRED} scale(${to})`}];
}

//: «принята»: a comet from the first participant to the one at work, rings where it goes.
function accepted(stage) {
  const target = stage.worker ?? stage.middle;
  if (stage.origin !== null) {
    play(lay("comet", stage.origin, DOT, glow(ION)), flight(stage.origin, target), TIMINGS.comet);
  }
  play(lay("ring", target, RING, outline(ION)), swell(0.3, 1.8), TIMINGS.ring);
  play(lay("ring", target, RING, outline(ION)), swell(0.3, 1.8), TIMINGS.ring_late);
}

//: A wave on the counter of what waits for the person, when the desk draws one.
function tally() {
  const counter = document.querySelector(COUNTER);
  if (counter === null || !shown(counter)) return;
  play(lay("ring", centreOf(counter), RING, outline(AMBER)), swell(0.3, 1.8), TIMINGS.count);
}

//: «к вам»: a comet to the gate that waits, two amber waves over it, a wave on the counter.
function toYou(stage) {
  const target = stage.gate ?? stage.middle;
  if (stage.gate !== null && stage.worker !== null) {
    play(lay("comet", stage.worker, DOT, glow(AMBER)), flight(stage.worker, target),
      TIMINGS.comet);
  }
  play(lay("ring", target, WAVE, outline(AMBER)), swell(0.2, 2.2), TIMINGS.wave);
  play(lay("ring", target, WAVE, outline(AMBER)), swell(0.2, 2.2), TIMINGS.wave_late);
  tally();
}

//: «завершена»: rings and sparks where the plan ends.
function finished(stage) {
  const at = stage.end ?? stage.middle;
  play(lay("ring", at, RING, outline(ION)), swell(0.3, 1.8), TIMINGS.ring);
  play(lay("ring", at, RING, outline(ION)), swell(0.3, 1.8), TIMINGS.ring_late);
  for (let index = 0; index < SPARKS; index += 1) {
    const turn = (2 * Math.PI * index) / SPARKS;
    const out = {x: at.x + 38 * Math.cos(turn), y: at.y + 38 * Math.sin(turn)};
    play(lay("spark", at, SPECK, glow(ION)), flight(at, out), TIMINGS.spark);
  }
}

const SCENE_MOMENTS = Object.freeze({accepted, to_you: toYou, finished});

//: The rail row of a task, found by comparing ids and never by building a selector from one.
function railRow(taskId) {
  return [...document.querySelectorAll(RAIL_ROWS)]
    .find((node) => node.dataset.taskId === taskId) ?? null;
}

//: A halo round the row of a task that has entered the list.
function halo(taskId) {
  const row = railRow(taskId);
  if (row === null) return;
  const box = row.getBoundingClientRect();
  const at = {x: box.left + box.width / 2, y: box.top + box.height / 2};
  const size = {width: box.width + 12, height: box.height + 12};
  play(lay("halo", at, size, {...outline(ION), borderRadius: "10px"}), swell(0.94, 1.1),
    TIMINGS.halo);
}

//: The plaque: "<task> · <its word>", the words the rail row says, so a person who prefers no
//: movement still reads the moment. One plaque at a time; the newest replaces the last.
function plaque(taskId) {
  const row = railRow(taskId);
  const title = row?.querySelector(".desk-task__title")?.textContent;
  const state = row?.querySelector(".desk-task__state")?.textContent;
  if (!title || !state) return;
  const note = element("p", {"data-fx": "plaque", text: `${title} · ${state}`});
  Object.assign(note.style, {position: "absolute", left: "50%", bottom: "24px",
    transform: "translateX(-50%)", margin: "0", padding: "8px 14px", maxWidth: "min(90vw, 560px)",
    border: "1px solid var(--line-strong)", borderRadius: "8px", background: "var(--panel)",
    color: "var(--ink)", font: "600 13px var(--sans)"});
  layer().querySelector("[data-fx='plaque']")?.remove();
  layer().append(note);
  later(() => note.remove(), PLAQUE_MS);
}

//: Play what one render's moments decided: the plaque always, the marks only when movement is
//: allowed and the thing they land on is on the screen.
function show(plan) {
  if (plan.plaque !== null) plaque(plan.plaque.taskId);
  if (!motionAllowed()) return;
  const stage = plan.scene === null ? null : stageOf();
  if (stage !== null) SCENE_MOMENTS[plan.scene.kind](stage);
  for (const taskId of plan.entered) halo(taskId);
}

//: The scene reads a run again (what it draws is about to be replaced), or the lists a moment is
//: checked against are out.
const unsettled = (view) => view.run.phase === "loading" || view.run.phase === "stale"
  || view.tasks.phase !== "ready" || view.runs.phase !== "ready";

//: Whether the wizard's shell stands over the desk. Read off the page at the moment of asking;
//: nothing is kept.
function covered() {
  const shell = document.getElementById(WIZARD);
  return shell !== null && !shell.hidden;
}

//: Take everything off the glass and forget what waits: the marks and the plaque leave the layer,
//: a wait for the scene is made void, and no moment seen so far is played later.
function hush() {
  latest += 1;
  pending = NONE;
  document.getElementById(LAYER)?.replaceChildren();
}

//: Two animation frames: what the page was asked to draw has been drawn, and the deck's own
//: layout (it measures after it is mounted) has been applied.
function drawn() {
  return new Promise((done) => window.requestAnimationFrame(() =>
    window.requestAnimationFrame(done)));
}

//: The one place a wait for frames is made, and only while none stands. When its frames come it
//: plans over the last view that settled: not at all when a render that did not settle, a hide or
//: the wizard has come since (the render counter has moved), and not yet when a render that settled
//: came during the wait, which has had fewer than two frames: that one is waited for again.
function settle() {
  waiting = true;
  const asked = held;
  drawn().then(() => {
    waiting = false;
    const {view, at} = held;
    if (at !== latest) {
      held = null;
      return;
    }
    if (held !== asked) {
      settle();
      return;
    }
    held = null;
    const plan = planOf(pending, view);
    pending = NONE;
    show(plan);
  });
}

//: Hand the module the view of a render. It watches for a moment and, when one is due and the
//: scene has settled, plays it after the render has finished drawing, over the last view that
//: settled while it waited; a render that has not settled voids the wait. It never holds a render
//: up.
export function watchMotion(view) {
  layer();
  latest += 1;
  const found = detector.observe(view);
  if (document.hidden) {
    hush();
    return;
  }
  pending = isLive(view) ? [...pending, ...found] : NONE;
  // The wizard is drawn after the scene in the same render: whether it covers the desk is asked
  // once the render has finished.
  Promise.resolve().then(() => { if (covered()) hush(); });
  if (pending.length === 0 || unsettled(view)) return;
  held = Object.freeze({view, at: latest});
  if (!waiting) settle();
}

//: A tab that leaves the screen, or comes back to it, starts from what stands: nothing waiting is
//: played on return, and the next change is compared with the reading the detector last took.
document.addEventListener("visibilitychange", hush);
