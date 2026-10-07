"""The hub keeps native folder paths out of HTTP and bounds the one picker it owns."""
from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from conductor.hub import dialogs, events, pick_folder, refusals


class Group:
    def __init__(self):
        self.terminated = False
        self.closed = False

    def terminate(self):
        self.terminated = True

    def close(self):
        self.closed = True


class Chosen:
    returncode = 0
    stdout = None

    def __init__(self, path):
        self.path = path

    def communicate(self, *, timeout):
        assert timeout == dialogs.TIMEOUT
        return json.dumps({"path": str(self.path)}).encode("utf-8"), b""


def settled(manager, ident):
    for _ in range(100):
        row = manager.get(ident)
        if row["state"] != "open":
            return row
        time.sleep(.01)
    raise AssertionError("dialog did not settle")


def test_project_pick_uses_one_grouped_helper_and_returns_only_folder_name(
        tmp_path, monkeypatch):
    home, project = tmp_path / "home", tmp_path / "проект"
    home.mkdir()
    project.mkdir()
    captured = []
    group = Group()

    def launch(argv, **kwargs):
        captured.append((argv, kwargs))
        return Chosen(project)

    monkeypatch.setattr(dialogs._procgroup, "popen_kwargs", lambda: {"start_new_session": True})
    monkeypatch.setattr(dialogs._procgroup, "make_group", lambda _proc: group)
    manager = dialogs.Dialogs(home, events.EventBus(), popen=launch, backend="linux",
                              available=lambda: True)
    ident = manager.begin("project")
    row = settled(manager, ident)
    assert row == {"pick_id": ident, "purpose": "project", "state": "picked",
                   "folder": "проект", "project": "none", "code": None}
    assert str(project) not in json.dumps(row, ensure_ascii=False)
    assert manager.resolve(ident).path == str(project)
    assert captured[0][0] == [sys.executable, "-m", "conductor.hub.pick_folder",
                              "--backend", "linux"]
    assert captured[0][1]["start_new_session"] is True
    assert group.closed and not group.terminated
    manager.consume(ident)
    assert manager.resolve(ident) is None


def test_only_one_open_dialog_and_cancel_or_expiry_never_releases_its_path(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    now = [0.0]
    manager = dialogs.Dialogs(home, events.EventBus(), clock=lambda: now[0],
                              available=lambda: True)
    manager._choose = lambda _ident: {"cancelled": True}
    ident = manager.begin("project")
    assert settled(manager, ident)["state"] == "cancelled"
    with pytest.raises(refusals.HubRefusal) as error:
        manager.get("pick-" + "0" * 32)
    assert error.value.code == "pick_not_found"
    ident = manager.begin("project")
    assert settled(manager, ident)["state"] == "cancelled"
    now[0] = dialogs.PICK_LIFETIME + 1
    assert manager.get(ident)["state"] == "expired"
    assert manager.resolve(ident) is None


def test_native_backend_command_order_is_explicit_without_opening_a_window(monkeypatch):
    calls = []
    monkeypatch.setattr(pick_folder, "_command", lambda argv, **options: (
        calls.append((argv, options)) or {"unavailable": True}))
    monkeypatch.setattr(pick_folder, "_tkinter", lambda: {"cancelled": True})
    assert pick_folder.choose("mac") == {"unavailable": True}
    assert calls == [(["/usr/bin/osascript", "-e", "POSIX path of (choose folder)"],
                      {"mac": True})]
    calls.clear()
    monkeypatch.setenv("DISPLAY", ":fake")
    monkeypatch.setattr(pick_folder.os.path, "isfile", lambda _path: True)
    monkeypatch.setattr(pick_folder.os, "access", lambda _path, _mode: True)
    assert pick_folder.choose("linux") == {"cancelled": True}
    assert [argv[0] for argv, _options in calls] == ["/usr/bin/zenity", "/usr/bin/kdialog"]
    calls.clear()
    assert pick_folder.choose("windows") == {"cancelled": True}
    assert calls == []


def test_external_picker_preserves_spaces_in_the_chosen_folder(monkeypatch):
    class Completed:
        returncode = 0
        stdout = b"/home/user/a folder  \n"
        stderr = b""

    monkeypatch.setattr(pick_folder.subprocess, "run", lambda *_args, **_kwargs: Completed())
    assert pick_folder._command(["/usr/bin/zenity"]) == {"path": "/home/user/a folder  "}


def test_cancel_keeps_the_single_slot_until_the_helper_really_exits(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    entered, release = threading.Event(), threading.Event()
    manager = dialogs.Dialogs(home, events.EventBus(), available=lambda: True)

    def choose(_ident):
        entered.set()
        assert release.wait(2)
        return {"cancelled": True}

    manager._choose = choose
    ident = manager.begin("project")
    assert entered.wait(1)
    manager.cancel(ident)
    with pytest.raises(refusals.HubRefusal) as error:
        manager.begin("project")
    assert error.value.code == "dialog_busy"
    release.set()
    for _ in range(100):
        if manager._open is None:
            break
        time.sleep(.01)
    assert manager._open is None


def test_a_picked_project_whose_restart_was_only_prepared_is_reported_as_activated(
        tmp_path, monkeypatch):
    from tests._boot_world import counter, measure
    from tests.test_project_recovery_prepare import abandoned_legacy
    from conductor import ownership_transition
    home, project = tmp_path / "home", tmp_path / "prepared"
    home.mkdir()
    project.mkdir()
    abandoned_legacy(project)
    measure(monkeypatch, counter(42))
    ownership_transition.prepare_recovery(project)
    monkeypatch.setattr(dialogs._procgroup, "popen_kwargs", lambda: {"start_new_session": True})
    monkeypatch.setattr(dialogs._procgroup, "make_group", lambda _proc: Group())
    manager = dialogs.Dialogs(home, events.EventBus(), popen=lambda argv, **kwargs: Chosen(project),
                              backend="linux", available=lambda: True)
    row = settled(manager, manager.begin("project"))
    assert row["state"] == "picked" and row["project"] == "activated"
