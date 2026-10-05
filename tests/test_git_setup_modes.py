"""The Git mode of each file and the versioned digest of what the person is shown (OD-7).

A `chmod` after the shown preview and before the confirmation must not leave the digest equal:
the executable bit is part of what is shown and sealed, decided by one function whose value
travels to the tree build.
"""
import json
import os
import re
from pathlib import Path

import pytest

from conductor.command import git_setup_first_records as records
from conductor.command import git_setup_modes as modes
from conductor.command import git_setup_snapshot as snapshot_module
from conductor.command.accept_manifest import sha256
from conductor.command.project_git import GitReadFailed
from tests.git_repo_helpers import git, needs_git, real_reader, repository
from tests.test_git_setup import preview, reason, unborn

SRC = Path(__file__).resolve().parents[1] / "src" / "conductor"
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="the execute bit is a POSIX fact")
ROWS = [
    {"path": "a.txt", "length": 6, "sha256": "sha256:" + "a" * 64, "git_oid": "1" * 40,
     "git_mode": "100644"},
    {"path": "run.sh", "length": 9, "sha256": "sha256:" + "b" * 64, "git_oid": "2" * 40,
     "git_mode": "100755"},
]


def legacy_digest(rows):
    """The digest of version 1: the bare list, with no version and no mode in the string."""
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return sha256(raw.encode("ascii"))


def rows_of(project, mode="snapshot"):
    return preview(project, mode).payload["setup"]


def row_named(value, path):
    return next(row for row in value["files"] if row["path"] == path)


def make_executable(project, name="run.sh", data=b"echo hi\n"):
    """A file whose stat carries the owner execute bit."""
    path = project.root / name
    path.write_bytes(data)
    path.chmod(0o755)
    return path


@pytest.mark.parametrize("st_mode, expected", [
    (0o100644, "100644"), (0o100755, "100755"), (0o100744, "100755"), (0o100700, "100755"),
    (0o100655, "100644"), (0o100611, "100644"), (0o100600, "100644")])
def test_effective_git_mode_follows_core_filemode_and_only_the_owner_execute_bit(
        st_mode, expected):
    assert modes.effective_git_mode(True, st_mode) == expected
    assert modes.effective_git_mode(False, st_mode) == "100644"


@needs_git
def test_core_filemode_reads_the_repository_setting_and_an_absent_one_is_true(tmp_path):
    repo, reader = repository(tmp_path), real_reader(tmp_path)
    for written, expected in (("false", False), ("true", True), ("no", False), ("yes", True)):
        git("config", "core.filemode", written, cwd=repo)
        assert modes.core_filemode(repo, reader) is expected, written
    git("config", "--unset", "core.filemode", cwd=repo)
    assert modes.core_filemode(repo, reader) is True
    git("config", "core.filemode", "banana", cwd=repo)
    with pytest.raises(GitReadFailed) as caught:
        modes.core_filemode(repo, reader)
    assert caught.value.code == "git_failed"


@needs_git
def test_preview_rows_carry_git_mode_and_the_digest_is_over_the_versioned_list(tmp_path):
    project = unborn(tmp_path)
    (project.root / "a.txt").write_bytes(b"alpha\n")
    (project.root / "dir").mkdir()
    (project.root / "dir" / "b.txt").write_bytes(b"beta\n")
    value = rows_of(project)
    assert [row["path"] for row in value["files"]] == ["a.txt", "dir/b.txt"]
    for row in value["files"]:
        assert set(row) == {"path", "length", "sha256", "git_oid", "git_mode"}
        assert row["git_mode"] in {"100644", "100755"}
    raw = json.dumps({"digest_version": 2, "files": value["files"]}, sort_keys=True,
                     ensure_ascii=True, separators=(",", ":"))
    assert value["digest_version"] == 2 and value["paths_digest"] == sha256(raw.encode("ascii"))
    assert value["paths_digest"] != legacy_digest(value["files"])
    empty = rows_of(project, "empty")
    assert empty["files"] == [] and empty["digest_version"] == 2
    assert empty["paths_digest"] == modes.paths_digest([]) != legacy_digest([])


def test_a_version_one_digest_can_never_equal_a_version_two_digest():
    for rows in ([], ROWS[:1], ROWS):
        assert modes.paths_digest(rows) != legacy_digest(rows)
        assert modes.canonical(rows).startswith(b'{"digest_version":2,"files":')
    flipped = [{**ROWS[0], "git_mode": "100755"}, ROWS[1]]
    assert modes.paths_digest(flipped) != modes.paths_digest(ROWS)


