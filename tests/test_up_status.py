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
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conductor import atomic_replace, up_status

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
