"""An archived rejected action exposes its own bytes through the public read route."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.accept_manifest import FileImage, build_snapshot
from conductor.command.accept_snapshot import _folder, read_snapshot, write_snapshot
from conductor.command.adapters import AdapterRegistry
from conductor.command.feedback_payload import payload_bytes
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore
from conductor.command.seed_record import write_seed
from conductor.command.seed_stage import move_staged, stage_empty
from tests.relay_roads import CODEX, Site
from tests.test_command_http_api import PORT, TOKEN, get_headers, ids
from tests.test_patch_do_policy import ACTUAL, PATCH, REGRESSION, one_grant, reply, work_and_calls
from tests.test_policy_runtime import NOW


PLAN = {"runner": "python-unittest-v1", "toolchain": {
    "install": "C:\\trusted\\harnesses\\python\\3.12.14", "entry": "python.exe",
    "runtime_digest": "sha256:" + "9" * 64}, "start": "suite", "pattern": "test_*.py",
    "timeout_seconds": 20}
FINDINGS = {"protocol": "conduct.feedback.v1", "findings": [{"kind": "verification_gap",
    "summary": "The mixed input regression failed", "path": "test_count.py", "line": 4}]}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def rejected(tmp_path, *, accepted=False):
    site = Site(tmp_path, CODEX)
    install = tmp_path / "harnesses" / "python-unittest" / "3.12.14"
    install.mkdir(parents=True)
    runtime = b"fake-python-never-executed"
    (install / "python.exe").write_bytes(runtime)
    inventory = [{"path": "python.exe", "length": len(runtime),
                  "sha256": hashlib.sha256(runtime).hexdigest()}]
    plan = json.loads(canonical(PLAN))
    plan["toolchain"] = {"install": str(install), "entry": "python.exe",
                         "runtime_digest": digest(inventory)}
    with site.owned():
        seed = stage_empty(site.root, task_id="one", work_scope="one", work_item_id="work-001",
                           staged_at=NOW)
        write_seed(site.root, seed)
        move_staged(site.root, seed)
        work, calls = work_and_calls(site, PATCH, item="work-001", verdict=accepted)
        (work / "suite").mkdir()
        original = site.runner.run

        def run(spec):
            if Path(spec.argv[0]).name == "python.exe":
                calls.append("tests")
                assert spec.boundary and not spec.boundary.internet_client
                if accepted:
                    return reply(b'Ran 2 tests\nOK\n\nconduct.test-result.v1 '
                                 b'{"total":2,"failures":0,"errors":0,"skipped":0}\n')
                return reply(b"Ran 1 test\nFAILED (failures=1)\n"
                    b'\nconduct.test-result.v1 '
                    b'{"total":1,"failures":1,"errors":0,"skipped":0}\n', code=1)
            result = original(spec)
            if "checker-model" in spec.argv:
                anchors = [row.value for row in RunStore(site.root).read("run").records
                           if row.kind == "evidence" and row.value.kind == "attempt_seal"]
                assert len(anchors) == 1 and anchors[0].verification == "unverified"
                if accepted:
                    return reply(b"VERDICT: accept\n")
                return reply(b"VERDICT: reject\n" + payload_bytes(FINDINGS))
            return result

        site.runner.run = run
        instruction = ("Count successes and cover a mixed input.\n"
                       "\nconduct.test-plan.v1\n" + json.dumps(plan))
        get, request = one_grant(site, item="work-001", instruction=instruction)
        result, = get("action_result")
        assert result.outcome == ("succeeded" if accepted else "verification_failed")
        assert len(get("correction_feedback")) == (0 if accepted else 1)
        snap = build_snapshot({}, {"count.py": FileImage(ACTUAL),
                                  "test_count.py": FileImage(REGRESSION)}, object_format="sha1")
        saved = read_snapshot(site.root, "run", snap.digest, object_format="sha1")
        assert saved.payload == snap.payload
        folder = _folder(site.root, "run")
        sealed_path = folder / "actions" / (request.action_id + ".json")
        assert calls == ["prepare", "apply", "tests", "check"]
        wrapped = json.loads(sealed_path.read_bytes())
        report = json.loads((folder / "tests" / (
            request.action_id + ".protocol.json")).read_bytes())
        (work / "count.py").write_bytes(b"subsequent workspace edit\n")
        api = CommandApi(RunStore(site.root), AdapterRegistry([]),
                         session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
                         clock=lambda: NOW, ids=ids(), publish_run=lambda _run: None)
        return SimpleNamespace(site=site, api=api, request=request, seal=wrapped, report=report)


def read(f):
    url = f"/command/runs/run/steps/do/actions/{f.request.action_id}"
    response = f.api.handle("GET", url, get_headers())
    assert response.status == 200, response.payload
    return response.payload


def test_rejected_attempt_exposes_bound_snapshot_findings_and_native_protocol(tmp_path):
    f = rejected(tmp_path)
    body = read(f)
    assert body["verdict"] == {"status": "rejected", "instance_id": "checker",
                               "adapter_id": "codex", "reason": "rejected",
                               "findings": FINDINGS["findings"]}
    assert body["files_total"] == 2
    assert "+    return sum(row == 'ok' for row in rows)" in body["files"][0]["lines"]
    assert body["tests"]["source"] == "native"
    assert body["tests"]["protocol"] == f.report
    assert body["tests"]["summary"] == {"total": 1, "errors": 0, "failures": 1, "skipped": 0}
    assert "subsequent workspace" not in str(body)
    assert not body.get("accepted", False)


def test_seeded_success_exposes_its_verified_snapshot_and_keeps_anchor_unverified(tmp_path):
    f = rejected(tmp_path, accepted=True)
    body = read(f)
    assert body["outcome"] == "succeeded"
    assert body["verdict"] == {"status": "verified", "instance_id": "checker",
                               "adapter_id": "codex"}
    assert body["files_total"] == 2 and body["tests"]["protocol"] == f.report
    evidence = [row.value for row in RunStore(f.site.root).read("run").records
                if row.kind == "evidence"]
    assert [(row.kind, row.verification) for row in evidence] == [
        ("attempt_seal", "unverified"), ("verification", "verified")]


@pytest.mark.parametrize("field,value", [
    ("attempt", "foreign-attempt"), ("workspace_tree", "sha256:" + "1" * 64),
    ("policy", "sha256:" + "2" * 64), ("toolpin", "sha256:" + "3" * 64),
    ("input_artifact_ids", ["later-instruction"]), ("snapshot_digest", "sha256:" + "4" * 64),
])
def test_foreign_or_damaged_seal_never_exposes_rejected_bytes(tmp_path, field, value):
    f = rejected(tmp_path)
    folder = _folder(f.site.root, "run") / "actions"
    changed = json.loads(canonical(f.seal))
    changed["seal"][field] = value
    changed["digest"] = digest(changed["seal"])
    (folder / (f.request.action_id + ".json")).write_bytes(canonical(changed))
    path = folder / (f.request.action_id + ".outcome.json")
    outcome = json.loads(path.read_bytes())
    outcome["seal_digest"] = changed["digest"]
    path.write_bytes(canonical(outcome))
    body = read(f)
    assert body["files"] == [] and body["files_total"] is None
    assert body["verdict"] is None
    assert body["tests"]["status"] == "unavailable"


@pytest.mark.parametrize("substitution", ["extra", "mode"])
def test_recomputed_seal_cannot_substitute_a_valid_snapshot(tmp_path, substitution):
    f = rejected(tmp_path)
    images = {"count.py": FileImage(ACTUAL, "100755" if substitution == "mode" else "100644"),
              "test_count.py": FileImage(REGRESSION)}
    if substitution == "extra":
        images["unreviewed.py"] = FileImage(b"never seen by this checker\n")
    replacement = build_snapshot({}, images, object_format="sha1")
    with f.site.owned():
        write_snapshot(f.site.root, "run", replacement, object_format="sha1")
    folder = _folder(f.site.root, "run") / "actions"
    changed = json.loads(canonical(f.seal))
    changed["seal"]["snapshot_digest"] = replacement.digest
    changed["digest"] = digest(changed["seal"])
    (folder / (f.request.action_id + ".json")).write_bytes(canonical(changed))
    path = folder / (f.request.action_id + ".outcome.json")
    outcome = json.loads(path.read_bytes())
    outcome["seal_digest"] = changed["digest"]
    path.write_bytes(canonical(outcome))
    body = read(f)
    assert body["files"] == [] and body["verdict"] is None
    assert body["tests"]["status"] == "unavailable"


def test_legacy_reject_does_not_acquire_a_snapshot_from_matching_content(tmp_path):
    f = rejected(tmp_path)
    folder = _folder(f.site.root, "run") / "actions"
    for suffix in (".json", ".outcome.json"):
        (folder / (f.request.action_id + suffix)).unlink()
    body = read(f)
    assert body["files_total"] is None and body["verdict"] is None
    assert body["tests"]["status"] == "not_recorded"


def test_test_claim_is_once_and_completion_must_match_original_binding(tmp_path):
    from conductor.command.accept_manifest import SnapshotRefused
    from conductor.command.attempt_protocol import claim_test_run, read_test_run, record_test_run
    f = rejected(tmp_path)
    request = SimpleNamespace(**{key: getattr(f.request, key) for key in (
        "run_id", "action_id", "attempt_id", "instance_id", "run_authorization_id",
        "run_authorization_digest")})
    request.action_id = "another-action"
    report = json.loads(canonical(f.report))
    report["binding"]["action"] = request.action_id
    root = tmp_path / "new-root"
    (root / "conductor").mkdir(parents=True)
    assert read_test_run(root, request) is None
    assert claim_test_run(root, request, report["binding"]) is True
    assert claim_test_run(root, request, report["binding"]) is False
    with pytest.raises(SnapshotRefused):
        read_test_run(root, request)
    swapped = json.loads(canonical(report))
    swapped["binding"]["workspace_tree"] = "sha256:" + "7" * 64
    with pytest.raises(SnapshotRefused):
        record_test_run(root, request, swapped)
    record_test_run(root, request, report)
    assert read_test_run(root, request) == report
    record_test_run(root, request, report)
    changed = json.loads(canonical(report))
    changed["argv"].append("other")
    with pytest.raises(SnapshotRefused):
        record_test_run(root, request, changed)
    assert read_test_run(root, request) == report


def test_handoff_seal_and_finish_bind_the_same_completed_report(tmp_path):
    from conductor.command.adapters import AdapterVerification
    from conductor.command.attempt_protocol import finish_attempt, read_attempt_seal, seal_attempt
    from conductor.command.seed_record import read_seed
    f = rejected(tmp_path)
    seal = f.seal["seal"]
    material = SimpleNamespace(result_manifest=seal["result_manifest"],
        input_artifact_ids=seal["input_artifact_ids"], after={
            "_tasks/one/work-001/count.py": hashlib.sha256(ACTUAL).hexdigest(),
            "_tasks/one/work-001/test_count.py": hashlib.sha256(REGRESSION).hexdigest()})
    frame = SimpleNamespace(accept_manifest_digest=seal["snapshot_digest"],
                            work_tree_digest=seal["subtree_tree"],
                            work_modes={"count.py": False, "test_count.py": False})
    verifier = SimpleNamespace(instance_id="checker", adapter_id="codex")
    verification = AdapterVerification("codex", f.request.action_id, "mismatch", NOW,
        "rejected", feedback=payload_bytes(FINDINGS), result_manifest=seal["result_manifest"])
    with f.site.owned():
        prepared = seal_attempt(f.site.root, f.request, verifier, material, frame,
                                read_seed(f.site.root, "one"), f.report)
        assert prepared == f.seal
        finish_attempt(f.site.root, f.request, prepared, verifier, verification)
    stored, outcome = read_attempt_seal(f.site.root, f.request)
    assert stored == seal and outcome["seal_digest"] == f.seal["digest"]
    assert outcome["state"] == "mismatch" and outcome["detail"] == "rejected"
