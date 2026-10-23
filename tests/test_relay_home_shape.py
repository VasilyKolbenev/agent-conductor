"""The shape of a relay home: where it may stand, how it is named and what it may not touch.

`relay_home_shape` is the one judgement the runner's loan, the transport's readiness and the test
double of the boundary all use, so each rule is pinned here once and the other layers are pinned
only to ask it (`test_relay_home_loans.py`, `test_relay_home_boundary.py`).
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from conductor.command.adapters.relay_home import relay_key, relay_root_for
from tests.relay_fixtures import HEX, layout, link, shape


def test_the_relay_folder_of_a_login_home_is_the_sibling_of_its_logins_folder(tmp_path):
    top = tmp_path / "DecemberCommand"
    assert relay_root_for(top / "logins" / "claude-code") == top / "relay"
    assert relay_root_for(str(top / "logins" / "x")) == top / "relay"


def test_the_names_of_the_login_home_are_compared_without_case_and_kept_as_written(tmp_path):
    top = tmp_path / "DECEMBERCOMMAND"
    assert relay_root_for(top / "LOGINS" / "x") == top / "relay"


@pytest.mark.parametrize("form", [
    "relative", "decembercommand-logins", "no-parent", "wrong-top", "wrong-logins", "too-deep",
    "the-logins-folder", "dots"])
def test_a_login_home_of_any_other_form_has_no_relay_folder(tmp_path, form):
    top = tmp_path / "DecemberCommand"
    other = {
        "relative": Path("DecemberCommand") / "logins" / "x",
        "decembercommand-logins": tmp_path / "DecemberCommand-logins" / "x",
        "no-parent": tmp_path / "x",
        "wrong-top": tmp_path / "Other" / "logins" / "x",
        "wrong-logins": top / "login" / "x",
        "too-deep": top / "logins" / "x" / "y",
        "the-logins-folder": top / "logins",
        "dots": Path(str(top / "logins") + os.sep + ".." + os.sep + "logins" + os.sep + "x"),
    }[form]
    assert relay_root_for(other) is None


@pytest.mark.parametrize("value", [None, 5, b"x", "", "\x00"])
def test_a_value_that_is_not_a_path_has_no_relay_folder(value):
    assert relay_root_for(value) is None


def test_the_key_is_16_hex_of_the_sha256_of_volume_and_file_id():
    expected = hashlib.sha256(b"3:5").hexdigest()[:16]
    assert relay_key((3, 5)) == relay_key([3, 5]) == expected
    assert len(expected) == 16 and set(expected) <= set("0123456789abcdef")
    assert relay_key((3, 6)) != expected and relay_key((5, 3)) != expected


@pytest.mark.parametrize("bad", [(1,), (1, 2, 3), ("1", 2), (-1, 2), (True, 2), None, 7])
def test_a_project_identity_that_is_not_two_counts_has_no_key(bad):
    with pytest.raises(ValueError):
        relay_key(bad)


@pytest.mark.skipif(os.name != "nt", reason="the mutex name is the Windows helper's")
def test_the_key_is_serialised_like_the_name_of_the_acl_mutex_of_a_folder():
    from conductor.command.adapters import _winlaunch
    assert _winlaunch.acl_mutex_name((3, 5)).endswith(relay_key((3, 5)) + hashlib.sha256(
        b"3:5").hexdigest()[16:32])


def test_the_relay_home_of_the_project_is_accepted(tmp_path):
    found = layout(tmp_path)
    assert shape(found) is None
    assert shape(found, path=str(found.home)) is None
    assert shape(layout(tmp_path / "second", kind="x")) is None


def test_the_login_homes_may_be_a_generator_and_one_of_them_is_enough(tmp_path):
    found = layout(tmp_path)
    other = tmp_path / "elsewhere" / "DecemberCommand" / "logins" / "codex"
    other.mkdir(parents=True)
    assert shape(found, auth_homes=iter((other, found.login))) is None


@pytest.mark.skipif(os.name != "nt", reason="the file system folds case on Windows")
def test_the_names_of_the_relay_folder_are_compared_without_case(tmp_path):
    found = layout(tmp_path)
    spelled = found.top.parent / "DECEMBERCOMMAND" / "RELAY" / found.key.name / found.home.name
    assert shape(found, path=spelled) is None


def test_a_relay_home_in_the_key_folder_of_another_project_is_refused(tmp_path):
    found = layout(tmp_path)
    foreign = found.relay / relay_key((found.ident[0], found.ident[1] + 1)) / f"c-{HEX}"
    foreign.mkdir(parents=True)
    assert "another project" in shape(found, path=foreign)
    assert "another project" in shape(found, root_identity=(found.ident[0], found.ident[1] + 1))


def test_the_key_is_compared_exactly_and_not_without_case(tmp_path):
    # The product writes the key in lower case, as it names a home; a folder that folds case would
    # make KEY and key one folder, and one that does not (a case sensitive folder) two.
    found = layout(tmp_path)
    ident = next((1, n) for n in range(1, 64) if relay_key((1, n)) != relay_key((1, n)).upper())
    wanted = relay_key(ident)  # a key with a letter in it, so its capitals are another spelling
    assert wanted == wanted.lower() != wanted.upper()
    for spelled, mistaken in ((wanted.upper(), True), (wanted, False)):
        reason = shape(found, root_identity=ident, path=found.relay / spelled / found.home.name)
        assert ("another project" in reason) is mistaken, (spelled, reason)


def test_a_relay_home_not_in_a_key_folder_at_all_is_refused(tmp_path):
    found = layout(tmp_path)
    bare = found.relay / f"c-{HEX}"
    bare.mkdir()
    assert "another project" in shape(found, path=bare)


@pytest.mark.parametrize("name", [
    "c-" + HEX[:15], "x-" + "0" * 17, "y-" + HEX, "C-" + HEX, "c-" + HEX.upper(), "c_" + HEX,
    HEX, "c-" + HEX + ".tmp", "-" + HEX, "claude-home"])
def test_a_relay_home_must_be_named_c_or_x_then_16_lower_case_hex(tmp_path, name):
    found = layout(tmp_path)
    (found.key / name).mkdir(exist_ok=True)  # on Windows a case variant is the home that stands
    assert "named c-" in shape(found, path=found.key / name)


def test_a_path_with_dots_or_a_relative_path_or_a_nul_is_refused(tmp_path):
    found = layout(tmp_path)
    sep = os.sep
    for bad in (str(found.key) + sep + ".." + sep + found.key.name + sep + found.home.name,
                str(found.key) + sep + "." + sep + found.home.name,
                str(found.home.relative_to(found.top.parent)), "", str(found.home) + "\x00",
                None, 5):
        assert "absolute path" in shape(found, path=bad), repr(bad)


def test_a_relay_home_that_is_not_in_the_relay_folder_of_a_login_home_the_project_holds(tmp_path):
    found = layout(tmp_path)
    stranger = tmp_path / "other" / "DecemberCommand" / "logins" / "claude-code"
    stranger.mkdir(parents=True)
    odd = tmp_path / "logins" / "claude-code"
    odd.mkdir(parents=True)
    for homes in ((), (stranger,), (odd,), (found.top / "logins",), ("not a path", None)):
        assert "relay folder of a login home" in shape(found, auth_homes=homes), repr(homes)


def test_a_relay_folder_under_another_name_is_refused(tmp_path):
    found = layout(tmp_path)
    (found.top / "relay2" / found.key.name / found.home.name).mkdir(parents=True)
    assert "does not stand in" in shape(found, path=found.top / "relay2" / found.key.name
                                        / found.home.name)


@pytest.mark.parametrize("where", ["relay", "key", "home"])
def test_a_link_anywhere_in_the_spelled_route_is_refused_though_its_real_path_has_none(
        tmp_path, where):
    found = layout(tmp_path)
    real = tmp_path / "elsewhere"
    target = {"relay": found.relay, "key": found.key, "home": found.home}[where]
    shutil.copytree(target, real)
    shutil.rmtree(target)
    link(target, real)
    reason = shape(found)
    assert reason is not None and ("junction" in reason or "symbolic link" in reason), reason


def test_a_component_that_is_missing_or_not_a_directory_is_refused(tmp_path):
    found = layout(tmp_path)
    found.home.rmdir()
    assert "does not exist" in shape(found)
    found.home.write_text("a file", encoding="utf-8")
    assert "not a directory" in shape(found)


@pytest.mark.parametrize("what", [
    "project-is-the-relay-folder", "project-is-the-relay-home", "project-inside-the-relay-home",
    "work-inside", "work-is-the-home", "work-holds-the-home", "install-inside",
    "install-is-the-home", "install-holds-the-home", "a-login-home-is-the-home",
    "a-login-home-inside", "a-login-home-holds-the-home"])
def test_a_relay_home_that_touches_the_project_work_install_or_a_login_home_is_refused(
        tmp_path, what):
    found = layout(tmp_path)
    inside = found.home / "inner"
    inside.mkdir()
    changes = {
        "project-is-the-relay-folder": {"root": found.relay},
        "project-is-the-relay-home": {"root": found.home},
        "project-inside-the-relay-home": {"root": inside},
        "work-inside": {"work": inside}, "work-is-the-home": {"work": found.home},
        "work-holds-the-home": {"work": found.key},
        "install-inside": {"install": inside}, "install-is-the-home": {"install": found.home},
        "install-holds-the-home": {"install": found.top},
        "a-login-home-is-the-home": {"auth_homes": (found.login, found.home)},
        "a-login-home-inside": {"auth_homes": (found.login, inside)},
        "a-login-home-holds-the-home": {"auth_homes": (found.login, found.key)},
    }[what]
    assert "overlaps" in shape(found, **changes)
