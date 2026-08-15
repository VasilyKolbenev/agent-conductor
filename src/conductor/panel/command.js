"use strict";

(() => {
  const mount = document.getElementById("commandCockpit");
  if (!mount) return;

  const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
  const CONTROL_NAMES = new Set([
    "dispatch", "review", "evidence", "stop", "retry", "switch",
  ]);
  const ERROR_LABELS = Object.freeze({
    authorization_refused: "Authorization refused.",
    capability_unsupported: "This capability is unavailable.",
    contract_invalid: "The request shape is invalid.",
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
  const state = {
    controls: [], mode: "unknown", phase: "idle", records: [], runId: "",
    warningCount: 0,
  };
  let epoch = 0;
  let refreshDirty = false;
  let refreshExplicit = false;
  let refreshInFlight = false;

  function element(tag, attributes = {}, children = []) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (name === "className") node.className = value;
      else if (name === "text") node.textContent = value;
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
  const status = element("p", {
    "aria-live": "polite", className: "command-status", id: "commandCockpitStatus",
    text: "Enter a run id to load its durable history.",
  });
  const summary = element("div", {className: "command-summary"});
  const controls = element("div", {
    "aria-label": "Available controls", className: "command-controls",
  });
  const history = element("ol", {
    "aria-label": "Durable command history", className: "command-history",
  });
  mount.querySelector(".empty")?.remove();
  mount.append(form, status, summary, controls, history);

  function safeMode(value) {
    return ["observe", "propose", "confirm"].includes(value) ? value : "unknown";
  }

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
    const names = payload.instances.flatMap((instance) =>
      instance && Array.isArray(instance.controls) ? instance.controls : []);
    return [...new Set(names.filter((name) => CONTROL_NAMES.has(name)))].sort();
  }

  function render() {
    mount.dataset.phase = state.phase;
    const busy = state.phase === "loading" || state.phase === "refreshing";
    const hasFacts = ["ready", "refreshing", "stale"].includes(state.phase);
    mount.setAttribute("aria-busy", String(busy));
    button.disabled = busy;
    summary.replaceChildren();
    controls.replaceChildren();
    history.replaceChildren();
    if (!hasFacts) return;
    summary.append(
      element("span", {className: "command-fact", text: `run: ${state.runId}`}),
      element("span", {className: "command-fact", text: `mode: ${state.mode}`}),
      element("span", {
        className: "command-fact", text: `warnings: ${state.warningCount}`,
      }),
    );
    for (const name of state.controls) {
      controls.append(element("span", {className: "command-control", text: name}));
    }
    for (const record of state.records) {
      history.append(element("li", {className: "command-record"}, [
        element("strong", {text: record.kind}),
        element("span", {className: "command-meta", text: record.facts.join(" · ")}),
      ]));
    }
  }

  function refusalCode(payload) {
    const code = payload && payload.error && payload.error.code;
    return typeof code === "string" && ERROR_LABELS[code] ? code : "store_error";
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
      state.mode = safeMode(run && run.run && run.run.mode);
      state.phase = "ready";
      state.records = projectRecords(run && run.records);
      state.runId = runId;
      state.warningCount = run && Array.isArray(run.warnings) ? run.warnings.length : 0;
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
      state.mode = "unknown";
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
    if (!state.runId) return;
    state.phase = "stale";
    status.textContent = "Connection lost. Showing the last authoritative facts.";
    render();
  });
  window.addEventListener("conduct:connected", () => {
    if (state.runId) refreshSelectedRun(state.runId);
  });
})();
