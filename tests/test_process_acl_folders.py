"""An attempt that stands on EXISTING folders owns only two fresh ones: its parent and its runtime.

The work folder, the per-spawn home and the install folder are loans (`process_loans`). The fresh
`work` and `login` folders of the four-folder attempt would be empty, granted and unused, so this
attempt does not make them, and every proof the four-folder attempt stands on (the owner, the
boot, the identities a restart preparation binds) holds for the two it does make.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.process_acl import AttemptAclJournal
from conductor.command.adapters.process_profile import ProfileRefused
from tests._boot_world import counter, later_boot, measure
from tests._prepared_world import LEGACY_SAME_MACHINE, read, rewrite
from tests.test_process_acl import fixture

NOW = counter(42)


def applied(tmp_path, monkeypatch, *, legacy=None):
    measure(monkeypatch, NOW)
    store, acl, profile_path, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile_path, sid, "dispatch", folders=True)
    if legacy is not None:
        rewrite(record, lambda row: row.update(schema=1, boot=legacy))
    again = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    return store, again, record, paths, state


def test_a_folders_attempt_makes_the_parent_and_the_runtime_folder_and_nothing_else(
        tmp_path, monkeypatch):
    _store, _acl, record, paths, state = applied(tmp_path, monkeypatch)
    assert set(paths) == {"parent", "runtime"}
    assert sorted(child.name for child in paths["parent"].iterdir()) == ["runtime"]
    assert set(read(record)["paths"]) == {"parent", "runtime"}
    assert set(state) == {str(paths["parent"]), str(paths["runtime"])}


def test_the_runtime_folder_keeps_the_rights_of_a_fresh_folder(tmp_path, monkeypatch):
    _store, _acl, _record, paths, state = applied(tmp_path, monkeypatch)
    sddl = state[str(paths["runtime"])][0]
    assert "(A;;0x1201bf;;;" in sddl and "(A;OICIIO;0x1301bf;;;" in sddl


def test_the_proof_that_the_group_ended_retires_a_folders_attempt(tmp_path, monkeypatch):
    _store, acl, record, paths, _state = applied(tmp_path, monkeypatch)
    (paths["runtime"] / "scratch.txt").write_text("x", encoding="utf-8")
    acl.retire(record, proven=True)
    assert not paths["parent"].exists() and read(record)["phase"] == "retired"


def test_without_the_proof_and_without_a_restart_a_folders_attempt_stays(tmp_path, monkeypatch):
    _store, acl, record, paths, _state = applied(tmp_path, monkeypatch)
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        acl.retire(record)
    assert paths["runtime"].exists()


def test_a_restart_the_counter_proves_retires_a_folders_attempt_through_the_recovery(
        tmp_path, monkeypatch):
    _store, acl, record, paths, _state = applied(tmp_path, monkeypatch)
    measure(monkeypatch, later_boot(NOW))
    acl.recover()
    assert not paths["parent"].exists() and read(record)["phase"] == "retired"


def test_a_preparation_binds_the_two_objects_a_folders_record_names(tmp_path, monkeypatch):
    _store, acl, record, _paths, _state = applied(
        tmp_path, monkeypatch, legacy=LEGACY_SAME_MACHINE)
    measure(monkeypatch, counter(43))
    row, created = acl.prepare_restart(record)
    assert created is True
    assert set(row["held"]) == {"parent", "runtime"}
    assert row["held"] == {key: read(record)["paths"][key]["identity"]
                           for key in ("parent", "runtime")}
    measure(monkeypatch, counter(44))
    acl.recover()
    assert read(record)["phase"] == "retired"
