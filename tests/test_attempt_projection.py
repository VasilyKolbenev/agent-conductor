"""Identity, provenance and display limits on the attempt read-model."""
from dataclasses import replace

import pytest

from conductor.command.accept_manifest import FileImage, build_snapshot
from conductor.command.accept_snapshot import write_snapshot
from conductor.command.attempt_detail import read_attempt
from conductor.command.api_contracts import ApiRefusal
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.run_store import RecoveredRun, StoredRecord, snapshot_digest
from conductor.command.seed_record import SeedRecord, write_seed
from tests.test_command_run_store import NOW, a_result, a_run, an_action, evidence
from tests.test_seed_record import an_empty_seed


RUN = "run-001"
TASK = "task-one"
CONFIG = {"task": {"id": TASK, "work_scope": TASK},
          "instances": [{"id": "doer", "adapter": "codex"}, {"id": "checker", "adapter": "codex"}]}
ARGS = {"profile": "implement-patch-v1", "work_item_id": "work-001", "work_scope": TASK}
NODE = GraphNode("do", "task", "Do", instance_id="doer", capability="dispatch", arguments=ARGS,
                 verifier_instance_id="checker", attempt_bound=2)
GRAPH = GraphDefinition("plan", RUN, NOW, nodes=(NODE,), execution_contract="bounded-run-v1")


def journal(*rows):
    return RecoveredRun(a_run(config_digest=snapshot_digest(CONFIG)), CONFIG,
                        (StoredRecord("graph_definition", GRAPH), *rows), ())


def attempt(root, identity, files, outcome="succeeded"):
    request = an_action(instance_id="doer", action_id="act-" + identity, attempt_id=identity,
                        mode="policy", arguments=ARGS, node_id="do", run_authorization_id="grant",
                        run_authorization_digest="sha256:" + "a" * 64)
    snapshot = build_snapshot({}, {name: FileImage(raw) for name, raw in files.items()},
                              object_format="sha1")
    digest = write_snapshot(root, RUN, snapshot, object_format="sha1")
    proof = evidence(evidence_id="proof-" + identity, kind="verification", digest=digest,
                     created_by="codex", verification="verified", verifier_instance_id="checker",
                     verified_at=NOW, verified_by="codex", uri=f"verification/{request.action_id}",
                     extra={"accept_manifest_digest": digest, "work_tree_digest": digest})
    result = a_result(instance_id="doer", action_id=request.action_id, attempt_id=identity,
                      outcome=outcome, evidence_refs=(proof.evidence_id,))
    return (StoredRecord("action_request", request), StoredRecord("evidence", proof),
            StoredRecord("action_result", result))


@pytest.fixture
def seeded(tmp_path):
    write_seed(tmp_path, SeedRecord.from_dict(an_empty_seed(task_id=TASK, work_scope=TASK)))
    return tmp_path


def test_two_attempt_snapshots_and_an_unfinished_action_never_mix(seeded):
    first = attempt(seeded, "first", {"first.txt": b"first content\n"})
    last = attempt(seeded, "last", {"second.txt": b"later content\n"})
    pending = replace(last[0].value, action_id="act-pending", attempt_id="pending")
    run = journal(*first, *last, StoredRecord("action_request", pending))
    older = read_attempt(seeded, run, "do", "act-first")
    later = read_attempt(seeded, run, "do", "act-last")
    assert older["manifest_digest"] != later["manifest_digest"]
    assert older["files"] == [{"path": "first.txt", "state": "added", "diff_status": "available",
                               "lines": ["@@ -0,0 +1 @@", "+first content"]}]
    assert later["files"][0]["lines"] == ["@@ -0,0 +1 @@", "+later content"]
    empty = read_attempt(seeded, run, "do", "act-pending")
    assert empty["outcome"] is None and empty["verdict"] is None and empty["files_total"] is None
    assert empty["files"] == [] and empty["tests"]["status"] == "not_recorded"
    with pytest.raises(ApiRefusal) as wrong:
        read_attempt(seeded, run, "other", "act-first")
    assert wrong.value.status == 404


@pytest.mark.parametrize("change", ["ref", "uri", "checker", "adapter", "attempt", "result"])
def test_borrowed_or_failed_actions_cannot_publish_files(seeded, change):
    req, proof, result = attempt(seeded, "one", {"a.txt": b"allowed"})
    if change == "ref":
        result = StoredRecord(result.kind, replace(result.value, evidence_refs=("foreign",)))
    elif change == "uri":
        proof = StoredRecord(proof.kind, replace(proof.value, uri="verification/another"))
    elif change == "checker":
        proof = StoredRecord(proof.kind, replace(proof.value, verifier_instance_id="doer"))
    elif change == "adapter":
        proof = StoredRecord(proof.kind, replace(proof.value, verified_by="foreign"))
    elif change == "attempt":
        result = StoredRecord(result.kind, replace(result.value, attempt_id="another"))
    else:
        result = StoredRecord(result.kind, replace(result.value, outcome="failed"))
    read = read_attempt(seeded, journal(req, proof, result), "do", "act-one")
    assert read["files"] == [] and read["files_total"] is None and read["manifest_digest"] is None
    if change != "result":
        assert read["verdict"] is None


def test_damaged_or_empty_snapshot_are_distinguishable(seeded):
    rows = attempt(seeded, "ok", {})
    empty = read_attempt(seeded, journal(*rows), "do", "act-ok")
    assert empty["files_total"] == 0 and empty["verdict"]["status"] == "verified"
    from conductor.ownership import data_root
    digest = empty["manifest_digest"].removeprefix("sha256:")
    path = data_root(seeded) / "accept" / RUN / "snapshots" / (digest + ".json")
    path.write_bytes(b"broken")
    damaged = read_attempt(seeded, journal(*rows), "do", "act-ok")
    assert damaged["files_total"] is None and damaged["tests"]["status"] == "unavailable"
    assert damaged["verdict"] == empty["verdict"] and damaged["files"] == []


def test_private_binary_and_large_files_never_emit_content(seeded):
    private = b"secret-witness-82"
    rows = attempt(seeded, "one", {"keys/.env": private, "binary": b"\0" + private,
                                   "large": private * 3000,
                                   "test_keys.py": b'def test_key():\n    api_key = "' + private
                                   + b'"\n    assert api_key\n'})
    view = read_attempt(seeded, journal(*rows), "do", "act-one")
    assert {r["path"]: r["diff_status"] for r in view["files"]} == {
        "keys/.env": "withheld", "binary": "binary", "large": "too_large",
        "test_keys.py": "withheld"}
    assert not any(r["lines"] for r in view["files"])
    assert private.decode() not in str(view)


@pytest.mark.parametrize("separator", [b"\n", b"\r", "\u2028".encode("utf-8")])
def test_diff_line_budget_also_covers_non_lf_text(seeded, separator):
    rows = attempt(seeded, "lines", {"many.txt": separator.join([b"x"] * 601)})
    view = read_attempt(seeded, journal(*rows), "do", "act-lines")
    assert view["files"] == [{"path": "many.txt", "state": "added",
                              "diff_status": "too_large", "lines": []}]


def test_sealed_content_outside_recorded_seed_scope_is_not_displayed(seeded):
    rows = attempt(seeded, "off", {"AGENTS.md": b"excluded instructions"})
    view = read_attempt(seeded, journal(*rows), "do", "act-off")
    assert view["files"] == [] and view["files_total"] is None
    assert view["tests"]["status"] == "unavailable"
    assert "excluded instructions" not in str(view)
