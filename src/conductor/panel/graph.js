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
  // It names the graph the write asked for, because only a read of THAT
  // plan confirms anything about it.
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
    // Two facts, not one. The drawing's SOURCE is what a read gave it; whether
    // it also carries work this window composed and has not written is a
    // different question, and answering only the first would offer a Human
    // their own unwritten step back to them as the run's own. A durable plan
    // with a composed step standing in it is neither purely one nor the other,
    // and says both.
    const source = state.provenance.source === "durable" ? "durable" : "local draft";
    const composed = state.nodes.some((node) => node.draft);
    return `run: ${selectedRun} · mode: ${mode} · `
      + `${composed && source === "durable" ? "durable + local draft" : source}`;
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
    refreshSelectedRun(saveRun, {graphId,
      phase: "idle", notice: result.created ? CREATED : RESTATED});
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
  // Which product drives each instance, and which model it pins. A SECOND
  // read, because it is a second document: the run read carries the plan and
  // its position, and only the frozen configuration says anything about a
  // deployment.
  //
  // It is read per run and never cached, unlike the registry: the registry
  // describes this BUILD and cannot change under a window, while a
  // configuration belongs to one run and the next run selected has its own. A
  // read that refuses leaves the deployment unstated -- which is what this
  // window says when it does not know, and is never a claim that a run pins no
  // model.
  async function readControls(runId) {
    try {
      return await readJson(
        `/command/runs/${encodeURIComponent(runId)}/controls`);
    } catch (_error) {
      return null;
    }
  }
  // The verdict alone, with no save outcome attached to it yet. It used to
  // carry one in, which meant a document that ARRIVED whole and was then
  // refused — two hundred bytes of valid HTTP saying something this window
  // cannot read as one plan and one position — still announced that the plan
  // was written. Which holder answers is a decision about the verdict, so it
  // is made where the verdict is known and not one step earlier.
  // `read: true` marks a refusal that came from READING A RUN, and it is
  // load-bearing rather than bookkeeping. The fixture seam refuses too, through
  // `conductGraph.load`, and the two mean opposite things about the drawing on
  // screen: there the Human handed this window something it could not read, and
  // the drawing they handed it goes; here the RUN could not be read, which says
  // nothing about the plan this window is holding and is no reason to destroy
  // it. One event type served both and the wrong half won.
  function loadOutcome(read, registry, controls) {
    const answer = adaptRunGraph(read, registry, controls);
    if (answer.state === GRAPH_LOADED) {
      const facts = projectPayload(answer.payload);
      return facts
        ? {type: "loaded", facts}
        : {type: "refused", read: true, notice: CORRUPT};
    }
    return answer.state === GRAPH_ABSENT
      ? {type: "absent", notice: ABSENT}
      : {type: "refused", read: true, notice: CORRUPT};
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
  // A read that could not be made, or could not be READ, says nothing about
  // which run the screen belongs to and confirms no write. Both are the same
  // fact to a Human: the request was accepted, and this window did not manage
  // to see what the run now holds. The held outcome is therefore dropped and
  // replaced by exactly that, never announced as a confirmation.
  function unconfirmed() {
    if (!pendingCarry) return {};
    pendingCarry = null;
    return {savePhase: "outcome-unknown", saveNotice: UNKNOWN};
  }
  // A read confirms a write only when it shows THAT plan. "The read did not
  // refuse" is a much weaker thing, and it was what this window checked: a
  // run answering that it follows no graph at all, and a run answering with
  // somebody else's graph, both landed cleanly and both were taken as proof
  // that the plan just submitted was written. One screen then said "follows
  // no graph yet" and "The plan is written" at the same time.
  //
  // So the holder carries the graph id the write ASKED FOR, and only a
  // durable read of that same id confirms it. Every other landed answer is a
  // successful read and no confirmation: the window saw what the run holds,
  // and it is not what was written.
  function confirmedBy(outcome) {
    if (!pendingCarry) return {};
    const written = outcome.type === "loaded"
      && outcome.facts.provenance.graphId === pendingCarry.graphId;
    return written ? takeCarry() : unconfirmed();
  }
  async function loadSelectedRun(runId) {
    const requestEpoch = epoch;
    try {
      const [read, registry, controls] = await Promise.all([
        readJson(`/command/runs/${encodeURIComponent(runId)}`), readRegistry(),
        readControls(runId),
      ]);
      // The epoch guard is what makes `ready` mean the CHOSEN run: every run
      // change bumps it, so an answer that still matches is an answer about
      // the run now selected and about no other.
      if (requestEpoch !== epoch) return;
      const outcome = loadOutcome(read, registry, controls);
      // Two different questions, answered separately. Whether this window is
      // CURRENT: any landed read of the chosen run says yes, whatever the run
      // turns out to follow, and only a refusal says no. Whether a write is
      // CONFIRMED: only a read showing that same plan says yes.
      dispatch({...outcome, ...confirmedBy(outcome),
        ready: outcome.type !== "refused" && streamOpen});
    } catch (error) {
      if (requestEpoch !== epoch) return;
      const code = error instanceof Error ? error.message : "store_error";
      dispatch({type: "refused", read: true, ...unconfirmed(), ready: false,
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
      // A plan held for THIS run is let go here, at the Human's own action,
      // before the next run's read goes out. A drawing built against one run is
      // not a draft of another's, and the save door beside it writes to
      // whichever run is selected.
      dispatch({type: "discard"});
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
