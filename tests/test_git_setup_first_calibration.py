"""The witnesses of recovery must be able to say no (plan Task 8, calibrations i to ix).

Each test runs the scenario of a guard with that guard sabotaged and asserts the VIOLATION the
guard exists to prevent. With the real code the same scenarios are refusals and nothing is lost:
those are the tests of `test_git_setup_first_recovery.py`, `..._supersede.py` and
`..._leftovers.py`. A calibration that passes shows the guard is not decoration.
"""
from __future__ import annotations

import errno
import os

import pytest

from conductor.command import git_setup_first as first
from conductor.command import git_setup_first_lock as lock_module
from conductor.command import git_setup_first_prepare as prepare_module
from conductor.command import git_setup_first_records as records
from conductor.command.accept_manifest import sha256
from conductor.command.git_setup_first_index import binding_of, mark, verify
from conductor.command.git_setup_first_lock import lock_state, release_own_lock
from conductor.command.git_setup_first_resume import Lock
from conductor.command.git_setup_facts import plain_git_dir
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, op_file, project, terms_of)
from tests.git_index_bytes import plain
from tests.git_repo_helpers import needs_git
from tests.test_git_index_marker_compat import FILES as BYTES
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import (
    an_owner_index, install_files, no_receipt, owner_ref, text, trunk_exists)
from tests.test_git_setup_first_lock import made
from tests.test_git_setup_first_recovery import FILES, git_path, owners_bytes_for_the_tree

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]


