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
import threading
import time

import pytest

from conductor.command import operator_config
from tests._hub_stack import A, B, Stack
from tests.test_hub_owner_command import Running, fake
from tests.test_login_recovery_prepare import legacy_lease
from tests.test_provider_profile import config

RECOVERED = json.dumps({"phase": "recovered"})
LOGIN_RECOVERED = json.dumps({"state": "recovered", "resource": "sha256:ab"})


class Command:
    """The fake owner command of a stack: a test says what it prints and what it leaves behind.

    `leaves` is `(project name, head)` set as the command runs, `on_run` is anything else it
    leaves, and a command with a `release` event runs on until the test sets it.
    """

    def __init__(self) -> None:
        self.out, self.err, self.code = RECOVERED, "", 0
        self.seen: list[list[str]] = []
        self.leaves: tuple[str, str] | None = None
        self.on_run = None
        self.release: threading.Event | None = None
        self.world = None

    def __call__(self, argv, **kwargs):
        self.seen.append(list(argv))
        if self.leaves is not None:
            self.world.heads[self.leaves[0]] = self.leaves[1]
        if self.on_run is not None:
            self.on_run()
        process = fake(out=self.out, err=self.err, code=self.code)(argv, **kwargs)
        return process if self.release is None else Running(process, self.release)


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
    for target in ("activate", "view", "stop", "forget", "recover", "providers"):
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


# -- POST /hub/logins/<login_key>/recover ----------------------------------------------------------


def _leased_login(stack, tmp_path, monkeypatch):
    """A login folder of the profile whose lease record nobody closed: `(folder, box, key)`."""
    login, box = _name_a_login(stack, tmp_path, monkeypatch, leased=True)
    (entry,) = stack.get("/hub/setup").json()["logins"]
    return login, box, entry["login_key"]


def _wait_until(condition) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "the condition never held"
        time.sleep(0.01)


def _the_lease_is_retired_as_the_command_runs(box):
    return lambda: (box / "active.json").rename(box / "recovered-test.json")


def test_a_login_recovery_passes_the_folder_the_hub_found_and_no_row_holds_a_path(
        stack, tmp_path, monkeypatch):
    login, box, key = _leased_login(stack, tmp_path, monkeypatch)
    stack.command.out = LOGIN_RECOVERED
    stack.command.on_run = _the_lease_is_retired_as_the_command_runs(box)
    reply = stack.post(f"/hub/logins/{key}/recover")
    assert reply.status == 202 and set(reply.json()) == {"operation_id"}
    row = _settled(stack, reply.json()["operation_id"])
    assert stack.command.seen[0][3:] == ["ownership", "recover-login", "--auth-home",
                                         str(login.resolve())]
    assert (row["kind"], row["step"], row["project_id"], row["source"]) == (
        "recover_login", "recover_login", None, None)
    assert (row["state"], row["code"], row["detail"], row["result"]) == (
        "succeeded", None, None, None)
    assert b"a-distinctive-login" not in json.dumps(row).encode("utf-8") + reply.body
    assert [one["state"] for one in stack.get("/hub/setup").json()["logins"]] == ["free"]


def test_an_unknown_key_is_login_not_found_and_changes_nothing(stack, tmp_path, monkeypatch):
    _leased_login(stack, tmp_path, monkeypatch)
    _refused_and_unchanged(stack, "/hub/logins/" + "ab" * 32 + "/recover", 404,
                           "login_not_found")


def test_a_box_with_no_lease_record_is_recover_not_needed(stack, tmp_path, monkeypatch):
    _name_a_login(stack, tmp_path, monkeypatch, leased=False)
    (entry,) = stack.get("/hub/setup").json()["logins"]
    _refused_and_unchanged(stack, f"/hub/logins/{entry['login_key']}/recover", 409,
                           "recover_not_needed")


def test_a_box_an_active_child_may_hold_is_recover_not_needed(stack, tmp_path, monkeypatch):
    _login, _box, key = _leased_login(stack, tmp_path, monkeypatch)
    stack.world.running("a", mode="active")
    assert [one["state"] for one in stack.get("/hub/setup").json()["logins"]] == ["in_use"]
    _refused_and_unchanged(stack, f"/hub/logins/{key}/recover", 409, "recover_not_needed")


def test_a_hub_state_nobody_can_read_makes_a_login_recovery_not_needed_not_offered(
        stack, tmp_path, monkeypatch):
    _login, _box, key = _leased_login(stack, tmp_path, monkeypatch)
    (stack.world.home / "hub-state.json").write_bytes(b"{not json")
    _refused_and_unchanged(stack, f"/hub/logins/{key}/recover", 409, "recover_not_needed")


