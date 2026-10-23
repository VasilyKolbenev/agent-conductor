"""The runner loans a relay home: an absolute home outside the project, judged by its shape.

The loan journal (fake natives, `tests/test_process_loans.py`) takes a home that stands in
`<relay>/<key>/<name>` beside the logins folder, under the key of its own project, with the DACLs
the relay layer needs, and refuses every other home that is not beneath the project, before
anything is held, journalled or changed. The key, rights, journal and recovery are those of the
per-spawn home. The runner's own seams (`ProcessRunner._loaned`, `AttemptFolders`) take an
absolute path as it is written, as a relay home only: one that lies in the project is refused.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.adapters import process_loans
from conductor.command.adapters.process import ContainmentError, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.relay_home import relay_key, relay_root_sddl
from tests.relay_fixtures import HEX, INHERITED, LOGIN_DACL, OWNER, ReadHold, link
from tests.test_process_loans import HOME, masks, prior_acl, record_files, world

ROOT = relay_root_sddl(OWNER)
ABSOLUTE = str(Path("/abs").resolve())


def relay_world(tmp_path):
    """A loan world whose home is a relay home: DACLs as a good relay layout reads back."""
    w = world(tmp_path)
    top = tmp_path / "DecemberCommand"
    w.login = top / "logins" / "claude-code"
    w.login.mkdir(parents=True)
    w.relay = top / "relay"
    w.key = w.relay / relay_key(w.store.root_identity)
    w.relay_home = w.key / f"c-{HEX}"
    w.relay_home.mkdir(parents=True)
    w.folders = {**w.folders, "home": w.relay_home}
    prior_acl(w)
    w.state[str(w.relay)] = (ROOT, True, OWNER)
    for path in (w.key, w.relay_home):
        w.state[str(path)] = (INHERITED, False, OWNER)
    w.loans = loans_of(w, w.login)
    return w


def loans_of(w, *logins):
    return FolderLoans(w.store, w.store.native, hold_factory=ReadHold, environ=w.environ,
                       login_homes=lambda: logins)


def refused(w, reason, folders=None):
    """The loan is refused as `profile_acl_invalid` for a reason that contains `reason`, with no
    record, no ACL changed and no entry of the profile anywhere."""
    folders = w.folders if folders is None else folders
    changed = []
    real = w.store.native.acl_set
    w.store.native.acl_set = lambda *args, **options: changed.append(args)
    try:
        with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*" + reason):
            w.loans.grant(w.profile_path, w.sid, "dispatch", folders)
    finally:
        w.store.native.acl_set = real
    assert record_files(w) == [] and changed == []
    assert all(w.sid not in sddl for sddl, _, _ in w.state.values())


def test_a_relay_home_is_loaned_like_a_home_and_given_back_exactly_as_it_was(tmp_path):
    w = relay_world(tmp_path)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    row = json.loads(record.read_text(encoding="utf-8"))
    assert set(row["loans"]) == {"work", "home", "install"} and row["phase"] == "applied"
    assert row["loans"]["home"]["rights"] == "modify"
    assert row["loans"]["home"]["path"] == str(Path(os.path.realpath(w.relay_home)))
    assert row["loans"]["home"]["before"] == INHERITED
    assert sorted(masks(w.state[str(w.relay_home)][0], w.sid)) == [0x1201BF, 0x1301BF]
    assert w.state[str(w.relay)] == (ROOT, True, OWNER)
    assert w.state[str(w.key)] == (INHERITED, False, OWNER), "only the home itself is lent"
    w.loans.restore(record)
    assert w.state[str(w.relay_home)] == (INHERITED, False, OWNER)
    assert json.loads(record.read_text(encoding="utf-8"))["phase"] == "retired"


def test_a_relay_home_is_written_in_a_review_too_as_any_home_is(tmp_path):
    w = relay_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "review", w.folders)
    assert 0x1201BF in masks(w.state[str(w.relay_home)][0], w.sid)
    assert masks(w.state[str(w.folders["work"])][0], w.sid) == [0x1200A9]


def test_the_targets_name_the_relay_home_in_its_real_place(tmp_path):
    w = relay_world(tmp_path)
    assert w.loans.targets(w.folders)["home"] == Path(os.path.realpath(w.relay_home))


def test_a_relay_home_loan_a_crash_left_behind_is_returned_by_the_recovery(tmp_path):
    w = relay_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    loans_of(w, w.login).recover()
    assert w.state[str(w.relay_home)] == (INHERITED, False, OWNER)
    assert json.loads(record_files(w)[0].read_text(encoding="utf-8"))["phase"] == "retired"


def test_the_loan_takes_a_folder_in_the_project_as_the_real_place_of_a_route_the_runner_walked(
        tmp_path):
    # The loan is handed real folders. A home in the project is the place of a route the runner
    # has walked link by link (`_resolve_cwd`), judged by the rules of a project home; the runner
    # never hands it an absolute path that lies in the project (the next tests).
    w = relay_world(tmp_path)
    inner = w.root / HOME / "a"
    inner.mkdir(parents=True, exist_ok=True)
    assert w.loans.targets({**w.folders, "home": inner})["home"] == inner
    odd = w.root / "src" / "h"
    odd.mkdir(parents=True)
    refused(w, "minted folder", {**w.folders, "home": odd})


def test_a_relay_shaped_folder_in_the_project_is_judged_as_a_project_home_by_the_loan(tmp_path):
    w = relay_world(tmp_path)
    login = w.root / "DecemberCommand" / "logins" / "claude-code"
    login.mkdir(parents=True)
    home = w.root / "DecemberCommand" / "relay" / relay_key(w.store.root_identity) / f"c-{HEX}"
    home.mkdir(parents=True)
    w.loans = loans_of(w, login)
    refused(w, "minted folder", {**w.folders, "home": home})


@pytest.mark.parametrize("where", [
    "written-inside", "through-a-junction-in-the-project", "through-a-junction-outside",
    "relay-shaped-inside"])
def test_an_absolute_home_that_lies_in_the_project_is_refused_not_taken_for_a_project_home(
        tmp_path, where):
    # An absolute path means a relay home and nothing else. It skips the walk of a route, so one
    # that stands in the project, as written or in its real place, would be taken for the
    # project's own home, past the walk that refuses a link in a route.
    w = relay_world(tmp_path)
    (w.root / HOME / "a").mkdir(parents=True, exist_ok=True)
    home = w.root / HOME / "a"
    if where == "through-a-junction-in-the-project":
        link(w.root / "jl", w.root / HOME)
        home = w.root / "jl" / "a"
    elif where == "through-a-junction-outside":
        link(tmp_path / "outside-link", w.root / HOME)
        home = tmp_path / "outside-link" / "a"
    elif where == "relay-shaped-inside":
        home = w.root / "DecemberCommand" / "relay" / relay_key(w.store.root_identity) / f"c-{HEX}"
        home.mkdir(parents=True)
    runner, install = ProcessRunner(w.root), str(w.folders["install"])
    with pytest.raises(ProfileRefused, match=(
            "profile_acl_invalid: the relay home is refused: an absolute home is a relay home")):
        runner._loaned(AttemptFolders(work="work/t1", home=str(home), install=install))
    if where == "written-inside":  # the same folder is the project's home when it is a route
        assert runner._loaned(AttemptFolders(
            work="work/t1", home=f"{HOME}/a", install=install))["home"] == home


def test_the_folder_that_is_lent_is_the_one_the_walk_judged(tmp_path, monkeypatch):
    # The real place of the home is read before the walk of its written route. If a component of
    # the route led elsewhere at that instant, the loan would lend a folder the walk never saw.
    w = relay_world(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "anything"
    elsewhere.mkdir(parents=True)
    plain, spelled = process_loans._plain_directory, str(w.relay_home)

    def swapped(path):
        return Path(os.path.realpath(elsewhere)) if str(path) == spelled else plain(path)

    monkeypatch.setattr(process_loans, "_plain_directory", swapped)
    refused(w, "not the one its written route leads to")


@pytest.mark.parametrize("where, phrase", [
    ("home", "the login home has an entry for ALL APPLICATION PACKAGES"),
    ("logins", "the logins folder has an entry for ALL APPLICATION PACKAGES"),
    ("leaf", "the login home entry .credentials.json has an entry for ALL APPLICATION PACKAGES")])
@pytest.mark.parametrize("trustee", ["AC", "S-1-15-3-1", "S-1-15-2-9-8-7-6-5-4-3"])
def test_a_real_login_home_a_container_could_read_is_refused_by_the_loan_itself(
        tmp_path, where, phrase, trustee):
    # What the transport proves at its readiness the runner proves again at the grant: nothing
    # tells it which login the attempt works from, so none beside the relay folder may be open.
    w = relay_world(tmp_path)
    (w.login / ".credentials.json").write_text("placeholder", encoding="utf-8")
    target = {"home": w.login, "logins": w.login.parent, "leaf": w.login / ".credentials.json"}
    w.state[str(target[where])] = (LOGIN_DACL + f"(A;;0x1200a9;;;{trustee})", False, OWNER)
    refused(w, phrase)


def test_a_login_home_that_does_not_exist_holds_no_credential_and_does_not_block_the_loan(
        tmp_path):
    w = relay_world(tmp_path)
    w.loans = loans_of(w, w.login, w.login.parent / "grok")  # configured, never signed in to
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert json.loads(record.read_text(encoding="utf-8"))["phase"] == "applied"


def test_every_login_home_beside_the_relay_folder_is_judged_not_only_the_first(tmp_path):
    w = relay_world(tmp_path)
    second = w.login.parent / "codex"
    second.mkdir()
    (second / "auth.json").write_text("placeholder", encoding="utf-8")
    w.state[str(second / "auth.json")] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    w.loans = loans_of(w, w.login, second)
    refused(w, "the login home entry auth.json has an entry for ALL APPLICATION PACKAGES")


def test_a_relay_home_in_the_key_folder_of_another_project_is_refused(tmp_path):
    w = relay_world(tmp_path)
    foreign = w.relay / relay_key((9, 9)) / f"c-{HEX}"
    foreign.mkdir(parents=True)
    refused(w, "another project", {**w.folders, "home": foreign})


@pytest.mark.parametrize("name", ["c-xyz", "c-" + HEX[:15], "z-" + HEX, HEX])
def test_a_relay_home_with_another_name_is_refused(tmp_path, name):
    w = relay_world(tmp_path)
    other = w.key / name
    other.mkdir()
    refused(w, "named c-", {**w.folders, "home": other})


def test_a_relay_home_written_with_dots_is_refused(tmp_path):
    w = relay_world(tmp_path)
    dotted = Path(str(w.key) + os.sep + ".." + os.sep + w.key.name + os.sep + w.relay_home.name)
    refused(w, "normal path", {**w.folders, "home": dotted})


@pytest.mark.parametrize("where", ["relay", "key", "home"])
def test_a_link_in_the_route_of_the_relay_home_is_refused_though_the_home_is_a_plain_folder(
        tmp_path, where):
    w = relay_world(tmp_path)
    target = {"relay": w.relay, "key": w.key, "home": w.relay_home}[where]
    real = tmp_path / "elsewhere"
    shutil.copytree(target, real)
    shutil.rmtree(target)
    link(target, real)
    # the home itself is refused as a link before its shape is judged; a link above it is only
    # seen by the walk of the spelled route, because the real path of the home has none left
    refused(w, "not a plain directory" if where == "home"
            else "relay home is refused: .*(junction|symbolic link)")


def test_a_home_outside_the_project_that_is_no_relay_home_at_all_is_refused(tmp_path):
    w = relay_world(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "h"
    elsewhere.mkdir(parents=True)
    refused(w, "relay home is refused", {**w.folders, "home": elsewhere})


def test_a_relay_home_of_no_login_home_the_project_holds_is_refused(tmp_path):
    w = relay_world(tmp_path)
    w.loans = loans_of(w)
    refused(w, "relay folder of a login home")
    w.loans = loans_of(w, tmp_path / "logins" / "claude-code")
    refused(w, "relay folder of a login home")


def test_a_relay_home_that_holds_the_install_folder_or_is_a_login_home_is_refused(tmp_path):
    w = relay_world(tmp_path)
    inner = w.relay_home / "harnesses" / "kit" / "1.0"
    inner.mkdir(parents=True)
    refused(w, "overlaps the install", {**w.folders, "install": inner})
    w.loans = loans_of(w, w.login, w.relay_home)
    refused(w, "overlaps the login")


@pytest.mark.parametrize("change", ["unprotected", "extra-entry", "no-owner", "container-entry"])
def test_a_relay_folder_without_exactly_its_protected_dacl_is_refused(tmp_path, change):
    w = relay_world(tmp_path)
    w.state[str(w.relay)] = {
        "unprotected": (ROOT, False, OWNER),
        "extra-entry": (ROOT + "(A;OICI;0x1200a9;;;BU)", True, OWNER),
        "no-owner": (f"O:{OWNER}D:P(A;OICI;FA;;;SY)", True, OWNER),
        "container-entry": (ROOT + "(A;OICI;0x1200a9;;;AC)", True, OWNER)}[change]
    refused(w, "protected with SYSTEM and its owner")


@pytest.mark.parametrize("entry", [
    "(A;OICIID;0x1200a9;;;AC)", "(A;OICIID;0x1200a9;;;S-1-15-3-1)",
    "(A;OICIID;0x1200a9;;;S-1-15-2-9-9-9-9-9-9-9)", "(OA;OICIID;0x1;;;S-1-15-3-1)",
    "(A;OICI;FA;;;S-1-5-21-9)", "(XA;OICIID;FA;;;SY;(Member_of{SID(BA)}))"])
@pytest.mark.parametrize("which", ["key", "home"])
def test_a_key_folder_or_relay_home_with_an_entry_of_its_own_or_for_a_container_is_refused(
        tmp_path, entry, which):
    w = relay_world(tmp_path)
    path = {"key": w.key, "home": w.relay_home}[which]
    w.state[str(path)] = (f"O:{OWNER}D:AI(A;OICIID;FA;;;SY)" + entry, False, OWNER)
    refused(w, "(key folder|relay home) has (an entry|a DACL)")


def test_a_refused_relay_home_is_refused_before_a_profile_exists(tmp_path, monkeypatch):
    w = relay_world(tmp_path)
    w.state[str(w.relay)] = (ROOT, False, OWNER)
    monkeypatch.setattr(process_loans, "FolderLoans", lambda profiles, native: w.loans)
    profiles = sorted(w.store.directory.glob("profile-*.json"))
    with pytest.raises(ProfileRefused, match="protected with SYSTEM"):
        with w.store.container(mode="dispatch", active_tokens=lambda: (), folders=w.folders):
            pytest.fail("the block must not be entered")
    assert sorted(w.store.directory.glob("profile-*.json")) == profiles


def test_the_runner_takes_an_absolute_home_as_written_and_still_walks_a_route(tmp_path):
    w = relay_world(tmp_path)
    runner = ProcessRunner(w.root)
    install = str(w.folders["install"])
    found = runner._loaned(AttemptFolders(work="work/t1", home=str(w.relay_home), install=install))
    assert found == {"work": runner._root / "work" / "t1", "install": Path(install),
                     "home": w.relay_home}
    assert runner._loaned(SimpleNamespace(work="work/t1", home=str(tmp_path / "anywhere"),
                                          install=install))["home"] == tmp_path / "anywhere"
    route = AttemptFolders(work="work/t1", home=f"{HOME}/a", install=install)
    assert runner._loaned(route)["home"] == runner._root / HOME / "a"
    with pytest.raises(ContainmentError):
        runner._loaned(SimpleNamespace(work="work/t1", home="../h", install=install))
    assert "home" not in runner._loaned(AttemptFolders(work="work/t1", home=None,
                                                       install=install))


def test_a_folders_value_takes_an_absolute_home_and_a_route_and_nothing_else():
    assert AttemptFolders(work="work/t1", home=ABSOLUTE, install=ABSOLUTE).home == ABSOLUTE
    assert AttemptFolders(work="work/t1", home=f"{HOME}/a", install=ABSOLUTE).home == f"{HOME}/a"
    for bad in ("", "../h", "a/../h", ABSOLUTE + "/../h", ABSOLUTE + "/./h", ABSOLUTE + "\x00",
                5, b"x"):
        with pytest.raises(ValueError):
            AttemptFolders(work="work/t1", home=bad, install=ABSOLUTE)
    with pytest.raises(ValueError):
        AttemptFolders(work="work/t1", home=ABSOLUTE, install=ABSOLUTE, login=ABSOLUTE)
