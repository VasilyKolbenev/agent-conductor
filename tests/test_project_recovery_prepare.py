"""A project record from before the boot counter: prepare, restart, then recover.

Every restart here is a model: the one seam `ownership_boot.current_boot` answers. A model of a
changing counter proves the protocol, never the OS; the real restart is the owner's window.
"""
from __future__ import annotations

import shutil

import pytest

from conductor import ownership, ownership_boot, ownership_records as records
from conductor import ownership_transition as transition
from conductor.boot_witness import BootRefused
from conductor.ownership_native import NativeHold
from tests._boot_world import GUID, OTHER_GUID, counter, later_boot, measure
from tests.test_command_task_store import durable_bytes
from tests.test_project_ownership import activated
from tests.test_project_ownership_process import child

LEGACY = f"windows:{GUID}"
SESSION = "d" * 32


def abandoned_legacy(root, boot=LEGACY):
    """A project whose last owner crashed with the pre-counter boot string on record."""
    activated(root)
    return records.publish(root, records.chain(root), phase="opened", session_id=SESSION,
                           boot_id=boot, recovered_session=None)


def tree(root):
    """Every ownership-relevant byte under the project, for a before/after comparison."""
    found = {}
    for folder in (root / ".conduct", root / "conductor.v3"):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name not in {".conduct-owner", ".conduct-owner-tree"}:
                found[path.relative_to(root).as_posix()] = path.read_bytes()
    found["fence"] = (root / "conductor").read_bytes()
    return found


def refusal(call, *args, **kwargs):
    with pytest.raises(ownership.OwnerRefused) as caught:
        call(*args, **kwargs)
    return caught.value


def test_a_legacy_record_cannot_be_recovered_even_when_the_machine_has_a_new_counter(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(43))
    before = tree(tmp_path)
    error = refusal(transition.recover, tmp_path)
    assert error.code == "recovery_required" and "--prepare-restart" in error.detail
    assert tree(tmp_path) == before


def test_preparing_writes_one_non_authorizing_generation_bound_to_the_old_record(
        tmp_path, monkeypatch):
    old = abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    data = durable_bytes(tmp_path / "conductor.v3")
    prepared, created = transition.prepare_recovery(tmp_path)
    assert created is True and prepared["phase"] == "recovery_prepared"
    assert prepared["prepared_boot"] == counter(42) and prepared["boot_id"] == LEGACY
    assert prepared["session_id"] == SESSION and prepared["recovered_session"] is None
    assert prepared["previous_digest"] == records.digest(records.canonical(old))
    assert records.chain(tmp_path) == prepared
    assert durable_bytes(tmp_path / "conductor.v3") == data


