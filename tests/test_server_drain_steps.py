"""The eight steps of the drain (spec 4.1.6), judged one at a time on a recording fake.

`tests/test_server_drain.py` runs the whole thing in a real process and reads only
durable facts. What a process cannot show cheaply is the ORDER of the steps and the
edges of each: which state is written when, what a failing step does to the steps
after it, what the deadline is made of. Those are judged here, with a fake server
that appends to one journal every call the drain makes on it, a recorder for the
status file, and a clock the test moves. The deadline is also read from a real run
store with a real open attempt, so its arithmetic is the store's and not a copy.
"""
from __future__ import annotations

import os
import signal
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from conductor import server_drain
from conductor.command.run_store import RunStore
from tests.test_policy_driver import authorize
from tests.test_policy_runtime import propose, setup

NOON = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
RUN_NOW = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)   # the fixture's clock


class Journal(list):
    """Every call the drain makes, in order."""


class FakeStatus:
    def __init__(self, journal: Journal, server: FakeServer | None = None) -> None:
        self.journal, self.server, self.rows = journal, server, []

    def write(self, state, *, code=None, port=None, drain_deadline=None):
        self.rows.append((state, drain_deadline))
        marker = f"status:{state}" + ("+deadline" if drain_deadline is not None else "")
        if state == "stopping" and self.server is not None and not self.server.draining:
            marker += "!not-draining"
        self.journal.append(marker)


class FakeDriver:
    def __init__(self, journal: Journal, fails: bool = False) -> None:
        self.journal, self.fails = journal, fails

    def hold_new_work(self):
        self.journal.append("hold_new_work")
        if self.fails:
            raise RuntimeError("the driver could not hold")


class FakeQuota:
    def __init__(self, journal: Journal, fails: bool = False) -> None:
        self.journal, self.fails = journal, fails

    def stop(self):
        self.journal.append("quota.stop")
        if self.fails:
            raise RuntimeError("quota retirement is unconfirmed")


class FakeExecution:
    def __init__(self, journal: Journal, busy_slices: int = 0, hook=None) -> None:
        self.journal, self.busy, self.hook = journal, busy_slices, hook

    def wait_idle(self, timeout):
        self.journal.append(f"wait_idle:{timeout}")
        if self.hook is not None:
            self.hook()
        if self.busy > 0:
            self.busy -= 1
            return False
        return True


class FakeServer:
    """Only what the drain touches; the optional resources are what `view` lacks."""

    def __init__(self, journal: Journal, *, driver=True, quota=True, execution=True,
                 busy_slices=0, fail_close=False, fail_shutdown=False, hook=None) -> None:
        self.journal, self.draining = journal, False
        self.retirement_uncertain = False
        self.command_store = None
        self.policy_driver = FakeDriver(journal, driver == "fails") if driver else None
        self.quota_collector = FakeQuota(journal, quota == "fails") if quota else None
        self.command_execution = (FakeExecution(journal, busy_slices, hook)
                                  if execution else None)
        self._fail_close, self._fail_shutdown = fail_close, fail_shutdown

    def shutdown(self):
        self.journal.append("shutdown")
        if self._fail_shutdown:
            raise RuntimeError("shutdown could not retire its workers")

    def server_close(self):
        self.journal.append("server_close")
        if self._fail_close:
            raise RuntimeError("the owner would not release")


class Clock:
    """A clock the test moves; every reading is recorded so a stale one shows."""

    def __init__(self, start: datetime = NOON) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _drain(server: FakeServer, journal: Journal, clock: Clock | None = None):
    status = FakeStatus(journal, server)
    code = server_drain.drain_and_close(server, status, clock=clock or Clock())
    return code, status


def test_the_drain_runs_the_steps_of_the_spec_in_order():
    journal = Journal()
    code, status = _drain(FakeServer(journal), journal)
    assert code == 0
    assert journal == [
        "status:stopping", "hold_new_work", "quota.stop", "status:stopping+deadline",
        f"wait_idle:{server_drain.WAIT_SLICE_SECONDS}", "shutdown", "server_close",
        "status:stopped"]


