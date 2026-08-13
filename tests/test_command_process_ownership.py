"""Process ownership: the runner stops only a child it started and still holds.

This is the foreign-PID sabotage class. The relation is token identity, not a
PID: `start` mints an unguessable token bound to the exact child handle, and
`stop` terminates only what a live token names. There is no method that accepts
a PID, so a foreign or recycled PID cannot even be expressed -- and a token
whose child has finished is refused, so a PID the OS later recycles is safe.

Termination is proved behaviourally, never by a liveness API: a child (and the
grandchild it spawns) writes an incrementing heartbeat, and a terminated process
is one whose heartbeat freezes across reads. Every child is driven off
`tests/_fakeproc.py`; the drain fixture and a `finally` guarantee none outlives
its test.
"""
from __future__ import annotations

import os
import subprocess
import time

import pytest

from conductor.command.adapters.process import (
    CommandSpec,
    OwnershipError,
    ProcessRunner,
)

from tests._fakeproc import (
    HEARTBEAT_FILE,
    HEARTBEAT_INTERVAL,
    PID_FILE,
    SPAWN_HB_FILE,
    fake_argv,
    read_int,
    wait_for_int,
    wait_for_pids,
)

_FOREIGN_TOKEN = "cafef00d" * 4  # 32 hex chars, the shape start mints, never minted here


@pytest.fixture
def root(tmp_path):
    (tmp_path / "project" / "work").mkdir(parents=True)
    return tmp_path / "project"


@pytest.fixture
def runners():
    built = []

    def make(project_root, **kwargs):
        runner = ProcessRunner(project_root, **kwargs)
        built.append(runner)
        return runner

    yield make
    for runner in built:
        for token in runner.active_tokens():
            try:
                runner.stop(token)
            except OwnershipError:
                pass


def _heartbeat_child(root, runner, tmp_path, name):
    beat = tmp_path / name
    owned = runner.start(CommandSpec(
        argv=fake_argv(), cwd="work",
        env={HEARTBEAT_FILE: str(beat), HEARTBEAT_INTERVAL: "0.02"}))
    wait_for_int(beat)
    return owned, beat


def _assert_frozen(beat):
    settled = read_int(beat)
    time.sleep(0.2)
    assert read_int(beat) == settled  # nothing still advances it: the process is dead


def _assert_advancing(beat):
    before = read_int(beat)
    time.sleep(0.1)
    assert read_int(beat) > before  # still ticking: alive and running


# --- the runner records the exact child it started ---


def test_the_runner_records_the_exact_child_it_started(root, runners, tmp_path):
    """The recorded pid is the process the runner started, confirmed by the child.

    The witness is obtained apart from the runner's bookkeeping: the child
    self-reports its own pid and its parent's. The runner's recorded pid is the
    process it spawned directly, which is the child itself or -- when
    ``sys.executable`` is a re-exec launcher stub -- the child's parent. It is a
    real, live process, distinct from the test runner.
    """
    pidfile = tmp_path / "pid"
    runner = runners(root)
    owned = runner.start(CommandSpec(
        argv=fake_argv(), cwd="work",
        env={PID_FILE: str(pidfile), HEARTBEAT_FILE: str(tmp_path / "beat"),
             HEARTBEAT_INTERVAL: "0.02"}))
    child_pid, child_ppid = wait_for_pids(pidfile)
    assert owned.pid in (child_pid, child_ppid)
    assert owned.pid != os.getpid()  # a real child, never the test process itself
    assert owned.token in runner.active_tokens()
    runner.stop(owned.token)


# --- stop terminates the recorded child, and refuses everything else ---


def test_stop_terminates_the_recorded_child(root, runners, tmp_path):
    runner = runners(root)
    owned, beat = _heartbeat_child(root, runner, tmp_path, "beat")
    _assert_advancing(beat)  # before: the child is running
    outcome = runner.stop(owned.token)
    assert outcome.status == "stopped"
    _assert_frozen(beat)  # after: the child is terminated
    assert runner.active_tokens() == ()


def test_stop_refuses_a_token_the_runner_never_minted(root, runners, tmp_path):
    """The named foreign-PID sabotage: a token never minted cannot terminate anything.

    A real child runs the whole time. A stop with a fabricated token is refused
    by the ownership relation, and the running child keeps advancing -- the
    refusal touched nothing.
    """
    runner = runners(root)
    owned, beat = _heartbeat_child(root, runner, tmp_path, "beat")
    with pytest.raises(OwnershipError, match="did not mint or no longer holds"):
        runner.stop(_FOREIGN_TOKEN)
    _assert_advancing(beat)  # the owned child is untouched by the refused stop
    runner.stop(owned.token)


def test_stop_refuses_a_token_whose_child_has_already_finished(root, runners):
    """A finished child's token is refused: a PID the OS recycles later is safe.

    The relation is a live token, never a PID comparison. After a run completes,
    its token is no longer owned, so stopping it raises rather than signalling
    whatever process now wears that integer pid.
    """
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={"FAKEPROC_EXIT": "0"}, timeout_seconds=10))
    assert runner.active_tokens() == ()
    with pytest.raises(OwnershipError, match="did not mint or no longer holds"):
        runner.stop(outcome.token)


def test_a_process_the_runner_did_not_start_is_never_touched(root, runners, tmp_path):
    """A foreign process, started outside the runner, survives every runner action.

    The runner offers no way to name a process it did not start, so a foreign
    heartbeat keeps advancing across an owned child's start and stop and across a
    refused foreign-token stop.
    """
    runner = runners(root)
    foreign_beat = tmp_path / "foreign"
    foreign = subprocess.Popen(
        fake_argv(), env={HEARTBEAT_FILE: str(foreign_beat), HEARTBEAT_INTERVAL: "0.02"})
    try:
        wait_for_int(foreign_beat)
        owned, _ = _heartbeat_child(root, runner, tmp_path, "owned")
        runner.stop(owned.token)
        with pytest.raises(OwnershipError):
            runner.stop(_FOREIGN_TOKEN)
        _assert_advancing(foreign_beat)  # the foreign process never felt any of it
    finally:
        foreign.terminate()
        foreign.wait()


# --- termination reaches the child's group, not just the child ---


def test_stop_reaches_the_childs_grandchild_through_the_group(root, runners, tmp_path):
    """A grandchild the child spawned dies with the group, not left orphaned.

    The child spawns a grandchild that heartbeats to its own file. After stop,
    both heartbeats freeze: on Windows the child is in a kill-on-close Job, on
    POSIX it leads its own session, so termination reaches the whole group.
    """
    parent_beat = tmp_path / "parent"
    child_beat = tmp_path / "child"
    runner = runners(root)
    owned = runner.start(CommandSpec(
        argv=fake_argv(), cwd="work",
        env={HEARTBEAT_FILE: str(parent_beat), SPAWN_HB_FILE: str(child_beat),
             HEARTBEAT_INTERVAL: "0.02"}))
    wait_for_int(parent_beat)
    wait_for_int(child_beat)
    _assert_advancing(child_beat)  # the grandchild is alive and running
    runner.stop(owned.token)
    _assert_frozen(parent_beat)
    _assert_frozen(child_beat)  # and dies with the group, not orphaned
    assert runner.active_tokens() == ()
