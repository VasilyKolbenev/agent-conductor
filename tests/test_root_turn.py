"""The root gate as a function: the turn a dispatch holds, taken by anyone who moves a seed (9.1.4).

The move of a staged seed under `work/` must not be seen by another dispatch's proof as a change
outside its own subtree, so it takes the same turn over the same root that a dispatch takes
(`HarnessWorkspace.owned`). `root_turn` is that gate without a workspace: the key is the resolved
root and nothing narrower, a wait may be bounded, and the holder of the one is the holder of the
other.
"""
from __future__ import annotations

import threading
import time

import pytest

from conductor.command.adapters.harness_workspace import HarnessWorkspace, WorkspaceBusy, root_turn


def workspace(root):
    return HarnessWorkspace.at(root, home_dir=".test-home", marker_dir=".test-marker")


def held_by_another_thread(turn):
    """Hold `turn()` in a thread until released; return (release, done) once it is held."""
    held, release = threading.Event(), threading.Event()

    def hold():
        with turn():
            held.set()
            release.wait(30)

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    assert held.wait(10)
    return release, thread


def test_a_turn_over_a_root_a_dispatch_holds_is_busy_and_is_free_once_it_lets_go(tmp_path):
    release, thread = held_by_another_thread(workspace(tmp_path).owned)
    with pytest.raises(WorkspaceBusy):
        with root_turn(tmp_path, wait=0.05):
            pass
    release.set()
    thread.join(10)
    with root_turn(tmp_path, wait=0.05):
        pass


def test_a_dispatch_is_held_off_by_a_turn_taken_over_its_root(tmp_path):
    release, thread = held_by_another_thread(lambda: root_turn(tmp_path))
    with pytest.raises(WorkspaceBusy):
        with workspace(tmp_path).owned(wait=0.05):
            pass
    release.set()
    thread.join(10)


def test_another_root_is_another_gate(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    release, thread = held_by_another_thread(lambda: root_turn(tmp_path / "one"))
    with root_turn(tmp_path / "two", wait=0.05):
        pass
    release.set()
    thread.join(10)


def test_two_spellings_of_one_root_are_one_gate(tmp_path):
    (tmp_path / "project").mkdir()
    release, thread = held_by_another_thread(lambda: root_turn(tmp_path / "project"))
    with pytest.raises(WorkspaceBusy):
        with root_turn(tmp_path / "project" / ".." / "project", wait=0.05):
            pass
    release.set()
    thread.join(10)


def test_a_bounded_wait_waits_and_then_says_busy(tmp_path):
    release, thread = held_by_another_thread(lambda: root_turn(tmp_path))
    started = time.monotonic()
    with pytest.raises(WorkspaceBusy):
        with root_turn(tmp_path, wait=0.3):
            pass
    assert 0.25 <= time.monotonic() - started < 10
    release.set()
    thread.join(10)


def test_a_turn_with_no_bound_waits_for_the_holder_and_then_takes_the_gate(tmp_path):
    release, thread = held_by_another_thread(lambda: root_turn(tmp_path))
    threading.Timer(0.2, release.set).start()
    with root_turn(tmp_path):
        assert not thread.is_alive() or release.is_set()
    thread.join(10)


def test_the_holder_of_a_turn_may_take_another_over_the_same_root(tmp_path):
    with root_turn(tmp_path):
        with workspace(tmp_path).owned(wait=0.05):
            with root_turn(tmp_path, wait=0.05):
                pass