def test_the_drain_marks_the_server_as_draining_before_it_writes_stopping():
    journal = Journal()
    server = FakeServer(journal)
    _drain(server, journal)
    assert server.draining is True
    assert "status:stopping!not-draining" not in journal


def test_a_drain_with_no_open_attempt_sets_its_deadline_ten_seconds_out():
    journal, clock = Journal(), Clock()
    _, status = _drain(FakeServer(journal), journal, clock)
    deadline = [moment for state, moment in status.rows if moment is not None][0]
    assert deadline == NOON + timedelta(seconds=server_drain.IDLE_DEADLINE_SECONDS) == \
        NOON + timedelta(seconds=10)


def test_the_constants_of_the_spec_are_the_numbers_of_the_spec():
    assert server_drain.DRAIN_MARGIN_SECONDS == 60
    assert server_drain.IDLE_DEADLINE_SECONDS == 10
    assert server_drain.WAIT_SLICE_SECONDS == 0.5


def test_a_server_without_a_driver_or_a_quota_collector_skips_those_two_steps():
    journal = Journal()
    code, _ = _drain(FakeServer(journal, driver=False, quota=False), journal)
    assert code == 0 and "hold_new_work" not in journal and "quota.stop" not in journal
    assert journal[-1] == "status:stopped"


def test_a_server_without_an_execution_coordinator_is_idle_at_once():
    journal = Journal()
    code, _ = _drain(FakeServer(journal, execution=False), journal)
    assert code == 0 and not any(entry.startswith("wait_idle") for entry in journal)


def test_stop_overdue_is_written_once_and_the_drain_ends_stopped_when_the_wait_ends():
    journal, clock = Journal(), Clock()
    server = FakeServer(journal, busy_slices=4, hook=lambda: clock.advance(6))
    code, status = _drain(server, journal, clock)
    states = [state for state, _ in status.rows]
    assert states == ["stopping", "stopping", "stop_overdue", "stopped"]
    assert code == 0 and journal.count("shutdown") == 1
    assert journal.index("status:stop_overdue+deadline") < journal.index("shutdown")
    overdue = status.rows[2]
    assert overdue[1] == status.rows[1][1], "the overdue record keeps the same deadline"


def test_an_overdue_drain_never_shuts_the_server_down_while_the_attempt_is_still_running():
    journal, clock = Journal(), Clock()
    ticks = {"n": 0}

    def hook():
        ticks["n"] += 1
        clock.advance(20)
        if ticks["n"] > 5:
            raise SystemExit("the test stops the wait; the server was still not closed")

    server = FakeServer(journal, busy_slices=10**6, hook=hook)
    with pytest.raises(SystemExit):
        _drain(server, journal, clock)
    assert "shutdown" not in journal and "server_close" not in journal
    assert journal.count("status:stop_overdue+deadline") == 1


@pytest.mark.parametrize("option", [{"quota": "fails"}, {"driver": "fails"}])
def test_a_failing_early_step_does_not_skip_the_wait_and_ends_stop_uncertain(option):
    journal = Journal()
    server = FakeServer(journal, **option)
    code, status = _drain(server, journal)
    assert code == 1 and status.rows[-1][0] == "stop_uncertain"
    assert any(entry.startswith("wait_idle") for entry in journal), "the attempt is awaited"
    assert server.retirement_uncertain is True
    assert "status:stopped" not in journal


@pytest.mark.parametrize("option", [{"fail_close": True}, {"fail_shutdown": True}])
def test_a_failing_shutdown_or_close_ends_stop_uncertain_and_still_tries_both(option):
    journal = Journal()
    server = FakeServer(journal, **option)
    code, status = _drain(server, journal)
    assert code == 1 and status.rows[-1][0] == "stop_uncertain"
    assert "shutdown" in journal and "server_close" in journal


