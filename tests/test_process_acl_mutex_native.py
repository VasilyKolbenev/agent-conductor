"""The cross-process mutex of one folder's DACL, natively, and the one witness of two processes.

`acl_exclusive` is named by the identity of the folder, held for one read-modify-write only, and
handed over by an owner that died holding it. The single controlled witness runs the product's
`change_dacl` in two real processes on one real folder: without the mutex one write is lost and
nothing raises (the control, which shows the witness can fail); with it neither is.
"""
from __future__ import annotations

import multiprocessing
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="a Windows mutex and Windows ACLs")

SID_SLOW, SID_FAST = "S-1-15-2-1-2-3-4-5-6-7", "S-1-15-2-1-2-3-4-5-6-8"


def folder_in(tmp_path, name="shared") -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def hold_of(path):
    from conductor.ownership_native import NativeHold
    return NativeHold(path, directory=True, grants=True)


def dacl_of(path) -> str:
    from conductor.command.adapters import _winlaunch
    from conductor.ownership_native import NativeHold
    hold = NativeHold(path, directory=True)
    try:
        return _winlaunch.acl_snapshot(hold)[0]
    finally:
        hold.close()


def test_the_mutex_is_named_by_the_identity_of_the_folder_and_not_by_the_path_that_reached_it(
        tmp_path):
    from conductor.command.adapters._winlaunch import acl_mutex_name
    folder, other = folder_in(tmp_path, "Shared"), folder_in(tmp_path, "other")
    holds = [hold_of(Path(spelling)) for spelling in (
        str(folder), str(folder).lower(), "\\\\?\\" + str(folder))]
    try:
        names = {acl_mutex_name(hold.identity) for hold in holds}
        assert len(names) == 1, "one folder, three spellings, one mutex"
        elsewhere = hold_of(other)
        try:
            assert acl_mutex_name(elsewhere.identity) not in names
        finally:
            elsewhere.close()
    finally:
        for hold in holds:
            hold.close()
    (name,) = names
    assert str(tmp_path).lower() not in name.lower() and name.startswith("Global\\conduct-acl-")


def test_an_owner_that_died_holding_the_mutex_hands_it_over_and_the_folder_is_checked_again(
        tmp_path):
    from conductor.command.adapters import _winlaunch
    hold = hold_of(folder_in(tmp_path))
    try:
        name = _winlaunch.acl_mutex_name(hold.identity)

        def dies_holding():  # the thread ends without ReleaseMutex: the owner is abandoned
            handle = _winlaunch._kernel.CreateMutexW(None, False, name)
            assert _winlaunch._kernel.WaitForSingleObject(handle, 5000) == 0

        thread = threading.Thread(target=dies_holding)
        thread.start()
        thread.join(30)
        checks, check = [], hold.check
        hold.check = lambda: (checks.append(True), check())[1]
        with _winlaunch.acl_exclusive(hold, wait=5) as abandoned:
            assert abandoned is True
        assert len(checks) >= 2, "the folder is checked on the way in and again once it is held"
        with _winlaunch.acl_exclusive(hold, wait=5) as abandoned:
            assert abandoned is False, "the hand-over is reported once"
    finally:
        hold.close()


def test_a_mutex_another_thread_keeps_for_too_long_fails_the_change_and_changes_nothing(tmp_path):
    from conductor.command.adapters import _winlaunch
    from conductor.command.adapters.process_loans import change_dacl, loan_sddl
    folder = folder_in(tmp_path)
    hold, owner = hold_of(folder), hold_of(folder)
    taken, leave = threading.Event(), threading.Event()

    def keeps():
        with _winlaunch.acl_exclusive(owner):
            taken.set()
            leave.wait(60)

    thread = threading.Thread(target=keeps)
    thread.start()
    try:
        assert taken.wait(30)
        before = dacl_of(folder)
        native = SimpleNamespace(
            acl_snapshot=_winlaunch.acl_snapshot, acl_set=_winlaunch.acl_set,
            acl_equal=_winlaunch.acl_equal,
            acl_exclusive=lambda held: _winlaunch.acl_exclusive(held, wait=0.2))
        with pytest.raises(TimeoutError):
            change_dacl(native, hold, lambda now: loan_sddl(now, SID_SLOW, "modify"))
        assert dacl_of(folder) == before
    finally:
        leave.set()
        thread.join(30)
        hold.close()
        owner.close()


def race(tmp_path, *, serialised: bool) -> str:
    """Two real processes change the DACL of one folder at once; the DACL they leave."""
    from tests.acl_race_child import worker
    folder = folder_in(tmp_path)
    context = multiprocessing.get_context("spawn")
    # Unserialised, the slow process waits for the fast one as long as it takes (it is quick); with
    # the mutex the fast one cannot finish inside the window, so the window is short by design.
    gate = SimpleNamespace(slow_read=context.Event(), fast_done=context.Event(),
                           patience=1.5 if serialised else 60)
    jobs = [context.Process(target=worker, args=(str(folder), sid, role, gate, serialised))
            for sid, role in ((SID_SLOW, "slow"), (SID_FAST, "fast"))]
    for job in jobs:
        job.start()
    for job in jobs:
        job.join(120)
    stuck = [job for job in jobs if job.is_alive()]
    for job in stuck:
        job.kill()
    assert not stuck and [job.exitcode for job in jobs] == [0, 0], "a process of the witness failed"
    return dacl_of(folder)


def test_without_the_mutex_two_processes_changing_one_acl_at_once_lose_an_entry_and_nothing_raises(
        tmp_path):
    left = race(tmp_path, serialised=False)
    assert SID_SLOW in left and SID_FAST not in left, "the witness cannot fail: the control is void"


def test_with_the_mutex_two_processes_changing_one_acl_at_once_lose_neither_entry(tmp_path):
    left = race(tmp_path, serialised=True)
    assert SID_SLOW in left and SID_FAST in left
