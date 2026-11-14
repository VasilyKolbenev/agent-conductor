"""A real bounded Do and independent check, substituting only external process responses."""
from hashlib import sha256
from itertools import count
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conductor import ownership
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.process import ProcessOutcome, STDIN_DELIVERED
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphLoop, GraphNode
from conductor.command.policy_service import PolicyService
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget, ControlRuntime
from tests.relay_roads import CODEX, Site
from tests.test_policy_driver import attach_driver, wait_terminal
from tests.test_policy_runtime import NOW, PD

PATCH = b"""*** Begin Patch
*** Update File: count.py
@@
 def count_succeeded(rows):
-    return len(rows)
+    return sum(row == 'ok' for row in rows)
*** Add File: test_count.py
+from count import count_succeeded
+
+def test_mixed():
+    assert count_succeeded(['ok', 'fail']) == 1
*** End Patch
"""
HEADER = b"# Kept from the task file; absent from the proposed patch.\n"
SOURCE = HEADER + b"def count_succeeded(rows):\n    return len(rows)\n"
ACTUAL = HEADER + b"def count_succeeded(rows):\n    return sum(row == 'ok' for row in rows)\n"
REGRESSION = (b"from count import count_succeeded\n\ndef test_mixed():\n"
              b"    assert count_succeeded(['ok', 'fail']) == 1\n")


def run_state(root, adapter, *, checker="checker", item="item", with_gates=False, documents=(),
              instruction="Count successes and cover a mixed input.", correction=False):
    registry, counter = AdapterRegistry([adapter]), count()
    store = RunStore(root)
    ids = lambda kind: f"{kind}-{next(counter)}"
    config = {"cycle": {"id": "cycle"}, "automation_contract": "bounded-run-v1",
              "task": {"id": "one", "work_scope": "one"},
              "workflow": {"id": "repair", "revision": 1},
              "instances": [{"id": name, "adapter": "codex", "model": name + "-model"}
                            for name in ("doer", "checker")]}
    store.create_run(RunEnvelope("run", "cycle", NOW, snapshot_digest(config), mode="policy"),
                     config)
    args = {"work_item_id": item, "instruction_ref": "brief", "profile": "implement-patch-v1",
            "artifact_refs": [d.artifact_ref for d in documents], "output_limit_profile": "normal",
            "work_scope": "one"}
    node = GraphNode("do", "task", "Do", instance_id="doer", capability="dispatch",
                     arguments=args, timeout_seconds=30, attempt_bound=2 if correction else 1,
                     verifier_instance_id=checker)
    nodes = (node,)
    edges = ()
    if correction:
        nodes += (GraphNode("correct", "loop", "Correct", loop=GraphLoop(bound=2, back_to="do")),)
        edges = (GraphEdge("do", "correct", condition="on_failed"),)
    if with_gates:
        nodes += (GraphNode("accept", "gate", "Accept the patch", gate_id="accept"),
                  GraphNode("next", "gate", "Next decision", gate_id="next"))
        edges += (GraphEdge("do", "accept"), GraphEdge("accept", "next"))
    store.append(GraphDefinition("graph", "run", NOW, nodes=nodes, edges=edges,
                                 execution_contract="bounded-run-v1"))
    store.append(ArtifactDocument("instruction", "brief", "run", NOW, "text/plain", instruction))
    for doc in documents:
        store.append(doc)
    policy = PolicyService(store, registry, budget=Budget(4, 3600, 300), clock=lambda: NOW,
                           provider_digest=lambda _: PD,
                           owner_check=lambda: ownership.require_owner(root),
                           session="test", notify=lambda run: None)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=ids)
    runtime._policy = policy
    return SimpleNamespace(policy=policy, store=store, runtime=runtime)


def reply(output, code=0):
    return ProcessOutcome("completed", code, output, False, 16384, 123, "fixture",
                          stdin_state=STDIN_DELIVERED)


