"""The `registry_invalid` rows the closed list of 7 October added, each reached over a real socket.

A file the hub cannot read (`registry.json`, `hub-state.json`) is `409 registry_invalid` on the two
reads and on the writes whose handler reads it: stop, recover, providers, forget, the projects
home and the queue order. Every scenario holds the same four facts: the answer names the file the
handler read (or no file, where it names none), the unreadable file is byte for byte as it was,
no child was started, and no owner command ran. `activate` and `view` (hub state) are held in
`test_hub_http_surface.py`, the registry read of `GET /hub/projects` there too, `project_busy` of
`forget` and `operation_busy` of the login recovery in `test_hub_handlers_http.py` and
`operation_busy` of the projects home in `test_hub_new_projects.py`.
"""
from __future__ import annotations

import pytest

from conductor.command import operator_config
from tests._hub_stack import A, Stack
from tests.test_provider_profile import config

BROKEN = b"{not json"


@pytest.fixture
def stack(tmp_path):
    launched: list[list[str]] = []

    def popen(argv, **_options):
        launched.append(list(argv))
        raise AssertionError("a refused move ran an owner command")

    made = Stack(tmp_path, owner_popen=popen)
    made.launched = launched
    yield made
    made.close()


def _envelope(reply) -> dict:
    body = reply.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "detail"}
    return body["error"]


def _damage(stack, name: str):
    """Make one file of the hub's folder one nobody can read; return its path."""
    path = stack.world.home / name
    path.write_bytes(BROKEN)
    return path


def _nothing_else_happened(stack, path, capsys) -> None:
    assert path.read_bytes() == BROKEN, "the unreadable file was written over"
    assert stack.world.spawner.calls == [], "a child was started on a file nobody could read"
    assert stack.launched == [], "an owner command ran on a file nobody could read"
    assert "Traceback" not in capsys.readouterr().err


# -- the writes on a project -------------------------------------------------------------------

MOVES = [("stop", "registry.json"), ("stop", "hub-state.json"),
         ("recover", "registry.json"),
         ("providers", "registry.json"), ("providers", "hub-state.json"),
         ("forget", "registry.json"), ("forget", "hub-state.json")]


@pytest.mark.parametrize(("route", "name"), MOVES)
def test_a_project_move_on_a_file_nobody_can_read_is_409_registry_invalid_and_writes_nothing(
        stack, capsys, route, name):
    if route == "providers":                  # a profile is judged before the state is read
        operator_config.save_provider_configs(
            stack.world.home / "providers.json", [config(stack.world.home.parent, "claude-code")])
    stack.world.gone("a")
    path = _damage(stack, name)
    reply = stack.post(f"/hub/projects/{A}/{route}")
    assert reply.status == 409, (reply.status, reply.body[:200])
    error = _envelope(reply)
    assert (error["code"], error["detail"]) == ("registry_invalid", {"file": name})
    _nothing_else_happened(stack, path, capsys)


def test_a_queue_order_on_a_hub_state_nobody_can_read_is_409_registry_invalid(stack, capsys):
    path = _damage(stack, "hub-state.json")
    reply = stack.post("/hub/queue/order", {"order": []})
    assert reply.status == 409, (reply.status, reply.body[:200])
    error = _envelope(reply)
    assert (error["code"], error["detail"]) == ("registry_invalid", {"file": "hub-state.json"})
    _nothing_else_happened(stack, path, capsys)


def test_the_projects_home_on_a_registry_nobody_can_read_is_409_registry_invalid(stack, capsys):
    path = _damage(stack, "registry.json")
    reply = stack.post("/hub/setup/projects-home", {"default": True})
    assert reply.status == 409, (reply.status, reply.body[:200])
    assert _envelope(reply)["code"] == "registry_invalid"
    _nothing_else_happened(stack, path, capsys)


# -- the two reads -----------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["/hub/projects", "/hub/limits"])
def test_a_read_on_a_hub_state_nobody_can_read_is_409_registry_invalid(stack, capsys, target):
    path = _damage(stack, "hub-state.json")
    reply = stack.get(target)
    assert reply.status == 409, (reply.status, reply.body[:200])
    error = _envelope(reply)
    assert (error["code"], error["detail"]) == ("registry_invalid", {"file": "hub-state.json"})
    _nothing_else_happened(stack, path, capsys)
