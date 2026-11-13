"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";

const outcomes = ["succeeded", "failed", "cancelled", "rejected", "unknown", "verification_failed"];
const states = ["added", "modified", "deleted"];
const diffs = ["available", "base_unavailable", "binary", "too_large", "withheld"];
const verdicts = ["verified", "unavailable", "mismatch", "error", "rejected"];
const testStates = ["passed", "failed", "zero_tests", "timed_out", "truncated",
  "infrastructure_error"];
const text = (v) => typeof v === "string";
const count = (v) => Number.isSafeInteger(v) && v >= 0;
const digest = (v) => text(v) && /^sha256:[0-9a-f]{64}$/.test(v);
const tabs = ["diff", "tests", "verdict"];
const tr = (view, key, args) => localize(view, "atlas." + key, args);
const note = (value) => element("p", {className: "studio-hint", text: value});
export function atlasTestSummary(view, tests) {
  if (tests.status !== "recorded") {
    return tr(view, tests.status === "unavailable" ? "test_broken" : "test_absent");
  }
  const args = Object.fromEntries(["total", "failures", "errors", "skipped"]
    .map(key => [key, String(tests.summary?.[key] ?? "—")]));
  if (tests.source === "native") return tr(view, "test_" + tests.protocol.status)
    + (tests.summary ? " · " + tr(view, "native_total", args) : "");
  return tr(view, "test_total", args);
}

function counts(value) {
  return value && ["total", "failures", "errors", "skipped"].every(key => count(value[key]))
    && value.skipped <= value.total;
}

function validProtocol(p, row, owner) {
  const b = p?.binding;
  if (!p || p.version !== 1 || !b || b.run !== row.run_id || b.action !== row.action_id
      || b.attempt !== row.attempt_id || b.instance !== owner || !text(b.grant)
      || ![b.grant_digest, b.policy, b.toolpin, b.workspace_tree, b.work_modes].every(digest)
      || !p.policy || typeof p.policy !== "object"
      || !testStates.includes(p.status) || !Array.isArray(p.argv)
      || !p.argv.length || p.argv.length > 16
      || !p.argv.every(arg => text(arg) && arg.length <= 4096)
      || !text(p.cwd) || p.cwd.length > 1024
      || !["completed", "timed_out", "stopped", "not_started"].includes(p.process_status)
      || !(p.exit_code === null || Number.isSafeInteger(p.exit_code))
      || !text(p.output) || p.output.length > 65536 || !text(p.output_b64)
      || p.output_b64.length > 87384 || !digest(p.output_sha256)
      || p.output_stream !== "merged" || typeof p.truncated !== "boolean"
      || !(p.reason === null || text(p.reason))
      || !(p.counts === null || counts(p.counts))) return false;
  return p.status !== "passed" || p.process_status === "completed" && p.exit_code === 0
    && !p.truncated && p.counts?.total > p.counts?.skipped
    && !p.counts.failures && !p.counts.errors;
}

function validTests(t, row, owner) {
  if (!t || !["recorded", "not_recorded", "unavailable"].includes(t.status)
      || !Array.isArray(t.cases) || !t.cases.every(c => c && text(c.name) && text(c.path)
        && count(c.line) && (c.assertion === null || text(c.assertion)))) return false;
  if (t.status !== "recorded") return t.summary === null && t.source === null
    && t.protocol === undefined;
  if (t.source === "native") return validProtocol(t.protocol, row, owner)
    && (t.summary === null ? t.protocol.counts === null
      : counts(t.summary) && t.protocol.counts && ["total", "failures", "errors", "skipped"]
        .every(key => t.summary[key] === t.protocol.counts[key]));
  return t.source === "external" && counts(t.summary) && t.protocol === undefined;
}

function validFindings(rows) {
  return Array.isArray(rows) && rows.length >= 1 && rows.length <= 16 && rows.every(row => row
    && ["defect", "missing_requirement", "verification_gap"].includes(row.kind)
    && text(row.summary) && row.summary.length > 0 && row.summary.length <= 8192
    && (row.path === null ? row.line === null : text(row.path)
      && (row.line === null || count(row.line) && row.line > 0)));
}

export function matchesAtlasAttempt(row, request, step, run) {
  if (!row || row.run_id !== run || row.node_id !== step.nodeId
      || row.action_id !== request.action_id || row.attempt_id !== request.attempt_id
      || !(row.outcome === null || outcomes.includes(row.outcome))
      || !(row.manifest_digest === null || digest(row.manifest_digest))
      || !Array.isArray(row.files) || !validTests(row.tests, row, step.ownerId)) return false;
  if (row.files_total === null ? row.files.length !== 0
      : !count(row.files_total) || row.files_total < row.files.length) return false;
  if (row.verdict !== null && (!row.verdict || !verdicts.includes(row.verdict.status)
      || !text(row.verdict.adapter_id) || !text(row.verdict.instance_id)
      || row.verdict.instance_id !== step.verifierId || row.verdict.instance_id === step.ownerId)) {
    return false;
  }
  if (row.verdict?.status === "rejected" && (row.outcome !== "verification_failed"
      || !text(row.verdict.reason) || !validFindings(row.verdict.findings))) return false;
  return row.files.every(file => file && text(file.path) && states.includes(file.state)
    && diffs.includes(file.diff_status) && Array.isArray(file.lines)
    && file.lines.every(text) && (file.diff_status === "available" || !file.lines.length));
}

function button(label, attributes, action) {
  const node = element("button", {type: "button", text: label, ...attributes});
  node.addEventListener("click", action);
  return node;
}

