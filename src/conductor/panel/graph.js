"use strict";
// Bootstrap for the ALPHA-2 Graph window: one store, one render pass, one
// fixture seam. There is deliberately no fetch anywhere in this file — the
// wire contracts belong to the runtime side and have not been handed over, so
// the only way facts enter this window is `window.conductGraph.load`, the same
// door the coming HTTP source will use. The visual layer cannot tell which
// source fed it; that is what keeps it stable when the real API arrives.
import {EMPTY, projectPayload, reduce} from "./graph-store.js";
import {renderComposer, renderDetail, renderGates, renderGraph, renderPalette,
  renderTimeline} from "./graph-view.js";

(() => {
  const field = document.getElementById("field");
  if (!field) return;
  const mounts = {
    composer: document.getElementById("composerCard"),
    detail: document.getElementById("detailCard"),
    edges: document.getElementById("edges"),
    empty: document.getElementById("fieldEmpty"),
    gates: document.getElementById("gatesCard"),
    notice: document.getElementById("notice"),
    palette: document.getElementById("paletteCard"),
    runFacts: document.getElementById("runFacts"),
    timeline: document.getElementById("timelineCard"),
  };
  let state = EMPTY;
  function dispatch(event) {
    const next = reduce(state, event);
    if (next === state) return;
    state = next;
    render();
  }
  const onSelect = (nodeId) => dispatch({type: "select", nodeId});
  const onDecide = (facts) => dispatch({type: "decide", ...facts});
  // The composer mints the next free step id itself: ids are presentation-side
  // here (a fixture is the only store), and a Human never has to invent one.
  function onCompose(facts) {
    let serial = state.nodes.length + 1;
    while (state.nodes.some((node) => node.node_id === `step-${serial}`)) {
      serial += 1;
    }
    dispatch({type: "compose", nodeId: `step-${serial}`, ...facts});
  }
  function render() {
    document.body.dataset.phase = state.phase;
    mounts.notice.textContent = state.notice;
    mounts.runFacts.textContent = state.phase === "loaded"
      ? `run: ${state.run.runId} · mode: ${state.run.mode} · fixture` : "";
    mounts.empty.hidden = state.phase === "loaded";
    renderGraph(field, mounts.edges, state, onSelect);
    renderPalette(mounts.palette, state);
    renderComposer(mounts.composer, state, onCompose);
    renderDetail(mounts.detail, state, onDecide);
    renderGates(mounts.gates, state);
    renderTimeline(mounts.timeline, state);
  }
  // The fixture seam. `load` validates at the boundary and refuses rather than
  // repairs; `state` answers with the current frozen value so a test can read
  // without reaching into module internals.
  window.conductGraph = Object.freeze({
    dispatch,
    load(payload) {
      const facts = projectPayload(payload);
      dispatch(facts ? {type: "loaded", facts} : {type: "refused"});
      return facts !== null;
    },
    state: () => state,
  });
  render();
})();
