"""The login folders the hub lists, found from the profile and the registered projects (4.1.8).

A login is named by the key of its box (`ownership_login.box_key`), never by a path; a source that
cannot be read hides only itself; and the state of a box is the word that offers no action
whenever the hub cannot tell. No test reads a token or a login file.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from conductor import ownership_login
from conductor.command import operator_config
from conductor.hub import registry
from tests._boot_world import counter, measure
from tests._hub_world import World, id_of
from tests.test_login_recovery_prepare import legacy_lease
from tests.test_provider_profile import config


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


@pytest.fixture
def logins():
    """The module under test, imported when a test runs (so a missing module fails that test)."""
    from conductor.hub import logins as module
    return module


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    operator_config.save_provider_configs(path, rows)


def _scan(logins, world):
    return logins.scan(world.home, registry.load(world.home).projects)


def _folder(tmp_path, name):
    folder = tmp_path / name
    folder.mkdir()
    return folder


def test_the_hubs_login_key_is_the_name_of_the_box_a_lease_makes(tmp_path, monkeypatch):
    measure(monkeypatch, counter(42))
    login = _folder(tmp_path, "login")
    lease = ownership_login.LoginLease(str(login))
    try:
        box = lease.box
    finally:
        lease.close()
    _home, found, key = ownership_login.box_key(str(login))
    assert found == box and box.name == ".conduct-login-" + key
    assert re.fullmatch(r"[0-9a-f]{64}", key)


def test_logins_are_found_from_the_profile_and_from_every_registered_projects_provider_file(
        logins, world, tmp_path):
    shared, solo = _folder(tmp_path, "shared"), _folder(tmp_path, "solo")
    _write(world.home / "providers.json", [config(tmp_path, "codex", login=solo)])
    for name in ("a", "b"):           # a project's file is `data_root(root)/providers.json`
        folder = Path(world.roots[name]) / "conductor"
        _write(folder / "providers.json", [config(tmp_path, "claude-code", label=name,
                                                  login=shared)])
    by_home = {Path(item.auth_home).resolve(): item for item in _scan(logins, world)}
    assert set(by_home) == {shared.resolve(), solo.resolve()}
    assert by_home[shared.resolve()].used_by == (id_of("a"), id_of("b"))     # one entry, both
    assert by_home[shared.resolve()].harness == "claude-code"
    assert by_home[solo.resolve()].used_by == () and by_home[solo.resolve()].harness == "codex"
    assert all(re.fullmatch(r"[0-9a-f]{64}", item.key) for item in by_home.values())


def test_a_login_the_profile_and_a_project_both_name_is_one_entry_the_profile_named_first(
        logins, world, tmp_path):
    shared = _folder(tmp_path, "shared")
    _write(world.home / "providers.json", [config(tmp_path, "codex", login=shared)])
    _write(Path(world.roots["c"]) / "conductor" / "providers.json",
           [config(tmp_path, "claude-code", login=shared)])
    (only,) = _scan(logins, world)
    assert (only.harness, only.used_by) == ("codex", (id_of("c"),))


def test_a_provider_file_that_cannot_be_read_hides_no_other_login(logins, world, tmp_path):
    broken = Path(world.roots["a"]) / "conductor"
    broken.mkdir(parents=True)
    (broken / "providers.json").write_text("{not json", encoding="utf-8")
    solo = _folder(tmp_path, "solo")
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=solo)])
    assert len(_scan(logins, world)) == 1


def test_a_login_directory_that_is_not_a_plain_existing_folder_is_left_out(
        logins, world, tmp_path):
    a_file = tmp_path / "a-file"
    a_file.write_text("x", encoding="utf-8")
    _write(world.home / "providers.json", [
        config(tmp_path, "claude-code", login=tmp_path / "absent"),
        config(tmp_path, "codex", login=a_file)])
    assert _scan(logins, world) == ()


def test_a_box_with_no_active_record_is_free(logins, world, tmp_path):
    solo = _folder(tmp_path, "solo")
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=solo)])
    (only,) = _scan(logins, world)
    assert logins.state_of(only, active_running=False, closing_owed=False) == "free"
    assert logins.state_of(only, active_running=True, closing_owed=True) == "free"


@pytest.mark.parametrize(("running", "owed", "word"), [
    (False, False, "unclosed"), (True, False, "in_use"), (False, True, "in_use"),
    (True, True, "in_use")])
def test_a_box_with_a_lease_record_is_unclosed_only_when_the_hub_knows_no_one_who_holds_it(
        logins, world, tmp_path, monkeypatch, running, owed, word):
    home, _box, _record = legacy_lease(tmp_path, monkeypatch)
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=home)])
    (only,) = _scan(logins, world)
    assert logins.state_of(only, active_running=running, closing_owed=owed) == word


def test_a_box_the_hub_cannot_read_is_in_use_the_word_that_offers_no_action(
        logins, world, tmp_path, monkeypatch):
    home, _box, _record = legacy_lease(tmp_path, monkeypatch)
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=home)])
    (only,) = _scan(logins, world)
    real = os.lstat

    def refuse(path, *args, **kwargs):
        if Path(path).name == "active.json":
            raise PermissionError("the box cannot be read")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", refuse)
    assert logins.state_of(only, active_running=False, closing_owed=False) == "in_use"


def test_the_public_form_has_exactly_four_keys_and_no_path(
        logins, world, tmp_path, monkeypatch):
    home, box, _record = legacy_lease(tmp_path, monkeypatch)
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=home)])
    (only,) = _scan(logins, world)
    entry = logins.public(only, "unclosed")
    assert set(entry) == {"login_key", "harness", "used_by", "state"}
    assert entry["login_key"] == box.name[len(".conduct-login-"):]
    assert entry["used_by"] == [] and entry["state"] == "unclosed"
    assert str(home) not in json.dumps(entry) and str(box) not in json.dumps(entry)


def _view(logins, world, reads, clock, flags=None):
    """A view whose two facts about the hub's children are the keys of `flags`, read each time."""
    flags = {} if flags is None else flags
    return logins.LoginView(
        world.home, lambda: reads.append(1) or registry.load(world.home).projects,
        lambda: flags.get("running", False), lambda: flags.get("owed", False),
        clock=lambda: clock[0], ttl=2.0)


