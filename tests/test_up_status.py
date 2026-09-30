"""The child's status file (spec 4.1.4): its shape, and how it is put on disk.

`atomic_replace.replace_bytes` is the one door: a reader that opens the file
just before a write must see the old whole or the new whole, and on Windows a
reader that HOLDS the file makes `os.replace` fail with `PermissionError` until
it lets go. The retry is what keeps a hub that polls the file from costing the
child a state change, so it has a claim of its own: bounded, and honest about
giving up.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conductor import atomic_replace, process_identity, up_status

PROJECT_ID = "3f9c0d5a7b2e4c168a90d3e1f4b7a625"
RECORD_KEYS = {"schema_version", "project_id", "pid", "process_started", "port", "mode",
               "state", "code", "drain_deadline", "updated_at"}
NOON = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


class HeldThenFree:
    """An `os.replace` that fails `failures` times the way a held file does, then works."""

    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    def __call__(self, source, target) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise PermissionError(13, "the file is held by a reader")
        os.replace(source, target)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _staging_files(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir() if entry.name.endswith(".tmp"))


def test_replace_bytes_retries_while_the_target_is_held_and_then_publishes(tmp_path):
    target = tmp_path / "status.json"
    target.write_bytes(b"old")
    replace, pauses = HeldThenFree(failures=3), []
    atomic_replace.replace_bytes(target, b"new", replace=replace, sleep=pauses.append)
    assert target.read_bytes() == b"new"
    assert replace.calls == 4 and pauses == [atomic_replace.PAUSE_SECONDS] * 3
    assert _staging_files(tmp_path) == []


def test_replace_bytes_gives_up_with_the_last_permission_error_after_its_bounded_retries(
        tmp_path):
    target = tmp_path / "status.json"
    target.write_bytes(b"old")
    replace, pauses = HeldThenFree(failures=10**6), []
    with pytest.raises(PermissionError, match="held by a reader"):
        atomic_replace.replace_bytes(target, b"new", replace=replace, sleep=pauses.append)
    assert replace.calls == atomic_replace.ATTEMPTS
    assert len(pauses) == atomic_replace.ATTEMPTS - 1
    assert target.read_bytes() == b"old"
    assert _staging_files(tmp_path) == []


def test_replace_bytes_does_not_retry_an_error_that_waiting_cannot_cure(tmp_path):
    target = tmp_path / "missing-folder" / "status.json"
    with pytest.raises(FileNotFoundError):
        atomic_replace.replace_bytes(target, b"new", sleep=lambda _: pytest.fail("slept"))


@pytest.mark.skipif(os.name != "nt", reason="a held file blocks os.replace only on Windows")
def test_a_reader_holding_the_status_file_on_windows_delays_but_never_loses_a_write(tmp_path):
    target = tmp_path / "status.json"
    target.write_bytes(b"old")
    holding, release = threading.Event(), threading.Event()

    def hold() -> None:
        with target.open("rb"):
            holding.set()
            release.wait(10)

    reader = threading.Thread(target=hold, daemon=True)
    reader.start()
    assert holding.wait(5)
    try:
        probe = tmp_path / "probe"
        probe.write_bytes(b"x")
        with pytest.raises(PermissionError):   # the instrument: the hold really blocks a swap
            os.replace(probe, target)
        threading.Timer(0.3, release.set).start()
        atomic_replace.replace_bytes(target, b"new")
    finally:
        release.set()
        reader.join(5)
    assert target.read_bytes() == b"new"


def _status(tmp_path: Path, **overrides) -> up_status.StatusFile:
    options = dict(path=tmp_path / "run" / f"{PROJECT_ID}.json", project_id=PROJECT_ID,
                   mode="active", port=7701, clock=lambda: NOON, pid=4812)
    options.update(overrides)
    return up_status.StatusFile(**options)


def test_the_status_file_has_the_keys_of_the_spec_record(tmp_path):
    status = _status(tmp_path)
    status.write("starting")
    record = _read(status.path)
    assert set(record) == RECORD_KEYS
    assert record["schema_version"] == 1 and record["project_id"] == PROJECT_ID
    assert record["pid"] == 4812 and record["mode"] == "active"
    assert record["state"] == "starting" and record["code"] is None
    assert record["drain_deadline"] is None and record["updated_at"] == "2026-09-29T12:00:00Z"


def test_each_write_keeps_project_pid_mode_and_updates_state_port_and_deadline(tmp_path):
    status = _status(tmp_path)
    status.write("starting")
    status.write("serving", port=54012)
    deadline = datetime(2026, 9, 29, 12, 5, 30, 999999, tzinfo=timezone.utc)
    status.write("stopping", drain_deadline=deadline)
    status.write("stop_overdue")
    record = _read(status.path)
    assert (record["project_id"], record["pid"], record["mode"]) == (PROJECT_ID, 4812, "active")
    assert record["state"] == "stop_overdue" and record["port"] == 54012
    assert record["drain_deadline"] == "2026-09-29T12:05:30Z"


def test_a_refused_record_carries_the_code_and_only_the_refused_record_does(tmp_path):
    status = _status(tmp_path)
    status.write("serving")
    assert _read(status.path)["code"] is None
    status.write("refused", code="owner_busy")
    assert (_read(status.path)["state"], _read(status.path)["code"]) == ("refused", "owner_busy")


def test_a_status_write_replaces_the_whole_file_atomically(tmp_path, monkeypatch):
    """Observed at the swap itself, through the door's own `replace=` seam.

    Atomic here means one swap between two whole files: at that instant the target is
    still the old whole record, the staged file is the complete new record beside it
    (the same folder, or the swap would not be one rename), and afterwards the target
    is exactly the staged bytes and nothing is left staged. A write in place, or a
    stage in another folder, cannot satisfy all of that.
    """
    status = _status(tmp_path)
    status.write("starting")
    old_whole = status.path.read_bytes()
    at_the_swap: list[dict] = []
    real = atomic_replace.replace_bytes

    def observing_swap(source, target) -> None:
        at_the_swap.append({"target": Path(target).read_bytes(),
                            "staged": Path(source).read_bytes(),
                            "same_folder": Path(source).parent == Path(target).parent})
        os.replace(source, target)

    def through_the_door(path, payload, **options) -> None:
        real(path, payload, replace=observing_swap, **options)

    monkeypatch.setattr(atomic_replace, "replace_bytes", through_the_door)
    status.write("serving")
    assert len(at_the_swap) == 1, "the record was not published by one swap"
    seen = at_the_swap[0]
    assert seen["target"] == old_whole                       # a reader still sees the old whole
    assert set(json.loads(seen["staged"])) == RECORD_KEYS    # the staged record is complete
    assert json.loads(seen["staged"])["state"] == "serving" and seen["same_folder"]
    assert status.path.read_bytes() == seen["staged"]        # the swap moved those very bytes
    assert _staging_files(status.path.parent) == []


def test_the_run_folder_is_created_by_the_first_write(tmp_path):
    status = _status(tmp_path)
    assert not status.path.parent.exists()
    status.write("starting")
    assert status.path.exists()


def test_the_null_status_accepts_every_write_and_writes_nothing(tmp_path):
    status = up_status.NullStatus()
    status.write("starting")
    status.write("stopping", drain_deadline=NOON)
    status.write("refused", code="owner_busy")
    assert list(tmp_path.iterdir()) == []


# -- when the process started (spec 4.1.4) ------------------------------------------------


def test_the_status_file_carries_when_its_process_started(tmp_path):
    status = _status(tmp_path, pid=os.getpid())
    status.write("starting")
    status.write("serving", port=54012)
    started = _read(status.path)["process_started"]
    assert started == process_identity.started_of(os.getpid()) and started is not None


def test_a_pid_that_runs_nothing_is_recorded_with_a_start_of_null(tmp_path):
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, check=True, timeout=60)
    status = _status(tmp_path, pid=int(done.stdout))
    status.write("starting")
    assert _read(status.path)["process_started"] is None


# -- the reader the hub uses: strict, typed, and silent about a file that is not there ----


def _good_record(**changes) -> dict:
    record = {"schema_version": 1, "project_id": PROJECT_ID, "pid": 4812,
              "process_started": "windows:133712345678901234", "port": 7701, "mode": "active",
              "state": "serving", "code": None, "drain_deadline": None,
              "updated_at": "2026-09-29T12:00:00Z"}
    return {**record, **changes}


def _publish(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "run" / f"{PROJECT_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(document if isinstance(document, bytes)
                     else json.dumps(document).encode("utf-8"))
    return path


def test_a_record_the_writer_published_is_read_back_typed(tmp_path):
    status = _status(tmp_path, pid=os.getpid())
    status.write("starting")
    status.write("stopping", drain_deadline=datetime(2026, 9, 29, 12, 5, 30, tzinfo=timezone.utc))
    found = up_status.read_status(status.path)
    assert (found.project_id, found.pid, found.mode, found.state) == (
        PROJECT_ID, os.getpid(), "active", "stopping")
    assert found.process_started == process_identity.started_of(os.getpid())
    assert found.updated_at == NOON and found.code is None and found.port == 7701
    assert found.drain_deadline == datetime(2026, 9, 29, 12, 5, 30, tzinfo=timezone.utc)


def test_a_refused_record_reads_back_with_its_code(tmp_path):
    status = _status(tmp_path)
    status.write("refused", code="owner_busy")
    found = up_status.read_status(status.path)
    assert (found.state, found.code) == ("refused", "owner_busy")


def test_a_file_that_is_not_there_reads_as_none(tmp_path):
    assert up_status.read_status(tmp_path / "run" / "missing.json") is None


BAD_RECORDS = {
    "an unknown key": {**_good_record(), "extra": 1},
    "a missing key": {k: v for k, v in _good_record().items() if k != "code"},
    "schema 2": _good_record(schema_version=2),
    "schema true": _good_record(schema_version=True),
    "a project id in capitals": _good_record(project_id=PROJECT_ID.upper()),
    "a pid of zero": _good_record(pid=0),
    "a pid that is true": _good_record(pid=True),
    "a pid that is text": _good_record(pid="4812"),
    "an unknown spelling of the start": _good_record(process_started="plan9:1"),
    "a start that is a number": _good_record(process_started=5),
    "a port below zero": _good_record(port=-1),
    "a port above 65535": _good_record(port=65536),
    "a port that is true": _good_record(port=True),
    "a mode that is not one": _good_record(mode="passive"),
    "a state that is not one": _good_record(state="done"),
    "a code on a state that refuses nothing": _good_record(code="owner_busy"),
    "a refusal without its code": _good_record(state="refused"),
    "a refusal with a code off the list": _good_record(state="refused", code="made_up"),
    "a deadline that is not a time": _good_record(drain_deadline="soon"),
    "an update that is missing": _good_record(updated_at=None),
    "an update in another zone": _good_record(updated_at="2026-09-29T12:00:00+03:00"),
    "a file that is not JSON": b"{not json",
    "an array": b"[]",
    "a key twice": b'{"schema_version":1,"schema_version":1}',
    "NaN": b'{"schema_version":NaN}',
    "a file over 64 KiB": b" " * (64 * 1024 + 1),
}


@pytest.mark.parametrize("what", sorted(BAD_RECORDS))
def test_a_file_that_is_not_the_record_is_refused_by_name_and_left_as_it_is(tmp_path, what):
    path = _publish(tmp_path, BAD_RECORDS[what])
    before = path.read_bytes()
    with pytest.raises(up_status.StatusInvalid) as caught:
        up_status.read_status(path)
    assert path.name in str(caught.value)
    assert path.read_bytes() == before


def test_the_reader_accepts_every_record_the_spec_shows_so_the_refusals_mean_something(tmp_path):
    for state in up_status.STATES:
        code = "start_failed" if state == "refused" else None
        path = _publish(tmp_path, _good_record(state=state, code=code, mode="view"))
        assert up_status.read_status(path).state == state


def test_every_state_the_writers_publish_is_one_the_reader_accepts():
    source = Path(up_status.__file__).parent
    pattern = re.compile(r"""(?:status\.write|_report\(status,)\s*\(?\s*["']([a-z_]+)["']""")
    published = {state for name in ("up_serve.py", "server_drain.py")
                 for state in pattern.findall((source / name).read_text(encoding="utf-8"))}
    assert published and published <= set(up_status.STATES), published - set(up_status.STATES)