def test_a_server_that_reports_retirement_uncertain_by_itself_ends_stop_uncertain():
    journal = Journal()
    server = FakeServer(journal)
    server.server_close = lambda: setattr(server, "retirement_uncertain", True)
    code, status = _drain(server, journal)
    assert code == 1 and status.rows[-1][0] == "stop_uncertain"


def test_a_status_file_that_cannot_be_written_never_stops_the_drain(capsys):
    journal = Journal()
    server = FakeServer(journal)

    class Broken:
        def write(self, state, **fields):
            raise PermissionError(13, "the run folder is read-only")

    assert server_drain.drain_and_close(server, Broken(), clock=Clock()) == 0
    assert journal[-2:] == ["shutdown", "server_close"]
    assert "read-only" in capsys.readouterr().err


def test_the_unknown_state_of_a_failed_step_is_one_stderr_line(capsys):
    journal = Journal()
    _drain(FakeServer(journal, quota="fails"), journal)
    lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(lines) == 1 and lines[0].startswith("conduct up: stop uncertain: ")


# -- the deadline, from a real run store ---------------------------------------


def _open_attempt(tmp_path, *, checker: bool):
    fixture = setup(tmp_path, two_steps=True, checker=checker)
    grant = authorize(fixture)
    propose(fixture)
    authority = fixture.runtime.authorize_policy("run", "proposal", grant.authorization_id)
    return fixture, authority


def test_the_deadline_is_the_open_attempts_reservation_plus_the_margin(tmp_path):
    fixture, _ = _open_attempt(tmp_path, checker=False)
    deadline = server_drain.drain_deadline(fixture.store, RUN_NOW)
    assert deadline == RUN_NOW + timedelta(seconds=30 + server_drain.DRAIN_MARGIN_SECONDS)


def test_a_step_with_a_checker_reserves_its_time_twice(tmp_path):
    fixture, _ = _open_attempt(tmp_path, checker=True)
    deadline = server_drain.drain_deadline(fixture.store, RUN_NOW)
    assert deadline == RUN_NOW + timedelta(seconds=60 + server_drain.DRAIN_MARGIN_SECONDS)


def test_the_deadline_counts_from_the_time_the_attempt_was_requested_not_from_now(tmp_path):
    fixture, _ = _open_attempt(tmp_path, checker=False)
    later = RUN_NOW + timedelta(hours=3)
    deadline = server_drain.drain_deadline(fixture.store, later)
    assert deadline == RUN_NOW + timedelta(seconds=30 + server_drain.DRAIN_MARGIN_SECONDS)


def test_an_attempt_that_has_its_receipt_is_no_longer_open(tmp_path):
    fixture, authority = _open_attempt(tmp_path, checker=False)
    fixture.runtime.execute(authority)
    deadline = server_drain.drain_deadline(fixture.store, RUN_NOW)
    assert deadline == RUN_NOW + timedelta(seconds=server_drain.IDLE_DEADLINE_SECONDS)


def test_a_request_that_names_no_plan_node_reserves_its_own_timeout(tmp_path):
    fixture, authority = _open_attempt(tmp_path, checker=True)
    request = replace(authority.request, node_id=None)
    ends = server_drain.open_attempt_ends((request,))
    assert ends == [RUN_NOW + timedelta(seconds=request.timeout_seconds)]


def test_a_store_with_no_runs_gets_the_idle_deadline(tmp_path):
    (tmp_path / "conductor").mkdir()
    assert server_drain.drain_deadline(RunStore(tmp_path), NOON) == NOON + timedelta(seconds=10)


# -- the stop event, the serve loop, and Ctrl+C ------------------------------------


def test_end_of_file_on_the_stdin_descriptor_sets_the_one_event():
    read_end, write_end = os.pipe()
    stopper = server_drain.Stopper()
    stopper.watch_stdin(read_end)
    os.write(write_end, b"the hub never writes, but a stray byte must not stop us")
    assert not stopper.event.wait(0.3)
    os.close(write_end)
    assert stopper.event.wait(5)
    os.close(read_end)


