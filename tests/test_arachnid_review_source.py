"""A second task can cite only a checked, accepted patch from this project."""
import json
from pathlib import Path

import pytest

from tests.desk_node import run_js

PROJECT = "a" * 32
MODULE = {"source": "arachnid-review-source.js"}
SCRIPT = """
const trace = [];
async function readJson(url) {
  trace.push(url);
  if (url === "/command/project") {
    return {project_id: d.switch && trace.length > 1 ? "b".repeat(32) : d.project,
      mode: d.mode || "active", hub_origin: null, demo: false};
  }
  if (url === "/command/runs/incomplete") return {...d.run, warnings: ["damaged"]};
  if (url === "/command/runs/first") {
    if (d.replaced && trace.filter(t => t === url).length > 1) {
      return {...d.run, warnings: ["replaced"]};
    }
    return d.run;
  }
  if (url === "/command/runs/first/steps/repair-counter/actions/action-first-2") return d.attempt;
  throw Error(url);
}
const result = await source.findReviewSource({projectId: d.project, runIds: d.ids, readJson,
  taskForRun: () => d.expectedTask || "one",
  valid: () => !d.cancelAt || trace.length < d.cancelAt});
console.log(JSON.stringify({result, trace}));
"""


def source_rows():
    attempt = json.loads((Path(__file__).parent / "fixtures" / "atlas-accepted-native.json")
                         .read_text(encoding="utf-8"))
    binding = attempt["tests"]["protocol"]["binding"]
    req = dict(run_id="first", node_id="repair-counter", action_id=binding["action"],
               instance_id="maker", attempt_id=binding["attempt"], capability="dispatch",
               run_authorization_id=binding["grant"],
               run_authorization_digest=binding["grant_digest"],
               arguments={"profile": "implement-patch-v1"})
    digest = "sha256:" + "1" * 64
    graph = {"nodes": [
        {"node_id": "repair-counter", "kind": "task", "instance_id": "maker",
         "verifier_instance_id": "checker", "capability": "dispatch",
         "arguments": {"profile": "implement-patch-v1"}},
        {"node_id": "accept", "kind": "gate", "gate_id": "accept-this"},
    ], "edges": [{"from_node": "repair-counter", "condition": "on_succeeded",
                  "to_node": "accept"}]}
    run = {"run": {"run_id": "first", "config_digest": digest},
           "task": {"id": "one", "unreadable": False}, "warnings": [],
           "config": {"task": {"id": "one"}, "instances": [
               {"id": "maker", "adapter": "codex"}, {"id": "checker", "adapter": "codex"}]},
           "graph": {"definition": graph}}
    seal = dict(kind="attempt_seal", action_id=req["action_id"], attempt_id=req["attempt_id"],
                instance_id="maker", node_id=req["node_id"], checker_instance_id="checker",
                checker_adapter_id="codex", snapshot_digest=attempt["manifest_digest"],
                digest="sha256:" + "2" * 64, test_report_digest="sha256:" + "3" * 64,
                evidence_id="seal", authorization_id=binding["grant"],
                authorization_digest=binding["grant_digest"])
    proof = dict(kind="verification", verifier_instance_id="checker", verified_by="codex",
                 verification="verified", attempt_seal_digest=seal["digest"],
                 accept_manifest_digest=seal["snapshot_digest"], evidence_id="review")
    records = [("action_request", req), ("evidence", seal), ("evidence", proof),
        ("action_result", dict(
        action_id=req["action_id"], attempt_id=req["attempt_id"], instance_id="maker",
        evidence_refs=["review"], outcome="succeeded")), ("decision", dict(
            action="approve", gate_id="accept-this", receipt_id="accept-1", config_digest=digest)),
        ("run_terminal", dict(state="complete", terminal_id="terminal-1",
                              settled_nodes=["repair-counter", "accept"]))]
    run["records"] = [{"record_type": t, "record": {"run_id": "first", **r}} for t, r in records]
    return {"project": PROJECT, "ids": ["incomplete", "first"], "run": run, "attempt": attempt}


