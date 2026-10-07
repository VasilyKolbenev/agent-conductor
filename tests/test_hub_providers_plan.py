"""The look a profile copy begins with, and the moves of the owner that outdate it (D-H3, R4).

`Supervisor.providers_plan` reads, in one hold of the lock, the status of a project, whether its
child may be started again, and the generation: the count of the owner's moves on the project
(activate, view, stop, forget). `restart_in_mode` refuses when the generation has moved since the
look, so a stop or a forget that came after the copy began is never undone by the restart, and a
child whose pipe the hub had already closed is never planned for one. The world is the supervisor
over fakes (`tests/_hub_world.py`); the operation itself is in `tests/test_hub_providers.py`.
"""
from __future__ import annotations

import pytest

from conductor.hub import supervisor
from tests._hub_world import PIDS, World, id_of
from tests.test_hub_providers import _ended, _gen, _listed_again, _running_child


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


def _again(world, name: str, mode: str, generation: int) -> bool:
    return world.supervisor.restart_in_mode(
        id_of(name), mode, root=world.roots[name], allowed=lambda: True, generation=generation)


def test_the_plan_of_a_serving_child_of_the_hubs_own_is_to_restart_it_in_its_mode(world):
    _running_child(world, "b", "view")
    plan = world.supervisor.providers_plan(id_of("b"))
    assert (plan.status.lifecycle.state, plan.status.mode, plan.restart) == (
        "running", "view", True)


def test_the_plan_of_a_process_the_hub_did_not_start_or_one_already_stopping_is_no_restart(world):
    world.running("c", mode="active")                         # no child of the hub's own
    plan = world.supervisor.providers_plan(id_of("c"))
    assert (plan.status.lifecycle.state, plan.restart) == ("running", False)
    _running_child(world, "b", "view")
    world.put_status("b", "stopping", mode="view")
    plan = world.supervisor.providers_plan(id_of("b"))
    assert (plan.status.lifecycle.state, plan.restart) == ("stopping", False)


def test_the_plan_of_a_project_nobody_listed_is_refused_project_not_found(world):
    with pytest.raises(supervisor.SupervisorRefused) as refused:
        world.supervisor.providers_plan("f" * 32)
    assert refused.value.code == "project_not_found"


def _stopped_by_the_owner(world):
    world.supervisor.stop(id_of("b"))


def _switched_away_from(world):
    world.supervisor.activate(id_of("c"))                     # the old active child is drained


def _the_hub_exits(world):
    world.supervisor.drain_all()


@pytest.mark.parametrize(("name", "mode", "way"), [
    ("b", "view", _stopped_by_the_owner), ("a", "active", _switched_away_from),
    ("b", "view", _the_hub_exits)], ids=["stop", "switch", "hub-exit"])
def test_the_plan_is_no_restart_once_the_hub_has_closed_the_pipe_of_the_child(
        world, name, mode, way):
    child = _running_child(world, name, mode)
    assert world.supervisor.providers_plan(id_of(name)).restart is True
    way(world)
    assert child.closed
    plan = world.supervisor.providers_plan(id_of(name))
    assert (plan.status.lifecycle.state, plan.restart) == ("running", False)   # the file lags


def test_a_child_that_never_came_to_serving_in_time_is_no_restart_once_its_pipe_is_closed(world):
    world.supervisor.view(id_of("b"))
    child = world.spawner.children[-1]
    world.alive.add(PIDS["b"])
    world.put_status("b", "starting", mode="view")
    assert world.supervisor.providers_plan(id_of("b")).restart is True
    world.clock.advance(supervisor.START_TIMEOUT_SECONDS + 1)
    world.supervisor.tick()
    plan = world.supervisor.providers_plan(id_of("b"))
    assert child.closed and plan.restart is False             # (its state says failed as well)


def test_a_child_started_after_an_earlier_one_was_stopped_is_a_restart_again(world):
    first = _running_child(world, "b", "view")
    world.supervisor.stop(id_of("b"))
    world.gone("b")
    second = _running_child(world, "b", "view")
    assert (first.closed, second.closed) == (True, False)
    assert world.supervisor.providers_plan(id_of("b")).restart is True


