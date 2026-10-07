"""A project record met in another boot environment: an explicit new preparation, then a Restart.

A preparation records the counter a later recovery must exceed, and a counter is comparable only
inside one boot environment. When the environment changes after a record (or after a preparation)
was made, another Restart cannot make the old environment the current one, so the product used to
have no exit. The exit is a NEW immutable preparation, written only by an explicit
`--prepare-restart`, that binds the earlier history and the new measurement and grants nothing: a
Restart inside the new environment is still required, and `recover` never creates the transition.

Every restart here is a model (the one seam `ownership_boot.current_boot`); the real one is the
owner's window. The four objects of the review's question 6 are the two cases below and, in
`test_login_scope_change`, the same two for a shared login lease.
"""
from __future__ import annotations

import json
import shutil

import pytest

from conductor import __main__ as cli, ownership, ownership_records as records
from conductor import ownership_transition as transition
from conductor.boot_witness import BootRefused
from conductor.ownership_native import NativeHold
from tests._boot_world import GUID, OTHER_GUID, assert_plain_restart_advice, counter, measure
from tests.test_command_task_store import durable_bytes
from tests.test_project_recovery_prepare import LEGACY, abandoned_legacy, refusal, tree

NOW_A = counter(42)
NOW_B = counter(500, OTHER_GUID)


def prepared_in_a(root, monkeypatch):
    """Case 1: a legacy record that was prepared while the machine read counter 42 of scope A."""
    abandoned_legacy(root)
    measure(monkeypatch, NOW_A)
    return transition.prepare_recovery(root)[0]


def counter_record_of_a(root, monkeypatch):
    """Case 2: an abandoned owner whose own record holds counter 42 of scope A."""
    return abandoned_legacy(root, boot=NOW_A)


CASES = pytest.mark.parametrize("start", [prepared_in_a, counter_record_of_a],
                                ids=["legacy-record-prepared-in-A", "counter-record-of-A"])


def generation_files(root):
    folder = root / ".conduct" / "ownership"
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}


def met_in_b(tmp_path, monkeypatch, start):
    old = start(tmp_path, monkeypatch)
    measure(monkeypatch, NOW_B)
    return old


@CASES
def test_a_plain_recover_in_another_environment_names_the_explicit_action_and_writes_nothing(
        tmp_path, monkeypatch, start):
    old = met_in_b(tmp_path, monkeypatch, start)
    before = tree(tmp_path)
    error = refusal(transition.recover, tmp_path)
    assert error.code == "recovery_required"
    assert "--prepare-restart" in error.detail and "environment" in error.detail
    assert "no preparation is needed" not in error.detail
    assert_plain_restart_advice(error.detail)
    assert tree(tmp_path) == before and records.chain(tmp_path) == old


@CASES
def test_no_entrance_other_than_the_explicit_preparation_writes_the_transition(
        tmp_path, monkeypatch, start):
    met_in_b(tmp_path, monkeypatch, start)
    before = tree(tmp_path)
    assert refusal(ownership.acquire_owner, tmp_path).code == "recovery_required"
    assert refusal(ownership.require_owner, tmp_path).code == "owner_required"
    assert refusal(transition.rollback, tmp_path, legacy_writers_stopped=True
                   ).code == "rollback_refused"
    refusal(transition.recover, tmp_path)
    assert tree(tmp_path) == before


@CASES
def test_the_explicit_preparation_writes_one_new_immutable_record_bound_to_the_old_history(
        tmp_path, monkeypatch, start):
    old = met_in_b(tmp_path, monkeypatch, start)
    data = durable_bytes(tmp_path / "conductor.v3")
    files = generation_files(tmp_path)
    new, created = transition.prepare_recovery(tmp_path)
    assert created is True and new["phase"] == "recovery_prepared"
    assert new["prepared_boot"] == NOW_B and new["boot_id"] == old["boot_id"]
    assert new["session_id"] == old["session_id"] and new["recovered_session"] is None
    assert new["previous_digest"] == records.digest(records.canonical(old))
    assert new["generation"] == old["generation"] + 1 and records.chain(tmp_path) == new
    after = generation_files(tmp_path)
    assert {name: after[name] for name in files} == files and len(after) == len(files) + 1
    assert durable_bytes(tmp_path / "conductor.v3") == data


