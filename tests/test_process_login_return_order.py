"""The rights of a login home are back before the lease on it ends, whatever order blocks end in.

The grant counts as one loan against the standing lease (`ownership_login.LoginLease.hold`), so a
caller that leaves the lease's block while the grant stands, or whose return failed, gets the same
refusal a process loan that did not end gets: the lease is not released as clean. The leases here
are the real ones; only the ACL natives are fakes.
"""
from __future__ import annotations

import pytest

from conductor import ownership_login
from conductor.command.adapters.process import OwnershipError
from conductor.command.adapters.process_loans import FolderLoans
from tests.test_process_login_refusals import LeasedWorld, lease_of, owned


@pytest.fixture
def lw(tmp_path):
    with owned(LeasedWorld(tmp_path)) as site:
        yield site


def grant_on(site, home):
    w = site.loans()
    folders = {**site.folders, "login": home}
    return w, w.loans.grant(w.profile_path, w.sid, "dispatch", folders)


def test_the_return_ends_before_the_lease_does_and_both_end_clean(lw, monkeypatch):
    events = []
    close, restore = ownership_login.LoginLease.close, FolderLoans.restore

    def closing(self):
        events.append("lease-closes")
        return close(self)

    def restoring(self, *args, **kwargs):
        restore(self, *args, **kwargs)
        events.append("rights-returned")

    monkeypatch.setattr(ownership_login.LoginLease, "close", closing)
    monkeypatch.setattr(FolderLoans, "restore", restoring)
    home = lw.homes["claude-code"]
    with lease_of(lw, home):
        w, record = grant_on(lw, home)
        w.loans.restore(record)
    assert events == ["rights-returned", "lease-closes"]


def test_a_lease_whose_block_ends_while_the_grant_stands_is_not_released_as_clean(lw):
    home = lw.homes["claude-code"]
    with pytest.raises(OwnershipError, match="native process loans"):
        with lease_of(lw, home):
            grant_on(lw, home)  # the block ends here, and the rights were never returned


def test_a_return_that_failed_leaves_the_lease_uncertain_at_the_end_of_its_block(lw):
    home = lw.homes["claude-code"]
    with pytest.raises(OwnershipError, match="uncertain"):
        with lease_of(lw, home):
            w, record = grant_on(lw, home)
            real = w.store.native.acl_set

            def failing(hold, sddl, *, protected):
                if hold.path == home.resolve():
                    raise OSError("native refusal on the return")
                real(hold, sddl, protected=protected)

            w.store.native.acl_set = failing
            with pytest.raises(OSError, match="native refusal"):
                w.loans.restore(record)
