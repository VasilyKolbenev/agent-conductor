"""What a damaged record, a stale op, a refusal and a read leave behind (plan Task 8; OD-4, OD-9).

A damaged record is judged and nothing is removed for it. An op that stands beside a receipt is a
leftover of a finish that died: the receipt answers and the next exact repeat cleans, the op
record first. A refusal drops the product's own copy and keeps the op and its bytes. A preview, a
GET, a new API object and a restart of the server resume nothing: only the same body, posted, does.
"""
from __future__ import annotations

import errno
import json
from types import SimpleNamespace

import pytest

from conductor.command import git_setup_first_lock as lock_module
from conductor.command import git_setup_first_records as records
from conductor.command.adapters import AdapterRegistry
from conductor.command.git_setup_first_index import verify
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.run_store import RunStore, StoreError
from conductor.ownership import data_root
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, op_file, project, terms_of)
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, ids
from tests.test_command_materials_routes import PROJECT_ID
from tests.test_command_project_doors import request
from tests.test_git_setup import PATH, reason
from tests.test_git_setup_first_commit import (
    an_owner_index, install_files, no_receipt, own_leftovers, owner_ref, text, trunk_exists)
from tests.test_git_setup_first_recovery import (
    FILES, failing_unlink_once, git_path, is_copy, own_copies, stage_of, writes)
from tests.test_project_git_state import read

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])


def setup_dir(p):
    return data_root(p.root) / "git" / "setup"


# --- a damaged record -------------------------------------------------------------------------


