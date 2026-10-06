"""The routes lane H makes live, over a real socket on the world of fakes (spec 4.6.3, 4.6.4).

`POST /hub/projects/<id>/recover`, `POST /hub/projects/<id>/providers`,
`POST /hub/logins/<key>/recover` and `POST /hub/tools/<tool>/pin` each answer in the closed forms
of the table, refuse before anything is written, and put no path and no text of a command in an
answer. The owner command is the one fake of `Command` below: what it prints and what it leaves
behind (the ownership head) are the only two things a test says about it.
"""
from __future__ import annotations

import json
import re
import time

import pytest

from conductor.command import operator_config
from tests._hub_stack import A, B, Stack
from tests.test_hub_owner_command import fake
from tests.test_login_recovery_prepare import legacy_lease
from tests.test_provider_profile import config

RECOVERED = json.dumps({"phase": "recovered"})


class Command:
    """The fake owner command of a stack: a test says what it prints and what it leaves behind."""

    def __init__(self) -> None:
        self.out, self.err, self.code = RECOVERED, "", 0
        self.seen: list[list[str]] = []
        self.leaves: tuple[str, str] | None = None      # (project name, head) set as it runs
        self.world = None

    def __call__(self, argv, **kwargs):
        self.seen.append(list(argv))
        if self.leaves is not None:
            self.world.heads[self.leaves[0]] = self.leaves[1]
        return fake(out=self.out, err=self.err, code=self.code)(argv, **kwargs)


@pytest.fixture
def stack(tmp_path):
    command = Command()
    made = Stack(tmp_path, owner_popen=command)
    command.world, made.command = made.world, command
    yield made
    made.close()


def _envelope(reply) -> dict:
    body = reply.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "detail"}
    return body["error"]


def _code(reply, status: int) -> str:
    assert reply.status == status, (reply.status, reply.body[:200])
    return _envelope(reply)["code"]


def _refused_and_unchanged(stack, target: str, status: int, code: str, body=None) -> None:
    before = stack.state_bytes()
    calls, launched = len(stack.world.spawner.calls), len(stack.command.seen)
    assert _code(stack.post(target, body), status) == code, target
    assert stack.state_bytes() == before, f"{code} changed hub-state.json"
    assert len(stack.world.spawner.calls) == calls
    assert len(stack.command.seen) == launched, f"{code} still ran an owner command"


def _row(stack, project_id: str) -> dict:
    rows = stack.get("/hub/projects").json()["projects"]
    return next(row for row in rows if row["project_id"] == project_id)


