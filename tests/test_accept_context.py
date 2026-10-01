"""Acceptance GET proves journal facts in view mode, never a live tree or Git permission."""
from dataclasses import replace
import json
import os
from types import SimpleNamespace

import pytest

from conductor.command.accept_context import read_context
from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import ActionProposal
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_template import GraphTemplate, TemplateNode
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.queue_store import Dropped, QueueEntry
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.run_terminal import RunTerminal
from conductor.command.seed_record import SeedRecord, write_seed
from conductor.command.task_contracts import TaskRecord
from conductor.ownership import data_root
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import PORT, TOKEN, get_headers, ids
from tests.test_command_run_store import CONFIG, NOW, a_run, an_action, a_result, a_decision, evidence
from tests.test_seed_record import a_git_seed

RUN, TASK, SCOPE = "run-001", "task-one", "scope-one"
TREE, MANIFEST = "sha256:" + "a" * 64, "sha256:" + "b" * 64
PATH = f"/command/runs/{RUN}/accept"


def create_run(api, run_id=RUN, task=TASK, scope=SCOPE, *, created_at=NOW, workflow=None):
    config = dict(CONFIG)
    if task is not None:
        config["task"] = {"id": task, "work_scope": scope}
    if workflow is not None:
        config["workflow"] = {"id": workflow[0], "revision": workflow[1]}
    api._store.create_run(a_run(run_id=run_id, created_at=created_at,
                              config_digest=snapshot_digest(config)), config)
    return config


def prepared(tmp_path, *, files=True, workflow=None, finish=True, seed_record=None, proof_extra=None):
    store = RunStore(tmp_path)
    def no_git(*args, **kwargs):
        raise AssertionError("GET acceptance must not ask Git")
    api = CommandApi(store, AdapterRegistry([FakeAdapter()]), session=CommandSession(PORT, TOKEN),
                     budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
                     publish_run=lambda _: None, project_git=no_git,
                     identity=ProjectIdentity("a" * 32, None, False, "view", None, None))
    api._tasks.create_task(TaskRecord(TASK, "Reviewed task", SCOPE, NOW))
    config = create_run(api, workflow=workflow)
    node = GraphNode("do", "task", "Work", instance_id="claude-dev", capability="dispatch",
                     arguments={"handoff": "packet-001"})
    nodes = ((GraphNode("start", "gate", "Start", gate_id="start-gate"), node) if files else ()) + (
        GraphNode("finish", "gate", "Accept", gate_id="release"),)
    plan = GraphDefinition("graph-one", RUN, NOW, nodes,
                           (GraphEdge("start", "do", "on_approved"),) if files else ())
    store.append(plan)
    if files:
        store.append(a_decision(receipt_id="start-approved", gate_id="start-gate",
                                config_digest=snapshot_digest(config)))
        write_seed(tmp_path, seed_record or SeedRecord.from_dict(a_git_seed(task_id=TASK, work_scope=SCOPE)))
        proposal = ActionProposal("proposal-one", RUN, "attempt-001", "claude-dev", "dispatch",
                                  node.payload(), ("src",), "owner", NOW, 900, "Reviewed",
                                  snapshot_digest(config), node_id="do")
        store.append(proposal)
        store.append(an_action(node_id="do", idempotency_key="dispatch-proposal-one",
                               preview_digest=proposal.preview_digest))
        store.append(evidence(kind="verification", uri="verification/action-001", digest=TREE,
                              verification="verified", verified_by="checker", verified_at=NOW,
                              verifier_instance_id="independent-checker",
                              extra=({"work_tree_digest": TREE, "accept_manifest_digest": MANIFEST}
                                     if proof_extra is None else proof_extra)))
        store.append(a_result())
    if finish:
        store.append(a_decision(config_digest=snapshot_digest(config)))
        store.append(RunTerminal("ended", RUN, plan.graph_id, "complete",
                                 tuple(node.node_id for node in nodes), (), NOW))
    return api


def get(api):
    return api.handle("GET", PATH, get_headers())


