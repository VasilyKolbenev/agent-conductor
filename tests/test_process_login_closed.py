"""The leased login home is NOT loaned as shipped: its gate is closed until the review ruling.

The loan gives an attempt the rights of a credential refresh on the leased login home, and those
rights let it create files in the home and overwrite every file beneath it (they reach nested
objects by inheritance). The vendor's own executable configuration lives in that home, and the
product runs the vendor there again outside the boundary: a status read, a quota read, the person's
sign-in. So the runner loans the home only while `process_boundary.LOGIN_LOAN_OPEN` is True, and as
shipped it is not. These tests pin the shipped state, on the loan journal with fake natives and on
the real runner; the tests of the loan itself open the gate (`tests/login_gate.py`).
"""
from __future__ import annotations

import os

import pytest

from conductor import ownership
from conductor.command.adapters import process_boundary
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from tests.test_process_loans import OWNER, PRIOR, prior_acl, record_files, world
from tests.test_process_login_grant import AnyHold, login_world

CLOSED = "profile_acl_invalid: the login home is not loaned"


def test_the_gate_of_the_login_home_is_closed_as_shipped():
    assert process_boundary.LOGIN_LOAN_OPEN is False
    assert process_boundary.login_loan_provided() is False


def test_the_fact_a_door_asks_follows_the_gate_and_only_the_boolean_true_opens_it(monkeypatch):
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)
    assert process_boundary.login_loan_provided() is True
    for not_true in (1, "yes", None, object()):
        monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", not_true)
        assert process_boundary.login_loan_provided() is False, repr(not_true)


@pytest.mark.parametrize("mode", ["dispatch", "review"])
def test_a_login_home_is_not_loaned_as_shipped_and_nothing_is_journalled_or_changed(tmp_path, mode):
    w = login_world(tmp_path)
    with pytest.raises(ProfileRefused, match=CLOSED):
        w.loans.grant(w.profile_path, w.sid, mode, w.folders)
    assert record_files(w) == []
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


def test_the_closed_gate_is_judged_before_the_lease_or_the_projects_logins_are_read(tmp_path):
    w = login_world(tmp_path)
    w.loans.leased_login = lambda: pytest.fail("the login lease was read")
    w.loans.login_homes = lambda: pytest.fail("the project's login folders were read")
    with pytest.raises(ProfileRefused, match=CLOSED):
        w.loans.targets(w.folders)


def test_a_loan_that_names_no_login_home_is_not_touched_by_the_closed_gate(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.sid in w.state[str(w.folders["work"])][0] and record.is_file()


def test_closing_the_gate_does_not_strand_a_login_loan_a_build_with_it_open_left_behind(
        tmp_path, monkeypatch):
    w = login_world(tmp_path)
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)  # the crash leaves this record
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", False)
    assert w.sid in w.state[str(w.leased)][0]
    again = FolderLoans(w.store, w.store.native, hold_factory=AnyHold, environ=w.environ,
                        leased_login=lambda: None)
    again.recover()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


@pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans")
def test_the_runner_refuses_a_login_home_its_own_lease_names_before_a_profile_exists(tmp_path):
    from tests.test_process_loans_native import same_acl, snapshot
    from tests.test_process_login_native import LoginSite
    site = LoginSite(tmp_path)
    runner, before = ProcessRunner(site.root), snapshot(site.login)
    with ownership.acquire_owner(site.root):
        with ProcessRunner.login_write_guard(site.root, str(site.login)):
            with pytest.raises(ProfileRefused, match=CLOSED):
                with runner.container_profile(mode="dispatch", folders=site.folders):
                    pytest.fail("the block must not be entered")
    journal = site.root / "conductor.v3" / "process-profiles"
    assert not journal.exists() or list(journal.glob("*")) == []
    assert same_acl(snapshot(site.login), before)
