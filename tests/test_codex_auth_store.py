"""Every Codex spawn that reads the login is told to keep it in a file.

Codex 0.112.0 reads its login from `auth.json` or from the system keyring, by the config key
`cli_auth_credentials_store`, whose literals are `file`, `keyring`, `auto` and `ephemeral` (measured
on 23.10.2026; a wrong literal makes the config fail to load). The relay copies a FILE, so a login
kept in a keyring would be invisible to it and a status read that went to the keyring would answer
for a different login than the one the relay copies. The same key therefore rides every spawn that
could read the login: the sign-in a person runs, the status read, a task, a review, the checker and
the quota read. The version print reads no login and is left as it was.

The value half of a `-c` pair is parsed by the CLI as TOML, so it is the quoted string `"file"`, the
form the Codex review of 23.10.2026 measured (`login status`) and the same spelling as the
telemetry pairs. A shell eats the quotes of a command a person pastes; the product's own spawns do
not, because they are given an argument list.

The argv here is spelled out token by token. Reading it from the module's own constants would put
the same value on both sides of the comparison.
"""
from __future__ import annotations

import os
import pytest

from conductor.command.adapters import codex_cli
from conductor.command.adapters.codex_cli import CODEX_PROFILE, QUOTA_RPC
from conductor.command.providers import login_hint
from conductor.command.quota_plans import quota_plan_for

from tests import _fakecodex
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests.test_command_codex_review import _run as run_a_review
from tests.test_command_codex_transport import _task_row, a_harness, a_request, run_once
from tests.test_harness_subscription_login import a_codex_harness
from tests.test_independent_checker_transport import setup as a_cross_check
from tests.test_provider_setup import configure, menu_choice, pinned_files, project
from tests.test_subscription_quota import adapter as a_quota_adapter

__all__ = ["project"]

TELEMETRY_START = ["-c", "analytics.enabled=false"]


def store_stands_once_before_the_telemetry(argv):
    assert argv.count('cli_auth_credentials_store="file"') == 1, argv
    at = argv.index('cli_auth_credentials_store="file"')
    assert argv[at - 1] == "-c", argv
    assert argv[at + 1:at + 3] == TELEMETRY_START, argv


def test_the_constants_a_person_and_the_transport_read():
    assert codex_cli.LOGIN_ARGV == ("-c", 'cli_auth_credentials_store="file"', "login")
    assert codex_cli.LOGIN_STATUS_ARGV == (
        "-c", 'cli_auth_credentials_store="file"', "login", "status")
    assert codex_cli.VERSION_ARGV == ("--version",)
    assert QUOTA_RPC.argv == ("-c", 'cli_auth_credentials_store="file"', "app-server")


def test_the_profile_asks_and_prints_the_same_two_commands():
    """One place for the wizard that prints the sign-in and the receipt that asks for status."""
    assert CODEX_PROFILE.login_command == ("-c", 'cli_auth_credentials_store="file"', "login")
    assert CODEX_PROFILE.login_argv == (
        "-c", 'cli_auth_credentials_store="file"', "login", "status")
    assert login_hint("codex-headless-v1") == (
        "CODEX_HOME", ("-c", 'cli_auth_credentials_store="file"', "login"))


def test_the_wizard_prints_the_sign_in_that_keeps_the_login_in_a_file(
        project, tmp_path, capsys):
    from conductor.provider_setup import _login_lines

    executable, _ = pinned_files(tmp_path, "codex")
    home = tmp_path / "DecemberCommand" / "logins" / "codex"  # where a relay is derived from

    assert configure(project, menu_choice("codex"), str(executable), "1", str(home), "", "y") == 0

    said = capsys.readouterr().err
    for line in _login_lines(
            str(home), str(executable),
            ("CODEX_HOME", ("-c", 'cli_auth_credentials_store="file"', "login"))):
        assert line in said, said
    # A person pastes this command into the platform shell. Native transport argv
    # uses the unescaped literal and is checked separately below.
    suffix = (r' --% -c cli_auth_credentials_store=\"file\" login' if os.name == "nt"
              else """ -c 'cli_auth_credentials_store="file"' login""")
    assert any(line.endswith(suffix) for line in said.splitlines())


def test_a_task_spawn_carries_the_store_once_ahead_of_the_telemetry_pairs(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    store_stands_once_before_the_telemetry(_task_row(log)["argv"])


def test_a_review_spawn_carries_it_too(tmp_path):
    _attempt, _store, _adapter, _seed, log, _root = run_a_review(tmp_path)

    (row,) = _fakecodex.task_spawns(log)

    store_stands_once_before_the_telemetry(row["argv"])
    assert "read-only" in row["argv"]


@pytest.mark.usefixtures("boundary_assumed")
def test_the_checker_spawn_carries_it_too(tmp_path):
    from conductor.command.runtime import AttemptState

    runtime, authorization, _store, _doer, _checker, _log, check_log, _root = a_cross_check(
        tmp_path, cross=True)

    assert runtime.execute(authorization).state is AttemptState.SUCCEEDED
    (row,) = _fakecodex.task_spawns(check_log)

    store_stands_once_before_the_telemetry(row["argv"])
    assert "read-only" in row["argv"] and "checker-model" in row["argv"]


def test_the_status_read_and_the_version_print_are_what_they_should_be(tmp_path):
    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    adapter, _root, log = a_codex_harness(tmp_path, auth="subscription", auth_home=str(home))

    run_once(adapter, a_request())

    rows = _fakecodex.spawns(log)
    asked = [row["argv"] for row in rows if _fakecodex.login_question(row["argv"])]
    assert asked == [["-c", 'cli_auth_credentials_store="file"', "login", "status"]]
    assert [row["argv"] for row in rows if row["argv"][-1] == "--version"] == [["--version"]]


def test_the_quota_read_asks_the_app_server_with_the_store_and_the_version_without(tmp_path):
    value, runner, _home = a_quota_adapter(tmp_path)
    plan = quota_plan_for("bound-provider", value)

    plan.request.read()

    argvs = [list(spec.argv[1:]) for spec in runner.specs]
    assert argvs == [["--version"], ["-c", 'cli_auth_credentials_store="file"', "app-server"]]
