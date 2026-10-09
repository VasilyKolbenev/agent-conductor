"""A signature wait meets the world: nothing repeats on its own, a term can change, a page is fresh.

While the product waits for the owner's signed commit, a reload, a preview, a GET and a new server
object repeat nothing. Another actor or another current author does not inherit the old
confirmation once the owner's commit exists, and before it exists they replace the wait by a new
intent. The branch HEAD names and the signing flag are read again at every repeat that comes before
the ref: a changed one replaces the wait, so the owner is never shown commands for a branch HEAD no
longer names. The last two tests are the two fresh-page scenarios of the ruling, at the API: a
client with no memory of the first call finishes a signature wait, and finishes a crash that came
after the branch moved. Real signed commits, made with a throwaway key (plan Task 9c).
"""
from __future__ import annotations

import pytest

from conductor.command import git_setup_first
from conductor.command import git_setup_first_records as records
from conductor.command import git_setup_first_signing as signing
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from conductor.ownership import data_root
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, op_file, project, terms_of)
from tests.git_first_signing import (  # noqa: F401
    FORMATS, owner_makes_the_commit, signing_key, signing_project, waits)
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_command_project_doors import request
from tests.test_git_setup import PATH, reason
from tests.test_git_setup_first_commit import install_files, no_receipt, own_leftovers, text
from tests.test_git_setup_first_leftovers import a_restarted_server, setup_dir, the_preview
from tests.test_git_setup_first_recovery import FILES, expected_status, git_path, own_copies, writes
from tests.test_project_git_state import read

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])
for_both_formats = pytest.mark.parametrize("fmt", FORMATS)


def world(p):
    """Everything a repeat could change: the product's records, `.git` and the message files."""
    return (snapshot(setup_dir(p)), snapshot(p.root / ".git"), snapshot(data_root(p.root) / "git"))


# --- a reload, a preview, a GET and a new server repeat nothing ------------------------------


@for_both_modes
def test_a_reload_a_get_and_a_server_start_repeat_nothing_while_a_signature_is_awaited(
        tmp_path, signing_key, mode):
    p = signing_project(tmp_path, signing_key, FILES)
    waits(p, mode)
    stored, asked = world(p), len(p.spy.calls)
    again = a_restarted_server(p)
    for server in (p, again):
        assert the_preview(server).status == 200              # the owner may look at it
        assert read(server)["first_commit_pending"]["state"] == "awaiting_signature"
    assert world(p) == stored
    started = [args for args, _ in p.spy.calls[asked:]]
    assert started and not [args for args in started if writes(args)]
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE and no_receipt(p)


# --- the old confirmation is not inherited -------------------------------------------------------


@for_both_modes
def test_another_actor_or_author_does_not_inherit_the_old_confirmation_once_the_commit_exists(
        tmp_path, signing_key, mode):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p, mode)
    detail = waits(p, mode, digest)
    owner_makes_the_commit(p, detail)
    stored = world(p)
    assert reason(confirm(p, mode, digest=digest, actor="Another")) == "setup_terms_changed"
    assert world(p) == stored
    p.git("config", "user.name", "Someone Else", cwd=p.root)
    changed = world(p)                                       # the owner's own config differs now
    assert reason(confirm(p, mode, digest=digest)) == "setup_terms_changed"
    assert world(p) == changed and no_receipt(p)
    p.git("config", "user.name", "First Author", cwd=p.root)
    assert confirm(p, mode, digest=digest).status == 201          # the original terms complete it


def test_another_actor_before_the_commit_exists_replaces_the_wait_and_retires_its_record_first(
        tmp_path, signing_key, monkeypatch):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    waits(p, "snapshot", digest)
    old = records.read_op(p.root)
    seen = []
    real = signing._remove_message

    def watching(root, op):
        seen.append((op_file(p).exists(), install_files(p)))     # the record is gone by now
        return real(root, op)

    monkeypatch.setattr(signing, "_remove_message", watching)
    detail = waits(p, "snapshot", digest, actor="Another")
    new = records.read_op(p.root)
    assert seen == [(False, [])]
    assert (new.requested_by, new.stage) == ("Another", AWAITING_SIGNATURE)
    assert new.nonce != old.nonce and detail["tree"] == new.expected_tree
    assert [path.name for path in install_files(p)] == [f"first_commit.index-{new.nonce}"]


# --- the branch HEAD names and the signing flag are read again before the ref exists ------------


def retarget(p):
    p.git("checkout", "--orphan", "main2", cwd=p.root)


@for_both_formats
def test_a_head_retarget_while_a_signature_is_awaited_replaces_the_wait_with_the_new_branch(
        tmp_path, signing_key, fmt):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt)
    digest = terms_of(p)
    old = waits(p, "snapshot", digest)
    assert old["target_ref"] == "refs/heads/trunk"
    retarget(p)
    new = waits(p, "snapshot", digest)
    assert new["target_ref"] == "refs/heads/main2"
    wait = records.read_op(p.root)
    assert (wait.target_ref, wait.stage) == ("refs/heads/main2", AWAITING_SIGNATURE)
    assert [path.name for path in install_files(p)] == [f"first_commit.index-{wait.nonce}"]
    assert (p.root / new["message_path"]).exists() and not own_copies(p)
    assert not [args for args, _ in p.spy.calls if "update-ref" in args]