@CASES
def test_the_new_preparation_grants_nothing_until_a_restart_inside_the_new_environment(
        tmp_path, monkeypatch, start):
    met_in_b(tmp_path, monkeypatch, start)
    transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    error = refusal(transition.recover, tmp_path)
    assert error.code == "recovery_required" and "restart" in error.detail
    assert_plain_restart_advice(error.detail)
    assert refusal(ownership.acquire_owner, tmp_path).code == "recovery_required"
    assert refusal(ownership.require_owner, tmp_path).code == "owner_required"
    assert tree(tmp_path) == before


@CASES
def test_a_restart_inside_the_new_environment_completes_the_recovery_and_the_owner_closes(
        tmp_path, monkeypatch, start):
    old = met_in_b(tmp_path, monkeypatch, start)
    data = durable_bytes(tmp_path / "conductor.v3")
    transition.prepare_recovery(tmp_path)
    measure(monkeypatch, counter(501, OTHER_GUID))
    done = transition.recover(tmp_path)
    assert done["phase"] == "recovered" and done["boot_id"] == counter(501, OTHER_GUID)
    assert done["recovered_session"] == old["session_id"] and done["prepared_boot"] == NOW_B
    assert durable_bytes(tmp_path / "conductor.v3") == data
    with ownership.acquire_owner(tmp_path):
        assert records.chain(tmp_path)["boot_id"] == counter(501, OTHER_GUID)
    assert records.chain(tmp_path)["phase"] == "closed"


@CASES
@pytest.mark.parametrize("now", [counter(900, OTHER_GUID), counter(3, OTHER_GUID), NOW_B])
def test_a_repeat_in_the_new_environment_returns_the_new_preparation_and_moves_no_baseline(
        tmp_path, monkeypatch, start, now):
    met_in_b(tmp_path, monkeypatch, start)
    first, _ = transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    measure(monkeypatch, now)
    again, created = transition.prepare_recovery(tmp_path)
    assert created is False and again == first and again["prepared_boot"] == NOW_B
    assert tree(tmp_path) == before


@CASES
def test_a_second_change_of_environment_is_prepared_again_and_only_the_newest_one_counts(
        tmp_path, monkeypatch, start):
    met_in_b(tmp_path, monkeypatch, start)
    in_b, _ = transition.prepare_recovery(tmp_path)
    measure(monkeypatch, counter(43))
    in_a_again, created = transition.prepare_recovery(tmp_path)
    assert created is True and in_a_again["prepared_boot"] == counter(43)
    assert in_a_again["previous_digest"] == records.digest(records.canonical(in_b))
    measure(monkeypatch, counter(501, OTHER_GUID))
    assert refusal(transition.recover, tmp_path).code == "recovery_required"
    measure(monkeypatch, counter(44))
    assert transition.recover(tmp_path)["prepared_boot"] == counter(43)


def test_a_counter_record_prepares_nothing_in_its_own_environment_whatever_the_counter(
        tmp_path, monkeypatch):
    abandoned_legacy(tmp_path, boot=NOW_A)
    before = tree(tmp_path)
    for now, word in ((counter(42), "full Restart"), (counter(41), "lower"),
                      (counter(43), "already proven")):
        measure(monkeypatch, now)
        error = refusal(transition.prepare_recovery, tmp_path)
        assert error.code == "recovery_refused" and word in error.detail, now
        assert tree(tmp_path) == before
    assert transition.recover(tmp_path)["boot_id"] == counter(43)


def test_a_preparation_that_stands_is_the_answer_in_its_own_environment_whatever_the_counter(
        tmp_path, monkeypatch):
    first = prepared_in_a(tmp_path, monkeypatch)
    before = tree(tmp_path)
    for now in (counter(41), counter(42), counter(43)):
        measure(monkeypatch, now)
        again, created = transition.prepare_recovery(tmp_path)
        assert created is False and again == first
    assert tree(tmp_path) == before


