"""R6 reads the accumulated result, not merely the correction's last changed file."""
from dataclasses import replace
import hashlib
import os
from types import SimpleNamespace

import pytest

from conductor.command import accept_capture, seed_stage
from conductor.command.accept_manifest import FileImage, SnapshotRefused, build_snapshot
from conductor.command.accept_snapshot import read_snapshot
from conductor.command.adapters.base import AdapterVerification, Published, VerifierBinding
from conductor.command.adapters.deep_commands import DeepDispatchArgs
from conductor.command.adapters.harness_workspace import FILE_BUDGET, HarnessWorkspace
from conductor.command.adapters.independent_check import CheckFrameError, build_frame
from conductor.command.adapters.independent_transport import IndependentCheckTransport
from conductor.command.adapters.process import ProcessOutcome
from conductor.command.artifact_handoff import ArtifactHandoff
from conductor.command.artifacts import ArtifactDocument
from conductor.command.run_store import RecordConflict, RunStore, snapshot_digest
from conductor.command.seed_record import SeedRecord, write_seed
from tests.git_repo_helpers import commit, git, needs_git, real_reader, repository, snapshot
from tests.test_command_claude_transport import a_request
from tests.test_command_run_store import CONFIG, NOW, a_run
from tests.test_seed_record import a_git_seed, an_empty_seed
from tests.test_independent_check_frame import material

TASK, SCOPE = "task-one", "scope-one"
PREFIX = f"_tasks/{SCOPE}/work-001/"


class Checker(IndependentCheckTransport):
    """Real shared check road; only the model boundary returns a deterministic verdict."""
    _retained, _login_residue = 0, False
    manifest = SimpleNamespace(adapter_id="checker")
    _artifact_document = staticmethod(ArtifactDocument.from_dict)

    def __init__(self, root, store):
        self._workspace = HarnessWorkspace.at(root, home_dir=".checker-home", marker_dir=".checker-markers")
        self._handoff = ArtifactHandoff(store, clock=lambda: NOW, ids=lambda _kind: "proof-one")
        self.frames = []
        self.during_check = lambda: None

    def _begin_road(self):
        pass

    def _sensitive_values(self):
        return ()

    def _dispatch_args(self, args):
        return DeepDispatchArgs.from_dict({key: list(value) if isinstance(value, tuple) else value
                                         for key, value in args.items()})

    def _preflight(self, _request):
        return None

    def _evidence(self):
        return self._workspace.digest_work_tree()

    def _attempt(self, *_args, **kwargs):
        self.frames.append(kwargs["stdin_bytes"])
        self.during_check()
        return ProcessOutcome("completed", 0, b"VERDICT: accept\nchecked", False, 1000, 1,
                              "checker-token", stdin_state="delivered")

    def _verdict_argv(self, *_args):
        raise AssertionError("the model boundary is the only fake")

    def _verification(self, request, state, refs, detail):
        return AdapterVerification(adapter_id="checker", action_id=request.action_id,
                                   state=state, evidence_refs=refs, detail=detail, observed_at=NOW)


def prepared(root, *, seed=None, reader=None, seeded=True):
    config = {**CONFIG, "task": {"id": TASK, "work_scope": SCOPE}}
    store = RunStore(root)
    store.create_run(a_run(config_digest=snapshot_digest(config)), config)
    request = replace(a_request(arguments={**dict(a_request().arguments), "artifact_refs": [],
                                           "work_scope": SCOPE}),
                      run_id="run-001", instance_id="claude-dev")
    store.append(request)
    checker = Checker(root, store)
    if reader is not None:
        checker._handoff._accept_git = reader
    if seed is None:
        seed = SeedRecord.from_dict(an_empty_seed(task_id=TASK, work_scope=SCOPE))
    if seeded:
        write_seed(root, seed)
    work = checker._workspace.work_dir("work-001", SCOPE)
    return checker, store, request, work


def published(checker, changed=("b.py",)):
    return Published(None, tuple(PREFIX + path for path in changed),
                     checker._evidence(), (), (), "Keep all accumulated changes correct.")


def frame(checker, request, value):
    return checker._check_frame(request, checker._dispatch_args(request.arguments), value)


