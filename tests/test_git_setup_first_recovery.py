"""Recovery of the first commit at every write boundary (plan Task 8; rulings OD-3, OD-4).

A crash is made on purpose: a performer of the driver does its effect and then fails like a
process that died (`crash_after`), so what is left is exactly what a crash after that effect
leaves. The exact repeat of the same confirmation must then finish the operation from what the
repository and the records show, whatever the working folder says by then. Two tests are rows of
gate G-old (row 8) and run with the isolated Git 2.31 as the reader and as the owner's own Git
when `CONDUCT_OLD_GIT` names it, in both modes and both object formats; the others use the
current reader. The route's confirm door is held open by `confirm_door` until it opens for real.
"""
from __future__ import annotations

import errno
import json
import os

import pytest

from conductor.command import git_setup_first_lock as lock_module
from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_first_index import verify
from conductor.command.project_git import GitAnswer
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crash_after, crashed, op_file, project, terms_of)
from tests.git_first_readers import READERS
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import (
    an_owner_index, install_files, no_receipt, own_leftovers, text, trunk_exists)
from tests.test_git_setup_first_driver import an_operation

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
FILES = {"a.txt": b"one\n", "docs/b.md": b"two\n", "owner.txt": b"mine\n"}
GRID = [("snapshot", "sha1"), ("snapshot", "sha256"), ("empty", "sha1"), ("empty", "sha256")]
for_every_reader = pytest.mark.parametrize("which", READERS)
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])
in_every_combination = pytest.mark.parametrize("mode, fmt", GRID)
CRASHES = ["_do_take_lock", "_do_mark_locked", "_do_move_ref", "_do_mark_ref_moved",
           "_do_install_index", "_do_finish", "records.start"]
PLANTS = ("nothing", "empty", "foreign_index", "unmarked_owner_bytes", "another_operations_bytes")
CASES = [(plant, mode, fmt) for plant in PLANTS for mode, fmt in GRID
         if not (plant == "another_operations_bytes" and mode == "empty")]
UNTRACKED = "?? a.txt\n?? docs/\n?? owner.txt"


def expected_status(mode):
    """`git status --porcelain` once the first commit stands: nothing for a snapshot, the
    untracked files for the empty commit."""
    return "" if mode == "snapshot" else UNTRACKED


def git_path(p, name):
    return p.root / ".git" / name


def own_copies(p):
    """The private copies of an operation that stand in `.git`."""
    return list((p.root / ".git").glob("conduct-first-index-*"))


def stage_of(p):
    return json.loads(op_file(p).read_text())["stage"]


def commit_of(p):
    return json.loads(op_file(p).read_text())["commit"]


def crash_at(monkeypatch, p, label, mode, digest):
    """`crashed` for a label: a performer of the driver, or the start of the records."""
    if label == "records.start":
        return crashed(monkeypatch, p, "start", mode, digest, owner=records)
    return crashed(monkeypatch, p, label, mode, digest)


def watch_the_install_bytes(monkeypatch):
    """The install bytes of the operation, taken when the records publish them."""
    seen, real = [], records.start

    def watching(root, op, data):
        seen.append(data)
        return real(root, op, data)

    monkeypatch.setattr(records, "start", watching)
    return seen


def finished_once(p, mode, installed, config):
    """What the exact repeat leaves after any crash: one commit, one move of the ref, the stored
    bytes installed, none of the product's own files left, the owner's files and config kept."""
    assert text(p, "rev-list", "--count", "HEAD") == "1"
    assert len(p.spy.argv("update-ref")) == 1
    assert own_leftovers(p) == []
    assert text(p, "status", "--porcelain") == expected_status(mode)
    assert git_path(p, "config").read_bytes() == config
    assert [(p.root / name).read_bytes() for name in FILES] == list(FILES.values())
    assert git_path(p, "index").read_bytes() == installed
    assert os.lstat(git_path(p, "index")).st_nlink == 1


# --- gate row 8: the lock is proved by bytes -----------------------------------------------------


def owners_bytes_for_the_tree(p, tmp_path, mode):
    """The index file the owner's own commands write for the tree of this mode."""
    scratch, env = tmp_path / "owner-made-index", {}
    env["GIT_INDEX_FILE"] = str(scratch)
    if mode == "empty":
        p.git("read-tree", "--empty", cwd=p.root, env=env)
    else:
        p.git("add", "-A", cwd=p.root, env=env)
        p.git("write-tree", cwd=p.root, env=env)
    return scratch.read_bytes()


def planted_bytes(p, tmp_path, plant, mode, fmt, which):
    """The bytes of the lock that replaces the product's own after its crash."""
    if plant == "empty":
        return b""
    if plant == "foreign_index":
        return an_owner_index(p, tmp_path)
    if plant == "unmarked_owner_bytes":
        return owners_bytes_for_the_tree(p, tmp_path, mode)
    twin = project(tmp_path, FILES, name="twin", which=which, fmt=fmt)
    return an_operation(twin)[1].install