def work_and_calls(site, patch, *, use_native=False, verdict=True, item="item"):
    """Wrap the CLI boundary. The checker judges actual content in its received stdin."""
    from conductor.command.adapters.deep_commands import PATCH_PROFILE

    adapter = site.adapter
    assert adapter.patch_dispatch_version == PATCH_PROFILE
    work = adapter._workspace.work_dir(item, "one")
    (work / "count.py").write_bytes(SOURCE)
    calls = []
    runner = adapter._runner
    real = runner.run

    def run(spec):
        if spec.codex_patch_stdin:
            calls.append("apply")
            assert spec.boundary and not spec.boundary.internet_client
            assert len(spec.argv) == 1 and spec.env_allow == () and "CODEX_HOME" not in spec.env
            if use_native:
                return real(spec)
            # Replace the vendor utility on non-native CI, never the product's validation,
            # installation, on-disk reread or independent check.
            folder = Path(spec.env["TMP"])
            assert (folder / "edit-0").read_bytes() == SOURCE
            (folder / "edit-0").write_bytes(ACTUAL)
            (folder / "edit-1").write_bytes(REGRESSION)
            return reply(b"done")
        if "exec" not in spec.argv:
            return real(spec)
        assert spec.boundary and "read-only" in spec.argv
        if "doer-model" in spec.argv:
            calls.append("prepare")
            assert b"*** Begin Patch" in spec.stdin_bytes and b"Count successes" in spec.stdin_bytes
            return reply(patch)
        assert "checker-model" in spec.argv
        calls.append("check")
        attempt, _, _ = spec.stdin_bytes.decode().partition("\nACCUMULATED RESULT\n")
        files = [json.loads(line) for line in attempt.splitlines()
                 if line.startswith("{") and '"encoding"' in line]
        data = {row["path"]: row["content"].encode() for row in files}
        prefix = f"_tasks/one/{item}/"
        assert HEADER not in patch and HEADER in data[prefix + "count.py"]
        expected = {prefix + "count.py": ACTUAL, prefix + "test_count.py": REGRESSION}
        assert data == expected
        assert all((work / name.removeprefix(prefix)).read_bytes() == value
                   for name, value in data.items())
        assert all(sha256(content).hexdigest().encode() in spec.stdin_bytes
                   for content in data.values())
        return reply(b"VERDICT: accept\n" if verdict else b"VERDICT: reject\n")
    runner.run = run
    return work, calls


def one_grant(site, **kwargs):
    f = run_state(site.root, site.adapter, **kwargs)
    driver, execution = attach_driver(f)
    try:
        terms = {"node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 1}],
                 "max_actions": 1, "max_action_seconds": 60, "max_total_task_seconds": 60,
                 "duration_seconds": 1800}
        preview = f.policy.preview("run", terms)
        assert preview["patch_steps"] == ["do"]
        grant = dict(authorization_id="grant", preview_digest=preview["preview_digest"],
                     terms=preview["terms"], authorized_by="test-owner", supersedes=None)
        f.policy.authorize("run", grant)
        read = wait_terminal(f)
    finally:
        driver.stop()
        execution.shutdown()
    get = lambda kind: [row.value for row in read.records if row.kind == kind]
    assert [len(get(kind)) for kind in ("run_authorization", "action_request", "action_result")
            ] == [1, 1, 1]
    request, = get("action_request")
    assert request.run_authorization_id == "grant"
    return get, request


