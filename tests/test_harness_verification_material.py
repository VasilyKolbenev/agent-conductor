"""The checker's claim and byte reader are narrower than the doer's work tree."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from conductor.command.adapters import harness_workspace as workspace_module
from conductor.command.adapters.harness_workspace import (
    FILE_BUDGET, HarnessWorkspace, WorkspaceNotContained,
)
from tests import sabotage_fixtures


def _workspace(tmp_path):
    return HarnessWorkspace.at(tmp_path, home_dir=".homes", marker_dir=".markers")


def test_checker_claims_are_disjoint_from_doer_legacy_and_other_run_claims(tmp_path):
    workspace = _workspace(tmp_path)
    workspace.claim("run-1", "action-1")
    (tmp_path / ".markers" / "action-1.marker").write_text("legacy", encoding="utf-8")
    assert not workspace.is_verification_claimed("run-1", "action-1")
    workspace.claim_verification("run-1", "action-1")
    assert workspace.is_verification_claimed("run-1", "action-1")
    assert not workspace.is_verification_claimed("run-2", "action-1")
    assert (tmp_path / ".markers" / "run-1" / "verification" / "action-1.marker").read_text() == "action-1"
    with pytest.raises(WorkspaceNotContained, match="already claimed"):
        workspace.claim_verification("run-1", "action-1")
    fresh = _workspace(tmp_path)
    assert fresh.is_verification_claimed("run-1", "action-1")


@pytest.mark.parametrize("value", ("", ".", "..", "../outside", "a/b", "a\\b", "a:b"))
def test_both_checker_marker_components_pass_the_containment_door(tmp_path, value):
    workspace = _workspace(tmp_path)
    for run_id, action_id in ((value, "action-1"), ("run-1", value)):
        with pytest.raises(WorkspaceNotContained):
            workspace.claim_verification(run_id, action_id)
        with pytest.raises(WorkspaceNotContained):
            workspace.is_verification_claimed(run_id, action_id)
    assert tuple(tmp_path.iterdir()) == ()


def test_the_reader_lists_all_files_but_inlines_only_small_changed_bytes(tmp_path):
    workspace = _workspace(tmp_path)
    work = workspace.work_dir("item-1")
    (work / "changed.txt").write_bytes(b"changed\r\nbytes\n")
    (work / "unchanged.txt").write_bytes(b"not prompt material")
    (work / "large.txt").write_bytes(b"L" * (FILE_BUDGET + 1))
    (work / "empty.txt").write_bytes(b"")
    foreign = workspace.work_dir("other-item") / "private.txt"
    foreign.write_bytes(b"another work item")
    changed = ("item-1/changed.txt", "item-1/large.txt", "item-1/empty.txt")
    tree, contents = workspace.read_work_tree("item-1", changed)
    assert tree == {key: value for key, value in workspace.digest_work_tree().items()
                    if key.startswith("item-1/")}
    assert contents == {"item-1/changed.txt": b"changed\r\nbytes\n", "item-1/empty.txt": b""}
    assert tree["item-1/large.txt"] == hashlib.sha256(b"L" * (FILE_BUDGET + 1)).hexdigest()


@pytest.mark.parametrize("size", (FILE_BUDGET - 1, FILE_BUDGET, FILE_BUDGET + 1))
def test_the_file_ceiling_is_in_bytes_and_inclusive(tmp_path, size):
    workspace = _workspace(tmp_path)
    path = workspace.work_dir("item") / "answer"
    content = b"\xff" * size
    path.write_bytes(content)
    tree, contents = workspace.read_work_tree("item", ("item/answer",))
    assert tree == {"item/answer": hashlib.sha256(content).hexdigest()}
    assert contents == ({"item/answer": content} if size <= FILE_BUDGET else {})


@pytest.mark.parametrize("budget", (-1, FILE_BUDGET + 1, True, 1.5))
def test_a_caller_cannot_widen_the_file_content_bound(tmp_path, budget):
    with pytest.raises(ValueError, match="budget"):
        _workspace(tmp_path).read_work_tree("item", (), budget)


def test_regular_files_are_read_in_bounded_chunks(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    path = workspace.work_dir("item") / "large"
    content = b"x" * (3 * FILE_BUDGET)
    path.write_bytes(content)
    original = Path.open
    reads = []

    class _Bounded:
        def __enter__(self):
            self.source = original(path, "rb")
            return self

        def __exit__(self, *args):
            self.source.close()

        def fileno(self):
            return self.source.fileno()

        def read(self, size=-1):
            assert 0 <= size <= FILE_BUDGET + 1
            reads.append(size)
            return self.source.read(size)

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: _Bounded())
    tree, contents = workspace.read_work_tree("item", ("item/large",))
    assert tree["item/large"] == hashlib.sha256(content).hexdigest()
    assert reads and contents == {}


def test_a_replaced_file_identity_is_refused_before_any_read(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    path = workspace.work_dir("item") / "answer"
    path.write_bytes(b"must not be read under a different identity")
    real_fstat = os.fstat
    original_open = Path.open

    class _MustNotRead:
        def __enter__(self):
            self.source = original_open(path, "rb")
            return self

        def __exit__(self, *args):
            self.source.close()

        def fileno(self):
            return self.source.fileno()

        def read(self, *args):
            pytest.fail("read bytes before comparing the opened identity")

    def replaced(fd):
        values = list(real_fstat(fd))
        values[1] += 1
        return os.stat_result(values)

    monkeypatch.setattr(workspace_module.os, "fstat", replaced)
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: _MustNotRead())
    with pytest.raises(WorkspaceNotContained):
        workspace.read_work_tree("item", ("item/answer",))


def test_an_aliased_file_is_listed_by_kind_and_never_opened(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside secret")
    link = workspace.work_dir("item") / "linked.txt"
    try:
        os.link(outside, link)
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: pytest.fail("opened a hard link"))
    tree, contents = workspace.read_work_tree("item", ("item/linked.txt",))
    assert tree == {"item/linked.txt": "hard_link"} and contents == {}


def test_a_portal_is_listed_without_walking_or_opening_its_target(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"outside secret")
    link = workspace.work_dir("item") / "portal"
    try:
        sabotage_fixtures.plant_route_portal(
            link, outside, kind="junction" if os.name == "nt" else "symlink")
    except sabotage_fixtures.SabotageUnavailable as error:
        pytest.skip(str(error))
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: pytest.fail("opened portal bytes"))
    tree, contents = workspace.read_work_tree("item", ("item/portal/secret.txt",))
    assert len(tree) == 1 and "item/portal" in tree
    assert len(tree["item/portal"]) != 64 and contents == {}
