"""A recollection belongs to the exact operator-approved document in a completed task."""
from tests.desk_node import run_js


def test_operator_procedure_requires_matching_task_document_actor_and_final_approval():
    body = """
const digest = "sha256:" + "1".repeat(64);
const note = {schema_version: 1, run_id: "first", task_id: "one", actor_id: "actor-1",
  reviewer: "Ира", performer: "", outcome: "Готово",
  checks: [{step: "Сверить итоги", result: "Все суммы сошлись"}]};
const records = (type, value) => ({record_type: type, record: {run_id: "first", ...value}});
const detail = {task: {id: "one", title: "Смета", unreadable: false},
  config: {task: {id: "one"}}, run: {run_id: "first", config_digest: digest}, warnings: [],
  graph: {definition: {nodes: [{kind: "gate", node_id: "operator-review",
    gate_id: "gate-operator-review"}], edges: []}},
  records: [records("artifact", {artifact_ref: "operator-review-procedure-v1", artifact_id: "doc",
    media_type: "text/plain", content: JSON.stringify(note)}),
    records("decision", {action: "approve", gate_id: "gate-operator-review", receipt_id: "approve",
      config_digest: digest, actor: "actor-1", scope_refs: ["doc"]}),
    records("run_terminal", {state: "complete", terminal_id: "end",
      settled_nodes: ["operator-review"]})]};
const read = detail => manual.manualReviewSource(detail, "first", "one", "a".repeat(32));
const doc = detail.records[0].record;
const encoded = new TextEncoder().encode(JSON.stringify(doc, Object.keys(doc).sort()));
const hash = Buffer.from(await crypto.subtle.digest("SHA-256", encoded)).toString("hex");
detail.records[1].record.reason = "Принята запись выполненных проверок. sha256:" + hash;
const source = await read(detail);
const breaks = [
  d => { d.records[1].record.action = "reject"; }, d => { d.records[1].record.actor = "other"; },
  d => { d.records[1].record.scope_refs = ["else"]; }, d => { d.task.id = "two"; },
  d => { d.records.reverse(); }, d => { d.records[0].record.source_action_id = "provider"; },
  d => { d.records.pop(); }, d => { d.graph.definition.nodes = []; },
  d => { d.records[0].record.content = "{"; }, d => { d.records[0].record.run_id = "other"; },
];
breaks.push(d => { d.records[0].record.content = d.records[0].record.content.replace(
  "Все суммы сошлись", "Другое наблюдение"); });
const invalid = await Promise.all(breaks.map(change => { const copy = structuredClone(detail);
  change(copy); return read(copy); }));
console.log(JSON.stringify({source, invalid}));
"""
    got = run_js(body, {"manual": "arachnid-manual-review.js"})
    assert got["source"]["kind"] == "operator"
    assert got["source"]["author"] == "Ира"
    assert got["source"]["documentId"] == "doc"
    assert got["source"]["steps"] == [{"label": "Сверить итоги", "result": "Все суммы сошлись"}]
    assert got["invalid"] == [None] * 11
