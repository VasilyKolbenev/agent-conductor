"use strict";
// Human write callbacks and a serial read queue; no read can create authority.
import {automationDraft, automationEligible, automationWriteReadBack, previewRequest, projectAutomation,
  projectAutomationPreview} from "./studio-automation-model.js";

class AutomationFlow {
  constructor(door) {
    this.door = door; this.epoch = 0; this.busy = false; this.queued = false;
    this.stop = null; this.detail = null; this.operation = 0; this.held = new Map();
    this.value = {runId: null, phase: "empty", view: null, draft: null,
      preview: null, pending: false, request: null, notice: ""};
  }
  publish(patch, redraw = true) {
    this.value = {...this.value, ...patch};
    if (redraw) this.door.changed();
  }
  current() {
    return this.door.ready() && this.value.runId === this.door.selected()
      && automationEligible(this.detail);
  }
  retire() {
    this.epoch += 1; this.queued = false;
    if (this.stop) this.stop.abort();
  }
  sync(detail) {
    const id = automationEligible(detail) ? detail.run.run_id : null;
    this.detail = detail;
    if (id !== this.value.runId) {
      this.retire(); this.operation += 1;
      if (this.value.runId) this.held.set(this.value.runId, {...this.value,
        pending: false, preview: null, notice: this.value.request ? "unknown" : this.value.notice});
      const prior = this.held.get(id);
      this.publish({runId: id, phase: "empty", view: null,
        draft: id ? automationDraft(detail) : null, request: null, notice: "", ...prior,
        pending: false, preview: null}, false);
    }
    if (id && this.current()) return this.refresh();
    this.door.changed();
  }
  disconnect() {
    this.retire(); this.operation += 1;
    this.publish({phase: "disconnected", preview: null, pending: false,
      notice: this.value.request ? "unknown" : "disconnected"});
  }
  clear() {
    if (this.value.runId) this.held.set(this.value.runId, {...this.value,
      pending: false, preview: null, notice: this.value.request ? "unknown" : this.value.notice});
    this.retire(); this.operation += 1; this.detail = null;
    this.publish({runId: null, phase: "empty", view: null, draft: null,
      preview: null, pending: false, request: null, notice: ""}, false);
  }
  refresh() {
    if (!this.current()) return;
    this.epoch += 1; this.queued = true;
    return this.pump();
  }
  async pump() {
    if (this.busy || !this.queued || !this.current()) return;
    this.busy = true; this.queued = false;
    const asked = this.epoch, runId = this.value.runId;
    this.stop = this.door.stop(); this.publish({phase: "loading"});
    let view = null;
    try { view = projectAutomation(await this.door.read(runId, this.stop), this.detail); }
    catch (_error) { /* Failed reads never turn an unknown write into success. */ }
    if (asked === this.epoch && runId === this.value.runId && this.current()) {
      this.publish({phase: view ? "ready" : "failed", view: view || this.value.view});
      if (view) this.readBack(view);
    }
    this.busy = false; this.stop = null;
    if (this.queued) return this.pump();
  }
  readBack(view) {
    const request = this.value.request;
    if (!request) return;
    const found = automationWriteReadBack(request, view, this.detail);
    if (found) this.publish({request: null, preview: null, notice: "recorded"});
  }
  edit(name, text, nodeId = null, redraw = true) {
    if (!this.value.draft || this.value.pending || this.value.request) return;
    const draft = this.value.draft;
    if (nodeId !== null) {
      if (!["timeout_seconds", "max_attempts"].includes(name)) return;
      this.publish({draft: {...draft, node_limits: draft.node_limits.map((row) =>
        row.node_id === nodeId ? {...row, [name]: text} : row)}, preview: null}, redraw);
    } else if (["actor", "max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"].includes(name)) {
      this.publish({draft: {...draft, [name]: text}, preview: name === "actor" ? this.value.preview : null}, redraw);
    }
  }
  async preview() {
    if (!this.current() || this.value.pending || this.value.request) return;
    const body = previewRequest(this.value.draft);
    if (!body) { this.publish({notice: "invalid"}); return; }
    const asked = ++this.operation, runId = this.value.runId;
    this.publish({pending: true, preview: null, notice: "previewing"});
    let answer = null;
    await this.door.write("automationPreview", runId, body, (result) => { answer = result; },
      (result) => { answer = result; });
    if (asked !== this.operation || runId !== this.value.runId) return;
    const value = answer?.status === "accepted" && this.current()
      ? projectAutomationPreview(answer.payload, this.detail) : null;
    this.publish({pending: false, preview: value, notice: value ? "review" : "preview_failed"});
  }
  authorize() {
    if (!this.current() || this.value.pending || this.value.request || !this.value.preview
        || this.value.phase !== "ready" || !this.value.draft.actor.trim()) return;
    const preview = this.value.preview;
    const body = {authorization_id: this.door.id("authorization"),
      preview_digest: preview.preview_digest, authorized_by: this.value.draft.actor,
      terms: preview.terms, supersedes: this.value.view.authorization?.authorization_id || null};
    return this.send({target: "automationAuthorize", body});
  }
  control(action) {
    if (!this.current() || this.value.pending || this.value.request || this.value.phase !== "ready"
        || !["pause", "resume", "revoke"].includes(action) || !this.value.draft.actor.trim()) return;
    const view = this.value.view, grant = view?.authorization;
    if (!grant || ["revoked", "expired", "complete"].includes(view.state)) return;
    return this.send({target: "automationControl", body: {control_id: this.door.id("control"),
      authorization_id: grant.authorization_id, authorization_digest: grant.authorization_digest,
      action, actor: this.value.draft.actor, expected_control_id: view.control?.control_id || null}});
  }
  retry() {
    if (!this.current() || this.value.pending || !this.value.request) return;
    return this.send(this.value.request);
  }
  async send(request) {
    const asked = ++this.operation, runId = this.value.runId;
    this.publish({pending: true, request, notice: "writing"});
    let answer = null;
    await this.door.write(request.target, runId, request.body, (result) => { answer = result; },
      (result) => { answer = result; });
    if (asked !== this.operation || runId !== this.value.runId) return;
    this.publish({pending: false, notice: answer?.status === "refused" ? "refused" : "unknown",
      request: answer?.status === "refused" ? null : request});
    if (this.current()) {
      this.door.refreshRun(runId);
      await this.refresh();
    }
  }
}

export function automationFlow(door) {
  const flow = new AutomationFlow(door);
  return {snapshot: () => flow.value, ...Object.fromEntries(
    ["sync", "clear", "disconnect", "refresh", "edit", "preview", "authorize", "control", "retry"]
      .map((name) => [name, flow[name].bind(flow)]))};
}
