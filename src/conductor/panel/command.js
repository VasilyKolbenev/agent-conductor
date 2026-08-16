"use strict";
import {
  ERROR_LABELS, RUN_ID, confirmationBody, exactArguments, isId, projectAction,
  projectControls, projectGates, projectProposal, projectRecords, projectScope,
  refusalCode, safeMode,
} from "./command-projection.js";
import {
  element, gateLabel, gateRow, renderComposer, renderConfirm,
  renderProposalReview,
} from "./command-view.js";
(() => {
  const mount = document.getElementById("commandCockpit");
  if (!mount) return;
  const UNKNOWN = "Outcome unknown. Reload the authoritative run.";
  const ACCEPTED = "Action request accepted and recorded. Nothing was executed.";
  const state = {action: null, confirmNotice: "", confirmPhase: "idle",
    controls: [], gates: {corrupt: false, rows: []}, mode: "unknown",
    phase: "idle", proposal: null, proposalNotice: "", proposalPhase: "idle",
    records: [], runId: "", warningCount: 0};
  const draft = {arguments: {}, attemptId: "", capability: "", confirmFocus: false,
    confirmedBy: "", instanceId: "", proposedBy: "", rationale: "", scope: "",
    timeout: "900"};
  let epoch = 0, csrfToken = "", sessionEpoch = 0;
  let refreshDirty = false, refreshExplicit = false, refreshInFlight = false;
  const input = element("input", {
    "aria-describedby": "commandCockpitStatus",
    autocomplete: "off",
    id: "commandRunId",
    maxlength: "128",
    name: "run_id",
    pattern: "[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
    required: "",
    spellcheck: "false",
    type: "text",
  });
  const button = element("button", {text: "Load run", type: "submit"});
  const form = element("form", {className: "command-form"}, [
    element("label", {className: "command-field", for: "commandRunId"}, [
      element("span", {text: "Run id"}), input,
    ]),
    button,
  ]);
  const status = element("p", {"aria-live": "polite", className: "command-status",
    id: "commandCockpitStatus", text: "Enter a run id to load its durable history."});
  const summary = element("div", {className: "command-summary"});
  const controls = element("div", {"aria-label": "Available controls",
    className: "command-controls"});
  const composer = element("section", {"aria-labelledby": "commandComposerTitle",
    className: "command-composer"});
  const proposalStatus = element("p", {"aria-live": "polite",
    className: "command-proposal-status"});
  const review = element("section", {"aria-labelledby": "commandReviewTitle",
    className: "command-review"});
  const confirmMount = element("section", {"aria-labelledby": "commandConfirmTitle",
    className: "command-confirm"});
  const confirmStatus = element("p", {"aria-live": "polite",
    className: "command-confirm-status"});
  const gates = element("section", {"aria-labelledby": "commandGateTitle",
    className: "command-gates"}, [
    element("h3", {id: "commandGateTitle", text: "Human gates"})]);
  const gateList = element("ul", {className: "command-gate-list"});
  gates.append(gateList);
  const history = element("ol", {"aria-label": "Durable command history",
    className: "command-history"});
  mount.querySelector(".empty")?.remove();
  mount.append(form, status, summary, controls, composer, proposalStatus, review,
    confirmMount, confirmStatus, gates, history);
  function render() {
    mount.dataset.phase = state.phase;
    const busy = state.phase === "loading" || state.phase === "refreshing";
    const hasFacts = ["ready", "refreshing", "stale"].includes(state.phase);
    mount.setAttribute("aria-busy", String(busy));
    button.disabled = busy;
    summary.replaceChildren();
    controls.replaceChildren();
    gateList.replaceChildren();
    history.replaceChildren();
    if (!hasFacts) {
      for (const node of [composer, review, confirmMount]) node.replaceChildren();
      return;
    }
    summary.append(
      element("span", {className: "command-fact", text: `run: ${state.runId}`}),
      element("span", {className: "command-fact", text: `mode: ${state.mode}`}),
      element("span", {
        className: "command-fact", text: `warnings: ${state.warningCount}`,
      }),
    );
    for (const row of state.controls) {
      for (const name of row.names) {
        controls.append(element("span", {
          className: "command-control", text: `${row.instanceId}: ${name}`,
        }));
      }
    }
    renderComposer(composer, proposalStatus, state, draft, submitProposal);
    renderProposalReview(review, state.proposal);
    renderConfirm(confirmMount, confirmStatus, state, draft, confirmProposal);
    if (state.gates.corrupt) {
      gateList.append(gateRow("corrupt", "Decision receipt relation is corrupt."));
    } else if (!state.gates.rows.length) {
      gateList.append(gateRow("idle", "No Human decision receipt."));
    } else {
      for (const gate of state.gates.rows) {
        gateList.append(gateRow(gate.state, `${gate.gateId}: ${gateLabel(gate.state)}`));
      }
    }
    for (const record of state.records) {
      history.append(element("li", {className: "command-record"}, [
        element("strong", {text: record.kind}),
        element("span", {className: "command-meta", text: record.facts.join(" · ")}),
      ]));
    }
  }
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
  function proposalBody(data) {
    const attemptId = String(data.get("attempt_id") || "").trim();
    const proposedBy = String(data.get("proposed_by") || "").trim();
    const rationale = String(data.get("rationale") || "").trim();
    const scope = projectScope(String(data.get("scope") || ""));
    const timeout = Number(String(data.get("timeout_seconds") || ""));
    const argumentsValue = exactArguments(draft.capability, data);
    if (!isId(attemptId) || !isId(proposedBy) || !rationale || !scope
        || !Number.isInteger(timeout) || timeout < 1 || timeout > 86400
        || !argumentsValue) return null;
    draft.arguments[draft.capability] = argumentsValue;
    return {
      instance_id: draft.instanceId, attempt_id: attemptId,
      capability: draft.capability, arguments: argumentsValue, scope,
      proposed_by: proposedBy, rationale, timeout_seconds: timeout,
    };
  }
  function setProposal(phase, notice) {
    state.proposalPhase = phase;
    state.proposalNotice = notice;
    render();
  }
  function setConfirm(phase, notice) {
    state.confirmPhase = phase;
    state.confirmNotice = notice;
    render();
  }
  function failurePhase(result) {
    return result.status === "refused" ? "refused" : "outcome-unknown";
  }
  function failureNotice(result) {
    return result.status === "refused"
      ? ERROR_LABELS[result.code] || ERROR_LABELS.store_error : UNKNOWN;
  }
  function runTarget(suffix) {
    return `/command/runs/${encodeURIComponent(state.runId)}${suffix}`;
  }
  // The single mutation door. Its target is a parameter, so every route the UI
  // can POST to is visible at the two call sites below and nowhere else.
  async function submitJson(target, body) {
    let session;
    try {
      session = await loadSession();
    } catch (error) {
      return {code: error instanceof Error ? error.message : "store_error",
        status: "refused"};
    }
    let response;
    try {
      response = await fetch(target, {
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
    return session.generation !== sessionEpoch
      ? {status: "unknown"} : {payload, status: "accepted"};
  }
  async function submitProposal(event) {
    event.preventDefault();
    const submitted = proposalBody(new FormData(event.currentTarget));
    if (!submitted || state.phase !== "ready") {
      setProposal("refused", "Complete the closed proposal fields with valid values.");
      return;
    }
    setProposal("submitting", "Creating one durable proposal…");
    const result = await submitJson(runTarget("/proposals"), submitted);
    if (result.status !== "accepted") {
      setProposal(failurePhase(result), failureNotice(result));
      return;
    }
    const proposal = projectProposal(result.payload, submitted, state.runId);
    if (!proposal) {
      setProposal("outcome-unknown", UNKNOWN);
      return;
    }
    state.action = null;
    state.confirmNotice = "";
    state.confirmPhase = "idle";
    state.proposal = proposal;
    setProposal("created", "Proposal created. No action was confirmed or executed.");
    refreshSelectedRun(state.runId);
  }
  // Reached only by the Human submitting the separate Confirm form; no load,
  // signal, reconnect or proposal success has a path to it.
  async function confirmProposal(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const submitted = confirmationBody(
      state.proposal, String(data.get("confirmed_by") || ""));
    if (!submitted || state.phase !== "ready") {
      setConfirm("refused", "Name the Human confirming this exact snapshot.");
      return;
    }
    // Held before the await: a run switch in flight clears the snapshot, and
    // the response must still be checked against the facts it was built from.
    const binding = state.proposal.binding;
    setConfirm("submitting", "Recording one authorized action request…");
    const result = await submitJson(runTarget("/actions"), submitted);
    if (result.status !== "accepted") {
      setConfirm(failurePhase(result), failureNotice(result));
      return;
    }
    const action = projectAction(result.payload, submitted, state.runId, binding);
    if (!action) {
      setConfirm("outcome-unknown", UNKNOWN);
      return;
    }
    state.action = action;
    setConfirm("accepted", ACCEPTED);
    refreshSelectedRun(state.runId);
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
  async function loadSelectedRun(runId, explicit) {
    const requestEpoch = epoch;
    state.phase = explicit ? "loading" : "refreshing";
    status.textContent = explicit
      ? "Loading durable command facts…"
      : "Refreshing authoritative command facts…";
    render();
    try {
      const base = `/command/runs/${encodeURIComponent(runId)}`;
      const [run, available] = await Promise.all([
        readJson(base), readJson(`${base}/controls`),
      ]);
      if (requestEpoch !== epoch) return;
      state.controls = projectControls(available);
      state.gates = projectGates(run && run.records, runId);
      state.mode = safeMode(run && run.run && run.run.mode);
      state.phase = "ready";
      state.records = projectRecords(run && run.records);
      state.runId = runId;
      state.warningCount = run && Array.isArray(run.warnings) ? run.warnings.length : 0;
      if (explicit && state.proposalPhase === "outcome-unknown") {
        state.proposalPhase = "idle"; state.proposalNotice = "Authoritative run reloaded."; }
      if (explicit && state.confirmPhase === "outcome-unknown") {
        state.confirmPhase = "idle"; state.confirmNotice = "Authoritative run reloaded."; }
      status.textContent = state.records.length
        ? "Authoritative durable history loaded."
        : "The run has no command records yet.";
    } catch (error) {
      if (requestEpoch !== epoch) return;
      const code = error instanceof Error ? error.message : "store_error";
      state.phase = explicit ? "refused" : "stale";
      status.textContent = ERROR_LABELS[code] || ERROR_LABELS.store_error;
    }
    render();
  }
  async function refreshSelectedRun(runId, explicit = false) {
    if (!RUN_ID.test(runId)) return;
    if (explicit && runId !== state.runId) {
      state.action = null;
      state.confirmNotice = "";
      state.confirmPhase = "idle";
      state.controls = [];
      state.gates = {corrupt: false, rows: []};
      state.mode = "unknown";
      state.proposal = null;
      state.proposalNotice = "";
      state.proposalPhase = "idle";
      state.records = [];
      state.warningCount = 0;
    }
    state.runId = runId;
    epoch += 1;
    refreshDirty = true;
    refreshExplicit = refreshExplicit || explicit;
    if (refreshInFlight) return;
    refreshInFlight = true;
    while (refreshDirty) {
      refreshDirty = false;
      const announce = refreshExplicit;
      refreshExplicit = false;
      const selected = state.runId;
      await loadSelectedRun(selected, announce);
    }
    refreshInFlight = false;
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const runId = input.value.trim();
    if (!RUN_ID.test(runId)) {
      state.phase = "refused";
      status.textContent = "Use a valid run id.";
      render();
      return;
    }
    refreshSelectedRun(runId, true);
  });
  window.addEventListener("conduct:run", (event) => {
    const runId = event.detail && event.detail.run_id;
    if (typeof runId === "string" && runId === state.runId && RUN_ID.test(runId)) {
      refreshSelectedRun(runId);
    }
  });
  window.addEventListener("conduct:disconnected", () => {
    epoch += 1;
    sessionEpoch += 1;
    csrfToken = "";
    if (!state.runId) return;
    state.phase = "stale";
    status.textContent = "Connection lost. Showing the last authoritative facts.";
    render();
  });
  window.addEventListener("conduct:connected", () => {
    if (state.runId) refreshSelectedRun(state.runId);
  });
})();
