"""Every read-modify-write of a loaned folder's DACL runs inside that folder's mutex (fake natives).

A pinned install folder is shared by every attempt of a harness and by every project server, so two
PROCESSES can change its DACL within the milliseconds between a read and a write, and the OS has no
compare-and-swap on a DACL. The grant and the return take the folder's cross-process mutex around
each read-modify-write and hold it for that change only. The mutex is the native callback
`acl_exclusive`; the real one, and two real processes, are in `test_process_acl_mutex_native`.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.test_process_loans import OWNER, PRIOR, record_files
from tests.test_process_login_grant import login_world


def mutexed_world(tmp_path):
    """A loan world (work, install, leased login home) whose natives record the mutex."""
    w = login_world(tmp_path)
    native, log, held = w.store.native, [], []
    real_snapshot, real_set = native.acl_snapshot, native.acl_set

    @contextmanager
    def exclusive(hold):
        path = Path(hold.path)
        log.append(("enter", path))
        held.append(path)
        try:
            yield False
        finally:
            held.remove(path)
            log.append(("leave", path))

    def snapshot(hold):
        log.append(("read", Path(hold.path), Path(hold.path) in held))
        return real_snapshot(hold)

    def set_acl(hold, sddl, *, protected):
        assert Path(hold.path) in held, "a DACL is written outside the folder's mutex"
        log.append(("write", Path(hold.path)))
        real_set(hold, sddl, protected=protected)

    native.acl_exclusive, native.acl_snapshot, native.acl_set = exclusive, snapshot, set_acl
    return w, log, held


def changes(log) -> list:
    """The runs of the log between an `enter` and its `leave`, one list per change."""
    runs, current = [], None
    for event in log:
        if event[0] == "enter":
            current = [event]
        elif current is not None:
            current.append(event)
            if event[0] == "leave":
                runs.append(current)
                current = None
    return runs


def test_the_grant_reads_writes_and_reads_back_each_folder_inside_that_folders_mutex(tmp_path):
    w, log, _ = mutexed_world(tmp_path)
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    runs = changes(log)
    assert [run[0][1] for run in runs] == list(w.folders.values())
    for run in runs:
        path = run[0][1]
        assert run == [("enter", path), ("read", path, True), ("write", path),
                       ("read", path, True), ("leave", path)]


def test_the_return_does_the_same_inside_the_mutex_of_each_folder(tmp_path):
    w, log, _ = mutexed_world(tmp_path)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    del log[:]
    w.loans.restore(record)
    runs = changes(log)
    assert sorted(run[0][1] for run in runs) == sorted(w.folders.values())
    for run in runs:
        path = run[0][1]
        assert run == [("enter", path), ("read", path, True), ("write", path),
                       ("read", path, True), ("leave", path)]


def test_no_mutex_is_held_while_the_attempt_stands_between_its_grant_and_its_return(tmp_path):
    w, log, held = mutexed_world(tmp_path)
    record = w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert held == [], "the agent would work while another server waits for the folder"
    w.loans.restore(record)
    assert held == []


def test_a_mutex_that_cannot_be_taken_fails_the_change_before_it_and_the_restore_returns_the_rest(
        tmp_path):
    w, log, _ = mutexed_world(tmp_path)
    real = w.store.native.acl_exclusive

    @contextmanager
    def busy(hold):
        if Path(hold.path) == w.folders["install"]:
            raise TimeoutError("another process is changing the ACL of this folder")
        with real(hold) as abandoned:
            yield abandoned

    w.store.native.acl_exclusive = busy
    with pytest.raises(TimeoutError):
        w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.state[str(w.folders["install"])] == (PRIOR, False, OWNER), "nothing was written"
    w.store.native.acl_exclusive = real
    w.loans.restore()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())
    phases = [json.loads(p.read_text(encoding="utf-8"))["phase"] for p in record_files(w)]
    assert phases == ["retired"]


def test_an_abandoned_mutex_does_not_stop_the_change_and_the_dacl_is_read_inside_it(tmp_path):
    w, log, _ = mutexed_world(tmp_path)
    real = w.store.native.acl_exclusive

    @contextmanager
    def abandoned(hold):
        with real(hold):
            yield True  # the owner before us died holding it; we hold it now

    w.store.native.acl_exclusive = abandoned
    w.loans.grant(w.profile_path, w.sid, "dispatch", w.folders)
    assert w.sid in w.state[str(w.folders["install"])][0]
    for run in changes(log):
        assert run[1] == ("read", run[0][1], True), "the DACL is read after the mutex is held"
