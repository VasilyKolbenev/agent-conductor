"""What the login-home loan refuses, before any change, against the REAL login lease.

The boundary grants the leased login home of the attempt and nothing else. The lease is the one the
project owner holds for the calling thread (`ownership_login`), so these tests take real leases, in
this thread and in another, over a loan journal whose ACL natives are fakes. Each refusal asserts
its own reason and that no record was written and no folder was held or changed.
"""
from __future__ import annotations

import os
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from conductor import ownership, ownership_transition
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders, login_home_named
from conductor.command.adapters.process_loans import FolderLoans
from tests.test_process_login_grant import AnyHold
from tests.test_process_loans import HOME, _refused, world

ABSOLUTE = str(Path("/abs").resolve())
SHAPE = "DecemberCommand/logins/<name>"


class LeasedWorld:
    """A loan world over a really owned project, with login homes in `DecemberCommand/logins`."""

    def __init__(self, base):
        self.w = world(base)
        self.logins = base / "DecemberCommand" / "logins"
        self.homes = {name: self.logins / name for name in ("claude-code", "codex")}
        for home in self.homes.values():
            home.mkdir(parents=True)
        (self.w.root / "conductor").mkdir(parents=True, exist_ok=True)
        ownership_transition.activate(self.w.root, legacy_writers_stopped=True)
        self.folders = {"work": self.w.folders["work"], "install": self.w.folders["install"]}
        self.listed = list(self.homes.values())
        self.owner = None

    def loans(self):
        """The loans of an attempt: the project's providers list every login, and the owner's
        lease decides which one this thread holds."""
        self.w.loans = FolderLoans(self.w.store, self.w.store.native, hold_factory=AnyHold,
                                   environ=self.w.environ, login_homes=lambda: tuple(self.listed))
        return self.w

    def refuses(self, login, reason, **extra):
        self.loans()
        _refused(self.w, {**self.folders, "login": login, **extra}, reason)


@contextmanager
def owned(site):
    with ownership.acquire_owner(site.w.root) as owner:
        site.owner = owner
        yield site


@pytest.fixture
def lw(tmp_path):
    with owned(LeasedWorld(tmp_path)) as site:
        yield site


@contextmanager
def lease_of(site, home):
    with ProcessRunner.login_write_guard(site.w.root, str(home)):
        yield


@contextmanager
def lease_held_by_another_thread(site, home):
    entered, leave = threading.Event(), threading.Event()

    def holder():
        with lease_of(site, home):
            entered.set()
            leave.wait(30)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert entered.wait(30), "the other attempt did not take its lease"
        yield
    finally:
        leave.set()
        thread.join(30)


@pytest.mark.parametrize("where", [
    "codex", ".", "..", "../../elsewhere/claude-code", "claude-code/sub"],
    ids=["another-harness", "logins-itself", "above-the-logins", "outside-everything",
         "inside-the-leased-home"])
def test_a_login_home_the_attempts_lease_does_not_name_is_refused(lw, where):
    target = (lw.logins / where).resolve()
    target.mkdir(parents=True, exist_ok=True)
    with lease_of(lw, lw.homes["claude-code"]):
        lw.refuses(target, "lease does not name")


def test_an_attempt_that_holds_no_lease_is_refused_a_home_another_attempt_holds(lw):
    with lease_held_by_another_thread(lw, lw.homes["claude-code"]):
        lw.refuses(lw.homes["claude-code"], "holds no login lease")


def test_an_attempt_that_holds_another_homes_lease_is_refused_the_home_another_attempt_holds(lw):
    with lease_held_by_another_thread(lw, lw.homes["claude-code"]):
        with lease_of(lw, lw.homes["codex"]):
            lw.refuses(lw.homes["claude-code"], "lease does not name")


def test_the_lease_the_owner_no_longer_trusts_is_no_lease(lw):
    with lease_of(lw, lw.homes["claude-code"]):
        lease = lw.owner._logins.local.lease
        lease.uncertain = True  # what a process loan that did not prove its end leaves
        try:
            lw.refuses(lw.homes["claude-code"], "login lease of the attempt is not standing")
        finally:
            lease.uncertain = False


@pytest.mark.parametrize("path", [
    "elsewhere/claude-code", "Other/logins/claude-code", "DecemberCommand/logs/claude-code",
    "DecemberCommand/logins/claude-code/deep", "DecemberCommand/logins", "DecemberCommand"])
def test_a_leased_folder_that_is_no_login_home_of_the_product_is_refused(lw, path):
    target = (lw.logins.parent.parent / path).resolve()
    target.mkdir(parents=True, exist_ok=True)
    with lease_of(lw, target):
        lw.refuses(target, SHAPE)


