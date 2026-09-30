"""A receipt the store cannot write must not be able to stop the queue (spec 4.4.3, 4.4.4, 4.4.5).

The receipt of a start is written before the grant or the control it names, under a path made of
the run's id, the journal kind and the record's id: longer than the path of the run itself, and
the record's id may be 128 characters. So a run the run store took can have a receipt that the
Windows path budget refuses. Two things keep such a key from stalling the pump for good: the door
of `POST /command/queue` refuses it (the very judgement the write makes, asked earlier), and the
pump, meeting one that is already on file, withdraws that one permission and goes on to the entry
behind it. The trigger is made up on every platform (`refuse_receipt_budget`) and real on Windows.
"""
from __future__ import annotations

import os
from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest

from conductor.command.api_contracts import refusal_from_exception
from conductor.command.path_admission import WindowsNameError, WindowsPathError
from conductor.command.queue_bodies import parse_write
from conductor.command.queue_service import QueueService
from conductor.command.queue_store import JOURNAL_KIND, Dropped, QueueStore
from conductor.command.task_store import TaskStore
from tests.queue_fixtures import Holder, long_root, project, refuse_receipt_budget, start_body
from tests.test_queue_pump import (  # noqa: F401  (q is the fixture)
    LATER, controls, grants, paused_grant, put, put_resume, q)

KIND = JOURNAL_KIND["start"]


def test_the_store_judges_the_name_and_then_the_budget_of_a_receipt_before_any_effect(
        tmp_path, monkeypatch):
    drive = PureWindowsPath("C:/") / ("p" * 150) / "queue"
    monkeypatch.setattr(QueueStore, "queue_dir", property(lambda self: drive))
    store = QueueStore(tmp_path)
    store.admit_receipt("run", KIND, "g" * 20)
    with pytest.raises(WindowsPathError):
        store.admit_receipt("run", KIND, "g" * 100)
    with pytest.raises(WindowsNameError):                  # a device name, and over the budget too
        store.admit_receipt("run", KIND, "nul." + "g" * 100)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["start", "resume"])
def test_enqueue_refuses_a_key_whose_receipt_could_never_be_written_and_writes_nothing(
        q, monkeypatch, kind):
    granted = paused_grant(q, "run") if kind == "resume" else None
    refuse_receipt_budget(monkeypatch, "run")
    before = q.f.store.read("run").records
    with pytest.raises(WindowsPathError):
        put(q, "run") if kind == "start" else put_resume(q, granted)
    assert not q.service.store.queue_dir.exists()          # no queue file, no directory
    assert q.f.store.read("run").records == before
    assert put(q, "run-b") is True                         # a key whose receipt fits is not touched


def test_the_refusal_is_the_word_every_other_door_says_for_a_path_over_the_budget(q, monkeypatch):
    refuse_receipt_budget(monkeypatch, "run")
    with pytest.raises(WindowsPathError) as refused:
        put(q, "run")
    refusal = refusal_from_exception(refused.value)
    assert (refusal.status, refusal.code) == (422, "windows_path_too_long")


@pytest.mark.skipif(os.name != "nt", reason="the Windows path budget applies to Windows paths")
def test_at_a_root_where_the_run_fits_the_door_refuses_the_grant_whose_receipt_does_not(tmp_path):
    grant_id = "g" * 100
    probe = QueueStore(tmp_path).receipt_path("run", KIND, grant_id)
    # the receipt's private temp name is 14 characters longer than the receipt: 3 over the 259
    root = long_root(tmp_path, 262 - 14 - (len(str(probe)) - len(str(tmp_path))))
    f = project(root, "run-b")
    f.policy.driver = Holder()
    service = QueueService(f.policy, TaskStore(root), mode="active")
    f.policy.queue = service
    body = start_body(f, "run", grant_id)
    with pytest.raises(WindowsPathError):
        service.enqueue(parse_write({"run_id": "run", "start": body}, f.policy.clock()))
    assert not service.store.queue_dir.exists()
    fits = start_body(f, "run-b", "grant-b")
    assert service.enqueue(parse_write({"run_id": "run-b", "start": fits}, f.policy.clock()))


# --- an entry that is already on file: the pump withdraws it and goes on --------------------------


def test_a_start_whose_receipt_cannot_be_written_is_dropped_and_the_entry_behind_it_starts(
        q, monkeypatch):
    put(q, "run"), put(q, "run-b")                         # the door had not yet judged the path
    refuse_receipt_budget(monkeypatch, "run")
    q.f.ticks[0] = LATER
    assert q.service.start_next() is True
    assert grants(q, "run") == [] and [row.authorization_id for row in grants(q, "run-b")] == [
        "grant-1"]
    assert q.driver.active == ("run-b", "grant-1")
    assert q.service.store.read_receipt("run", KIND, "grant-1") is None
    entry, = q.service.store.read().entries
    assert entry.run_id == "run" and entry.preauthorization is None
    assert entry.dropped == Dropped("preview_refused", LATER)
    row, = q.service.read()["entries"]
    assert (row["state"], row["reason_code"]) == ("confirmation_required", "preview_refused")
    q.driver.active = None
    before = q.service.store.path.read_bytes()
    assert q.service.start_next() is False                 # nothing is tried again, nothing moves
    assert q.service.store.path.read_bytes() == before


def test_a_resume_whose_receipt_cannot_be_written_is_dropped_and_the_entry_behind_it_starts(
        q, monkeypatch):
    put_resume(q, paused_grant(q, "run"))
    put(q, "run-b")
    refuse_receipt_budget(monkeypatch, "run")
    q.f.ticks[0] = LATER
    assert q.service.start_next() is True
    assert [row.control_id for row in controls(q)] == ["pause"]      # no resume was written
    assert q.driver.active == ("run-b", "grant-1")
    entry, = q.service.store.read().entries
    assert entry.run_id == "run" and entry.dropped == Dropped("preview_refused", LATER)


@pytest.mark.skipif(os.name != "nt", reason="the Windows path budget applies to Windows paths")
def test_at_a_real_root_an_entry_the_door_never_judged_no_longer_holds_the_queue(
        tmp_path, monkeypatch):
    grant_id = "g" * 100
    probe = QueueStore(tmp_path).receipt_path("run", KIND, grant_id)
    root = long_root(tmp_path, 262 - 14 - (len(str(probe)) - len(str(tmp_path))))
    f = project(root, "run-b")
    f.policy.driver = Holder()
    real = SimpleNamespace(f=f, service=QueueService(f.policy, TaskStore(root), mode="active"))
    f.policy.queue = real.service
    with monkeypatch.context() as before_the_door:         # how such an entry came in
        before_the_door.setattr(QueueStore, "admit_receipt", lambda self, *key: None)
        put(real, "run", grant_id), put(real, "run-b", "grant-b")
    assert real.service.start_next() is True
    assert f.policy.driver.active == ("run-b", "grant-b")
    entry, = real.service.store.read().entries
    assert (entry.run_id, entry.dropped.reason_code) == ("run", "preview_refused")
