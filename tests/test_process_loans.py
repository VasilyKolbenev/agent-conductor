"""ACL loans on EXISTING product-owned folders of one AppContainer attempt (fake natives).

The fresh folders of an attempt are made, granted and deleted by `AttemptAclJournal`. A loan is the
other case: `work/<id>`, the per-spawn home and the pinned install folder already exist and are not
the journal's to delete. The journal records each folder's prior DACL and identity before the first
change, adds only entries for the attempt's profile, and puts the prior DACL back by identity.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_loans import FolderLoans, loan_sddl
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.ownership_native import identity
from tests.test_process_acl import SID, fixture

OWNER = "S-1-5-21-1"
PRIOR = ("O:S-1-5-21-1D:AI(D;;0x2;;;S-1-5-21-9)(A;OICIID;FA;;;BA)(A;OICIID;FA;;;SY)"
         "(A;OICIID;0x1200a9;;;BU)")
WRITE_DAC, WRITE_OWNER, DELETE_CHILD = 0x40000, 0x80000, 0x40
#: The folder a catalogued harness keeps its per-spawn homes in; a loan names no other home root.
HOME = ".claude-home"


class LoanHold:
    """A held directory without the OS: identity from the file system, as the real hold reads it."""

    def __init__(self, path, *, directory, grants):
        assert directory and grants, "a loan holds a directory for its DACL, never to delete it"
        self.path, self.identity = Path(path), identity(path)

    def check(self):
        assert identity(self.path) == self.identity

    def close(self):
        pass


def world(tmp_path, *, extra_sids=()):
    store, _acl, profile_path, sid, state = fixture(tmp_path, extra_sids=extra_sids)
    root = tmp_path / "project"
    folders = {"work": root / "work" / "t1", "home": root / HOME / "a",
               "install": tmp_path / "harnesses" / "kit" / "1.0"}
    for path in folders.values():
        path.mkdir(parents=True)
    (folders["work"] / "seed.txt").write_text("seed", encoding="utf-8")
    store.owner_root = root
    environ = {"SystemRoot": str(tmp_path / "winnt"), "ProgramFiles": str(tmp_path / "pf"),
               "USERPROFILE": str(tmp_path / "profile")}
    loans = FolderLoans(store, store.native, hold_factory=LoanHold, environ=environ)
    return SimpleNamespace(store=store, loans=loans, profile_path=profile_path, sid=sid,
                           state=state, root=root, folders=folders, environ=environ)


def prior_acl(w, *, protected=False):
    for path in w.folders.values():
        w.state[str(path)] = (PRIOR, protected, OWNER)


def record_files(w):
    return sorted(w.store.directory.glob("loan-*.json"))


def masks(sddl, sid):
    return [int(m, 16) for m in re.findall(r"\(A;[A-Z]*;(0x[0-9a-f]+);;;" + sid + r"\)", sddl)]


def test_a_loan_adds_only_entries_for_the_profile_and_keeps_every_entry_the_folder_had():
    done = loan_sddl(PRIOR, SID, "modify")
    entries = re.findall(r"\([^()]*\)", done)
    old = re.findall(r"\([^()]*\)", PRIOR)
    assert [e for e in entries if SID not in e] == old
    assert entries[0] == old[0], "the explicit deny stays first; the grant goes after it"
    assert done.startswith("O:S-1-5-21-1D:AI")


@pytest.mark.parametrize("rights", ["modify", "rx"])
def test_a_loan_names_explicit_rights_never_full_control_nor_the_right_to_change_the_acl(rights):
    for mask in masks(loan_sddl(PRIOR, SID, rights), SID):
        assert not mask & (WRITE_DAC | WRITE_OWNER | DELETE_CHILD)
        assert mask != 0x1F01FF


def test_modify_cannot_delete_the_folder_itself_and_rx_cannot_write_at_all():
    modify = loan_sddl(PRIOR, SID, "modify")
    assert "(A;;0x1201bf;;;" + SID + ")" in modify
    assert "(A;OICIIO;0x1301bf;;;" + SID + ")" in modify
    rx = loan_sddl(PRIOR, SID, "rx")
    assert masks(rx, SID) == [0x1200A9] and "(A;OICI;0x1200a9;;;" + SID + ")" in rx


@pytest.mark.parametrize("text", [
    "", "D:(A;;FA;;;SY)", "O:S-1-5-21-1D:(XA;;FA;;;SY;(Member_of{SID(BA)}))",
    "O:S-1-5-21-1D:(A;;FA;;;SY"])
def test_a_dacl_text_the_loan_does_not_understand_is_refused_not_guessed(text):
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        loan_sddl(text, SID, "modify")


def test_the_prior_acl_and_identity_are_durable_before_the_first_native_change(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
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
    assert set(seen[0][1]) == {"work", "home", "install"}
    assert all(before == PRIOR for before in seen[0][1].values())
    assert json.loads(record_files(w)[0].read_text(encoding="utf-8"))["phase"] == "applied"


def test_a_returned_loan_leaves_every_folder_and_acl_exactly_as_it_was(tmp_path):
    w = world(tmp_path)
    prior_acl(w, protected=False)
    w.state[str(w.folders["home"])] = (PRIOR, True, OWNER)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert all(SID in w.state[str(path)][0] for path in w.folders.values())
    assert w.state[str(w.folders["home"])][1] is True, "protection is kept as the folder had it"
    w.loans.restore(record)
    assert w.state[str(w.folders["work"])] == (PRIOR, False, OWNER)
    assert w.state[str(w.folders["home"])] == (PRIOR, True, OWNER)
    assert w.state[str(w.folders["install"])] == (PRIOR, False, OWNER)
    assert (w.folders["work"] / "seed.txt").read_text(encoding="utf-8") == "seed"
    assert json.loads(record.read_text(encoding="utf-8"))["phase"] == "retired"


def test_the_review_mode_loans_the_work_folder_read_only_and_the_home_still_writable(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    w.loans.grant(w.profile_path, w.sid, "review", w.folders)
    assert masks(w.state[str(w.folders["work"])][0], SID) == [0x1200A9]
    assert masks(w.state[str(w.folders["install"])][0], SID) == [0x1200A9]
    assert 0x1201BF in masks(w.state[str(w.folders["home"])][0], SID)


def test_a_loan_without_a_home_grants_two_folders_and_journals_two(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    folders = {k: v for k, v in w.folders.items() if k != "home"}
    w.loans.grant(w.profile_path, w.sid, "dispatch", folders)
    row = json.loads(record_files(w)[0].read_text(encoding="utf-8"))
    assert set(row["loans"]) == {"work", "install"}
    assert SID not in w.state.get(str(w.folders["home"]), ("",))[0]


def test_a_failed_grant_is_returned_whole_by_the_restore_that_follows_it(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    real = w.store.native.acl_set
    calls = []

    def failing(hold, sddl, *, protected):
        calls.append(hold.path)
        if len(calls) == 2:
            raise OSError("native refusal")
        real(hold, sddl, protected=protected)

    w.store.native.acl_set = failing
    with pytest.raises(OSError):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    w.store.native.acl_set = real
    w.loans.restore()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


def test_a_loan_a_crash_left_behind_is_returned_by_the_recovery_by_identity(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    again = FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ)
    again.recover()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())
    assert json.loads(record_files(w)[0].read_text(encoding="utf-8"))["phase"] == "retired"
    again.recover()  # a retired record is never acted on twice


def test_recovery_will_not_touch_a_folder_that_is_no_longer_the_one_the_record_names(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    work = w.folders["work"]
    work.rename(work.with_name("t1-moved"))  # the granted folder lives on, under another name
    work.mkdir()  # and another folder now has the name (its identity cannot be the old one)
    stranger = (OWNER + "x", True, OWNER)
    w.state[str(work)] = stranger
    again = FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ)
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        again.recover()
    assert w.state[str(work)] == stranger
    assert json.loads(record_files(w)[0].read_text(encoding="utf-8"))["phase"] == "applied"


def test_a_loaned_folder_that_is_gone_has_nothing_to_return_and_the_record_retires(tmp_path):
    w = world(tmp_path)
    prior_acl(w)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    (w.folders["home"] / "x.txt").write_text("x", encoding="utf-8")
    (w.folders["home"] / "x.txt").unlink()
    w.folders["home"].rmdir()
    again = FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ)
    again.recover()
    assert w.state[str(w.folders["work"])] == (PRIOR, False, OWNER)
    assert json.loads(record_files(w)[0].read_text(encoding="utf-8"))["phase"] == "retired"


def _refused(w, folders, reason=""):
    """The grant is refused as `profile_acl_invalid`, for a reason that contains `reason`, and
    nothing is recorded or changed."""
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*" + reason):
        w.loans.grant(w.profile_path, w.sid, "dispatch", folders)
    assert record_files(w) == []
    assert all(str(path) not in w.state for path in folders.values())


@pytest.mark.parametrize("where, reason", [
    ("root", "overlaps the project"), ("above-root", "overlaps the project"),
    ("profile", "user profile"), ("above-profile", "user profile"),
    ("system", "system program"), ("inside-system", "system program"),
    ("program-files", "system program"), ("inside-program-files", "system program")])
def test_an_install_folder_that_would_widen_the_owners_or_the_systems_reach_is_refused(
        tmp_path, where, reason):
    w = world(tmp_path)
    profile, winnt, files = (tmp_path / n for n in ("accounts/bob", "winnt", "pf"))
    w.environ["USERPROFILE"] = str(profile)  # beside the project, so no other rule is the reason
    for path in (profile / "deep", winnt / "system32", files / "node"):
        path.mkdir(parents=True)
    bad = {"root": w.root, "above-root": w.root.parent, "profile": profile,
           "above-profile": profile.parent, "system": winnt, "inside-system": winnt / "system32",
           "program-files": files, "inside-program-files": files / "node"}[where]
    _refused(w, {**w.folders, "install": bad}, reason)


def test_an_install_folder_must_be_an_existing_absolute_plain_directory(tmp_path):
    w = world(tmp_path)
    a_file = tmp_path / "file.txt"
    a_file.write_text("x", encoding="utf-8")
    for bad in (Path("relative") / "kit", tmp_path / "absent", a_file):
        _refused(w, {**w.folders, "install": bad})


@pytest.mark.parametrize("route", [".git/t1", "conductor.v3/t1", "src/t1", "t1", "work", ".GIT"])
def test_a_work_folder_outside_the_work_tree_or_inside_the_owners_git_is_refused(tmp_path, route):
    w = world(tmp_path)
    bad = w.root / route
    bad.mkdir(parents=True, exist_ok=True)
    _refused(w, {**w.folders, "work": bad})


@pytest.mark.parametrize("route", [".git/h", "conductor.v3/h", "work/t1/h"])
def test_a_home_inside_the_owners_git_the_data_root_or_the_work_folder_is_refused(tmp_path, route):
    w = world(tmp_path)
    bad = w.root / route
    bad.mkdir(parents=True, exist_ok=True)
    _refused(w, {**w.folders, "home": bad})


def test_the_folders_value_is_checked_where_it_is_made():
    ok = AttemptFolders(work="work/t1", home=f"{HOME}/a", install=str(Path("/abs").resolve()))
    assert ok.home == f"{HOME}/a"
    for bad in ({"work": ""}, {"work": "/abs"}, {"work": "work/../x"}, {"work": "C:/x"},
                {"home": ""}, {"home": "../h"}, {"install": "relative/kit"}, {"install": ""},
                {"work": 5}, {"install": None}):
        fields = {"work": "work/t1", "home": None, "install": str(Path("/abs").resolve()), **bad}
        with pytest.raises(ValueError):
            AttemptFolders(**fields)
