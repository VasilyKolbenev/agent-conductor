"""A loan record that cannot be returned whole: what goes back anyway, and how the record ends.

A record names up to three folders. One of them can be gone astray (the work folder recreated after
a crash) while the others still carry the profile's entries. A recovery returns every folder it can
prove, says which one it could not, and leaves a way out that only the owner takes.
"""
from __future__ import annotations

import json
import os

import pytest

from conductor.command.adapters import process_loans
from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from tests.test_process_loans import LoanHold, OWNER, PRIOR, prior_acl, record_files, world

STRANGER = (OWNER + "x", True, OWNER)


def again(w):
    return FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ)


def phase(path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["phase"]


def granted_with_work_replaced(tmp_path):
    """A loan of three folders whose work folder is another folder by the time of the recovery."""
    w = world(tmp_path)
    prior_acl(w)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    work = w.folders["work"]
    work.rename(work.with_name("t1-moved"))  # the granted folder lives on, under another name
    work.mkdir()  # and another folder now has the name (its identity cannot be the old one)
    w.state[str(work)] = STRANGER
    return w, record


def returned(w, *keys) -> bool:
    return all(w.state[str(w.folders[key])] == (PRIOR, False, OWNER) for key in keys)


def test_a_work_folder_that_was_replaced_does_not_keep_the_install_and_the_home_from_going_back(
        tmp_path):
    w, record = granted_with_work_replaced(tmp_path)
    with pytest.raises(ProfileRefused) as raised:
        again(w).recover()
    assert returned(w, "install", "home")
    assert w.state[str(w.folders["work"])] == STRANGER, "the other folder is left as it is"
    assert phase(record) == "applied", "the record stays until the folder is accounted for"
    assert "work folder is not the one the record names" in str(raised.value)


def test_the_owner_can_give_up_a_folder_that_went_astray_and_the_rest_still_goes_back(tmp_path):
    w, record = granted_with_work_replaced(tmp_path)
    again(w).recover(abandon=True)
    assert returned(w, "install", "home")
    assert w.state[str(w.folders["work"])] == STRANGER
    assert phase(record) == "abandoned"
    again(w).recover()  # an abandoned record is never acted on again


def test_giving_a_loan_up_does_not_hide_a_folder_that_could_not_be_returned(tmp_path):
    w, record = granted_with_work_replaced(tmp_path)
    real = w.store.native.acl_set

    def refusing(hold, sddl, *, protected):
        if hold.path == w.folders["install"]:
            raise OSError("native refusal")
        real(hold, sddl, protected=protected)

    w.store.native.acl_set = refusing
    with pytest.raises(OSError, match="native refusal"):
        again(w).recover(abandon=True)
    assert returned(w, "home")
    assert phase(record) == "applied"


def test_a_record_that_cannot_be_read_does_not_keep_the_healthy_ones_from_going_back(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    (w.store.directory / f"loan-{'0' * 32}.json").write_text("{", encoding="utf-8")
    with pytest.raises(ProfileRefused, match="malformed"):
        again(w).recover()
    assert returned(w, "work", "home", "install")
    assert phase(record) == "retired"


def test_a_loan_whose_retire_write_was_lost_is_returned_again_without_harm(tmp_path, monkeypatch):
    w = world(tmp_path)
    prior_acl(w)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    real = process_loans._replace

    def lost(path, value):
        if value["phase"] == "retired":
            raise OSError("power cut")
        real(path, value)

    monkeypatch.setattr(process_loans, "_replace", lost)
    with pytest.raises(OSError, match="power cut"):
        w.loans.restore(record)
    monkeypatch.setattr(process_loans, "_replace", real)
    assert returned(w, "work", "home", "install") and phase(record) == "applied"
    again(w).recover()
    assert returned(w, "work", "home", "install") and phase(record) == "retired"


def test_a_failed_first_write_of_the_record_leaves_no_record_and_changes_no_acl(
        tmp_path, monkeypatch):
    w = world(tmp_path)
    prior_acl(w)

    def disk_full(descriptor):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", disk_full)
    with pytest.raises(OSError, match="disk full"):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    monkeypatch.undo()
    assert record_files(w) == [], "a half-written record would be malformed for good"
    assert list(w.store.directory.glob(".loan-*.tmp")) == []
    assert returned(w, "work", "home", "install")