def _nothing_first(world):
    return None


def _a_serving_view_child(world):
    _running_child(world, "b", "view")


def _the_active_child_serving(world):
    _running_child(world, "a", "active")


def _the_active_childs_process_is_gone(world):
    _running_child(world, "a", "active")
    world.gone("a")


def _forget_and_list_again(world):
    world.supervisor.forget(id_of("a"))
    _listed_again(world, "a")


MOVES = [
    ("b", _nothing_first, lambda world: world.supervisor.view(id_of("b"))),
    ("b", _a_serving_view_child, lambda world: world.supervisor.stop(id_of("b"))),
    ("a", _the_active_child_serving, lambda world: world.supervisor.stop(id_of("a"))),
    ("a", _nothing_first, lambda world: world.supervisor.activate(id_of("a"))),
    ("a", _the_active_childs_process_is_gone, lambda world: world.supervisor.activate(id_of("a"))),
    ("a", _nothing_first, _forget_and_list_again)]


@pytest.mark.parametrize(("name", "first", "move"), MOVES, ids=[
    "view", "stop-a-view-child", "stop-the-active-child", "activate",
    "activate-the-active-project-whose-process-is-gone", "forget-and-list-again"])
def test_each_move_of_the_owner_adds_one_to_the_generation_of_its_project(
        world, name, first, move):
    first(world)
    before = _gen(world, name)
    move(world)
    assert _gen(world, name) == before + 1


@pytest.mark.parametrize("name", ["a", "b", "c"])
def test_a_move_on_another_project_leaves_the_generation_of_this_one_as_it_was(world, name):
    others = [other for other in "abc" if other != name]
    before = _gen(world, name)
    world.supervisor.view(id_of(others[0]))
    world.supervisor.forget(id_of(others[1]))
    assert _gen(world, name) == before


def _view_of_a_live_project(world):
    _running_child(world, "b", "view")
    return "b", lambda: world.supervisor.view(id_of("b")), "project_running"


def _stop_of_a_stopped_project(world):
    world.gone("b")
    return "b", lambda: world.supervisor.stop(id_of("b")), "project_not_running"


def _activate_of_the_live_active_project(world):
    _running_child(world, "a", "active")
    return "a", lambda: world.supervisor.activate(id_of("a")), "already_active"


def _forget_of_a_live_project(world):
    _running_child(world, "b", "view")
    return "b", lambda: world.supervisor.forget(id_of("b")), "project_running"


@pytest.mark.parametrize("refused_move", [
    _view_of_a_live_project, _stop_of_a_stopped_project, _activate_of_the_live_active_project,
    _forget_of_a_live_project])
def test_a_move_the_supervisor_refuses_leaves_the_generation_as_it_was(world, refused_move):
    name, act, code = refused_move(world)
    before = _gen(world, name)
    with pytest.raises(supervisor.SupervisorRefused) as refused:
        act()
    assert refused.value.code == code and _gen(world, name) == before


def test_restart_in_mode_refuses_once_the_owner_stopped_the_project_after_the_look(world):
    _running_child(world, "b", "view")
    looked = _gen(world, "b")                                 # the copy began here
    world.supervisor.stop(id_of("b"))                         # the owner's stop
    world.gone("b")
    assert _again(world, "b", "view", looked) is False
    assert len(world.spawner.started("b")) == 1
    assert _again(world, "b", "view", _gen(world, "b")) is True    # a fresh look says it may
    assert len(world.spawner.started("b")) == 2


def test_restart_in_mode_refuses_a_project_forgotten_and_listed_again_after_the_look(world):
    _ended(world, "b", "view")
    looked = _gen(world, "b")
    world.supervisor.forget(id_of("b"))
    _listed_again(world, "b")
    assert _again(world, "b", "view", looked) is False
    assert len(world.spawner.started("b")) == 1
    assert _again(world, "b", "view", _gen(world, "b")) is True
