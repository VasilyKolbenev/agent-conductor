"""The DACL facts a relay home rests on, over fake natives: what is refused and what is made.

A container reaches a folder through an entry for its own profile (the loan adds that) or through
one for ALL APPLICATION PACKAGES, a package or a capability. The relay folder must carry neither,
exactly SYSTEM and its owner, protected; the key folder and the relay home only what they inherit;
the operator's real login home and its parent no such entry at all. The OS part is witnessed
natively (`test_relay_home_native.py`); here the text is judged.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.relay_home import (
    LOGIN_ENTRIES, ace_refusal, ensure_relay_root, login_side_refusal, logins_refusal,
    relay_acl_refusal, relay_root_refusal, relay_root_sddl, relay_side_refusal)
from tests.relay_fixtures import (
    INHERITED, LOGIN_DACL, OWNER, ReadHold, fake_native, layout, link, sealed)

HEAD = f"O:{OWNER}D:AI"
ROOT = relay_root_sddl(OWNER)


def _with(*entries: str) -> str:
    return HEAD + "".join(entries)


def test_the_dacl_of_the_relay_folder_is_protected_system_and_the_owner_handed_down():
    assert ROOT == (f"O:{OWNER}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{OWNER})")


@pytest.mark.parametrize("sddl", [
    INHERITED, LOGIN_DACL, ROOT, _with("(D;;FA;;;AC)", "(A;ID;0x1200a9;;;BU)"),
    _with("(D;;FA;;;S-1-15-3-1)", "(A;;FA;;;S-1-5-21-1)"), _with("(A;;FA;;;S-1-5-21-1)"),
    _with("(A;;FA;;;S-1-15-1-1)"), _with("(A;;FA;;;S-1-5-21-15-2-1)"), _with()])
def test_a_dacl_with_no_allow_entry_for_a_container_is_not_refused(sddl):
    assert ace_refusal(sddl) is None


@pytest.mark.parametrize("trustee", [
    "AC", "ac", "S-1-15-2-1", "S-1-15-2-2", "S-1-15-2-1-2-3-4-5-6-7", "s-1-15-2-1",
    "S-1-15-3-1", "S-1-15-3-1024-1-2-3-4-5-6-7-8", "S-1-15-3-2"])
def test_an_allow_entry_for_all_application_packages_a_package_or_a_capability_is_refused(trustee):
    for kind in ("A", "OA"):
        reason = ace_refusal(_with("(A;OICIID;FA;;;SY)", f"({kind};ID;0x1200a9;;;{trustee})"))
        assert reason is not None and "APPLICATION PACKAGES" in reason, (kind, trustee)


@pytest.mark.parametrize("sddl", [
    _with("(XA;;FA;;;SY;(Member_of{SID(BA)}))"), _with("(XA;;FA;;;S-1-5-21-1;@User.x)"),
    _with("(ZA;;FA;;;S-1-5-21-1)"), _with("(AU;SA;FA;;;WD)"), _with("(A;;FA;;SY)"),
    _with("(A;;FA;;;SY;;)"), "", "D:(A;;FA;;;SY", f"O:{OWNER}",
    f"O:{OWNER}D:(A;;FA;;;SY)S:(AU;SA;FA;;;WD)", None, 5, b"D:"])
def test_a_conditional_or_unrecognised_entry_or_a_dacl_that_does_not_parse_is_refused(sddl):
    reason = ace_refusal(sddl)
    assert reason is not None and ("conditional" in reason or "does not understand" in reason)


def _state(tmp_path):
    found = layout(tmp_path)
    state: dict = {}
    sealed(found, state)
    return found, state, fake_native(state)


def _refusal(function, native, *arguments, **options):
    return function(native, *arguments, hold_factory=ReadHold, **options)


def test_the_relay_folder_with_exactly_its_dacl_is_not_refused(tmp_path):
    found, _, native = _state(tmp_path)
    assert _refusal(relay_root_refusal, native, found.relay) is None


@pytest.mark.parametrize("change", [
    "unprotected", "an-extra-entry", "no-owner-entry", "a-container-entry",
    "a-stranger-for-the-owner", "inherited-flags", "a-deny-first"])
def test_a_relay_folder_that_is_not_exactly_protected_system_and_owner_is_refused(
        tmp_path, change):
    found, state, native = _state(tmp_path)
    exact = (ROOT, True, OWNER)
    state[str(found.relay)] = {
        "unprotected": (ROOT, False, OWNER),
        "an-extra-entry": (ROOT + "(A;OICI;0x1200a9;;;BU)", True, OWNER),
        "no-owner-entry": (f"O:{OWNER}D:P(A;OICI;FA;;;SY)", True, OWNER),
        "a-container-entry": (ROOT + "(A;OICI;0x1200a9;;;AC)", True, OWNER),
        "a-stranger-for-the-owner": (f"O:{OWNER}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;S-1-5-21-9)",
                                     True, OWNER),
        "inherited-flags": (f"O:{OWNER}D:P(A;OICIID;FA;;;SY)(A;OICIID;FA;;;{OWNER})", True, OWNER),
        "a-deny-first": (f"O:{OWNER}D:P(D;OICI;FA;;;WD)(A;OICI;FA;;;SY)(A;OICI;FA;;;{OWNER})",
                         True, OWNER),
    }[change]
    assert state[str(found.relay)] != exact
    reason = _refusal(relay_root_refusal, native, found.relay)
    assert "protected with SYSTEM and its owner" in reason


def test_a_relay_folder_that_cannot_be_read_is_refused(tmp_path):
    found, _, native = _state(tmp_path)
    assert "cannot be read" in _refusal(relay_root_refusal, native, found.relay / "absent")


def test_the_key_folder_and_the_relay_home_may_hold_only_what_they_inherit(tmp_path):
    found, state, native = _state(tmp_path)
    assert _refusal(relay_side_refusal, native, found.home) is None
    for path, what in ((found.key, "key folder"), (found.home, "relay home")):
        state[str(path)] = (_with("(A;;FA;;;S-1-5-21-9)", "(A;OICIID;FA;;;SY)"), False, OWNER)
        assert f"the {what} has an entry of its own" in _refusal(relay_side_refusal, native,
                                                                  found.home)
        state[str(path)] = (INHERITED, False, OWNER)


@pytest.mark.parametrize("trustee", ["AC", "S-1-15-2-1", "S-1-15-3-1", "S-1-15-3-2"])
def test_an_inherited_entry_for_a_container_on_the_key_folder_or_the_home_is_refused(
        tmp_path, trustee):
    found, state, native = _state(tmp_path)
    for path, what in ((found.key, "key folder"), (found.home, "relay home")):
        state[str(path)] = (_with("(A;OICIID;FA;;;SY)", f"(A;OICIID;0x1200a9;;;{trustee})"),
                            False, OWNER)
        assert f"the {what} has an entry for ALL APPLICATION PACKAGES" in _refusal(
            relay_side_refusal, native, found.home)
        state[str(path)] = (INHERITED, False, OWNER)


def test_the_side_of_the_relay_is_judged_root_first_then_the_key_folder_then_the_home(tmp_path):
    found, state, native = _state(tmp_path)
    for path in (found.relay, found.key, found.home):
        state[str(path)] = (_with("(A;;FA;;;AC)"), False, OWNER)
    named = []
    for path, good in ((found.relay, (ROOT, True, OWNER)), (found.key, (INHERITED, False, OWNER)),
                       (found.home, (INHERITED, False, OWNER))):
        reason = _refusal(relay_side_refusal, native, found.home)
        named.append(" ".join(reason.split(" ")[1:3]))
        state[str(path)] = good
    assert named == ["relay folder", "key folder", "relay home"]
    assert _refusal(relay_side_refusal, native, found.home) is None


@pytest.mark.parametrize("trustee", ["AC", "S-1-15-2-1-2-3-4-5-6-7", "S-1-15-3-1"])
def test_the_real_login_home_or_its_parent_with_an_entry_for_a_container_is_refused(
        tmp_path, trustee):
    found, state, native = _state(tmp_path)
    assert _refusal(login_side_refusal, native, found.login) is None
    for path, what in ((found.login, "login home"), (found.login.parent, "logins folder")):
        state[str(path)] = (LOGIN_DACL + f"(A;;0x1200a9;;;{trustee})", False, OWNER)
        assert f"the {what} has an entry for ALL APPLICATION PACKAGES" in _refusal(
            login_side_refusal, native, found.login)
        state[str(path)] = (LOGIN_DACL, False, OWNER)


def test_an_entry_of_the_operator_on_the_login_home_is_not_a_reason_to_refuse(tmp_path):
    found, state, native = _state(tmp_path)
    state[str(found.login)] = (LOGIN_DACL + "(A;;FA;;;S-1-5-21-77)(D;;FA;;;AC)", True, OWNER)
    assert _refusal(login_side_refusal, native, found.login) is None


def _leaf(found, name: str) -> Path:
    path = found.login / name
    if name == "sub":
        path.mkdir()
    else:
        path.write_text("placeholder", encoding="utf-8")
    return path


@pytest.mark.parametrize("name", [".credentials.json", ".claude.json", "auth.json", "sub"])
@pytest.mark.parametrize("trustee", ["AC", "S-1-15-2-1-2-3-4-5-6-7", "S-1-15-3-1"])
def test_an_entry_at_the_top_of_the_real_login_home_with_its_own_entry_for_a_container_is_refused(
        tmp_path, name, trustee):
    # A container reads a file by its full path though the folders above it are closed to it, so
    # the leaf's own DACL counts (measured natively: `test_relay_home_native.py`).
    found, state, native = _state(tmp_path)
    leaf = _leaf(found, name)
    assert _refusal(login_side_refusal, native, found.login) is None
    state[str(leaf)] = (LOGIN_DACL + f"(A;;0x1200a9;;;{trustee})", False, OWNER)
    expected = (f"the login home entry {name} has an entry for ALL APPLICATION PACKAGES, "
                "a package or a capability")
    assert _refusal(login_side_refusal, native, found.login) == expected
    assert _refusal(relay_acl_refusal, native, found.login) == expected
    assert _refusal(relay_acl_refusal, native, found.login, found.home) == expected


def test_an_entry_of_the_operator_or_a_deny_on_a_login_home_entry_is_not_a_reason_to_refuse(
        tmp_path):
    found, state, native = _state(tmp_path)
    leaf = _leaf(found, "auth.json")
    state[str(leaf)] = (LOGIN_DACL + "(A;;FA;;;S-1-5-21-77)(D;;FA;;;AC)", True, OWNER)
    assert _refusal(login_side_refusal, native, found.login) is None


def test_the_entries_of_the_login_home_are_read_in_name_order_after_the_home_and_its_parent(
        tmp_path):
    found, state, native = _state(tmp_path)
    for name in ("b.json", "a.json"):
        state[str(_leaf(found, name))] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    first = _refusal(login_side_refusal, native, found.login)
    assert first.startswith("the login home entry a.json")
    state[str(found.login.parent)] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    assert _refusal(login_side_refusal, native, found.login).startswith("the logins folder")
    state[str(found.login)] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    assert _refusal(login_side_refusal, native, found.login).startswith("the login home has")


def test_a_login_home_entry_that_is_a_link_or_has_two_names_cannot_be_read_and_is_refused(
        tmp_path):
    found, _, native = _state(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link(found.login / "lnk", elsewhere)
    assert _refusal(login_side_refusal, native, found.login) == (
        "the login home entry lnk cannot be read")
    if os.name == "nt":
        (found.login / "lnk").rmdir()  # a junction is a folder to remove
    else:
        (found.login / "lnk").unlink()
    first = _leaf(found, "first.json")
    os.link(first, found.login / "second.json")
    assert _refusal(login_side_refusal, native, found.login) == (
        "the login home entry first.json cannot be read")


def test_a_login_home_with_more_entries_than_are_read_is_refused(tmp_path):
    found, _, native = _state(tmp_path)
    for number in range(LOGIN_ENTRIES):
        (found.login / f"f{number}").write_text("x", encoding="utf-8")
    assert _refusal(login_side_refusal, native, found.login) is None
    (found.login / "one-more").write_text("x", encoding="utf-8")
    assert f"more than {LOGIN_ENTRIES} entries" in _refusal(login_side_refusal, native, found.login)


def test_the_logins_beside_the_relay_folder_are_each_judged_and_an_absent_one_holds_nothing(
        tmp_path):
    found, state, native = _state(tmp_path)
    second = found.top / "logins" / "codex"
    other = layout(tmp_path / "second")
    state[str(other.login)] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    homes = (found.login, second, other.login)  # `second` does not exist, `other` is elsewhere
    assert _refusal(logins_refusal, native, homes, found.home) is None
    second.mkdir()
    state[str(second)] = (LOGIN_DACL + "(A;;0x1;;;S-1-15-3-1)", False, OWNER)
    assert _refusal(logins_refusal, native, homes, found.home).startswith("the login home has")
    state[str(second)] = (LOGIN_DACL, False, OWNER)
    (second / "auth.json").write_text("placeholder", encoding="utf-8")
    state[str(second / "auth.json")] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    assert _refusal(logins_refusal, native, homes, found.home) == (
        "the login home entry auth.json has an entry for ALL APPLICATION PACKAGES, "
        "a package or a capability")


def test_the_readiness_asks_the_relay_folder_the_relay_home_and_the_real_login_home(tmp_path):
    found, state, native = _state(tmp_path)
    assert _refusal(relay_acl_refusal, native, found.login) is None
    assert _refusal(relay_acl_refusal, native, found.login, found.home) is None
    state[str(found.login)] = (LOGIN_DACL + "(A;;0x1;;;AC)", False, OWNER)
    assert "login home" in _refusal(relay_acl_refusal, native, found.login)
    assert "login home" in _refusal(relay_acl_refusal, native, found.login, found.home)
    state[str(found.login)] = (LOGIN_DACL, False, OWNER)
    state[str(found.relay)] = (ROOT, False, OWNER)
    assert "relay folder" in _refusal(relay_acl_refusal, native, found.login)
    assert "relay folder" in _refusal(relay_acl_refusal, native, found.login, found.home)


def test_the_readiness_refuses_a_relay_home_of_another_relay_folder_or_another_login_form(tmp_path):
    found, state, native = _state(tmp_path)
    elsewhere = layout(tmp_path / "second")
    assert "not in the relay folder" in _refusal(relay_acl_refusal, native, found.login,
                                                 elsewhere.home)
    odd = tmp_path / "logins" / "x"
    assert "does not stand in" in _refusal(relay_acl_refusal, native, odd)


def _bare(tmp_path):
    """A login home in its DecemberCommand folder, and no relay folder yet."""
    found = layout(tmp_path)
    found.home.rmdir()
    found.key.rmdir()
    found.relay.rmdir()
    return found


def _staged(found):
    """The staging folders beside the relay folder."""
    return sorted(path.name for path in found.top.glob(".relay.*"))


def test_the_relay_folder_is_made_beside_itself_given_its_dacl_and_renamed_under_the_mutex(
        tmp_path):
    found, events = _bare(tmp_path), []
    state: dict = {}
    native = fake_native(state, events)
    assert ensure_relay_root(found.login, native=native, hold_factory=ReadHold) == found.relay
    assert found.relay.is_dir() and _staged(found) == []
    [enter, setting, leave] = events
    assert enter == ("enter", str(found.top)) and leave == ("exit", str(found.top))
    assert setting[0] == "set" and setting[2:] == (ROOT, True)
    assert re.fullmatch(r"\.relay\.[0-9a-f]{16}\.tmp", Path(setting[1]).name)
    assert Path(setting[1]).parent == found.top, "staged beside `relay`, on the same volume"
    assert native.acl_snapshot(ReadHold(found.relay, directory=True)) == (ROOT, True, OWNER), (
        "the DACL went with the folder to its new name")


def test_the_relay_folder_never_stands_without_its_dacl(tmp_path):
    # A process that is killed after it made the folder and before it gave it its DACL left
    # `relay` with the DACL it inherited, and every later call refused it for good. The DACL is
    # now set on a staging folder, so at the moment it is set `relay` does not exist yet.
    found = _bare(tmp_path)
    seen = []
    native = fake_native({})
    real = native.acl_set

    def watching(hold, sddl, *, protected):
        seen.append((found.relay.exists(), Path(hold.path).name))
        real(hold, sddl, protected=protected)

    native.acl_set = watching
    ensure_relay_root(found.login, native=native, hold_factory=ReadHold)
    assert [exists for exists, _ in seen] == [False] and seen[0][1] != found.relay.name


@pytest.mark.parametrize("stopped", [OSError("native refusal"), KeyboardInterrupt()])
def test_a_process_stopped_before_the_dacl_is_set_leaves_no_relay_folder_and_no_stage(
        tmp_path, stopped):
    found = _bare(tmp_path)
    native = fake_native({})

    def stopping(hold, sddl, *, protected):
        raise stopped

    native.acl_set = stopping
    with pytest.raises((ProfileRefused, KeyboardInterrupt)):
        ensure_relay_root(found.login, native=native, hold_factory=ReadHold)
    assert not found.relay.exists() and _staged(found) == []
    ensure_relay_root(found.login, native=fake_native({}), hold_factory=ReadHold)
    assert found.relay.is_dir(), "the next call makes it"


def test_a_staging_folder_a_dead_process_left_is_swept_when_it_is_empty_and_only_then(tmp_path):
    found = _bare(tmp_path)
    empty, full = ".relay." + "0" * 16 + ".tmp", ".relay." + "1" * 16 + ".tmp"
    odd = (".relay.tmp", ".relay." + "2" * 15 + ".tmp", "relay." + "3" * 16 + ".tmp",
           ".relay." + "4" * 16 + ".tmp.old")
    for name in (empty, full, *odd):
        (found.top / name).mkdir()
    (found.top / full / "kept.txt").write_text("not ours", encoding="utf-8")
    ensure_relay_root(found.login, native=fake_native({}), hold_factory=ReadHold)
    assert _staged(found) == sorted([full, *(name for name in odd if name.startswith(".relay."))])
    assert (found.top / ("relay." + "3" * 16 + ".tmp")).is_dir(), "not a staging name: untouched"
    assert (found.top / full / "kept.txt").read_text(encoding="utf-8") == "not ours"


def test_a_relay_folder_that_already_has_its_dacl_is_only_checked(tmp_path):
    found, events = _bare(tmp_path), []
    state = {str(found.relay): (ROOT, True, OWNER)}
    found.relay.mkdir()
    native = fake_native(state, events)
    for _ in range(2):
        assert ensure_relay_root(found.login, native=native, hold_factory=ReadHold) == found.relay
    assert [e for e in events if e[0] == "set"] == []


@pytest.mark.parametrize("dacl", [
    (ROOT, False, OWNER), (ROOT + "(A;OICI;0x1200a9;;;BU)", True, OWNER),
    (ROOT + "(A;OICI;0x1200a9;;;AC)", True, OWNER), (INHERITED, False, OWNER)])
def test_an_existing_relay_folder_with_another_dacl_is_refused_and_left_as_it_is(
        tmp_path, dacl):
    found, events = _bare(tmp_path), []
    found.relay.mkdir()
    state = {str(found.relay): dacl}
    native = fake_native(state, events)
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*protected with SYSTEM") as no:
        ensure_relay_root(found.login, native=native, hold_factory=ReadHold)
    assert "DecemberCommand/relay" in str(no.value) and "remove it when no attempt runs" in str(
        no.value), "the refusal names the folder and what the person does"
    assert [e for e in events if e[0] == "set"] == []
    assert state[str(found.relay)] == dacl and found.relay.is_dir() and _staged(found) == []


def test_a_relay_folder_that_is_a_file_is_refused_and_left_as_it_is(tmp_path):
    found = _bare(tmp_path)
    found.relay.write_text("not a folder", encoding="utf-8")
    with pytest.raises(ProfileRefused, match="cannot be read; remove it"):
        ensure_relay_root(found.login, native=fake_native({}), hold_factory=ReadHold)
    assert found.relay.read_text(encoding="utf-8") == "not a folder" and _staged(found) == []


def test_a_relay_folder_made_here_whose_dacl_cannot_be_set_is_removed_again(tmp_path):
    found = _bare(tmp_path)
    native = fake_native({})

    def failing(hold, sddl, *, protected):
        raise OSError("native refusal")

    native.acl_set = failing
    with pytest.raises(ProfileRefused, match="cannot be made"):
        ensure_relay_root(found.login, native=native, hold_factory=ReadHold)
    assert not found.relay.exists() and _staged(found) == []


def test_a_relay_folder_whose_dacl_reads_back_different_is_never_published(tmp_path):
    found, state = _bare(tmp_path), {}
    native = fake_native(state)

    def drifting(hold, sddl, *, protected):
        state[str(hold.path)] = (sddl + "(A;OICI;0x1200a9;;;AC)", protected, OWNER)

    native.acl_set = drifting
    with pytest.raises(ProfileRefused, match="protected with SYSTEM"):
        ensure_relay_root(found.login, native=native, hold_factory=ReadHold)
    assert not found.relay.exists() and _staged(found) == []


def test_a_relay_folder_that_drifts_after_the_rename_is_taken_away_again_if_still_empty(
        tmp_path):
    found, state = _bare(tmp_path), {}
    native = fake_native(state)
    real = native.acl_snapshot

    def drifting_after(hold):
        found_acl = real(hold)
        if Path(hold.path) == found.relay:
            return (found_acl[0] + "(A;OICI;0x1200a9;;;AC)", True, OWNER)
        return found_acl

    native.acl_snapshot = drifting_after
    with pytest.raises(ProfileRefused, match="protected with SYSTEM"):
        ensure_relay_root(found.login, native=native, hold_factory=ReadHold)
    assert not found.relay.exists() and _staged(found) == []


def test_a_login_home_of_another_form_or_without_a_decembercommand_folder_is_refused(tmp_path):
    native = fake_native({})
    with pytest.raises(ProfileRefused, match="does not stand in"):
        ensure_relay_root(tmp_path / "logins" / "x", native=native, hold_factory=ReadHold)
    missing = tmp_path / "gone" / "DecemberCommand" / "logins" / "x"
    with pytest.raises(ProfileRefused, match="cannot be made"):
        ensure_relay_root(missing, native=native, hold_factory=ReadHold)
    assert not (tmp_path / "gone").exists()