@pytest.mark.parametrize(("err", "code", "reason"), [
    ("login_recovery_required: restart the OS before recovering the shared login lease "
     "(do a full Restart, not a shutdown)\n", "login_recovery_required", "restart_needed"),
    ("login_recovery_required: the lease predates the boot counter and cannot prove a "
     "restart; run `ownership recover-login --prepare-restart`\n", "login_recovery_required",
     "prepare_needed"),
    ("login_recovery_required: no restart is proven: x\n", "login_recovery_required",
     "not_proven"),
    ("login_owner_busy: x\n", "login_owner_busy", None),
    ("login_ownership_invalid: x\n", "login_ownership_invalid", None),
    ("login_context_required: x\n", "login_context_required", None),
    ("recovery_refused: x\n", "subprocess_failed", None)])
def test_a_refused_login_recovery_ends_failed_with_its_code_and_the_reason_of_a_restart_code(
        stack, tmp_path, monkeypatch, err, code, reason):
    login, _box, key = _leased_login(stack, tmp_path, monkeypatch)
    stack.command.code, stack.command.out, stack.command.err = 1, "", err
    row = _settled(stack, stack.post(f"/hub/logins/{key}/recover").json()["operation_id"])
    assert (row["state"], row["code"]) == ("failed", code)
    assert row["detail"] == (None if reason is None else {"reason": reason})
    assert "prepare" not in " ".join(arg for argv in stack.command.seen for arg in argv)
    assert str(login).encode("utf-8") not in json.dumps(row).encode("utf-8")


def test_a_second_login_recovery_of_the_same_key_answers_the_operation_already_running(
        stack, tmp_path, monkeypatch):
    _login, box, key = _leased_login(stack, tmp_path, monkeypatch)
    stack.command.out, stack.command.release = LOGIN_RECOVERED, threading.Event()
    stack.command.on_run = _the_lease_is_retired_as_the_command_runs(box)
    first = stack.post(f"/hub/logins/{key}/recover")
    _wait_until(lambda: len(stack.command.seen) == 1)       # the command runs; its lease is gone
    again = stack.post(f"/hub/logins/{key}/recover")
    assert (first.status, again.status) == (202, 202)
    assert again.json()["operation_id"] == first.json()["operation_id"]
    assert len(stack.command.seen) == 1
    stack.command.release.set()
    assert _settled(stack, first.json()["operation_id"])["state"] == "succeeded"
    _refused_and_unchanged(stack, f"/hub/logins/{key}/recover", 409, "recover_not_needed")


def test_a_login_recovery_runs_beside_a_project_operation_and_an_add(
        tmp_path, monkeypatch):
    from conductor.hub import operations
    adding = Command()
    adding.release, adding.out = threading.Event(), ""
    command = Command()
    made = Stack(tmp_path, owner_popen=command, operation_popen=adding)
    command.world = made.world
    command.out = LOGIN_RECOVERED
    try:
        _login, box = _name_a_login(made, tmp_path, monkeypatch, leased=True)
        command.on_run = _the_lease_is_retired_as_the_command_runs(box)
        key = made.get("/hub/setup").json()["logins"][0]["login_key"]
        made.service._operations.open_project_row("recover", A, "recover")     # stays running
        made.service._operations.begin(operations.FolderPick(str(tmp_path / "x"), "none"),
                                       "x", True)                              # an add runs on
        reply = made.post(f"/hub/logins/{key}/recover")
        assert reply.status == 202
        assert _settled(made, reply.json()["operation_id"])["state"] == "succeeded"
    finally:
        adding.release.set()
        made.close()


def test_the_setup_says_so_when_a_login_recovery_has_ended_and_the_box_changed(
        stack, tmp_path, monkeypatch):
    _login, box, key = _leased_login(stack, tmp_path, monkeypatch)
    mailbox = stack.bus.register()
    stack.tick()                                            # the baseline of the loop
    mailbox.drain()
    stack.command.out = LOGIN_RECOVERED
    stack.command.on_run = _the_lease_is_retired_as_the_command_runs(box)
    ident = stack.post(f"/hub/logins/{key}/recover").json()["operation_id"]
    _settled(stack, ident)
    stack.tick()
    frames = [json.loads(chunk[len(b"data: "):]) for chunk in mailbox.drain()]
    assert {"kind": "setup"} in frames
    assert {"kind": "operation", "operation_id": ident} in frames


def test_a_hub_that_is_closing_refuses_a_new_login_recovery_and_starts_no_command(
        stack, tmp_path, monkeypatch):
    _login, _box, key = _leased_login(stack, tmp_path, monkeypatch)
    stack.service.close_operations()
    _refused_and_unchanged(stack, f"/hub/logins/{key}/recover", 409, "operation_busy")


# -- POST /hub/projects/<project_id>/providers -------------------------------------------------

