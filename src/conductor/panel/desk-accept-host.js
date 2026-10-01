"use strict";
// Acceptance belongs to the selected task/run, not to whether its centre panel is open.
// The server owns eligibility and Git facts; this host only presents exact preview terms.
import {element} from "./command-view.js";
import {localize, MESSAGES} from "./studio-i18n.js";
import {path} from "./desk-transport.js";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const text = (locale, key, params) => localize({locale: locale()}, key, params);
const word = (locale, kind, value) => text(locale,
  Object.hasOwn(MESSAGES, `desk.accept.${kind}.${value}`)
    ? `desk.accept.${kind}.${value}` : "desk.accept.other");
const line = (label, value) => element("p", {className: "desk-accept__fact"}, [
  element("strong", {text: label}), document.createTextNode(` ${value ?? "—"}`)]);

export function createAcceptHost({door, binding, locale, onChange, onForeign, openDetails}) {
  let selected = null, task = null, detailStamp = null, epoch = 0, disposed = false;
  let facts = null, preview = null, confirming = false, phase = "idle", error = null;
  let branch = "", title = "", documents = null, actor = null, optionsRevision = 0;
  let availableDocs = [];
  const pult = element("section", {className: "desk-accept"});
  const detail = element("section", {className: "desk-accept desk-accept--detail"});
  function current(ticket, write = false) {
    const now = binding();
    return !disposed && ticket === epoch && !now.foreign && now.ready
      && now.runId === selected && now.taskId === task
      && (!write || (now.mode === "active" && now.connection === "open"));
  }
  function reset() {
    facts = preview = null; confirming = false; phase = "idle"; error = null;
    branch = title = ""; documents = null; availableDocs = []; optionsRevision += 1;
  }
  function notice(code, reason) {
    if (reason && Object.hasOwn(MESSAGES, `accept.reason.${reason}`)) {
      return text(locale, `accept.reason.${reason}`);
    }
    return text(locale, Object.hasOwn(MESSAGES, `error.${code}`)
      ? `error.${code}` : "desk.accept.failed");
  }
  async function read() {
    if (selected === null || !current(epoch)) return;
    const ticket = epoch, runId = selected;
    phase = "reading"; error = null; preview = null; confirming = false;
    void Promise.resolve().then(() => { if (current(ticket)) onChange(); });
    try {
      const answer = await door.readJson(path.accept(runId));
      if (!current(ticket)) return;
      facts = answer; phase = "ready";
    } catch (failure) {
      if (!current(ticket)) return;
      if (failure?.message === "project_mismatch") { onForeign(); return; }
      facts = null; phase = "failed"; error = notice(failure?.message);
    }
    onChange();
  }
  function sync(desk) {
    if (disposed) return;
    const detail = desk.run.detail;
    const value = desk.run.phase === "ready" &&
      detail?.config?.task?.id === desk.taskId ? detail?.run?.run_id ?? null : null;
    const records = detail?.records ?? [];
    const last = records.at(-1);
    const stamp = value === null ? null : `${detail?.run?.status ?? ""}/${records.length}/`
      + `${last?.sequence ?? last?.record_id ?? last?.record_type ?? ""}`;
    if (value !== selected || desk.taskId !== task || stamp !== detailStamp) {
      epoch += 1; selected = value; task = desk.taskId; detailStamp = stamp; reset();
      if (value !== null) {
        const nodes = desk.run.detail?.graph?.definition?.nodes ?? [];
        const refs = new Set(nodes.filter((node) => node.capability === "review")
          .map((node) => node.arguments?.result_artifact_ref).filter(Boolean));
        if (desk.run.detail?.config?.workflow?.workflow_id === "desk-starter-docs") {
          for (const ref of ["artifact-brief", "artifact-plan", "artifact-ideas",
            "artifact-scheme"]) refs.add(ref);
        }
        const artifacts = desk.run.detail?.records ?? [];
        availableDocs = [...refs].filter((ref) => artifacts.some((row) =>
          row.record_type === "artifact" && row.record?.artifact_ref === ref));
      }
      if (value !== null) void read();
    }
    if (actor !== desk.actor) confirming = false;
    actor = desk.actor;
  }
  async function makePreview() {
    const ticket = epoch, runId = selected;
    if (!current(ticket, true) || phase !== "ready" || !facts || facts.basis?.refused
        || facts.commit || !actor) return;
    const body = {};
    if (branch.trim()) body.branch = branch.trim();
    if (title.trim()) body.title = title.trim();
    if (documents !== null) body.documents = documents;
    const revision = optionsRevision;
    phase = "previewing"; preview = null; confirming = false; error = null; onChange();
    let answer;
    try { answer = await door.submit("acceptPreview", runId, body); }
    catch (_failure) { answer = {status: "unknown"}; }
    if (!current(ticket) || revision !== optionsRevision) return;
    if (answer.code === "project_mismatch") { onForeign(); return; }
    const value = answer.payload?.accept;
    if (answer.status === "accepted" && value?.run_id === runId
        && value.task_id === task && DIGEST.test(value.accept_digest)) {
      preview = value; phase = "preview";
      availableDocs = [...new Set([...availableDocs,
        ...(value.documents ?? []).map((row) => row.artifact_ref)])];
    } else {
      phase = answer.status === "unknown" ? "unknown" : "ready";
      error = answer.status === "unknown" ? text(locale, "desk.accept.unknown_preview")
        : notice(answer.code, answer.payload?.error?.detail?.reason);
    }
    onChange();
  }
  async function commit() {
    const ticket = epoch, runId = selected, digest = preview?.accept_digest;
    const signer = actor;
    if (!confirming || phase !== "preview" || !DIGEST.test(digest)
        || !current(ticket, true) || !signer) return;
    phase = "committing"; confirming = false; error = null; onChange();
    let answer;
    try { answer = await door.submit("acceptCommit", runId,
      {accept_digest: digest, actor: signer}); }
    catch (_failure) { answer = {status: "unknown"}; }
    if (!current(ticket)) return;
    if (answer.code === "project_mismatch") { onForeign(); return; }
    if (answer.status === "accepted" && answer.payload?.commit?.accept_digest === digest) {
      facts = {...facts, commit: answer.payload.commit};
      phase = "ready"; preview = null;
    } else {
      phase = answer.status === "unknown" ? "unknown" : "ready";
      preview = null;
      error = answer.status === "unknown" ? text(locale, "desk.accept.unknown_commit")
        : notice(answer.code, answer.payload?.error?.detail?.reason);
    }
    onChange();
  }
  function button(label, action, disabled = false, where = "detail") {
    const node = element("button", {type: "button", text: text(locale, label),
      "data-focus-key": `accept:${where}:${label}`});
    node.disabled = disabled; node.addEventListener("click", action); return node;
  }
  function editField(key, value, set) {
    const input = element("input", {type: "text", value, autocomplete: "off",
      "data-focus-key": key, "data-focus-value": "state"});
    input.disabled = phase === "committing";
    input.addEventListener("input", () => {
      if (phase === "committing") return;
      set(input.value); optionsRevision += 1; preview = null;
      confirming = false; if (phase === "preview" || phase === "previewing") phase = "ready";
    });
    return element("label", {className: "desk-accept__field"}, [
      element("span", {text: text(locale, key)}), input]);
  }
  function previewContent(target) {
    const value = preview;
    target.append(line(text(locale, "desk.accept.base"), value.base?.commit),
      line(text(locale, "desk.accept.branch"), value.branch),
      line(text(locale, "desk.accept.author"),
        `${value.author?.name ?? ""} <${value.author?.email ?? ""}>`),
      line(text(locale, "desk.accept.digest"), value.accept_digest),
      element("h4", {text: text(locale, "desk.accept.files")}));
    const files = element("ul");
    for (const row of value.files ?? []) files.append(element("li", {
      text: `${word(locale, "state", row.state)} · ${row.path} · ${row.mode}`}));
    target.append(files);
    if (value.skipped?.length) {
      target.append(element("h4", {text: text(locale, "desk.accept.skipped")}));
      for (const row of value.skipped) target.append(line(row.path,
        word(locale, "skip", row.reason)));
    }
    if (value.warnings?.length) target.append(line(text(locale, "desk.accept.warnings"),
      value.warnings.map((warning) => word(locale, "warning", warning)).join(", ")));
    target.append(element("h4", {text: text(locale, "desk.accept.message")}),
      element("pre", {text: value.message ?? ""}),
      element("h4", {text: text(locale, "desk.accept.patch")}),
      element("pre", {text: value.patch?.text ?? ""}));
    if (value.patch?.truncated) target.append(element("p", {
      text: text(locale, "desk.accept.truncated")}));
  }
  function draw(target, desk, full) {
    target.replaceChildren(element("h3", {text: text(locale, "desk.accept.heading")}));
    target.setAttribute("data-subject", `${task ?? "none"}/${selected ?? "none"}`);
    if (selected === null) { target.append(element("p", {
      text: text(locale, "desk.accept.no_run")})); return; }
    if (phase === "reading") target.append(element("p", {
      text: text(locale, "desk.accept.reading")}));
    if (facts?.commit) {
      target.append(line(text(locale, "desk.accept.branch"), facts.commit.branch),
        line(text(locale, "desk.accept.commit"), facts.commit.commit));
      return;
    }
    if (facts?.basis?.refused) target.append(element("p", {
      text: notice("accept_refused", facts.basis.refused)}));
    if (desk.mode === "view") target.append(element("p", {
      text: text(locale, "desk.run.view_blocked")}));
    if (error) target.append(element("p", {role: "status", text: error}));
    if (!full) {
      if (phase === "previewing" || phase === "committing") target.append(element("p", {
        text: text(locale, "desk.accept.working")}));
      if (phase === "unknown" || phase === "failed" || phase === "ready") {
        target.append(button("desk.accept.refresh", read, false, "pult"));
      }
      target.append(button("desk.accept.open", openDetails, !facts, "pult"));
      return;
    }
    if (phase === "unknown" || phase === "failed" || phase === "ready") {
      target.append(button("desk.accept.refresh", read));
    }
    if (!facts) return;
    if (facts.basis?.refused) {
      target.append(button("desk.accept.preview", makePreview, true));
      return;
    }
    if (facts.commit) return;
    if (full) {
      target.append(editField("desk.accept.branch", branch, (v) => { branch = v; }),
        editField("desk.accept.title", title, (v) => { title = v; }));
      if (availableDocs.length) {
        target.append(element("h4", {text: text(locale, "desk.accept.documents")}));
        for (const ref of availableDocs) {
          const check = element("input", {type: "checkbox",
            "data-focus-key": `accept:document:${ref}`});
          check.disabled = phase === "committing";
          check.checked = documents === null ? facts.kind === "documents"
            : documents.includes(ref);
          check.addEventListener("change", () => {
            if (phase === "committing") return;
            const selected = documents === null
              ? facts.kind === "documents" ? [...availableDocs] : [] : [...documents];
            documents = check.checked ? [...new Set([...selected, ref])]
              : selected.filter((item) => item !== ref);
            optionsRevision += 1; preview = null; confirming = false;
            phase = "ready"; onChange();
          });
          const shown = preview?.documents?.find((row) => row.artifact_ref === ref);
          target.append(element("label", {className: "desk-accept__choice"}, [check,
            document.createTextNode(shown?.path ?? ref)]));
        }
      }
    }
    const blocked = desk.mode !== "active" || !actor || !current(epoch, true);
    if (!actor) target.append(element("p", {text: text(locale, "desk.accept.actor")}));
    if (phase === "ready" || phase === "preview") {
      target.append(button("desk.accept.preview", makePreview, blocked));
    }
    if (phase === "previewing" || phase === "committing") target.append(element("p", {
      text: text(locale, "desk.accept.working")}));
    if (phase !== "preview" || !preview) return;
    previewContent(target);
    if (!confirming) target.append(button("desk.accept.review", () => {
      if (!current(epoch, true) || phase !== "preview") return;
      confirming = true; onChange();
    }, blocked));
    else target.append(element("p", {text: text(locale, "desk.accept.confirm_text", {
      digest: preview.accept_digest, actor})}),
      button("desk.accept.commit_action", commit, blocked),
      button("desk.accept.cancel", () => { confirming = false; onChange(); }));
  }
  function render(desk, open) {
    sync(desk);
    draw(pult, desk, false);
    if (open) draw(detail, desk, true);
  }
  function dispose() { disposed = true; epoch += 1; reset(); pult.remove(); detail.remove(); }
  return Object.freeze({pult, detail, render, dispose});
}
