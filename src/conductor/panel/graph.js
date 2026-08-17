"use strict";
// Bootstrap for the ALPHA-2 Graph window: one store, one render pass, one
// fixture seam. There is deliberately no fetch anywhere in this file — the
// wire contracts belong to the runtime side and have not been handed over, so
// the only way facts enter this window is `conductGraph.load`, the same door
// the coming HTTP source will use. The visual layer cannot tell which source
// fed it; that is what keeps it stable when the real API arrives.
import {EMPTY, projectPayload, reduce} from "./graph-store.js";
import {renderComposer, renderDetail, renderGates, renderGraph, renderPalette,
  renderTimeline} from "./graph-view.js";

(() => {
  const field = document.getElementById("field");
  if (!field) return;
  const mounts = {
    composer: document.getElementById("composerCard"),
    composeStatus: document.getElementById("composeStatus"),
    decideStatus: document.getElementById("decideStatus"),
    detailBody: document.getElementById("detailBody"),
    edges: document.getElementById("edges"),
    empty: document.getElementById("fieldEmpty"),
    gates: document.getElementById("gatesCard"),
    notice: document.getElementById("notice"),
    palette: document.getElementById("paletteCard"),
    runFacts: document.getElementById("runFacts"),
    timeline: document.getElementById("timelineCard"),
  };
  let state = EMPTY;
  // What the Human has typed but not landed. A refused decision or a
  // selection made while composing must not erase it (command.js keeps the
  // same promise with its draft object); a successful landing clears it.
  const composeDraft = {title: "", harness: "", placement: "after", anchor: ""};
  const decisionDraft = {action: "approve", actor: "", reason: ""};
  // dispatch stays module-internal: the public seam is load/state only, so
  // no caller can commit facts that skipped the projectPayload boundary.
  function dispatch(event) {
    const next = reduce(state, event);
    if (next === state) return;
    state = next;
    render();
  }
  const onSelect = (nodeId) => dispatch({type: "select", nodeId});
  function onDecide(facts) {
    const before = state.decisions[facts.gateId];
    dispatch({type: "decide", ...facts});
    if (state.decisions[facts.gateId] !== before) {
      decisionDraft.action = "approve";
      decisionDraft.actor = "";
      decisionDraft.reason = "";
      render();
    }
  }
  // The composer mints the next free step id itself: ids are presentation-side
  // here (a fixture is the only store), and a Human never has to invent one.
  function onCompose(facts) {
    let serial = state.nodes.length + 1;
    while (state.nodes.some((node) => node.node_id === `step-${serial}`)) {
      serial += 1;
    }
    const before = state.nodes.length;
    dispatch({type: "compose", nodeId: `step-${serial}`, ...facts});
    if (state.nodes.length > before) {
      composeDraft.title = "";
      render();
    }
  }
  // A render pass replaces the focused control, so focus intent is captured
  // before the pass and restored to the control's successor after it — a
  // keyboard Human is never dropped to the top of the document by their own
  // selection, decision or composition.
  function focusTarget() {
    const active = document.activeElement;
    if (!active || active === document.body) return null;
    if (active.dataset && active.dataset.nodeId) {
      return {node: active.dataset.nodeId};
    }
    const name = active.getAttribute ? active.getAttribute("name") : "";
    if (name && mounts.detailBody.contains(active)) return {detail: name};
    if (name && mounts.composer.contains(active)) return {compose: name};
    return null;
  }
  function restoreFocus(target) {
    if (!target) return;
    const successor = target.node
      ? field.querySelector(`[data-node-id="${target.node}"]`)
      : (target.detail ? mounts.detailBody : mounts.composer)
          .querySelector(`[name="${target.detail || target.compose}"]`);
    if (successor) successor.focus();
  }
  function render() {
    const target = focusTarget();
    document.body.dataset.phase = state.phase;
    mounts.notice.textContent = state.notice;
    mounts.composeStatus.textContent = state.composeNotice;
    mounts.decideStatus.textContent = state.decisionNotice;
    mounts.runFacts.textContent = state.phase === "loaded"
      ? `run: ${state.run.runId} · mode: ${state.run.mode} · fixture` : "";
    mounts.empty.hidden = state.phase === "loaded";
    renderGraph(field, mounts.edges, state, onSelect);
    renderPalette(mounts.palette, state);
    renderComposer(mounts.composer, state, composeDraft, onCompose);
    renderDetail(mounts.detailBody, state, decisionDraft, onDecide);
    renderGates(mounts.gates, state);
    renderTimeline(mounts.timeline, state);
    restoreFocus(target);
  }
  // The fixture seam, and the whole of it: load validates at the boundary and
  // refuses rather than repairs; state answers with the current frozen value
  // so a test can read without reaching into module internals.
  window.conductGraph = Object.freeze({
    load(payload) {
      const facts = projectPayload(payload);
      dispatch(facts ? {type: "loaded", facts} : {type: "refused"});
      return facts !== null;
    },
    state: () => state,
  });
  render();
})();