// Prefer a case introduced by this exact patch. A definition is not a per-case pass receipt.
export function relatedAtlasCase(evidence) {
  return evidence.tests.cases.find(c => c.assertion && evidence.files.some(f => f.path === c.path
    && f.lines.some(line => line.startsWith("+") && !line.startsWith("+++")
      && line.slice(1).trimStart().startsWith("def " + c.name + "("))))
    || evidence.tests.cases.find(c => c.assertion) || evidence.tests.cases[0];
}

export function answerFor(view, tab, evidence) {
  if (tab === "tests") {
    const t = evidence.tests;
    const c = relatedAtlasCase(evidence);
    return atlasTestSummary(view, t)
      + (c ? " " + c.name + " · " + (c.assertion || tr(view, "no_assert")) : "");
  }
  if (tab === "verdict") {
    const verdict = evidence.verdict;
    const key = verdict?.status === "unavailable" ? "verifier_unavailable" : verdict?.status;
    return verdict ? tr(view, key) + " · " + verdict.instance_id : tr(view, "no_verdict");
  }
  return evidence.files_total === null ? tr(view, "no_files")
    : tr(view, "files", {n: String(evidence.files_total)})
      + (evidence.files.length ? " · " + evidence.files.map(file => file.path).join(", ") : "");
}

export function atlasDiff(body, view, data, choice, select) {
  if (data.files_total === null) { body.append(note(tr(view, "no_files"))); return; }
  body.append(element("strong", {text: tr(view, "files", {n: String(data.files_total)})}));
  if (data.files.length < data.files_total) body.append(note(tr(view, "partial",
    {shown: String(data.files.length), total: String(data.files_total)})));
  const file = data.files.find(f => f.path === choice.file) || data.files[0];
  if (!file) return;
  for (const f of data.files) {
    body.append(button(f.path, {className: "atlas-file", "aria-pressed": String(file === f),
      "data-focus": "atlas:file:" + f.path}, () => select({file: f.path})));
  }
  body.append(element("small", {text: tr(view, file.state)}));
  if (file.diff_status !== "available") {
    body.append(note(tr(view, file.diff_status)));
    return;
  }
  const lines = element("pre", {className: "atlas-diff", tabindex: "0",
    "aria-label": file.path, "data-atlas-diff": file.path});
  for (const line of file.lines) {
    const kind = line.startsWith("@@") ? "range" : line.startsWith("+") ? "add"
      : line.startsWith("-") ? "remove" : "context";
    lines.append(element("code", {"data-line": kind, text: line + "\n"}));
  }
  body.append(lines);
}

function tests(body, view, data, choice, select) {
  const t = data.tests;
  body.append(note(atlasTestSummary(view, t)));
  if (t.source === "native") {
    const p = t.protocol;
    body.append(element("h4", {text: tr(view, "protocol")}),
      element("pre", {className: "atlas-assert", "data-atlas-command": "",
        text: JSON.stringify(p.argv)}),
      note(tr(view, "protocol_cwd", {cwd: p.cwd})),
      note(tr(view, "protocol_exit", {code: String(p.exit_code ?? "—")})),
      note(tr(view, "protocol_stream")),
      element("pre", {className: "atlas-assert", "data-atlas-protocol": "", text: p.output}));
    if (p.reason) body.append(note(p.reason));
  }
  if (!t.cases.length) { body.append(note(tr(view, "no_cases"))); return; }
  const current = t.cases[choice.test] || relatedAtlasCase(data);
  body.append(element("h4", {text: tr(view, "case")}));
  body.append(element("strong", {text: current.name}),
    element("small", {text: current.path + ":" + current.line}));
  body.append(current.assertion ? element("pre",
    {className: "atlas-assert", text: current.assertion})
    : note(tr(view, "no_assert")));
  t.cases.forEach((c, index) => body.append(button(c.name,
    {className: "atlas-file", "aria-pressed": String(current === c),
      "data-focus": "atlas:test:" + index},
    () => select({test: index}))));
}

export function atlasInspector(body, view, data, choice, select) {
  const bar = element("div", {className: "atlas-tabs", role: "tablist",
    "aria-label": tr(view, "inspect")});
  tabs.forEach((tab, index) => {
    const b = button(tr(view, tab), {role: "tab", id: "atlas-tab-" + tab,
      "aria-controls": "atlas-tab-panel", "aria-selected": String(choice.tab === tab),
      tabindex: choice.tab === tab ? "0" : "-1", "data-atlas-tab": tab,
      "data-focus": "atlas:tab:" + tab}, () => select({tab}));
    b.addEventListener("keydown", event => {
      const order = {ArrowRight: (index + 1) % 3, ArrowLeft: (index + 2) % 3, Home: 0, End: 2};
      if (!Object.hasOwn(order, event.key)) return;
      event.preventDefault(); select({tab: tabs[order[event.key]]}, true);
    });
    bar.append(b);
  });
  const panel = element("div", {role: "tabpanel", id: "atlas-tab-panel",
    className: "atlas-artifacts", "aria-labelledby": "atlas-tab-" + choice.tab});
  body.append(bar, panel);
  if (choice.tab === "diff") atlasDiff(panel, view, data, choice, select);
  else if (choice.tab === "tests") tests(panel, view, data, choice, select);
  else {
    panel.append(element("strong", {text: answerFor(view, "verdict", data)}));
    if (data.verdict) panel.append(note(data.verdict.adapter_id));
    if (data.verdict?.status === "rejected") {
      panel.append(note(data.verdict.reason));
      for (const finding of data.verdict.findings) {
        panel.append(element("p", {"data-atlas-finding": "", text: finding.summary}));
        if (finding.path) panel.append(element("small", {text: finding.path
          + (finding.line === null ? "" : ":" + finding.line)}));
      }
    }
    if (data.manifest_digest) panel.append(element("code", {text: data.manifest_digest}));
  }
}