def test_a_prepared_project_is_unfinished_ownership_for_every_entrance(tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    assert ownership.is_activated(tmp_path) and ownership.data_root(tmp_path).name == "conductor.v3"
    assert refusal(ownership.require_owner, tmp_path).code == "owner_required"
    error = refusal(ownership.acquire_owner, tmp_path)
    assert error.code == "recovery_required" and "not released" in error.detail
    assert refusal(transition.rollback, tmp_path, legacy_writers_stopped=True
                   ).code == "rollback_refused"
    assert refusal(transition.resume_activation, tmp_path, legacy_writers_stopped=True
                   ).code == "transition_conflict"
    assert tree(tmp_path) == before


def test_a_proper_later_restart_completes_the_recovery_and_the_owner_closes_cleanly(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    data = durable_bytes(tmp_path / "conductor.v3")
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(tmp_path)
    measure(monkeypatch, counter(43))
    done = transition.recover(tmp_path)
    assert done["phase"] == "recovered" and done["boot_id"] == counter(43)
    assert done["recovered_session"] == SESSION and done["prepared_boot"] == counter(42)
    assert durable_bytes(tmp_path / "conductor.v3") == data
    with ownership.acquire_owner(tmp_path):
        assert records.chain(tmp_path)["boot_id"] == counter(43)
    closed = records.chain(tmp_path)
    assert closed["phase"] == "closed" and closed["prepared_boot"] is None


@pytest.mark.parametrize("now, word", [(counter(42), "restart"), (counter(41), "lower"),
                                       (counter(500, OTHER_GUID), "environment")])
def test_the_same_boot_a_lower_counter_and_another_environment_refuse_and_write_nothing(
        tmp_path, monkeypatch, now, word):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    measure(monkeypatch, now)
    error = refusal(transition.recover, tmp_path)
    assert error.code == "recovery_required" and word in error.detail
    assert tree(tmp_path) == before


def test_a_scheme_change_alone_is_no_restart_even_with_a_preparation_on_record(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    for now in (f"windows:{OTHER_GUID}", "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"):
        measure(monkeypatch, now)
        assert refusal(transition.recover, tmp_path).code == "recovery_required"
    assert tree(tmp_path) == before


def test_a_history_that_jumps_from_a_legacy_opened_to_a_counter_recovery_refuses_everything(
        tmp_path, monkeypatch):
    old = abandoned_legacy(tmp_path)
    forged = dict(old, schema=2, phase="recovered", boot_id=counter(43), prepared_boot=None,
                  recovered_session=SESSION, generation=old["generation"] + 1,
                  previous_digest=records.digest(records.canonical(old)))
    records.exclusive(tmp_path / ".conduct" / "ownership" / f"gen-{forged['generation']:08d}.json",
                      records.canonical(forged))
    measure(monkeypatch, counter(44))
    before = tree(tmp_path)
    for call in (ownership.acquire_owner, transition.recover, transition.prepare_recovery,
                 records.state):
        assert refusal(call, tmp_path).code == "transition_conflict"
    assert tree(tmp_path) == before


def test_a_repeated_preparation_returns_the_first_one_and_does_not_refresh_its_measurement(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    first, created = transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    measure(monkeypatch, counter(99))
    again, created_again = transition.prepare_recovery(tmp_path)
    assert (created, created_again) == (True, False) and again == first
    assert again["prepared_boot"] == counter(42) and tree(tmp_path) == before


def test_a_preparation_taken_from_another_project_does_not_fit_this_chain(tmp_path, monkeypatch):
    first, second = tmp_path / "one", tmp_path / "two"
    abandoned_legacy(first)
    abandoned_legacy(second, boot=f"windows:{OTHER_GUID}")
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(first)
    name = f"gen-{records.chain(first)['generation']:08d}.json"
    shutil.copyfile(first / ".conduct" / "ownership" / name,
                    second / ".conduct" / "ownership" / name)
    measure(monkeypatch, counter(43))
    assert refusal(transition.recover, second).code == "transition_conflict"
    assert refusal(ownership.acquire_owner, second).code == "transition_conflict"


def test_a_preparation_of_an_earlier_session_is_not_the_preparation_of_a_later_one(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(tmp_path)
    measure(monkeypatch, counter(43))
    transition.recover(tmp_path)
    head = records.chain(tmp_path)
    crashed = records.publish(tmp_path, head, phase="opened", session_id="e" * 32,
                              boot_id=counter(43), recovered_session=None)
    assert crashed["prepared_boot"] is None
    assert refusal(transition.prepare_recovery, tmp_path).code == "recovery_refused"
    assert "no preparation is needed" in refusal(transition.prepare_recovery, tmp_path).detail
    measure(monkeypatch, counter(43))
    assert refusal(transition.recover, tmp_path).code == "recovery_required"


def test_a_live_holder_of_the_project_is_not_displaced_by_a_preparation_or_a_recovery(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    before = tree(tmp_path)
    holder = NativeHold(tmp_path / ".conduct" / ".conduct-owner", exclusive=True)
    try:
        assert refusal(transition.prepare_recovery, tmp_path).code == "recovery_refused"
        assert refusal(transition.recover, tmp_path).code == "recovery_refused"
    finally:
        holder.close()
    assert tree(tmp_path) == before


def test_a_prepared_record_that_is_damaged_or_partial_grants_nothing(tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    prepared, _ = transition.prepare_recovery(tmp_path)
    target = tmp_path / ".conduct" / "ownership" / f"gen-{prepared['generation']:08d}.json"
    whole = target.read_bytes()
    measure(monkeypatch, counter(43))
    for damaged in (b"", whole[:len(whole) // 2], whole.replace(b'"schema":2', b'"schema":9'),
                    whole.replace(counter(42).encode(), LEGACY.encode()),
                    whole.replace(b"\n", b' "extra":1\n')):
        target.write_bytes(damaged)
        before = tree(tmp_path)
        for call in (transition.recover, transition.prepare_recovery, ownership.acquire_owner):
            assert refusal(call, tmp_path).code == "transition_conflict"
        assert tree(tmp_path) == before


def test_a_repeat_after_a_completed_recovery_overwrites_no_evidence(tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    transition.prepare_recovery(tmp_path)
    measure(monkeypatch, counter(43))
    transition.recover(tmp_path)
    before = tree(tmp_path)
    measure(monkeypatch, counter(44))
    assert refusal(transition.recover, tmp_path).code == "recovery_refused"
    assert refusal(transition.prepare_recovery, tmp_path).code == "recovery_refused"
    assert tree(tmp_path) == before


def test_a_preparation_checks_the_live_layout_like_a_recovery_does(tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)
    measure(monkeypatch, counter(42))
    (tmp_path / "conductor").write_bytes(b"not the fence")
    before = tree(tmp_path)
    assert refusal(transition.prepare_recovery, tmp_path).code == "ownership_lost"
    assert tree(tmp_path) == before


def test_a_record_that_already_holds_a_comparable_boot_needs_no_preparation(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path, boot=counter(42))
    measure(monkeypatch, counter(43))
    before = tree(tmp_path)
    error = refusal(transition.prepare_recovery, tmp_path)
    assert error.code == "recovery_refused" and "no preparation is needed" in error.detail
    assert tree(tmp_path) == before
    assert transition.recover(tmp_path)["boot_id"] == counter(43)


def test_a_boot_that_cannot_be_measured_prepares_and_recovers_nothing(tmp_path, monkeypatch):
    abandoned_legacy(tmp_path)

    def unreadable():
        raise BootRefused("layout_unknown", "the page is not the documented one")
    measure(monkeypatch, unreadable)
    before = tree(tmp_path)
    for call in (transition.prepare_recovery, transition.recover):
        error = refusal(call, tmp_path)
        assert error.code == "recovery_required" and "documented" in error.detail
    assert tree(tmp_path) == before


def test_an_owner_session_is_not_opened_when_the_boot_cannot_be_measured(tmp_path, monkeypatch):
    activated(tmp_path)

    def unreadable():
        raise BootRefused("partial_read", "only 16 of 736 bytes were read")
    measure(monkeypatch, unreadable)
    before = tree(tmp_path)
    error = refusal(ownership.acquire_owner, tmp_path)
    assert error.code == "ownership_unavailable" and "partial_read" in error.detail
    assert tree(tmp_path) == before


CRASH = """
import os, sys
from conductor.ownership import acquire_owner
owner = acquire_owner(sys.argv[1])
os._exit(0)
"""


def test_a_session_that_crashed_recorded_the_boot_the_real_reader_gives_and_recovers_by_restart(
        tmp_path, monkeypatch):
    activated(tmp_path)
    assert child(tmp_path, CRASH).returncode == 0
    opened = records.chain(tmp_path)
    assert opened["phase"] == "opened" and opened["boot_id"] == ownership_boot.current_boot()
    assert refusal(transition.recover, tmp_path).code == "recovery_required"
    assert records.chain(tmp_path) == opened
    measure(monkeypatch, later_boot(opened["boot_id"]))
    assert transition.recover(tmp_path)["phase"] == "recovered"
