"use strict";
// Bootstrap and transport for the Graph window: one store, one render pass,
// one payload seam, and one door to the wire.
//
// The wire arrived, and it arrived with a shape. Facts enter this window
// through `conductGraph.load` — a fixture, as before — or through the
// authoritative run read, which is the ONLY door durable facts come through.
// A run-event on the stream carries a run id and nothing else: it never
// carries a record, so it can never be a fact here. It buys exactly one
// thing, a re-read, and everything on screen after it came from that read.
//
// Writing is one button pressed by a Human. Nothing else in this file can
// reach the mutation door: not a load, not a signal, not a reconnect, not a
// successful write. The plan a run follows is immutable — written once, never
// edited — so it may only ever be written on purpose.
import {ERROR_LABELS, RUN_ID, refusalCode} from "./command-projection.js";
import {GRAPH_ABSENT, GRAPH_LOADED, adaptPayload, adaptRunGraph,
  graphRequestBody} from "./graph-adapter.js";
import {DALIO_DEFAULT} from "./graph-default.js";
import {projectPayload} from "./graph-payload.js";
import {EMPTY, reduce} from "./graph-store.js";
import {renderComposer, renderDetail, renderGates, renderGraph, renderPalette,
  renderSave, renderSource, renderTimeline} from "./graph-view.js";

const UNKNOWN = "Outcome unknown. Reload the authoritative run.";
const CREATED = "The plan is written. This run follows it and can never edit "
  + "it: a graph is immutable once it reaches the journal.";
const RESTATED = "This exact plan already stands. Nothing was appended and "
  + "nothing was published — this is the record the first write settled.";
const ABSENT = "This run follows no graph yet. Nothing has been written to it.";
const CORRUPT = "The run's graph could not be read as one plan and one "
  + "position. Nothing about it is inferred from a document this window "
  + "cannot read.";
const DRAFT_REFUSED = "The drawing was refused before it was offered to the "
  + "run: a plan may carry no observed fact, and this one does.";
