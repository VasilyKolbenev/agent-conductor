"""The owner commands the hub runs, run for real: a process of their own, the real boot reader.

`tests/test_hub_owner_command.py` and `tests/test_hub_recovery_reasons.py` say what the hub does
with a sentence and that the commands still print it, over a model of a restart. This file runs
the commands themselves through `OwnerOps` with the real `subprocess.Popen`, on projects and
logins made in a folder of the test, and reads the row each one leaves in the ledger. No fake
child, no fake popen. A restart cannot be made here, so no real recovery SUCCEEDS in this file:
what is proven is what the machine answers for the situations a person meets before one, and that
a profile copy changes configuration and never a login folder. Nothing here touches a real
project or login.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import conductor
from conductor import boot_witness, ownership, ownership_boot, ownership_login
from conductor import ownership_records as records
from conductor.command import operator_config
from conductor.hub import cli, events, operations, owner_ops, registry
from tests.test_login_recovery_prepare import legacy_lease
from tests.test_project_recovery_prepare import LEGACY, SESSION
from tests.test_provider_profile import config

BOUND_SECONDS = 90


def _stopped(_ident: str) -> tuple[str, None]:
    return "stopped", None


class Real:
    """A hub folder, a ledger and the real runner of the owner commands, over a test folder."""

    def __init__(self, tmp_path, monkeypatch, capsys) -> None:
        self.tmp, self.monkeypatch, self._capsys = tmp_path, monkeypatch, capsys
        self.home = tmp_path / "hub-home"
        self.home.mkdir()                    # the hub's folder exists before its first command
        monkeypatch.setenv("CONDUCT_HOME", str(self.home))
        monkeypatch.setenv("PYTHONPATH", str(Path(conductor.__file__).resolve().parents[1]))
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
        self.ledger = operations.Operations(self.home, events.EventBus(), start=lambda _id: None,
                                            status=_stopped)
        self.ops = owner_ops.OwnerOps(self.home, self.ledger, SimpleNamespace(), status=_stopped,
                                      policy=lambda: "none", poll_seconds=0.01)

    def project(self, name: str = "project") -> registry.Project:
        """A folder made a registered, activated project by the real `conduct projects add`."""
        root = self.tmp / name
        root.mkdir()
        assert cli.projects_add(str(root), legacy_writers_stopped=True) == 0
        self._capsys.readouterr()
        return registry.load(self.home).projects[-1]

    def abandon(self, project: registry.Project, boot: str) -> None:
        """Leave the project `opened` by an owner that is gone, with `boot` on the record."""
        root = Path(project.root)
        records.publish(root, records.chain(root), phase="opened", session_id=SESSION,
                        boot_id=boot, recovered_session=None)

    def login(self, name: str = "login") -> Path:
        folder = self.tmp / name
        folder.mkdir()
        (folder / "credential.json").write_bytes(b"synthetic-login-secret-0123456789")
        return folder

    def profile(self, login: Path) -> None:
        operator_config.save_profile_configs(
            self.home / "providers.json", [config(self.tmp, "claude-code", login=login)])

    def settled(self, ident: str) -> dict:
        deadline = time.monotonic() + BOUND_SECONDS
        while time.monotonic() < deadline:
            row = self.ledger.get(ident)
            if row["state"] != "running":
                return row
            time.sleep(0.05)
        raise AssertionError("the real command did not end")


@pytest.fixture
def real(tmp_path, monkeypatch, capsys):
    return Real(tmp_path, monkeypatch, capsys)


@pytest.fixture
def boot() -> str:
    """The witness of the boot this machine measures now, or a skip when it cannot."""
    try:
        return ownership_boot.current_boot()
    except (boot_witness.BootRefused, OSError) as error:
        pytest.skip(f"this machine cannot measure its boot: {error}")


def _bytes_under(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in sorted(folder.rglob("*")) if path.is_file()}


# -- a refusal of the real command is the row's own code ------------------------------------------


def test_a_real_ownership_command_that_refuses_reaches_the_operation_as_its_own_code(real):
    project = real.project()
    row = real.settled(real.ops.recover(project))
    assert (row["state"], row["code"], row["detail"]) == ("failed", "recovery_refused", None)
    assert str(project.root) not in json.dumps(row)


def test_a_real_project_recovery_in_the_same_boot_says_restart_needed(real, boot):
    project = real.project()
    real.abandon(project, boot)
    row = real.settled(real.ops.recover(project))
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "recovery_required", {"reason": "restart_needed"})
    assert str(project.root) not in json.dumps(row)
    assert records.chain(Path(project.root))["phase"] == "opened", "the refusal wrote nothing"


def test_a_real_login_recovery_in_the_same_boot_is_refused_login_recovery_required(
        real, boot):
    login, _box, _record = legacy_lease(real.tmp, real.monkeypatch, boot=boot)
    key = ownership_login.box_key(str(login))[2]
    row = real.settled(real.ops.recover_login(key, str(login)))
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "login_recovery_required", {"reason": "restart_needed"})
    assert str(login) not in json.dumps(row)


@pytest.mark.skipif(os.name != "nt", reason="the pre-counter boot format is a Windows record")
def test_a_real_recovery_of_a_legacy_record_says_prepare_needed_and_never_restart_needed(
        real, boot):
    project = real.project()
    real.abandon(project, LEGACY)
    row = real.settled(real.ops.recover(project))
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "recovery_required", {"reason": "prepare_needed"})
    login, _box, _record = legacy_lease(real.tmp, real.monkeypatch, boot=LEGACY)
    key = ownership_login.box_key(str(login))[2]
    login_row = real.settled(real.ops.recover_login(key, str(login)))
    assert (login_row["code"], login_row["detail"]) == (
        "login_recovery_required", {"reason": "prepare_needed"})


# -- a profile copy changes configuration and nothing of a login ----------------------------------


def test_a_real_profile_copy_into_a_stopped_project_succeeds_and_leaves_the_login_folder_untouched(
        real):
    project = real.project()
    login = real.login()
    real.profile(login)
    before = _bytes_under(login)
    row = real.settled(real.ops.providers(project, mode=None, restart=False))
    assert (row["state"], row["code"]) == ("succeeded", None), row
    assert row["result"]["providers"] == "copied"
    assert _bytes_under(login) == before
    copied = operator_config.load_provider_configs(
        ownership.data_root(Path(project.root)) / "providers.json")
    assert [one.provider_id for one in copied] == ["claude-code"]


def test_a_real_profile_copy_with_a_live_owner_in_this_process_fails_owner_busy(real):
    project = real.project()
    real.profile(real.login())
    with ownership.acquire_owner(Path(project.root)):
        row = real.settled(real.ops.providers(project, mode=None, restart=False))
    assert (row["state"], row["code"]) == ("failed", "owner_busy"), row
    assert not (ownership.data_root(Path(project.root)) / "providers.json").exists()


def test_a_real_profile_copy_into_an_abandoned_project_keeps_the_typed_recovery_reason(
        real, boot):
    project = real.project()
    real.profile(real.login())
    real.abandon(project, boot)
    row = real.settled(real.ops.providers(project, mode=None, restart=False))
    assert (row["state"], row["code"]) == ("failed", "subprocess_failed"), row
    assert row["detail"] == {"reason": "recovery_required"}
    assert str(project.root) not in json.dumps(row)