READER_REFUSALS = ["layout_unknown", "partial_read", "native_unavailable", "value_empty",
                   "counter_overflow"]


@CASES
@pytest.mark.parametrize("code", READER_REFUSALS)
def test_an_unreadable_boot_is_never_a_way_to_prepare_again(tmp_path, monkeypatch, start, code):
    start(tmp_path, monkeypatch)

    def unreadable():
        raise BootRefused(code, "the page cannot be used as a measurement")
    measure(monkeypatch, unreadable)
    before = tree(tmp_path)
    error = refusal(transition.prepare_recovery, tmp_path)
    assert error.code == "recovery_required" and f"{code}:" in error.detail
    assert tree(tmp_path) == before


UNUSABLE = [f"windows-bootid.v1:{OTHER_GUID}:4294967295", "", f"windows:{OTHER_GUID}",
            "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"]


@CASES
@pytest.mark.parametrize("now", UNUSABLE)
def test_a_measurement_that_is_no_usable_counter_prepares_nothing(
        tmp_path, monkeypatch, start, now):
    start(tmp_path, monkeypatch)
    measure(monkeypatch, now)
    before = tree(tmp_path)
    error = refusal(transition.prepare_recovery, tmp_path)
    assert error.code == "recovery_required"
    assert tree(tmp_path) == before


@CASES
def test_a_live_holder_of_the_project_is_not_displaced_by_the_new_preparation(
        tmp_path, monkeypatch, start):
    met_in_b(tmp_path, monkeypatch, start)
    before = tree(tmp_path)
    holder = NativeHold(tmp_path / ".conduct" / ".conduct-owner", exclusive=True)
    try:
        assert refusal(transition.prepare_recovery, tmp_path).code == "recovery_refused"
    finally:
        holder.close()
    assert tree(tmp_path) == before


@CASES
def test_the_new_preparation_checks_the_live_layout_like_the_first_one(
        tmp_path, monkeypatch, start):
    met_in_b(tmp_path, monkeypatch, start)
    (tmp_path / "conductor").write_bytes(b"not the fence")
    before = tree(tmp_path)
    assert refusal(transition.prepare_recovery, tmp_path).code == "ownership_lost"
    assert tree(tmp_path) == before


@CASES
@pytest.mark.parametrize("field, value", [
    ("nonce", "f" * 32), ("root_identity", [1, 2]), ("data_identity", [3, 4]),
    ("data_digest", "sha256:" + "0" * 64)])
def test_a_head_whose_bound_objects_changed_refuses_the_new_preparation(
        tmp_path, monkeypatch, start, field, value):
    old = met_in_b(tmp_path, monkeypatch, start)
    target = tmp_path / ".conduct" / "ownership" / f"gen-{old['generation']:08d}.json"
    target.write_bytes(records.canonical(dict(old, **{field: value})))
    before = tree(tmp_path)
    for call in (transition.prepare_recovery, transition.recover, ownership.acquire_owner):
        assert refusal(call, tmp_path).code in {"transition_conflict", "ownership_lost"}
    assert tree(tmp_path) == before


@CASES
def test_an_earlier_generation_that_was_changed_refuses_the_new_preparation(
        tmp_path, monkeypatch, start):
    old = met_in_b(tmp_path, monkeypatch, start)
    earlier = tmp_path / ".conduct" / "ownership" / f"gen-{old['generation'] - 1:08d}.json"
    earlier.write_bytes(earlier.read_bytes().replace(b'"schema":1', b'"schema":1,"x":0'))
    before = tree(tmp_path)
    for call in (transition.prepare_recovery, transition.recover, ownership.acquire_owner):
        assert refusal(call, tmp_path).code == "transition_conflict"
    assert tree(tmp_path) == before


def forge_next(root, head, **changes):
    """A generation written the way a hostile or buggy writer would: no judgment at all."""
    value = dict(head, **changes)
    value.update(generation=head["generation"] + 1,
                 previous_digest=records.digest(records.canonical(head)))
    records.exclusive(root / ".conduct" / "ownership" / f"gen-{value['generation']:08d}.json",
                      records.canonical(value))
    return value