def test_a_retarget_to_a_branch_a_shell_could_read_replaces_the_wait_then_refuses_the_new_branch(
        tmp_path, signing_key, monkeypatch):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    p.git("symbolic-ref", "HEAD", "refs/heads/a$(calc)", cwd=p.root)       # not a signable branch
    seen, real = [], signing._remove_message

    def watching(root, op):
        seen.append((op_file(p).exists(), install_files(p)))       # the record is gone by now
        return real(root, op)

    monkeypatch.setattr(signing, "_remove_message", watching)
    asked = len(p.spy.calls)
    answer = confirm(p, digest=digest)
    assert reason(answer) == "signing_ref_unsupported"
    assert answer.payload["error"]["detail"] == {"reason": "signing_ref_unsupported"}
    assert seen == [(False, [])]                              # the old record was retired first
    assert not op_file(p).exists() and install_files(p) == [] and no_receipt(p)
    assert not (p.root / detail["message_path"]).exists() and not own_copies(p)
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert not [args for args, _ in p.spy.calls[asked:] if writes(args)]


@for_both_formats
def test_turning_signing_off_while_a_signature_is_awaited_replaces_the_wait_with_the_unsigned_road(
        tmp_path, signing_key, fmt):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    p.git("config", "commit.gpgsign", "false", cwd=p.root)
    answer = confirm(p, digest=digest)
    assert answer.status == 201, answer.payload
    receipt = answer.payload["setup"]
    assert receipt["signature"] == "not_required" and receipt["target_ref"] == "refs/heads/trunk"
    raw = p.git("cat-file", "commit", receipt["commit"], cwd=p.root).stdout.decode()
    assert "gpgsig" not in raw
    assert own_leftovers(p) == [] and not (p.root / detail["message_path"]).exists()
    assert text(p, "status", "--porcelain") == expected_status("snapshot")


def test_the_same_terms_while_a_signature_is_awaited_answer_the_same_commands(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    nonce, stored = records.read_op(p.root).nonce, world(p)
    assert waits(p, "snapshot", digest) == detail
    assert records.read_op(p.root).nonce == nonce and world(p) == stored


@for_both_formats
def test_a_commit_the_owner_published_is_recognised_although_head_was_retargeted_afterwards(
        tmp_path, signing_key, fmt):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    oid = owner_makes_the_commit(p, detail)
    p.git("symbolic-ref", "HEAD", "refs/heads/main2", cwd=p.root)
    answer = confirm(p, digest=digest)
    assert answer.status == 201, answer.payload
    receipt = answer.payload["setup"]
    assert (receipt["target_ref"], receipt["commit"]) == ("refs/heads/trunk", oid)
    assert text(p, "rev-parse", "refs/heads/trunk") == oid and own_leftovers(p) == []


def test_calibration_a_wait_that_skips_the_freshness_check_would_show_commands_for_a_stale_branch(
        tmp_path, signing_key, monkeypatch):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    waits(p, "snapshot", digest)
    real = git_setup_first._stored_terms_hold

    def only_for_the_unsigned_road(api, op, request):
        if op.stage == AWAITING_SIGNATURE:
            return (op.mode, op.paths_digest, op.requested_by) == (
                request.mode, request.digest, request.actor)
        return real(api, op, request)

    monkeypatch.setattr(git_setup_first, "_stored_terms_hold", only_for_the_unsigned_road)
    retarget(p)
    stale = waits(p, "snapshot", digest)
    assert text(p, "symbolic-ref", "HEAD") == "refs/heads/main2"
    assert stale["target_ref"] == "refs/heads/trunk"              # the violation


# --- the two scenarios of the ruling, from a client with no memory -----------------------------


def continue_body(pending: dict, actor: str) -> dict:
    """The body of a continue, built from the stored terms of the description and the actor."""
    terms = pending["terms"]
    return dict(step="first_commit", mode=terms["mode"], paths_digest=terms["paths_digest"],
                actor=actor)


@for_both_modes
def test_a_fresh_page_finishes_a_wait_for_a_signature(tmp_path, signing_key, mode):
    p = signing_project(tmp_path, signing_key, FILES)
    waits(p, mode)
    page = a_restarted_server(p)                               # no memory of the first call
    pending = read(page)["first_commit_pending"]
    assert pending["state"] == "awaiting_signature"
    owner_makes_the_commit(p, pending["signing"])              # the commands from the read ALONE
    answer = request(page, "POST", PATH, continue_body(pending, "Owner"))
    assert answer.status == 201, answer.payload
    assert answer.payload["setup"]["signature"] == "present"
    facts = read(page)
    assert facts["first_commit_pending"] is None and facts["state"] == "repo"
    assert text(p, "status", "--porcelain") == expected_status(mode)


@for_both_modes
def test_a_fresh_page_finishes_a_crash_after_the_ref_moved(tmp_path, monkeypatch, mode):
    p = project(tmp_path, FILES)
    crashed(monkeypatch, p, "_do_mark_ref_moved", mode, terms_of(p, mode))
    page = a_restarted_server(p)
    facts = read(page)
    pending = facts["first_commit_pending"]
    assert facts["state"] == "repo" and pending["state"] == "unfinished"
    answer = request(page, "POST", PATH, continue_body(pending, "Owner"))
    assert answer.status == 201, answer.payload
    assert len([args for args, _ in p.spy.calls if "update-ref" in args]) == 1
    assert git_path(p, "index").exists() and read(page)["first_commit_pending"] is None
    assert own_leftovers(p) == []
