"use strict";
(() => {
  const mount = document.getElementById("commandCockpit");
  if (!mount) return;
  const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
  const CONTROL_NAMES = new Set(
    ["dispatch", "review", "evidence", "stop", "retry", "switch"]);
  const CAPABILITY_FIELDS = Object.freeze({
    dispatch: Object.freeze([
      ["work_item_id", "id"], ["instruction_ref", "id"],
      ["profile", "enum", ["implement", "review"]],
      ["artifact_refs", "ids"],
      ["output_limit_profile", "enum", ["small", "normal"]],
    ]),
    review: Object.freeze([
      ["work_item_id", "id"], ["target_artifact_refs", "ids-required"],
      ["review_profile", "enum", ["quality", "security", "spec"]],
    ]),
    evidence: Object.freeze([["target_action_id", "id"],
      ["kinds", "enum-list", ["result", "diff", "tests", "status"]]]),
    stop: Object.freeze([["target_attempt_id", "id"],
      ["reason", "enum", ["user", "timeout", "switch"]]]),
    retry: Object.freeze([["prior_action_id", "id"],
      ["reason", "enum", ["failed", "unknown", "verification_failed", "user"]]]),
    switch: Object.freeze([
      ["prior_action_id", "id"], ["target_instance_id", "id"],
      ["handoff_ref", "id"],
    ]),
  });
  const ERROR_LABELS = Object.freeze({
    authorization_refused: "Authorization refused.",
    capability_unsupported: "This capability is unavailable.",
    contract_invalid: "The request shape is invalid.",
    csrf_denied: "The local session expired. Submit again.",
    malformed_request: "The request could not be read.",
    method_not_allowed: "That operation is unavailable.",
    record_conflict: "The durable record conflicts with an existing fact.",
    route_not_found: "The run route was not found.",
    route_unsafe: "The run route is structurally unsafe.",
    run_corrupt: "The run history is corrupt.",
    same_origin_denied: "The local origin was refused.",
    service_refused: "The command service refused the request.",
    store_error: "The run store is unavailable.",
  });
  const RECORD_FIELDS = Object.freeze({
    action_proposal: ["proposal_id", "instance_id", "capability", "proposed_at"],
    action_request: ["action_id", "instance_id", "capability", "requested_at"],
    action_result: ["receipt_id", "outcome", "finished_at"],
    adapter_observation: ["observation_id", "instance_id", "health", "observed_at"],
    attempt_event: ["event_id", "phase", "outcome", "recorded_at"],
    decision: ["receipt_id", "gate_id", "action", "decided_at"],
    evidence: ["evidence_id", "kind", "verification", "observed_at"],
  });
  const DECISION_STATES = Object.freeze({
    approve: "satisfied",
    reject: "failed",
    request_changes: "changes_requested",
    waive: "waived",
  });
  const state = {controls: [], gates: {corrupt: false, rows: []}, mode: "unknown",
    phase: "idle", proposal: null, proposalNotice: "", proposalPhase: "idle",
    records: [], runId: "", warningCount: 0};
  const draft = {arguments: {}, attemptId: "", capability: "", instanceId: "",
    proposedBy: "", rationale: "", scope: "", timeout: "900"};
  let epoch = 0, csrfToken = "", sessionEpoch = 0;
  let refreshDirty = false, refreshExplicit = false, refreshInFlight = false;
  function element(tag, attributes = {}, children = []) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (name === "className") node.className = value;
      else if (name === "text") node.textContent = value;
      else if (value === null) continue;
      else node.setAttribute(name, value);
    }
    node.append(...children);
    return node;
  }
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
  const gates = element("section", {"aria-labelledby": "commandGateTitle",
    className: "command-gates"}, [
    element("h3", {id: "commandGateTitle", text: "Human gates"})]);
  const gateList = element("ul", {className: "command-gate-list"});
  gates.append(gateList);
  const history = element("ol", {"aria-label": "Durable command history",
    className: "command-history"});
  mount.querySelector(".empty")?.remove();
  mount.append(form, status, summary, controls, composer, proposalStatus, review,
    gates, history);
  function safeMode(value) {
    return ["observe", "propose", "confirm"].includes(value) ? value : "unknown"; }
  function projectRecords(wrappers) {
    if (!Array.isArray(wrappers)) return [];
    return wrappers.map((wrapper) => {
      const kind = wrapper && typeof wrapper.record_type === "string"
        ? wrapper.record_type : "";
      const source = wrapper && wrapper.record && typeof wrapper.record === "object"
        ? wrapper.record : {};
      const fields = RECORD_FIELDS[kind];
      if (!fields) return {kind: "unknown", facts: []};
      const facts = fields.flatMap((name) => {
        const value = source[name];
        if (typeof value !== "string" || !value) return [];
        return [`${name}: ${value}`];
      });
      return {kind, facts};
    });
  }
  function projectControls(payload) {
    if (!payload || !Array.isArray(payload.instances)) return [];
    return payload.instances.flatMap((instance) => {
      if (!instance || !isId(instance.instance_id)
          || !Array.isArray(instance.controls)) return [];
      const names = [...new Set(instance.controls.filter((name) =>
        CONTROL_NAMES.has(name) && CAPABILITY_FIELDS[name]))].sort();
      return names.length ? [{instanceId: instance.instance_id, names}] : [];
    }).sort((left, right) => left.instanceId.localeCompare(right.instanceId));
  }
  function isId(value) { return typeof value === "string" && RUN_ID.test(value); }
  function isIdList(value) { return Array.isArray(value) && value.every(isId); }
  function projectDecision(value) {
    if (!value || typeof value !== "object") return null;
    if (!Number.isInteger(value.schema_version) || value.schema_version < 2) return null;
    if (![value.receipt_id, value.run_id, value.gate_id, value.actor].every(isId)) {
      return null;
    }
    if (!DECISION_STATES[value.action] || typeof value.decided_at !== "string") {
      return null;
    }
    if (typeof value.reason !== "string"
        || (["request_changes", "waive"].includes(value.action)
            && !value.reason.trim())) return null;
    if (!isIdList(value.scope_refs) || !isIdList(value.evidence_refs)) return null;
    if (typeof value.config_digest !== "string"
        || !/^sha256:[0-9a-f]{64}$/.test(value.config_digest)) return null;
    if (value.supersedes !== null && !isId(value.supersedes)) return null;
    if (value.supersedes === value.receipt_id) return null;
    return {
      action: value.action, gateId: value.gate_id, receiptId: value.receipt_id,
      runId: value.run_id, supersedes: value.supersedes,
    };
  }
  function projectGates(wrappers, runId) {
    if (!Array.isArray(wrappers)) return {corrupt: true, rows: []};
    const receipts = [];
    for (const wrapper of wrappers) {
      if (!wrapper || wrapper.record_type !== "decision") continue;
      const receipt = projectDecision(wrapper.record);
      if (!receipt || receipt.runId !== runId) return {corrupt: true, rows: []};
      receipts.push(receipt);
    }
    const byId = new Map(receipts.map((receipt) => [receipt.receiptId, receipt]));
    if (byId.size !== receipts.length) return {corrupt: true, rows: []};
    const gateIds = [...new Set(receipts.map((receipt) => receipt.gateId))].sort();
    const rows = [];
    for (const gateId of gateIds) {
      const matching = receipts.filter((receipt) => receipt.gateId === gateId);
      for (const receipt of matching) {
        if (receipt.supersedes === null) continue;
        const prior = byId.get(receipt.supersedes);
        if (!prior || prior.runId !== runId || prior.gateId !== gateId) {
          return {corrupt: true, rows: []};
        }
      }
      const superseded = new Set(matching.flatMap((receipt) =>
        receipt.supersedes === null ? [] : [receipt.supersedes]));
      const current = matching.filter((receipt) => !superseded.has(receipt.receiptId));
      if (current.length !== 1) return {corrupt: true, rows: []};
      rows.push({gateId, state: DECISION_STATES[current[0].action]});
    }
    return {corrupt: false, rows};
  }
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
      composer.replaceChildren();
      review.replaceChildren();
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
    renderComposer();
    renderProposalReview();
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
  function field(label, control) {
    return element("label", {className: "command-field"}, [
      element("span", {text: label}), control,
    ]);
  }
  function option(value) { return element("option", {text: value, value}); }
  function exactArguments(capability, data) {
    const output = {};
    for (const [name, kind, choices] of CAPABILITY_FIELDS[capability] || []) {
      const raw = String(data.get(`argument:${name}`) || "").trim();
      if (kind === "id") {
        if (!isId(raw)) return null;
        output[name] = raw;
      } else if (kind === "ids" || kind === "ids-required") {
        const values = raw ? raw.split(",").map((value) => value.trim()) : [];
        if (!isIdList(values) || (kind === "ids-required" && !values.length)) {
          return null;
        }
        output[name] = values;
      } else if (kind === "enum") {
        if (!choices.includes(raw)) return null;
        output[name] = raw;
      } else {
        const values = [...data.getAll(`argument:${name}`)];
        if (!values.length || !values.every((value) => choices.includes(value))
            || new Set(values).size !== values.length) return null;
        output[name] = values;
      }
    }
    return output;
  }
  function argumentControl(name, kind, choices) {
    const saved = (draft.arguments[draft.capability] || {})[name];
    if (kind === "enum") {
      const control = element(
        "select", {name: `argument:${name}`}, choices.map(option));
      if (choices.includes(saved)) control.value = saved;
      return control;
    }
    if (kind === "enum-list") {
      const control = element("select", {
        multiple: "", name: `argument:${name}`, size: String(choices.length),
      }, choices.map(option));
      for (const row of control.options) {
        row.selected = Array.isArray(saved) && saved.includes(row.value);
      }
      return control;
    }
    const control = element("input", {
      autocomplete: "off", name: `argument:${name}`,
      placeholder: kind.startsWith("ids") ? "id-1, id-2" : "stable-id",
      required: kind === "ids" ? null : "", spellcheck: "false", type: "text",
    });
    control.value = Array.isArray(saved) ? saved.join(", ") : saved || "";
    return control;
  }
  function renderComposer() {
    composer.replaceChildren();
    proposalStatus.textContent = state.proposalNotice;
    proposalStatus.dataset.proposalState = state.proposalPhase;
    if (!state.controls.length) return;
    const instances = state.controls.map((row) => row.instanceId);
    if (!instances.includes(draft.instanceId)) draft.instanceId = instances[0];
    const selected = state.controls.find((row) => row.instanceId === draft.instanceId);
    if (!selected.names.includes(draft.capability)) draft.capability = selected.names[0];
    const proposalForm = element("form", {className: "command-proposal-form"});
    const instance = element("select", {name: "instance_id"}, instances.map(option));
    instance.value = draft.instanceId;
    const capability = element(
      "select", {name: "capability"}, selected.names.map(option));
    capability.value = draft.capability;
    const argumentFields = element("fieldset", {className: "command-arguments"}, [
      element("legend", {text: "Closed capability arguments"}),
    ]);
    function fillArguments() {
      argumentFields.replaceChildren(element("legend", {
        text: "Closed capability arguments",
      }));
      for (const [name, kind, choices = []] of CAPABILITY_FIELDS[draft.capability]) {
        argumentFields.append(field(name, argumentControl(name, kind, choices)));
      }
    }
    instance.addEventListener("change", () => {
      draft.instanceId = instance.value;
      const row = state.controls.find((item) => item.instanceId === draft.instanceId);
      capability.replaceChildren(...row.names.map(option));
      draft.capability = row.names[0];
      fillArguments();
    });
    capability.addEventListener("change", () => {
      draft.capability = capability.value;
      fillArguments();
    });
    fillArguments();
    proposalForm.append(
      element("h3", {id: "commandComposerTitle", text: "Create proposal"}),
      field("Instance", instance), field("Capability", capability),
      field("Attempt id", proposalInput("attempt_id", "attempt-001")),
      field("Project scope", proposalInput("scope", "src, tests")),
      field("Proposed by", proposalInput("proposed_by", "operator")),
      field("Rationale", proposalInput("rationale", "Describe the reviewed work.")),
      field("Timeout seconds", proposalInput("timeout_seconds", "900", "number")),
      argumentFields,
      element("button", {text: "Create proposal", type: "submit"}),
    );
    proposalForm.addEventListener("submit", submitProposal);
    composer.append(proposalForm);
    const disabled = state.phase !== "ready"
      || ["submitting", "outcome-unknown"].includes(state.proposalPhase);
    for (const control of proposalForm.elements) control.disabled = disabled;
  }
  function proposalInput(name, fallback, type = "text") {
    const key = {
      attempt_id: "attemptId", proposed_by: "proposedBy",
      timeout_seconds: "timeout",
    }[name] || name;
    if (!draft[key]) draft[key] = fallback;
    const control = element("input", {
      autocomplete: "off", name, required: "", spellcheck: "false", type,
      value: draft[key],
    });
    control.addEventListener("input", () => { draft[key] = control.value; });
    return control;
  }
  function renderProposalReview() {
    review.replaceChildren();
    if (!state.proposal) return;
    review.append(element("h3", {
      id: "commandReviewTitle", text: "Proposal created — review only",
    }));
    for (const [label, value] of Object.entries(state.proposal)) {
      review.append(element("p", {className: "command-review-fact"}, [
        element("strong", {text: label}), element("span", {text: value}),
      ]));
    }
  }
  function gateLabel(value) {
    return {
      changes_requested: "■ changes requested",
      failed: "✕ rejected",
      satisfied: "✓ approved",
      waived: "◇ waived",
    }[value] || "✕ corrupt";
  }
  function gateRow(gateState, text) {
    return element("li", {className: "command-gate",
      "data-gate-state": gateState, text}); }
  function refusalCode(payload) {
    const code = payload && payload.error && payload.error.code;
    return typeof code === "string" && ERROR_LABELS[code] ? code : "store_error"; }
  function canonicalJson(value) {
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
    if (value && typeof value === "object") {
      const facts = Object.keys(value).sort().map((name) =>
        `${JSON.stringify(name)}:${canonicalJson(value[name])}`);
      return `{${facts.join(",")}}`;
    }
    return JSON.stringify(value);
  }
  function projectScope(value) {
    const rows = value.split(",").map((row) => row.trim()).filter(Boolean);
    if (!rows.length) return null;
    for (const row of rows) {
      const parts = row.split("/");
      if (row.startsWith("/") || row.includes("\\") || row.includes(":")
          || parts.some((part) => !part || part === "." || part === "..")) {
        return null;
      }
    }
    return rows;
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
  function projectProposal(payload, submitted) {
    if (!payload || typeof payload !== "object" || payload.schema_version !== 2
        || payload.run_id !== state.runId || !isId(payload.proposal_id)
        || typeof payload.proposed_at !== "string"
        || !/^sha256:[0-9a-f]{64}$/.test(payload.preview_digest || "")
        || !/^sha256:[0-9a-f]{64}$/.test(payload.config_digest || "")) return null;
    for (const name of ["instance_id", "attempt_id", "capability", "proposed_by",
      "rationale", "timeout_seconds"]) {
      if (payload[name] !== submitted[name]) return null;
    }
    if (canonicalJson(payload.arguments) !== canonicalJson(submitted.arguments)
        || canonicalJson(payload.scope) !== canonicalJson(submitted.scope)) return null;
    return Object.freeze({
      proposal_id: payload.proposal_id,
      preview_digest: payload.preview_digest,
      config_digest: payload.config_digest,
      instance: payload.instance_id,
      capability: payload.capability,
      arguments: canonicalJson(payload.arguments),
      scope: payload.scope.join(", "),
      timeout_seconds: String(payload.timeout_seconds),
      rationale: payload.rationale,
    });
  }
  async function submitProposal(event) {
    event.preventDefault();
    const submitted = proposalBody(new FormData(event.currentTarget));
    if (!submitted || state.phase !== "ready") {
      state.proposalPhase = "refused";
      state.proposalNotice = "Complete the closed proposal fields with valid values.";
      render();
      return;
    }
    state.proposalPhase = "submitting";
    state.proposalNotice = "Creating one durable proposal…";
    render();
    let session;
    try {
      session = await loadSession();
    } catch (error) {
      const code = error instanceof Error ? error.message : "store_error";
      state.proposalPhase = "refused";
      state.proposalNotice = ERROR_LABELS[code] || ERROR_LABELS.store_error;
      render();
      return;
    }
    let response;
    try {
      response = await fetch(`/command/runs/${encodeURIComponent(state.runId)}/proposals`, {
        body: JSON.stringify(submitted),
        headers: {
          "Content-Type": "application/json", "X-Conduct-CSRF": session.token,
        },
        method: "POST",
      });
    } catch (_error) {
      state.proposalPhase = "outcome-unknown";
      state.proposalNotice = "Outcome unknown. Reload the authoritative run.";
      render();
      return;
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
      state.proposalPhase = "refused";
      state.proposalNotice = ERROR_LABELS[code];
      render();
      return;
    }
    if (session.generation !== sessionEpoch) {
      state.proposalPhase = "outcome-unknown";
      state.proposalNotice = "Outcome unknown. Reload the authoritative run.";
      render();
      return;
    }
    const proposal = projectProposal(payload, submitted);
    if (!proposal) {
      state.proposalPhase = "outcome-unknown";
      state.proposalNotice = "Outcome unknown. Reload the authoritative run.";
      render();
      return;
    }
    state.proposal = proposal;
    state.proposalPhase = "created";
    state.proposalNotice = "Proposal created. No action was confirmed or executed.";
    render();
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
