"""A process is told by its pid AND the moment it started (spec 4.1.4, 4.1.13 item 4).

A pid alone is not an identity: the OS hands a pid out again, and a launcher redirector makes
two or three processes of one child. The hub therefore keeps the pair `(pid, process_started)`
and asks `probe` whether that pair still stands. What is judged: the running process reads its
own pair back and is alive; a child that has exited is dead whether or not its entry lingers
(a handle we still hold on Windows, a zombie not yet reaped on POSIX); a pid that has come to
mean another process is dead; a pid with nothing recorded against it can be proven gone but
never proven alive (`unproven`), so nothing may take it for closed. The spelling of each OS is
pinned, and the two readers that only one OS can run (`/proc/<pid>/stat`, `proc_pidinfo`) are
judged on text and bytes every host can build; the real `proc_pidinfo` call is answered by
the macOS job of CI, the only place it can be measured.
"""
from __future__ import annotations

import os
import re
import struct
import subprocess
import sys
import time

import pytest

from conductor import process_identity

SLEEPER = [sys.executable, "-c", "import time; time.sleep(120)"]
SPELLING = {"nt": r"windows:\d+", "linux": r"linux:[0-9a-f-]{36}:\d+",
            "darwin": r"darwin:\d+\.\d{6}"}


def _spelling() -> str:
    if os.name == "nt":
        return SPELLING["nt"]
    return SPELLING["darwin" if sys.platform == "darwin" else "linux"]


def _wait_until(predicate, what: str, bound: float = 20.0) -> None:
    deadline = time.monotonic() + bound
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.02)


@pytest.fixture
def sleeper():
    proc = subprocess.Popen(SLEEPER, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=20)


# -- the running process ---------------------------------------------------------------


def test_this_process_reads_its_own_pair_back_and_is_alive():
    started = process_identity.started_of(os.getpid())
    assert started is not None and re.fullmatch(_spelling(), started), started
    assert process_identity.started_of(os.getpid()) == started
    assert process_identity.current() == started
    assert process_identity.probe(os.getpid(), started) == "alive"


def test_two_running_processes_do_not_share_a_start(sleeper):
    mine, theirs = (process_identity.started_of(p) for p in (os.getpid(), sleeper.pid))
    assert theirs is not None and mine != theirs


# -- the ones that are gone ----------------------------------------------------------------


def test_a_child_that_was_killed_is_dead_while_its_entry_still_lingers(sleeper):
    started = process_identity.started_of(sleeper.pid)
    assert process_identity.probe(sleeper.pid, started) == "alive"
    sleeper.kill()             # not waited for: a zombie on POSIX, a held handle on Windows
    _wait_until(lambda: process_identity.probe(sleeper.pid, started) == "dead",
                "the killed child to read as dead")
    assert process_identity.started_of(sleeper.pid) is None
    sleeper.wait(timeout=20)
    assert process_identity.probe(sleeper.pid, started) == "dead"


def test_a_pid_that_has_come_to_mean_another_process_is_dead(sleeper):
    recorded = process_identity.started_of(sleeper.pid)
    other = recorded + "0" if not recorded.endswith("0") else recorded[:-1] + "1"
    assert process_identity.probe(sleeper.pid, other) == "dead"
    assert process_identity.probe(sleeper.pid, recorded) == "alive", "the control must stand"


def test_nothing_recorded_proves_a_pid_gone_but_never_proves_it_alive(sleeper):
    assert process_identity.probe(sleeper.pid, None) == "unproven"
    sleeper.kill()
    sleeper.wait(timeout=20)
    assert process_identity.probe(sleeper.pid, None) == "dead"


def test_a_pid_that_does_not_exist_reads_none_and_is_dead():
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, check=True, timeout=60)
    gone = int(done.stdout)
    assert process_identity.started_of(gone) is None
    assert process_identity.probe(gone, None) == "dead"
    assert process_identity.probe(gone, "windows:1") == "dead"


@pytest.mark.parametrize("pid", [0, -1, True, "12", 2**40])
def test_a_pid_that_cannot_be_one_is_a_fault_of_the_caller(pid):
    with pytest.raises(ValueError, match="pid"):
        process_identity.started_of(pid)


# -- what only another OS can run, judged on what every host can build -----------------------

STAT = ("4242 (py thon) S 1 4242 4242 0 -1 4194560 100 0 0 0 1 1 0 0 20 0 1 0 987654 "
        "1000000 100 18446744073709551615 0 0 0 0 0 0 0 0 0 0 0 0 17 0 0 0 0 0 0")


def test_the_proc_stat_line_is_read_after_the_last_bracket_whatever_the_name_holds():
    assert process_identity.parse_proc_stat(STAT) == ("S", "987654")
    tricky = STAT.replace("(py thon)", "(a) b) (c)")
    assert process_identity.parse_proc_stat(tricky) == ("S", "987654")


@pytest.mark.parametrize("text", ["", "4242 no-brackets S 1", "4242 (x) S 1 2"])
def test_a_proc_stat_line_that_is_not_one_is_refused(text):
    with pytest.raises(process_identity.IdentityUnreadable):
        process_identity.parse_proc_stat(text)


def _bsdinfo(status: int = 2, sec: int = 1_700_000_000, usec: int = 123) -> bytes:
    buffer = bytearray(process_identity.BSDINFO_SIZE)
    struct.pack_into("I", buffer, 4, status)
    struct.pack_into("QQ", buffer, 120, sec, usec)
    return bytes(buffer)


def test_the_darwin_record_gives_its_start_in_seconds_and_microseconds():
    assert process_identity.parse_bsdinfo(_bsdinfo()) == ("darwin:1700000000.000123", False)
    assert process_identity.parse_bsdinfo(_bsdinfo(status=5))[1] is True


def test_the_darwin_record_of_another_size_is_refused():
    with pytest.raises(process_identity.IdentityUnreadable):
        process_identity.parse_bsdinfo(_bsdinfo()[:-1])
    assert process_identity.BSDINFO_SIZE == 136


def test_a_zombie_has_no_identity_on_any_spelling_of_it():
    assert process_identity.started_from_proc("Z", "987654", "boot") is None
    assert process_identity.started_from_proc("X", "987654", "boot") is None
    assert process_identity.started_from_proc("S", "987654", "boot") == "linux:boot:987654"
