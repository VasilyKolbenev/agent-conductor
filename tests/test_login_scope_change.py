"""A shared login lease met in another boot environment: an explicit new receipt, then a Restart.

The same exit as for a project (`test_project_scope_change`), for the two login objects of the
review's question 6: a legacy lease whose receipt was made in scope A, and a lease that already
holds a counter of scope A. A NEW immutable receipt, written only by `--prepare-restart`, binds the
lease, the previous receipt and its digest, and the new measurement; it grants nothing, and
`recover_login` never writes it. Receipts form a chain `prepared-<nonce>.json`,
`prepared-<nonce>-1.json`, ... that the checker reads whole.

Every restart is a model (the seam `ownership_boot.current_boot`). No test reads a token or a login
file.
"""
from __future__ import annotations

import json

import pytest

from conductor import __main__ as cli, ownership, ownership_login as login
from conductor import ownership_records as records
from conductor.boot_witness import BootRefused
from conductor.command.adapters.process import ProcessRunner
from conductor.ownership_native import NativeHold
from tests._boot_world import (GUID, OTHER_GUID, assert_plain_restart_advice, counter, later_boot,
                               measure)
from tests.test_command_task_store import durable_bytes
from tests.test_login_recovery_prepare import legacy_lease, receipt_path, refusal
from tests.test_project_ownership import activated

NOW_A = counter(42)
NOW_B = counter(500, OTHER_GUID)
V1 = "conduct.login-recovery-prepared.v1"
V2 = "conduct.login-recovery-prepared.v2"


def receipt_in_a(tmp_path, monkeypatch):
    """Case 3: a legacy lease that was prepared while the machine read counter 42 of scope A."""
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, NOW_A)
    login.prepare_login_recovery(str(home))
    return home, box, record


def counter_lease_of_a(tmp_path, monkeypatch):
    """Case 4: a lease that itself holds counter 42 of scope A."""
    return legacy_lease(tmp_path, monkeypatch, boot=NOW_A)


CASES = pytest.mark.parametrize("start", [receipt_in_a, counter_lease_of_a],
                                ids=["legacy-lease-receipt-in-A", "counter-lease-of-A"])


def names(box, record):
    return sorted(path.name for path in box.glob(f"prepared-{record['nonce']}*"))


def numbered(box, record, index):
    suffix = "" if index == 0 else f"-{index}"
    return box / f"prepared-{record['nonce']}{suffix}.json"


def stored(box, record):
    count = len(names(box, record))
    return [json.loads(numbered(box, record, i).read_bytes()) for i in range(count)]


def in_b(tmp_path, monkeypatch, start):
    home, box, record = start(tmp_path, monkeypatch)
    measure(monkeypatch, NOW_B)
    return home, box, record