def _settled(stack, ident: str) -> dict:
    """The row of an operation once it left `running` (polled for at most 5 s)."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        found = stack.get(f"/hub/operations/{ident}").json()
        if found["state"] != "running":
            return found
        time.sleep(0.01)
    raise AssertionError("the operation did not settle")


# -- POST /hub/projects/<project_id>/recover -------------------------------------------------------

def test_recover_answers_202_and_the_row_reads_stopped_once_the_command_left_the_head_recovered(
        stack):
    stack.world.gone("a", "stop_uncertain", head="opened")
    assert _row(stack, A)["state"] == "stop_uncertain"
    stack.command.leaves = ("a", "recovered")
    reply = stack.post(f"/hub/projects/{A}/recover")
    assert reply.status == 202 and set(reply.json()) == {"operation_id"}
    row = _settled(stack, reply.json()["operation_id"])
    assert (row["kind"], row["state"], row["project_id"]) == ("recover", "succeeded", A)
    assert _row(stack, A)["state"] == "stopped"
    assert stack.command.seen[0][3:] == ["ownership", "recover", "--dir", stack.world.roots["a"]]


def test_a_recovery_that_the_command_refused_leaves_the_project_asking_for_one(stack):
    stack.world.gone("a", "stop_uncertain", head="opened")
    stack.command.code, stack.command.out = 1, ""
    stack.command.err = "recovery_required: restart the OS before recovering a writer\n"
    row = _settled(stack, stack.post(f"/hub/projects/{A}/recover").json()["operation_id"])
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "recovery_required", {"reason": "restart_needed"})
    assert _row(stack, A)["state"] == "stop_uncertain"


def test_recover_refuses_by_the_rules_of_the_table_and_changes_nothing(stack):
    _refused_and_unchanged(stack, f"/hub/projects/{'f' * 32}/recover", 404, "project_not_found")
    stack.world.running("a")
    _refused_and_unchanged(stack, f"/hub/projects/{A}/recover", 409, "project_running")
    stack.world.gone("b")
    _refused_and_unchanged(stack, f"/hub/projects/{B}/recover", 409, "recover_not_needed")


def test_a_project_with_a_running_operation_refuses_every_other_move_project_busy_first(stack):
    # Project A is stopped with a closed head, so each move below would otherwise be judged by its
    # own rules (`recover` would be `recover_not_needed`): the busy refusal comes FIRST.
    stack.world.gone("a")
    stack.service._operations.open_project_row("recover", A, "recover")   # stays running
    for target in ("activate", "view", "stop", "forget", "recover"):
        _refused_and_unchanged(stack, f"/hub/projects/{A}/{target}", 409, "project_busy")
    stack.world.gone("b")
    assert stack.post(f"/hub/projects/{B}/view").status == 202           # another project is free


def test_a_hub_that_is_closing_refuses_a_new_recovery_and_starts_no_command(stack):
    stack.world.gone("a", "stop_uncertain", head="opened")
    stack.service.close_operations()
    _refused_and_unchanged(stack, f"/hub/projects/{A}/recover", 409, "project_busy")


def test_no_answer_of_a_recovery_holds_a_path_or_a_word_the_command_printed(stack):
    stack.world.gone("a", "stop_uncertain", head="opened")
    stack.command.code, stack.command.out = 1, ""
    stack.command.err = f"recovery_refused: {stack.world.roots['a']} is somewhere\n"
    reply = stack.post(f"/hub/projects/{A}/recover")
    row = _settled(stack, reply.json()["operation_id"])
    assert row["code"] == "recovery_refused"
    for body in (reply.body, json.dumps(row).encode("utf-8"),
                 stack.get("/hub/projects").body, stack.get("/hub/setup").body):
        assert stack.world.roots["a"].encode("utf-8") not in body
        assert b"is somewhere" not in body


# -- GET /hub/setup: the logins ----------------------------------------------------------------


def _name_a_login(stack, tmp_path, monkeypatch, *, leased: bool):
    """Put one login folder in the shared profile; with a lease record nobody closed if asked."""
    if leased:
        login, box, _record = legacy_lease(tmp_path, monkeypatch, name="a-distinctive-login")
    else:
        login = tmp_path / "a-distinctive-login"
        login.mkdir()
        box = None
    operator_config.save_provider_configs(
        stack.world.home / "providers.json", [config(tmp_path, "claude-code", login=login)])
    return login, box


def test_the_setup_lists_the_logins_of_the_profile_in_their_public_form_and_no_path(
        stack, tmp_path, monkeypatch):
    login, _box = _name_a_login(stack, tmp_path, monkeypatch, leased=False)
    reply = stack.get("/hub/setup")
    (entry,) = reply.json()["logins"]
    assert set(entry) == {"login_key", "harness", "used_by", "state"}
    assert (entry["harness"], entry["used_by"], entry["state"]) == ("claude-code", [], "free")
    assert re.fullmatch(r"[0-9a-f]{64}", entry["login_key"])
    assert b"a-distinctive-login" not in reply.body and str(login).encode() not in reply.body


def test_a_login_with_a_lease_nobody_closed_reads_unclosed_in_the_setup(
        stack, tmp_path, monkeypatch):
    _name_a_login(stack, tmp_path, monkeypatch, leased=True)
    assert [row["state"] for row in stack.get("/hub/setup").json()["logins"]] == ["unclosed"]


def test_a_hub_state_nobody_can_read_leaves_the_login_in_use_and_offers_no_action(
        stack, tmp_path, monkeypatch):
    _name_a_login(stack, tmp_path, monkeypatch, leased=True)
    (stack.world.home / "hub-state.json").write_bytes(b"{not json")
    assert [row["state"] for row in stack.get("/hub/setup").json()["logins"]] == ["in_use"]


def test_a_registry_nobody_can_read_leaves_the_setup_answering_with_no_logins(
        stack, tmp_path, monkeypatch):
    _name_a_login(stack, tmp_path, monkeypatch, leased=True)
    (stack.world.home / "registry.json").write_text("{not json", encoding="utf-8")
    reply = stack.get("/hub/setup")
    assert reply.status == 200 and reply.json()["logins"] == []