@CASES
@pytest.mark.parametrize("changes", [
    {"prepared_boot": counter(900, GUID)},            # the standing environment again
    {"prepared_boot": counter(900, OTHER_GUID), "session_id": "e" * 32},
    {"prepared_boot": counter(900, OTHER_GUID), "boot_id": counter(7)},
    {"prepared_boot": counter(900, OTHER_GUID), "recovered_session": "d" * 32},
    {"prepared_boot": f"windows:{OTHER_GUID}"}])
def test_a_forged_second_preparation_is_refused_by_the_history_and_every_entrance(
        tmp_path, monkeypatch, start, changes):
    head = start(tmp_path, monkeypatch)
    forge_next(tmp_path, head, schema=2, phase="recovery_prepared", **changes)
    measure(monkeypatch, counter(901, OTHER_GUID))
    before = tree(tmp_path)
    for call in (transition.recover, transition.prepare_recovery, ownership.acquire_owner,
                 records.state):
        assert refusal(call, tmp_path).code == "transition_conflict"
    assert tree(tmp_path) == before


@CASES
def test_a_new_preparation_taken_from_another_project_does_not_fit_this_chain(
        tmp_path, monkeypatch, start):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    start(first, monkeypatch)
    start(second, monkeypatch)
    measure(monkeypatch, NOW_B)
    transition.prepare_recovery(first)
    name = f"gen-{records.chain(first)['generation']:08d}.json"
    shutil.copyfile(first / ".conduct" / "ownership" / name,
                    second / ".conduct" / "ownership" / name)
    measure(monkeypatch, counter(501, OTHER_GUID))
    assert refusal(transition.recover, second).code == "transition_conflict"
    assert refusal(ownership.acquire_owner, second).code == "transition_conflict"


@CASES
def test_after_the_new_preparation_the_old_environment_no_longer_recovers(
        tmp_path, monkeypatch, start):
    met_in_b(tmp_path, monkeypatch, start)
    transition.prepare_recovery(tmp_path)
    before = tree(tmp_path)
    measure(monkeypatch, counter(43))
    error = refusal(transition.recover, tmp_path)
    assert error.code == "recovery_required" and "environment" in error.detail
    assert tree(tmp_path) == before


@CASES
def test_a_history_that_changed_after_it_was_read_refuses_the_new_preparation(
        tmp_path, monkeypatch, start):
    old = met_in_b(tmp_path, monkeypatch, start)
    stale = dict(old, generation=old["generation"] - 1)
    monkeypatch.setattr(transition, "_abandoned", lambda root, verb: (tmp_path.resolve(), stale))
    before = tree(tmp_path)
    assert refusal(transition.prepare_recovery, tmp_path).code == "transition_conflict"
    assert tree(tmp_path) == before


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@CASES
def test_the_command_prepares_in_the_new_environment_and_says_ownership_is_not_released(
        tmp_path, monkeypatch, capsys, start):
    met_in_b(tmp_path, monkeypatch, start)
    code, out, err = run(capsys, "ownership", "recover", "--prepare-restart", "--dir",
                         str(tmp_path))
    result = json.loads(out)
    assert code == 0 and result["state"] == "recovery_prepared" and result["released"] is False
    assert result["created"] is True and result["prepared_boot"] == NOW_B
    assert "NOT released" in err and "Restart" in err and "no preparation is needed" not in err
    code, out, _ = run(capsys, "ownership", "status", "--dir", str(tmp_path))
    assert json.loads(out)["state"] == "recovery_prepared"


@CASES
def test_the_plain_command_in_another_environment_refuses_with_the_exact_action_only(
        tmp_path, monkeypatch, capsys, start):
    met_in_b(tmp_path, monkeypatch, start)
    before = tree(tmp_path)
    code, out, err = run(capsys, "ownership", "recover", "--dir", str(tmp_path))
    assert code == 1 and out == "" and "--prepare-restart" in err and "environment" in err
    assert "no preparation is needed" not in err and tree(tmp_path) == before
