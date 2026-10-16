"""A login home that holds Grok's hook objects is loaned only while they cannot inherit its rights.

Grok keeps a directory `hooks` and a file `hooks-paths` in its home and loads what they name, so an
agent that can write into or replace them can run its own code the next time Grok starts. The login
loan hands the rights of a refresh down to nested objects by inheritance. It is therefore made only
when each of those two objects that exists is a plain object whose inheritance is cut (nothing is
handed down to it), and it is checked again after the rights are handed down. An absent object is
the vendor's own rule (its checks before and after each spawn), and the loan does not decide it.
The loan is a generic one: nothing here turns Grok on.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conductor.command.adapters.process_profile import ProfileRefused
from tests.test_process_loans import OWNER, PRIOR, record_files
from tests.test_process_login_grant import login_world


def make(w, name, kind, *, protected):
    """A hook object in the leased home, with the DACL the fake natives report for it."""
    path = w.leased / name
    if kind == "dir":
        path.mkdir()
    else:
        path.write_bytes(b"")
    w.state[str(path)] = (PRIOR, protected, OWNER)
    return path


def folders_untouched(w) -> bool:
    return all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


@pytest.mark.parametrize("name, kind", [
    ("hooks", "dir"), ("hooks-paths", "file"), ("Hooks", "dir"), ("HOOKS-PATHS", "file")])
def test_a_hook_object_that_inherits_is_refused_before_any_change(tmp_path, name, kind):
    w = login_world(tmp_path)
    make(w, name, kind, protected=False)
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*inherits its rights"):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert record_files(w) == [] and folders_untouched(w)


def test_hook_objects_with_their_inheritance_cut_are_left_exactly_as_they_were(tmp_path):
    w = login_world(tmp_path)
    hooks = make(w, "hooks", "dir", protected=True)
    paths = make(w, "hooks-paths", "file", protected=True)
    touched = []
    real = w.store.native.acl_set
    w.store.native.acl_set = lambda hold, sddl, *, protected: (
        touched.append(Path(hold.path)), real(hold, sddl, protected=protected))
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.sid in w.state[str(w.leased)][0]
    assert hooks not in touched and paths not in touched
    for path in (hooks, paths):
        assert w.state[str(path)] == (PRIOR, True, OWNER)
    w.loans.restore(record)
    assert folders_untouched(w)


def test_a_hook_object_that_is_absent_is_not_the_loans_concern(tmp_path):
    w = login_world(tmp_path)
    assert not (w.leased / "hooks").exists()
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.sid in w.state[str(w.leased)][0]


def test_a_hook_name_deeper_in_the_home_is_not_one_of_the_two_the_vendor_loads(tmp_path):
    w = login_world(tmp_path)
    (w.leased / "plugins").mkdir()
    (w.leased / "plugins" / "hooks").mkdir()
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.sid in w.state[str(w.leased)][0]


def test_a_hook_object_that_stops_being_protected_while_the_rights_are_handed_down_is_found(
        tmp_path):
    w = login_world(tmp_path)
    hooks = make(w, "hooks", "dir", protected=True)
    real = w.store.native.acl_set

    def hands_down(hold, sddl, *, protected):
        real(hold, sddl, protected=protected)
        if Path(hold.path) == w.leased:  # what an OS that handed the rights on would leave
            w.state[str(hooks)] = (PRIOR, False, OWNER)

    w.store.native.acl_set = hands_down
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*inherits its rights"):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    w.store.native.acl_set = real
    w.loans.restore()
    assert folders_untouched(w), "the rights are taken back although the grant was refused"


@pytest.mark.skipif(os.name != "nt", reason="a junction is how Windows makes a folder link")
def test_a_hook_object_that_is_a_junction_is_refused(tmp_path):
    w = login_world(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(w.leased / "hooks"), str(target)],
                          capture_output=True)
    assert made.returncode == 0, made.stderr
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*not a plain object"):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert record_files(w) == [] and folders_untouched(w)
