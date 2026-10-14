"""What a loan may name: the runner's own limits, not the manners of the callers it has today.

A loan changes the DACL of three kinds of folder. The runner must hold to that whatever it is
asked: an install folder is the version folder of a pinned harness, never a login home or a folder
that holds one, and it is the folder the launched program stands in; a home is a minted folder of
a catalogued harness home root; a work folder is one item of the work tree.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command import operator_config, product_names
from conductor.command.adapters import process_loans
from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from tests.test_process_loans import HOME, LoanHold, _refused, record_files, world

SID = "S-1-15-2-1-2-3-4-5-6-7"


def with_logins(w, *homes):
    w.loans = FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ,
                          login_homes=lambda: homes)


@pytest.mark.parametrize("where", ["is-one", "lies-in-one", "holds-one"])
def test_an_install_folder_that_is_a_login_home_or_holds_or_lies_in_one_is_refused(
        tmp_path, where):
    w = world(tmp_path)
    install = w.folders["install"]  # a pinned version folder: no other rule is the reason
    (install / "login").mkdir()
    with_logins(w, {"is-one": install, "lies-in-one": install.parent,
                    "holds-one": install / "login"}[where])
    _refused(w, w.folders, "login folder")


def test_a_home_folder_that_is_a_login_home_is_refused(tmp_path):
    w = world(tmp_path)
    with_logins(w, w.folders["home"])
    _refused(w, w.folders, "login folder")


def test_the_login_folders_are_the_auth_homes_of_the_providers_the_project_holds(
        tmp_path, monkeypatch):
    data = tmp_path / "conductor.v3"
    first, second = tmp_path / "logins" / "a", tmp_path / "logins" / "b"
    rows = (SimpleNamespace(auth_home=str(first)), SimpleNamespace(auth_home=""),
            SimpleNamespace(auth_home=str(second)))
    asked = []

    def load(path):
        asked.append(Path(path))
        return rows

    monkeypatch.setattr(operator_config, "load_provider_configs", load)
    found = process_loans.configured_login_homes(data)
    assert asked == [data / operator_config.PROVIDER_CONFIG_FILENAME]
    assert set(found) == {Path(os.path.realpath(first)), Path(os.path.realpath(second))}


def test_a_provider_file_that_cannot_be_read_refuses_the_loan_it_cannot_vouch_for(
        tmp_path, monkeypatch):
    def broken(path):
        raise operator_config.OperatorConfigError(f"{path}: not the reviewed document")

    monkeypatch.setattr(operator_config, "load_provider_configs", broken)
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        process_loans.configured_login_homes(tmp_path / "conductor.v3")


def test_a_loan_asks_the_providers_of_its_own_project_for_the_login_folders(
        tmp_path, monkeypatch):
    w = world(tmp_path)
    asked = []

    def homes(data_root):
        asked.append(data_root)
        return (w.folders["install"],)

    monkeypatch.setattr(process_loans, "configured_login_homes", homes)
    w.loans = FolderLoans(w.store, w.store.native, hold_factory=LoanHold, environ=w.environ)
    _refused(w, w.folders, "login folder")
    assert asked == [w.store.directory.parent]


@pytest.mark.parametrize("where, reason", [
    ("pin-root", "pinned"), ("pin-name", "pinned"), ("inside-the-version", "pinned"),
    ("beside-the-pins", "pinned"), ("app-data", "pinned"), ("a-vendors-dot-folder", "pinned")])
def test_an_install_folder_that_is_not_the_version_folder_of_a_pin_is_refused(
        tmp_path, where, reason):
    w = world(tmp_path)
    version = w.folders["install"]  # tmp/harnesses/<name>/<version>
    profile = tmp_path / "profile"  # the user profile `world` names; none of it is a pin
    bad = {"pin-root": version.parent.parent, "pin-name": version.parent,
           "inside-the-version": version / "bin", "beside-the-pins": tmp_path / "other" / "k" / "1",
           "app-data": profile / "AppData" / "Local",
           "a-vendors-dot-folder": profile / ".codex"}[where]
    bad.mkdir(parents=True, exist_ok=True)
    _refused(w, {**w.folders, "install": bad}, reason)


def test_the_pin_root_is_found_by_its_name_whatever_the_case(tmp_path):
    w = world(tmp_path)
    pin = tmp_path / "pins" / "HARNESSES" / "kit" / "1.0"
    pin.mkdir(parents=True)
    assert w.loans.targets({**w.folders, "install": pin})["install"] == pin


def test_the_home_root_the_fixtures_use_is_one_a_catalogued_harness_has():
    assert HOME in {home for home, _marker in product_names._HARNESS_NAMES}


@pytest.mark.parametrize("route", [
    "src", "src/h", HOME, f"{HOME}/a/b", "claude-home/a", ".claude/a", ".kit-home/a",
    ".evil-home/a", "work/t2", "work/_tasks"])
def test_a_home_that_is_not_a_minted_folder_of_a_catalogued_home_root_is_refused(tmp_path, route):
    w = world(tmp_path)
    bad = w.root / route
    bad.mkdir(parents=True, exist_ok=True)
    _refused(w, {**w.folders, "home": bad})


@pytest.mark.parametrize("route", ["work/t1/sub", "work/_tasks", "work/_tasks/s1",
                                   "work/_tasks/s1/t1/x"])
def test_a_work_folder_that_is_not_one_item_of_the_work_tree_is_refused(tmp_path, route):
    w = world(tmp_path)
    bad = w.root / route
    bad.mkdir(parents=True, exist_ok=True)
    _refused(w, {**w.folders, "work": bad})


def test_the_work_folder_of_a_task_is_the_item_beneath_its_scope(tmp_path):
    w = world(tmp_path)
    task = w.root / "work" / "_tasks" / "s1" / "t1"
    task.mkdir(parents=True)
    assert w.loans.targets({**w.folders, "work": task})["work"] == task


def test_every_home_root_a_catalogued_harness_uses_is_one_a_home_may_stand_in(tmp_path):
    w = world(tmp_path)
    for root_name, _marker in product_names._HARNESS_NAMES:
        home = w.root / root_name / "a"
        home.mkdir(parents=True, exist_ok=True)
        assert w.loans.targets({**w.folders, "home": home})["home"] == home


def test_a_refused_folder_leaves_no_record(tmp_path):
    w = world(tmp_path)
    (w.root / "src").mkdir()
    with pytest.raises(ProfileRefused):
        w.loans.grant(w.profile_path, w.sid, "dispatch", {**w.folders, "home": w.root / "src"})
    assert record_files(w) == []


def test_a_program_in_the_install_folder_is_the_program_the_loan_was_for(tmp_path):
    holds_entry = process_loans.holds_entry
    install, elsewhere = tmp_path / "kit" / "1.0", tmp_path / "other"
    install.mkdir(parents=True)
    elsewhere.mkdir()
    assert holds_entry((str(install / "kit.exe"), "--version"), str(install))
    assert not holds_entry((str(elsewhere / "kit.exe"),), str(install))
    assert not holds_entry((str(install / ".." / "other" / "kit.exe"),), str(install))
    assert not holds_entry((str(install / "kit.exe"),), str(elsewhere))


def test_a_loan_that_names_no_install_folder_binds_no_program(tmp_path):
    assert process_loans.holds_entry((str(tmp_path / "anything.exe"),), None)


def test_a_runtime_in_a_system_folder_is_not_the_entry_the_script_it_runs_is(tmp_path):
    holds_entry = process_loans.holds_entry
    install, system = tmp_path / "kit" / "1.0", tmp_path / "winnt"
    install.mkdir(parents=True)
    system.mkdir()
    environ = {"SystemRoot": str(system)}
    node = str(system / "node.exe")
    script = str(install / "bin.js")
    assert holds_entry((node, "--preserve-symlinks", script, "run"), str(install), environ)
    assert not holds_entry((node, "--preserve-symlinks", "bin.js"), str(install), environ)
    assert not holds_entry((node, str(tmp_path / "bin.js")), str(install), environ)
    assert not holds_entry((node,), str(install), environ)


def test_a_spawn_whose_program_is_not_in_the_loaned_install_folder_is_refused_before_any_child(
        tmp_path):
    root, install = tmp_path / "project", tmp_path / "kit" / "1.0"
    (root / "work").mkdir(parents=True)
    install.mkdir(parents=True)
    runner = ProcessRunner(root)
    spec = CommandSpec((sys.executable, "-c", "pass"), "work",
                       boundary=WindowsContainer(SID, install=str(install)))
    with pytest.raises(CommandSpecError, match="install folder"):
        runner.run(spec)
    assert runner.active_tokens() == ()


@pytest.mark.parametrize("install", ["relative", 5, ""])
def test_a_container_names_its_install_folder_as_an_absolute_path_or_not_at_all(install):
    with pytest.raises(ValueError):
        WindowsContainer(SID, install=install)
    assert WindowsContainer(SID).install is None
