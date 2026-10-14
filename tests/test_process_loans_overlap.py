"""Loans that overlap in time: two attempts on one install folder, and a hand that edits a DACL.

The pinned install folder of a harness is shared by every attempt of that harness and by every
project. A loan is therefore returned by taking away ITS OWN entries from the DACL as it stands at
the exit, never by writing back the DACL that was read at the start: that second way gives the
other attempt's entry away at the first exit and keeps a dead profile's entry at the last.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor.command.adapters.process_loans import FolderLoans
from tests.test_process_loans import HOME, LoanHold, OWNER, PRIOR, masks, prior_acl, world

SID2 = "S-1-15-2-1-2-3-4-5-6-8"
RX = 0x1200A9
FOREIGN = "(A;OICI;0x1200a9;;;S-1-5-21-77)"


def second_attempt(w):
    """A second profile of the same owner, with a loan of its own on the SAME install folder."""
    profile_path, sid = w.store.create_profile()
    folders = {"work": w.root / "work" / "t2", "home": w.root / HOME / "b",
               "install": w.folders["install"]}
    for key in ("work", "home"):
        folders[key].mkdir(parents=True)
        w.state[str(folders[key])] = (PRIOR, False, OWNER)
    loans = FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ)
    return SimpleNamespace(loans=loans, profile_path=profile_path, sid=sid, folders=folders)


@pytest.mark.parametrize("order", ["first-in-first-out", "first-in-last-out"])
def test_of_two_loans_on_one_install_folder_the_one_that_leaves_takes_back_only_its_own_entries(
        tmp_path, order):
    w = world(tmp_path, extra_sids=(SID2,))
    prior_acl(w)
    b = second_attempt(w)
    record_a = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    record_b = b.loans.grant(b.profile_path, b.sid, "dispatch", b.folders)
    install = str(w.folders["install"])
    assert masks(w.state[install][0], w.sid) == [RX] and masks(w.state[install][0], SID2) == [RX]
    first, second = (w.loans, record_a, w.sid), (b.loans, record_b, SID2)
    (leaving, record, gone), (staying, kept_record, kept) = {
        "first-in-first-out": (first, second), "first-in-last-out": (second, first)}[order]
    leaving.restore(record)
    during = w.state[install][0]
    assert gone not in during
    assert masks(during, kept) == [RX], "the attempt still running keeps its read-and-execute"
    staying.restore(kept_record)
    assert w.state[install] == (PRIOR, False, OWNER), "no entry of either profile is left"


def test_an_entry_another_hand_added_while_the_loan_stood_is_still_there_after_it(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    install = str(w.folders["install"])
    sddl, protected, owner = w.state[install]
    w.state[install] = (sddl + FOREIGN, protected, owner)  # a later `icacls /grant`, at the end
    w.loans.restore(record)
    assert w.state[install] == (PRIOR + FOREIGN, False, OWNER)


def test_a_grant_is_built_on_the_dacl_as_it_is_when_the_change_is_made_not_as_it_was_read(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    install = str(w.folders["install"])
    real, seen = w.store.native.acl_snapshot, []

    def snapshot(hold):
        found = real(hold)
        if str(hold.path) == install and not seen:
            seen.append(found)  # the journalled read; another hand edits right after it
            w.state[install] = (found[0] + FOREIGN, found[1], found[2])
        return found

    w.store.native.acl_snapshot = snapshot
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    now = w.state[install][0]
    assert FOREIGN in now and masks(now, w.sid) == [RX]