def test_recall_project_bound_native_review_order_without_private_command_or_new_action():
    response = run_js(SCRIPT, MODULE, source_rows())
    result = response["result"]
    assert result["steps"] == ["apply_patch", "run_tests", "independent_check", "result_gate"]
    assert result["checker"] == {"instanceId": "checker", "adapter": "codex"}
    assert result["doer"] == {"instanceId": "maker", "adapter": "codex"}
    assert result["tests"] == {"runner": "python-unittest-v1", "total": 3,
                               "failures": 0, "errors": 0, "skipped": 0}
    assert (result["projectId"], result["runId"], result["taskId"]) == (
        PROJECT, "first", "one")
    assert (result["actionId"], result["attemptId"]) == ("action-first-2", "attempt-action-first-2")
    assert (result["receiptId"], result["terminalId"]) == ("accept-1", "terminal-1")
    assert result["snapshot"] == source_rows()["attempt"]["manifest_digest"]
    assert response["trace"] == [
        "/command/project", "/command/runs/incomplete", "/command/runs/first",
        "/command/runs/first/steps/repair-counter/actions/action-first-2", "/command/project",
    ]


@pytest.mark.parametrize(("target", "key", "value"), [
    ("request", "attempt_id", "other"), ("request", "run_authorization_id", "unrelated"),
    ("result", "outcome", "failed"), ("gate", "action", "reject"),
    ("gate", "gate_id", "unrelated"), ("terminal", "state", "stalled"),
    ("terminal", "settled_nodes", ["accept"]), ("attempt", "outcome", "failed"),
    ("attempt", "node_id", "unrelated"), ("tests", "source", "external"),
    ("protocol", "status", "failed"), ("checker", "instance_id", "maker"),
    ("checker", "adapter_id", "other"), ("outer", "switch", True), ("outer", "cancelAt", 3),
    ("attempt", "manifest_digest", "sha256:" + "f" * 64), ("result", "evidence_refs", []),
    ("seal", "test_report_digest", None), ("proof", "attempt_seal_digest", "sha256:" + "4" * 64),
    ("binding", "grant", "another-valid-grant"),
    ("outer", "expectedTask", "elsewhere"),
])
def test_reject_mismatch_and_unsettled_source(target, key, value):
    data = source_rows()
    req, seal, proof, result, gate, terminal = (row["record"] for row in data["run"]["records"])
    attempt = data["attempt"]
    targets = dict(outer=data, request=req, result=result, gate=gate, terminal=terminal,
                   seal=seal, proof=proof,
                   attempt=attempt, checker=attempt["verdict"], tests=attempt["tests"],
                   protocol=attempt["tests"]["protocol"],
                   binding=attempt["tests"]["protocol"]["binding"])
    targets[target][key] = value
    assert run_js(SCRIPT, MODULE, data)["result"] is None


@pytest.mark.parametrize("change", [
    "approval_before_result", "duplicate", "ambiguous_gate", "intermediate_gate", "later_action",
])
def test_unordered_or_ambiguous_completion_is_no_source(change):
    data = source_rows()
    rows = data["run"]["records"]
    if change == "approval_before_result":
        rows[-3], rows[-2] = rows[-2], rows[-3]
    elif change == "duplicate":
        rows.insert(0, rows[0])
    elif change == "ambiguous_gate":
        nodes = data["run"]["graph"]["definition"]["nodes"]
        nodes.append(dict(nodes[-1]))
    elif change == "intermediate_gate":
        graph = data["run"]["graph"]["definition"]
        graph["edges"].append(dict(from_node="accept", to_node="publish", condition="on_approved"))
    else:
        new = {**rows[0]["record"], "action_id": "other-action", "attempt_id": "other-attempt"}
        rows.insert(-1, {"record_type": "action_request", "record": new})
    assert run_js(SCRIPT, MODULE, data)["result"] is None


def test_unidentified_archive_rechecks_source_after_native_attempt_read():
    data = {**source_rows(), "project": None, "mode": "view"}
    response = run_js(SCRIPT, MODULE, data)
    assert response["result"]["actionId"] == "action-first-2"
    assert response["trace"].count("/command/runs/first") == 2
    assert run_js(SCRIPT, MODULE, {**data, "replaced": True})["result"] is None
    assert run_js(SCRIPT, MODULE, {**data, "mode": "active"})["result"] is None