def test_unseeded_legacy_item_keeps_attempt_check_but_cannot_claim_seeded_r6(tmp_path):
    checker, _, request, _ = prepared(tmp_path, seeded=False)
    request = replace(request, arguments={**dict(request.arguments), "work_item_id": "item-legacy"})
    work = checker._workspace.work_dir("item-legacy", SCOPE)
    (work / "b.py").write_bytes(b"done")
    changed = (f"_tasks/{SCOPE}/item-legacy/b.py",)
    value = Published(None, changed, checker._evidence(), (), (), "Check the exact result.")
    result = frame(checker, request, value)
    assert b'{"content":"done","encoding":"utf-8","path":"_tasks/scope-one/item-legacy/b.py"}' in result.payload
    assert result.work_tree_digest is result.accept_manifest_digest is result.work_modes is None
    # A real standing seed makes the canonical work item mandatory; legacy fallback
    # cannot borrow a different item's saved base or publish acceptance evidence.
    write_seed(tmp_path, SeedRecord.from_dict(an_empty_seed(task_id=TASK, work_scope=SCOPE)))
    with pytest.raises(CheckFrameError, match="material_unavailable"):
        frame(checker, request, value)
    assert not (tmp_path / "conductor/accept").exists()


@needs_git
def test_accumulation_uses_seed_base_after_head_moves_and_reads_each_live_file_once(tmp_path, monkeypatch):
    root, reader = repository(tmp_path), real_reader(tmp_path)
    commit(root, {"a.py": b"old a", "gone": b"deleted", "fixed": b"unchanged"})
    base = seed_stage.read_base(root, reader)
    seed = seed_stage.stage_from_git(root, reader, task_id=TASK, work_scope=SCOPE,
        work_item_id="work-001", base=base, include_agent_instructions=False, staged_at=NOW)
    seed_stage.move_staged(root, seed)
    checker, _, request, work = prepared(root, seed=seed, reader=reader)
    (work / "a.py").write_bytes(b"change from rejected attempt")
    (work / "b.py").write_bytes(b"correction now")
    (work / "gone").unlink()
    commit(root, {"a.py": b"owner moved HEAD", "elsewhere": b"owner"}, "later owner work")
    git_before = snapshot(root / ".git")
    original, reads = HarnessWorkspace.capture_work_tree, []
    def counted(subject, *args, **kwargs):
        reads.append(args)
        return original(subject, *args, **kwargs)
    monkeypatch.setattr(HarnessWorkspace, "capture_work_tree", counted)
    result = frame(checker, request, published(checker))
    assert len(reads) == 1
    assert b"ACCUMULATED RESULT" in result.payload
    assert b"change from rejected attempt" in result.payload and b"correction now" in result.payload
    assert b'"state":"deleted"' in result.payload and b"owner moved HEAD" not in result.payload
    saved = read_snapshot(root, request.run_id, result.accept_manifest_digest, object_format=base.object_format)
    assert [(row.path, row.state) for row in saved.rows] == [
        ("a.py", "modified"), ("b.py", "added"), ("gone", "deleted")]
    assert snapshot(root / ".git") == git_before


def test_frame_uses_saved_bytes_and_evidence_binds_both_digests(tmp_path, monkeypatch):
    checker, store, request, work = prepared(tmp_path)
    (work / "b.py").write_bytes(b"checked bytes")
    value = published(checker)
    with checker._workspace.owned():
        answer = checker._check_owned(request, VerifierBinding("independent", "checker", None), value)
    assert answer.state == "verified" and len(checker.frames) == 1
    evidence = next(row.value for row in store.read(request.run_id).records if row.kind == "evidence")
    assert set(evidence.extra) == {"work_tree_digest", "accept_manifest_digest"}
    saved = read_snapshot(tmp_path, request.run_id, evidence.extra["accept_manifest_digest"], object_format="sha1")
    assert saved.blobs[saved.rows[0].sha256] == b"checked bytes"
    exact = dict(adapter_id="checker", digest=evidence.digest, verifier_instance_id="independent",
                 **dict(evidence.extra))
    assert checker._handoff.record_dispatch(request, **exact) == evidence
    for name in evidence.extra:
        with pytest.raises(RecordConflict, match="another snapshot"):
            checker._handoff.record_dispatch(request, **{**exact, name: "sha256:" + "f" * 64})
        with pytest.raises(RecordConflict, match="another snapshot"):
            checker._handoff.record_dispatch(request, **{**exact, "digest": None,
                                                        name: "sha256:" + "f" * 64})
    legacy = replace(evidence, extra={})
    with pytest.raises(RecordConflict, match="another snapshot"):
        checker._handoff._hold_evidence(legacy, request, "checker", evidence.digest,
                                      verifier_instance_id="independent", **dict(evidence.extra))
    capture = checker._handoff.capture_dispatch
    def changed_after_capture(*args, **kwargs):
        result = capture(*args, **kwargs)
        (work / "b.py").write_bytes(b"unreviewed later bytes")
        return result
    monkeypatch.setattr(checker._handoff, "capture_dispatch", changed_after_capture)
    fresh_frame = frame(checker, request, value)
    assert b"checked bytes" in fresh_frame.payload and b"unreviewed later bytes" not in fresh_frame.payload


