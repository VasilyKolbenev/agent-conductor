"""A shared login lease from before the boot counter: prepare, restart, then recover.

Every restart here is a model (the one seam `ownership_boot.current_boot`); the real restart is
the owner's window. No test reads a token or an auth file, and one proves the code does not.
"""
from __future__ import annotations

import builtins
import io
import json
import os
import re

import pytest

from conductor import ownership, ownership_login as login, ownership_records as records
from conductor.boot_witness import BootRefused
from conductor.command.adapters.process import ProcessRunner
from conductor.ownership_native import NativeHold
from tests._boot_world import GUID, OTHER_GUID, counter, later_boot, measure
from tests.test_command_task_store import durable_bytes
from tests.test_project_ownership import activated

LEGACY = f"windows:{GUID}"
SECRET = b"synthetic-login-secret-0123456789"


def legacy_lease(tmp_path, monkeypatch, name="login", boot=LEGACY):
    """A lease whose writer is gone and whose record carries the pre-counter boot string."""
    home = tmp_path / name
    home.mkdir()
    (home / "credential.json").write_bytes(SECRET)
    measure(monkeypatch, boot)
    lease = login.LoginLease(str(home))
    lease.stack.close()
    record = json.loads((lease.box / "active.json").read_bytes())
    return home, lease.box, record


def refusal(call, *args):
    with pytest.raises(ownership.OwnerRefused) as caught:
        call(*args)
    return caught.value


def receipt_path(box, record):
    return box / f"prepared-{record['nonce']}.json"


def test_a_legacy_lease_cannot_be_recovered_even_when_the_machine_has_a_new_counter(
        tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(43))
    before = durable_bytes(box)
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required" and "--prepare-restart" in error.detail
    assert durable_bytes(box) == before and (box / "active.json").is_file()


