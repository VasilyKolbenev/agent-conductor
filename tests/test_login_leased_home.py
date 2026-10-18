"""The project owner names the login home the calling thread's standing lease holds.

The boundary grants the leased login home and no other folder. The fact that the attempt holds the
lease on a given home comes from the lease itself, which is thread-bound, and not from any value a
caller writes down; the home is named by the identity the lease recorded, and the lease can be
asked to count one loan against its closing, so a grant on the home ends before the lease does.
"""
from __future__ import annotations

import threading

import pytest

from conductor import ownership, ownership_login, ownership_transition
from conductor.command.adapters.process import OwnershipError, ProcessRunner
from conductor.ownership_native import identity


def an_owned_project(base):
    root = (base / "project").resolve()
    (root / "conductor").mkdir(parents=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    return root


def a_login_home(base, name):
    home = base / "DecemberCommand" / "logins" / name
    home.mkdir(parents=True)
    return home.resolve()


def test_the_owner_names_the_login_home_the_calling_thread_holds_while_it_holds_it(tmp_path):
    root, home = an_owned_project(tmp_path), a_login_home(tmp_path, "claude-code")
    with ownership.acquire_owner(root) as owner:
        assert owner.leased_login() is None, "no lease is held before the guard is entered"
        with ProcessRunner.login_write_guard(root, str(home)):
            assert owner.leased_login().home == home
        assert owner.leased_login() is None, "the lease is gone with the guard"


def test_the_leased_home_is_named_by_the_identity_the_lease_recorded_and_not_by_its_spelling(
        tmp_path):
    root, home = an_owned_project(tmp_path), a_login_home(tmp_path, "claude-code")
    lookalike = a_login_home(tmp_path / "elsewhere", "claude-code")
    with ownership.acquire_owner(root) as owner:
        with ProcessRunner.login_write_guard(root, str(home)):
            leased = owner.leased_login()
    assert leased.identity == tuple(identity(home))
    assert leased.identity != tuple(identity(lookalike)), "same spelling of the end, another folder"


def test_a_lease_held_by_another_thread_is_not_the_calling_threads_lease(tmp_path):
    root, home = an_owned_project(tmp_path), a_login_home(tmp_path, "claude-code")
    entered, leave, seen = threading.Event(), threading.Event(), []

    def holder():
        with ProcessRunner.login_write_guard(root, str(home)):
            entered.set()
            assert leave.wait(30)

    with ownership.acquire_owner(root) as owner:
        thread = threading.Thread(target=holder)
        thread.start()
        try:
            assert entered.wait(30)
            seen.append(owner.leased_login())
        finally:
            leave.set()
            thread.join(30)
    assert seen == [None]


def test_the_two_leases_of_two_threads_each_name_their_own_home(tmp_path):
    root = an_owned_project(tmp_path)
    homes = {name: a_login_home(tmp_path, name) for name in ("claude-code", "codex")}
    both, leave, seen = threading.Barrier(3, timeout=30), threading.Event(), {}

    def holder(name, owner):
        with ProcessRunner.login_write_guard(root, str(homes[name])):
            seen[name] = owner.leased_login().home
            both.wait()
            assert leave.wait(30)

    with ownership.acquire_owner(root) as owner:
        threads = [threading.Thread(target=holder, args=(name, owner)) for name in homes]
        for thread in threads:
            thread.start()
        try:
            both.wait()
        finally:
            leave.set()
            for thread in threads:
                thread.join(30)
    assert seen == homes


def test_a_lease_the_owner_no_longer_trusts_names_no_home(tmp_path):
    root, home = an_owned_project(tmp_path), a_login_home(tmp_path, "claude-code")
    with ownership.acquire_owner(root) as owner:
        with ProcessRunner.login_write_guard(root, str(home)):
            lease = owner._logins.local.lease
            lease.uncertain = True  # what a process loan that did not prove its end leaves
            with pytest.raises(ownership.OwnerRefused, match="uncertain"):
                owner.leased_login()
            lease.uncertain = False


def test_the_scopes_of_the_login_lease_know_nothing_without_one():
    assert ownership_login.LoginScopes().held() is None


def test_a_hold_on_the_lease_keeps_it_from_closing_until_it_is_retired_as_proven(tmp_path):
    root, home = an_owned_project(tmp_path), a_login_home(tmp_path, "claude-code")
    with ownership.acquire_owner(root) as owner:
        with ProcessRunner.login_write_guard(root, str(home)):
            retire = owner.leased_login().hold()
            retire(True)
        reached = []
        with pytest.raises(OwnershipError, match="native process loans"):
            with ProcessRunner.login_write_guard(root, str(home)):
                owner.leased_login().hold()  # never retired
                reached.append(True)
        assert reached == [True]


def test_a_hold_retired_as_unproven_leaves_the_lease_uncertain_and_it_does_not_close_clean(
        tmp_path):
    root, home = an_owned_project(tmp_path), a_login_home(tmp_path, "claude-code")
    with ownership.acquire_owner(root) as owner:
        reached = []
        with pytest.raises(OwnershipError, match="uncertain"):
            with ProcessRunner.login_write_guard(root, str(home)):
                owner.leased_login().hold()(False)
                reached.append(True)
        assert reached == [True], "the block ended by itself, and the lease then refused to close"
