"""A project opened for viewing never starts an agent (spec 4.3.1, 4.3.6, 12.10 day 8).

The guarantee sits on the runner, not on the page: a `ProcessRunner` built with
`spawns_allowed=False` refuses every `run` and `start` before it does anything else, so no
child exists, no ownership loan was claimed (a loan that is retired without proof would poison
the owner), and the refusal is the same `CommandSpecError` every unusable command gets.

This is the first slice of that section. What is here: the runner's refusal (with a control,
so a spy that sees nothing cannot pass), and a witness that a server launched with
`Launch(mode="view")` spawns nothing through task creation, the reads and the preview.

What that witness does NOT prove, and why its name says what it walks and not what it
guarantees: the mode does not gate spawning yet. `Launch.mode` reaches only the project
identity; the runner built at `command/providers.py` is still spawn-capable whatever the mode,
so the witness is green in `active` too. It says that today's walk starts no child, not that a
view process cannot start one. Also not here: the policy driver and the quota collector are
not gated by the mode, `--mode view` still refuses to start, and the routes that read git or
request a seed are lane L's.

The spec's own name for the witness (4.3.6) is kept for the day-8 version, which must (a) make
the mode reach the runner's construction site and (b) discriminate: assert that the runner the
flow reaches refuses to spawn, or add the control where the same flow does spawn in `active`
(authorize, then the driver). A green test under that name is read as the guarantee holding,
so it is not used before it is true.
"""
from __future__ import annotations

import subprocess
from threading import Thread

import pytest

from conductor import ownership, ownership_transition, server
from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.project_claim import Launch
from tests._fakeproc import fake_argv
from tests.test_command_http_api import TOKEN
from tests.test_policy_driver import ask
from tests.test_policy_runtime import NOW, PD, setup
from tests.test_server_command_http import _request
from tests.test_store import good_lane, write_project

REAL_POPEN = subprocess.Popen


class PopenSpy:
    """Counts every child the process starts, and starts it (a control needs a real one)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(tuple(args))
        return REAL_POPEN(*args, **kwargs)


@pytest.fixture
def spy(monkeypatch) -> PopenSpy:
    watcher = PopenSpy()
    monkeypatch.setattr(subprocess, "Popen", watcher)
    return watcher


def _spec() -> CommandSpec:
    return CommandSpec(argv=fake_argv(), cwd="work", timeout_seconds=10)


def _root(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    (root / "work").mkdir()
    return root


# -- the runner ----------------------------------------------------------------------


@pytest.mark.parametrize("door", ["run", "start"])
def test_a_runner_that_may_not_spawn_refuses_before_a_child_exists(tmp_path, spy, door):
    runner = ProcessRunner(_root(tmp_path), spawns_allowed=False)
    with pytest.raises(CommandSpecError, match="may not spawn"):
        getattr(runner, door)(_spec())
    assert spy.calls == [] and runner.active_tokens() == ()


def test_a_runner_that_may_spawn_still_does_through_the_same_spy(tmp_path, spy):
    runner = ProcessRunner(_root(tmp_path))
    assert runner.run(_spec()).status == "completed"
    assert len(spy.calls) == 1


def test_a_refused_spawn_claims_no_ownership_loan_and_leaves_the_owner_whole(tmp_path, spy):
    from tests._drain_harness import DrainProject
    root = DrainProject.build(tmp_path).root
    (root / "work").mkdir()
    owner = ownership.acquire_owner(root)
    try:
        runner = ProcessRunner(root, spawns_allowed=False)
        with pytest.raises(CommandSpecError):
            runner.run(_spec())
        owner.check()            # a loan retired without proof would say recovery_required
    finally:
        owner.release()          # and would refuse to let go while a loan stood
    assert spy.calls == []


# -- the first witness ---------------------------------------------------------------


def test_a_server_launched_for_viewing_spawns_no_child_through_task_creation_reads_and_preview(
        tmp_path, spy):
    """A task, the reads and the preview, walked on a server launched for viewing: no child.

    It holds for `Launch(mode="active")` as well, because the mode does not reach the runner
    yet (see the module docstring). What it pins is the walk: each step below answers as
    written, and the process starts nothing while it does.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    f = setup(root, two_steps=True, checker=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, registry=f.registry, clock=lambda: NOW,
                           ids=f.runtime._ids, token_factory=lambda _: TOKEN,
                           launch=Launch(mode="view"))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    # A registry given by hand has no installed provider configuration to judge.
    subject.command_api._policy.provider_digest = lambda config: PD
    subject.command_api._policy.provider_facts = None
    flow = [
        ("GET", "/command/session", None, 200),
        ("GET", "/command/tasks", None, 200),
        ("POST", "/command/tasks", {"task_id": "task-1", "title": "Look around"}, 201),
        ("GET", "/command/tasks/task-1", None, 200),
        ("GET", "/command/workflows", None, 200),
        ("GET", "/command/runs", None, 200),
        ("GET", "/command/runs/run", None, 200),
        ("GET", "/command/runs/run/controls", None, 200),
        ("GET", "/command/quotas", None, 200),
        ("GET", "/command/runs/run/automation", None, 200),
        ("POST", "/command/runs/run/automation/preview", ask(), 200),
    ]
    try:
        walked = []
        for method, path, body, expected in flow:
            status, payload, _ = _request(subject, method, path, body)
            walked.append((method, path, status))
            assert status == expected, (method, path, status, payload)
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(10)
    assert len(walked) == len(flow) and not thread.is_alive()
    assert spy.calls == [], f"a child was started: {spy.calls}"