COPIED = {"folder": None, "activated": None, "providers": "copied", "git": None, "exclude": None,
          "exclude_names": None, "agent_instructions": None, "projects_home_created": None}


def _a_profile(stack, tmp_path) -> None:
    operator_config.save_provider_configs(
        stack.world.home / "providers.json", [config(tmp_path, "claude-code")])


def _a_running_child(stack, name: str = "a", mode: str = "active"):
    world = stack.world
    if mode == "active":
        world.supervisor.activate(name * 32)
        world.supervisor.tick()
    else:
        world.supervisor.view(name * 32)
    world.running(name, mode=mode)
    return world.spawner.children[-1]


def test_providers_for_a_stopped_project_answers_202_copies_and_starts_nothing(stack, tmp_path):
    _a_profile(stack, tmp_path)
    stack.world.gone("a")
    before = stack.state_bytes()
    reply = stack.post(f"/hub/projects/{A}/providers")
    assert reply.status == 202 and set(reply.json()) == {"operation_id"}
    row = _settled(stack, reply.json()["operation_id"])
    assert (row["kind"], row["step"], row["state"], row["project_id"]) == (
        "providers", "providers", "succeeded", A)
    assert row["result"] == COPIED and row["code"] is None and row["detail"] is None
    assert stack.command.seen[0][3:] == ["providers", "--dir", stack.world.roots["a"],
                                         "--from-profile"]
    assert stack.state_bytes() == before and stack.world.spawner.calls == []
    assert stack.world.roots["a"].encode("utf-8") not in json.dumps(row).encode("utf-8")


def test_providers_refuses_an_absent_or_invalid_profile_before_draining_anything(
        stack, tmp_path):
    child = _a_running_child(stack)
    for text in (None, "{not json", json.dumps({"schema_version": 1, "providers": "nope"})):
        profile = stack.world.home / "providers.json"
        if text is None:
            profile.unlink(missing_ok=True)
        else:
            profile.write_text(text, encoding="utf-8")
        _refused_and_unchanged(stack, f"/hub/projects/{A}/providers", 409,
                               "profile_absent" if text is None else "profile_invalid")
        assert child.closed is False
        assert stack.service._operations.running_for(A) is None


def test_providers_refuses_an_unknown_project_and_one_with_an_operation_running(stack, tmp_path):
    _a_profile(stack, tmp_path)
    _refused_and_unchanged(stack, f"/hub/projects/{'f' * 32}/providers", 404, "project_not_found")
    stack.world.gone("a")
    stack.service._operations.open_project_row("recover", A, "recover")       # stays running
    _refused_and_unchanged(stack, f"/hub/projects/{A}/providers", 409, "project_busy")


@pytest.mark.parametrize("mode", ["active", "view"])
def test_providers_for_a_running_project_drains_copies_and_starts_it_again_in_its_mode(
        stack, tmp_path, mode):
    _a_profile(stack, tmp_path)
    name = "a" if mode == "active" else "b"
    child = _a_running_child(stack, name, mode)
    before = stack.state_bytes()
    ident = stack.post(f"/hub/projects/{name * 32}/providers").json()["operation_id"]
    _wait_until(lambda: child.closed)
    assert stack.command.seen == []                       # the copy waits for the drain to end
    stack.world.gone(name, "stopped", head="closed")
    _wait_until(lambda: stack.get(f"/hub/operations/{ident}").json()["step"] == "start")
    stack.tick()                                          # the loop's own pass starts an active one
    stack.world.running(name, mode=mode)
    row = _settled(stack, ident)
    assert (row["state"], row["step"], row["result"]) == ("succeeded", "start", COPIED)
    starts = stack.world.spawner.started(name)
    assert len(starts) == 2 and starts[-1]["mode"] == mode
    assert (starts[-1]["transition"], starts[-1]["auto_continue"]) == (None, None)
    assert stack.state_bytes() == before


def test_a_child_that_was_already_stopping_is_drained_and_copied_and_not_brought_back(
        stack, tmp_path):
    _a_profile(stack, tmp_path)
    child = _a_running_child(stack, "a", "active")
    stack.world.put_status("a", "stopping")
    ident = stack.post(f"/hub/projects/{A}/providers").json()["operation_id"]
    _wait_until(lambda: child.closed)
    stack.world.gone("a", "stopped", head="closed")
    row = _settled(stack, ident)
    stack.tick()
    assert (row["state"], row["result"]) == ("succeeded", COPIED)
    assert len(stack.world.spawner.started("a")) == 1


def test_a_hub_that_is_closing_refuses_a_profile_copy_and_starts_no_command(stack, tmp_path):
    _a_profile(stack, tmp_path)
    stack.world.gone("a")
    stack.service.close_operations()
    _refused_and_unchanged(stack, f"/hub/projects/{A}/providers", 409, "project_busy")