@for_every_reader
@pytest.mark.parametrize("plant, mode, fmt", CASES)
def test_first_commit_proves_its_lock_by_bytes_and_never_removes_an_empty_or_foreign_lock(
        tmp_path, monkeypatch, which, plant, mode, fmt):
    p = project(tmp_path, FILES, which=which, fmt=fmt)
    digest, lock = terms_of(p, mode), git_path(p, "index.lock")
    crashed(monkeypatch, p, "_do_take_lock", mode, digest)
    assert lock.exists() and stage_of(p) == "prepared"      # the gap: locked, `locked` not written
    if plant == "nothing":
        assert confirm(p, mode, digest=digest).status == 201
        assert not lock.exists() and own_leftovers(p) == []
        assert text(p, "status", "--porcelain") == expected_status(mode)
        return
    data = planted_bytes(p, tmp_path, plant, mode, fmt, which)
    lock.unlink()
    lock.write_bytes(data)
    stamp = (os.lstat(lock).st_ino, os.lstat(lock).st_mtime_ns)
    assert reason(confirm(p, mode, digest=digest)) == "index_locked"
    assert lock.read_bytes() == data
    assert (os.lstat(lock).st_ino, os.lstat(lock).st_mtime_ns) == stamp
    assert not own_copies(p) and stage_of(p) == "prepared"
    assert not trunk_exists(p) and not git_path(p, "index").exists() and no_receipt(p)


# --- gate row 8: the matrix of faults ------------------------------------------------------------


@for_every_reader
@in_every_combination
@pytest.mark.parametrize("crash", CRASHES)
def test_first_commit_resumes_after_a_fault_at_every_write_boundary(
        tmp_path, monkeypatch, which, mode, fmt, crash):
    p = project(tmp_path, FILES, which=which, fmt=fmt)
    digest, config = terms_of(p, mode), git_path(p, "config").read_bytes()
    installed = watch_the_install_bytes(monkeypatch)
    crash_at(monkeypatch, p, crash, mode, digest)
    again = confirm(p, mode, digest=digest)
    assert again.status == (200 if crash == "_do_finish" else 201), again.payload
    finished_once(p, mode, installed[0], config)


def failing_unlink_once(monkeypatch, wanted):
    """The first removal of a name that `wanted` accepts fails: a move that died between its two
    halves, by link and unlink. Returns the function that restarts the process."""
    real, done = lock_module._unlink, []

    def unlink(path):
        if not done and wanted(os.path.basename(path)):
            done.append(path)
            raise OSError(errno.EIO, "the removal failed")
        real(path)

    monkeypatch.setattr(lock_module, "LINK_MOVES", True)
    monkeypatch.setattr(lock_module, "_unlink", unlink)
    return lambda: monkeypatch.setattr(lock_module, "_unlink", real)


def is_copy(name):
    return name.startswith("conduct-first-index-")


def is_lock(name):
    return name == "index.lock"


def the_move_died(p, monkeypatch, mode, digest, wanted):
    """Confirm with a move whose second half fails: the refusal, and the process restarted."""
    restart = failing_unlink_once(monkeypatch, wanted)
    answer = confirm(p, mode, digest=digest)
    restart()
    assert reason(answer) == "git_failed"


@for_every_reader
@in_every_combination
@pytest.mark.parametrize("names", ["copy_and_lock", "lock_and_index", "copy_lock_and_index"])
def test_first_commit_resumes_from_two_or_three_names_of_one_file_left_by_a_move_that_died(
        tmp_path, monkeypatch, which, mode, fmt, names):
    p = project(tmp_path, FILES, which=which, fmt=fmt)
    digest, config = terms_of(p, mode), git_path(p, "config").read_bytes()
    installed = watch_the_install_bytes(monkeypatch)
    lock, index = git_path(p, "index.lock"), git_path(p, "index")
    the_move_died(p, monkeypatch, mode, digest, is_copy if names == "copy_and_lock" else is_lock)
    if names == "copy_and_lock":                       # the take: the copy and the lock, one inode
        assert own_copies(p) and lock.exists() and os.lstat(lock).st_nlink == 2
    else:                                              # the install: the lock and the index
        assert lock.exists() and index.exists() and os.lstat(lock).st_nlink == 2
    if names == "copy_lock_and_index":                 # not reachable by the driver: made by hand
        os.link(lock, git_path(p, copy_name(p)))
        assert os.lstat(lock).st_nlink == 3
    again = confirm(p, mode, digest=digest)
    assert again.status == 201, again.payload
    finished_once(p, mode, installed[0], config)