def test_first_commit_with_a_damaged_op_record_is_setup_damaged_and_deletes_nothing(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    crashed(monkeypatch, p, "_do_take_lock", "snapshot", digest)
    op_file(p).write_bytes(b"not an op record\n")
    before = (snapshot(p.root / ".git"), snapshot(setup_dir(p)))
    assert reason(confirm(p, digest=digest)) == "setup_damaged"
    assert (snapshot(p.root / ".git"), snapshot(setup_dir(p))) == before
    assert git_path(p, "index.lock").exists() and len(install_files(p)) == 1 and no_receipt(p)


# --- an op beside a receipt ------------------------------------------------------------------


def a_finish_that_died_before_the_retirement(p, monkeypatch, digest):
    """The receipt is written and the process dies before the op is retired: the stale op."""
    real, seen = records.retire, []

    def dies_before_the_retirement(root, op):
        seen.append(op)
        raise StoreError("simulated interruption before the op was retired")

    monkeypatch.setattr(records, "retire", dies_before_the_retirement)
    assert confirm(p, digest=digest).status == 500
    monkeypatch.setattr(records, "retire", real)
    assert op_file(p).exists() and install_files(p) and not no_receipt(p)
    return seen[0]


@pytest.mark.parametrize("copy", [False, True], ids=["no_copy_stands", "a_copy_stands"])
def test_first_commit_receipt_and_op_both_standing_answers_the_receipt_and_removes_the_op(
        tmp_path, monkeypatch, copy):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    op = a_finish_that_died_before_the_retirement(p, monkeypatch, digest)
    if copy:
        lock_module.ensure_copy(p.root / ".git", op.nonce, records.read_install(p.root, op))
    removed, unlink = [], records._unlink_plain

    def watching(root, path):
        removed.append(path.name)
        unlink(root, path)

    monkeypatch.setattr(records, "_unlink_plain", watching)
    again = confirm(p, digest=digest)
    assert again.status == 200 and own_leftovers(p) == []
    assert removed[0] == records.OP_NAME and removed[1].startswith(records.INSTALL)


def test_a_cleanup_that_fails_still_answers_the_receipt_and_the_next_repeat_finishes_it(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    a_finish_that_died_before_the_retirement(p, monkeypatch, digest)
    real = records._unlink_plain

    def fails(root, path):
        raise OSError(errno.EIO, "the removal failed")

    monkeypatch.setattr(records, "_unlink_plain", fails)
    assert confirm(p, digest=digest).status == 200 and op_file(p).exists()
    monkeypatch.setattr(records, "_unlink_plain", real)
    assert confirm(p, digest=digest).status == 200 and own_leftovers(p) == []


def test_a_damaged_op_beside_a_receipt_is_left_alone_and_the_receipt_still_answers(tmp_path):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    done = confirm(p, digest=digest)
    assert done.status == 201
    op_file(p).write_bytes(b"not an op record\n")
    before = (snapshot(p.root / ".git"), snapshot(setup_dir(p)))
    again = confirm(p, digest=digest)
    assert (again.status, again.payload) == (200, done.payload)
    assert (snapshot(p.root / ".git"), snapshot(setup_dir(p))) == before


# --- what a preview, a GET and a restart do ---------------------------------------------------


def a_restarted_server(p):
    """A second API object over the same folder and the same reader: a server started again."""
    api = CommandApi(RunStore(p.root), AdapterRegistry([FakeAdapter()]),
                     session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
                     clock=lambda: NOW, ids=ids(), publish_run=lambda _run: None,
                     project_git=p.api._project_git,
                     identity=ProjectIdentity(PROJECT_ID, None, False, "active", None, None))
    return SimpleNamespace(root=p.root, api=api)


def the_preview(p):
    return request(p, "POST", PATH, dict(step="first_commit", mode="snapshot", preview=True))


@pytest.mark.parametrize("crash, refusal", [("_do_take_lock", "index_locked"),
                                            ("_do_mark_ref_moved", "head_exists")])
def test_recovery_is_only_an_explicit_repeat_never_a_side_effect_of_a_preview_or_startup(
        tmp_path, monkeypatch, crash, refusal):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    crashed(monkeypatch, p, crash, "snapshot", digest)
    before = (snapshot(p.root / ".git"), snapshot(setup_dir(p)), stage_of(p))
    asked = len(p.spy.calls)
    again = a_restarted_server(p)
    for server in (p, again):
        assert reason(the_preview(server)) == refusal
        assert read(server)["first_commit_pending"]["state"] == "unfinished"
    assert (snapshot(p.root / ".git"), snapshot(setup_dir(p)), stage_of(p)) == before
    started = [args for args, _ in p.spy.calls[asked:]]
    assert started and not [args for args in started if writes(args)]
    assert confirm(p, digest=digest).status == 201          # only the same body, posted, continues


# --- decision E: a refusal leaves no copy ---------------------------------------------------------


def lays_the_copy_then_dies(monkeypatch):
    """`take_lock` lays the copy and fails before it is moved onto the lock: a crash between."""
    real = lock_module.take_lock

    def take(git_dir, nonce, data):
        lock_module.ensure_copy(git_dir, nonce, data)
        raise StoreError("simulated interruption after the copy was laid")

    monkeypatch.setattr(lock_module, "take_lock", take)
    return lambda: monkeypatch.setattr(lock_module, "take_lock", real)


@for_both_modes
def test_first_commit_head_exists_after_a_crash_before_the_lock_leaves_no_copy(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    restart = lays_the_copy_then_dies(monkeypatch)
    assert confirm(p, mode, digest=digest).status == 500
    restart()
    assert len(own_copies(p)) == 1 and not git_path(p, "index.lock").exists()
    theirs = owner_ref(p)
    assert reason(confirm(p, mode, digest=digest)) == "head_exists"
    assert not own_copies(p) and not git_path(p, "index.lock").exists()
    assert op_file(p).exists() and len(install_files(p)) == 1 and no_receipt(p)    # nothing retired
    assert text(p, "rev-parse", "refs/heads/trunk") == theirs


@for_both_modes
def test_first_commit_index_exists_with_the_copy_still_linked_to_the_lock_leaves_neither(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    restart = failing_unlink_once(monkeypatch, is_copy)         # the move died: copy and lock
    assert reason(confirm(p, mode, digest=digest)) == "git_failed"
    restart()
    assert len(own_copies(p)) == 1 and git_path(p, "index.lock").exists()
    git_path(p, "index").write_bytes(an_owner_index(p, tmp_path))
    theirs = git_path(p, "index").read_bytes()
    assert reason(confirm(p, mode, digest=digest)) == "index_exists"
    assert not own_copies(p) and not git_path(p, "index.lock").exists()
    assert git_path(p, "index").read_bytes() == theirs and not trunk_exists(p)
    assert op_file(p).exists() and len(install_files(p)) == 1 and no_receipt(p)


@for_both_modes
def test_a_supersede_drops_the_copy_an_interrupted_take_left_and_the_old_op_with_it(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    restart = lays_the_copy_then_dies(monkeypatch)
    assert confirm(p, mode, digest=digest).status == 500
    restart()
    old = json.loads(op_file(p).read_text())["nonce"]
    assert len(own_copies(p)) == 1 and not git_path(p, "index.lock").exists()
    answer = confirm(p, mode, digest=digest, actor="Another")      # another actor: a new operation
    assert answer.status == 201, answer.payload
    assert own_leftovers(p) == []                                  # the old copy went with its op
    assert verify(git_path(p, "index").read_bytes(), "sha1").marker[0] != old
