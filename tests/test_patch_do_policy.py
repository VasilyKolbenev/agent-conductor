"""A real bounded Do and independent check, substituting only external process responses."""
from hashlib import sha256
from itertools import count
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import ownership
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.process import ProcessOutcome, STDIN_DELIVERED
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphNode
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


def run_state(root, adapter, *, checker="checker"):
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
    args = {"work_item_id": "item", "instruction_ref": "brief", "profile": "implement-patch-v1",
            "artifact_refs": [], "output_limit_profile": "normal", "work_scope": "one"}
    node = GraphNode("do", "task", "Do", instance_id="doer", capability="dispatch",
                     arguments=args, timeout_seconds=30, attempt_bound=1,
                     verifier_instance_id=checker)
    store.append(GraphDefinition("graph", "run", NOW, nodes=(node,), edges=(),
                                 execution_contract="bounded-run-v1"))
    store.append(ArtifactDocument("instruction", "brief", "run", NOW, "text/plain",
                                  "Count successes and cover a mixed input."))
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


def work_and_calls(site, patch, *, use_native=False, verdict=True):
    """Wrap the CLI boundary. The checker judges actual content in its received stdin."""
    from conductor.command.adapters.deep_commands import PATCH_PROFILE

    adapter = site.adapter
    assert adapter.patch_dispatch_version == PATCH_PROFILE
    work = adapter._workspace.work_dir("item", "one")
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
        files = [json.loads(line) for line in spec.stdin_bytes.decode().splitlines()
                 if line.startswith("{") and '"encoding"' in line]
        data = {row["path"]: row["content"].encode() for row in files}
        assert HEADER not in patch and HEADER in data["_tasks/one/item/count.py"]
        expected = {"_tasks/one/item/count.py": ACTUAL,
                    "_tasks/one/item/test_count.py": REGRESSION}
        assert data == expected
        assert all((work / name.split("/item/")[1]).read_bytes() == value
                   for name, value in data.items())
        assert all(sha256(content).hexdigest().encode() in spec.stdin_bytes
                   for content in data.values())
        return reply(b"VERDICT: accept\n" if verdict else b"VERDICT: reject\n")
    runner.run = run
    return work, calls


def one_grant(site):
    f = run_state(site.root, site.adapter)
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
        assert [r.verifier_instance_id for r in get("evidence")] == (
            ["checker"] if case == "accept" else [])
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
