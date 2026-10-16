"""The leased login home is loaned to the attempt's AppContainer, with fake natives.

A subscription attempt keeps its vendor state in the operator's dedicated login home, which the
attempt holds under the shared login lease. The loan journal gives the profile an explicit list of
rights on that one folder for the attempt's life: what a credential refresh does (in-place write,
native rename over, delete then move) and nothing more. The folder itself and a nested directory
can be written into but not deleted, a nested regular file can be written and deleted but not run,
nothing can change an ACL or delete a child through the folder, and there is no deny entry. The
return takes the profile's own entries away again.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.ownership_login import LeasedLogin
from conductor.ownership_native import identity
from tests.test_process_loans import (
    DELETE_CHILD, LoanHold, OWNER, PRIOR, WRITE_DAC, WRITE_OWNER, masks, prior_acl, record_files,
    world)

DELETE, EXECUTE = 0x10000, 0x20
FOLDER, FILES = 0x1201BF, 0x13019F
ABSOLUTE = str(Path("/abs").resolve())


class AnyHold(LoanHold):
    """A held folder or, for the DACL of a hook object, a held file."""

    def __init__(self, path, *, directory, grants):
        assert directory or not grants, "only a folder is held for its DACL to be changed"
        self.path, self.identity = Path(path), identity(path)


def leased_fact(path, hold=None):
    """What the owner answers for a lease on `path`: the folder and its identity."""
    return None if path is None else LeasedLogin(Path(path), tuple(identity(path)), hold)


def login_world(tmp_path, *, name="claude-code"):
    """A loan world whose login home stands in `DecemberCommand/logins/<name>` and is leased."""
    w = world(tmp_path)
    login = tmp_path / "DecemberCommand" / "logins" / name
    login.mkdir(parents=True)
    (login / "auth.json").write_text("placeholder, not a credential", encoding="utf-8")
    w.folders = {"work": w.folders["work"], "install": w.folders["install"], "login": login}
    w.leased = login
    w.loans = loans_of(w)
    prior_acl(w)
    return w


def loans_of(w):
    """The attempt's loans: the project's providers list the login, and its lease names it."""
    return FolderLoans(w.store, w.store.native, hold_factory=AnyHold, environ=w.environ,
                       login_homes=lambda: (w.leased,), leased_login=lambda: leased_fact(w.leased))


def _entries(sddl):
    return re.findall(r"\([^()]*\)", sddl)


def test_the_folders_value_takes_a_login_home_as_an_absolute_folder_and_nothing_else():
    ok = AttemptFolders(work="work/t1", home=None, install=ABSOLUTE, login=ABSOLUTE)
    assert ok.login == ABSOLUTE
    assert AttemptFolders(work="work/t1", home=None, install=ABSOLUTE).login is None
    for bad in ("relative/login", "", 5, "a\x00b"):
        with pytest.raises(ValueError):
            AttemptFolders(work="work/t1", home=None, install=ABSOLUTE, login=bad)


def test_the_prior_acl_of_the_login_home_is_durable_before_the_first_native_change(tmp_path):
    w = login_world(tmp_path)
    seen = []
    real = w.store.native.acl_set

    def watched(hold, sddl, *, protected):
        files = record_files(w)
        assert len(files) == 1, "the record exists before any ACL is changed"
        row = json.loads(files[0].read_text(encoding="utf-8"))
        seen.append((row["phase"], {k: v["before"] for k, v in row["loans"].items()}))
        real(hold, sddl, protected=protected)

    w.store.native.acl_set = watched
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert seen[0][0] == "planned"
    assert set(seen[0][1]) == {"work", "install", "login"}
    assert seen[0][1]["login"] == PRIOR
    row = json.loads(record_files(w)[0].read_text(encoding="utf-8"))
    assert row["phase"] == "applied"
    assert row["loans"]["login"]["path"] == str(w.leased)
    assert row["loans"]["login"]["rights"] == "login"


def test_the_login_home_is_given_the_rights_of_a_refresh_and_not_the_right_to_change_its_acl(
        tmp_path):
    w = login_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    now = w.state[str(w.leased)][0]
    assert sorted(masks(now, w.sid)) == [FOLDER, FOLDER, FILES]
    for mask in masks(now, w.sid):
        assert not mask & (WRITE_DAC | WRITE_OWNER | DELETE_CHILD)
        assert mask != 0x1F01FF
    assert f"(A;;0x{FOLDER:x};;;{w.sid})" in now
    assert f"(A;CIIO;0x{FOLDER:x};;;{w.sid})" in now
    assert f"(A;OIIO;0x{FILES:x};;;{w.sid})" in now


def test_neither_the_login_home_nor_a_nested_directory_can_be_deleted_by_the_profile(tmp_path):
    w = login_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    directory_entries = [ace for ace in _entries(w.state[str(w.leased)][0])
                         if w.sid in ace and ace.split(";")[1] in ("", "CIIO")]
    assert len(directory_entries) == 2
    for ace in directory_entries:
        assert not int(ace.split(";")[2], 16) & DELETE, f"a directory entry can delete: {ace}"


def test_a_nested_regular_file_is_given_what_a_refresh_needs_and_the_right_to_run_nothing(tmp_path):
    w = login_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    (file_entry,) = [ace for ace in _entries(w.state[str(w.leased)][0])
                     if w.sid in ace and ace.split(";")[1] == "OIIO"]
    mask = int(file_entry.split(";")[2], 16)
    assert mask & DELETE, "delete-then-move and a rename over a file need DELETE on the file"
    assert mask & 0x2 and mask & 0x1, "an in-place rewrite reads and writes the data"
    assert not mask & EXECUTE, "a refresh runs nothing"


def test_the_grant_on_the_login_home_adds_no_deny_entry_and_keeps_every_entry_it_had(tmp_path):
    w = login_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    entries = _entries(w.state[str(w.leased)][0])
    assert [e for e in entries if w.sid in e and e.startswith("(D")] == []
    assert [e for e in entries if w.sid not in e] == _entries(PRIOR)
    assert entries[0] == _entries(PRIOR)[0], "the explicit deny of the folder stays in front"


@pytest.mark.parametrize("mode", ["dispatch", "review"])
def test_a_review_writes_the_login_home_like_a_dispatch_because_a_credential_refresh_is_a_write(
        tmp_path, mode):
    w = login_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, mode, w.folders)
    assert FOLDER in masks(w.state[str(w.leased)][0], w.sid)
    work_masks = masks(w.state[str(w.folders["work"])][0], w.sid)
    assert (work_masks == [0x1200A9]) is (mode == "review")


def test_the_only_folders_a_login_attempt_changes_are_its_work_its_install_and_the_leased_home(
        tmp_path):
    w = login_world(tmp_path)
    touched = []
    real = w.store.native.acl_set
    w.store.native.acl_set = lambda hold, sddl, *, protected: (
        touched.append(Path(hold.path)), real(hold, sddl, protected=protected))
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert sorted(touched) == sorted(w.folders.values())
    assert w.leased.parent not in touched and w.leased.parent.parent not in touched


def test_a_returned_login_loan_leaves_the_folder_and_its_acl_exactly_as_it_was(tmp_path):
    w = login_world(tmp_path)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.sid in w.state[str(w.leased)][0]
    w.loans.restore(record)
    assert w.state[str(w.leased)] == (PRIOR, False, OWNER)
    assert (w.leased / "auth.json").read_text(encoding="utf-8") == "placeholder, not a credential"
    assert json.loads(record.read_text(encoding="utf-8"))["phase"] == "retired"


def test_a_failed_grant_on_the_login_home_is_returned_whole_by_the_restore_that_follows(tmp_path):
    w = login_world(tmp_path)
    real, calls = w.store.native.acl_set, []

    def failing(hold, sddl, *, protected):
        calls.append(hold.path)
        if Path(hold.path) == w.leased:
            raise OSError("native refusal on the login home")
        real(hold, sddl, protected=protected)

    w.store.native.acl_set = failing
    with pytest.raises(OSError):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    w.store.native.acl_set = real
    w.loans.restore()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


def test_a_login_loan_a_crash_left_behind_is_returned_by_the_recovery_without_a_lease(tmp_path):
    w = login_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    w.leased = None  # the crash took the attempt and its lease with it
    again = FolderLoans(w.store, w.store.native, hold_factory=AnyHold, environ=w.environ,
                        leased_login=lambda: None)
    again.recover()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())
    assert json.loads(record_files(w)[0].read_text(encoding="utf-8"))["phase"] == "retired"


def test_the_grant_is_counted_against_the_lease_and_retired_as_proven_by_a_whole_return(tmp_path):
    w = login_world(tmp_path)
    retired = []
    held = leased_fact(w.leased, hold=lambda: retired.append)  # `retired.append` is the retire
    w.loans.leased_login = lambda: held
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert retired == [], "the lease is counted, not yet retired, while the grant stands"
    w.loans.restore(record)
    assert retired == [True]


def test_a_return_that_fails_retires_the_count_as_unproven_so_the_lease_cannot_end_clean(tmp_path):
    w = login_world(tmp_path)
    retired = []
    held = leased_fact(w.leased, hold=lambda: retired.append)
    w.loans.leased_login = lambda: held
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    real = w.store.native.acl_set

    def failing(hold, sddl, *, protected):
        if Path(hold.path) == w.leased:
            raise OSError("native refusal on the return")
        real(hold, sddl, protected=protected)

    w.store.native.acl_set = failing
    with pytest.raises(OSError):
        w.loans.restore(record)
    assert retired == [False]


def test_a_grant_refused_while_the_folders_are_observed_has_taken_no_count_at_all(tmp_path):
    w = login_world(tmp_path)
    retired = []
    held = leased_fact(w.leased, hold=lambda: retired.append)
    w.loans.leased_login = lambda: held
    w.store.native.acl_snapshot = lambda hold: (_ for _ in ()).throw(OSError("cannot read"))
    with pytest.raises(OSError):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    w.loans.restore()
    assert retired == [] and record_files(w) == []


def test_a_grant_that_never_reached_its_record_retires_the_count_as_proven_nothing_changed(
        tmp_path, monkeypatch):
    from conductor.command.adapters import process_loans
    w = login_world(tmp_path)
    retired = []
    held = leased_fact(w.leased, hold=lambda: retired.append)
    w.loans.leased_login = lambda: held
    monkeypatch.setattr(process_loans, "_replace",
                        lambda *args: (_ for _ in ()).throw(OSError("the journal is full")))
    with pytest.raises(OSError, match="journal is full"):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert retired == [], "the count stands until the attempt's block ends"
    w.loans.restore()
    assert retired == [True]
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


def test_a_login_attempt_that_holds_no_lease_has_no_count_to_retire_either(tmp_path):
    w = login_world(tmp_path)
    w.leased = None
    with pytest.raises(ProfileRefused, match="holds no login lease"):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    w.loans.restore()
    assert record_files(w) == []


def test_the_runner_takes_the_login_home_of_a_folders_value_and_still_takes_one_without_the_field(
        tmp_path):
    root = tmp_path / "project"
    (root / "work" / "t1").mkdir(parents=True)
    runner = ProcessRunner(root)
    old = SimpleNamespace(work="work/t1", home=None, install=ABSOLUTE)  # the three-field value
    assert set(runner._loaned(old)) == {"work", "install"}
    new = AttemptFolders(work="work/t1", home=None, install=ABSOLUTE, login=ABSOLUTE)
    assert runner._loaned(new)["login"] == Path(ABSOLUTE)