def test_view_get_confirms_only_journal_without_work_or_git_reads_or_writes(tmp_path, monkeypatch):
    api = prepared(tmp_path)
    from conductor.command.adapters import work_seed
    monkeypatch.setattr(work_seed, "capture_work_tree", lambda *a, **k: pytest.fail("work walk"))
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    answer = get(api)
    assert answer.status == 200
    assert answer.payload == {"kind": "files", "basis": {
        "final_gate": "release", "decided_at": "2026-08-11T09:02:00Z",
        "verified_action": "action-001", "accept_manifest_digest": MANIFEST,
        "pending_checks": ["snapshot_integrity", "current_work_tree"]},
        "commit": None, "push": None, "pull_request": None}
    assert not (tmp_path / "work").exists()
    assert before == {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_documents_need_neither_seed_nor_a_work_folder(tmp_path):
    answer = get(prepared(tmp_path, files=False))
    assert answer.status == 200 and answer.payload["kind"] == "documents"
    assert answer.payload["basis"]["final_gate"] == "release"
    assert "pending_checks" not in answer.payload["basis"]


def test_later_empty_run_and_unbound_legacy_are_not_later_work(tmp_path):
    api = prepared(tmp_path)
    create_run(api, "later-empty", created_at="2026-08-12T09:00:00Z")
    create_run(api, "legacy", task=None)
    assert get(api).payload["basis"].get("refused") is None
    api._store.append(an_action(run_id="later-empty"))
    assert get(api).payload["basis"] == {"refused": "superseded_by_later_run"}


@pytest.mark.parametrize("source", ["request", "queue", "driver"])
def test_pending_request_queue_and_driver_each_hold_the_task(tmp_path, source):
    api = prepared(tmp_path)
    create_run(api, "older", created_at="2026-08-10T09:00:00Z")
    if source == "request":
        api._store.append(an_action(run_id="older"))
    elif source == "queue":
        api._queue.store.write((QueueEntry("older", "start", NOW, "owner", None,
                                          Dropped("terms_changed", NOW)),))
    else:
        api._policy.driver = SimpleNamespace(slot=lambda: SimpleNamespace(
            active_run_id="older", inflight_run_id=None, holding_new_work=False))
    assert get(api).payload["basis"] == {"refused": "task_run_active"}


@pytest.mark.parametrize("damage", ["journal", "binding", "missing", "shared-scope"])
def test_inventory_never_drops_an_ambiguous_or_foreign_owner(tmp_path, damage):
    api = prepared(tmp_path)
    create_run(api, "neighbor", task="other", scope=SCOPE if damage == "shared-scope" else "other")
    root = api._store.run_path("neighbor")
    if damage == "journal":
        (root / "records.jsonl").write_bytes(b"not-json\n")
    elif damage == "binding":
        (root / "config.json").write_text("{}", encoding="utf-8")
    elif damage == "missing":
        (root / "run.json").unlink()
    answer = get(api)
    assert answer.status == 409 and answer.payload["error"]["code"] in {"run_corrupt", "store_error"}


def test_other_known_scope_does_not_block_and_wrong_host_or_verb_still_refuses(tmp_path):
    api = prepared(tmp_path)
    create_run(api, "other", task="other", scope="other")
    api._store.append(an_action(run_id="other"))
    assert get(api).payload["basis"].get("refused") is None
    assert api.handle("GET", PATH, get_headers("foreign:7802")).status == 403
    assert api.handle("POST", PATH, get_headers()).status == 405


def test_frozen_workflow_revision_is_loaded_and_missing_revision_never_uses_latest(tmp_path):
    api = prepared(tmp_path, files=False, workflow=("workflow-one", 1))
    template = GraphTemplate("workflow-one", 1, "Frozen title",
                             (TemplateNode("finish", "gate", "Accept", gate_id="release"),))
    api._templates.save(template)
    api._templates.save(replace(template, revision=2, title="Latest title"))
    assert read_context(api, RUN).template.title == "Frozen title"
    api._templates.revision_path("workflow-one", 1).unlink()
    assert get(api).status != 200


def commit_record():
    return {"schema_version": 1, "acceptance_id": "acc-" + "a" * 32,
            "run_id": RUN, "task_id": TASK, "kind": "files", "base_commit": "a" * 40,
            "commit": "b" * 40, "tree": "c" * 40, "branch": "conduct/run-001",
            "accept_digest": TREE, "accept_manifest_digest": MANIFEST, "file_count": 1,
            "requested_by": "owner", "recorded_at": NOW}


@pytest.mark.parametrize("damage", [None, "foreign", "secret", "hardlink"])
def test_durable_records_are_bound_and_cannot_disclose_remote_credentials(tmp_path, damage):
    api = prepared(tmp_path)
    folder = data_root(tmp_path) / "accept" / RUN
    folder.mkdir(parents=True)
    record = commit_record()
    if damage == "foreign":
        record["task_id"] = "foreign-task"
    path = folder / "commit.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    if damage == "secret":
        push = {"schema_version": 1, "acceptance_id": record["acceptance_id"], "remote": "origin",
                "push_url": "https://test-secret@github.com/owner/repo", "remote_repo": "owner/repo",
                "ref": "refs/heads/conduct/run-001", "commit": record["commit"], "push_digest": TREE,
                "remote_oid": record["commit"], "requested_by": "owner", "pushed_at": NOW}
        (folder / "push.json").write_text(json.dumps(push), encoding="utf-8")
    elif damage == "hardlink":
        os.link(path, folder / "alias")
    answer = get(api)
    if damage is None:
        assert answer.status == 200 and answer.payload["commit"] == record
    else:
        assert answer.status == 409 and answer.payload["error"]["code"] == "run_corrupt"
        assert "test-secret" not in json.dumps(answer.payload)
