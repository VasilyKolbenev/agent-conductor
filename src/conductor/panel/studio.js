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
import {focusTarget, restoreFocus, restoreTyped, typedValues} from "./studio-focus.js";
import {mountInspector} from "./studio-inspector.js";
import {mountAgents, mountDecisions} from "./studio-people.js";
import {mountRuns} from "./studio-runs.js";
import {workflowWriters} from "./studio-workflowwrite.js";
import {automationFlow} from "./studio-automation-flow.js";
import {mountAutomation} from "./studio-automation.js";
import {mountBridge} from "./studio-bridge.js";
import {mountTasks} from "./studio-tasks.js";
import {studioMounts} from "./studio-mounts.js";
import {mountShell, wireScreenKeys} from "./studio-shell.js";
import {preferences, preferenceHash} from "./studio-preferences.js";
import {quotaFlow} from "./studio-quotaflow.js";
import {navigation, navigationHash, taskFlow} from "./studio-taskflow.js";
//: What a Human's press on a step control MEANS. The wire stays HERE: that
//: module is handed this one's `write` and reaches no socket of its own.
import {decisionWriters, documentWriters, stepWriters}
  from "./studio-runwrite.js";
import {EMPTY, SCREENS, reduce} from "./studio-store.js";
import {isId, mountDiagnostics, mountOverview, mountToolbar}
  from "./studio-view.js";

//: What this window says is stored as a catalogue key and drawn in the reader's language
//: (`studio-notice-copy.js`), so a sentence already on screen switches with it.
const UNKNOWN = Object.freeze({key: "notice.outcome_unknown"});
const STREAM_DOWN = Object.freeze({key: "notice.stream_down_write"});
//: A GET is aborted at READ_DEADLINE, its body included -- wide, as a healthy
//: read can queue behind a write. LATE is this window's word for it.
const READ_DEADLINE = 20000;
const LATE = "read_late";
const LATE_SAID = Object.freeze({key: "notice.read_late"});
const UNSENT = Object.freeze({key: "notice.unsent"});
const WRITING = Object.freeze({key: "notice.writing"});
//: Whether a stored notice says this message, alone or as one of its parts.
const noticeHas = (notice, key) => Array.isArray(notice)
  ? notice.some((part) => noticeHas(part, key)) : notice?.key === key;



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


