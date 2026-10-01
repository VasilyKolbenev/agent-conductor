"""Pinned GitHub reads disclose only typed public account/repository facts."""
import json
from dataclasses import replace

import pytest

from conductor import tool_pins
from conductor.command.adapters.process import ProcessOutcome
from conductor.hub.github import Github, FIELDS, LOGIN_COMMAND
from conductor.hub.refusals import HubRefusal
from tests.test_hub_http_surface import stack  # noqa: F401


def outcome(data=b"octocat\n", **changes):
    return replace(ProcessOutcome("completed", 0, data, False, 1024 * 1024,
                                  1, "test-process"), **changes)


@pytest.fixture
def reader(tmp_path, monkeypatch):
    home = tmp_path / "hub"
    home.mkdir()
    pin = tool_pins.ToolPin("gh", str(tmp_path / "gh.exe"), "2.70.0")
    monkeypatch.setattr(tool_pins, "load_pins", lambda _home: tool_pins.ToolPins(gh=pin))
    calls, checks, replies = [], [], [outcome()]
    def run(spec):
        calls.append(spec)
        return replies.pop(0)
    def verify(*args, **kwargs):
        checks.append((args, kwargs))
        return pin
    api = Github(home, run=run, verify=verify,
                 source={"GH_TOKEN": "do-not-forward", "GH_HOST": "evil.example"})
    return api, calls, checks, replies


def test_account_read_uses_pinned_binary_and_the_common_clean_environment(reader):
    api, calls, checks, replies = reader
    assert api.status() == {"state": "ok", "login": "octocat", "login_command": None}
    spec = calls[0]
    assert spec.argv[1:] == ("api", "user", "--jq", ".login")
    assert "GH_TOKEN" not in spec.env and "GH_HOST" not in spec.env
    assert spec.timeout_seconds == 15 and spec.output_limit == 1024 * 1024
    assert spec.separate_stderr and spec.stdin_bytes is None
    replies.append(outcome())
    api.status()
    assert len(checks) == 1


@pytest.mark.parametrize("reply,code", [
    (outcome(exit_code=4), "gh_not_logged_in"),
    (outcome(status="timed_out", exit_code=None), "gh_unreachable"),
    (outcome(output_truncated=True), "gh_failed"),
    (outcome(exit_code=1), "gh_failed"),
    (outcome(data=b"\xff"), "gh_failed"),
])
def test_failures_are_typed_without_child_text_or_credentials(reader, reply, code):
    api, _calls, _checks, replies = reader
    replies[:] = [reply, reply]
    status = api.status()
    assert status == {"state": code[3:], "login": None,
                      "login_command": LOGIN_COMMAND if code == "gh_not_logged_in" else None}
    with pytest.raises(HubRefusal) as caught:
        api.repositories()
    assert caught.value.code == code


def test_repository_list_is_bounded_typed_and_owner_is_one_argument(reader):
    api, calls, _checks, replies = reader
    row = dict(nameWithOwner="octocat/app", description="<b>" + "x" * 250,
               visibility="PRIVATE", updatedAt="2026-09-30T12:00:00Z", isArchived=False, isFork=True)
    replies[:] = [outcome(json.dumps([row] * 200).encode())]
    result = api.repositories("octocat")
    assert result["owner"] == "octocat" and result["truncated"] is True
    assert len(result["repos"]) == 200 and len(result["repos"][0]["description"]) == 200
    assert result["repos"][0]["visibility"] == "private"
    assert calls[0].argv[1:] == ("repo", "list", "--limit", "200", "--json", FIELDS, "--", "octocat")
    for owner in ("--help", "a/b", "x\n--flag"):
        with pytest.raises(HubRefusal, match="contract_invalid"):
            api.repositories(owner)
    assert len(calls) == 1


def test_bad_repo_rows_cannot_become_ui_facts(reader):
    api, _calls, _checks, replies = reader
    for raw in (b"{}", b"[null]", b"[{\"nameWithOwner\":\"bad\"}]", b"[{}]" * 201):
        replies[:] = [outcome(raw)]
        with pytest.raises(HubRefusal) as caught:
            api.repositories()
        assert caught.value.code == "gh_failed"


@pytest.mark.parametrize("code", ["gh_not_pinned", "gh_changed"])
def test_unconfirmed_tool_never_starts_and_does_not_disclose_pin_path(reader, code):
    api, calls, _checks, _replies = reader
    def refused(*_args, **_kwargs):
        raise tool_pins.ToolPinError(code, "C:/private/pin/path")
    api.verify = refused
    assert api.status() == {"state": code[3:], "login": None, "login_command": None}
    assert calls == []


def test_http_github_routes_use_service_and_preserve_no_path_response(stack, reader):
    api, _calls, _checks, replies = reader
    stack.service._github = api
    assert stack.get("/hub/github/status").json()["login"] == "octocat"
    replies[:] = [outcome(b"[]"), outcome(b"[]")]
    assert stack.get("/hub/github/repos").json() == {"owner": None, "repos": [], "truncated": False}
    assert stack.get("/hub/github/repos/octocat").json()["owner"] == "octocat"
