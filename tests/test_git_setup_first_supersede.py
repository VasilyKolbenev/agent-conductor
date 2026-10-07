"""A stored first commit meets changed terms (plan Task 8; rulings OD-6, OD-8, OD-9, OD-10).

Before the ref was published a changed term replaces the unfinished operation: only what the
stored bytes prove is the product's own is undone (the lock, the copy), the record goes before its
install bytes, and the fresh path then runs on the facts as they are now. After the ref was
published nothing is replaced: the commit is on its branch, a changed actor or author is
`setup_terms_changed`, and the install is finished from the stored bytes. A resume that has not
published the ref is an entry of the write like the first one: the branch HEAD names, the object
format and the signing flag are read again, and a changed one is a changed term.
"""
from __future__ import annotations

import errno
import json
from types import SimpleNamespace

import pytest

from conductor.command import git_setup_first as first
from conductor.command import git_setup_first_lock as lock_module
from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_first_index import verify
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, op_file, project, terms_of)
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import (
    an_owner_index, install_files, no_receipt, own_leftovers, owner_ref, text, trunk_exists)
from tests.test_git_setup_first_driver import an_operation
from tests.test_git_setup_first_records import an_op
from tests.test_git_setup_first_recovery import FILES, expected_status, git_path

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])
NO_SUCH = "sha256:" + "0" * 64


def op_nonce(p):
    return json.loads(op_file(p).read_text())["nonce"]


def marker_nonce(p):
    """The nonce of the operation whose marked bytes are the installed index."""
    return verify(git_path(p, "index").read_bytes(), "sha1").marker[0]


def the_stored_world(p):
    """What the stored operation holds: its record, its install bytes and everything in `.git`."""
    return (op_file(p).read_bytes(), [path.read_bytes() for path in install_files(p)],
            snapshot(p.root / ".git"))


# --- after the ref was published: nothing is replaced ----------------------------------------


@for_both_modes
def test_another_actor_or_another_current_author_does_not_inherit_the_old_confirmation(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, digest)
    before = the_stored_world(p)
    assert reason(confirm(p, mode, digest=digest, actor="Another")) == "setup_terms_changed"
    assert the_stored_world(p) == before
    p.git("config", "user.name", "Someone Else", cwd=p.root)
    changed = the_stored_world(p)
    assert reason(confirm(p, mode, digest=digest)) == "setup_terms_changed"
    assert the_stored_world(p) == changed and no_receipt(p)
    p.git("config", "user.name", "First Author", cwd=p.root)
    assert confirm(p, mode, digest=digest).status == 201


@pytest.mark.parametrize("mode, change", [("snapshot", "actor"), ("snapshot", "digest"),
                                          ("empty", "actor")])
@pytest.mark.parametrize("crash", ["_do_move_ref", "_do_mark_ref_moved"])
def test_first_commit_with_changed_terms_after_the_ref_moved_is_setup_terms_changed(
        tmp_path, monkeypatch, mode, change, crash):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, crash, mode, digest)
    before = the_stored_world(p)
    other = dict(digest=NO_SUCH) if change == "digest" else dict(digest=digest, actor="Another")
    assert reason(confirm(p, mode, **other)) == "setup_terms_changed"
    assert the_stored_world(p) == before and trunk_exists(p) and no_receipt(p)
    assert confirm(p, mode, digest=digest).status == 201        # the original terms complete it


def test_a_ref_at_our_commit_under_a_record_that_still_says_prepared_is_setup_terms_changed(
        tmp_path):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    op, made = an_operation(p)                    # the records only: `prepared`, nothing in `.git`
    lock_module.take_lock(p.root / ".git", op.nonce, made.install)
    p.git("update-ref", "refs/heads/trunk", op.commit, cwd=p.root)    # the swap, then the crash
    before = the_stored_world(p)
    assert op.stage == "prepared"
    assert reason(confirm(p, digest=digest, actor="Another")) == "setup_terms_changed"
    assert the_stored_world(p) == before
    assert confirm(p, digest=digest).status == 201


# --- before the ref was published: a changed term replaces the operation -------------------------


@pytest.mark.parametrize("crash", ["_do_take_lock", "records.start"])
def test_first_commit_with_changed_terms_supersedes_an_op_that_has_not_moved_the_ref(
        tmp_path, monkeypatch, crash):
    p = project(tmp_path, FILES)
    old_digest = terms_of(p)
    (p.root / "new.txt").write_bytes(b"fresh\n")
    new_digest = terms_of(p)                      # the preview of the files as they will be
    (p.root / "new.txt").unlink()
    if crash == "records.start":
        crashed(monkeypatch, p, "start", "snapshot", old_digest, owner=records)
    else:
        crashed(monkeypatch, p, crash, "snapshot", old_digest)
    old = op_nonce(p)
    (p.root / "new.txt").write_bytes(b"fresh\n")
    answer = confirm(p, digest=new_digest)
    assert answer.status == 201, answer.payload
    assert own_leftovers(p) == [] and marker_nonce(p) != old
    assert "new.txt" in text(p, "ls-tree", "-r", "--name-only", "HEAD").splitlines()