def test_the_version_of_the_digest_the_op_records_is_the_version_the_preview_seals():
    assert modes.DIGEST_VERSION == records.DIGEST_VERSION == 2


@POSIX_ONLY
@needs_git
def test_a_mode_only_change_after_the_preview_changes_the_digest_and_the_shown_mode(tmp_path):
    project = unborn(tmp_path)
    path = project.root / "tool"
    path.write_bytes(b"#!/bin/sh\n")
    path.chmod(0o644)
    before = rows_of(project)
    path.chmod(0o755)
    after = rows_of(project)
    assert row_named(before, "tool")["git_mode"] == "100644"
    assert row_named(after, "tool")["git_mode"] == "100755"
    assert after["paths_digest"] != before["paths_digest"]
    assert {key: value for key, value in row_named(after, "tool").items() if key != "git_mode"} \
        == {key: value for key, value in row_named(before, "tool").items() if key != "git_mode"}


@POSIX_ONLY
@needs_git
def test_core_filemode_false_shows_100644_for_an_executable_file_and_flipping_it_changes_the_digest(
        tmp_path):
    project = unborn(tmp_path)
    make_executable(project)
    (project.root / "plain.txt").write_bytes(b"plain\n")
    git("config", "core.filemode", "true", cwd=project.root)
    trusted = rows_of(project)
    git("config", "core.filemode", "false", cwd=project.root)
    ignored = rows_of(project)
    assert row_named(trusted, "run.sh")["git_mode"] == "100755"
    assert row_named(ignored, "run.sh")["git_mode"] == "100644"
    assert row_named(trusted, "plain.txt") == row_named(ignored, "plain.txt")
    assert row_named(trusted, "plain.txt")["git_mode"] == "100644"
    assert trusted["paths_digest"] != ignored["paths_digest"]


@needs_git
def test_preview_hands_the_repository_core_filemode_and_the_sealed_mode_to_the_one_decision(
        tmp_path, monkeypatch):
    project = unborn(tmp_path)
    path = project.root / "a.txt"
    path.write_bytes(b"alpha\n")
    seen, real = [], snapshot_module.effective_git_mode

    def record(filemode, st_mode):
        seen.append((filemode, st_mode))
        return real(filemode, st_mode)
    monkeypatch.setattr(snapshot_module, "effective_git_mode", record)
    for written, expected in (("false", False), ("true", True)):
        git("config", "core.filemode", written, cwd=project.root)
        seen.clear()
        assert [row["path"] for row in rows_of(project)["files"]] == ["a.txt"]
        assert seen == [(expected, os.lstat(path).st_mode)], written


@needs_git
def test_a_change_of_core_filemode_without_an_executable_file_leaves_the_digest_alone(tmp_path):
    project = unborn(tmp_path)
    (project.root / "plain.txt").write_bytes(b"plain\n")
    git("config", "core.filemode", "true", cwd=project.root)
    trusted = rows_of(project)
    git("config", "core.filemode", "false", cwd=project.root)
    assert rows_of(project) == trusted


@needs_git
def test_a_mode_that_changes_while_the_preview_is_sealed_refuses_paths_changed(tmp_path):
    project = unborn(tmp_path)
    path = project.root / "moved.txt"
    path.write_bytes(b"before")
    original = project.api._project_git
    calls = []

    def flip_the_mode_after_the_hash(args, *positional, **keywords):
        result = original(args, *positional, **keywords)
        if "hash-object" in args and not calls:
            calls.append(args)
            path.chmod(0o444)           # POSIX: another mode; Windows: the read-only attribute
        return result
    project.api._project_git = flip_the_mode_after_the_hash
    try:
        assert reason(preview(project)) == "paths_changed"
    finally:
        path.chmod(0o666)
    assert calls


def test_effective_git_mode_has_exactly_one_caller_in_src():
    callers = {}
    for path in sorted(SRC.rglob("*.py")):
        found = len(re.findall(r"\beffective_git_mode\(", path.read_text(encoding="utf-8")))
        if found:
            callers[path.name] = found
    assert callers == {"git_setup_modes.py": 1, "git_setup_snapshot.py": 1}