def assert_account_evidence(evidence, request):
    accounts = [row for row in evidence if row.kind == "subscription_account_v1"]
    assert len(accounts) == 2
    request_bytes = json.dumps(request.as_dict(), sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
    request_digest = "sha256:" + sha256(request_bytes).hexdigest()
    for row, role, actor in zip(accounts, ("doer", "checker"), ("doer", "checker")):
        assert (row.run_id, row.created_by, row.verification, row.verifier_instance_id) == (
            request.run_id, "codex", "unverified", None)
        assert row.uri == (
            f"subscription-account/{request.action_id}/{request.attempt_id}/{role}/{actor}")
        assert dict(row.extra) == {
            "binding": {"run_id": request.run_id, "action_id": request.action_id,
                        "attempt_id": request.attempt_id, "instance_id": "doer",
                        "actor_instance_id": actor, "adapter_id": "codex", "role": role},
            "request_digest": request_digest,
            "proof": {"version": 1, "vendor": "openai", "source": "source_relay",
                      "status": "local_match", "account_sha256":
                      "sha256:4eebedef3c736cc27d5dd2486167f10d3cd6bae47dfb846051bdee53b822735e"}}


@pytest.mark.parametrize("case", [
    "accept", "reject", "foreign", "stale", "truncated", "patch_error", "concurrent"])
def test_one_grant_checks_real_changed_bytes_and_never_replays(tmp_path, case, monkeypatch):
    from dataclasses import replace
    from conductor.command.adapters import patch_publish

    site = Site(tmp_path, CODEX)
    patch = PATCH if case != "foreign" else PATCH.replace(b"count.py", b"../foreign.py")
    with site.owned():
        work, calls = work_and_calls(site, patch, verdict=case == "accept")
        run = site.runner.run
        def observed(spec):
            result = run(spec)
            if "doer-model" in spec.argv:
                if case == "stale":
                    (work / "count.py").write_bytes(b"outside edit\n")
                if case == "truncated":
                    return replace(result, output_truncated=True)
            if case == "patch_error" and spec.codex_patch_stdin:
                return reply(b"failed", code=1)
            return result
        site.runner.run = observed
        if case == "concurrent":
            publish = patch_publish.publish
            def external_edit(*args):
                publish(*args)
                (work / "outside.py").write_bytes(b"external editor")
            monkeypatch.setattr(patch_publish, "publish", external_edit)
        get, request = one_grant(site)
        receipt, = get("action_result")
        if case in ("foreign", "stale", "truncated", "patch_error"):
            assert receipt.outcome == "failed", receipt.detail
            expected = b"outside edit\n" if case == "stale" else SOURCE
            assert calls == (["prepare", "apply"] if case == "patch_error" else ["prepare"])
            assert (work / "count.py").read_bytes() == expected
            assert not (work / "test_count.py").exists()
        elif case == "concurrent":
            assert receipt.outcome == "unknown" and calls == ["prepare", "apply"]
            assert (work / "outside.py").read_bytes() == b"external editor"
        else:
            expected = "succeeded" if case == "accept" else "verification_failed"
            assert receipt.outcome == expected, receipt.detail
            assert calls == ["prepare", "apply", "check"]
            assert (work / "count.py").read_bytes() == ACTUAL
        evidence = get("evidence")
        expected_kinds = (["subscription_account_v1"] * 2
                          if case in ("accept", "reject") else [])
        if case == "accept":
            expected_kinds.append("verification")
        assert [row.kind for row in evidence] == expected_kinds
        if case in ("accept", "reject"):
            assert_account_evidence(evidence, request)
        verification = [row for row in evidence if row.kind == "verification"]
        assert [r.verifier_instance_id for r in verification] == (
            ["checker"] if case == "accept" else [])
        assert [r.verification for r in verification] == (
            ["verified"] if case == "accept" else [])
        before = calls.copy()
        assert site.adapter.execute(site.adapter.prepare(request)).outcome == "unknown"
        assert calls == before
        assert not site.leftovers()


def test_preview_without_a_checker_grants_no_patch_authority(tmp_path):
    from conductor.command.contracts import ContractError

    site = Site(tmp_path, CODEX)
    with site.owned():
        f = run_state(site.root, site.adapter, checker=None)
        with pytest.raises(ContractError, match="separate checker"):
            f.policy.preview("run", {"node_limits": [
                {"node_id": "do", "timeout_seconds": 30, "max_attempts": 1}],
                "max_actions": 1, "max_action_seconds": 30, "max_total_task_seconds": 30,
                "duration_seconds": 300})
        assert all(row.kind not in {"run_authorization", "action_request"}
                   for row in f.store.read("run").records)


def test_two_patch_attempts_apply_typed_finding_and_check_the_cumulative_result(tmp_path):
    from conductor.command.adapters.local_test_plan import inventory_digest
    from conductor.command.attempt_detail import read_attempt
    from conductor.command.attempt_protocol import read_test_run
    from conductor.command.seed_record import SeedRecord, write_seed
    from tests.test_policy_native_feedback import terminal
    from tests.test_seed_record import an_empty_seed

    site = Site(tmp_path, CODEX)
    old = "def answer():\n    return 2\n"
    fixed = "def answer():\n    return 1\n"
    test = ("import unittest\nfrom answer import answer\n\nclass Answer(unittest.TestCase):\n"
            "    def test_result(self):\n        self.assertEqual(answer(), 1)\n")
    finding = {"kind": "defect", "summary": "Return 1 from answer() to meet the requirement.",
               "path": "answer.py", "line": 2}
    payload = {"protocol": "conduct.feedback.v1", "findings": [finding]}
    first_patch = ("*** Begin Patch\n*** Add File: answer.py\n+def answer():\n+    return 2\n"
                   "*** Add File: tests/test_answer.py\n"
                   + "".join("+" + line + "\n" for line in test.splitlines()) + "*** End Patch\n")
    correction = ("*** Begin Patch\n*** Update File: answer.py\n@@\n def answer():\n"
                  "-    return 2\n+    return 1\n*** End Patch\n")
    pin = tmp_path / "harnesses" / "python-unittest" / "3.12.14"
    pin.mkdir(parents=True)
    (pin / "python.exe").write_bytes(b"process double")
    policy = {"runner": "python-unittest-v1", "start": "tests", "pattern": "test_*.py",
              "timeout_seconds": 30, "toolchain": {"install": str(pin), "entry": "python.exe",
                                                    "runtime_digest": inventory_digest(pin)}}
    instruction = ("Make answer return one.\n\nconduct.test-plan.v1\n" + json.dumps(policy)
                   + '\n\nconduct.patch-sources.v1\n["answer.py","tests/test_answer.py"]')
    calls, frames, feedback_rows = [], [], []
    original = site.runner.run

    def child(spec):
        if spec.codex_patch_stdin:
            calls.append("patch")
            scratch = Path(spec.env["TMP"])
            if not frames:
                (scratch / "edit-0").write_bytes(old.encode())
                (scratch / "edit-1").write_bytes(test.encode())
            else:
                assert (scratch / "edit-0").read_bytes() == old.encode()
                (scratch / "edit-0").write_bytes(fixed.encode())
            return reply(b"done")
        if spec.argv[0] == str(pin / "python.exe"):
            calls.append("unittest")
            assert spec.boundary and not spec.boundary.internet_client
            assert (work / "tests/test_answer.py").read_bytes() == test.encode()
            assert (work / "answer.py").read_text() in (old, fixed)
            # Execute the product bootstrap against only these known fixture bytes.
            command = [sys.executable, *spec.argv[1:5], sys.base_prefix, *spec.argv[6:]]
            proc = subprocess.run(command, cwd=work, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=15)
            return reply(proc.stdout, code=proc.returncode)
        if "doer-model" in spec.argv:
            calls.append("prepare")
            frame = spec.stdin_bytes.decode()
            section = frame.partition("\nCORRECTION DATA")[2]
            if section:
                feedback_rows.extend(json.loads(section.splitlines()[1]))
                source = [json.loads(s) for s in frame.splitlines() if s.startswith('{"path":')]
                assert {s["path"]: s["content"] for s in source} == {
                    "answer.py": old, "tests/test_answer.py": test}
            return reply((correction if section else first_patch).encode())
        if "checker-model" not in spec.argv:
            return original(spec)
        calls.append("check")
        frame = spec.stdin_bytes.decode()
        frames.append(frame)
        protocol = frame.split("\nPOST-PATCH TEST EXECUTION\n")[1]
        report = json.loads(protocol.splitlines()[0])
        if report["status"] == "failed" and "2 != 1" in report["output"]:
            return reply(b"VERDICT: reject\n" + json.dumps(payload).encode())
        assert report["status"] == "passed" and "test_result" in report["output"]
        return reply(b"VERDICT: accept\n")

    with site.owned():
        write_seed(site.root, SeedRecord.from_dict(an_empty_seed(task_id="one", work_scope="one")))
        work = site.adapter._workspace.work_dir("work-001", "one")
        (work / "tests").mkdir()
        site.runner.run = child
        f = run_state(site.root, site.adapter, item="work-001", instruction=instruction,
                      correction=True)
        driver, execution = attach_driver(f)
        try:
            terms = {"node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 2}],
                     "max_actions": 2, "max_action_seconds": 60, "max_total_task_seconds": 120,
                     "duration_seconds": 1800}
            preview = f.policy.preview("run", terms)
            f.policy.authorize("run", {"authorization_id": "grant", "authorized_by": "test-owner",
                "preview_digest": preview["preview_digest"], "terms": preview["terms"],
                "supersedes": None})
            read = terminal(f)
        finally:
            driver.stop()
            execution.shutdown()
        requests = [row.value for row in read.records if row.kind == "action_request"]
        receipts = [row.value for row in read.records if row.kind == "action_result"]
        assert [r.outcome for r in receipts] == ["verification_failed", "succeeded"]
        first, second = requests
        assert first.attempt_id != second.attempt_id and first.action_id != second.action_id
        assert all(r.node_id == "do" and r.instance_id == "doer" and
                   r.run_authorization_id == "grant" for r in requests)
        assert sum(row.kind == "run_authorization" for row in read.records) == 1
        feedback, = (r.value for r in read.records if r.kind == "correction_feedback")
        assert feedback_rows == [feedback.as_dict()] and feedback_rows[0]["payload"] == payload
        assert feedback.source_attempt_id == first.attempt_id and feedback.source_lap == 1
        assert feedback.source_action_id == first.action_id
        assert feedback.checker_instance_id == "checker"
        assert calls == ["prepare", "patch", "unittest", "check"] * 2
        attempts = [(first, "failed", old, 1), (second, "passed", fixed, 0)]
        for (request, status, data, failures), frame in zip(attempts, frames, strict=True):
            report = read_test_run(site.root, request)
            assert report["status"] == status
            assert report["counts"] == dict(total=1, failures=failures, errors=0, skipped=0)
            assert report["binding"]["action"] == request.action_id
            assert report["binding"]["attempt"] == request.attempt_id
            assert "test_result" in report["output"]
            protocol = frame.split("\nPOST-PATCH TEST EXECUTION\n")[1]
            assert json.loads(protocol.splitlines()[0]) == report
            accumulated = frame.split("\nACCUMULATED RESULT\n")[1].split("\nPOST-PATCH")[0]
            files = [json.loads(s) for s in accumulated.splitlines() if '"encoding"' in s]
            assert {v["path"]: v["content"] for v in files} == {
                "answer.py": data, "tests/test_answer.py": test}
            detail = read_attempt(site.root, read, "do", request.action_id)
            assert {row["path"] for row in detail["files"]} == {"answer.py", "tests/test_answer.py"}
            assert detail["verdict"]["instance_id"] == "checker"
            assert detail["verdict"]["status"] == ("rejected" if request == first else "verified")
        changed = json.loads(frames[1].split("\nCHANGED PATHS\n")[1].splitlines()[0])
        assert changed == ["_tasks/one/work-001/answer.py"]