def test_a_lease_that_took_the_counter_witness_is_a_closed_v2_record_the_old_reader_refuses(
        tmp_path, monkeypatch):
    home = tmp_path / "login"
    home.mkdir()
    measure(monkeypatch, counter(42))
    lease = login.LoginLease(str(home))
    record = dict(lease.record)
    lease.close()
    assert record["protocol"] == "conduct.login-lease.v2" and record["boot"] == counter(42)
    old_boot = re.compile(r"(?:windows|linux|darwin):[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
    assert record["protocol"] != "conduct.login-lease.v1"
    assert old_boot.fullmatch(record["boot"]) is None
    assert len(list(lease.box.glob("closed-*.json"))) == 1


def test_a_per_boot_id_lease_stays_the_v1_record(tmp_path, monkeypatch):
    linux = "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
    _, _, record = legacy_lease(tmp_path, monkeypatch, boot=linux)
    assert record["protocol"] == "conduct.login-lease.v1" and record["boot"] == linux


def test_preparing_writes_one_exclusive_receipt_bound_to_the_lease(tmp_path, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    result = login.prepare_login_recovery(str(home))
    assert result["state"] == "recovery_prepared" and result["released"] is False
    assert result["created"] is True and result["prepared_boot"] == counter(42)
    value = json.loads(receipt_path(box, record).read_bytes())
    assert value["lease_nonce"] == record["nonce"] and value["lease_boot"] == LEGACY
    assert value["lease_identity"] == record["identity"] and value["prepared_boot"] == counter(42)
    assert value["format_digest"] == record["format_digest"]
    assert value["lease_digest"] == records.digest(records.canonical(record))
    assert (box / "active.json").is_file()


def test_a_proper_later_restart_completes_the_recovery_and_the_login_is_usable_again(
        tmp_path, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    receipt = receipt_path(box, record).read_bytes()
    measure(monkeypatch, counter(43))
    assert login.recover_login(str(home))["state"] == "recovered"
    assert not (box / "active.json").exists()
    assert (box / f"recovered-{record['nonce']}.json").is_file()
    assert receipt_path(box, record).read_bytes() == receipt
    project = tmp_path / "project"
    project.mkdir()
    activated(project)
    with ownership.acquire_owner(project):
        with ProcessRunner.login_write_guard(project, str(home)):
            pass
    assert len(list(box.glob("closed-*.json"))) == 1


@pytest.mark.parametrize("now, word", [(counter(42), "restart"), (counter(41), "lower"),
                                       (counter(500, OTHER_GUID), "environment")])
def test_the_same_boot_a_lower_counter_and_another_environment_refuse_and_write_nothing(
        tmp_path, monkeypatch, now, word):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    before = durable_bytes(box)
    measure(monkeypatch, now)
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required" and word in error.detail
    assert durable_bytes(box) == before


def test_a_scheme_change_alone_is_no_restart_even_with_a_receipt_on_record(
        tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    before = durable_bytes(box)
    for now in (f"windows:{OTHER_GUID}", "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"):
        measure(monkeypatch, now)
        assert refusal(login.recover_login, str(home)).code == "login_recovery_required"
    assert durable_bytes(box) == before


def test_a_lease_record_that_mixes_its_protocol_and_its_boot_scheme_is_refused(
        tmp_path, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch, boot=counter(42))
    for changes in ({"protocol": "conduct.login-lease.v1"},
                    {"protocol": "conduct.login-lease.v2", "boot": LEGACY}):
        mixed = dict(record, **changes)
        (box / "active.json").write_bytes(records.canonical(mixed))
        mixed["identity"] = list(login.identity(box / "active.json"))
        (box / "active.json").write_bytes(records.canonical(mixed))
        measure(monkeypatch, counter(99))
        assert refusal(login.recover_login, str(home)).code == "login_ownership_invalid"
        assert refusal(login.prepare_login_recovery, str(home)).code == "login_ownership_invalid"


@pytest.mark.parametrize("field, value", [
    ("lease_nonce", "f" * 32), ("lease_identity", [1, 2]), ("lease_digest", "sha256:" + "0" * 64),
    ("lease_boot", f"windows:{OTHER_GUID}"), ("format_digest", "sha256:" + "1" * 64),
    ("prepared_boot", f"windows:{OTHER_GUID}"), ("prepared_boot", None)])
def test_a_receipt_that_is_not_bound_to_this_lease_grants_nothing(
        tmp_path, monkeypatch, field, value):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    path = receipt_path(box, record)
    path.write_bytes(records.canonical(dict(json.loads(path.read_bytes()), **{field: value})))
    measure(monkeypatch, counter(43))
    before = durable_bytes(box)
    assert refusal(login.recover_login, str(home)).code == "login_ownership_invalid"
    assert refusal(login.prepare_login_recovery, str(home)).code == "login_ownership_invalid"
    assert durable_bytes(box) == before and (box / "active.json").is_file()


def test_a_receipt_of_one_lease_does_not_serve_the_next_lease_of_the_same_box(
        tmp_path, monkeypatch):
    home, box, first = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    measure(monkeypatch, counter(43))
    login.recover_login(str(home))
    measure(monkeypatch, LEGACY)
    again = login.LoginLease(str(home))
    again.stack.close()
    second = json.loads((box / "active.json").read_bytes())
    assert second["nonce"] != first["nonce"] and receipt_path(box, first).is_file()
    measure(monkeypatch, counter(500))
    error = refusal(login.recover_login, str(home))
    assert error.code == "login_recovery_required" and "--prepare-restart" in error.detail


def test_a_receipt_copied_from_another_login_does_not_fit(tmp_path, monkeypatch):
    home_a, box_a, record_a = legacy_lease(tmp_path, monkeypatch, "login-a")
    home_b, box_b, record_b = legacy_lease(tmp_path, monkeypatch, "login-b")
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home_a))
    receipt_path(box_b, record_b).write_bytes(receipt_path(box_a, record_a).read_bytes())
    measure(monkeypatch, counter(43))
    before = durable_bytes(box_b)
    assert refusal(login.recover_login, str(home_b)).code == "login_ownership_invalid"
    assert durable_bytes(box_b) == before


def test_a_live_holder_of_the_login_is_not_displaced_by_a_preparation_or_a_recovery(
        tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    before = durable_bytes(box)
    holder = NativeHold(box / "anchor", exclusive=True, tree=True)
    try:
        assert refusal(login.prepare_login_recovery, str(home)).code == "login_owner_busy"
        assert refusal(login.recover_login, str(home)).code == "login_owner_busy"
    finally:
        holder.close()
    assert durable_bytes(box) == before


def test_a_receipt_that_is_damaged_or_partial_grants_nothing(tmp_path, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    path = receipt_path(box, record)
    whole = path.read_bytes()
    measure(monkeypatch, counter(43))
    for damaged in (b"", whole[:len(whole) // 2], whole.replace(b"\n", b' "extra":1\n'),
                    whole.replace(b"conduct.login-recovery-prepared.v1", b"conduct.other.v1"),
                    whole.rstrip(b"\n")):
        path.write_bytes(damaged)
        before = durable_bytes(box)
        assert refusal(login.recover_login, str(home)).code == "login_ownership_invalid"
        assert refusal(login.prepare_login_recovery, str(home)).code == "login_ownership_invalid"
        assert durable_bytes(box) == before and (box / "active.json").is_file()


def test_a_repeated_preparation_returns_the_first_receipt_and_does_not_refresh_it(
        tmp_path, monkeypatch):
    home, box, record = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    first = login.prepare_login_recovery(str(home))
    before = durable_bytes(box)
    measure(monkeypatch, counter(99))
    again = login.prepare_login_recovery(str(home))
    assert (first["created"], again["created"]) == (True, False)
    assert again["prepared_boot"] == counter(42) and durable_bytes(box) == before


def test_a_repeat_after_the_recovery_overwrites_no_evidence(tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    measure(monkeypatch, counter(42))
    login.prepare_login_recovery(str(home))
    measure(monkeypatch, counter(43))
    login.recover_login(str(home))
    before = durable_bytes(box)
    measure(monkeypatch, counter(44))
    for call in (login.recover_login, login.prepare_login_recovery):
        refusal(call, str(home))
    assert durable_bytes(box) == before


def test_a_lease_that_already_holds_a_comparable_boot_needs_no_receipt(tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch, boot=counter(42))
    measure(monkeypatch, counter(43))
    before = durable_bytes(box)
    error = refusal(login.prepare_login_recovery, str(home))
    assert error.code == "login_recovery_required" and "no preparation is needed" in error.detail
    assert durable_bytes(box) == before
    assert login.recover_login(str(home))["state"] == "recovered"


def test_a_per_boot_id_lease_still_recovers_by_the_difference_of_the_id(
        tmp_path, monkeypatch):
    linux = "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
    home, box, _ = legacy_lease(tmp_path, monkeypatch, boot=linux)
    measure(monkeypatch, linux)
    assert "restart the OS" in refusal(login.recover_login, str(home)).detail
    measure(monkeypatch, later_boot(linux))
    assert login.recover_login(str(home))["state"] == "recovered"


def test_a_boot_that_cannot_be_measured_prepares_and_recovers_nothing(tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)

    def unreadable():
        raise BootRefused("layout_unknown", "the page is not the documented one")
    measure(monkeypatch, unreadable)
    before = durable_bytes(box)
    for call in (login.prepare_login_recovery, login.recover_login):
        error = refusal(call, str(home))
        assert error.code == "login_recovery_required" and "documented" in error.detail
    assert durable_bytes(box) == before


def test_a_lease_is_not_taken_when_the_boot_cannot_be_measured(tmp_path, monkeypatch):
    home = tmp_path / "login"
    home.mkdir()

    def unreadable():
        raise BootRefused("partial_read", "only 16 of 736 bytes were read")
    measure(monkeypatch, unreadable)
    error = refusal(login.LoginLease, str(home))
    assert error.code == "ownership_unavailable" and "shared login lease" in error.detail
    _, box = login._route(str(home))
    assert not (box / "active.json").exists()


def test_preparing_and_recovering_never_open_a_file_of_the_login_home(tmp_path, monkeypatch):
    home, box, _ = legacy_lease(tmp_path, monkeypatch)
    opened = []
    real_open, real_io, real_os = builtins.open, io.open, os.open

    def spying(real):
        def spy(path, *args, **kwargs):
            opened.append(str(path))
            return real(path, *args, **kwargs)
        return spy
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", spying(real_open))
        patch.setattr(io, "open", spying(real_io))
        patch.setattr(os, "open", spying(real_os))
        measure(patch, counter(42))
        login.prepare_login_recovery(str(home))
        measure(patch, counter(43))
        login.recover_login(str(home))
    inside = [path for path in opened if str(home) in path and str(box) not in path]
    assert inside == [] and any(str(box) in path for path in opened)
    assert (home / "credential.json").read_bytes() == SECRET
    assert all(SECRET not in payload for payload in durable_bytes(box).values())
