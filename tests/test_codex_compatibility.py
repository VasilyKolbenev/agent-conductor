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
