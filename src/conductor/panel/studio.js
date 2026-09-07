"use strict";
// Boot, transport and router for the Workflow Studio: one store, one render
// pass, one door to the wire and one door that writes.
//
// This is the ONLY module of the Studio that touches the network. `graph.js`
// holds the same position in its own window and the source gate pins both the
// same way: two `fetch(` -- one read, one write -- and one `new EventSource(`.
//
// Facts enter through a READ and through nothing else. A frame on the stream
// carries an identifier and never a record, so it can never be a fact here: it
// buys exactly one thing, a re-read, and everything on screen after it came
// from that read.
//
// Writing is a Human pressing a button. No load, no frame, no reconnect and no
// earlier write can reach `submit`, and every write is followed by a read that
// is what actually confirms it -- only a read whose provenance matches what the
// write ASKED FOR. Anything else is outcome-unknown, and never a guess.
import {ERROR_LABELS, canonicalJson, refusalCode} from "./command-projection.js";
import {mountCanvas} from "./studio-canvas.js";
import {mountInspector} from "./studio-inspector.js";
import {mountAgents, mountDecisions} from "./studio-people.js";
import {mountRuns} from "./studio-runs.js";
//: What a Human's press on a step control MEANS. The wire stays HERE: that
//: module is handed this one's `write` and reaches no socket of its own.
import {decisionWriters, documentWriters, stepWriters}
  from "./studio-runwrite.js";
import {EMPTY, SCREENS, draftFrom, reduce, saveProblems} from "./studio-store.js";
import {isId, mountDiagnostics, mountOverview, mountShell, mountToolbar}
  from "./studio-view.js";

const UNKNOWN = "Outcome unknown. Read this workflow again to see what stands.";
const STREAM_DOWN = "Connection lost. The last read facts are still on screen, "
  + "and nothing may be written until the stream is back and what you are "
  + "writing to has been read again.";
const DRAFT_REFUSED = "The drawing was refused before it was offered to the "
  + "server: what stops it is listed beside the canvas.";
const SAVED = "The draft is stored on the server. It is not a revision: "
  + "publishing is what makes one, and a revision can never be edited.";
const PUBLISHED = "The revision is published and read back. A published "
  + "revision is immutable -- a change makes the next one and leaves this "
  + "exactly as it is.";
const RUN_OPENED = "The run is open and its plan is materialized from that "
  + "exact revision. Nothing about the workflow changed.";
//: The refusals a PUBLISH can meet that this window recovers from instead of
//: only reporting: both say the reviewed draft is not what the server holds --
//: one because its content moved, one because it is gone -- and both are
//: answered by closing the stale review and reading the workflow again. Every
//: other refusal is reported and nothing is reopened.
//:
//: A SAVE refused as `draft_conflict` is deliberately not on any such list. A
//: read there would merge the server's draft into the drawing on screen, which
//: is the automatic overwrite this whole seam exists to refuse: the person's
//: unsaved work stays exactly as it is and the read is theirs to ask for.
const REOPENED = Object.freeze(["draft_changed", "draft_conflict"]);

