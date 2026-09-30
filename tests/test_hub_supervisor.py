"""The supervisor of the hub's children (spec 4.1.4, 4.1.5, 4.1.7, 4.1.13 item 3).

This file grows with the supervisor. It begins with the rule the supervisor stands on: a project
is proven closed only when its process is dead by `(pid, process_started)` AND the head of its
ownership, read without writing, is not `opened` (4.1.7). The rule is a function of the state
module; what it is asked here is the claim of the spec under its own name, on the real
probe and the real head of a real project, next to the fakes of `test_hub_state.py`.
"""
from __future__ import annotations

import subprocess
import sys

from conductor import ownership, ownership_records, ownership_transition, process_identity
from conductor.hub import state
from tests.test_store import good_lane, write_project

NOW = "2026-09-30T10:00:00Z"
SLEEPER = [sys.executable, "-c", "import time; time.sleep(120)"]


def _activated(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    write_project(root, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    return root


def test_proven_closed_needs_a_dead_process_and_an_ownership_head_that_is_not_opened(tmp_path):
    root = _activated(tmp_path)
    nonce = ownership_records.state(root)[1]["nonce"]
    child = subprocess.Popen(SLEEPER, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        recorded = state.ClosingEntry("a" * 32, child.pid,
                                      process_identity.started_of(child.pid), nonce, NOW)
        # A live process, a head that was never opened: not closed, and the word says why.
        assert state.proven_closed(recorded, root) == state.Closure(False, "process_alive")
        child.kill()
        child.wait(timeout=20)
        # Dead, and the head is `active`, never opened: closed.
        assert state.proven_closed(recorded, root) == state.Closure(True, "proven")
        # Dead, and the project's owner opened it and never closed it: not closed.
        owner = ownership.acquire_owner(root)
        try:
            assert state.proven_closed(recorded, root) == state.Closure(False, "head_opened")
        finally:
            owner.release()
        assert state.proven_closed(recorded, root) == state.Closure(True, "proven")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=20)