@for_both_modes
def test_a_changed_author_before_the_ref_supersedes_the_old_op_and_the_new_commit_carries_it(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_take_lock", mode, digest)
    old = op_nonce(p)
    p.git("config", "user.name", "Second Author", cwd=p.root)
    answer = confirm(p, mode, digest=digest)
    assert answer.status == 201, answer.payload
    assert text(p, "log", "-1", "--format=%an") == "Second Author"
    assert marker_nonce(p) != old and own_leftovers(p) == []


def retarget(p):
    p.git("checkout", "--orphan", "main2", cwd=p.root)


def sign_from_now_on(p):
    p.git("config", "commit.gpgsign", "true", cwd=p.root)


def trunk_moves(p):
    """The refs the spy saw `update-ref` move, in order."""
    return [args[-3] for args in p.spy.argv("update-ref")]


@for_both_modes
@pytest.mark.parametrize("crash", ["_do_take_lock", "_do_mark_locked"])
@pytest.mark.parametrize("change", ["retarget", "signing_on", "none"])
def test_a_resume_before_the_ref_supersedes_when_a_frozen_term_changed(
        tmp_path, monkeypatch, mode, crash, change):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, crash, mode, digest)
    stored = json.loads(op_file(p).read_text())
    assert git_path(p, "index.lock").exists()                 # the product's own lock stands
    {"retarget": retarget, "signing_on": sign_from_now_on, "none": lambda folder: None}[change](p)
    answer = confirm(p, mode, digest=digest)
    if change == "signing_on":
        assert reason(answer) == "signing_required"
        assert trunk_moves(p) == [] and text(p, "rev-list", "--all") == ""
        assert no_receipt(p) and own_leftovers(p) == []       # the old op is superseded
    elif change == "retarget":
        receipt = answer.payload["setup"]
        assert answer.status == 201 and receipt["target_ref"] == "refs/heads/main2"
        assert trunk_moves(p) == ["refs/heads/main2"] and not trunk_exists(p)
        assert text(p, "rev-parse", "main2") == receipt["commit"]
        assert text(p, "rev-list", "--count", "main2") == "1"
        assert marker_nonce(p) != stored["nonce"] and own_leftovers(p) == []
        assert text(p, "status", "--porcelain") == expected_status(mode)
    else:
        assert answer.status == 201 and answer.payload["setup"]["commit"] == stored["commit"]
        assert trunk_moves(p) == ["refs/heads/trunk"] and marker_nonce(p) == stored["nonce"]


@for_both_modes
def test_a_head_retarget_after_the_ref_moved_is_not_a_changed_term_and_the_operation_finishes(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, digest)
    stored, nonce = install_files(p)[0].read_bytes(), op_nonce(p)
    p.git("symbolic-ref", "HEAD", "refs/heads/main2", cwd=p.root)
    answer = confirm(p, mode, digest=digest)
    receipt = answer.payload["setup"]
    assert answer.status == 201 and receipt["target_ref"] == "refs/heads/trunk"
    assert text(p, "rev-parse", "refs/heads/trunk") == receipt["commit"]
    assert git_path(p, "index").read_bytes() == stored and marker_nonce(p) == nonce
    assert trunk_moves(p) == ["refs/heads/trunk"] and own_leftovers(p) == []


# --- the pure judgement ----------------------------------------------------------------------

OP = an_op()
ANOTHER_AUTHOR = {"name": "Second Author", "email": "second@example.invalid"}
API = SimpleNamespace(_store=SimpleNamespace(project_root="root"), _project_git=None)
REQUEST = SimpleNamespace(mode=OP.mode, digest=OP.paths_digest, actor=OP.requested_by)


def a_world(monkeypatch, *, ref, **differs):
    """Git replaced by fakes: `frozen_facts` answers the op's own four terms but `differs`, and
    `ref_oid` the id of the target ref (None: absent). Returns the list of facts that were read."""
    facts = dict(target_ref=OP.target_ref, object_format=OP.object_format,
                 author=dict(OP.author), signing=OP.signing)
    facts.update(differs)
    read = []

    def frozen_facts(root, git):
        read.append("frozen_facts")
        return dict(facts)

    for name, fake in (("admitted", lambda root, git: None), ("frozen_facts", frozen_facts),
                       ("ref_oid", lambda root, git, name: ref),
                       ("author_now", lambda root, git: facts["author"])):
        monkeypatch.setattr(first, name, fake, raising=False)
    return read


@pytest.mark.parametrize("stage", ["prepared", "locked"])
@pytest.mark.parametrize("differs, holds", [
    ({}, True), ({"target_ref": "refs/heads/main2"}, False), ({"object_format": "sha256"}, False),
    ({"author": ANOTHER_AUTHOR}, False), ({"signing": True}, False)],
    ids=["nothing", "target_ref", "object_format", "author", "signing"])
def test_stored_terms_hold_judges_each_frozen_fact_while_the_ref_is_absent(
        monkeypatch, stage, differs, holds):
    a_world(monkeypatch, ref=None, **differs)
    assert first._stored_terms_hold(API, an_op(stage=stage), REQUEST) is holds