def test_the_view_does_not_read_the_sources_again_within_its_ttl_and_does_after_it(
        logins, world, tmp_path):
    solo = _folder(tmp_path, "solo")
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=solo)])
    clock, reads = [0.0], []
    view = _view(logins, world, reads, clock)
    assert len(view.entries()) == 1 and len(view.entries()) == 1
    assert len(reads) == 1
    clock[0] = 1.9
    view.entries()
    assert len(reads) == 1
    clock[0] = 2.5
    view.entries()
    assert len(reads) == 2


def test_the_state_is_read_afresh_on_every_call_though_the_sources_are_kept(
        logins, world, tmp_path, monkeypatch):
    home, _box, _record = legacy_lease(tmp_path, monkeypatch)
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=home)])
    clock, reads, flags = [0.0], [], {}
    view = _view(logins, world, reads, clock, flags)
    assert view.entries()[0]["state"] == "unclosed"
    flags["running"] = True
    assert view.entries()[0]["state"] == "in_use"
    flags.update(running=False, owed=True)
    assert view.entries()[0]["state"] == "in_use"
    flags["owed"] = False
    assert view.entries()[0]["state"] == "unclosed"
    assert len(reads) == 1                           # the sources were read once for all four


def test_a_lookup_by_key_always_scans_afresh_and_names_no_one_for_an_unknown_key(
        logins, world, tmp_path):
    solo = _folder(tmp_path, "solo")
    _write(world.home / "providers.json", [config(tmp_path, "claude-code", login=solo)])
    clock, reads = [0.0], []
    view = _view(logins, world, reads, clock)
    (only,) = _scan(logins, world)
    assert view.find(only.key) == only and view.find(only.key) == only
    assert len(reads) == 2                           # no cache for a decision
    assert view.find("0" * 64) is None


def test_nothing_is_listed_and_no_state_is_asked_for_when_no_login_is_named(logins, world):
    asked = []
    view = logins.LoginView(world.home, lambda: registry.load(world.home).projects,
                            lambda: asked.append("running") or False,
                            lambda: asked.append("owed") or False)
    assert view.entries() == [] and asked == []