def test_a_descriptor_that_cannot_be_read_counts_as_end_of_file():
    stopper = server_drain.Stopper()
    stopper.watch_stdin(-1)
    assert stopper.event.wait(5)


def test_the_stdin_watcher_is_a_daemon_thread_named_for_what_it_does():
    read_end, write_end = os.pipe()
    stopper = server_drain.Stopper()
    stopper.watch_stdin(read_end)
    try:
        watcher = next(t for t in threading.enumerate() if t.name == "conduct-stdin")
        assert watcher.daemon
    finally:
        os.close(write_end)
        stopper.event.wait(5)
        os.close(read_end)


class ServingFake(FakeServer):
    """A server whose serve loop blocks until `shutdown`, as the real one does."""

    def __init__(self, journal, *, returns_at_once=False, **options) -> None:
        super().__init__(journal, **options)
        self._loop_over, self._returns_at_once = threading.Event(), returns_at_once
        self.serving_thread = None

    def serve_forever(self):
        self.serving_thread = threading.current_thread().name
        if not self._returns_at_once:
            self._loop_over.wait(30)

    def shutdown(self):
        super().shutdown()
        self._loop_over.set()


def test_a_stop_event_drains_once_and_returns_the_drain_exit_code():
    journal, stopper = Journal(), server_drain.Stopper()
    server = ServingFake(journal)
    threading.Timer(0.2, stopper.event.set).start()
    code = server_drain.serve_until_stopped(server, FakeStatus(journal), stopper,
                                            clock=Clock())
    assert code == 0 and journal.count("shutdown") == 1
    assert server.serving_thread == "conduct-http"
    assert journal[-1] == "status:stopped"


def test_a_serve_loop_that_ends_by_itself_is_a_stop():
    journal = Journal()
    server = ServingFake(journal, returns_at_once=True)
    code = server_drain.serve_until_stopped(server, FakeStatus(journal), server_drain.Stopper())
    assert code == 0 and journal.count("shutdown") == 1


def test_an_interrupt_in_the_main_wait_starts_the_drain():
    journal, stopper = Journal(), server_drain.Stopper()

    class Interrupted:
        def wait(self, timeout):
            raise KeyboardInterrupt

        def set(self):
            pass

        def is_set(self):
            return True

    stopper.event = Interrupted()
    server = ServingFake(journal)
    code = server_drain.serve_until_stopped(server, FakeStatus(journal), stopper)
    assert code == 0 and journal.count("shutdown") == 1


def test_a_second_interrupt_during_the_drain_prints_the_deadline_and_changes_nothing(capsys):
    journal, stopper = Journal(), server_drain.Stopper()
    fired = []

    def second_ctrl_c():
        if not fired:
            fired.append(True)
            signal.raise_signal(signal.SIGINT)    # what a second Ctrl+C is, to Python

    server = ServingFake(journal, hook=second_ctrl_c)
    stopper.event.set()
    before = signal.getsignal(signal.SIGINT)
    code = server_drain.serve_until_stopped(server, FakeStatus(journal), stopper,
                                            clock=Clock())
    assert code == 0 and fired and journal[-1] == "status:stopped"
    assert signal.getsignal(signal.SIGINT) is before, "the handler is restored afterwards"
    err = capsys.readouterr().err
    assert "Ctrl+C does not interrupt" in err and "12:00:10" in err


def test_the_console_reset_asks_the_os_to_stop_ignoring_ctrl_c_and_only_on_windows():
    calls = []
    server_drain.enable_ctrl_c(set_handler=lambda handler, add: calls.append((handler, add)),
                               windows=True)
    assert calls == [(None, False)]
    server_drain.enable_ctrl_c(set_handler=lambda *a: calls.append(a), windows=False)
    assert calls == [(None, False)]