def test_checker_content_change_leaves_no_evidence(tmp_path):
    checker, store, request, work = prepared(tmp_path)
    (work / "b.py").write_bytes(b"before")
    value = published(checker)
    checker.during_check = lambda: (work / "b.py").write_bytes(b"after")
    with checker._workspace.owned():
        answer = checker._check_owned(request, VerifierBinding("independent", "checker", None), value)
    assert answer.detail == "tree_changed"
    assert not [row for row in store.read(request.run_id).records if row.kind == "evidence"]


def test_wrong_task_scope_refuses_before_capture_or_git(tmp_path, monkeypatch):
    checker, _, request, _ = prepared(tmp_path)
    monkeypatch.setattr(HarnessWorkspace, "capture_work_tree", lambda *_a, **_kw: pytest.fail("foreign read"))
    monkeypatch.setattr(checker._handoff, "_snapshot_git", lambda: pytest.fail("foreign Git read"))
    args = replace(checker._dispatch_args(request.arguments), work_scope="foreign")
    with pytest.raises(CheckFrameError, match="material_unavailable"):
        checker._handoff.capture_dispatch(request, args, checker._workspace)
    assert not (tmp_path / "conductor/accept").exists()


def test_hardlinked_result_refuses_before_any_snapshot_publication(tmp_path):
    checker, _, request, work = prepared(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"foreign")
    os.link(outside, work / "b.py")
    with pytest.raises(CheckFrameError, match="irregular_result"):
        frame(checker, request, published(checker))
    assert not (tmp_path / "conductor/accept").exists() and outside.read_bytes() == b"foreign"


def test_semantic_secret_in_earlier_change_is_neither_saved_nor_framed(tmp_path):
    checker, _, request, work = prepared(tmp_path)
    secret = b'old-secret"\\\xff'
    (work / "earlier").write_bytes(secret)
    (work / "b.py").write_bytes(b"latest")
    with pytest.raises(CheckFrameError, match="frame_env_echo"):
        frame(checker, request, replace(published(checker), sensitive=(secret,)))
    assert not (tmp_path / "conductor/accept").exists()


def test_empty_seed_needs_no_git_and_does_not_inherit_global_object_format(tmp_path, monkeypatch):
    checker, _, request, work = prepared(tmp_path)
    monkeypatch.setattr(checker._handoff, "_snapshot_git", lambda: pytest.fail("Git is absent"))
    monkeypatch.setenv("GIT_DEFAULT_HASH", "sha256")
    (work / "b.py").write_bytes(b"new")
    result = frame(checker, request, published(checker))
    saved = read_snapshot(tmp_path, request.run_id, result.accept_manifest_digest, object_format="sha1")
    assert len(saved.rows[0].git_oid) == 40
    with pytest.raises(SnapshotRefused):
        read_snapshot(tmp_path, request.run_id, result.accept_manifest_digest, object_format="sha256")