def copy_name(p):
    """The name the operation's own copy has: `conduct-first-index-<nonce>`."""
    return "conduct-first-index-" + json.loads(op_file(p).read_text())["nonce"]


def test_a_retry_never_moves_the_ref_twice(tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    p.git("config", "core.logAllRefUpdates", "true", cwd=p.root)
    digest = terms_of(p)
    crashed(monkeypatch, p, "_do_move_ref", "snapshot", digest)
    answers = [confirm(p, digest=digest).status for _ in range(3)]
    assert answers == [201, 200, 200]
    assert len(p.spy.argv("update-ref")) == 1
    log = git_path(p, "logs/refs/heads/trunk").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and log[0].endswith("conduct: first commit")


# --- the ref moved, the lock gone, the index is what decides ----------------------------------


@for_both_modes
def test_first_commit_after_a_moved_ref_retakes_the_lock_and_rechecks_the_index_before_installing(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest, config = terms_of(p, mode), git_path(p, "config").read_bytes()
    installed = watch_the_install_bytes(monkeypatch)
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, digest)
    git_path(p, "index.lock").unlink()                  # the `ref_moved` without lock row
    assert stage_of(p) == "ref_moved" and not git_path(p, "index").exists()
    assert confirm(p, mode, digest=digest).status == 201
    finished_once(p, mode, installed[0], config)


@for_both_modes
def test_an_index_that_appeared_while_the_lock_was_gone_is_index_exists_and_is_left_as_it_is(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, digest)
    commit = commit_of(p)
    git_path(p, "index.lock").unlink()
    p.git("add", "owner.txt", cwd=p.root)               # an index with another tree appears
    theirs, stamp = git_path(p, "index").read_bytes(), os.lstat(git_path(p, "index"))
    assert reason(confirm(p, mode, digest=digest)) == "index_exists"
    assert git_path(p, "index").read_bytes() == theirs
    assert os.lstat(git_path(p, "index")).st_mtime_ns == stamp.st_mtime_ns
    assert not git_path(p, "index.lock").exists() and text(p, "rev-parse", "trunk") == commit
    assert no_receipt(p) and not own_copies(p)


@for_both_modes
def test_an_index_installed_without_its_receipt_is_not_installed_a_second_time(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_install_index", mode, digest)
    index = git_path(p, "index")
    before = (index.read_bytes(), os.lstat(index).st_ino, os.lstat(index).st_mtime_ns)
    assert not git_path(p, "index.lock").exists() and no_receipt(p)
    assert confirm(p, mode, digest=digest).status == 201
    assert (index.read_bytes(), os.lstat(index).st_ino, os.lstat(index).st_mtime_ns) == before
    assert own_leftovers(p) == [] and not no_receipt(p)


WRITERS = ("read-tree", "update-index", "write-tree", "add", "reset", "checkout-index", "checkout",
           "commit", "update-ref")


def writes(args):
    """Whether one Git call of the product may write: an index, a ref, an object."""
    return bool(set(args) & set(WRITERS)) or ("hash-object" in args and "-w" in args)


@for_both_modes
def test_an_equivalent_owner_index_is_left_untouched_and_the_operation_finishes(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, digest)
    git_path(p, "index.lock").unlink()
    p.git(*(("read-tree", "--empty") if mode == "empty" else ("read-tree", "HEAD")), cwd=p.root)
    index = git_path(p, "index")
    before = (index.read_bytes(), os.lstat(index).st_ino, os.lstat(index).st_mtime_ns)
    asked = len(p.spy.calls)
    assert confirm(p, mode, digest=digest).status == 201
    assert (index.read_bytes(), os.lstat(index).st_ino, os.lstat(index).st_mtime_ns) == before
    assert own_leftovers(p) == [] and not no_receipt(p)
    later = [args for args, _ in p.spy.calls[asked:]]
    assert later and not [args for args in later if writes(args)]


def test_an_absent_index_in_mode_empty_is_installed_and_never_read_as_the_empty_tree(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p, "empty")
    crashed(monkeypatch, p, "_do_mark_ref_moved", "empty", digest)
    git_path(p, "index.lock").unlink()
    alone = p.git("diff-index", "--cached", "--quiet", "HEAD", cwd=p.root)
    assert alone.returncode == 0 and not git_path(p, "index").exists()    # Git alone says "equal"
    assert confirm(p, "empty", digest=digest).status == 201
    data = git_path(p, "index").read_bytes()
    assert len(data) not in (65, 89) and verify(data, "sha1").marker is not None


def scripted_diff_index(p, answer, during=None):
    """The product's reader answers its one read of the owner's index with `answer`."""
    inner = p.api._project_git

    def reader(args, *positional, **keywords):
        if "diff-index" in args:
            if during is not None:
                during()
            return answer
        return inner(args, *positional, **keywords)

    p.api._project_git = reader


def an_equivalent_index_stands_and_the_lock_is_gone(monkeypatch, p, mode, digest):
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, digest)
    git_path(p, "index.lock").unlink()
    p.git(*(("read-tree", "--empty") if mode == "empty" else ("read-tree", "HEAD")), cwd=p.root)


UNJUDGEABLE = [
    (GitAnswer(128, b""), "git_failed"), (GitAnswer(2, b""), "git_failed"),
    (GitAnswer(None, b"", timed_out=True), "git_timed_out"),
    (GitAnswer(None, b""), "git_timed_out"),
    (GitAnswer(0, b"", truncated=True), "git_failed")]


@for_both_modes
@pytest.mark.parametrize("answer, word", UNJUDGEABLE)
def test_an_error_a_timeout_or_a_cut_answer_of_the_index_read_is_never_success(
        tmp_path, monkeypatch, mode, answer, word):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    an_equivalent_index_stands_and_the_lock_is_gone(monkeypatch, p, mode, digest)
    before, stamp = snapshot(p.root / ".git"), os.lstat(git_path(p, "index")).st_mtime_ns
    scripted_diff_index(p, answer)
    assert reason(confirm(p, mode, digest=digest)) == word
    assert snapshot(p.root / ".git") == before and no_receipt(p) and op_file(p).exists()
    assert os.lstat(git_path(p, "index")).st_mtime_ns == stamp


def test_an_index_that_changed_between_the_two_looks_of_the_read_is_never_success(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p, "snapshot")
    an_equivalent_index_stands_and_the_lock_is_gone(monkeypatch, p, "snapshot", digest)
    index = git_path(p, "index")
    scripted_diff_index(p, GitAnswer(0, b""), during=lambda: index.write_bytes(b"DIRC changed"))
    assert reason(confirm(p, "snapshot", digest=digest)) == "git_failed"
    assert index.read_bytes() == b"DIRC changed" and no_receipt(p) and op_file(p).exists()


def make_it_a_directory(p, tmp_path):
    git_path(p, "index").unlink()
    git_path(p, "index").mkdir()


def make_it_a_link(p, tmp_path):
    target = tmp_path / "linked-index"
    target.write_bytes(an_owner_index(p, tmp_path))
    git_path(p, "index").unlink()
    git_path(p, "index").symlink_to(target)


def make_it_a_hard_link_of_another_file(p, tmp_path):
    other = tmp_path / "other-file"
    other.write_bytes(an_owner_index(p, tmp_path))
    git_path(p, "index").unlink()
    os.link(other, git_path(p, "index"))


@for_both_modes
@pytest.mark.parametrize("make", [make_it_a_directory, make_it_a_link,
                                  make_it_a_hard_link_of_another_file])
def test_an_index_that_is_not_one_plain_file_of_its_own_is_never_success_and_never_removed(
        tmp_path, monkeypatch, mode, make):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    an_equivalent_index_stands_and_the_lock_is_gone(monkeypatch, p, mode, digest)
    try:
        make(p, tmp_path)
    except OSError as error:
        pytest.skip(str(error))
    before = os.lstat(git_path(p, "index"))
    answered = reason(confirm(p, mode, digest=digest))
    assert answered in {"git_failed", "git_timed_out", "index_exists"}
    assert os.path.lexists(git_path(p, "index")) and no_receipt(p) and op_file(p).exists()
    assert os.lstat(git_path(p, "index")).st_mtime_ns == before.st_mtime_ns
    assert not git_path(p, "index.lock").exists() and trunk_exists(p)


# --- a resume reads what was stored ------------------------------------------------------------


@for_both_modes
def test_a_resume_reads_the_stored_bytes_and_terms_never_a_changed_working_folder(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_mark_locked", mode, digest)
    stored, commit = install_files(p)[0].read_bytes(), commit_of(p)
    (p.root / "a.txt").write_bytes(b"edited\n")
    (p.root / "a.txt").chmod(0o755)
    p.git("config", "core.filemode", "false", cwd=p.root)
    p.git("config", "core.autocrlf", "true", cwd=p.root)
    (p.root / "untracked.txt").write_bytes(b"new\n")
    again = confirm(p, mode, digest=digest)
    assert again.status == 201 and again.payload["setup"]["commit"] == commit
    assert git_path(p, "index").read_bytes() == stored and text(p, "rev-parse", "HEAD") == commit
    shown = p.git("status", "--porcelain", cwd=p.root).stdout.decode().splitlines()
    assert shown == ([" M a.txt", "?? untracked.txt"] if mode == "snapshot"
                     else [*UNTRACKED.splitlines(), "?? untracked.txt"])