(() => {
  const shell = document.getElementById("studioShell");
  if (!shell) return;
  const byId = (name) => document.getElementById(name);
  const mounts = {
    project: byId("studioProject"),
    connection: byId("studioConnection"),
    primary: byId("studioPrimary"),
    status: byId("studioStatus"),
    tabs: [...byId("studioNav").querySelectorAll("[data-screen]")],
    screens: {
      overview: byId("screenOverview"), workflow: byId("screenWorkflow"),
      runs: byId("screenRuns"), decisions: byId("screenDecisions"),
      agents: byId("screenAgents"),
    },
    states: {
      overview: byId("stateOverview"), workflow: byId("stateWorkflow"),
      runs: byId("stateRuns"), decisions: byId("stateDecisions"),
      agents: byId("stateAgents"),
    },
    bodyOverview: byId("bodyOverview"),
    bodyRuns: byId("bodyRuns"),
    bodyDecisions: byId("bodyDecisions"),
    bodyAgents: byId("bodyAgents"),
    toolbar: byId("workflowToolbar"),
    edges: byId("workflowEdges"),
    nodes: byId("workflowNodes"),
    inspector: byId("workflowInspector"),
    diagnostics: byId("workflowDiagnostics"),
  };

  let state = EMPTY;
  // The token this process minted, held in ONE module-local variable. It goes
  // into a request header and nowhere else: never a URL, never a DOM node,
  // never storage. A generation travels with it so an answer authorized by a
  // session that has since rotated cannot land.
  let csrfToken = "", sessionEpoch = 0;
  let streamOpen = false;
  // Which write is the current one. A dropped stream retires the write in
  // flight along with the session that authorized it.
  let writeGeneration = 0;
  // Which workflow and which run this window is reading, held outside the
  // state because a read that refuses still has a subject worth naming.
  let chosenWorkflow = "", chosenRun = "";
  let workflowEpoch = 0, workflowDirty = false, workflowBusy = false;
  let runEpoch = 0, runDirty = false, runBusy = false;
  // A write outcome waiting for the read that will make it true. It names what
  // the write ASKED FOR -- a document's canonical text, or a revision number --
  // because only a read showing that same thing confirms anything about it.
  let pendingCarry = null;

  function dispatch(event, redraw = true) {
    const next = reduce(state, event);
    if (next === state) return;
    state = next;
    if (redraw) render();
  }

  // -- focus, kept across a render pass ------------------------------------
  //
  // Every mounting module restores focus inside its own subtree. This is the
  // net under all of them: it acts only when the pass ended with focus on the
  // body, so it can never fight a module that already put focus back.
  //
  // It carries the person's WORDS and CARET as well as the key. A pass
  // replaces the control, and the successor is drawn from the reducer, which
  // holds what `change` committed: the letters typed since, and where the
  // caret stood among them, would be lost or moved to the end (the fold
  // review's R1/R5). A step field belongs to its original form: if that form
  // vanished, even a now-unique sibling key must not take its caret (R4).
  function focusTarget() {
    const active = document.activeElement;
    if (!active || active === document.body || !active.getAttribute) return null;
    const key = active.getAttribute("data-focus")
      || active.getAttribute("data-focus-key");
    if (!key) return null;
    const form = active.closest("[data-step]");
    const typed = typeof active.setSelectionRange === "function"
      && typeof active.value === "string";
    return {key, step: form === null ? null : form.getAttribute("data-step"),
      value: typed ? active.value : null,
      start: typed ? active.selectionStart : null,
      end: typed ? active.selectionEnd : null};
  }

  function restoreFocus(held) {
    const active = document.activeElement;
    if (held === null || (active && active !== document.body)) return;
    const within = held.step === null ? "" : `[data-step="${held.step}"] `;
    const found = shell.querySelectorAll(
      `${within}[data-focus="${held.key}"], ${within}[data-focus-key="${held.key}"]`);
    if (found.length !== 1) return;
    const successor = found[0];
    successor.focus();
    if (held.value === null
        || typeof successor.setSelectionRange !== "function") return;
    if (successor.value !== held.value) successor.value = held.value;
    successor.setSelectionRange(held.start, held.end);
  }

  function render() {
    const key = focusTarget();
    mountShell(mounts, state, handlers);
    mountOverview(mounts.bodyOverview, state, handlers);
    mountToolbar(mounts.toolbar, state, handlers);
    mountDiagnostics(mounts.diagnostics, state);
    mountCanvas(mounts.nodes, mounts.edges, state, handlers);
    mountInspector(mounts.inspector, state, handlers);
    mountRuns(mounts.bodyRuns, state, handlers);
    mountDecisions(mounts.bodyDecisions, state, handlers);
    mountAgents(mounts.bodyAgents, state, handlers);
    restoreFocus(key);
  }

  // -- reads ---------------------------------------------------------------
  //
  // The one read door. Every GET on this surface goes through it, so a refusal
  // is translated in one place and no caller invents a second vocabulary for
  // what went wrong.
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

  //: `graph.js:209-226`, in shape and in order. The exact key set is checked
  //: rather than the two keys read, the origin is compared to this window's
  //: own, and a session that rotated under the request makes its answer
  //: unusable -- a token that arrived for a generation nobody is waiting for
  //: is not this window's token.
  async function loadSession() {
    if (csrfToken) return {generation: sessionEpoch, token: csrfToken};
    const generation = ++sessionEpoch;
    const payload = await readJson("/command/session");
    if (generation !== sessionEpoch
        || !payload || Object.keys(payload).sort().join(",") !== "csrf_token,origin"
        || typeof payload.csrf_token !== "string" || !payload.csrf_token
        || payload.origin !== location.origin) throw new Error("same_origin_denied");
    csrfToken = payload.csrf_token;
    return {generation, token: csrfToken};
  }

  const path = Object.freeze({
    workflows: () => "/command/workflows",
    workflow: (id) => `/command/workflows/${encodeURIComponent(id)}`,
    revision: (id, n) => `/command/workflows/${encodeURIComponent(id)}`
      + `/revisions/${encodeURIComponent(String(n))}`,
    draft: (id) => `/command/workflows/${encodeURIComponent(id)}/draft`,
    revisions: (id) => `/command/workflows/${encodeURIComponent(id)}/revisions`,
    runs: () => "/command/runs",
    run: (id) => `/command/runs/${encodeURIComponent(id)}`,
    controls: (id) => `/command/runs/${encodeURIComponent(id)}/controls`,
    decisions: (id) => `/command/runs/${encodeURIComponent(id)}/decisions`,
    proposals: (id) => `/command/runs/${encodeURIComponent(id)}/proposals`,
    actions: (id) => `/command/runs/${encodeURIComponent(id)}/actions`,
    artifacts: (id) => `/command/runs/${encodeURIComponent(id)}/artifacts`,
  });
  //: The seven targets the one mutation door may name. A write to anything
  //: else is unrepresentable rather than screened out afterwards.
  const WRITE_TARGETS = Object.freeze(["draft", "revisions", "runs",
    "decisions", "proposals", "actions", "artifacts"]);
  //: Which of them are about a RUN. They are gated on the STREAM being open
  //: rather than on a workflow's readiness, because none of them is about a
  //: workflow at all.
  const RUN_SCOPED = Object.freeze(
    ["decisions", "proposals", "actions", "artifacts"]);

  function said(code) {
    return ERROR_LABELS[code] || ERROR_LABELS.store_error;
  }

  async function loadWorkflows() {
    dispatch({type: "workflows-phase", phase: "loading"});
    try {
      dispatch({type: "workflows-loaded", payload: await readJson(path.workflows())});
    } catch (error) {
      dispatch({type: "workflows-phase", phase: "refused",
        notice: said(error instanceof Error ? error.message : "store_error")});
    }
  }

  async function loadRuns() {
    dispatch({type: "runs-phase", phase: "loading"});
    try {
      dispatch({type: "runs-loaded", payload: await readJson(path.runs())});
    } catch (error) {
      dispatch({type: "runs-phase", phase: "refused",
        notice: said(error instanceof Error ? error.message : "store_error")});
    }
  }

  // A held outcome is consumed only by the read that ANNOUNCES it. Consuming
  // it before the dispatch is how a write came to land with nothing on screen
  // ever saying so: a frame arriving mid-read superseded that read, the
  // outcome had already been taken out of the holder, and the retry announced
  // nothing.
  function takeCarry() {
    const held = {savePhase: pendingCarry.phase, saveNotice: pendingCarry.notice};
    pendingCarry = null;
    return held;
  }

  // A read that could not be MADE, or could not be READ, says nothing about
  // what the write did. The held outcome is dropped and replaced by exactly
  // that, never announced as a confirmation.
  function unconfirmed() {
    if (!pendingCarry) return {};
    pendingCarry = null;
    return {savePhase: "outcome-unknown", saveNotice: UNKNOWN};
  }

  //: A read confirms a write only when it shows THAT thing. "The read did not
  //: refuse" is a much weaker claim: a workflow answering with somebody else's
  //: draft, or with no draft at all, lands cleanly and confirms nothing. So a
  //: draft save is confirmed by the stored document's own canonical text and a
  //: publish by reading the revision back through its own route.
  function confirmedBy(payload, revision) {
    if (!pendingCarry) return {};
    if (pendingCarry.kind === "publish") {
      return revision !== null && revision.revision === pendingCarry.revision
        && revision.workflow_id === pendingCarry.workflowId
        ? takeCarry() : unconfirmed();
    }
    const draft = payload && payload.draft;
    const stored = draft ? canonicalJson(draft.document) : null;
    return stored === pendingCarry.text ? takeCarry() : unconfirmed();
  }

  async function loadWorkflow(workflowId) {
    const asked = workflowEpoch;
    const wants = pendingCarry && pendingCarry.kind === "publish"
      ? pendingCarry.revision : null;
    try {
      const [payload, revision] = await Promise.all([
        readJson(path.workflow(workflowId)),
        wants === null ? Promise.resolve(null)
          : readJson(path.revision(workflowId, wants)).catch(() => null),
      ]);
      if (asked !== workflowEpoch) return;
      dispatch({type: "workflow-loaded", payload,
        ...confirmedBy(payload, revision), ready: streamOpen});
    } catch (error) {
      if (asked !== workflowEpoch) return;
      const code = error instanceof Error ? error.message : "store_error";
      dispatch({type: "workflow-unread", phase: "refused", ...unconfirmed(),
        notice: said(code)});
    }
  }

  // Serialized like the Cockpit's: a burst of frames collapses into one more
  // read after the one in flight, so a stream cannot stack reads on a window.
  async function refreshWorkflow(workflowId, carry = null) {
    if (!isId(workflowId)) return;
    if (workflowId !== chosenWorkflow) {
      // Choosing a workflow shuts the write door THIS INSTANT, before any
      // request goes out: until the new read lands the drawing on screen is
      // still the previous workflow's, and a save taken from it would write
      // one workflow's document to another's draft.
      pendingCarry = null;
      dispatch({type: "workflow-chosen", workflowId});
    }
    chosenWorkflow = workflowId;
    workflowEpoch += 1;
    workflowDirty = true;
    if (carry) pendingCarry = carry;
    if (workflowBusy) return;
    workflowBusy = true;
    while (workflowDirty) {
      workflowDirty = false;
      await loadWorkflow(chosenWorkflow);
    }
    workflowBusy = false;
  }

  async function loadRun(runId) {
    const asked = runEpoch;
    try {
      const [read, controls] = await Promise.all([
        readJson(path.run(runId)),
        readJson(path.controls(runId)).catch(() => null),
      ]);
      if (asked !== runEpoch) return;
      dispatch({type: "run-loaded", read, controls});
    } catch (error) {
      if (asked !== runEpoch) return;
      const code = error instanceof Error ? error.message : "store_error";
      dispatch({type: "runs-phase", phase: "refused", notice: said(code)});
      dispatch({type: "decisions-phase", phase: "refused"});
      dispatch({type: "agents-phase", phase: "refused"});
    }
  }

  async function refreshRun(runId) {
    if (!isId(runId)) return;
    if (runId !== chosenRun) dispatch({type: "run-chosen", runId});
    chosenRun = runId;
    runEpoch += 1;
    runDirty = true;
    if (runBusy) return;
    runBusy = true;
    while (runDirty) {
      runDirty = false;
      await loadRun(chosenRun);
    }
    runBusy = false;
  }

  // -- the one mutation door -----------------------------------------------
  //
  // Its target comes from a closed list and its body from the caller. Nothing
  // else in this file reaches the wire with a method, and a Human's click is
  // the only thing that reaches this.
  async function submit(target, subject, body) {
    if (!WRITE_TARGETS.includes(target)) return {status: "refused",
      code: "route_not_found"};
    let session;
    try {
      session = await loadSession();
    } catch (error) {
      return {code: error instanceof Error ? error.message : "store_error",
        status: "refused"};
    }
    let response;
    try {
      response = await fetch(path[target](subject), {
        body: JSON.stringify(body),
        headers: {"Content-Type": "application/json",
          "X-Conduct-CSRF": session.token},
        method: "POST",
      });
    } catch (_error) {
      return {status: "unknown"};
    }
    let payload = null;
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
      return {code, payload, status: "refused"};
    }
    // A session rotated under an in-flight write makes its answer unusable:
    // this window cannot say what landed, and saying nothing landed would be a
    // claim about a durable record it did not observe.
    return session.generation !== sessionEpoch
      ? {status: "unknown"} : {payload, status: "accepted"};
  }

  function refusalOf(result) {
    if (result.status !== "refused") {
      return {phase: "outcome-unknown", notice: UNKNOWN};
    }
    const rows = result.payload && Array.isArray(result.payload.diagnostics)
      ? result.payload.diagnostics.map((row) => row.message).join(" · ") : "";
    return {phase: "refused",
      notice: rows ? `${said(result.code)} ${rows}` : said(result.code)};
  }

  //: A write's outcome lands beside the control that asked for it. A decision
  //: refusal written to the workflow save line would answer one question in
  //: the place another was asked.
  function say(channel, phase, notice) {
    dispatch(RUN_SCOPED.includes(channel)
      ? {type: "status", notice} : {type: "save", phase, notice});
  }

  //: Every write goes through this shape: shut the door, ask, and let the READ
  //: that follows say what happened. `mine` is taken BEFORE the request and
  //: never read from the module again -- a POST for one workflow finishing
  //: after the Human has moved to another would otherwise announce the first's
  //: success on the second's screen.
  //:
  //: A RUN-SCOPED write is gated on the STREAM and a workflow write on
  //: `writeReady`, and they are two questions: readiness names one answer about
  //: one workflow, and a run write is not about a workflow at all.
  //: `recover` is offered the REFUSAL, after it has been said. A refusal is
  //: normally the end of a write, but one of them names a state this window
  //: can still act on -- see `onPublishConfirm` -- and a window that only
  //: printed it would leave a person looking at a review of a document that no
  //: longer exists, with no control that does anything but fail again.
  async function write(target, subject, body, carry, recover = null) {
    const ready = RUN_SCOPED.includes(target)
      ? streamOpen : state.workflows.writeReady;
    if (!ready) {
      say(target, "refused", STREAM_DOWN);
      return;
    }
    // A RUN-SCOPED write is retired by nothing but its own answer. Its
    // ownership is per run and step (`runs.writes`), a sibling write is
    // permitted while it is in flight, and a dropped stream reaches it
    // through the session it was authorized under (`submit`). The counter is
    // the workflow doors' rule -- one workflow write at a time -- and over
    // both it retired alpha's refusal the moment omega's write began.
    const mine = RUN_SCOPED.includes(target) ? null : ++writeGeneration;
    say(target, "submitting", "Writing…");
    const result = await submit(target, subject, body);
    if (mine !== null && mine !== writeGeneration) return;
    if (result.status !== "accepted") {
      const refusal = refusalOf(result);
      say(target, refusal.phase, refusal.notice);
      if (recover) recover(result);
      return;
    }
    carry(result);
  }

  // -- what a Human presses -------------------------------------------------
  function onSaveDraft() {
    const held = state.workflows;
    const drawing = held.draft;
    if (drawing === null || !isId(chosenWorkflow)) {
      dispatch({type: "save", phase: "refused",
        notice: "Choose a workflow and draw something before saving."});
      return;
    }
    if (saveProblems(drawing).length) {
      dispatch({type: "save", phase: "refused", notice: DRAFT_REFUSED});
      return;
    }
    // The document is read into a value ONCE and that value is what is judged,
    // what is sent, and what the confirming read is compared against.
    const written = JSON.parse(JSON.stringify(drawing));
    // Beside it, WHICH stored draft this window is replacing: the digest the
    // last read carried, or the claim that the last read carried none. It is
    // the same echo the publish body sends, one road earlier, and it is what
    // stops this save silently overwriting a draft another window stored after
    // this one last looked. `reviewedDigest` is exactly that answer and is
    // taken away by the read that would make it wrong.
    const body = held.reviewedDigest === null
      ? {document: written, expected_absent: true}
      : {document: written, expected_digest: held.reviewedDigest};
    const asked = chosenWorkflow;
    write("draft", asked, body, () => {
      // The answer belongs to the workflow it was asked about. If the Human
      // has moved on, it is not announced here and no read is provoked for a
      // workflow this write never touched.
      if (asked !== chosenWorkflow) return;
      refreshWorkflow(asked, {kind: "draft", workflowId: asked,
        text: canonicalJson(written), phase: "saved", notice: SAVED});
    });
  }

  // Publishing is two steps. This one opens the review and writes NOTHING; the
  // reducer refuses to open it over a workflow the server has not called
  // publishable, so a review can never be shown for a write that would be
  // refused anyway.
  function onPublish() {
    dispatch({type: "publish-review", open: true});
  }

  // Cancel writes nothing at all: the draft, the drawing and every standing
  // revision are exactly as they were, and the panel closes.
  function onPublishCancel() {
    dispatch({type: "publish-review", open: false});
  }

  function onPublishConfirm() {
    const held = state.workflows;
    const number = held.nextRevision;
    if (!isId(chosenWorkflow) || !held.publishable
        || !Number.isInteger(number)) {
      dispatch({type: "save", phase: "refused",
        notice: "Publishing needs a SAVED draft the server says would "
          + "construct a revision."});
      return;
    }
    const asked = chosenWorkflow;
    // The body names the revision expected, no document, and WHICH draft this
    // window reviewed. The draft the server holds is the one durable source,
    // read once by the route -- and the echo is what lets the route refuse when
    // that source moved between the review and this click.
    write("revisions", asked,
          {revision: number, reviewed_digest: held.reviewedDigest}, () => {
      if (asked !== chosenWorkflow) return;
      refreshWorkflow(asked, {kind: "publish", workflowId: asked,
        revision: number, phase: "saved", notice: PUBLISHED});
    }, (result) => {
      // The two refusals a window can act on rather than only report, and the
      // recovery is one shape because the situation is: the review on screen is
      // of a document the server no longer holds. Leaving the panel open would
      // show a person that document above a Confirm now guaranteed to fail. So
      // the review is closed and the workflow is re-read, and what comes back
      // is what actually stands -- the newer DRAFT, which the person reviews
      // instead, or, when the draft was consumed rather than replaced, the
      // published REVISION, from which Edit as new draft is the road on.
      if (!REOPENED.includes(result.code) || asked !== chosenWorkflow) return;
      dispatch({type: "publish-review", open: false});
      refreshWorkflow(asked);
    });
  }

  function onOpenRun(request) {
    if (!isId(request.runId) || !isId(request.cycleId)
        || !isId(chosenWorkflow) || !Number.isInteger(request.revision)) {
      dispatch({type: "save", phase: "refused",
        notice: "A run needs a chosen workflow with a published revision, a "
          + "run id and a cycle id -- each letters, digits, dot, underscore "
          + "or hyphen."});
      return;
    }
    const body = {run_id: request.runId, cycle_id: request.cycleId,
      mode: request.mode, participants: request.participants,
      workflow_id: chosenWorkflow, revision: request.revision,
      assignments: request.assignments};
    write("runs", null, body, () => {
      dispatch({type: "save", phase: "saved", notice: RUN_OPENED});
      dispatch({type: "opening-cleared"});
      loadRuns();
      refreshRun(request.runId);
    });
  }

  function onStartWorkflow(request) {
    if (!isId(request.workflowId)) {
      dispatch({type: "status",
        notice: "A workflow id is letters, digits, dot, underscore or hyphen, "
          + "up to 128 characters."});
      return;
    }
    const starter = state.workflows.starters.find(
      (row) => row.starter_id === request.starterId) || null;
    const seed = starter === null
      ? {schema_version: 1, title: request.workflowId, nodes: [], edges: []}
      : starter.document;
    // The read goes first and the drawing lands on top of it: opening a name
    // that already exists must show what the server holds, not bury it.
    refreshWorkflow(request.workflowId);
    dispatch({type: "seed", document: draftFrom(seed)});
  }

  //: The one road out of a published workflow that holds no draft. It copies
  //: the revision ON SCREEN -- `detail.published`, the document the canvas is
  //: drawing -- into a draft this window holds, and reaches the wire not at
  //: all: `draftFrom` rebuilds it without `template_id` and `revision`, the two
  //: words the save route refuses, and Save draft is what puts it on the server
  //: through the draft route that already exists. The revision is untouched;
  //: publishing the copy makes the NEXT one, which is what immutability means
  //: from the editing side.
  //:
  //: It seeds for the workflow ALREADY chosen and never re-chooses it. Choosing
  //: is the one door a held drawing is let go through, and it clears the very
  //: read this copy is taken from, so a re-choose here would throw away the
  //: published document on the way to copying it.
  //:
  //: The two refusals are this door's own rule rather than a second opinion
  //: about the control's: a drawing already on screen is work a copy would
  //: destroy, and a revision that is not there cannot be copied. The toolbar
  //: shuts the control on those same two facts and on the write door besides,
  //: because the road ends in a write.
  function onEditPublished() {
    const held = state.workflows;
    const copy = held.detail === null ? null : draftFrom(held.detail.published);
    if (held.draft !== null || copy === null) {
      dispatch({type: "status", notice: held.draft !== null
        ? "There is already a drawing on screen, and copying the published "
          + "revision would replace it. Nothing was copied."
        : "There is no published revision on screen to copy."});
      return;
    }
    dispatch({type: "seed", document: copy});
  }

  function onValidate() {
    if (!isId(chosenWorkflow)) return;
    refreshWorkflow(chosenWorkflow);
    dispatch({type: "status", notice: "Read again. The server's diagnostics "
      + "describe the SAVED draft; the list beside them is what this window "
      + "already sees about the drawing, which has not been sent."});
  }

  //: The step road's four callbacks, handed the doors they may use and no
  //: others. `chosenRun` is a getter because the answer moves.
  const step = stepWriters({chosenRun: () => chosenRun, dispatch, isId,
    refreshRun, said, write});
  const docs = documentWriters({chosenRun: () => chosenRun, dispatch, isId,
    refreshRun, said, write});
  const decisions = decisionWriters({chosenRun: () => chosenRun, dispatch,
    draft: () => state.decisions.draft, isId, refreshRun, write});

  const handlers = Object.freeze({
    onScreen: (screen) => {
      if (!SCREENS.includes(screen)) return;
      dispatch({type: "screen", screen});
      if (screen === "runs" && state.runs.phase === "empty") loadRuns();
    },
    onChooseWorkflow: (workflowId) => {
      if (workflowId) refreshWorkflow(workflowId);
    },
    onStartWorkflow, onValidate, onSaveDraft, onPublish, onPublishConfirm,
    onPublishCancel, onEditPublished, onOpenRun,
    onFold: (name, open) => dispatch({type: "fold", name, open}),
    // Text commits on blur must not replace the next click's target. Their
    // live controls already show the edit; a later frame reads the held value.
    editStarter: (patch) => dispatch({type: "starter-edit", patch},
      !Object.hasOwn(patch, "workflowId")),
    editOpening: (patch) => dispatch({type: "opening-edit", patch},
      !Object.hasOwn(patch, "runId") && !Object.hasOwn(patch, "cycleId")),
    onRefreshRuns: () => loadRuns(),
    onRefreshRun: () => { if (chosenRun) refreshRun(chosenRun); },
    onRefreshAgents: () => loadWorkflows(),
    onSelectRun: (runId) => {
      dispatch({type: "screen", screen: "runs"});
      refreshRun(runId);
    },
    onSelect: (selection) => dispatch({type: "canvas-select", selection}),
    onView: (view) => dispatch({type: "canvas-view", ...view}),
    onEdit: (edit) => dispatch({type: "edit", edit}),
    onStatus: (notice) => dispatch({type: "status", notice}),
    selectRun: (runId) => refreshRun(runId),
    refreshRuns: () => loadRuns(),
    showDecisions: (runId) => {
      dispatch({type: "screen", screen: "decisions"});
      if (isId(runId)) refreshRun(runId);
    },
    chooseStep: step.chooseStep,
    editStep: step.editStep,
    proposeStep: step.proposeStep,
    confirmStep: step.confirmStep,
    editDocument: docs.editDocument,
    publishDocument: docs.publishDocument,
    selectDecision: (key) => dispatch({type: "decision-chosen", key}),
    editDecision: (patch) => dispatch({type: "decision-edit", patch}),
    submitDecision: decisions.submitDecision,
    refreshAgents: () => {
      loadWorkflows();
      if (chosenRun) refreshRun(chosenRun);
    },
  });

  // -- the router ----------------------------------------------------------
  //
  // Five screens and one place that changes which is showing. The tabs are
  // wired by `mountShell` through `onScreen`; this adds the keyboard road the
  // platform expects of a tablist and nothing else.
  mounts.tabs.forEach((node, at) => {
    node.addEventListener("keydown", (event) => {
      const step = {ArrowRight: 1, ArrowLeft: -1}[event.key];
      if (!step) return;
      event.preventDefault();
      const next = mounts.tabs[(at + step + mounts.tabs.length)
        % mounts.tabs.length];
      handlers.onScreen(next.getAttribute("data-screen"));
      next.focus();
    });
  });

  // -- the stream ----------------------------------------------------------
  //
  // Two frame kinds and no third. A `state` frame stands in for a run signal
  // the server had to drop from a full mailbox, so it buys the same re-read; a
  // `run` frame carries identifiers only, and no field of it ever becomes a
  // fact on screen.
  const stream = new EventSource("/events");
  stream.onmessage = (event) => {
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch (_error) {
      return;
    }
    if (!frame || typeof frame !== "object") return;
    if (frame.kind === "state") {
      loadWorkflows();
      if (chosenWorkflow) refreshWorkflow(chosenWorkflow);
      if (chosenRun) refreshRun(chosenRun);
      return;
    }
    if (frame.kind !== "run" || !isId(frame.run_id)) return;
    loadRuns();
    if (frame.run_id === chosenRun) refreshRun(frame.run_id);
  };
  // A reconnect does not by itself make this window current again. The stream
  // is open, but what it missed while it was down is unknown, so readiness is
  // granted by the READ that follows -- and until that read lands the write
  // door stays shut.
  stream.addEventListener("open", () => {
    streamOpen = true;
    dispatch({type: "connection", state: "open"});
    loadWorkflows();
    loadRuns();
    if (chosenWorkflow) refreshWorkflow(chosenWorkflow);
    if (chosenRun) refreshRun(chosenRun);
  });
  // A dropped stream rotates the session, both read epochs and the write
  // generation together: an answer to a write issued before the drop can no
  // longer be counted, the token that authorized it is gone, and the door it
  // came through is shut until the stream is back and re-read.
  stream.addEventListener("error", () => {
    streamOpen = false;
    workflowEpoch += 1;
    runEpoch += 1;
    sessionEpoch += 1;
    writeGeneration += 1;
    csrfToken = "";
    pendingCarry = null;
    dispatch({type: "connection", state: "closed"});
  });

  render();
  // The window opens by reading what this project holds. Nothing is drawn from
  // a fixture and nothing is assumed: until these land, every screen says in
  // plain language that nothing has been read.
  loadWorkflows();
  loadRuns();
})();
