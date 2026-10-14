"""`PosixWatch.wait_gone`: the POSIX analogue of the Windows settle (2026-10-05-H-job-timeout).

The runner's group stop returns when the signal has been delivered, not when every process of the
killed tree has been reaped, so a single `is_gone` taken the moment `run` or `stop` returns can
precede the exit. The darwin runner tests wait instead of asking once. The logic does not depend on
`ps`, so it is checked here with a scripted process table, on every host.
"""
from __future__ import annotations

import time

from tests.os_boundary_seatbelt_box import PosixWatch

ALIVE = "S Mon Oct 13 20:00:00 2026"


def watch_over(monkeypatch, *states):
    """A watch whose process table answers `states` in order, then the last one for ever."""
    answers = iter(states)
    last = [states[-1]]

    def state(pid):
        last[0] = next(answers, last[0])
        return last[0]

    monkeypatch.setattr(PosixWatch, "_state", staticmethod(state))
    return PosixWatch(4242)


def test_a_process_that_is_still_alive_when_first_asked_but_ends_soon_is_waited_for(monkeypatch):
    watch = watch_over(monkeypatch, ALIVE, ALIVE, ALIVE, ALIVE, "")
    assert watch.is_gone() is False, "the one-shot question still answers at once"
    assert watch.wait_gone(5.0) is True


def test_a_process_that_never_ends_is_waited_for_no_longer_than_the_bound(monkeypatch):
    watch = watch_over(monkeypatch, ALIVE)
    started = time.monotonic()
    assert watch.wait_gone(0.2) is False
    assert 0.2 <= time.monotonic() - started < 3.0


def test_a_zombie_and_a_process_reborn_under_the_same_number_count_as_gone(monkeypatch):
    assert watch_over(monkeypatch, ALIVE, "Z Mon Oct 13 20:00:00 2026").wait_gone(1.0) is True
    assert watch_over(monkeypatch, ALIVE, "S Mon Oct 13 20:05:00 2026").wait_gone(1.0) is True


def test_a_process_already_gone_is_not_waited_for(monkeypatch):
    watch = watch_over(monkeypatch, ALIVE, "")
    started = time.monotonic()
    assert watch.wait_gone(30.0) is True
    assert time.monotonic() - started < 1.0
