"""Literal selected source bytes at the public Grok task-file process boundary."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import ownership
from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget, Confirmation, ControlRuntime
from tests import _fakegrok
from tests.test_command_grok_transport import NOW, _Ids
from tests.test_grok_activation import EXPECTED_ARGV, _site

MARKER = "\n\nconduct.review-sources.v1\n"
SOURCES = {"runstats/counts.py": "def count_succeeded(rows):\n    return len(rows)\n",
           "tests/test_counts.py": "# Проверка\nassert count_succeeded([]) == 0\n"}


def fixture(tmp_path, *, context=None, ref="source-context", selected=True):
    adapter, root, log, login, original, runner = _site(tmp_path, "subscription")
    held = []
    with ownership.acquire_owner(root):
        work = adapter._workspace.work_dir("work-001", "one")
        other = adapter._workspace.work_dir("work-001", "two")
        for name, text in SOURCES.items():
            target = work / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(text.encode())
            neighbor = other / name
            neighbor.parent.mkdir(exist_ok=True)
            neighbor.write_bytes(b"SIBLING-SOURCE-CANARY")
        (work / "unused.py").write_bytes(b"UNREQUESTED-SOURCE-CANARY")
    context = MARKER + json.dumps([*SOURCES, "tests/missing.py"]) if context is None else context

    def capture(spec):
        if "--prompt-file" in spec.argv:
            task = Path(spec.argv[spec.argv.index("--prompt-file") + 1]).read_bytes()
            held.append((spec, task))

    runner.hooks["run"] = capture
    return SimpleNamespace(adapter=adapter, root=root, log=log, runner=runner,
        work=work, other=other, held=held, context=context, ref=ref, selected=selected)


def execute(f):
    args = {"work_item_id": "work-001", "work_scope": "one", "review_profile": "quality",
        "step_purpose": "Diagnose the concrete defect in the supplied source code",
        "target_artifact_refs": ["candidate"] + ([f.ref] if f.selected else []),
        "result_artifact_ref": "diagnosis"}
    config = {"cycle": {"id": "review"}, "task": {"id": "one", "work_scope": "one"},
              "instances": [{"id": "reviewer", "adapter": "grok-build"}]}
    digest = snapshot_digest(config)
    with ownership.acquire_owner(f.root):
        store = RunStore(f.root)
        store.create_run(RunEnvelope("run", "review", NOW, digest, mode="confirm"), config)
        for identity, ref, text in (("brief", "candidate", "Diagnose the selected task sources."),
                                     ("sources", f.ref, f.context)):
            store.append(ArtifactDocument(identity, ref, "run", NOW, "text/plain", text))
        proposal = ActionProposal("proposal", "run", "attempt", "reviewer", "review", args,
            ("work/_tasks/one/work-001",), "owner", NOW, 60, "Read selected source data", digest,
            input_binding="proposal-v1")
        store.append(proposal)
        runtime = ControlRuntime(store, AdapterRegistry([f.adapter]), clock=lambda: NOW, ids=_Ids())
        confirmation = Confirmation("confirmation", "run", "proposal", proposal.preview_digest,
            "review", proposal.scope, digest, "owner", NOW)
        runtime.execute(runtime.authorize(confirmation, budget=Budget(1, 60, 60)))
        records = store.read("run").records
    result, = [row.value for row in records if row.kind == "action_result"]
    return result, records


def test_public_review_delivers_only_selected_task_source_bytes_and_hashes(tmp_path):
    f = fixture(tmp_path)
    result, records = execute(f)
    spec, task = f.held[0]
    rows = [json.loads(line) for line in task.decode().splitlines()
            if line.startswith('{"path":')]
    assert len(rows) == 3, "selected source rows did not reach the Grok task file"
    assert {row["path"]: row["content"] for row in rows[:-1]} == SOURCES
    assert rows[-1] == {"path": "tests/missing.py", "state": "absent"}
    for row in rows[:-1]:
        assert row["sha256"] == hashlib.sha256(SOURCES[row["path"]].encode()).hexdigest()
    assert b"SIBLING-SOURCE-CANARY" not in task and b"UNREQUESTED-SOURCE-CANARY" not in task
    assert spec.cwd == "work/_tasks/one/work-001" and spec.boundary
    assert list(spec.argv[1:-1]) == EXPECTED_ARGV
    assert [entry.mode for entry in f.runner.entries] == ["review"]
    child, = _fakegrok.prompt_spawns(f.log)
    assert child["task_sha256"] == hashlib.sha256(task).hexdigest()
    assert result.outcome == "succeeded"
    output, = [r.value for r in records if r.kind == "artifact"
               and r.value.source_action_id is not None]
    assert output.input_artifact_ids == ("brief", "sources")


@pytest.mark.parametrize("context", [
    "conduct.review-sources.v1\n[]", MARKER + "{}", MARKER + '["../outside.py"]',
    MARKER + '["C:/outside.py"]', MARKER + '[".env"]',
    MARKER + '["runstats/counts.py","RUNSTATS/counts.py"]',
    MARKER + '[] trailing', MARKER + '[]' + MARKER + '[]',
])
def test_bad_selected_policy_refuses_before_version_or_model(tmp_path, context):
    f = fixture(tmp_path, context=context)
    result, _ = execute(f)
    assert result.outcome == "failed"
    assert _fakegrok.spawns(f.log) == [] and f.held == []


@pytest.mark.parametrize("case", ["hardlink", "binary", "nul", "oversize", "secret", "total"])
def test_unsafe_source_bytes_refuse_before_version_or_model(tmp_path, case):
    f = fixture(tmp_path)
    target = f.work / "runstats/counts.py"
    if case == "hardlink":
        outside = tmp_path / "outside.py"
        outside.write_bytes(b"OUTSIDE-HARDLINK-CANARY")
        target.unlink()
        os.link(outside, target)
        assert os.lstat(target).st_nlink == 2
    elif case == "binary":
        target.write_bytes(b"\xff\xfe\xfd")
    elif case == "nul":
        target.write_bytes(b"def f():\n    return 'bad\0text'\n")
    elif case == "oversize":
        target.write_bytes(b"x" * (128 * 1024 + 1))
    elif case == "secret":
        target.write_bytes(b"token='fake-access-activation-1234'\n")
    else:
        for name in SOURCES:
            (f.work / name).write_bytes(b"x" * (128 * 1024))
    result, _ = execute(f)
    assert result.outcome == "failed" and _fakegrok.spawns(f.log) == [] and f.held == []
    assert "CANARY" not in result.detail and "fake-access" not in result.detail


def test_portal_source_refuses_without_reading_external_bytes(tmp_path):
    from tests.sabotage_fixtures import plant_junction
    f = fixture(tmp_path, context=MARKER + '["portal/code.py"]')
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "code.py").write_bytes(b"EXTERNAL-PORTAL-CANARY")
    portal = f.work / "portal"
    if os.name == "nt":
        plant_junction(portal, outside)
    else:
        portal.symlink_to(outside, target_is_directory=True)
    found = os.lstat(portal)
    assert getattr(found, "st_reparse_tag", 0) or portal.is_symlink()
    try:
        result, _ = execute(f)
        assert result.outcome == "failed" and _fakegrok.spawns(f.log) == []
        assert "EXTERNAL-PORTAL-CANARY" not in result.detail
        assert (outside / "code.py").read_bytes() == b"EXTERNAL-PORTAL-CANARY"
    finally:
        if portal.is_symlink():
            portal.unlink()
        else:
            portal.rmdir()  # remove the junction entry itself, never recursively traverse it


@pytest.mark.parametrize("ref,selected", [("artifact-brief", True), ("source-context", False)])
def test_wrong_ref_and_unselected_initial_context_cannot_read_sources(tmp_path, ref, selected):
    f = fixture(tmp_path, ref=ref, selected=selected)
    result, _ = execute(f)
    _, task = f.held[0]
    assert result.outcome == "succeeded"
    assert b"TASK SOURCE FILES" not in task
    assert b"return len(rows)" not in task and "# Проверка".encode() not in task


@pytest.mark.parametrize("generated,ref,context", [
    (True, "source-context", MARKER + '["runstats/counts.py"]'),
    (False, "artifact-brief", MARKER + '["runstats/counts.py"]'),
    (False, "source-context", "Legacy context, without a policy marker."),
])
def test_non_authoritative_context_preserves_the_literal_legacy_frame(
        tmp_path, generated, ref, context):
    from conductor.command.adapters.deep_commands import DeepReviewArgs
    from conductor.command.adapters.review_sources import materialize
    f = fixture(tmp_path)
    document = ArtifactDocument("context", ref, "run", NOW, "text/plain", context,
                                source_action_id="model-action" if generated else None)
    args = DeepReviewArgs("work-001", [ref], "answer", "quality", work_scope="one")
    with ownership.acquire_owner(f.root):
        assert materialize(f.adapter, args, (document,), "LEGACY-BYTES\r\n") == (
            "LEGACY-BYTES\r\n", None)


def test_preflight_change_of_unselected_file_cannot_rebind_the_materialized_tree(tmp_path):
    f = fixture(tmp_path)
    original = f.runner.run
    changed = []

    def change_during_version(spec):
        if "--version" in spec.argv:
            (f.work / "unused.py").write_bytes(b"CHANGED-AFTER-SOURCE-MATERIALIZATION")
            changed.append(True)
        return original(spec)

    f.runner.run = change_during_version
    result, _ = execute(f)
    assert changed == [True]
    assert result.outcome == "failed" and result.detail == "adapter reported failed"
    assert f.held == [] and _fakegrok.prompt_spawns(f.log) == []
