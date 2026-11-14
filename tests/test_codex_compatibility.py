"""Public transport witnesses for the reviewed 0.164.0 compatibility changes."""
from __future__ import annotations

import pytest

from conductor.command.adapters.provider import ProviderConfigError
from tests import _fakecodex
from tests.test_command_codex_transport import _task_row, a_harness, a_request, run_once
from tests.test_harness_subscription_login import a_codex_harness
from tests.test_provider_auth_mode import AUTH_HOME, a_config


@pytest.mark.parametrize("version,admitted", [("0.164.0", True), ("0.112.0", False)])
def test_only_the_new_reviewed_binary_may_start_a_task(tmp_path, version, admitted):
    adapter, _root, log = a_harness(
        tmp_path, **{_fakecodex.VERSION: f"codex-cli {version}"})

    receipt = run_once(adapter, a_request())

    assert (receipt.outcome == "succeeded") is admitted, receipt.detail
    assert len(_fakecodex.task_spawns(log)) == int(admitted)


def test_the_real_task_argv_disables_feedback(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    argv = _task_row(log)["argv"]
    assert argv.count("feedback.enabled=false") == 1
    assert argv[argv.index("feedback.enabled=false") - 1] == "-c"


@pytest.mark.parametrize("name", [
    ".env", ".ENV", ".EnV", "environments.toml", "ENVIRONMENTS.TOML", "Environments.ToMl",
])
@pytest.mark.parametrize("body", ["", 'harmless = "still a forbidden input"\n'])
def test_external_login_configuration_refuses_before_any_spawn(tmp_path, name, body):
    home = tmp_path / "login"
    home.mkdir()
    source = home / name
    source.write_text(body, encoding="utf-8", newline="\n")
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", receipt.detail
    assert "also holds" in receipt.detail and "configuration" in receipt.detail
    assert _fakecodex.spawns(log) == []
    assert source.read_text(encoding="utf-8") == body


def test_an_unreadable_login_listing_refuses_before_any_spawn(tmp_path, monkeypatch):
    from conductor.command.adapters import login_home

    home = tmp_path / "login"
    home.mkdir()
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    monkeypatch.setattr(login_home, "entries", lambda _home: None)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", receipt.detail
    assert "also holds" in receipt.detail and "configuration" in receipt.detail
    assert _fakecodex.spawns(log) == []


@pytest.mark.parametrize("name", [
    "CODEX_ACCESS_TOKEN", "OPENAI_FEDERATION_RULE_ID", "OPENAI_IDENTITY_TOKEN_FILE",
    "OPENAI_WORKLOAD_IDENTITY_CONTEXT", "CODEX_GUARDIAN_DECISIONS_API_KEY",
])
@pytest.mark.parametrize("lower", [False, True])
def test_additional_credentials_cannot_replace_the_subscription(name, lower):
    selected = name.lower() if lower else name
    with pytest.raises(ProviderConfigError):
        a_config(auth="subscription", auth_home=AUTH_HOME, env_allow=[selected])


@pytest.mark.parametrize("emit,task_exit,verdict_exit,expected", [
    (False, 1, 0, 1), (False, 0, 1, 0), (True, 1, 0, 0), (True, 0, 1, 1),
])
def test_fake_checker_final_file_follows_the_exit_road_it_actually_uses(
        tmp_path, monkeypatch, emit, task_exit, verdict_exit, expected):
    """No subprocess: the vendor double must not invent a completed-turn file on failure."""
    import os
    import sys

    answer = tmp_path / "last-message.txt"
    monkeypatch.setattr(os, "environ", {
        _fakecodex.EXIT: str(task_exit), _fakecodex.VERDICT_EXIT: str(verdict_exit),
        **({_fakecodex.EMIT_VERDICT: "enabled-verdict-accept"} if emit else {}),
    })
    monkeypatch.setattr(sys, "argv", ["codex", "exec", "--sandbox", "read-only", "-o", str(answer)])
    monkeypatch.setattr(_fakecodex, "_read_task", lambda: (
        {"read": False}, "conduct independent verification"))
    monkeypatch.setattr(_fakecodex, "_record", lambda *_args: None)

    assert _fakecodex.main() == expected
    assert answer.exists() is (expected == 0)
    if expected == 0:
        assert answer.read_text(encoding="utf-8") == "the fake Codex CLI reports a final message"


@pytest.mark.parametrize("preexisting", [False, True])
def test_native_quota_accounts_for_measured_home_state(tmp_path, monkeypatch, preexisting):
    """P6/P11 names at the CLI seam, through the actual quota read and login cleanup."""
    from conductor.command.quota_plans import quota_plan_for
    from tests.test_subscription_quota import PAYLOAD, adapter as quota_adapter

    value, runner, home = quota_adapter(tmp_path)
    scratch_dirs = ("tmp", "log", ".sandbox")
    scratch_files = (
        "goals_1.sqlite", "goals_1.sqlite-shm", "goals_1.sqlite-wal",
        "logs_2.sqlite", "logs_2.sqlite-shm", "logs_2.sqlite-wal",
        "memories_1.sqlite", "memories_1.sqlite-shm", "memories_1.sqlite-wal",
        "queue_1.sqlite", "queue_1.sqlite-shm", "queue_1.sqlite-wal",
        "state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal",
    )
    kept_files = ("models_cache.json", "installation_id", "version.json")
    original = b'{"synthetic":"operator-owned-login"}\n'
    (home / "auth.json").write_bytes(original)
    (home / "owner-notes.txt").write_bytes(b"operator-owned")
    if preexisting:
        for name in scratch_files:
            (home / name).write_bytes(b"operator-owned")
        for name in scratch_dirs:
            (home / name).mkdir()
            (home / name / "previous.txt").write_bytes(b"operator-owned")
    run = runner.run

    def write_measured_state(spec):
        if spec.argv[-1] == "app-server":
            assert runner._child_env(spec)["CODEX_HOME"] == str(home)
            for name in (*scratch_files, *kept_files):
                if not (home / name).exists():
                    (home / name).write_bytes(b"synthetic-vendor-state")
            for name in (*scratch_dirs, "skills"):
                (home / name).mkdir(exist_ok=True)
                (home / name / "current.txt").write_bytes(b"synthetic-vendor-state")
        return run(spec)

    monkeypatch.setattr(runner, "run", write_measured_state)

    assert quota_plan_for("p7-provider", value).request.read() == PAYLOAD
    assert len(runner.specs) == 2
    assert [spec.argv[-1] for spec in runner.specs] == ["--version", "app-server"]
    assert (home / "auth.json").read_bytes() == original
    assert (home / "owner-notes.txt").read_bytes() == b"operator-owned"
    for name in (*kept_files, "skills/current.txt"):
        assert (home / name).read_bytes() == b"synthetic-vendor-state"
    for name in scratch_files:
        assert (home / name).exists() is preexisting, name
        if preexisting:
            assert (home / name).read_bytes() == b"operator-owned"
    for name in scratch_dirs:
        assert (home / name).exists() is preexisting, name
        if preexisting:
            assert (home / name / "previous.txt").read_bytes() == b"operator-owned"
        assert not (home / name / "current.txt").exists(), name


def test_native_quota_still_refuses_an_unmeasured_new_database(tmp_path, monkeypatch):
    from conductor.command.adapters.quota_connection import NativeQuotaReadError
    from conductor.command.quota_plans import quota_plan_for
    from tests.test_subscription_quota import adapter as quota_adapter

    value, runner, home = quota_adapter(tmp_path)
    run = runner.run

    def write_unknown_state(spec):
        if spec.argv[-1] == "app-server":
            (home / "future_1.sqlite").write_bytes(b"synthetic-unaccounted-state")
        return run(spec)

    monkeypatch.setattr(runner, "run", write_unknown_state)

    with pytest.raises(NativeQuotaReadError):
        quota_plan_for("p7-provider", value).request.read()
    assert len(runner.specs) == 2
    assert (home / "future_1.sqlite").read_bytes() == b"synthetic-unaccounted-state"


@pytest.mark.parametrize("database_stood", [False, True])
def test_native_quota_takes_a_wal_back_only_with_its_database(
        tmp_path, monkeypatch, database_stood):
    """A database the operator had stays with its write-ahead files, read or not."""
    from conductor.command.quota_plans import quota_plan_for
    from tests.test_subscription_quota import PAYLOAD, adapter as quota_adapter

    value, runner, home = quota_adapter(tmp_path)
    names = ("state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal")
    if database_stood:
        (home / names[0]).write_bytes(b"operator-owned")
    run = runner.run

    def write_the_state(spec):
        if spec.argv[-1] == "app-server":
            for name in names:
                if not (home / name).exists():
                    (home / name).write_bytes(b"synthetic-vendor-state")
        return run(spec)

    monkeypatch.setattr(runner, "run", write_the_state)

    assert quota_plan_for("p7-provider", value).request.read() == PAYLOAD
    assert [(home / name).exists() for name in names] == [database_stood] * 3
    if database_stood:
        assert (home / names[0]).read_bytes() == b"operator-owned"
        assert (home / names[1]).read_bytes() == b"synthetic-vendor-state"
        assert (home / names[2]).read_bytes() == b"synthetic-vendor-state"


def test_take_back_leaves_the_companions_of_a_database_it_could_not_remove(
        tmp_path, monkeypatch):
    from conductor.command.adapters import login_home
    from conductor.command.adapters.codex_cli import LOGIN_SCRATCH

    names = ("state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal")
    for name in names:
        (tmp_path / name).write_bytes(b"synthetic-vendor-state")
    real = login_home._take_one
    monkeypatch.setattr(
        login_home, "_take_one", lambda where, name: name == names[0] or real(where, name))

    left = login_home.take_back(str(tmp_path), LOGIN_SCRATCH, frozenset(names))

    assert left == names, "a database that stays was left without its write-ahead files"
    assert all((tmp_path / name).exists() for name in names)


@pytest.mark.parametrize("database_stood", [False, True])
def test_take_back_keeps_a_companion_beside_a_standing_database_and_removes_an_orphan(
        tmp_path, database_stood):
    from conductor.command.adapters import login_home
    from conductor.command.adapters.codex_cli import LOGIN_SCRATCH

    if database_stood:
        (tmp_path / "state_5.sqlite").write_bytes(b"operator-owned")
    (tmp_path / "state_5.sqlite-wal").write_bytes(b"synthetic-vendor-state")

    left = login_home.take_back(
        str(tmp_path), LOGIN_SCRATCH, frozenset({"state_5.sqlite-wal"}))

    assert left == (), "a companion that was kept, or removed, is not residue"
    assert (tmp_path / "state_5.sqlite-wal").exists() is database_stood


def test_take_back_keeps_and_counts_a_companion_beside_a_database_it_cannot_measure(
        tmp_path, monkeypatch):
    """A stat that fails otherwise than as absent is no answer: not 'stood', not 'gone'."""
    import os

    from conductor.command.adapters import login_home
    from conductor.command.adapters.codex_cli import LOGIN_SCRATCH

    (tmp_path / "state_5.sqlite").write_bytes(b"operator-owned")
    (tmp_path / "state_5.sqlite-wal").write_bytes(b"synthetic-vendor-state")
    real = os.lstat

    def lstat(path, *args, **kwargs):
        if str(path).endswith("state_5.sqlite"):
            raise PermissionError(13, "synthetic: the database cannot be measured")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    left = login_home.take_back(
        str(tmp_path), LOGIN_SCRATCH, frozenset({"state_5.sqlite-wal"}))

    monkeypatch.undo()
    assert left == ("state_5.sqlite-wal",), "a measurement not taken was not counted as residue"
    assert (tmp_path / "state_5.sqlite-wal").exists()
    assert (tmp_path / "state_5.sqlite").read_bytes() == b"operator-owned"