(() => {
  const shell = document.getElementById("studioShell");
  if (!shell) return;
  const byId = (name) => document.getElementById(name);
  const mounts = studioMounts(byId);
  // A control a person typed into and has not committed carries its words across a pass.
  shell.addEventListener("input", (event) => event.target.setAttribute?.("data-typed", ""));
  // Only a commit unmarks it: a control that refused its words (`aria-invalid`) still holds them.
  shell.addEventListener("change", (event) => {
    if (event.target.getAttribute?.("aria-invalid") !== "true") event.target.removeAttribute?.("data-typed");
  });

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
  let runEpoch = 0, runNavigation = 0, runDirty = false, runBusy = false;
  // What each queue has on the wire, for a press or a new subject to abort, and
  // the newest read of each list that has landed.
  let workflowReading = new AbortController();
  let runReading = new AbortController();
  let listReads = 0, workflowsLanded = 0, runsLanded = 0;
  // A write outcome waiting for the read that will make it true. It names what
  // the write ASKED FOR -- a document's canonical text, or a revision number --
  // because only a read showing that same thing confirms anything about it.
  let pendingCarry = null;
  const resume = navigation(location.hash);
  let readLocale = null;
  const appearance = preferences({root: document.documentElement,
    mount: byId("studioPreferences"), hash: location.hash, language: navigator.language,
    media: window.matchMedia("(prefers-color-scheme: dark)"), change: () => {
      history.replaceState(null, "", preferenceHash(navigationHash(state), appearance.value));
      render();
      if (readLocale !== appearance.value.locale) {
        readLocale = appearance.value.locale;
        loadWorkflows();
        if (chosenWorkflow && state.workflows.draft === state.workflows.readDraft) refreshWorkflow(chosenWorkflow);
        if (chosenRun) refreshRun(chosenRun);
      }
    }});
  readLocale = appearance.value.locale;
  window.addEventListener("pagehide", () => appearance.dispose());

  function dispatch(event, redraw = true) {
    const next = reduce(state, event);
    if (next === state) return;
    state = next;
    history.replaceState(null, "", preferenceHash(navigationHash(state), appearance.value));
    if (redraw) render();
  }

  // -- one render pass ----------------------------------------------------
  //
  // Every mount redraws from the state. What a person had focused, typed and
  // selected is carried across the pass by the net in `studio-focus.js`.
  function render() {
    const key = focusTarget(), typed = typedValues(shell), presentation = {...state, locale: appearance.value.locale};
    mountShell(mounts, presentation, handlers);
    mountTasks(byId("studioTasks"), presentation, handlers);
    mountOverview(mounts.bodyOverview, presentation, handlers);
    mountToolbar(mounts.toolbar, presentation, handlers);
    mountDiagnostics(mounts.diagnostics, presentation);
    mountCanvas(mounts.nodes, mounts.edges, presentation, handlers);
    mountInspector(mounts.inspector, presentation, handlers);
    mountRuns(mounts.bodyRuns, presentation, handlers);
    mountBridge(mounts.bridge, presentation, handlers);
    mountAutomation(mounts.bodyRuns, presentation, automation.snapshot(), automation);
    mountDecisions(mounts.bodyDecisions, presentation, handlers);
    mountAgents(mounts.bodyAgents, presentation, handlers);
    restoreTyped(shell, typed);
    restoreFocus(shell, key);
  }

  // -- reads ---------------------------------------------------------------
  //
  // The one read door. Every GET on this surface goes through it, so a refusal
  // is translated in one place and no caller invents a second vocabulary for
  // what went wrong -- and every GET is bounded in one place, body and all.
  async function readJson(target, stop = new AbortController()) {
    const timer = setTimeout(() => stop.abort(LATE), READ_DEADLINE);
    let response, payload;
    try {
      response = await fetch(target, {cache: "no-store", signal: stop.signal,
        headers: {"Accept-Language": appearance.value.locale}});
      payload = await response.json();
    } catch (_error) {
      throw new Error(stop.signal.aborted ? LATE : "store_error");
    } finally {
      clearTimeout(timer);
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
    tasks: () => "/command/tasks",
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
    automation: (id) => `/command/runs/${encodeURIComponent(id)}/automation`,
    automationPreview: (id) => `/command/runs/${encodeURIComponent(id)}/automation/preview`,
    automationAuthorize: (id) => `/command/runs/${encodeURIComponent(id)}/automation/authorize`,
    automationControl: (id) => `/command/runs/${encodeURIComponent(id)}/automation/control`,
  });
  // Closed mutation targets share the same CSRF and refusal door.
  const WRITE_TARGETS = Object.freeze(["draft", "revisions", "runs",
    "decisions", "proposals", "actions", "artifacts", "tasks",
    "automationPreview", "automationAuthorize", "automationControl"]);
  // These writes are independent of a selected workflow.
  const RUN_SCOPED = Object.freeze(
    ["decisions", "proposals", "actions", "artifacts", "tasks",
    "automationPreview", "automationAuthorize", "automationControl"]);

  function said(code) {
    if (code === LATE) return LATE_SAID;
    return Object.freeze({key: `error.${Object.hasOwn(ERROR_LABELS, code) ? code : "store_error"}`});
  }

  //: A read abandoned at its deadline FAILED. That is said once however many
  //: screens it fails, beside a person's own sentence rather than over it.
  function unread(error) {
    const code = error instanceof Error ? error.message : "store_error";
    if (code !== LATE) return {phase: "refused", notice: said(code)};
    const {notice, noticeFrom} = state;
    if (noticeHas(notice, LATE_SAID.key)) return {phase: "failed", notice};
    return {phase: "failed", notice: noticeFrom === "human" && notice
      ? Object.freeze([notice, LATE_SAID]) : LATE_SAID};
  }

  //: A deadline that passed while a frame's read of the SAME subject queued
  //: behind it, stream open. Nothing newer is out -- the queue waits on this
  //: read -- so the failure is still news, however steadily frames arrive.
  function stillNews(same, stop) {
    return same && streamOpen && stop.signal.reason === LATE;
  }

  //: Frames read the lists unserialized, so two reads of one list can be out
  //: at once. An outcome lands unless a NEWER read of that list already has:
  //: a dead read never paints over the recovery that replaced it.
  async function loadWorkflows() {
    const asked = ++listReads;
    dispatch({type: "workflows-phase", phase: "loading"});
    let heard;
    try {
      heard = {type: "workflows-loaded", payload: await readJson(path.workflows())};
    } catch (error) {
      heard = {type: "workflows-phase", ...unread(error)};
    }
    if (asked < workflowsLanded) return;
    workflowsLanded = asked;
    dispatch(heard);
  }

  async function loadRuns() {
    const asked = ++listReads;
    dispatch({type: "runs-phase", phase: "loading"});
    let heard;
    try {
      heard = {type: "runs-loaded", payload: await readJson(path.runs())};
    } catch (error) {
      heard = {type: "runs-phase", ...unread(error)};
    }
    if (asked < runsLanded) return;
    runsLanded = asked;
    dispatch(heard);
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
    const stop = workflowReading = new AbortController();
    const wants = pendingCarry && pendingCarry.kind === "publish"
      ? pendingCarry.revision : null;
    try {
      const [payload, revision] = await Promise.all([
        readJson(path.workflow(workflowId), stop),
        wants === null ? Promise.resolve(null)
          : readJson(path.revision(workflowId, wants), stop).catch(() => null),
      ]);
      if (asked !== workflowEpoch) return;
      dispatch({type: "workflow-loaded", payload,
        ...confirmedBy(payload, revision), ready: streamOpen});
    } catch (error) {
      // Only the current read settles a held write outcome. A late failure
      // under a queued frame says where it got to and leaves that to the next.
      if (asked === workflowEpoch) {
        dispatch({type: "workflow-unread", ...unconfirmed(), ...unread(error)});
      } else if (stillNews(workflowId === chosenWorkflow, stop)) {
        dispatch({type: "workflows-phase", ...unread(error)});
      }
    }
  }

  // Serialized like the Cockpit's: a burst of frames collapses into one more
  // read after the one in flight, so a stream cannot stack reads on a window.
  // A press or a change of subject aborts that read instead of queueing.
  async function refreshWorkflow(workflowId, carry = null, fresh = false) {
    if (!isId(workflowId)) return;
    if (fresh || workflowId !== chosenWorkflow) workflowReading.abort();
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
    try {
      while (workflowDirty) {
        workflowDirty = false;
        await loadWorkflow(chosenWorkflow);
      }
    } finally {
      workflowBusy = false;
    }
  }

  async function loadRun(runId) {
    const asked = runEpoch;
    const stop = runReading = new AbortController();
    try {
      const [read, controls] = await Promise.all([
        readJson(path.run(runId), stop),
        readJson(path.controls(runId), stop).catch(() => null),
      ]);
      if (asked !== runEpoch) return;
      if (state.tasks.selectedId && read.config?.task?.id !== state.tasks.selectedId) {
        clearRun();
        dispatch({type: "status", notice: {key: "notice.run_other_task"}});
        return;
      }
      dispatch({type: "run-loaded", read, controls});
      automation.sync(state.runs.detail);
    } catch (error) {
      if (asked !== runEpoch && !stillNews(runId === chosenRun, stop)) return;
      const heard = unread(error);
      dispatch({type: "runs-phase", ...heard});
      dispatch({type: "decisions-phase", phase: heard.phase});
      dispatch({type: "agents-phase", phase: heard.phase});
    }
  }

  // Serialized the same way, and a press or a change of run aborts likewise.
  async function refreshRun(runId, fresh = false) {
    if (!isId(runId)) return;
    if (fresh || runId !== chosenRun) { runNavigation += 1; runReading.abort(); }
    if (runId !== chosenRun) { automation.clear(); dispatch({type: "run-chosen", runId}); }
    chosenRun = runId;
    runEpoch += 1;
    runDirty = true;
    if (runBusy) return;
    runBusy = true;
    try {
      while (runDirty) {
        runDirty = false;
        await loadRun(chosenRun);
      }
    } finally {
      runBusy = false;
    }
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
        headers: {"Content-Type": "application/json", "Accept-Language": appearance.value.locale,
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
    if (result.code === LATE) return {phase: "refused", notice: UNSENT};
    const rows = result.payload && Array.isArray(result.payload.diagnostics)
      ? result.payload.diagnostics.map((row) => row.message).join(" · ") : "";
    return {phase: "refused",
      notice: rows ? Object.freeze({key: "notice.refusal_rows", params: {label: said(result.code), rows}})
        : said(result.code)};
  }

  //: A write's outcome lands beside the control that asked for it. A decision
  //: refusal written to the workflow save line would answer one question in
  //: the place another was asked.
  function say(channel, phase, notice) {
    if (["automationPreview", "automationAuthorize", "automationControl"].includes(channel)) return;
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
      if (recover) recover({status: "refused", code: LATE});
      return;
    }
    // A RUN-SCOPED write is retired by nothing but its own answer. Its
    // ownership is per run and step (`runs.writes`), a sibling write is
    // permitted while it is in flight, and a dropped stream reaches it
    // through the session it was authorized under (`submit`). The counter is
    // the workflow doors' rule -- one workflow write at a time -- and over
    // both it retired alpha's refusal the moment omega's write began.
    const mine = RUN_SCOPED.includes(target) ? null : ++writeGeneration;
    // A run-scoped refusal is spoken only where it was asked: a person who has
    // since chosen another task or run is not told about a run they left.
    const asked = mine === null && target !== "tasks" ? subject : null;
    say(target, "submitting", WRITING);
    const result = await submit(target, subject, body);
    if (mine !== null && mine !== writeGeneration) return;
    if (result.status !== "accepted") {
      const refusal = refusalOf(result);
      if (asked === null || asked === chosenRun) say(target, refusal.phase, refusal.notice);
      else if (noticeHas(state.notice, WRITING.key) && !Object.entries(state.runs.writes).some(([key, word]) =>
        key.startsWith(`${chosenRun}/`) && word === "writing")) dispatch({type: "status", notice: ""});
      if (recover) recover(result);
      return;
    }
    carry(result);
  }



  function clearRun() {
    automation.clear();
    runNavigation += 1;
    chosenRun = "";
    runEpoch += 1;
    runDirty = false;
    runReading.abort();
    dispatch({type: "run-cleared"});
  }



  //: The step road's four callbacks, handed the doors they may use and no
  //: others. `chosenRun` is a getter because the answer moves.
  const workflow = workflowWriters({state: () => state, chosenWorkflow: () => chosenWorkflow,
    dispatch, write, refreshWorkflow});
  const step = stepWriters({chosenRun: () => chosenRun, dispatch, isId,
    refreshRun, said, write});
  const docs = documentWriters({state: () => ({...state, locale: appearance.value.locale}), chosenRun: () => chosenRun, dispatch, isId,
    refreshRun, said, write});
  const decisions = decisionWriters({chosenRun: () => chosenRun, dispatch,
    draft: () => state.decisions.draft, isId, refreshRun, write});
  const tasks = taskFlow({state: () => state, read: readJson, write, dispatch,
    clearRun, loadRuns, refreshRun, runSelection: () => runNavigation});
  const automation = automationFlow({changed: render, selected: () => chosenRun,
    ready: () => streamOpen && state.runs.phase === "ready" && state.runs.detail?.run.run_id === chosenRun,
    read: (id, stop) => readJson(path.automation(id), stop), stop: () => new AbortController(),
    id: (kind) => `${kind}-${crypto.randomUUID()}`, write, refreshRun});
  const quotas = quotaFlow({read: readJson, dispatch,
    enabled: () => streamOpen && ["runs", "agents"].includes(state.screen) && !document.hidden,
    stop: () => new AbortController(), cancel: (timer) => clearTimeout(timer),
    schedule: (callback) => setTimeout(callback, 60000)});
  document.addEventListener("visibilitychange", () => quotas.syncQuotas());
  window.addEventListener("pagehide", () => { quotas.disposeQuotas(); automation.clear(); });

  const handlers = Object.freeze({
    onScreen: (screen) => {
      if (!SCREENS.includes(screen)) return;
      runNavigation += 1;
      dispatch({type: "screen", screen});
      if (screen === "runs" && state.runs.phase === "empty") loadRuns();
      quotas.syncQuotas();
    },
    onChooseWorkflow: (workflowId) => {
      if (workflowId) refreshWorkflow(workflowId);
    },
    ...workflow, onOpenRun: tasks.openRun,
    chooseTask: tasks.chooseTask, createTask: tasks.createTask,
    refreshTasks: tasks.refreshTasks,
    refreshQuotas: quotas.refreshQuotas,
    editTask: tasks.editTask,
    onFold: (name, open) => dispatch({type: "fold", name, open}),
    // Text edits keep their live controls; a later frame reads the held value.
    editStarter: (patch) => dispatch({type: "starter-edit", patch},
      !Object.hasOwn(patch, "workflowId")),
    editOpening: (patch) => dispatch({type: "opening-edit", patch},
      !Object.hasOwn(patch, "runId") && !Object.hasOwn(patch, "cycleId")
      && !Object.hasOwn(patch, "models")),
    onRefreshRuns: () => loadRuns(),
    onRefreshRun: () => { if (chosenRun) refreshRun(chosenRun, true); },
    onRefreshAgents: () => loadWorkflows(),
    onSelectTaskRun: (taskId, runId) => {
      tasks.chooseTask(taskId, false);
      dispatch({type: "screen", screen: "runs"});
      refreshRun(runId, true);
    },
    onSelectRun: (runId) => {
      dispatch({type: "screen", screen: "runs"});
      refreshRun(runId, true);
    },
    onSelect: (selection) => dispatch({type: "canvas-select", selection}),
    onView: (view) => dispatch({type: "canvas-view", ...view}),
    onEdit: (edit) => dispatch({type: "edit", edit}),
    onStatus: (notice) => dispatch({type: "status", notice}),
    selectRun: (runId) => refreshRun(runId, true),
    refreshRuns: () => loadRuns(),
    showDecisions: (runId) => {
      dispatch({type: "screen", screen: "decisions"});
      if (isId(runId)) refreshRun(runId, true);
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
      if (chosenRun) refreshRun(chosenRun, true);
    },
  });

  // -- the router ----------------------------------------------------------
  //
  // Five screens and one place that changes which is showing. The tabs are
  // wired by `mountShell` through `onScreen`; this adds the keyboard road the
  // platform expects of a tablist and nothing else.
  wireScreenKeys(mounts.tabs, handlers);

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
      tasks.refreshTasks();
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
    tasks.refreshTasks();
    quotas.syncQuotas();
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
    quotas.disconnectQuotas();
    automation.disconnect();
    dispatch({type: "connection", state: "closed"});
  });

  if (resume.taskId) dispatch({type: "task-chosen", taskId: resume.taskId}, false);
  dispatch({type: "screen", screen: resume.screen}, false);
  if (resume.workflowId) refreshWorkflow(resume.workflowId);
  if (resume.runId) refreshRun(resume.runId);
  render();
  // Only authoritative reads turn navigation hints into displayed facts.
  loadWorkflows();
  loadRuns();
  tasks.refreshTasks();
  quotas.syncQuotas();
})();