def test_the_names_of_the_login_shape_are_found_whatever_their_case(lw):
    mixed = lw.logins.parent.parent / "alt" / "DECEMBERCOMMAND" / "LOGINS" / "Claude-Code"
    mixed.mkdir(parents=True)
    with lease_of(lw, mixed):
        found = lw.loans().loans.targets({**lw.folders, "login": mixed})
    assert found["login"] == mixed.resolve()


def test_a_login_home_and_a_per_spawn_home_are_never_loaned_together(lw):
    with lease_of(lw, lw.homes["claude-code"]):
        lw.refuses(lw.homes["claude-code"], "never both", home=lw.w.folders["home"])
    with pytest.raises(ValueError, match="never both"):
        AttemptFolders(work="work/t1", home=f"{HOME}/a", install=ABSOLUTE, login=ABSOLUTE)


@pytest.mark.parametrize("holder", ["work", "install"])
def test_a_login_home_inside_the_work_or_the_install_folder_is_refused(lw, holder):
    home = lw.folders[holder] / "DecemberCommand" / "logins" / "claude-code"
    home.mkdir(parents=True)
    lw.listed = [home]
    with lease_of(lw, home):
        lw.refuses(home, f"overlaps the {holder} folder")


def test_a_login_home_inside_the_project_is_refused_whatever_its_name(lw):
    home = lw.w.root / "DecemberCommand" / "logins" / "claude-code"
    home.mkdir(parents=True)
    lw.listed = [home]
    with lease_of(lw, home):
        lw.refuses(home, "overlaps the project folder")


def test_a_leased_folder_that_only_looks_like_a_login_home_is_not_the_leased_one(lw):
    lookalike = lw.logins.parent.parent / "other" / "DecemberCommand" / "logins" / "claude-code"
    lookalike.mkdir(parents=True)
    assert login_home_named(str(lookalike)), "the spelling is the product's"
    with lease_of(lw, lw.homes["claude-code"]):
        lw.refuses(lookalike, "lease does not name")


def test_a_login_home_that_holds_the_work_folder_is_refused(tmp_path):
    base = tmp_path / "DecemberCommand" / "logins" / "claude-code" / "inner"
    base.mkdir(parents=True)
    with owned(LeasedWorld(base)) as site:
        holder = base.parent
        site.listed = [holder]
        with lease_of(site, holder):
            site.refuses(holder, "overlaps the work folder")


@pytest.mark.parametrize("make, reason", [("absent", "cannot be read"),
                                          ("file", "not a plain directory")])
def test_a_login_home_that_is_gone_or_is_a_file_is_refused(lw, make, reason):
    target = lw.logins / "gone"
    if make == "file":
        target.write_text("not a folder", encoding="utf-8")
    with lease_of(lw, lw.homes["claude-code"]):
        lw.refuses(target, reason)


@pytest.mark.skipif(os.name != "nt", reason="a junction is how Windows makes a folder link")
def test_a_login_home_that_is_a_junction_is_refused(lw):
    link = lw.logins / "link"
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(lw.homes["claude-code"])],
                          capture_output=True)
    assert made.returncode == 0, made.stderr
    with lease_of(lw, lw.homes["claude-code"]):
        lw.refuses(link, "not a plain directory")


def test_an_install_folder_that_is_a_login_folder_is_still_refused_beside_a_leased_login_home(lw):
    lw.listed = [lw.homes["claude-code"], lw.folders["install"]]
    with lease_of(lw, lw.homes["claude-code"]):
        lw.refuses(lw.homes["claude-code"], "login folder, lies in one or holds one")


@pytest.mark.parametrize("path, named", [
    (r"C:\Users\User\DecemberCommand\logins\claude-code", True),
    ("/home/user/DecemberCommand/logins/codex", True),
    ("c:/x/decembercommand/LOGINS/Kimi-Code", True),
    ("C:\\x\\DecemberCommand\\logins\\claude-code\\", True),
    (r"C:\Users\User\DecemberCommand\logins", False),
    (r"C:\Users\User\DecemberCommand", False),
    (r"C:\Users\User\DecemberCommand\logins\claude-code\sub", False),
    (r"C:\Users\User\Other\logins\claude-code", False),
    (r"C:\Users\User\DecemberCommand\logs\claude-code", False),
    (r"C:\Users\User\DecemberCommand\logins\..\claude-code", False),
    ("logins/claude-code", False), ("", False), (None, False), (5, False)])
def test_a_login_home_is_named_by_the_place_the_product_keeps_it(path, named):
    assert login_home_named(path) is named
