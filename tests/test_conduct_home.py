"""`<conduct-home>` (spec 4.1.2): where the hub's folder is, that it exists, and where it may be.

The path: `~/.december-command` unless `CONDUCT_HOME` names an absolute path, and a relative or
empty override is refused rather than resolved against whatever the working folder happens to
be. Making the folder: `conduct_home()` creates it (mode 0700 where the OS has modes) and leaves
an existing one as it is. Placement: a home inside an activated project, or one that has become
a project itself, is refused `conduct_home_invalid` with the reason in the detail, and a login
folder that is the home or one of its parents is `conduct_home_overlaps_login`. Two claims of
4.1.13 item 7 are measured against the rest of the product: the hub never makes a `.conduct` or
a `conductor.v3` anywhere in its folder (`_hub_operations` lists what the hub does, and grows
with each one), and a write of `<home>/providers.json` passes the `provider_write_guard` that
this slice did not change.
"""
from __future__ import annotations

import hashlib
import inspect
import os
import stat
import sys
from pathlib import Path

import pytest

from conductor import ownership, tool_pins
from conductor.hub import home
from conductor.ownership_errors import OwnerRefused


def test_conduct_home_defaults_to_the_dot_folder_in_the_user_profile(monkeypatch):
    monkeypatch.delenv("CONDUCT_HOME", raising=False)
    assert home.conduct_home_path() == Path.home() / ".december-command"


def test_an_absolute_conduct_home_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("CONDUCT_HOME", str(tmp_path / "elsewhere"))
    assert home.conduct_home_path() == tmp_path / "elsewhere"


@pytest.mark.parametrize("value", ["relative/folder", ".", "", "~/home"])
def test_a_relative_or_empty_conduct_home_is_refused_with_its_code(monkeypatch, value):
    monkeypatch.setenv("CONDUCT_HOME", value)
    with pytest.raises(home.ConductHomeInvalid) as caught:
        home.conduct_home_path()
    assert caught.value.code == "conduct_home_invalid"
    assert "absolute" in str(caught.value)


def test_computing_the_path_creates_nothing(monkeypatch, tmp_path):
    target = tmp_path / "not-yet"
    monkeypatch.setenv("CONDUCT_HOME", str(target))
    home.conduct_home_path()
    assert not target.exists()


# -- making the folder ---------------------------------------------------------------------


def test_conduct_home_creates_the_folder_with_its_parents_and_returns_its_path(
        monkeypatch, tmp_path):
    target = tmp_path / "profile" / ".december-command"
    monkeypatch.setenv("CONDUCT_HOME", str(target))
    assert home.conduct_home() == target
    assert target.is_dir()


@pytest.mark.skipif(os.name == "nt", reason="Windows has no POSIX mode bits to judge")
def test_the_folder_it_creates_is_private_to_the_user_on_posix(monkeypatch, tmp_path):
    monkeypatch.setenv("CONDUCT_HOME", str(tmp_path / ".december-command"))
    made = home.conduct_home()
    assert stat.S_IMODE(made.stat().st_mode) == 0o700


def test_a_folder_that_is_already_there_is_left_exactly_as_it_is(monkeypatch, tmp_path):
    target = tmp_path / ".december-command"
    target.mkdir()
    (target / "registry.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CONDUCT_HOME", str(target))
    assert home.conduct_home() == home.conduct_home() == target
    assert [entry.name for entry in target.iterdir()] == ["registry.json"]


