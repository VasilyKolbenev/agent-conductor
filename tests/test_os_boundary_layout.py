"""The instrument the OS-boundary checks judge by: a snapshot that can say "changed".

A denial proves nothing unless the same operation, run without the boundary, is seen
to change the tree. These tests hold the two halves that do not depend on an OS
mechanism: the snapshot notices every kind of change the checks care about, and the
POSIX operation table really changes its protected root when nothing confines it (the
Windows table has its own unconfined control beside its tests). Nothing here starts a
sandbox.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

from tests.os_boundary_layout import (
    OPERATIONS,
    make_layout,
    operations_for,
    render,
    snapshot,
)

POSIX_SH = "/bin/sh"


def test_snapshot_reports_changed_content_a_new_name_a_removed_name_and_a_new_link(tmp_path):
    layout = make_layout(tmp_path)
    root = layout.source
    before = snapshot(root)
    assert snapshot(root) == before

    (root / "file.txt").write_bytes(b"changed\n")
    assert snapshot(root) != before
    (root / "file.txt").write_bytes(b"original source\n")
    assert snapshot(root) == before

    (root / "new.txt").write_bytes(b"x")
    assert snapshot(root) != before
    (root / "new.txt").unlink()
    assert snapshot(root) == before

    os.link(root / "file.txt", layout.tmp / "hard-link")
    assert snapshot(root) != before, "a second name for a protected file must be noticed"
    (layout.tmp / "hard-link").unlink()
    assert snapshot(root) == before

    (root / "sub" / "inner.txt").unlink()
    assert snapshot(root) != before


def test_snapshot_of_a_missing_root_differs_from_the_tree_that_was_there(tmp_path):
    layout = make_layout(tmp_path)
    before = snapshot(layout.work)
    layout.work.rename(tmp_path / "work-moved")
    assert snapshot(layout.work) != before


def test_the_fake_git_store_exists_in_the_source_tree_and_not_in_the_work_copy(tmp_path):
    layout = make_layout(tmp_path)
    assert (layout.source / ".git" / "HEAD").is_file()
    assert (layout.source / ".git" / "objects" / "ab" / "cdef0123").is_file()
    assert not (layout.work / ".git").exists()
    for name in ("file.txt", "sub/inner.txt"):
        assert (layout.source / name).is_file() and (layout.work / name).is_file()


def test_every_operation_has_a_body_for_each_os_and_no_token_survives_rendering(tmp_path):
    layout = make_layout(tmp_path)
    assert len(OPERATIONS) >= 15
    for operation in OPERATIONS:
        assert operation.windows and operation.posix, operation.name
        for steps in (operation.windows, operation.posix):
            for step in steps:
                left = re.findall(r"@[A-Z]+@", render(step.body, layout.tokens(operation.roots[0])))
                assert left == [], (operation.name, left)


def test_the_git_operations_apply_to_the_source_tree_only():
    source_only = {op.name for op in OPERATIONS if op.roots == ("source",)}
    assert {"git_overwrite_head", "git_delete_head", "git_rename_head",
            "git_delete_object", "git_delete_store", "git_rename_store"} <= source_only
    both = {op.name for op in operations_for("work")}
    assert not any(name.startswith("git_") for name in both)
    assert {"create_file", "overwrite_file", "delete_file", "rename_root"} <= both


@pytest.mark.skipif(os.name == "nt", reason="needs a POSIX /bin/sh: this table is the POSIX one")
@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
def test_each_posix_operation_run_unconfined_changes_its_protected_root(operation, tmp_path):
    layout = make_layout(tmp_path)
    root = layout.root(operation.roots[0])
    before = snapshot(root)
    tokens = layout.tokens(operation.roots[0])
    for step in operation.posix:
        assert step.tool == "sh"
        subprocess.run([POSIX_SH, "-c", render(step.body, tokens)], check=False, timeout=30,
                       capture_output=True)
    assert snapshot(root) != before, f"{operation.name} did not change {root}: not a probe"