def test_seed_skipped_subtree_is_not_a_deletion_but_cannot_be_reintroduced(tmp_path):
    from tests.git_repo_helpers import Script, said
    seed = SeedRecord.from_dict(a_git_seed(task_id=TASK, work_scope=SCOPE,
        skipped=[{"path": "omitted", "reason": "submodule"}], agent_instructions_skipped=[]))
    listing = b"160000 commit " + b"a" * 40 + b" -\tomitted\0"
    reader = Script(said(b"sha1"), said(seed.base_tree.encode()), said(listing))
    checker, _, request, work = prepared(tmp_path, seed=seed, reader=reader)
    (work / "b.py").write_bytes(b"new")
    result = frame(checker, request, published(checker))
    saved = read_snapshot(tmp_path, request.run_id, result.accept_manifest_digest, object_format="sha1")
    assert [row.path for row in saved.rows] == ["b.py"]
    reader.answers.extend([said(b"sha1"), said(seed.base_tree.encode()), said(listing)])
    (work / "omitted").mkdir()
    (work / "omitted/new").write_bytes(b"forbidden")
    with pytest.raises(CheckFrameError, match="reserved_path"):
        frame(checker, request, published(checker))


def test_format_mismatch_refuses_before_work_bytes(tmp_path, monkeypatch):
    from tests.git_repo_helpers import Script, said
    seed = SeedRecord.from_dict(a_git_seed(task_id=TASK, work_scope=SCOPE))
    checker, _, request, _ = prepared(tmp_path, seed=seed, reader=Script(said(b"sha256")))
    monkeypatch.setattr(HarnessWorkspace, "capture_work_tree", lambda *_a, **_kw: pytest.fail("read"))
    with pytest.raises(CheckFrameError, match="object_format_changed"):
        frame(checker, request, published(checker))


def test_empty_seed_uses_existing_repository_format_without_reading_head(tmp_path):
    from tests.git_repo_helpers import Script, said
    reader = Script(said(b"sha256"))
    checker, _, request, work = prepared(tmp_path, reader=reader)
    (tmp_path / ".git").mkdir()
    (work / "b.py").write_bytes(b"new")
    result = frame(checker, request, published(checker))
    saved = read_snapshot(tmp_path, request.run_id, result.accept_manifest_digest, object_format="sha256")
    assert len(saved.rows[0].git_oid) == 64
    assert len(reader.calls) == 1 and reader.calls[0][0][-1] == "--show-object-format"


@pytest.mark.skipif(os.name != "posix", reason="Windows does not derive Git mode from chmod")
def test_checker_mode_change_alone_cannot_receive_evidence(tmp_path):
    checker, store, request, work = prepared(tmp_path)
    path = work / "b.py"
    path.write_bytes(b"same bytes")
    path.chmod(0o644)
    value = published(checker)
    checker.during_check = lambda: path.chmod(0o755)
    with checker._workspace.owned():
        answer = checker._check_owned(request, VerifierBinding("independent", "checker", None), value)
    assert answer.detail == "tree_changed"
    assert not [row for row in store.read(request.run_id).records if row.kind == "evidence"]


def test_large_listing_summarizes_only_unchanged_rows_and_keeps_small_tree_digest():
    from conductor.command.contracts import _content_digest
    request, value = a_request(), material()
    content = b"x" * FILE_BUDGET
    path = value.changed[0]
    one = {path: hashlib.sha256(content).hexdigest()}
    small = build_frame(request, value, one, {path: content})
    assert small.digest == _content_digest({"action_id": request.action_id,
        "input_artifact_ids": [], "changed": list(value.changed), "tree": one})
    many = {**one, **{f"work-001/unchanged-{n}": "b" * 64 for n in range(1200)}}
    large = build_frame(request, value, many, {path: content})
    assert b"WORK TREE SUMMARY" in large.payload and b"CHANGED TREE ROWS" in large.payload
    assert content in large.payload and b"unchanged-1199" not in large.payload
    assert large.digest != small.digest


def test_accumulated_content_exceeding_whole_frame_refuses_without_truncation():
    accumulated = build_snapshot({}, {"earlier": FileImage(b"a" * (256 * 1024))}, object_format="sha1")
    with pytest.raises(CheckFrameError, match="frame_over_limit"):
        build_frame(a_request(), material(), {}, {}, accumulated=accumulated)
    path = material().changed[0]
    with pytest.raises(CheckFrameError, match="frame_over_limit"):
        build_frame(a_request(), material(), {path: "a" * 64}, {})


def test_tree_seal_binds_unchanged_file_modes_and_bytes():
    image = FileImage(b"same", "100644")
    before = accept_capture.tree_digest({"a": image})
    assert accept_capture.tree_digest({"a": replace(image, mode="100755")}) != before
    assert accept_capture.tree_digest({"a": FileImage(b"different")}) != before