const STREAM_DOWN = "Connection lost. The last authoritative facts are still "
  + "on screen, and nothing may be written until the stream is back and this "
  + "run has been read again.";

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
    runForm: document.getElementById("runForm"),
    runInput: document.getElementById("graphRunId"),
    save: document.getElementById("saveCard"),
    saveStatus: document.getElementById("saveStatus"),
    seed: document.getElementById("seedDefault"),
    source: document.getElementById("sourceLine"),
    timeline: document.getElementById("timelineCard"),
  };
  let state = EMPTY;
  // What the Human has typed but not landed. A refused decision or a
  // selection made while composing must not erase it (command.js keeps the
  // same promise with its draft object); a successful landing clears it.
  const composeDraft = {title: "", harness: "", placement: "after", anchor: ""};
  const decisionDraft = {action: "approve", actor: "", reason: ""};
  const saveDraft = {graphId: ""};
  // Which run this window is reading. Held outside the graph state because a
  // run that answers with no graph, or with one this window cannot read,
  // still has an id worth naming on screen.
  let selectedRun = "";
  let registryRows = null;
  let epoch = 0, csrfToken = "", sessionEpoch = 0;
  let refreshDirty = false, refreshInFlight = false;
  // Whether the run-event stream is carrying right now. Transport's own fact,
  // held here; what the SCREEN may do about it is `state.writeReady`, which
  // an authoritative read grants and a drop takes away.
  let streamOpen = false;
  // Which write is the current one. A drop retires the write in flight along
  // with the session that authorized it, so a late answer cannot land.
  let writeGeneration = 0;
  // A save outcome waiting for the authoritative read that will make it true.
  // It rides THROUGH the re-read rather than being announced before it: the
  // answer belongs to the Human who asked, and the read is what confirms it.
  let pendingCarry = null;
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
    const before = Object.hasOwn(state.decisions, facts.gateId)
      ? state.decisions[facts.gateId] : undefined;
    dispatch({type: "decide", ...facts});
    if (state.decisions[facts.gateId] !== before) {
      decisionDraft.action = "approve";
      decisionDraft.actor = "";
      decisionDraft.reason = "";
      render();
    }
  }
  // The composer mints the next free step id itself: a Human never has to
  // invent one, and a durable plan's own ids are never reused.
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
    if (name && mounts.save.contains(active)) return {save: name};
    return null;
  }
  function focusMount(target) {
    if (target.detail) return mounts.detailBody;
    return target.save ? mounts.save : mounts.composer;
  }
  function restoreFocus(target) {
    if (!target) return;
    const successor = target.node
      ? field.querySelector(`[data-node-id="${target.node}"]`)
      : focusMount(target).querySelector(
        `[name="${target.detail || target.compose || target.save}"]`);
    if (successor) successor.focus();
  }
  function runFactsText() {
    if (!selectedRun) {
      return state.phase === "loaded"
        ? `run: ${state.run.runId} · mode: ${state.run.mode} · fixture` : "";
    }
    const mode = state.phase === "loaded" ? state.run.mode : "unknown";
    return `run: ${selectedRun} · mode: ${mode} · `
      + `${state.provenance.source === "durable" ? "durable" : "local draft"}`;
  }
  function render() {
    const target = focusTarget();
    document.body.dataset.phase = state.phase;
    document.body.dataset.source = state.provenance.source;
    mounts.notice.textContent = state.notice;
    mounts.composeStatus.textContent = state.composeNotice;
    mounts.decideStatus.textContent = state.decisionNotice;
    mounts.saveStatus.textContent = state.saveNotice;
    mounts.runFacts.textContent = runFactsText();
    mounts.empty.hidden = state.phase === "loaded";
    mounts.seed.hidden = state.phase === "loaded";
    renderGraph(field, mounts.edges, state, onSelect);
    renderPalette(mounts.palette, state);
    renderSource(mounts.source, state);
    renderComposer(mounts.composer, state, composeDraft, onCompose);
    renderSave(mounts.save, state, saveDraft, onSave);
    renderDetail(mounts.detailBody, state, decisionDraft, onDecide);
    renderGates(mounts.gates, state);
    renderTimeline(mounts.timeline, state);
    // The write door is shut while a write is in flight AND while the stream
    // is not known to be carrying. The second half is not decoration: the
    // window promises in words that nothing may be written until the stream
    // is back, and a live button would make that sentence false.
    mounts.save.querySelector('[name="save"]').disabled =
      state.savePhase === "submitting" || !state.writeReady;
    restoreFocus(target);
  }
  // The fixture seam, and the whole of it: the adapter names the accepted
  // schema, the projection validates at the boundary, and both refuse rather
  // than repair; state answers with the current frozen value so a test can
  // read without reaching into module internals.
  window.conductGraph = Object.freeze({
    load(payload) {
      const adapted = adaptPayload(payload);
      const facts = adapted === null ? null : projectPayload(adapted);
      dispatch(facts ? {type: "loaded", facts} : {type: "refused"});
      return facts !== null;
    },
    state: () => state,
  });

  async function loadSession() {
    if (csrfToken) return {generation: sessionEpoch, token: csrfToken};
    const generation = ++sessionEpoch;
    const response = await fetch("/command/session", {cache: "no-store"});
    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      throw new Error("store_error");
    }
    if (!response.ok) throw new Error(refusalCode(payload));
    if (generation !== sessionEpoch
        || !payload || Object.keys(payload).sort().join(",") !== "csrf_token,origin"
        || typeof payload.csrf_token !== "string" || !payload.csrf_token
        || payload.origin !== location.origin) throw new Error("same_origin_denied");
    csrfToken = payload.csrf_token;
    return {generation, token: csrfToken};
  }
  // The single mutation door, and its one target. A Human's click is the only
  // thing that reaches it.
  async function submitGraph(runId, body) {
    let session;
    try {
      session = await loadSession();
    } catch (error) {
      return {code: error instanceof Error ? error.message : "store_error",
        status: "refused"};
    }
    let response;
    try {
      response = await fetch(
        `/command/runs/${encodeURIComponent(runId)}/graph`, {
          body: JSON.stringify(body),
          headers: {
            "Content-Type": "application/json", "X-Conduct-CSRF": session.token,
          },
          method: "POST",
        });
    } catch (_error) {
      return {status: "unknown"};
    }
    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const code = refusalCode(payload);
      if (["csrf_denied", "same_origin_denied"].includes(code)) {
        sessionEpoch += 1;
        csrfToken = "";
      }
      return {code, status: "refused"};
    }
    // A session rotated under an in-flight write makes its answer unusable:
    // this window cannot say what landed, and saying nothing landed would be
    // a claim about a durable record it did not observe.
    return session.generation !== sessionEpoch
      ? {status: "unknown"} : {created: response.status === 201, status: "accepted"};
  }
  function saveRefusal(result) {
    if (result.status !== "refused") return {phase: "outcome-unknown", notice: UNKNOWN};
    return {phase: "refused",
      notice: ERROR_LABELS[result.code] || ERROR_LABELS.store_error};
  }
  // Reached only by the Human submitting the save form. No load, signal,
  // reconnect or earlier write has a path here.
  //
  // The run and the write's own generation are taken BEFORE the request and
  // never read from the module again: `selectedRun` is a moving value, and a
  // POST for one run finishing after the Human has moved to another would
  // otherwise announce the first run's success on the second run's screen —
  // and re-read the second run as though the first's write had touched it.
  async function onSave(graphId) {
    const saveRun = selectedRun;
    if (!RUN_ID.test(saveRun) || !RUN_ID.test(graphId)) {
      dispatch({type: "save", phase: "refused", notice:
        "Load a run and name a valid graph id before writing a plan."});
      return;
    }
    if (!state.writeReady) {
      dispatch({type: "save", phase: "refused", notice: STREAM_DOWN});
      return;
    }
    const body = graphRequestBody(graphId, state);
    if (!body) {
      dispatch({type: "save", phase: "refused", notice: DRAFT_REFUSED});
      return;
    }
    const mine = ++writeGeneration;
    dispatch({type: "save", phase: "submitting",
      notice: "Writing one immutable plan…"});
    const result = await submitGraph(saveRun, body);
    // A dropped stream and a newer write both retire this one. Its answer is
    // about a screen that is no longer here, and it may not become a fact on
    // the one that is: whatever landed, the authoritative read will say so.
    if (mine !== writeGeneration || saveRun !== selectedRun) return;
    if (result.status !== "accepted") {
      // Nothing on screen moves on a refusal: the drawing stays the Human's
      // and no local value is promoted to durable by a request that failed.
      dispatch({type: "save", ...saveRefusal(result)});
      return;
    }
    // An accepted answer is still only an answer. What this run follows is
    // whatever the authoritative read says it follows, so the local copy is
    // dropped and re-read rather than trusted.
    refreshSelectedRun(saveRun,
      {phase: "idle", notice: result.created ? CREATED : RESTATED});
  }
  async function readJson(target) {
    const response = await fetch(target, {cache: "no-store"});
    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      throw new Error("store_error");
    }
    if (!response.ok) throw new Error(refusalCode(payload));
    return payload;
  }
  // Vendor rows are DATA, read once from the one registry the server serves.
  // A registry this window cannot read leaves every badge neutral; it never
  // leaves a step unnamed and never becomes a branch.
  async function readRegistry() {
    if (registryRows !== null) return registryRows;
    try {
      const payload = await readJson("/harnesses.json");
      registryRows = Array.isArray(payload) ? payload : [];
    } catch (_error) {
      registryRows = [];
    }
    return registryRows;
  }
  function loadOutcome(read, registry, carry) {
    const answer = adaptRunGraph(read, registry);
    if (answer.state === GRAPH_LOADED) {
      const facts = projectPayload(answer.payload);
      if (facts) return {type: "loaded", facts, ...carry};
      return {type: "refused", notice: CORRUPT, ...carry};
    }
    return answer.state === GRAPH_ABSENT
      ? {type: "absent", notice: ABSENT, ...carry}
      : {type: "refused", notice: CORRUPT, ...carry};
  }
  // A held save outcome is consumed only by the read that ANNOUNCES it.
  // Consuming it before the dispatch is how a plan came to be written with
  // nothing on screen ever saying so: a run frame arriving mid-read
  // superseded that read, the outcome had already been taken out of the
  // holder, and the retry announced nothing.
  //
  // It needs no run of its own to compare against. There is one door between
  // this holder and another run's screen — `refreshSelectedRun` empties it
  // the instant a different run is chosen — and a second check here would be
  // a branch no caller can reach, which is a guard nobody can prove.
  function takeCarry() {
    if (!pendingCarry) return {};
    const held = {savePhase: pendingCarry.phase, saveNotice: pendingCarry.notice};
    pendingCarry = null;
    return held;
  }
  // A read that could not be made says nothing about which run the screen
  // belongs to, and confirms no write. A save outcome still waiting on a read
  // is therefore DROPPED here rather than announced: the request was
  // accepted, and this window did not manage to see what the run now holds.
  function unconfirmed() {
    if (!pendingCarry) return {};
    pendingCarry = null;
    return {savePhase: "outcome-unknown", saveNotice: UNKNOWN};
  }
  async function loadSelectedRun(runId) {
    const requestEpoch = epoch;
    try {
      const [read, registry] = await Promise.all([
        readJson(`/command/runs/${encodeURIComponent(runId)}`), readRegistry(),
      ]);
      // The epoch guard is what makes `ready` mean the CHOSEN run: every run
      // change bumps it, so an answer that still matches is an answer about
      // the run now selected and about no other.
      if (requestEpoch !== epoch) return;
      dispatch(loadOutcome(read, registry,
        {...takeCarry(), ready: streamOpen}));
    } catch (error) {
      if (requestEpoch !== epoch) return;
      const code = error instanceof Error ? error.message : "store_error";
      dispatch({type: "refused", ...unconfirmed(), ready: false,
        notice: ERROR_LABELS[code] || ERROR_LABELS.store_error});
    }
  }
  // Serialized like the Cockpit's: a burst of signals collapses into one more
  // read after the one in flight, so a stream cannot stack reads on a window.
  async function refreshSelectedRun(runId, carry = null) {
    if (!RUN_ID.test(runId)) return;
    if (runId !== selectedRun) {
      // Choosing a run shuts the write door THIS INSTANT, before any request
      // goes out. Until the new run's read lands, the drawing on screen is
      // still the previous run's — and a write taken from it would build one
      // run's plan and send it to another run's immutable route, which no
      // later read could take back.
      //
      // A save status names one run's answer too, and carrying it onto
      // another run's screen would attribute a write to a run that never
      // received it.
      pendingCarry = null;
      dispatch({type: "ready", ready: false});
      dispatch({type: "save", phase: "idle", notice: ""});
    }
    selectedRun = runId;
    epoch += 1;
    refreshDirty = true;
    if (carry) pendingCarry = carry;
    if (refreshInFlight) return;
    refreshInFlight = true;
    while (refreshDirty) {
      refreshDirty = false;
      await loadSelectedRun(selectedRun);
    }
    refreshInFlight = false;
  }
  mounts.runForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const runId = mounts.runInput.value.trim();
    if (!RUN_ID.test(runId)) {
      dispatch({type: "refused", notice: "Use a valid run id."});
      return;
    }
    refreshSelectedRun(runId);
  });
  // Starting from the product's default plan is a Human's act too, and it
  // writes nothing: it puts the five-step process on screen as a LOCAL DRAFT
  // that the save button may then be pressed on.
  mounts.seed.addEventListener("click", () => {
    window.conductGraph.load(DALIO_DEFAULT);
  });

  const stream = new EventSource("/events");
  stream.onmessage = (event) => {
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch (_error) {
      return;
    }
    if (!frame || typeof frame !== "object" || !selectedRun) return;
    // A state frame also stands in for a run signal the server had to drop
    // from a full mailbox, so it buys the selected run's re-read too.
    if (frame.kind === "state") {
      refreshSelectedRun(selectedRun);
      return;
    }
    // Identifiers only, and only this run's. A frame naming another run, or
    // naming nothing this window can read as a run id, moves nothing here —
    // and no field of it ever becomes a fact on screen.
    if (frame.kind !== "run" || typeof frame.run_id !== "string"
        || !RUN_ID.test(frame.run_id) || frame.run_id !== selectedRun) return;
    refreshSelectedRun(frame.run_id);
  };
  // A reconnect does not by itself make this window current again. The stream
  // is open, but what it missed while it was down is unknown, so readiness is
  // granted by the authoritative READ that follows — and until that read
  // lands, the write door stays shut.
  stream.addEventListener("open", () => {
    streamOpen = true;
    if (selectedRun) {
      refreshSelectedRun(selectedRun);
      return;
    }
    dispatch({type: "ready", ready: true});
  });
  // A dropped stream rotates the session, the read epoch and the write
  // generation together: an answer to a write issued before the drop can no
  // longer be counted, the token that authorized it is gone, and the door it
  // came through is shut until the stream is back and re-read.
  stream.addEventListener("error", () => {
    streamOpen = false;
    epoch += 1;
    sessionEpoch += 1;
    writeGeneration += 1;
    csrfToken = "";
    dispatch({type: "ready", ready: false, notice: STREAM_DOWN});
  });
  render();
  // The window opens on the product's default graph — the five-step process
  // the December Command fixed — through the same public seam any other
  // fixture uses. Loading a run replaces it with that run's own facts.
  window.conductGraph.load(DALIO_DEFAULT);
})();