@CASES
def test_a_plain_recover_in_another_environment_names_the_explicit_action_and_writes_nothing(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    before = durable_bytes(box)
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required"
    assert "--prepare-restart" in error.detail and "environment" in error.detail
    assert "no preparation is needed" not in error.detail
    assert_plain_restart_advice(error.detail)
    assert durable_bytes(box) == before and (box / "active.json").is_file()


@CASES
def test_the_explicit_preparation_writes_one_new_immutable_receipt_bound_to_the_lease(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    old = durable_bytes(box)
    result = login.prepare_login_recovery(str(home))
    assert result["state"] == "recovery_prepared" and result["released"] is False
    assert result["created"] is True and result["prepared_boot"] == NOW_B
    after = durable_bytes(box)
    assert {name: after[name] for name in old} == old and len(after) == len(old) + 1
    newest = stored(box, record)[-1]
    assert newest["prepared_boot"] == NOW_B and newest["lease_nonce"] == record["nonce"]
    assert newest["lease_identity"] == record["identity"] and newest["lease_boot"] == record["boot"]
    assert newest["format_digest"] == record["format_digest"]
    assert newest["lease_digest"] == records.digest(records.canonical(record))
    assert (box / "active.json").is_file()


def test_a_legacy_lease_gets_a_numbered_receipt_that_binds_the_digest_of_the_one_before(
        tmp_path, monkeypatch):
    home, box, record = in_b(tmp_path, monkeypatch, receipt_in_a)
    first = numbered(box, record, 0).read_bytes()
    login.prepare_login_recovery(str(home))
    assert names(box, record) == [f"prepared-{record['nonce']}-1.json",
                                  f"prepared-{record['nonce']}.json"]
    second = json.loads(numbered(box, record, 1).read_bytes())
    assert second["protocol"] == V2 and second["sequence"] == 1
    assert second["previous_digest"] == records.digest(first)
    assert numbered(box, record, 0).read_bytes() == first


def test_a_counter_lease_gets_its_first_receipt_in_the_closed_first_shape(tmp_path, monkeypatch):
    home, box, record = in_b(tmp_path, monkeypatch, counter_lease_of_a)
    login.prepare_login_recovery(str(home))
    assert names(box, record) == [f"prepared-{record['nonce']}.json"]
    first = json.loads(numbered(box, record, 0).read_bytes())
    assert first["protocol"] == V1 and "sequence" not in first and first["lease_boot"] == NOW_A


@CASES
def test_the_new_receipt_grants_nothing_until_a_restart_inside_the_new_environment(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    login.prepare_login_recovery(str(home))
    before = durable_bytes(box)
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required" and "restart" in error.detail
    assert_plain_restart_advice(error.detail)
    assert durable_bytes(box) == before and (box / "active.json").is_file()


@CASES
def test_a_restart_inside_the_new_environment_completes_the_recovery_and_the_login_is_usable(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    login.prepare_login_recovery(str(home))
    receipts = {name: (box / name).read_bytes() for name in names(box, record)}
    measure(monkeypatch, counter(501, OTHER_GUID))
    assert login.recover_login(str(home))["state"] == "recovered"
    assert not (box / "active.json").exists()
    assert (box / f"recovered-{record['nonce']}.json").is_file()
    assert {name: (box / name).read_bytes() for name in receipts} == receipts
    project = tmp_path / "project"
    project.mkdir()
    activated(project)
    measure(monkeypatch, counter(502, OTHER_GUID))
    with ownership.acquire_owner(project):
        with ProcessRunner.login_write_guard(project, str(home)):
            pass


@CASES
@pytest.mark.parametrize("now", [counter(900, OTHER_GUID), counter(3, OTHER_GUID), NOW_B])
def test_a_repeat_in_the_new_environment_returns_the_new_receipt_and_moves_no_baseline(
        tmp_path, monkeypatch, start, now):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    login.prepare_login_recovery(str(home))
    before = durable_bytes(box)
    measure(monkeypatch, now)
    again = login.prepare_login_recovery(str(home))
    assert again["created"] is False and again["prepared_boot"] == NOW_B
    assert durable_bytes(box) == before


@CASES
def test_a_second_change_of_environment_is_prepared_again_and_only_the_newest_one_counts(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    login.prepare_login_recovery(str(home))
    before = len(names(box, record))
    measure(monkeypatch, counter(43))
    assert login.prepare_login_recovery(str(home))["created"] is True
    chain = stored(box, record)
    assert len(chain) == before + 1 and chain[-1]["prepared_boot"] == counter(43)
    assert chain[-1]["previous_digest"] == records.digest(records.canonical(chain[-2]))
    measure(monkeypatch, counter(501, OTHER_GUID))
    assert refusal(login.recover_login, str(home)).code == "login_recovery_required"
    measure(monkeypatch, counter(44))
    assert login.recover_login(str(home))["state"] == "recovered"


def test_a_counter_lease_prepares_nothing_in_its_own_environment_whatever_the_counter(
        tmp_path, monkeypatch):
    home, box, record = counter_lease_of_a(tmp_path, monkeypatch)
    before = durable_bytes(box)
    for now, word in ((counter(42), "full Restart"), (counter(41), "lower"),
                      (counter(43), "already proven")):
        measure(monkeypatch, now)
        error = refusal(login.prepare_login_recovery, str(home))
        assert error.code == "login_recovery_required" and word in error.detail, now
        assert durable_bytes(box) == before
    assert login.recover_login(str(home))["state"] == "recovered"


def test_a_receipt_that_stands_is_the_answer_in_its_own_environment_whatever_the_counter(
        tmp_path, monkeypatch):
    home, box, record = receipt_in_a(tmp_path, monkeypatch)
    before = durable_bytes(box)
    for now in (counter(41), counter(42), counter(43)):
        measure(monkeypatch, now)
        assert login.prepare_login_recovery(str(home))["created"] is False
    assert durable_bytes(box) == before


READER_REFUSALS = ["layout_unknown", "partial_read", "native_unavailable", "value_empty",
                   "counter_overflow"]


@CASES
@pytest.mark.parametrize("code", READER_REFUSALS)
def test_an_unreadable_boot_is_never_a_way_to_prepare_again(tmp_path, monkeypatch, start, code):
    home, box, record = start(tmp_path, monkeypatch)

    def unreadable():
        raise BootRefused(code, "the page cannot be used as a measurement")
    measure(monkeypatch, unreadable)
    before = durable_bytes(box)
    error = refusal(login.prepare_login_recovery, str(home))
    assert error.code == "login_recovery_required" and f"{code}:" in error.detail
    assert durable_bytes(box) == before


UNUSABLE = [f"windows-bootid.v1:{OTHER_GUID}:4294967295", "", f"windows:{OTHER_GUID}",
            "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"]


@CASES
@pytest.mark.parametrize("now", UNUSABLE)
def test_a_measurement_that_is_no_usable_counter_prepares_nothing(
        tmp_path, monkeypatch, start, now):
    home, box, record = start(tmp_path, monkeypatch)
    measure(monkeypatch, now)
    before = durable_bytes(box)
    assert refusal(login.prepare_login_recovery, str(home)).code == "login_recovery_required"
    assert durable_bytes(box) == before


@CASES
def test_a_live_holder_of_the_login_is_not_displaced_by_the_new_receipt(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    before = durable_bytes(box)
    holder = NativeHold(box / "anchor", exclusive=True, tree=True)
    try:
        assert refusal(login.prepare_login_recovery, str(home)).code == "login_owner_busy"
    finally:
        holder.close()
    assert durable_bytes(box) == before


def prepared_twice(tmp_path, monkeypatch):
    """A legacy lease with receipts 0 (scope A) and 1 (scope B), the machine now in scope B."""
    home, box, record = in_b(tmp_path, monkeypatch, receipt_in_a)
    login.prepare_login_recovery(str(home))
    return home, box, record


def damaged_ok(home, box):
    """Both entrances refuse, with the invalid-ownership code, and nothing is written."""
    before = durable_bytes(box)
    for call in (login.recover_login, login.prepare_login_recovery):
        assert refusal(call, str(home)).code == "login_ownership_invalid"
    assert durable_bytes(box) == before and (box / "active.json").is_file()


@pytest.mark.parametrize("field, value", [
    ("previous_digest", "sha256:" + "0" * 64), ("sequence", 2), ("sequence", 0),
    ("lease_nonce", "f" * 32), ("lease_identity", [1, 2]), ("lease_digest", "sha256:" + "0" * 64),
    ("lease_boot", f"windows:{OTHER_GUID}"), ("format_digest", "sha256:" + "1" * 64),
    ("prepared_boot", counter(900)), ("prepared_boot", f"windows:{OTHER_GUID}"),
    ("prepared_boot", None)])
def test_a_follow_up_receipt_that_does_not_bind_what_it_follows_grants_nothing(
        tmp_path, monkeypatch, field, value):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    path = numbered(box, record, 1)
    path.write_bytes(records.canonical(dict(json.loads(path.read_bytes()), **{field: value})))
    damaged_ok(home, box)


@pytest.mark.parametrize("damage", ["empty", "half", "extra", "other_protocol", "no_newline"])
def test_a_follow_up_receipt_that_is_damaged_or_partial_grants_nothing(
        tmp_path, monkeypatch, damage):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    path = numbered(box, record, 1)
    whole = path.read_bytes()
    path.write_bytes({"empty": b"", "half": whole[:len(whole) // 2],
                      "extra": whole.replace(b"\n", b' "extra":1\n'),
                      "other_protocol": whole.replace(V2.encode(), b"conduct.other.v2"),
                      "no_newline": whole.rstrip(b"\n")}[damage])
    damaged_ok(home, box)


def test_a_follow_up_receipt_in_the_shape_of_the_first_one_grants_nothing(tmp_path, monkeypatch):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    path = numbered(box, record, 1)
    value = json.loads(path.read_bytes())
    for key in ("sequence", "previous_digest"):
        value.pop(key)
    path.write_bytes(records.canonical(dict(value, protocol=V1)))
    damaged_ok(home, box)


def test_a_follow_up_in_the_environment_that_already_stands_grants_nothing(
        tmp_path, monkeypatch):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    first = json.loads(numbered(box, record, 0).read_bytes())
    follow = json.loads(numbered(box, record, 1).read_bytes())
    follow["prepared_boot"] = counter(77, GUID)
    assert first["prepared_boot"] == NOW_A
    numbered(box, record, 1).write_bytes(records.canonical(follow))
    damaged_ok(home, box)


def test_the_first_receipt_changed_after_a_follow_up_was_written_breaks_the_chain(
        tmp_path, monkeypatch):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    path = numbered(box, record, 0)
    path.write_bytes(records.canonical(dict(json.loads(path.read_bytes()),
                                            prepared_boot=counter(43))))
    damaged_ok(home, box)


def test_a_gap_in_the_numbering_grants_nothing(tmp_path, monkeypatch):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    numbered(box, record, 1).rename(numbered(box, record, 3))
    damaged_ok(home, box)


def test_a_follow_up_without_its_first_receipt_grants_nothing(tmp_path, monkeypatch):
    home, box, record = prepared_twice(tmp_path, monkeypatch)
    numbered(box, record, 0).unlink()
    damaged_ok(home, box)


@pytest.mark.parametrize("stray", ["-0.json", "-x.json", "-01.json", ".json.bak", "-1.json.tmp"])
def test_a_name_of_the_lease_that_is_not_a_receipt_of_the_chain_grants_nothing(
        tmp_path, monkeypatch, stray):
    home, box, record = receipt_in_a(tmp_path, monkeypatch)
    (box / f"prepared-{record['nonce']}{stray}").write_bytes(b"{}\n")
    measure(monkeypatch, NOW_B)
    damaged_ok(home, box)


def test_a_chain_copied_from_another_login_does_not_fit(tmp_path, monkeypatch):
    home_a, box_a, record_a = legacy_lease(tmp_path, monkeypatch, "login-a")
    home_b, box_b, record_b = legacy_lease(tmp_path, monkeypatch, "login-b")
    measure(monkeypatch, NOW_A)
    login.prepare_login_recovery(str(home_a))
    measure(monkeypatch, NOW_B)
    login.prepare_login_recovery(str(home_a))
    for index in (0, 1):
        numbered(box_b, record_b, index).write_bytes(numbered(box_a, record_a, index).read_bytes())
    before = durable_bytes(box_b)
    for call in (login.recover_login, login.prepare_login_recovery):
        assert refusal(call, str(home_b)).code == "login_ownership_invalid"
    assert durable_bytes(box_b) == before


def test_the_receipts_of_an_earlier_lease_do_not_serve_the_next_lease_of_the_same_box(
        tmp_path, monkeypatch):
    home, box, first = in_b(tmp_path, monkeypatch, receipt_in_a)
    login.prepare_login_recovery(str(home))
    measure(monkeypatch, counter(501, OTHER_GUID))
    login.recover_login(str(home))
    measure(monkeypatch, f"windows:{GUID}")
    again = login.LoginLease(str(home))
    again.stack.close()
    second = json.loads((box / "active.json").read_bytes())
    assert second["nonce"] != first["nonce"]
    measure(monkeypatch, counter(900, OTHER_GUID))
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required" and "--prepare-restart" in error.detail
    assert len(names(box, first)) == 2


@CASES
def test_after_the_new_receipt_the_old_environment_no_longer_recovers(
        tmp_path, monkeypatch, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    login.prepare_login_recovery(str(home))
    before = durable_bytes(box)
    measure(monkeypatch, counter(43))
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required" and "environment" in error.detail
    assert durable_bytes(box) == before and (box / "active.json").is_file()


def test_a_per_boot_id_lease_is_never_asked_for_receipts(tmp_path, monkeypatch):
    linux = "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
    home, box, record = legacy_lease(tmp_path, monkeypatch, boot=linux)
    (box / f"prepared-{record['nonce']}-x.json").write_bytes(b"not a receipt")
    measure(monkeypatch, later_boot(linux))
    assert login.recover_login(str(home))["state"] == "recovered"


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@CASES
def test_the_command_prepares_in_the_new_environment_and_says_the_lease_is_not_released(
        tmp_path, monkeypatch, capsys, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    code, out, err = run(capsys, "ownership", "recover-login", "--prepare-restart",
                         "--auth-home", str(home))
    result = json.loads(out)
    assert code == 0 and result["state"] == "recovery_prepared" and result["released"] is False
    assert result["created"] is True and result["prepared_boot"] == NOW_B
    assert "NOT released" in err and "recover-login" in err
    assert "no preparation is needed" not in err
    assert (box / "active.json").is_file()


@CASES
def test_the_plain_command_in_another_environment_refuses_with_the_exact_action_only(
        tmp_path, monkeypatch, capsys, start):
    home, box, record = in_b(tmp_path, monkeypatch, start)
    before = durable_bytes(box)
    code, out, err = run(capsys, "ownership", "recover-login", "--auth-home", str(home))
    assert code == 1 and out == "" and "--prepare-restart" in err and "environment" in err
    assert "no preparation is needed" not in err and durable_bytes(box) == before