def test_a_relative_override_creates_nothing_and_is_refused(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", "relative")
    with pytest.raises(home.ConductHomeInvalid):
        home.conduct_home()
    assert list(tmp_path.iterdir()) == []


# -- where it may be (rules 1 and 2 of 4.1.2) ------------------------------------------------


@pytest.mark.parametrize("marker", [".conduct", "conductor.v3"])
def test_a_home_inside_an_activated_project_is_refused_with_its_reason(tmp_path, marker):
    project = tmp_path / "project"
    (project / marker).mkdir(parents=True)
    inside = project / "deep" / "er" / ".december-command"
    with pytest.raises(home.ConductHomeInvalid) as caught:
        home.require_placement(inside)
    assert caught.value.code == "conduct_home_invalid"
    assert marker in str(caught.value) and str(project) in str(caught.value)


def test_a_home_that_has_become_a_project_itself_is_refused(tmp_path):
    folder = tmp_path / ".december-command"
    (folder / ".conduct").mkdir(parents=True)
    with pytest.raises(home.ConductHomeInvalid, match=r"\.conduct"):
        home.require_placement(folder)


def test_a_home_beside_a_project_and_a_home_that_does_not_exist_yet_are_allowed(tmp_path):
    (tmp_path / "project" / ".conduct").mkdir(parents=True)
    assert home.require_placement(tmp_path / ".december-command") == tmp_path / ".december-command"
    assert home.require_placement(tmp_path / "new" / "home") == tmp_path / "new" / "home"


def test_a_login_folder_that_is_the_home_or_one_of_its_parents_overlaps_it(tmp_path):
    folder = tmp_path / "a" / "b" / ".december-command"
    for login in (folder, folder.parent, tmp_path):
        with pytest.raises(home.ConductHomeOverlapsLogin) as caught:
            home.require_placement(folder, [login])
        assert caught.value.code == "conduct_home_overlaps_login"
        assert str(login) in str(caught.value)


def test_a_login_folder_beside_or_beneath_the_home_is_not_an_overlap_judged_here(tmp_path):
    folder = tmp_path / ".december-command"
    beside, beneath = tmp_path / "logins" / "claude", folder / "logins" / "claude"
    assert home.require_placement(folder, [beside, beneath]) == folder


def test_a_login_folder_that_is_not_absolute_is_a_fault_of_the_caller(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        home.require_placement(tmp_path / ".december-command", ["logins/claude"])


def test_the_placement_rules_name_the_project_before_the_login(tmp_path):
    folder = tmp_path / "project" / ".december-command"
    (tmp_path / "project" / ".conduct").mkdir(parents=True)
    with pytest.raises(home.ConductHomeInvalid):
        home.require_placement(folder, [tmp_path])


# -- what the hub does to its folder never makes a project of it ------------------------------


def _hub_operations(folder: Path) -> None:
    """Every operation of the hub's core that writes into `<conduct-home>`; each adds its own."""
    made = home.conduct_home()
    assert made == folder
    tool_pins.pin_tool("git", str(Path(sys.executable).resolve()), folder=made,
                       run=lambda argv, env: "git version 2.47.1")


def _markers_at_or_above(folder: Path) -> list[str]:
    names = (".conduct", "conductor.v3")
    found = [str(path) for path in folder.rglob("*") if path.name in names]
    found += [str(place / name) for place in (folder, *folder.parents) for name in names
              if os.path.lexists(place / name)]
    return found


def test_the_hub_never_creates_dot_conduct_in_the_home_folder(monkeypatch, tmp_path):
    folder = tmp_path / ".december-command"
    monkeypatch.setenv("CONDUCT_HOME", str(folder))
    _hub_operations(folder)
    assert sorted(entry.name for entry in folder.iterdir()), "the operations made nothing to judge"
    assert _markers_at_or_above(folder) == []


def test_the_marker_search_can_say_yes(tmp_path):
    folder = tmp_path / "home"
    (folder / "run" / ".conduct").mkdir(parents=True)
    assert _markers_at_or_above(folder) == [str(folder / "run" / ".conduct")]


# -- the profile's write goes through the guard nobody changed ------------------------------

#: The text of `provider_write_guard` this slice leaves as it is (spec 4.1.2 and 8.7): the
#: home needs no exception in it, so any change to it is a decision somebody must make on
#: purpose, and this digest is what tells them they are making one.
GUARD_DIGEST = "73b796ec1a982b34798c9193838cc8a428a5369f95a106517c15261d253cf014"


def test_profile_write_passes_the_unchanged_provider_write_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("CONDUCT_HOME", str(tmp_path / ".december-command"))
    target = home.conduct_home() / "providers.json"
    with ownership.provider_write_guard(target, None):
        target.write_text("{}", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "{}"
    shown = hashlib.sha256(inspect.getsource(ownership.provider_write_guard).encode()).hexdigest()
    assert shown == GUARD_DIGEST, "provider_write_guard changed: the home needed no exception"


@pytest.mark.parametrize("marker", [".conduct", "conductor.v3"])
def test_the_same_guard_refuses_a_profile_under_a_folder_that_holds_a_project(tmp_path, marker):
    (tmp_path / marker).mkdir()
    target = tmp_path / ".december-command" / "providers.json"
    target.parent.mkdir()
    with pytest.raises(OwnerRefused) as caught:
        with ownership.provider_write_guard(target, None):
            pass
    assert caught.value.code == "project_context_required"