def test_calibration_a_lock_judged_by_existence_would_delete_the_empty_lock_the_witness_plants(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest, lock = terms_of(p, "empty"), git_path(p, "index.lock")
    crashed(monkeypatch, p, "_do_take_lock", "empty", digest)
    lock.unlink()
    lock.write_bytes(b"")                                # somebody's `git add` has begun

    def by_existence(folder, binding):                   # the sabotage: a name is proof enough
        found = lock_module._look(folder / lock_module.LOCK)
        return None if isinstance(found, str) else found

    monkeypatch.setattr(lock_module, "_prove", by_existence)
    confirm(p, "empty", digest=digest)
    assert not lock.exists() and trunk_exists(p)         # the lock was taken as ours, and moved


def test_calibration_an_update_ref_without_the_zero_oid_would_overwrite_the_owners_ref(
        tmp_path, monkeypatch):
    p, theirs = project(tmp_path, FILES), []

    def move_without_the_old_value(api, op):
        theirs.append(owner_ref(p))                      # the owner wins the race
        p.api._project_git(["-C", str(p.root), "update-ref", op.target_ref, op.commit], True)
        return op

    monkeypatch.setattr(first, "_do_move_ref", move_without_the_old_value)
    answer = confirm(p)
    assert answer.status == 201
    assert text(p, "rev-parse", "refs/heads/trunk") == answer.payload["setup"]["commit"]
    assert text(p, "rev-parse", "refs/heads/trunk") != theirs[0]     # the owner's ref is gone


def test_calibration_a_replacing_install_would_overwrite_the_index_that_appeared(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    planted, real = an_owner_index(p, tmp_path), first._do_install_index

    def the_owner_writes_first(api, op):
        git_path(p, "index").write_bytes(planted)
        return real(api, op)

    monkeypatch.setattr(first, "_do_install_index", the_owner_writes_first)
    monkeypatch.setattr(lock_module, "_move", lambda source, target: os.replace(source, target))
    confirm(p)
    assert git_path(p, "index").read_bytes() != planted             # the owner's bytes are gone


def test_calibration_unmarked_bytes_would_let_an_empty_mode_lock_pass_as_own(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    lock = git_path(p, "index.lock")
    monkeypatch.setattr(prepare_module, "mark", lambda data, fmt, **terms: data)     # unmarked
    monkeypatch.setattr(lock_module, "verify_binding",                      # the sha256 alone
                        lambda data, binding: sha256(data) == binding.install_sha256)
    crashed(monkeypatch, p, "_do_take_lock", "empty", None)
    product = lock.read_bytes()
    owners = owners_bytes_for_the_tree(p, tmp_path, "empty")
    assert len(product) == 65 and owners == product     # what Git writes is what was built
    lock.unlink()
    lock.write_bytes(owners)                              # a foreign lock, byte for byte the same
    confirm(p, "empty", digest=None)
    assert not lock.exists()                              # taken as its own, and moved or removed


def test_calibration_the_marker_alone_would_prove_ownership_of_other_bytes(tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 2)
    impostor = mark(plain(list(BYTES)[:3], "sha1", tree=m.op.expected_tree), "sha1",
                    nonce=m.op.nonce, terms=m.binding.terms)       # one more entry, same marker
    m.lock.write_bytes(impostor)
    assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN
    assert release_own_lock(m.git_dir, m.binding) is False and m.lock.exists()

    def marker_only(data, binding):
        return verify(data, binding.object_format).marker == (binding.nonce, binding.terms)

    monkeypatch.setattr(lock_module, "verify_binding", marker_only)
    assert lock_state(m.git_dir, m.binding) is Lock.OWN
    assert release_own_lock(m.git_dir, m.binding) is True and not m.lock.exists()


def test_calibration_the_equivalence_read_would_delete_an_equivalent_owner_index(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    crashed(monkeypatch, p, "_do_mark_ref_moved", "snapshot", digest)
    git_path(p, "index.lock").unlink()
    p.git("read-tree", "HEAD", cwd=p.root)
    theirs, real = git_path(p, "index").read_bytes(), first._do_finish

    def exit_zero_means_ours(api, op):                    # the sabotaged branch of the table
        folder, data = plain_git_dir(p.root, p.api._project_git), records.read_install(p.root, op)
        os.unlink(folder / "index")
        lock_module.take_lock(folder, op.nonce, data)
        lock_module.install_index(folder, binding_of(op), data)
        return real(api, op)

    monkeypatch.setattr(first, "_do_finish", exit_zero_means_ours)
    confirm(p, digest=digest)
    assert git_path(p, "index").read_bytes() != theirs    # the owner's file was replaced by ours


def only_the_body_and_the_author(api, op, request):
    """The first form of the freshness check: what the stored op says of the body and the author."""
    now = first.author_now(api._store.project_root, api._project_git)
    return (op.mode, op.paths_digest, op.requested_by, op.author) == (
        request.mode, request.digest, request.actor, now)


@pytest.mark.parametrize("mode", ["snapshot", "empty"])
@pytest.mark.parametrize("change", ["retarget", "signing_on"])
def test_calibration_a_resume_that_compares_only_the_body_would_publish_to_a_stale_target(
        tmp_path, monkeypatch, mode, change):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_take_lock", mode, digest)
    monkeypatch.setattr(first, "_stored_terms_hold", only_the_body_and_the_author)
    if change == "retarget":
        p.git("checkout", "--orphan", "main2", cwd=p.root)
    else:
        p.git("config", "commit.gpgsign", "true", cwd=p.root)
    answer = confirm(p, mode, digest=digest)
    assert answer.status == 201 and trunk_exists(p)
    if change == "retarget":                              # a branch HEAD does not name
        assert text(p, "symbolic-ref", "HEAD") == "refs/heads/main2"
        assert p.git("rev-parse", "--verify", "-q", "HEAD", cwd=p.root, check=False).returncode != 0
    else:                                                 # an unsigned commit where signing is on
        raw = p.git("cat-file", "commit", "refs/heads/trunk", cwd=p.root).stdout.decode()
        configured = p.git("config", "--file", str(p.root / ".git" / "config"),
                           "commit.gpgsign", cwd=p.root).stdout.decode().strip()
        assert "gpgsig" not in raw and configured == "true"
        assert answer.payload["setup"]["signature"] == "not_required"


def test_calibration_a_retirement_that_removes_the_bytes_first_leaves_an_op_without_them(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    crashed(monkeypatch, p, "_do_take_lock", "snapshot", digest)
    real = records.retire

    def bytes_first_and_a_crash_between(root, op):
        records._unlink_plain(root, records._setup(root) / f"{records.INSTALL}{op.nonce}")
        raise OSError(errno.EIO, "the process died between the two removals")

    monkeypatch.setattr(records, "retire", bytes_first_and_a_crash_between)
    assert reason(confirm(p, digest=digest, actor="Another")) == "git_failed"
    monkeypatch.setattr(records, "retire", real)
    assert op_file(p).exists() and not install_files(p)           # a live op without its bytes
    assert reason(confirm(p, digest=digest)) == "setup_damaged"   # the state the ruling names


def test_calibration_skipping_the_existence_check_would_finish_empty_mode_with_no_index(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p, "empty")
    crashed(monkeypatch, p, "_do_mark_ref_moved", "empty", digest)
    git_path(p, "index.lock").unlink()
    real = first._look
    monkeypatch.setattr(first, "_look", lambda path: real(path) or (0, 0, 0, 0))   # never absent
    answer = confirm(p, "empty", digest=digest)
    assert answer.status == 201 and not no_receipt(p)
    assert not git_path(p, "index").exists()              # finished, and nothing was installed