@pytest.mark.parametrize("stage, ref", [("ref_moved", None), ("prepared", "c" * 40),
                                        ("locked", "c" * 40), ("ref_moved", "c" * 40)])
def test_stored_terms_hold_ignores_the_branch_the_format_and_signing_once_the_ref_is_published(
        monkeypatch, stage, ref):
    read = a_world(monkeypatch, ref=ref, target_ref="refs/heads/main2", object_format="sha256",
                   signing=True)
    assert first._stored_terms_hold(API, an_op(stage=stage), REQUEST) is True
    assert read == []                                  # the frozen facts are not read at all


@pytest.mark.parametrize("stage, ref", [("prepared", None), ("locked", None), ("ref_moved", None),
                                        ("locked", "c" * 40)])
@pytest.mark.parametrize("body, holds", [
    ({"actor": "Another"}, False), ({"mode": "empty"}, False),
    ({"digest": "sha256:" + "e" * 64}, False), ({}, True)],
    ids=["actor", "mode", "digest", "same"])
def test_stored_terms_hold_always_judges_the_body_and_the_actor(
        monkeypatch, stage, ref, body, holds):
    a_world(monkeypatch, ref=ref)
    sent = SimpleNamespace(**{**vars(REQUEST), **body})
    assert first._stored_terms_hold(API, an_op(stage=stage), sent) is holds


@pytest.mark.parametrize("stage, ref", [("prepared", None), ("ref_moved", None),
                                        ("locked", "c" * 40)])
def test_stored_terms_hold_always_judges_the_author_of_now(monkeypatch, stage, ref):
    a_world(monkeypatch, ref=ref, author=ANOTHER_AUTHOR)
    assert first._stored_terms_hold(API, an_op(stage=stage), REQUEST) is False


# --- what a supersede keeps -----------------------------------------------------------------------


def the_owner_takes_the_lock(p, tmp_path):
    git_path(p, "index.lock").unlink()
    git_path(p, "index.lock").write_bytes(b"")
    return git_path(p, "index.lock")


def the_owner_writes_an_index(p, tmp_path):
    git_path(p, "index").write_bytes(an_owner_index(p, tmp_path))
    return git_path(p, "index")


@for_both_modes
@pytest.mark.parametrize("meets, refusal", [(the_owner_takes_the_lock, "index_locked"),
                                            (the_owner_writes_an_index, "index_exists")])
def test_a_supersede_keeps_a_foreign_lock_and_a_foreign_index_and_refuses_on_them(
        tmp_path, monkeypatch, mode, meets, refusal):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_take_lock", mode, digest)
    theirs = meets(p, tmp_path)
    kept = theirs.read_bytes()
    assert reason(confirm(p, mode, digest=digest, actor="Another")) == refusal
    assert theirs.read_bytes() == kept and not trunk_exists(p) and no_receipt(p)
    assert (git_path(p, "index.lock").exists()) == (refusal == "index_locked")
    assert not op_file(p).exists() and not install_files(p)     # the op went first, its bytes after
    assert not list((p.root / ".git").glob("conduct-first-index-*"))


@for_both_modes
def test_a_supersede_answers_a_foreign_ref_as_head_exists_and_keeps_the_old_op(
        tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    digest = terms_of(p, mode)
    crashed(monkeypatch, p, "_do_take_lock", mode, digest)
    record, bytes_ = op_file(p).read_bytes(), install_files(p)[0].read_bytes()
    theirs = owner_ref(p)
    assert reason(confirm(p, mode, digest=digest, actor="Another")) == "head_exists"
    assert text(p, "rev-parse", "refs/heads/trunk") == theirs and no_receipt(p)
    assert op_file(p).read_bytes() == record and install_files(p)[0].read_bytes() == bytes_
    assert not git_path(p, "index.lock").exists()    # our own lock goes, as the table's does


# --- the order of the retirement -------------------------------------------------------------


def test_a_supersede_retires_the_op_before_its_install_bytes_and_survives_a_crash_between_them(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    digest = terms_of(p)
    crashed(monkeypatch, p, "_do_take_lock", "snapshot", digest)
    real = records._unlink_plain

    def fails_on_the_bytes(root, path):
        if path.name.startswith(records.INSTALL):
            raise OSError(errno.EIO, "the removal failed")
        real(root, path)

    monkeypatch.setattr(records, "_unlink_plain", fails_on_the_bytes)
    assert reason(confirm(p, digest=digest, actor="Another")) == "git_failed"
    monkeypatch.setattr(records, "_unlink_plain", real)
    assert not op_file(p).exists() and len(install_files(p)) == 1       # one orphan, no live op
    assert not git_path(p, "index.lock").exists() and not list(
        (p.root / ".git").glob("conduct-first-index-*"))
    again = confirm(p, digest=digest, actor="Another")                   # nothing is resumed
    assert again.status == 201 and again.payload["setup"]["requested_by"] == "Another"
    assert own_leftovers(p) == []                                        # the orphan was swept
