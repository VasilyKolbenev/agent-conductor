"""The message file of a signed road: stored with the intent, removed with the receipt (Task 9).

The owner's `git commit-tree -F <message_path>` reads the commit message from a file the product
wrote beside the intent (`msg-first-<32 hex>.txt`). The write of the intent has two named points
(the message file, then the operation record) and the exact repeat finishes it from either. Once
the receipt of a finished signed road stands the file has no reader left, so the finish removes
it, and only the plain file the product wrote: a file whose bytes changed, or one that has
another name, is not the product's to delete.
"""
from __future__ import annotations

import os

import pytest

from conductor.command import git_setup_first_records as records
from conductor.command import git_setup_first_signing as signing
from conductor.command.git_setup_first_index import verify
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from conductor.ownership import data_root
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, op_file, terms_of)
from tests.git_first_signing import (  # noqa: F401
    owner_makes_the_commit, signing_key, signing_project, waits)
from tests.git_repo_helpers import needs_git
from tests.test_git_setup_first_commit import install_files, no_receipt, own_leftovers
from tests.test_git_setup_first_recovery import FILES, git_path

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
CRASHES = [pytest.param("_put", signing, id="after_the_message_file"),
           pytest.param("start", records, id="after_the_operation_record")]


def message_files(p):
    return sorted((data_root(p.root) / "git").glob("msg-first-*.txt"))


# --- a crash inside the write of the intent -------------------------------------------------


@pytest.mark.parametrize("crash, owner", CRASHES)
def test_a_crash_inside_the_write_of_the_signed_intent_is_finished_by_the_exact_repeat(
        tmp_path, monkeypatch, signing_key, crash, owner):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    crashed(monkeypatch, p, crash, "snapshot", digest, owner=owner)
    left = message_files(p)
    assert len(left) == 1 and no_receipt(p)                  # the message file is the first effect
    assert op_file(p).exists() == (crash == "start")         # the record is the second
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    detail = waits(p, "snapshot", digest)                    # the exact repeat
    assert message_files(p) == left and (p.root / detail["message_path"]).samefile(left[0])
    op = records.read_op(p.root)
    assert op.stage == AWAITING_SIGNATURE and [path.name for path in install_files(p)] == [
        f"first_commit.index-{op.nonce}"]
    assert verify(records.read_install(p.root, op), "sha1").marker[0] == op.nonce
    owner_makes_the_commit(p, detail)
    assert confirm(p, "snapshot", digest=digest).status == 201
    assert message_files(p) == [] and own_leftovers(p) == []


# --- the file goes with the receipt, and only the file the product wrote -------------------


def test_a_signed_first_commit_removes_the_message_file_it_wrote_once_the_receipt_stands(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    assert message_files(p) and (p.root / detail["message_path"]).is_file()
    owner_makes_the_commit(p, detail)
    assert confirm(p, "snapshot", digest=digest).status == 201
    assert message_files(p) == [] and not no_receipt(p) and own_leftovers(p) == []


def edit_it(p, path, tmp_path):
    path.write_bytes(b"another message\n")


def give_it_a_second_name(p, path, tmp_path):
    os.link(path, tmp_path / "second-name-of-the-message.txt")


@pytest.mark.parametrize("change", [edit_it, give_it_a_second_name],
                         ids=["bytes_changed", "second_name"])
def test_a_message_file_that_is_no_longer_the_one_the_product_wrote_is_kept(
        tmp_path, monkeypatch, signing_key, change):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    owner_makes_the_commit(p, detail)
    crashed(monkeypatch, p, "_do_install_index", "snapshot", digest)   # recognised, then it died
    path = p.root / detail["message_path"]
    try:
        change(p, path, tmp_path)
    except OSError as error:
        pytest.skip(str(error))
    before = path.read_bytes()
    assert confirm(p, "snapshot", digest=digest).status == 201
    assert path.read_bytes() == before and [kept.name for kept in message_files(p)] == [path.name]
    assert not no_receipt(p) and own_leftovers(p) == []


def test_a_finish_that_died_right_after_the_receipt_has_the_message_removed_by_the_next_repeat(
        tmp_path, monkeypatch, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    owner_makes_the_commit(p, waits(p, "snapshot", digest))
    crashed(monkeypatch, p, "write_receipt", "snapshot", digest, owner=records)
    assert not no_receipt(p) and op_file(p).exists() and len(message_files(p)) == 1
    assert confirm(p, "snapshot", digest=digest).status == 200
    assert message_files(p) == [] and own_leftovers(p) == []


def test_a_finish_that_died_after_the_message_was_removed_has_its_record_retired_by_the_repeat(
        tmp_path, monkeypatch, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    owner_makes_the_commit(p, waits(p, "snapshot", digest))
    crashed(monkeypatch, p, "remove_finished_message", "snapshot", digest, owner=signing)
    assert message_files(p) == [] and not no_receipt(p)             # the message went first ...
    assert op_file(p).exists()                                      # ... the record is still here
    assert confirm(p, "snapshot", digest=digest).status == 200
    assert message_files(p) == [] and own_leftovers(p) == []
